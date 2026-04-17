#!/usr/bin/env python3
"""Collects video-encoding news and builds a Markdown digest."""

from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

DEFAULT_FEEDS = [
    "https://news.google.com/rss/search?q=video+encoding+OR+video+codec+OR+AV1+OR+VVC+OR+HEVC",
    "https://news.google.com/rss/search?q=ffmpeg+OR+x264+OR+x265+OR+SVT-AV1+OR+libaom",
    "https://news.ycombinator.com/rss",
    "https://www.v-nova.com/feed/",
    "https://github.com/FFmpeg/FFmpeg/releases.atom",
    "https://github.com/AOMediaCodec/libavif/releases.atom",
    "https://github.com/xiph/rav1e/releases.atom",
]

DEFAULT_KEYWORDS = [
    "video encoding",
    "video codec",
    "codec",
    "transcoding",
    "av1",
    "h.264",
    "h264",
    "h.265",
    "hevc",
    "h.266",
    "vvc",
    "vp9",
    "ffmpeg",
    "x264",
    "x265",
    "svt-av1",
    "libaom",
    "rav1e",
    "webrtc",
]


@dataclass
class NewsItem:
    title: str
    link: str
    published: datetime | None
    published_raw: str
    summary: str
    source: str
    score: int
    matched_keywords: list[str]


def get_env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(item).strip() for item in data if str(item).strip()]
        except json.JSONDecodeError:
            pass
    items = [part.strip() for part in re.split(r"[\n,;]+", raw) if part.strip()]
    return items or default


def get_env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"[WARN] Invalid {name}={raw!r}. Using default {default}.", file=sys.stderr)
        return default
    if value < minimum:
        print(
            f"[WARN] {name}={value} is below minimum ({minimum}). Using default {default}.",
            file=sys.stderr,
        )
        return default
    return value


def fetch_url(url: str, timeout: int = 25) -> str | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "video-news-agent/1.0 (+https://github.com/actions)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"[WARN] Cannot fetch {url}: {exc}", file=sys.stderr)
        return None


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def child_text(element: ET.Element, names: Iterable[str]) -> str:
    wanted = set(names)
    for child in element:
        if local_name(child.tag) in wanted and child.text:
            return clean_whitespace(child.text)
    return ""


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return clean_whitespace(html.unescape(text))


def parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    iso = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url.strip())
    query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    filtered_query = [(k, v) for k, v in query_items if not k.lower().startswith("utm_")]
    cleaned = parsed._replace(
        netloc=parsed.netloc.lower(),
        query=urllib.parse.urlencode(filtered_query),
        fragment="",
    )
    return urllib.parse.urlunparse(cleaned)


def parse_feed(xml_text: str, source_url: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"[WARN] Invalid feed XML at {source_url}: {exc}", file=sys.stderr)
        return []

    rows: list[dict[str, str]] = []
    root_name = local_name(root.tag).lower()

    if root_name in {"rss", "rdf", "rdf:rdf"}:
        for item in root.iter():
            if local_name(item.tag) != "item":
                continue
            title = child_text(item, ["title"])
            link = child_text(item, ["link"])
            summary = child_text(item, ["description", "encoded", "summary", "content"])
            pub = child_text(item, ["pubDate", "published", "updated", "dc:date", "date"])
            source = child_text(item, ["source"]) or source_url
            if title and link:
                rows.append(
                    {
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "published": pub,
                        "source": source,
                    }
                )
        return rows

    # Atom feed
    if root_name == "feed":
        feed_title = child_text(root, ["title"]) or source_url
        for entry in root:
            if local_name(entry.tag) != "entry":
                continue
            title = child_text(entry, ["title"])
            summary = child_text(entry, ["summary", "content"])
            pub = child_text(entry, ["published", "updated"])
            link = ""
            for child in entry:
                if local_name(child.tag) == "link":
                    href = child.attrib.get("href", "").strip()
                    rel = child.attrib.get("rel", "alternate")
                    if href and rel in {"alternate", ""}:
                        link = href
                        break
            if title and link:
                rows.append(
                    {
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "published": pub,
                        "source": feed_title,
                    }
                )
        return rows

    print(f"[WARN] Unsupported feed format at {source_url}", file=sys.stderr)
    return []


def keyword_score(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    text_lower = text.lower()
    matched: list[str] = []
    for kw in keywords:
        if kw.lower() in text_lower:
            matched.append(kw)
    return len(matched), matched


def build_digest(items: list[NewsItem], max_items: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Video Encoding News Digest",
        "",
        f"_Generated at: {now}_",
        "",
    ]
    if not items:
        lines.extend(
            [
                "No relevant updates found for configured keywords.",
                "",
                "Try broadening `NEWS_KEYWORDS` or adding more feeds via `NEWS_FEEDS`.",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.append(f"Found **{len(items)}** relevant items. Showing top **{min(max_items, len(items))}**.")
    lines.append("")

    for idx, item in enumerate(items[:max_items], start=1):
        pub = item.published.strftime("%Y-%m-%d %H:%M UTC") if item.published else (item.published_raw or "n/a")
        match_line = ", ".join(item.matched_keywords[:6]) if item.matched_keywords else "n/a"
        lines.extend(
            [
                f"## {idx}. {item.title}",
                f"- Source: {item.source}",
                f"- Published: {pub}",
                f"- Match: {match_line}",
                f"- Link: {item.link}",
                "",
                f"{item.summary[:400]}{'...' if len(item.summary) > 400 else ''}",
                "",
            ]
        )

    return "\n".join(lines) + "\n"


def send_telegram(digest: str, items: list[NewsItem], token: str, chat_id: str) -> None:
    header = "Video Encoding Digest\n"
    if not items:
        message = header + "No relevant updates found today."
    else:
        top = items[:5]
        chunks = [header + f"Top updates: {len(items)}\n"]
        for idx, item in enumerate(top, start=1):
            chunks.append(f"{idx}. {item.title}\n{item.link}\n")
        message = "\n".join(chunks)

    # Telegram message limit is 4096 chars.
    message = message[:3900]

    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"}).encode(
        "utf-8"
    )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status >= 300:
                raise RuntimeError(f"Telegram response status: {response.status}")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Telegram delivery failed: {exc}", file=sys.stderr)


def collect_news(feeds: list[str], keywords: list[str], max_items: int) -> list[NewsItem]:
    seen: set[str] = set()
    scored: list[NewsItem] = []

    for feed_url in feeds:
        xml_text = fetch_url(feed_url)
        if not xml_text:
            continue
        for raw in parse_feed(xml_text, feed_url):
            title = strip_html(raw.get("title", ""))
            link = normalize_url(raw.get("link", ""))
            summary = strip_html(raw.get("summary", ""))
            source = strip_html(raw.get("source", "")) or urllib.parse.urlparse(feed_url).netloc
            if not title or not link:
                continue

            unique_key = link.lower()
            if unique_key in seen:
                continue
            seen.add(unique_key)

            score, matched = keyword_score(f"{title} {summary}", keywords)
            if score <= 0:
                continue

            scored.append(
                NewsItem(
                    title=title,
                    link=link,
                    published=parse_date(raw.get("published", "")),
                    published_raw=raw.get("published", ""),
                    summary=summary,
                    source=source,
                    score=score,
                    matched_keywords=matched,
                )
            )

    scored.sort(
        key=lambda item: (
            item.score,
            item.published.timestamp() if item.published else 0,
        ),
        reverse=True,
    )
    return scored[: max(max_items * 3, max_items)]


def main() -> int:
    feeds = get_env_list("NEWS_FEEDS", DEFAULT_FEEDS)
    keywords = [kw.lower() for kw in get_env_list("NEWS_KEYWORDS", DEFAULT_KEYWORDS)]
    max_items = get_env_int("NEWS_MAX_ITEMS", default=15, minimum=1)
    output_path = os.getenv("NEWS_OUTPUT_FILE", "video-news-digest.md")

    items = collect_news(feeds, keywords, max_items=max_items)
    digest = build_digest(items, max_items=max_items)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(digest)
    print(f"[INFO] Digest saved to {output_path}")
    print(f"[INFO] Relevant items: {len(items)}")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        send_telegram(digest, items, token=token, chat_id=chat_id)
        print("[INFO] Telegram notification attempted")
    else:
        print("[INFO] Telegram credentials are not set; skipping notification")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
