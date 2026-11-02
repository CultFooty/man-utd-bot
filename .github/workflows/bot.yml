name: Man Utd bot

on:
  schedule:
    - cron: "*/5 * * * *"    # every 5 minutes (GitHub sometimes runs a few minutes late)
  workflow_dispatch:          # adds a "Run workflow" button for testing

# never run two checks at once (stops double posts)
concurrency:
  group: bot
  cancel-in-progress: false

permissions:
  contents: write             # only used to keep the schedule switched on (see last step)

jobs:
  check-news:
    runs-on: ubuntu-latest
    timeout-minutes: 4
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - run: pip install -r requirements.txt

      # The bot's memory of what it already posted, carried from one check to the next
      - name: Load memory
        uses: actions/cache/restore@v4
        with:
          path: seen.json
          key: seen-${{ github.run_id }}
          restore-keys: seen-

      - name: Check news and post to Telegram
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python bot.py

      - name: Save memory
        if: always()
        uses: actions/cache/save@v4
        with:
          path: seen.json
          key: seen-${{ github.run_id }}

      # GitHub switches off schedules on repos with no changes for 60 days.
      # This makes a tiny change about once a month so the bot never stops.
      - name: Keep schedule alive
        run: |
          last=$(git log -1 --format=%ct)
          if [ $(( $(date +%s) - last )) -gt $(( 40 * 86400 )) ]; then
            date -u > keepalive.txt
            git config user.name "news-bot"
            git config user.email "news-bot@users.noreply.github.com"
            git add keepalive.txt
            git commit -m "Keep schedule alive"
            git push
          fi
