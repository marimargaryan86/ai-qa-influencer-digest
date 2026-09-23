# AI-in-QA Daily Influencer Digest

A scheduled job that collects **today's LinkedIn posts** from AI-in-QA thought leaders
and sends them to the Telegram channel **[@marimargaryan](https://t.me/marimargaryan)** via a bot.

## How it works
1. `digest.py` calls an [Apify](https://apify.com) LinkedIn scraper
   (`harvestapi~linkedin-profile-posts`) for every profile in `influencers.json`.
2. Keeps only posts **written by** the influencer (reposts / likes are skipped).
3. **Date filter:** keeps only posts published *today* in `Asia/Yerevan` time — older posts
   are skipped even if they are at the top of the feed.
4. Sends a header + one message per post (author, time, excerpt, link) through the Telegram Bot API.
   If there are no posts, sends one "📭 No new posts today" message.

Standard library only — no `pip install` needed (Python 3.9+).

## Configuration
Settings are read from environment variables, or from a local `.env` file (see `.env.example`).
`.env` is git-ignored — never commit tokens.

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from @BotFather (bot must be admin of the channel) |
| `TELEGRAM_CHAT_ID` | Channel, e.g. `@marimargaryan` |
| `APIFY_TOKEN` | Apify API token |
| `TIMEZONE` | Default `Asia/Yerevan` |
| `MAX_POSTS_PER_PROFILE` | Default `5` |

## Run
```bash
cp .env.example .env    # fill in tokens
python3 digest.py --dry-run   # print only
python3 digest.py             # send to Telegram
```

## Scheduling
- **Claude scheduled task** (current): runs daily at 23:30 Yerevan, clones this repo and runs `digest.py`.
- **GitHub Actions** (alternative): `.github/workflows/digest.yml` — add the three secrets in
  *Settings → Secrets and variables → Actions*, then uncomment the `schedule` block.
  Use only one scheduler at a time to avoid duplicate messages.
- Any cron: `30 19 * * * cd /path/to/repo && python3 digest.py`
