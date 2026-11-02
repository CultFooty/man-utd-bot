"""
Settings for the MAN UTD bot: all Manchester United news, squad, reserves,
academy, women's team, and the pundits who talk about United.
"""

BOT_NAME = "Man Utd bot"

CHECK_EVERY_SECONDS = 60     # only used when running non-stop on your own PC
MAX_AGE_HOURS = 4            # ignore stories older than this
MAX_POSTS_PER_RUN = 15       # GitHub checks every 5 minutes, so allow a few more per check
INCLUDE_LINK = True
SIMILARITY_THRESHOLD = 0.70
DEFAULT_TOPIC = "🔴 UNITED"   # label for United stories that don't fit a category below
GOOGLE_EVERY_SECONDS = 120

from urllib.parse import quote_plus as _q

_NOT_US = '-NFL -NCAA -"college football" -quarterback -touchdown'


def google(query, hours=3):
    """A Google News search (UK edition) as a feed: everything published in the last few hours."""
    return ("Google News",
            f"https://news.google.com/rss/search?hl=en-GB&gl=GB&ceid=GB:en&q="
            f"{_q(f'when:{hours}h ({query}) ' + _NOT_US)}")


MU = '("Manchester United" OR "Man Utd" OR "Man United")'

FEEDS = [
    # --- United-only feeds: everything from these is about United ---
    ("Guardian", "https://www.theguardian.com/football/manchester-united/rss"),
    ("ManUtd.com", "https://www.manutd.com/Feeds/NewsSecondRSSFeed"),
    ("Manchester Evening News", "https://www.manchestereveningnews.co.uk/all-about/manchester-united-fc?service=rss"),

    # --- All United news, across every outlet ---
    google(MU),
    google(f"{MU} (squad OR injury OR injured OR fitness OR \"ruled out\" OR \"team news\" OR captain OR dressing room)"),
    google(f"{MU} (transfer OR bid OR signing OR loan OR \"here we go\" OR contract OR target)"),
    google(f"{MU} (Ratcliffe OR INEOS OR Glazers OR Berrada OR Wilcox OR takeover OR stadium OR revenue OR sponsor)"),
    google('Carrick ("Man Utd" OR United OR "Old Trafford" OR Carrington)'),

    # --- Reserves, academy and youth ---
    google(f"{MU} (academy OR U21 OR U21s OR U18 OR U18s OR youth OR reserves OR \"FA Youth Cup\" OR \"Premier League 2\" OR loanee OR wonderkid OR teenager)", hours=6),
    google('"Manchester United Women" OR "Man Utd Women" OR "Man United Women"', hours=6),

    # --- Pundits and United voices ---
    google('"Gary Neville" OR "Roy Keane" OR "Rio Ferdinand" OR "Patrice Evra" OR "Paul Scholes" OR "Mark Goldbridge"'),
    google('"Wayne Rooney" OR "Peter Schmeichel" OR "Dimitar Berbatov" OR "Louis Saha" OR "Owen Hargreaves" OR "Nicky Butt"'),
    google('"The United Stand" OR "Stretford Paddock" OR "The Overlap" OR "Rio Ferdinand Presents" OR "Andy Mitten"', hours=6),
]

# Feeds that only carry United stories: everything from them is allowed (spam/live filters still apply).
TRUSTED_FEEDS = [url for name, url in FEEDS[:3]]
ON_TOPIC_LINK_WORDS = ["manchester-united", "man-utd", "man-united", "/mufc", "manutd.com"]

# Pundits and United voices. Anything they say gets through, about any club.
PUNDITS = [
    "gary neville", "neville", "roy keane", "keane", "rio ferdinand", "ferdinand",
    "patrice evra", "evra", "paul scholes", "scholes", "mark goldbridge", "goldbridge",
    "wayne rooney", "rooney", "peter schmeichel", "schmeichel", "dimitar berbatov", "berbatov",
    "louis saha", "owen hargreaves", "nicky butt", "the united stand", "stretford paddock",
    "the overlap", "andy mitten",
]

# For Google results, the headline must mention one of these (or a pundit).
SEARCH_MUST_MENTION = [
    "man utd", "man united", "manchester united", "united", "mufc", "red devils",
    "old trafford", "carrington", "carrick", "ratcliffe", "ineos", "glazer", "glazers",
    "berrada", "wilcox",
] + PUNDITS

# Other "Uniteds" (and United States etc.) don't count as Man Utd in a headline.
IGNORE_PHRASES = [
    "newcastle united", "leeds united", "west ham united", "sheffield united", "rotherham united",
    "cambridge united", "oxford united", "carlisle united", "peterborough united", "colchester united",
    "southend united", "hartlepool united", "torquay united", "scunthorpe united", "dundee united",
    "ayr united", "dc united", "atlanta united", "minnesota united", "united states",
    "united kingdom", "united nations", "united airlines", "united arab emirates", "united way",
]

# Categories: the first one found in the headline sets the label.
TOPICS = {
    "🎙 PUNDITS": PUNDITS,
    "🌱 ACADEMY": [
        "academy", "u21", "u21s", "under-21", "under-21s", "u18", "u18s", "under-18", "under-18s",
        "youth", "reserves", "fa youth cup", "premier league 2", "loanee", "loanees", "on loan",
        "wonderkid", "teenager", "teenage", "prospect", "graduate", "debutant", "first-team debut",
    ],
    "👩 WOMEN": ["man utd women", "man united women", "manchester united women", "wsl"],
    "👔 MANAGEMENT": [
        "carrick", "manager", "head coach", "boss", "ratcliffe", "ineos", "glazer", "glazers",
        "berrada", "wilcox", "board", "director", "sacked", "appointed",
    ],
    "🔁 TRANSFER": [
        "transfer", "transfers", "sign", "signs", "signing", "signed", "bid", "bids", "fee",
        "loan", "medical", "here we go", "release clause", "personal terms", "contract",
        "new deal", "extension", "target", "targets", "swap", "talks", "exit", "departure",
    ],
    "🩺 SQUAD": [
        "squad", "injury", "injuries", "injured", "ruled out", "fitness", "return", "returns",
        "team news", "line-up", "lineup", "starting xi", "captain", "captaincy", "dropped",
        "suspended", "suspension", "illness", "surgery", "hamstring", "selection",
    ],
    "💰 FINANCE": [
        "takeover", "stake", "investment", "revenue", "profit", "loss", "losses", "accounts",
        "debt", "wage bill", "psr", "stadium", "new stadium", "sponsor", "sponsorship",
        "shirt deal", "kit deal", "adidas", "snapdragon", "billion",
    ],
}

# Spam detector: if any of these appear in a headline, even disguised as
# "L I V E", "𝐋𝐈𝐕𝐄" or "LIVeSTREAMS", the story is dropped.
SPAM_WORDS = [
    "livestream", "watchlive", "livefree", "freelive", "freestream", "streamfree",
    "streaming", "tvchannel", "liveonline", "watchonline", "envivo", "transmision",
    "transmissao", "howtowatch", "wheretowatch", "livetv",
]

# Stories are skipped if any of these appear ANYWHERE: headline, description or link.
# (Whole words only, so "live" blocks live coverage but not "Liverpool" or "lively".)
EXCLUDE_ANYWHERE = ["live", "livestream", "live stream", "streaming", "as it happened"]

# Stories whose web address contains any of these are skipped (stream / TV-guide pages)
EXCLUDE_IN_LINK = [
    "stream", "how-to-watch", "where-to-watch", "watch-free", "watch-live", "tv-channel",
    "what-channel", "/live/", "live-blog", "/tips", "predictions",
]

# Sources (publisher names) to never post from
EXCLUDE_SOURCES = ["stream", "sportsurge", "totalsportek", "methstreams", "buffstreams", "live tv"]

# Words that make a story "high impact" -> 🔴 marker and pushed up the queue
HIGH_IMPACT = [
    "breaking", "here we go", "official", "confirmed", "confirms", "sacked", "resigns",
    "appointed", "completes", "completed", "done deal", "record", "club-record", "takeover",
    "banned", "charged", "first-team debut", "injury blow", "ruled out",
]

# Headlines containing any of these are skipped (live blogs, betting tips, other sports, etc.)
EXCLUDE = [
    # match streams / TV listings
    "stream", "streams", "streaming", "livestream", "live stream", "watch live",
    "for free", "watch free", "free live", "kick-off time", "kick off time", "ko time", "tv channel", "what channel",
    "tv coverage", "tv info", "how to watch", "where to watch", "reddit", "vs live",
    # American football and other US sports
    "nfl", "ncaa", "college football", "college football playoff", "cfp", "quarterback",
    "touchdown", "touchdowns", "super bowl", "high school", "flag football",
    "transfer portal", "heisman", "fbs", "fcs", "mls next",
    # adverts
    "hotel", "hotels", "from just", "travel deal", "holiday deal",
    # other noise
    "live", "as it happened", "quiz", "football weekly", "football daily",
    "the fiver", "predictions", "prediction", "betting tips", "odds", "tips", "fantasy",
    "fpl", "how to watch", "where to watch", "tv channel", "live stream", "highlights",
    "player ratings", "in pictures", "crossword",
    "rugby", "cricket", "nfl", "nba", "tennis", "golf", "f1", "formula 1", "boxing",
]
