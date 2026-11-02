#!/usr/bin/env python3
"""
Market & geopolitics headline bot for Telegram.

Reads news feeds, keeps only stories about markets, commodities, US policy,
central banks, conflict and geopolitics, removes duplicates, and posts short
headlines to a Telegram chat.

Usage:
  python bot.py                 run once (used by the free GitHub schedule)
  python bot.py --loop          keep running, checking for breaking news every minute
  python bot.py --dry-run       print what it would post, send nothing
  python bot.py --get-chat-id   help find your chat ID during setup

Needs two settings (environment variables):
  TELEGRAM_BOT_TOKEN   from @BotFather
  TELEGRAM_CHAT_ID     where to post (see README)
"""

import argparse
import calendar
import difflib
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import feedparser
import requests

import config

STATE_FILE = Path(os.environ.get("STATE_FILE", Path(__file__).with_name("seen.json")))
USER_AGENT = "Mozilla/5.0 (compatible; HeadlineBot/1.0)"
KEEP_SEEN_DAYS = 3


def load_settings():
    """Read TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from settings.txt next to this file."""
    path = Path(__file__).with_name("settings.txt")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            if value and "paste" not in value.lower():
                os.environ.setdefault(key.strip(), value)


load_settings()


def check_telegram():
    """Confirm the token and chat ID work, and say clearly what's wrong if not."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("\n❌ Your token or chat ID is missing.\n"
              "   Open settings.txt, paste them in after the = signs, save, and start again.\n")
        return False
    try:
        me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15).json()
    except requests.RequestException as e:
        print(f"\n❌ Couldn't reach Telegram. Check your internet connection.\n   ({e})\n")
        return False
    if not me.get("ok"):
        print("\n❌ Telegram doesn't recognise that bot token.\n"
              "   Copy it again from @BotFather (the whole thing, including the part after the colon)\n"
              "   into settings.txt. If you used /revoke, you need the new token.\n")
        return False
    name = me["result"].get("username")
    bot_name = getattr(config, "BOT_NAME", "News bot")
    ok = send_telegram(token, chat_id, f"✅ {bot_name} connected. Headlines will appear here as they break.")
    if not ok:
        print(f"\n❌ The token works (bot @{name}), but it can't message chat ID {chat_id}.\n"
              f"   Open Telegram, search for @{name}, press START, then run this again.\n"
              "   (If you're posting to a channel, the bot must be an admin of it.)\n")
        return False
    print(f"\n✅ Connected as @{name}. Check Telegram, you should have a message.\n", flush=True)
    return True


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------

def _pattern(words):
    """Whole-word, case-insensitive regex for a list of words/phrases."""
    parts = sorted((re.escape(w) for w in words), key=len, reverse=True)
    return re.compile(r"(?<![\w])(" + "|".join(parts) + r")(?![\w])", re.IGNORECASE)


TOPIC_PATTERNS = [(label, _pattern(words)) for label, words in config.TOPICS.items()]
# Optional name tags (e.g. clubs you follow): shown on the post and pushed up the queue
TAG_PATTERNS = [(name, _pattern(words)) for name, words in getattr(config, "TAGS", {}).items()]


_must = getattr(config, "SEARCH_MUST_MENTION", None)
SEARCH_CHECK = _pattern(_must) if _must else None


_link_block = getattr(config, "EXCLUDE_IN_LINK", [])
_anywhere = getattr(config, "EXCLUDE_ANYWHERE", [])
ANYWHERE_PATTERN = _pattern(_anywhere) if _anywhere else None
_source_block = [w.lower() for w in getattr(config, "EXCLUDE_SOURCES", [])]
_topic_paths = getattr(config, "ON_TOPIC_LINK_WORDS", [])


def is_on_topic(item):
    """Filters applied before a story can be posted."""
    link = (item.get("link") or "").lower()
    source = (item.get("source") or "").lower()
    if any(w in link for w in _link_block):          # e.g. ".../live-stream-how-to-watch..."
        return False
    if ANYWHERE_PATTERN and (ANYWHERE_PATTERN.search(item.get("title", ""))
                             or ANYWHERE_PATTERN.search(item.get("summary", ""))
                             or ANYWHERE_PATTERN.search(link.replace("-", " "))):
        return False                                 # e.g. "...has live coverage of..." in the description
    if any(w in source for w in _source_block):      # e.g. sites with "stream" in their name
        return False
    if item.get("feed_url") in getattr(config, "TRUSTED_FEEDS", []):
        return True                                  # dedicated football feeds we've confirmed
    if "news.google.com" not in link and any(w in link for w in _topic_paths):
        return True                                  # article lives in the site's football section
    title = item["title"]
    for phrase in getattr(config, "IGNORE_PHRASES", []):
        title = re.sub(re.escape(phrase), " ", title, flags=re.IGNORECASE)
    return bool(SEARCH_CHECK and SEARCH_CHECK.search(title))


def tags_for(title):
    found = [(m.start(), name) for name, pat in TAG_PATTERNS if (m := pat.search(title))]
    return [name for _, name in sorted(found)]  # in the order they appear in the headline
HIGH_IMPACT_PATTERN = _pattern(config.HIGH_IMPACT)
EXCLUDE_PATTERN = _pattern(config.EXCLUDE)


def classify(title, summary=""):
    """Return (topic_label, score, high_impact) or None if not relevant."""
    if EXCLUDE_PATTERN.search(title):
        return None
    text = f"{title} {summary}"
    label, score = None, 0
    for topic, pat in TOPIC_PATTERNS:
        in_title = len(pat.findall(title))
        in_text = len(pat.findall(text))
        if in_title or in_text:
            if label is None and in_title:
                label = topic
            score += in_title * 2 + (in_text - in_title)
    if score == 0:
        # Optional catch-all label for feeds that are already on-topic (e.g. football-only feeds)
        default = getattr(config, "DEFAULT_TOPIC", None)
        if not default:
            return None
        high = bool(HIGH_IMPACT_PATTERN.search(title))
        return default, 1 + (3 if high else 0), high
    if label is None:
        # matched only in the summary; require a decent signal
        if score < 2:
            return None
        for topic, pat in TOPIC_PATTERNS:
            if pat.search(text):
                label = topic
                break
    high = bool(HIGH_IMPACT_PATTERN.search(title))
    return label, score + (3 if high else 0), high


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------

def clean_title(title, source):
    title = html.unescape(re.sub(r"<[^>]+>", "", title or "")).strip()
    title = re.sub(r"\s+", " ", title)
    # Google News adds " - Publisher" to the end of each headline
    if "news.google.com" in source or source in ("Reuters", "Google News"):
        title = re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", title)
    return title


def publisher_from_google(entry, fallback):
    src = entry.get("source")
    if isinstance(src, dict) and src.get("title"):
        return src["title"]
    m = re.search(r"\s+[-–]\s+([^-–]{2,40})$", entry.get("title", ""))
    return m.group(1).strip() if m else fallback


# Stream-spam sites disguise words with styled letters (𝐋𝐈𝐕𝐄, Ｆｒｅｅ), spacing (L I V E)
# or joined words (LIVeSTREAMS). These checks see through all three.
_STYLED = re.compile("[\U0001D400-\U0001D7FF\uFF01-\uFF5E\u24B6-\u24E9\u300C-\u300F\u2295]")
_SPACED = re.compile(r"(?:\b[^\W\d_]\s+){4,}")


def looks_like_spam(text):
    if _STYLED.search(text):
        return True
    norm = unicodedata.normalize("NFKC", text)
    if _SPACED.search(norm):
        return True
    squashed = re.sub(r"[^a-z]", "", norm.lower())
    return any(w in squashed for w in getattr(config, "SPAM_WORDS", []))


_warned = set()
_fetched_once = set()      # feeds we've read at least once since starting
START_TIME = time.time()
LOOP_MODE = False          # True when running non-stop (--loop); False for one check (GitHub)
_next_due = {}    # url -> time this feed should next be checked
_feed_cache = {}  # url -> (etag, last_modified); lets sites answer "nothing new" cheaply


def fetch_feed(name, url):
    headers = {"User-Agent": USER_AGENT}
    etag, modified = _feed_cache.get(url, (None, None))
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 304:  # unchanged since last check
            return []
        if r.status_code in (429, 503):  # site says "slow down": leave it alone for 10 minutes
            _next_due[url] = time.time() + 600
            print(f"  ! {name} asked us to slow down; pausing that search for 10 minutes", file=sys.stderr)
            return []
        r.raise_for_status()
    except requests.RequestException as e:
        if url not in _warned:  # say it once, not every minute
            _warned.add(url)
            print(f"  ! could not read {name} ({url[:60]}…): {e}", file=sys.stderr)
        return []
    _feed_cache[url] = (r.headers.get("ETag"), r.headers.get("Last-Modified"))
    parsed = feedparser.parse(r.content)
    items = []
    now = time.time()
    for e in parsed.entries:
        published = e.get("published_parsed") or e.get("updated_parsed")
        ts = calendar.timegm(published) if published else now
        if now - ts > config.MAX_AGE_HOURS * 3600:
            continue
        is_google = "news.google.com" in url
        source = publisher_from_google(e, name) if is_google else name
        raw_title = clean_title(e.get("title", ""), url if is_google else name)
        if looks_like_spam(raw_title):
            continue
        title = unicodedata.normalize("NFKC", raw_title)
        if len(title) < 20:
            continue
        summary = html.unescape(re.sub(r"<[^>]+>", " ", e.get("summary", "")))
        items.append({
            "title": title,
            "summary": summary,
            "link": e.get("link", ""),
            "source": source,
            "ts": ts,
            "from_search": is_google,
            "feed_url": url,
        })
    return items


# ---------------------------------------------------------------------------
# Remembering what has been posted
# ---------------------------------------------------------------------------

def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"seen": {}, "recent_titles": []}


def save_state(state):
    cutoff = time.time() - KEEP_SEEN_DAYS * 86400
    state["seen"] = {k: v for k, v in state["seen"].items() if v > cutoff}
    state["recent_titles"] = [t for t in state["recent_titles"] if t[1] > time.time() - 86400][-400:]
    STATE_FILE.write_text(json.dumps(state))


def item_id(item):
    key = re.sub(r"\W+", "", item["title"].lower())
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def norm(title):
    return re.sub(r"[^a-z0-9 ]", "", title.lower())


def is_near_duplicate(title, recent):
    n = norm(title)
    return any(difflib.SequenceMatcher(None, n, r).ratio() >= config.SIMILARITY_THRESHOLD
               for r in recent)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def format_message(item):
    label, _, high = item["class"]
    head = ("🔴 " if high else "") + label
    if item.get("tags"):
        head += " · " + ", ".join(item["tags"])
    lines = [f"<b>{html.escape(head)}</b>", html.escape(item["title"])]
    src = html.escape(item["source"])
    if config.INCLUDE_LINK and item["link"]:
        lines.append(f'<i>{src}</i> · <a href="{html.escape(item["link"], quote=True)}">link</a>')
    else:
        lines.append(f"<i>{src}</i>")
    return "\n".join(lines)


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    for _ in range(3):
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code == 429:  # Telegram asks us to slow down
            wait = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(wait + 1)
            continue
        if not r.ok:
            print(f"  ! Telegram error {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return r.ok
    return False


def get_chat_id(token):
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
    data = r.json()
    if not data.get("ok"):
        print("Telegram said:", data)
        return
    chats = {}
    for u in data.get("result", []):
        msg = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
        chat = msg.get("chat")
        if chat:
            chats[chat["id"]] = chat.get("title") or chat.get("username") or chat.get("first_name")
    if not chats:
        print("No chats found yet. Send your bot a message (or post in your channel "
              "after adding the bot as admin), then run this again.")
    for cid, name in chats.items():
        print(f"Chat ID: {cid}    ({name})")


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run_once(dry_run=False):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not dry_run and not (token and chat_id):
        sys.exit("Put your bot token and chat ID in settings.txt first.")

    state = load_state()
    first_run = not state["seen"]
    recent = [t[0] for t in state["recent_titles"]]

    # read every feed at the same time, so a check takes seconds not minutes
    # only check feeds that are due (Google searches run less often so we don't get blocked)
    now = time.time()
    google_every = getattr(config, "GOOGLE_EVERY_SECONDS", 120)
    due = []
    for i, feed in enumerate(config.FEEDS):
        name, url = feed[0], feed[1]
        if LOOP_MODE and now < _next_due.get(url, 0):
            continue
        every = feed[2] if len(feed) > 2 else (google_every if "news.google.com" in url else 0)
        if LOOP_MODE and every and url not in _next_due:
            # on start-up, spread the Google searches over the first 2 minutes
            # instead of firing dozens at once (which can get us blocked)
            offset = (i * 7) % min(every, 120)
            if offset:
                _next_due[url] = now + offset
                continue
        _next_due[url] = now + every
        due.append((name, url))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda f: fetch_feed(*f), due))

    candidates = []
    for (_, feed_url), feed_items in zip(due, results):
        warming_up = feed_url not in _fetched_once
        _fetched_once.add(feed_url)
        for item in feed_items:
            iid = item_id(item)
            if iid in state["seen"]:
                continue
            if LOOP_MODE and warming_up and not first_run and item["ts"] < START_TIME - 600:
                # first look at this source since starting: don't dump its back catalogue
                state["seen"][iid] = time.time()
                continue
            if not is_on_topic(item):
                state["seen"][iid] = time.time()  # off-topic or a stream/spam link: never post
                continue
            cls = classify(item["title"], item["summary"])
            if not cls:
                state["seen"][iid] = time.time()  # irrelevant: don't re-check
                continue
            item["tags"] = tags_for(item["title"])
            if item["tags"]:  # tracked clubs go first, your priority clubs before the rest
                priority = getattr(config, "PRIORITY_TAGS", [])
                boost = 4 if any(t in priority for t in item["tags"]) else 2
                cls = (cls[0], cls[1] + boost, cls[2])
            item["id"], item["class"] = iid, cls
            candidates.append(item)

    # strongest stories first, then newest
    candidates.sort(key=lambda i: (i["class"][1], i["ts"]), reverse=True)

    limit = 5 if first_run else config.MAX_POSTS_PER_RUN
    to_post = []
    for item in candidates:
        if len(to_post) >= limit:
            if first_run:
                state["seen"][item["id"]] = time.time()  # skip the backlog
                continue
            break  # leave the rest for the next run
        state["seen"][item["id"]] = time.time()
        if is_near_duplicate(item["title"], recent):
            continue
        recent.append(norm(item["title"]))
        state["recent_titles"].append([norm(item["title"]), time.time()])
        to_post.append(item)

    # post oldest first so the chat reads in time order
    to_post.sort(key=lambda i: i["ts"])
    sent = failed = 0
    for item in to_post:
        msg = format_message(item)
        if dry_run:
            print(msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""), "\n")
            continue
        if send_telegram(token, chat_id, msg):
            sent += 1
        else:
            # Telegram refused it: forget it, so it's tried again next check
            failed += 1
            state["seen"].pop(item["id"], None)
            state["recent_titles"] = [t for t in state["recent_titles"] if t[0] != norm(item["title"])]
        time.sleep(1.2)  # stay under Telegram's rate limit

    if not dry_run:  # a preview shouldn't count headlines as already posted
        save_state(state)
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] checked {len(due)}/{len(config.FEEDS)} feeds · {len(candidates)} new relevant · "
          f"posted {sent if not dry_run else len(to_post)}" + (f" · {failed} FAILED" if failed else ""),
          flush=True)
    if failed and not sent and not LOOP_MODE:
        # make the GitHub run show a red cross so the problem is visible
        sys.exit("\n❌ Telegram refused every message. 'chat not found' = press START in the bot's chat "
                 "in Telegram, and check the TELEGRAM_CHAT_ID secret. 'Unauthorized' = check the "
                 "TELEGRAM_BOT_TOKEN secret.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="keep running")
    ap.add_argument("--dry-run", action="store_true", help="print instead of sending")
    ap.add_argument("--get-chat-id", action="store_true", help="show chat IDs that messaged the bot")
    args = ap.parse_args()

    if args.get_chat_id:
        token = os.environ.get("TELEGRAM_BOT_TOKEN") or input("Paste your bot token: ").strip()
        get_chat_id(token)
        return

    if args.loop:
        global LOOP_MODE
        LOOP_MODE = True
        if not args.dry_run and not check_telegram():
            sys.exit(1)
        print(f"Watching {len(config.FEEDS)} feeds every {config.CHECK_EVERY_SECONDS}s. Ctrl+C to stop.",
              flush=True)
        while True:
            started = time.time()
            try:
                run_once(args.dry_run)
            except Exception as e:  # keep going if one run fails
                print(f"Run failed: {e}", file=sys.stderr, flush=True)
            time.sleep(max(5, config.CHECK_EVERY_SECONDS - (time.time() - started)))
    else:
        run_once(args.dry_run)


if __name__ == "__main__":
    main()
