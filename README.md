# news-agent

GitHub Actions agent that collects video encoding news, builds a digest, and can send a Telegram summary.

## What it does

- Runs on schedule (`daily`) and on manual trigger (`workflow_dispatch`).
- Collects RSS/Atom updates about codecs and encoding (AV1, VVC, HEVC, FFmpeg, etc.).
- Filters and ranks items by keyword matches.
- Publishes a Markdown digest as a workflow artifact.
- Optionally sends one new item to Telegram (or nothing if no new items).
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
- `NEWS_MAX_ITEMS` (optional): ignored by design. Agent always sends at most **1** new item per run.
- `NEWS_MAX_AGE_DAYS` (optional): only include items newer than this age in days (default `14`, `0` disables age filter).
- `NEWS_SEEN_LOOKBACK_DAYS` (optional): how long sent links are remembered to avoid repeats (default `0` = keep all forever).
- `NEWS_BLOCKED_DOMAINS` (optional): comma/newline list of domains to exclude (default includes `fathomjournal.org`).
- `NEWS_BLOCKED_URL_PREFIXES` (optional): comma/newline list of URL prefixes to exclude.
  - Default includes `https://github.com/ffmpeg/ffmpeg/releases/tag/`.

Example values:

`NEWS_FEEDS`:
```json
[
  "https://news.google.com/rss/search?q=video+encoding+OR+AV1+OR+VVC",
  "https://github.com/AOMediaCodec/libavif/releases.atom"
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

- Workflow restores `.news-agent/history.json` from GitHub Actions cache.
- Script excludes links that were seen before.
- Script also excludes repeated stories by `source + normalized title` (handles same article with different Google RSS URLs).
- Script excludes repeated stories by normalized title only (across all sources) for stricter anti-repeat behavior.
- Default `NEWS_SEEN_LOOKBACK_DAYS=0` keeps all seen entries forever for strongest anti-repeat behavior.
- Script filters out too old entries using `NEWS_MAX_AGE_DAYS`.
- Script excludes blocked domains via `NEWS_BLOCKED_DOMAINS` (includes `fathomjournal.org` by default).
- Script excludes blocked URLs via `NEWS_BLOCKED_URL_PREFIXES` (includes FFmpeg release tag URLs by default).
- Agent sends exactly one new news item or nothing.
- If there are no new items, Telegram notification is skipped (no empty message is sent).
- Updated history is saved and cached for the next run.
