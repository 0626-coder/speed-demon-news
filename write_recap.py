#!/usr/bin/env python3
"""Turn one feed item into a draft original recap in content/posts.

Uses only the title, date, link, and feed summary/description. Never invents
quotes, names, results, or beef. Marks the post draft: true unless --approve
is passed (still local; it does not deploy).
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

import yaml

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "content" / "posts"
sys.path.insert(0, str(ROOT))

from build import (  # noqa: E402
    fetch_feed,
    entry_excerpt,
    entry_link,
    entry_date,
    strip_html,
    YOUTUBE_BOILER_RE,
)


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "recap"


def load_feeds() -> list[dict]:
    data = yaml.safe_load((ROOT / "feeds.yaml").read_text(encoding="utf-8"))
    return [f for f in data.get("feeds", []) if f.get("enabled", True)]


def normalize(url: str) -> str:
    parts = urlparse((url or "").strip())
    query = [(k, v) for k, v in parse_qs(parts.query, keep_blank_values=True).items() if not k.lower().startswith(("utm_", "si", "fbclid"))]
    # parse_qs values are lists
    flat = []
    for k, vals in query:
        for v in vals:
            if k.lower() in {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "si", "fbclid"}:
                continue
            flat.append((k, v))
    path = parts.path.rstrip("/") or "/"
    return urlunparse((parts.scheme, parts.netloc.lower().removeprefix("www."), path, "", "", ""))


def source_text(entry: dict) -> str:
    raw = entry.get("summary") or entry.get("description") or ""
    if not raw and entry.get("summary_detail"):
        raw = entry["summary_detail"].get("value") or ""
    if not raw and entry.get("media_description"):
        raw = entry.get("media_description")
    # Prefer a longer feed summary for recaps than the short card excerpt.
    text = strip_html(raw)
    text = YOUTUBE_BOILER_RE.split(text)[0].strip()
    text = re.sub(r"\s*(The post\s+.*Read more.*)$", "", text, flags=re.I)
    text = re.sub(r"\s*\[&?#8230;\]\s*The pos(?:t)?\s*$", "", text, flags=re.I)
    text = re.sub(r"\[\s*[…\.]+\s*\]\s*The post\s+.*$", "", text, flags=re.I)
    text = re.sub(r"The post\s+.+?appeared first on.+?$", "", text, flags=re.I)
    text = re.sub(r"\s*source\s*$", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def punch_headline(title: str) -> str:
    """Tighten the source title. Do not add claims that were not already there."""
    t = html.unescape(title or "").strip()
    t = re.sub(r"\s+", " ", t)
    t = t.replace(" & ", " and ").replace("&amp;", "and")
    t = re.sub(r"^#\S+(\s+#\S+)*\s*$", t, t)  # leave hashtag-only titles alone
    # Drop a trailing " - SourceName" if present, keep the rest.
    t = re.sub(r"\s+[|–-]\s+[A-Z][A-Za-z0-9 .]{2,30}$", "", t).strip()
    if t.isupper() and len(t) > 12:
        t = t.title()
    return t or "Draft recap"


def casual_paragraphs(text: str) -> list[str]:
    """Break the source text into short readable paragraphs without adding facts."""
    if not text:
        return []
    # Split on sentence boundaries already in the source.
    parts = re.split(r"(?<=[.!?])\s+", text)
    parts = [p.strip() for p in parts if p.strip()]
    cleaned = []
    for part in parts:
        low = part.lower()
        if any(s in low for s in ("subscribe", "sponsor", "use code", "follow me @", "social media links", "appeared first on")):
            continue
        if re.match(r"^(we|we're|i|i'm|our)\b", part, re.I):
            part = "They wrote: " + part
        cleaned.append(part)
    if not cleaned:
        return []
    # Group into paragraphs of 1-2 source sentences.
    paras = []
    buf = []
    for part in cleaned:
        buf.append(part)
        if len(" ".join(buf)) > 220 or len(buf) == 2:
            paras.append(" ".join(buf))
            buf = []
    if buf:
        paras.append(" ".join(buf))
    return paras


def write_recap(item: dict, approve: bool = False) -> Path:
    title = punch_headline(item["title"])
    source = item["source"]
    url = item["url"]
    body_paras = casual_paragraphs(item["text"])
    kind = "video" if item.get("is_video") else "article"

    credit_top = (
        f"**Source:** [{source}]({url}) — this recap is drafted from the "
        f"{kind}'s own title and the text they put in their public feed. "
        f"No names, cars, results, quotes, or beef were added on top of that."
    )
    credit_bottom = (
        f"That's what {source} published. The original {kind} is here: "
        f"[{source} — {item['title']}]({url}). If something isn't in that "
        f"source, it shouldn't be in this recap either."
    )

    if body_paras:
        lead = f"{source} ran this one under “{item['title']}.”"
        body = "\n\n".join([credit_top, lead] + body_paras + [credit_bottom])
    else:
        body = (
            f"{credit_top}\n\n"
            f"{source} ran a {kind} titled “{item['title']}.” "
            f"The feed did not include a description, so this draft stops there "
            f"instead of filling in the blanks.\n\n"
            f"{credit_bottom}"
        )

    summary = body_paras[0] if body_paras else f"A draft recap of a {source} {kind}, using only what the feed included."
    summary = summary[:220].rsplit(" ", 1)[0] + ("…" if len(summary) > 220 else "")

    post_date = item.get("date") or date.today().isoformat()
    if isinstance(item.get("dt"), datetime):
        post_date = item["dt"].date().isoformat()

    front = {
        "title": title,
        "date": post_date,
        "category": item.get("category") or "drag",
        "summary": summary,
        "image": "",
        "draft": not approve,
        "recap_of": url,
        "recap_source": source,
    }
    # Manual dump so the file stays easy to edit.
    def q(val: str) -> str:
        return '"' + str(val).replace('"', "'") + '"'

    slug = slugify(title)[:70]
    filename = f"{post_date}-{slug}.md"
    POSTS.mkdir(parents=True, exist_ok=True)
    path = POSTS / filename
    n = 2
    while path.exists():
        path = POSTS / f"{post_date}-{slug}-{n}.md"
        n += 1
    lines = [
        "---",
        f"title: {q(title)}",
        f"date: {post_date}",
        f"category: {front['category']}",
        f"summary: {q(summary)}",
        "image:",
        f"draft: {'true' if front['draft'] else 'false'}",
        f"recap_of: {url}",
        f"recap_source: {q(source)}",
        "---",
        "",
        body.rstrip() + "\n",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def collect_items(feeds: list[dict], wanted_source: str | None = None) -> list[dict]:
    items = []
    for cfg in feeds:
        if wanted_source and wanted_source.lower() not in cfg["name"].lower():
            continue
        cfg, entries, error = fetch_feed(cfg)
        if error or not entries:
            continue
        for entry in entries:
            title = strip_html(entry.get("title") or "").strip()
            link = entry_link(entry)
            if not title or not link:
                continue
            dt = entry_date(entry)
            items.append(
                {
                    "title": title,
                    "url": link,
                    "source": cfg["name"],
                    "category": cfg.get("category") or "drag",
                    "text": source_text(entry),
                    "excerpt": entry_excerpt(entry, 400),
                    "dt": dt,
                    "date": dt.date().isoformat() if dt else date.today().isoformat(),
                    "is_video": cfg.get("type") == "youtube" or "youtube.com" in link,
                    "norm": normalize(link),
                }
            )
    return items


def find_item(items: list[dict], url: str | None, query: str | None) -> dict | None:
    if url:
        target = normalize(url)
        for item in items:
            if item["norm"] == target or url.rstrip("/") in item["url"] or item["url"].rstrip("/") in url:
                return item
        # looser path match
        path = urlparse(url).path.rstrip("/")
        for item in items:
            if path and path in item["url"]:
                return item
        return None
    if query:
        q = query.lower()
        hits = [i for i in items if q in i["title"].lower() or q in i["text"].lower() or q in i["url"].lower()]
        return hits[0] if hits else None
    return items[0] if items else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Draft a recap post from one feed item. Local only.")
    parser.add_argument("--url", help="Original article or YouTube URL from a configured feed")
    parser.add_argument("--query", help="Search titles and feed text for this phrase")
    parser.add_argument("--source", help="Limit to a feed name (partial match is fine)")
    parser.add_argument("--list", action="store_true", help="List matching feed items and exit")
    parser.add_argument("--approve", action="store_true", help="Set draft: false (still does not deploy)")
    args = parser.parse_args()

    feeds = load_feeds()
    print("Fetching feeds to find a source item (feed text only)…")
    items = collect_items(feeds, args.source)
    if not items:
        print("No feed items found.", file=sys.stderr)
        return 1
    if args.list:
        for item in items[:40]:
            print(f"{item['date']}  [{item['source']}]  {item['title']}\n    {item['url']}")
        print(f"({len(items)} items)")
        return 0
    if not args.url and not args.query and not args.source:
        print("Pass --url, --query, or --source (and optionally --list).", file=sys.stderr)
        return 1
    item = find_item(items, args.url, args.query)
    if not item:
        print("Could not find that item in the configured feeds.", file=sys.stderr)
        return 1
    path = write_recap(item, approve=args.approve)
    state = "approved (draft: false)" if args.approve else "draft (not published until you set draft: false)"
    print(f"Wrote {path.relative_to(ROOT)}  [{state}]")
    print(f"Source: {item['source']} — {item['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
