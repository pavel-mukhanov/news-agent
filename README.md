# news-agent

GitHub Actions agent that collects video encoding news, builds a digest, and can send a Telegram summary.

## What it does

- Runs on schedule (`daily`) and on manual trigger (`workflow_dispatch`).
- Collects RSS/Atom updates about codecs and encoding (AV1, VVC, HEVC, FFmpeg, etc.).
- Filters and ranks items by keyword matches.
- Publishes a Markdown digest as a workflow artifact.
- Optionally sends top items to Telegram.
- Avoids repeated stories between runs using persisted history.

## Files

- `.github/workflows/video-news-agent.yml` - workflow schedule and execution.
- `scripts/video_news_digest.py` - feed parser, keyword filter, digest generator, Telegram sender.

## Setup in GitHub

### 1) Optional repository variables

Go to **Settings -> Secrets and variables -> Actions -> Variables** and configure:

- `NEWS_FEEDS` (optional): list of feed URLs.
  - Supports JSON array or comma/newline separated string.
  - If empty, defaults are used.
- `NEWS_KEYWORDS` (optional): list of matching keywords.
  - Supports JSON array or comma/newline separated string.
  - If empty, defaults are used.
- `NEWS_MAX_ITEMS` (optional): number of digest items (default `15`).
- `NEWS_MAX_AGE_DAYS` (optional): only include items newer than this age in days (default `14`, `0` disables age filter).
- `NEWS_SEEN_LOOKBACK_DAYS` (optional): how long sent links are remembered to avoid repeats (default `30`).

Example values:

`NEWS_FEEDS`:
```json
[
  "https://news.google.com/rss/search?q=video+encoding+OR+AV1+OR+VVC",
  "https://github.com/FFmpeg/FFmpeg/releases.atom"
]
```

`NEWS_KEYWORDS`:
```json
[
  "av1",
  "vvc",
  "hevc",
  "ffmpeg",
  "transcoding"
]
```

### 2) Telegram delivery (optional)

Go to **Settings -> Secrets and variables -> Actions -> Secrets** and add:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

If secrets are missing, workflow still runs and creates artifact digest, but skips Telegram send.

## Run

- Automatic: every day at `08:00 UTC` (cron in workflow).
- Manual: **Actions -> Video News Agent -> Run workflow**.

## Output

- Artifact: `video-news-digest` containing `artifacts/video-news-digest.md`.
- Job Summary: rendered digest in run summary page.

## Anti-duplicate behavior

- Workflow restores `.news-agent/sent_links.json` from GitHub Actions cache.
- Script excludes links seen within `NEWS_SEEN_LOOKBACK_DAYS`.
- Script filters out too old entries using `NEWS_MAX_AGE_DAYS`.
- Updated history is saved and cached for the next run.
