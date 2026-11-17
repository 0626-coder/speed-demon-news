#!/usr/bin/env python3
"""Rebuild the Speed-Demon News static site from feeds and local Markdown posts."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import feedparser
import frontmatter
import markdown
import yaml
from bs4 import BeautifulSoup
from bs4 import MarkupResemblesLocatorWarning
import warnings
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)
from dateutil import parser as dateparser
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
POSTS = ROOT / "content" / "posts"
FEED_CACHE = ROOT / ".feed-cache"
IMAGES = ROOT / "content" / "images"
MERCH = ROOT / "content" / "merch.yaml"
LIVE = ROOT / "content" / "live.yaml"
FOLLOW = ROOT / "content" / "follow.yaml"
WONDERLAND_YAML = ROOT / "content" / "wonderland.yaml"
WONDERLAND_POSTS = ROOT / "content" / "wonderland"
WONDERLAND_MEDIA = STATIC / "wonderland"

# Same browser UA used when the feeds were verified with curl.
# A few outlets (notably Frontstretch) return 403 to unknown bot UAs.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
TIMEOUT = 20

YOUTUBE_CHANNEL_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")

ENGINE_RE = re.compile(
    r"\b(engine|engines|engine-tech|small-block|big-block|crate engine|cylinder head|"
    r"camshaft|carburetor|dyno|ignition|lsx|ls engine|sbc|nhra stock|super stock|"
    r"power adder|nitrous|flat tappet|valvetrain|intake manifold)\b",
    re.I,
)
CATEGORY_PATTERNS = {
    "nascar": re.compile(r"\b(nascar|cup series|xfinity|craftsman truck)\b", re.I),
    "imsa": re.compile(r"\b(imsa|weathertech|le mans|wec|sportscars?|sports cars?)\b", re.I),
    "dirt": re.compile(r"\b(world of outlaws|sprint car|late model|dirt track|dirt racing)\b", re.I),
    "drag": re.compile(
        r"\b(nhra|drag racing|dragster|top fuel|funny car|pro stock|stock eliminator|"
        r"super stock|sportsman|bracket racing|dragstrip)\b",
        re.I,
    ),
}


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "post"


CATEGORY_ALIASES = {
    "outlaw-racing": "street",
    "outlaw": "street",
    "street-grudge": "street",
    "street_racing": "street",
}

PLATFORM_ORDER = ["youtube", "x", "instagram", "facebook", "tiktok"]
PLATFORM_LABELS = {
    "youtube": "YouTube",
    "x": "X",
    "twitter": "X",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "tiktok": "TikTok",
}

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*(Keep reading|Continue reading|Read more)\s*$", "", text, flags=re.I)
    return text


def shorten(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    cut = text[: limit + 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".,;: ") + "…"


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if not k.lower().startswith(("utm_", "fbclid", "gclid", "mc_"))]
    path = parts.path.rstrip("/") or "/"
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return urllib.parse.urlunsplit((parts.scheme.lower(), host, path, urllib.parse.urlencode(query), ""))


def normalize_title(title: str) -> str:
    title = unicodedata.normalize("NFKD", title or "")
    title = re.sub(r"['’]", "", title)
    title = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return re.sub(r"\s+", " ", title).strip()


def parse_date(value: Any, tz: ZoneInfo | None = None) -> datetime | None:
    """Parse a timestamp. Date-only values are midnight in tz (not UTC)."""
    if not value:
        return None
    from datetime import date as date_cls
    tz = tz or ZoneInfo("America/Chicago")
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt
    if isinstance(value, date_cls):
        return datetime(value.year, value.month, value.day, tzinfo=tz)
    raw = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        d = datetime.strptime(raw, "%Y-%m-%d")
        return d.replace(tzinfo=tz)
    try:
        dt = dateparser.parse(raw)
    except (ValueError, OverflowError, TypeError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def format_date(dt: datetime | None, tz: ZoneInfo, date_only: bool = False) -> tuple[str | None, str]:
    if not dt:
        return None, "Date not listed in feed"
    local = dt.astimezone(tz)
    # America/Chicago: CST or CDT. Label as CT.
    if date_only or (local.hour, local.minute, local.second, local.microsecond) == (0, 0, 0, 0):
        return local.date().isoformat(), local.strftime("%b %-d, %Y")
    return local.isoformat(), local.strftime("%b %-d, %Y, %-I:%M %p CT")


def detect_category(text: str, default: str, rematch: bool) -> str:
    if not rematch:
        return default
    scores: dict[str, int] = {}
    for cat_id, pattern in CATEGORY_PATTERNS.items():
        if pattern.search(text or ""):
            scores[cat_id] = scores.get(cat_id, 0) + 1
    if not scores:
        return default
    # Prefer a non-default match when the outlet covers multiple series.
    if default in scores and len(scores) == 1:
        return default
    best = max(scores, key=scores.get)
    return best


def has_engine_tag(text: str, preset: list[str]) -> bool:
    if "engines" in preset:
        return True
    return bool(ENGINE_RE.search(text or ""))


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def is_youtube_feed(url: str) -> bool:
    return "youtube.com/feeds/videos.xml" in (url or "")


def cache_path_for(url: str) -> Path:
    name = re.sub(r"[^a-zA-Z0-9]+", "_", url).strip("_")[:160]
    return FEED_CACHE / f"{name}.xml"


def save_feed_cache(url: str, raw: bytes) -> None:
    FEED_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path_for(url).write_bytes(raw)


def load_feed_cache(url: str) -> bytes | None:
    path = cache_path_for(url)
    if path.exists() and path.stat().st_size > 200:
        return path.read_bytes()
    return None


def fetch_feed(feed_cfg: dict) -> tuple[dict, list[dict], str | None]:
    url = feed_cfg["url"]
    attempts = 5 if is_youtube_feed(url) else 1
    last_err = "unknown error"
    for i in range(attempts):
        raw = b""
        try:
            raw = fetch_bytes(url)
            parsed = feedparser.parse(raw)
        except Exception as exc:  # noqa: BLE001 — keep other feeds building
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(0.6)
            continue
        entries = list(parsed.entries or [])
        if entries:
            if is_youtube_feed(url):
                save_feed_cache(url, raw)
            return feed_cfg, entries, None
        bozo = getattr(parsed, "bozo_exception", None)
        last_err = "no items in feed"
        if bozo:
            last_err = f"no items ({bozo})"
        if raw and b"<html" in raw[:400].lower():
            last_err = "YouTube RSS returned an HTML error page (intermittent 404/500)"
        if i < attempts - 1:
            time.sleep(0.6)
    # Last-good cache: YouTube RSS is known to 404/500 even for valid channel IDs.
    if is_youtube_feed(url):
        cached = load_feed_cache(url)
        if cached:
            parsed = feedparser.parse(cached)
            entries = list(parsed.entries or [])
            if entries:
                print(f"  CACHE {feed_cfg.get('name', url)}: using last good YouTube RSS ({len(entries)} entries)")
                return feed_cfg, entries, None
    return feed_cfg, [], last_err


def entry_link(entry: dict) -> str:
    link = (entry.get("link") or "").strip()
    if link:
        return link
    for key in ("id", "guid"):
        val = entry.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
        if isinstance(val, dict) and str(val.get("value", "")).startswith("http"):
            return str(val["value"])
    return ""


def entry_excerpt(entry: dict, limit: int) -> str:
    # Only use short feed summary/description fields — never content:encoded bodies.
    raw = entry.get("summary") or entry.get("description") or ""
    if not raw and entry.get("summary_detail"):
        raw = entry["summary_detail"].get("value") or ""
    if not raw and entry.get("media_description"):
        raw = entry.get("media_description")
    text = strip_html(raw)
    text = YOUTUBE_BOILER_RE.split(text)[0].strip()
    text = re.sub(r"(?is)\b(subscribe now:?|contact me:|social media links:|thank you .+? for sponsoring!).*", " ", text)
    text = re.sub(r"(?i)\bfollow me @\S*", " ", text)
    text = re.sub(r"(?i)\s+source\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -|")
    return shorten(text, limit)


def entry_date(entry: dict) -> datetime | None:
    for key in ("published", "updated", "created"):
        dt = parse_date(entry.get(key))
        if dt:
            return dt
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    return None


YOUTUBE_BOILER_RE = re.compile(
    r"(Subscribe\s*►|1320Video Gear\s*►|Watch more of our recent|Hand-polished hose|"
    r"Need more Power\?|————————————————).*$",
    re.I | re.S,
)

DIRT_CLASS_PATTERNS: list[tuple[str, re.Pattern[str], list[str]]] = [
    ("sprint-410", re.compile(r"\b(410 sprint|410 winged|winged 410)\b", re.I), ["sprint"]),
    ("sprint-360", re.compile(r"\b(360 sprint|360 winged|winged 360|ascs)\b", re.I), ["sprint"]),
    ("sprint-305", re.compile(r"\b(305 sprint|winged 305)\b", re.I), ["sprint"]),
    ("sprint", re.compile(r"\b(sprint car|sprint cars|world of outlaws sprint|high limit)\b", re.I), []),
    ("late-model-crate", re.compile(r"\bcrate late model", re.I), ["late-model"]),
    ("late-model-super", re.compile(r"\b(super late model|lucas oil late model|world of outlaws late model)\b", re.I), ["late-model"]),
    ("late-model", re.compile(r"\blate models?\b", re.I), []),
    ("modified-ump", re.compile(r"\b(ump modified|dirtcar ump)\b", re.I), ["modified"]),
    ("modified-imca", re.compile(r"\bimca modified", re.I), ["modified"]),
    ("modified-bigblock", re.compile(r"\b(big[- ]block modified|super dirtcar)\b", re.I), ["modified"]),
    ("modified", re.compile(r"\b(crate modified|dirt modified|modifieds?)\b", re.I), []),
    ("midget", re.compile(r"\b(midgets?|chili bowl|usac national midget|usac)\b", re.I), []),
    ("micro", re.compile(r"\b(micro sprints?|micros)\b", re.I), []),
    ("stock-car", re.compile(r"\b(street stocks?|hobby stocks?|pure stocks?|mini stocks?|stock cars?)\b", re.I), []),
    ("kart", re.compile(r"\b(karts?|karting|ekarting)\b", re.I), []),
]


def dirt_class_tags(text: str, preset: list[str]) -> list[str]:
    tags = list(preset)
    blob = text or ""
    for tag_id, pattern, extras in DIRT_CLASS_PATTERNS:
        if pattern.search(blob):
            if tag_id not in tags:
                tags.append(tag_id)
            for extra in extras:
                if extra not in tags:
                    tags.append(extra)
    return tags


def youtube_meta(entry: dict, url: str) -> tuple[str, str]:
    vid = str(entry.get("yt_videoid") or "").strip()
    if not vid:
        mid = str(entry.get("id") or "")
        m = re.search(r"yt:video:([\w-]+)", mid)
        if m:
            vid = m.group(1)
    if not vid:
        parts = urllib.parse.urlsplit(url or "")
        q = urllib.parse.parse_qs(parts.query)
        vid = (q.get("v") or [""])[0]
        if not vid:
            m = re.search(r"/(?:shorts|live|embed)/([\w-]{6,})", url or "")
            if m:
                vid = m.group(1)
    thumb = ""
    thumbs = entry.get("media_thumbnail") or []
    if thumbs and isinstance(thumbs, list):
        thumb = str(thumbs[0].get("url") or "")
    if not thumb and vid:
        thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return vid, thumb


class SiteBuilder:
    def __init__(self, output: Path | None = None, preview_merch: bool = False, prod: bool = False, force_local: bool = False) -> None:
        self.outdir = Path(output) if output else PUBLIC
        self.site = load_yaml(ROOT / "site.yaml")
        feeds_cfg = load_yaml(ROOT / "feeds.yaml")
        self.categories = feeds_cfg["categories"]
        self.category_map = {c["id"]: c for c in self.categories}
        self.dirt_classes = feeds_cfg.get("dirt_classes") or []
        self.feed_list = [f for f in feeds_cfg.get("feeds", []) if f.get("enabled", True)]
        self.tz = ZoneInfo(self.site.get("timezone", "America/Chicago"))
        self._resolve_base(prod=prod, force_local=force_local)
        self.excerpt_chars = int(self.site.get("excerpt_chars", 220))
        merch_cfg = self.site.get("merch") or {}
        # Nav, footer, and sitemap only when merch.enabled is true.
        # --preview-merch builds the page without those links.
        self.merch_enabled = bool(merch_cfg.get("enabled", False))
        self.preview_merch = bool(preview_merch)
        self.build_merch = self.merch_enabled or self.preview_merch
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES)),
            autoescape=select_autoescape(["html"]),
        )
        self.env.globals["site"] = self.site
        self.env.globals["categories"] = self.categories
        self.env.globals["dirt_classes"] = self.dirt_classes
        self.env.globals["merch_enabled"] = self.merch_enabled
        self.env.globals["url_for"] = self.url_for
        self.env.globals["absolute"] = self.absolute
        self.env.globals["category_url"] = self.category_url
        self.env.globals["category_slug"] = self.category_slug
        self.failed: list[tuple[str, str]] = []
        self.feed_counts: list[tuple[str, int]] = []

    def _resolve_base(self, prod: bool, force_local: bool) -> None:
        """Local preview is the default so plain ./build.sh keeps working.

        Production URLs come from site.yaml when --prod is passed, SDN_BUILD=prod
        is set, or the build is running on GitHub Actions. SDN_BASE_URL and
        SDN_BASE_PATH override the resolved values in either mode.
        """
        local_url = "http://127.0.0.1:8080"
        yaml_url = (self.site.get("base_url") or local_url).rstrip("/")
        yaml_path = (self.site.get("base_path") or "").rstrip("/")
        env_build = os.environ.get("SDN_BUILD", "").strip().lower()
        if force_local or env_build in {"local", "preview"}:
            use_prod = False
        elif prod or env_build in {"prod", "production"} or os.environ.get("GITHUB_ACTIONS") == "true":
            use_prod = True
        else:
            use_prod = False
        self.prod_build = use_prod
        if use_prod:
            self.base_url = yaml_url
            self.base_path = yaml_path
        else:
            self.base_url = local_url
            self.base_path = ""
        env_url = os.environ.get("SDN_BASE_URL", "").strip()
        if env_url:
            self.base_url = env_url.rstrip("/")
        if "SDN_BASE_PATH" in os.environ:
            self.base_path = os.environ.get("SDN_BASE_PATH", "").rstrip("/")

    def origin(self) -> str:
        parts = urllib.parse.urlsplit(self.base_url)
        return f"{parts.scheme}://{parts.netloc}"

    def url_for(self, path: str) -> str:
        path = path.lstrip("/")
        if path.endswith("index.html"):
            path = path[: -len("index.html")]
        prefix = self.base_path
        if prefix and not prefix.startswith("/"):
            prefix = "/" + prefix
        return f"{prefix}/{path}" if path else (prefix + "/" if prefix else "/")

    def absolute(self, path: str) -> str:
        """Absolute URL for a site path, without doubling base_path."""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        rel = self.url_for(path)
        if rel.startswith("http://") or rel.startswith("https://"):
            return rel
        if not rel.startswith("/"):
            rel = "/" + rel
        return self.origin() + rel

    def resolve_category(self, category: str, default: str = "drag") -> str:
        category = str(category or default).strip().lower()
        category = CATEGORY_ALIASES.get(category, category)
        if category not in self.category_map:
            return default
        return category

    def category_slug(self, cat: Any) -> str:
        if not isinstance(cat, dict):
            cat = self.category_map.get(str(cat), {"id": cat})
        return str(cat.get("slug") or cat.get("id") or "")

    def category_url(self, cat: Any) -> str:
        return self.url_for(f"category/{self.category_slug(cat)}/index.html")

    def make_item(
        self,
        *,
        title: str,
        source: str,
        url: str,
        excerpt: str,
        dt: datetime | None,
        category: str,
        tags: list[str],
        is_original: bool = False,
        slug: str | None = None,
        video_id: str = "",
        thumbnail: str = "",
        channel_id: str = "",
    ) -> dict:
        category = self.resolve_category(category, "drag")
        date_iso, date_display = format_date(dt, self.tz)
        href = self.url_for(f"articles/{slug}/index.html") if is_original and slug else url
        return {
            "title": title,
            "source": source,
            "url": url,
            "href": href,
            "excerpt": excerpt,
            "date": dt,
            "date_iso": date_iso,
            "date_display": date_display,
            "category": category,
            "category_name": self.category_map[category]["name"],
            "tags": tags,
            "is_original": is_original,
            "slug": slug,
            "video_id": video_id,
            "thumbnail": thumbnail,
            "channel_id": channel_id,
        }

    def collect_feed_items(self) -> list[dict]:
        items: list[dict] = []
        print(f"Fetching {len(self.feed_list)} feeds…")
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(fetch_feed, cfg): cfg for cfg in self.feed_list}
            for fut in as_completed(futures):
                cfg, entries, error = fut.result()
                name = cfg["name"]
                if error:
                    self.failed.append((name, f"{cfg['url']} — {error}"))
                    print(f"  FAIL  {name}: {error}")
                    continue
                cap = int(cfg.get("max_items") or self.site.get("feed_max_items_default", 10))
                count = 0
                rematch = bool(cfg.get("rematch_category"))
                preset_tags = list(cfg.get("tags") or [])
                for entry in entries[:cap]:
                    title = strip_html(entry.get("title") or "").strip()
                    link = entry_link(entry)
                    if not title or not link:
                        continue
                    excerpt = entry_excerpt(entry, self.excerpt_chars)
                    text = f"{title} {excerpt}"
                    category = detect_category(text, cfg["category"], rematch)
                    tags = list(preset_tags)
                    if has_engine_tag(text, tags) and "engines" not in tags:
                        tags.append("engines")
                    if category == "dirt" or cfg.get("category") == "dirt":
                        tags = dirt_class_tags(text, tags)
                    video_id, thumbnail = "", ""
                    channel_id = str(cfg.get("channel_id") or "")
                    if cfg.get("type") == "youtube" or is_youtube_feed(cfg.get("url", "")) or "youtube.com/watch" in link or "youtube.com/shorts" in link:
                        video_id, thumbnail = youtube_meta(entry, link)
                    items.append(
                        self.make_item(
                            title=title,
                            source=name,
                            url=link,
                            excerpt=excerpt,
                            dt=entry_date(entry),
                            category=category,
                            tags=tags,
                            video_id=video_id,
                            thumbnail=thumbnail,
                            channel_id=channel_id,
                        )
                    )
                    count += 1
                self.feed_counts.append((name, count))
                print(f"  OK    {name}: {count} item(s)")
        return items

    def collect_posts(self) -> list[dict]:
        items: list[dict] = []
        if not POSTS.exists():
            return items
        used_slugs: set[str] = set()
        for path in sorted(POSTS.glob("*.md")):
            post = frontmatter.load(path)
            if post.get("draft") in (True, "true", "True", "yes", "1", 1):
                print(f"  SKIP  draft post {path.name}")
                continue
            title = str(post.get("title") or path.stem).strip()
            if not title:
                continue
            slug = slugify(str(post.get("slug") or title))
            if slug in used_slugs:
                slug = slugify(f"{slug}-{path.stem}")
            used_slugs.add(slug)
            dt = parse_date(post.get("date"), self.tz) or datetime.fromtimestamp(path.stat().st_mtime, tz=self.tz)
            category = self.resolve_category(str(post.get("category") or "drag"), "drag")
            tags = list(post.get("tags") or [])
            summary = str(post.get("summary") or "").strip()
            body_html = markdown.markdown(
                post.content,
                extensions=["extra", "sane_lists", "smarty"],
            )
            image = post.get("image") or ""
            image_url = ""
            image_alt = str(post.get("image_alt") or "")
            if image:
                image = str(image).strip()
                if image.startswith("http://") or image.startswith("https://"):
                    image_url = image
                else:
                    src = Path(image)
                    if not src.is_absolute():
                        candidates = [IMAGES / src.name, ROOT / image, path.parent / image]
                        src = next((c for c in candidates if c.exists()), IMAGES / src.name)
                    dest_dir = self.outdir / "images"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest = dest_dir / src.name
                    if src.exists():
                        shutil.copy2(src, dest)
                        image_url = self.url_for(f"images/{src.name}")
            excerpt = summary or shorten(strip_html(body_html), self.excerpt_chars)
            if has_engine_tag(f"{title} {excerpt} {post.content}", tags) and "engines" not in tags:
                tags.append("engines")
            item = self.make_item(
                title=title,
                source=self.site["site_name"],
                url=self.absolute(f"articles/{slug}/index.html"),
                excerpt=excerpt,
                dt=dt,
                category=category,
                tags=tags,
                is_original=True,
                slug=slug,
            )
            item["html"] = body_html
            item["summary"] = summary
            item["image_url"] = image_url
            item["image_alt"] = image_alt
            item["path"] = path
            items.append(item)
        return items

    def dedupe(self, items: list[dict]) -> list[dict]:
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        unique: list[dict] = []
        # Originals always win if they collide with a feed headline.
        ordered = sorted(items, key=lambda i: (not i["is_original"],))
        dropped = 0
        for item in ordered:
            url_key = normalize_url(item["url"])
            title_key = normalize_title(item["title"])
            if url_key and url_key in seen_urls:
                dropped += 1
                continue
            if title_key and title_key in seen_titles:
                dropped += 1
                continue
            if url_key:
                seen_urls.add(url_key)
            if title_key:
                seen_titles.add(title_key)
            unique.append(item)
        if dropped:
            print(f"Deduped {dropped} duplicate headline(s).")
        return unique

    def sort_items(self, items: list[dict]) -> list[dict]:
        def key(item: dict) -> tuple:
            dt = item["date"]
            # Dated items first (newest), then undated feed items.
            if dt is None:
                return (1, 0.0)
            return (0, -dt.timestamp())

        return sorted(items, key=key)


    def _format_price(self, value: Any) -> str:
        if value is None or value == "":
            return ""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if float(value).is_integer():
                return f"${int(value)}"
            return f"${value:.2f}"
        text = str(value).strip()
        return text

    def _merch_image(self, raw: Any, item_type: str, placeholder: bool, name: str) -> tuple[str, str]:
        """Return (url, alt). Default shirt/hat art when no image is given."""
        defaults = {
            "shirt": "static/img/merch-shirt.svg",
            "hat": "static/img/merch-hat.svg",
        }
        image = str(raw or "").strip()
        if not image:
            rel = defaults.get(item_type, defaults["shirt"])
            alt = "" if placeholder else name
            return self.url_for(rel), alt
        if image.startswith("http://") or image.startswith("https://"):
            return image, name
        src = Path(image)
        if not src.is_absolute():
            candidates = [IMAGES / src.name, ROOT / image, ROOT / "content" / image]
            src = next((c for c in candidates if c.exists()), IMAGES / src.name)
        dest_dir = self.outdir / "images"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if src.exists():
            shutil.copy2(src, dest)
            return self.url_for(f"images/{src.name}"), name
        rel = defaults.get(item_type, defaults["shirt"])
        print(f"  WARN  merch image missing ({image}); using default {item_type} art")
        return self.url_for(rel), "" if placeholder else name

    def load_merch(self) -> dict:
        data = load_yaml(MERCH) if MERCH.exists() else {}
        items: list[dict] = []
        type_labels = {"shirt": "Shirt", "hat": "Hat", "other": "Gear"}
        for raw in data.get("items") or []:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "Design coming soon").strip()
            item_type = str(raw.get("type") or "other").strip().lower()
            buy_url = str(raw.get("buy_url") or "").strip()
            if "placeholder" in raw and raw.get("placeholder") is not None:
                placeholder = bool(raw.get("placeholder"))
            else:
                placeholder = not buy_url
            price = "" if placeholder else self._format_price(raw.get("price"))
            image, image_alt = self._merch_image(raw.get("image"), item_type, placeholder, name)
            items.append({
                "name": name,
                "type": item_type,
                "type_label": type_labels.get(item_type, item_type.replace("-", " ").title() or "Gear"),
                "image": image,
                "image_alt": image_alt,
                "price": price,
                "buy_url": "" if placeholder else buy_url,
                "placeholder": placeholder,
            })
        mtime = None
        if MERCH.exists():
            mtime = datetime.fromtimestamp(MERCH.stat().st_mtime, tz=self.tz)
        return {
            "kicker": str(data.get("kicker") or "Speed-Demon News gear").strip(),
            "headline": str(data.get("headline") or "Coming soon").strip(),
            "lede": str(data.get("lede") or "Shirts and hats are in the works. Designs drop soon.").strip(),
            "note": str(data.get("note") or "Designs drop soon.").strip(),
            "items": items,
            "mtime": mtime,
        }


    def _youtube_channel_urls(self, channel_id: str, handle: str) -> dict[str, str]:
        handle = (handle or "").strip().lstrip("@")
        if handle:
            base = f"https://www.youtube.com/@{handle}"
        elif channel_id:
            base = f"https://www.youtube.com/channel/{channel_id}"
        else:
            base = ""
        return {
            "channel_url": base,
            "live_url": f"{base}/live" if base else "",
            "streams_url": f"{base}/streams" if base else "",
        }

    def _latest_for_channel(self, items: list[dict], channel_id: str, name: str, limit: int = 3) -> list[dict]:
        matches: list[dict] = []
        seen: set[str] = set()
        for item in items:
            if not item.get("video_id"):
                continue
            cid_ok = bool(channel_id) and item.get("channel_id") == channel_id
            name_ok = bool(name) and item.get("source") == name
            if not (cid_ok or name_ok):
                continue
            key = item.get("video_id") or item.get("url") or ""
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            matches.append(item)
        return self.sort_items(matches)[:limit]

    def _prepare_live_channel(self, raw: dict, items: list[dict]) -> dict | None:
        if not raw or raw.get("enabled") is False:
            return None
        name = str(raw.get("name") or "").strip()
        channel_id = str(raw.get("youtube_channel_id") or raw.get("channel_id") or "").strip()
        if channel_id and not YOUTUBE_CHANNEL_RE.match(channel_id):
            print(f"  WARN  live.yaml: skipping {name or channel_id} (invalid YouTube channel id)")
            return None
        handle = str(raw.get("handle") or "").strip()
        category = self.resolve_category(str(raw.get("category") or "street"), "street")
        watch_url = str(raw.get("watch_url") or "").strip()
        if not name:
            return None
        if not channel_id and not watch_url:
            print(f"  WARN  live.yaml: skipping {name} (need youtube_channel_id or watch_url)")
            return None
        urls = self._youtube_channel_urls(channel_id, handle)
        latest = self._latest_for_channel(items, channel_id, name) if channel_id or name else []
        poster = ""
        for vid in latest:
            if vid.get("thumbnail"):
                poster = vid["thumbnail"]
                break
        section = str(raw.get("section") or ("street" if category == "street" else "other")).strip().lower()
        return {
            "name": name,
            "youtube_channel_id": channel_id,
            "handle": handle.lstrip("@"),
            "category": category,
            "category_name": self.category_map[category]["name"],
            "section": section,
            "note": str(raw.get("note") or "").strip(),
            "watch_url": watch_url,
            "poster": poster,
            "latest": latest,
            **urls,
        }

    def _prepare_watch_card(self, raw: dict) -> dict | None:
        if not raw or raw.get("enabled") is False:
            return None
        name = str(raw.get("name") or "").strip()
        if not name:
            return None
        category = self.resolve_category(str(raw.get("category") or "drag"), "drag")
        links = []
        for link in raw.get("links") or []:
            if not isinstance(link, dict):
                continue
            label = str(link.get("label") or "").strip()
            url = str(link.get("url") or "").strip()
            if not label or not url:
                continue
            if not url.startswith("https://"):
                print(f"  WARN  live.yaml: skipped non-https link for {name}: {url}")
                continue
            links.append({"label": label, "url": url})
        return {
            "name": name,
            "category": category,
            "category_name": self.category_map[category]["name"],
            "section": str(raw.get("section") or "track").strip().lower(),
            "note": str(raw.get("note") or "").strip(),
            "links": links,
        }

    def load_live(self, items: list[dict]) -> dict:
        raw = load_yaml(LIVE) if LIVE.exists() else {}
        page = raw.get("page") or {}
        street: list[dict] = []
        other: list[dict] = []
        for entry in list(raw.get("channels") or []) + list(raw.get("other_channels") or []):
            if not isinstance(entry, dict):
                continue
            channel = self._prepare_live_channel(entry, items)
            if not channel:
                continue
            # other_channels list always goes to the other section unless
            # the entry itself says section: street.
            in_other_list = entry in (raw.get("other_channels") or [])
            section = channel["section"]
            if section == "street" and not in_other_list:
                street.append(channel)
            else:
                other.append(channel)
        watch_cards = []
        for entry in raw.get("watch") or []:
            if not isinstance(entry, dict):
                continue
            card = self._prepare_watch_card(entry)
            if card:
                watch_cards.append(card)
        default_lede = (
            "Outlaw racing streams first. Track racing that lives on TV "
            "or a paid app follows, with official links only."
        )
        return {
            "kicker": str(page.get("kicker") or "They're live. Or they will be."),
            "headline": str(page.get("headline") or "Live"),
            "lede": str(page.get("lede") or default_lede),
            "street_channels": street,
            "other_channels": other,
            "watch_cards": watch_cards,
        }


    def load_follow(self) -> dict:
        raw = load_yaml(FOLLOW) if FOLLOW.exists() else {}
        page = raw.get("page") or {}
        accounts: list[dict] = []
        for entry in raw.get("accounts") or []:
            if not isinstance(entry, dict) or entry.get("enabled") is False:
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            category = self.resolve_category(str(entry.get("category") or "street"), "street")
            platforms: list[dict] = []
            raw_plats = entry.get("platforms") or {}
            if isinstance(raw_plats, dict):
                items = raw_plats.items()
            elif isinstance(raw_plats, list):
                items = []
                for item in raw_plats:
                    if isinstance(item, dict):
                        items.append((item.get("key") or item.get("platform"), item.get("url")))
            else:
                items = []
            seen: set[str] = set()
            pending: dict[str, str] = {}
            for key, url in items:
                key = str(key or "").strip().lower()
                if key == "twitter":
                    key = "x"
                url = str(url or "").strip()
                if key not in PLATFORM_LABELS or not url.startswith("https://"):
                    if url and not url.startswith("https://"):
                        print(f"  WARN  follow.yaml: skipped non-https link for {name}: {url}")
                    continue
                pending[key] = url
            for key in PLATFORM_ORDER:
                if key in pending and key not in seen:
                    platforms.append({
                        "key": key,
                        "label": PLATFORM_LABELS[key],
                        "url": pending[key],
                    })
                    seen.add(key)
            if not platforms:
                print(f"  WARN  follow.yaml: skipped {name} (no verified https platform URLs)")
                continue
            accounts.append({
                "name": name,
                "category": category,
                "category_name": self.category_map[category]["name"],
                "note": str(entry.get("note") or "").strip(),
                "featured": bool(entry.get("featured")),
                "platforms": platforms,
            })
        groups: list[dict] = []
        grouped: dict[str, list[dict]] = {}
        for account in accounts:
            grouped.setdefault(account["category"], []).append(account)
        for cat in self.categories:
            cat_accounts = grouped.pop(cat["id"], [])
            if cat_accounts:
                groups.append({
                    "id": cat["id"],
                    "name": cat["name"],
                    "accounts": cat_accounts,
                })
        for cat_id, cat_accounts in grouped.items():
            groups.append({
                "id": cat_id,
                "name": self.category_map.get(cat_id, {}).get("name") or cat_id,
                "accounts": cat_accounts,
            })
        highlights = [a for a in accounts if a.get("featured")]
        if not highlights:
            highlights = accounts[:5]
        return {
            "page": {
                "kicker": str(page.get("kicker") or "The crew").strip(),
                "headline": str(page.get("headline") or "Follow").strip(),
                "lede": str(page.get("lede") or "Accounts we watch, and that you can follow too.").strip(),
            },
            "accounts": accounts,
            "groups": groups,
            "highlights": highlights[:5],
        }

    def _youtube_id(self, raw: str) -> str:
        raw = (raw or "").strip()
        if YOUTUBE_ID_RE.match(raw):
            return raw
        parts = urllib.parse.urlsplit(raw)
        host = (parts.netloc or "").lower()
        if "youtu.be" in host:
            candidate = parts.path.strip("/").split("/")[0]
            return candidate if YOUTUBE_ID_RE.match(candidate) else ""
        if "youtube.com" in host or "youtube-nocookie.com" in host:
            q = urllib.parse.parse_qs(parts.query)
            if q.get("v") and YOUTUBE_ID_RE.match(q["v"][0]):
                return q["v"][0]
            m = re.search(r"/(?:embed|shorts|live)/([A-Za-z0-9_-]{11})", parts.path)
            if m:
                return m.group(1)
        return ""

    def _wonderland_src_path(self, src: str) -> Path | None:
        src = (src or "").strip()
        if not src or src.startswith("http://") or src.startswith("https://"):
            return None
        candidate = Path(src)
        if candidate.is_absolute() and candidate.exists():
            return candidate
        options = [
            WONDERLAND_MEDIA / Path(src).name,
            WONDERLAND_MEDIA / src,
            IMAGES / Path(src).name,
            ROOT / src,
        ]
        for option in options:
            if option.exists() and option.is_file():
                return option
        return None

    def _optimize_wonderland_image(self, src_path: Path) -> tuple[str, str]:
        """Return (full_url, thumb_url). Resizes to max 1600px and writes a thumbnail when Pillow is available."""
        dest_dir = self.outdir / "static" / "wonderland"
        dest_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir = dest_dir / "thumbs"
        suffix = src_path.suffix.lower() or ".jpg"
        stem = src_path.stem
        dest = dest_dir / f"{stem}{suffix}"
        thumb = thumb_dir / f"{stem}{suffix}"
        full_url = self.url_for(f"static/wonderland/{dest.name}")
        thumb_url = self.url_for(f"static/wonderland/thumbs/{thumb.name}")
        try:
            from PIL import Image, ImageOps
        except ImportError:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if src_path.resolve() != dest.resolve():
                shutil.copy2(src_path, dest)
            return full_url, full_url
        try:
            with Image.open(src_path) as im:
                im = ImageOps.exif_transpose(im)
                if im.mode not in {"RGB", "RGBA"}:
                    im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
                full = im.copy()
                full.thumbnail((1600, 1600))
                if suffix in {".jpg", ".jpeg"} and full.mode == "RGBA":
                    bg = Image.new("RGB", full.size, (8, 7, 5))
                    bg.paste(full, mask=full.split()[-1])
                    full = bg
                    dest = dest_dir / f"{stem}.jpg"
                    full_url = self.url_for(f"static/wonderland/{dest.name}")
                save_kw: dict[str, Any] = {}
                if dest.suffix.lower() in {".jpg", ".jpeg"}:
                    save_kw = {"quality": 88, "optimize": True, "progressive": True}
                elif dest.suffix.lower() == ".webp":
                    save_kw = {"quality": 85, "method": 4}
                elif dest.suffix.lower() == ".png":
                    save_kw = {"optimize": True}
                dest.parent.mkdir(parents=True, exist_ok=True)
                full.save(dest, **save_kw)
                thumb_im = im.copy()
                thumb_im.thumbnail((640, 640))
                if suffix in {".jpg", ".jpeg"} and thumb_im.mode == "RGBA":
                    bg = Image.new("RGB", thumb_im.size, (8, 7, 5))
                    bg.paste(thumb_im, mask=thumb_im.split()[-1])
                    thumb_im = bg
                    thumb = thumb_dir / f"{stem}.jpg"
                    thumb_url = self.url_for(f"static/wonderland/thumbs/{thumb.name}")
                thumb.parent.mkdir(parents=True, exist_ok=True)
                thumb_im.save(thumb, **save_kw)
            return full_url, thumb_url
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN  could not optimize {src_path.name}: {exc}")
            if src_path.resolve() != dest.resolve():
                shutil.copy2(src_path, dest)
            return full_url, full_url

    def _prepare_wonderland_media(self, raw: Any) -> dict | None:
        if not isinstance(raw, dict):
            return None
        kind = str(raw.get("type") or "image").strip().lower()
        src = str(raw.get("src") or raw.get("url") or "").strip()
        if not src:
            return None
        caption = str(raw.get("caption") or "").strip()
        alt = str(raw.get("alt") or caption).strip()
        if kind in {"yt", "youtube"}:
            video_id = self._youtube_id(src)
            if not video_id:
                print(f"  WARN  wonderland: skipped YouTube item with no video id ({src})")
                return None
            return {
                "type": "youtube",
                "src": f"https://www.youtube.com/watch?v={video_id}",
                "video_id": video_id,
                "thumb": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                "caption": caption,
                "alt": alt or "YouTube video",
            }
        if kind in {"video", "mp4"}:
            if src.startswith("https://") or src.startswith("http://"):
                url = src
            else:
                path = self._wonderland_src_path(src)
                if not path:
                    print(f"  WARN  wonderland: missing video file {src}")
                    return None
                dest_dir = self.outdir / "static" / "wonderland"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / path.name
                if path.resolve() != dest.resolve():
                    shutil.copy2(path, dest)
                url = self.url_for(f"static/wonderland/{dest.name}")
            poster = str(raw.get("poster") or "").strip()
            poster_url = ""
            if poster:
                if poster.startswith("https://") or poster.startswith("http://"):
                    poster_url = poster
                else:
                    poster_path = self._wonderland_src_path(poster)
                    if poster_path:
                        poster_url, _ = self._optimize_wonderland_image(poster_path)
            mime = "video/webm" if url.lower().endswith(".webm") else "video/mp4"
            return {
                "type": "video",
                "src": url,
                "poster": poster_url,
                "caption": caption,
                "alt": alt,
                "mime": mime,
            }
        # image (default)
        if src.startswith("https://") or src.startswith("http://"):
            return {
                "type": "image",
                "src": src,
                "thumb": src,
                "caption": caption,
                "alt": alt or caption,
            }
        path = self._wonderland_src_path(src)
        if not path:
            print(f"  WARN  wonderland: missing image file {src}")
            return None
        full_url, thumb_url = self._optimize_wonderland_image(path)
        return {
            "type": "image",
            "src": full_url,
            "thumb": thumb_url,
            "caption": caption,
            "alt": alt or caption or path.stem.replace("-", " "),
        }

    def _prepare_adventure(self, raw: dict, *, body_html: str = "", slug: str | None = None) -> dict | None:
        title = str(raw.get("title") or "").strip()
        if not title:
            return None
        if raw.get("enabled") is False:
            return None
        media: list[dict] = []
        for entry in raw.get("media") or []:
            item = self._prepare_wonderland_media(entry)
            if item:
                media.append(item)
        cover_src = str(raw.get("cover") or "").strip()
        cover = ""
        cover_thumb = ""
        cover_alt = title
        if cover_src:
            cover_item = self._prepare_wonderland_media({"type": "image", "src": cover_src, "alt": title})
            if cover_item:
                cover = cover_item["src"]
                cover_thumb = cover_item.get("thumb") or cover
                cover_alt = cover_item.get("alt") or title
        if not cover:
            first_image = next((m for m in media if m["type"] == "image"), None)
            if first_image:
                cover = first_image["src"]
                cover_thumb = first_image.get("thumb") or cover
                cover_alt = first_image.get("alt") or title
            else:
                first_yt = next((m for m in media if m["type"] == "youtube"), None)
                if first_yt:
                    cover = first_yt.get("thumb") or ""
                    cover_thumb = cover
                    cover_alt = title
        dt = parse_date(raw.get("date"), self.tz)
        date_iso, date_display = format_date(dt, self.tz, date_only=True)
        slug = slugify(str(slug or raw.get("slug") or title))
        tags = [str(t).strip() for t in (raw.get("tags") or []) if str(t).strip()]
        caption = str(raw.get("caption") or raw.get("summary") or "").strip()
        href = ""
        if body_html:
            href = self.url_for(f"willseys-wonderland/{slug}/index.html")
        return {
            "title": title,
            "slug": slug,
            "date": dt,
            "date_iso": date_iso,
            "date_display": date_display if dt else "",
            "caption": caption,
            "tags": tags,
            "media": media,
            "cover": cover,
            "cover_thumb": cover_thumb,
            "cover_alt": cover_alt,
            "body_html": body_html,
            "href": href,
        }

    def load_wonderland(self) -> dict:
        raw = load_yaml(WONDERLAND_YAML) if WONDERLAND_YAML.exists() else {}
        page = raw.get("page") or {}
        adventures: list[dict] = []
        used_slugs: set[str] = set()
        for entry in raw.get("adventures") or []:
            if not isinstance(entry, dict):
                continue
            item = self._prepare_adventure(entry)
            if not item:
                continue
            slug = item["slug"]
            if slug in used_slugs:
                slug = slugify(f"{slug}-entry")
                item["slug"] = slug
            used_slugs.add(slug)
            adventures.append(item)
        if WONDERLAND_POSTS.exists():
            for path in sorted(WONDERLAND_POSTS.glob("*.md")):
                post = frontmatter.load(path)
                if post.get("draft") in (True, "true", "True", "yes", "1", 1):
                    print(f"  SKIP  draft wonderland post {path.name}")
                    continue
                body_html = markdown.markdown(
                    post.content or "",
                    extensions=["extra", "sane_lists", "smarty"],
                ) if (post.content or "").strip() else ""
                meta = dict(post.metadata or {})
                slug = slugify(str(meta.get("slug") or path.stem))
                item = self._prepare_adventure(meta, body_html=body_html, slug=slug)
                if not item:
                    continue
                if item["slug"] in used_slugs:
                    item["slug"] = slugify(f"{item['slug']}-{path.stem}")
                    if body_html:
                        item["href"] = self.url_for(f"willseys-wonderland/{item['slug']}/index.html")
                used_slugs.add(item["slug"])
                adventures.append(item)

        def sort_key(item: dict) -> tuple:
            dt = item.get("date")
            if dt is None:
                return (1, 0.0)
            return (0, -dt.timestamp())

        adventures.sort(key=sort_key)
        latest = adventures[0] if adventures else None
        return {
            "page": {
                "kicker": str(page.get("kicker") or "From the pits").strip(),
                "headline": str(page.get("headline") or "Willseys Wonderland").strip(),
                "lede": str(
                    page.get("lede")
                    or "Our team. Our cars. Our adventures. Straight from the pits."
                ).strip(),
            },
            "adventures": adventures,
            "latest": latest,
        }

    def write(self, rel: str, content: str | bytes, binary: bool = False) -> None:

        path = self.outdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            path.write_bytes(content)  # type: ignore[arg-type]
        else:
            path.write_text(content, encoding="utf-8")

    def render(self, template: str, rel: str, **ctx: Any) -> None:
        page_title = ctx.pop("page_title", None) or self.site["site_name"]
        page_description = ctx.pop("page_description", None) or self.site["description"]
        canonical = ctx.pop("canonical", None) or self.absolute(rel)
        og_image = ctx.get("og_image")
        if og_image and og_image.startswith("/"):
            ctx["og_image"] = self.origin() + og_image
        html_out = self.env.get_template(template).render(
            page_title=page_title,
            page_description=page_description,
            canonical=canonical,
            **ctx,
        )
        self.write(rel, html_out)

    def write_robots(self) -> None:
        sitemap = self.absolute("sitemap.xml")
        self.write(
            "robots.txt",
            "User-agent: *\nAllow: /\n\nSitemap: {0}\n".format(sitemap),
        )

    def write_sitemap(self, pages: list[tuple[str, datetime | None]]) -> None:
        chunks = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        for rel, dt in pages:
            loc = self.absolute(rel)
            chunks.append("  <url>")
            chunks.append(f"    <loc>{html.escape(loc)}</loc>")
            if dt:
                chunks.append(f"    <lastmod>{dt.astimezone(timezone.utc).date().isoformat()}</lastmod>")
            chunks.append("  </url>")
        chunks.append("</urlset>\n")
        self.write("sitemap.xml", "\n".join(chunks))

    def write_rss(self, items: list[dict]) -> None:
        now = datetime.now(timezone.utc)
        chunks = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
            "<channel>",
            f"<title>{html.escape(self.site['site_name'])}</title>",
            f"<link>{html.escape(self.absolute('index.html'))}</link>",
            f"<description>{html.escape(self.site['description'])}</description>",
            f"<language>{html.escape(self.site.get('language', 'en'))}</language>",
            f"<lastBuildDate>{now.strftime('%a, %d %b %Y %H:%M:%S %z')}</lastBuildDate>",
            f'<atom:link href="{html.escape(self.absolute("feed.xml"))}" rel="self" type="application/rss+xml"/>',
        ]
        for item in items[:50]:
            chunks.append("<item>")
            chunks.append(f"<title>{html.escape(item['title'])}</title>")
            # item["url"] is already an absolute URL for original posts.
            link = item["url"]
            chunks.append(f"<link>{html.escape(link)}</link>")
            chunks.append(f'<guid isPermaLink="true">{html.escape(link)}</guid>')
            desc = item["excerpt"] or ""
            source_note = f"Source: {item['source']}"
            if not item["is_original"]:
                desc = f"{desc} ({source_note})".strip()
            chunks.append(f"<description>{html.escape(desc)}</description>")
            if item["date"]:
                rfc = item["date"].astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
                chunks.append(f"<pubDate>{rfc}</pubDate>")
            chunks.append(f"<category>{html.escape(item['category_name'])}</category>")
            chunks.append("</item>")
        chunks.append("</channel></rss>\n")
        self.write("feed.xml", "\n".join(chunks))

    def copy_static(self) -> None:
        dest = self.outdir / "static"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(STATIC, dest)

    def build(self) -> int:
        started = time.time()
        if self.outdir.exists():
            # Keep the output folder, replace contents except maybe nothing special.
            for child in self.outdir.iterdir():
                if child.name == ".git":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        self.outdir.mkdir(parents=True, exist_ok=True)
        # Tell GitHub Pages not to run Jekyll over the artifact.
        (self.outdir / ".nojekyll").write_text("", encoding="utf-8")
        if self.base_path:
            print(f"Building for {self.base_url} (base_path={self.base_path})")
        else:
            print(f"Building for local preview at {self.base_url}/")
        self.copy_static()

        feed_items = self.collect_feed_items()
        posts = self.collect_posts()
        combined = self.sort_items(self.dedupe(feed_items + posts))

        homepage_limit = int(self.site.get("homepage_limit", 60))
        category_limit = int(self.site.get("category_limit", 80))
        street_items = [i for i in combined if i["category"] == "street"]
        street_videos = [i for i in street_items if i.get("video_id")]
        grudge_board = []
        seen_urls: set[str] = set()
        for item in street_items[:3] + street_videos + street_items:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            grudge_board.append(item)
            if len(grudge_board) >= 6:
                break
        # Street leads the grid even when other series published more this cycle.
        # Cap the reserved street block so the rest of the card still has room
        # for drag, dirt, and the big series.
        street_home = [i for i in combined if i["category"] == "street"][:24]
        taken = {id(i) for i in street_home}
        other_home = [i for i in combined if id(i) not in taken]
        home_items = (street_home + other_home)[:homepage_limit]
        sources = sorted({i["source"] for i in home_items})
        follow = self.load_follow()
        wonderland = self.load_wonderland()
        self.env.globals["follow_highlights"] = follow.get("highlights") or []

        desc = self.site["description"]
        self.render(
            "index.html",
            "index.html",
            current="home",
            grudge_board=grudge_board,
            items=home_items,
            sources=sources,
            wonderland=wonderland,
            page_title=f"{self.site['site_name']} — {self.site['tagline']}",
            page_description=desc,
        )
        self.render(
            "about.html",
            "about.html",
            current="about",
            page_title=f"About {self.site['site_name']}",
            page_description=(
                f"About {self.site['site_name']}: a lightweight racing news desk. "
                "Outlaw racing leads the card, with drag, dirt, NASCAR, and IMSA right behind."
            ),
        )
        live = self.load_live(combined)
        self.render(
            "live.html",
            "live/index.html",
            current="live",
            live=live,
            page_title=f"Live — {self.site['site_name']}",
            page_description=(
                "Outlaw racing livestreams from 1320Video, DRAG LENS, "
                "Lens 660, and BoostedGT, plus official where-to-watch links "
                "for NHRA, DIRTVision, and FloRacing."
            ),
        )
        self.render(
            "follow.html",
            "follow/index.html",
            current="follow",
            follow=follow,
            page_title=f"Follow — {self.site['site_name']}",
            page_description=follow["page"]["lede"],
        )
        self.render(
            "wonderland.html",
            "willseys-wonderland/index.html",
            current="wonderland",
            wonderland=wonderland,
            page_title=f"Willseys Wonderland — {self.site['site_name']}",
            page_description=wonderland["page"]["lede"],
        )
        for adventure in wonderland["adventures"]:
            if not adventure.get("body_html"):
                continue
            rel = f"willseys-wonderland/{adventure['slug']}/index.html"
            self.render(
                "wonderland_post.html",
                rel,
                current="wonderland",
                item=adventure,
                og_type="article",
                page_title=f"{adventure['title']} — Willseys Wonderland",
                page_description=adventure.get("caption") or adventure["title"],
                og_image=adventure.get("cover") or None,
            )
        merch = self.load_merch()
        if self.build_merch:
            merch_ctx = dict(
                current="merch",
                merch=merch,
                page_title=f"Merch — {self.site['site_name']}",
                page_description=merch.get("lede") or f"Speed-Demon News shirts and hats. Designs drop soon.",
            )
            if not self.merch_enabled:
                merch_ctx["robots"] = "noindex,nofollow"
            self.render("merch.html", "merch/index.html", **merch_ctx)
        self.render(
            "404.html",
            "404.html",
            current="",
            page_title=f"Page not found — {self.site['site_name']}",
            page_description="That page is not on this site.",
        )
        sitemap_pages: list[tuple[str, datetime | None]] = [
            ("index.html", datetime.now(self.tz)),
            ("willseys-wonderland/index.html", datetime.now(self.tz)),
            ("live/index.html", datetime.now(self.tz)),
            ("follow/index.html", datetime.now(self.tz)),
            ("about.html", None),
        ]
        for adventure in wonderland["adventures"]:
            if adventure.get("body_html"):
                sitemap_pages.append(
                    (f"willseys-wonderland/{adventure['slug']}/index.html", adventure.get("date"))
                )
        if self.merch_enabled:
            sitemap_pages.append(("merch/index.html", merch.get("mtime")))
        now_posts = {p["slug"]: p for p in posts}
        for post in posts:
            rel = f"articles/{post['slug']}/index.html"
            self.render(
                "article.html",
                rel,
                current=post["category"],
                post=post,
                og_type="article",
                page_title=f"{post['title']} — {self.site['site_name']}",
                page_description=post["summary"] or post["excerpt"] or post["title"],
                og_image=post["image_url"] or None,
            )
            sitemap_pages.append((rel, post["date"]))

        for cat in self.categories:
            cat_items = [i for i in combined if i["category"] == cat["id"]][:category_limit]
            slug = self.category_slug(cat)
            rel = f"category/{slug}/index.html"
            self.render(
                "category.html",
                rel,
                current=cat["id"],
                category=cat,
                items=cat_items,
                sources=sorted({i["source"] for i in cat_items}),
                page_title=f"{cat['name']} — {self.site['site_name']}",
                page_description=cat.get("description") or f"{cat['name']} headlines on {self.site['site_name']}.",
            )
            sitemap_pages.append((rel, cat_items[0]["date"] if cat_items else None))
            if slug != cat["id"]:
                self.render(
                    "redirect.html",
                    f"category/{cat['id']}/index.html",
                    current="",
                    robots="noindex,follow",
                    canonical=self.absolute(rel),
                    redirect_url=self.url_for(rel),
                    redirect_name=cat["name"],
                    page_title=f"{cat['name']} — {self.site['site_name']}",
                    page_description=f"This section moved to {cat['name']}.",
                )

        self.write_robots()
        self.write_sitemap(sitemap_pages)
        self.write_rss(combined)
        # A small build manifest helps later scheduled runs see what happened.
        manifest = {
            "built_at": datetime.now(self.tz).isoformat(),
            "headline_count": len(combined),
            "feed_items": len(feed_items),
            "original_posts": len(posts),
            "feeds": [{"name": n, "items": c} for n, c in sorted(self.feed_counts)],
            "failed": [{"name": n, "error": e} for n, e in self.failed],
        }
        self.write("build-manifest.json", json.dumps(manifest, indent=2) + "\n")

        elapsed = time.time() - started
        print()
        print(f"Built {len(combined)} headline(s) "
              f"({len(feed_items)} from feeds, {len(posts)} original) "
              f"in {elapsed:.1f}s → {self.outdir}")
        if self.failed:
            print(f"{len(self.failed)} feed(s) failed this run:")
            for name, err in self.failed:
                print(f"  - {name}: {err}")
            if not self.prod_build:
                return 2
            print("Production build: publishing anyway so a flaky feed does not skip the deploy.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the Speed-Demon News static site.")
    parser.add_argument(
        "--preview-merch",
        action="store_true",
        help="Build /merch/ even if merch.enabled is false. Still hidden from nav, footer, and sitemap.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: public/). Use a separate folder to preview merch without changing public/.",
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Use base_url and base_path from site.yaml (the GitHub Pages URL). Default is a local preview at http://127.0.0.1:8080/.",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Force local preview URLs even if GITHUB_ACTIONS or SDN_BUILD=prod is set.",
    )
    args = parser.parse_args()
    preview = args.preview_merch or os.environ.get("PREVIEW_MERCH", "").strip().lower() in {"1", "true", "yes"}
    return SiteBuilder(
        output=args.output,
        preview_merch=preview,
        prod=args.prod,
        force_local=args.local,
    ).build()


if __name__ == "__main__":
    sys.exit(main())
