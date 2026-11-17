#!/usr/bin/env python3
"""Draft X, Facebook, and Instagram/TikTok copy from a recap Markdown file.

Local drafts only. This script does not post anywhere, does not open social
apps, and does not publish the recap. It uses the recap's title, summary,
body, and source credit — it does not invent names, results, quotes, or beef.

Usage:
    python social_posts.py content/posts/your-recap.md
    python social_posts.py content/posts/a.md content/posts/b.md -o social/out.md
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "content" / "posts"
SOCIAL = ROOT / "social"
LINK_PLACEHOLDER = "[link]"
X_LIMIT = 280

# Only attach @handles we have actually confirmed. Everyone else is "via Name".
KNOWN_CREDITS = {
    "1320video blog": "via @1320Video",
    "1320video": "via @1320Video",
    "1320 video": "via @1320Video",
    "dirtcar racing": "via DIRTcar",
    "dirtcar": "via DIRTcar",
    "world of outlaws": "via @WorldofOutlaws",
    "speed sport": "via @SPEEDSPORT",
    "speedsport": "via @SPEEDSPORT",
    "dirton dirt": "via @DirtonDirt",
    "dirtondirt": "via @DirtonDirt",
    "lucas oil late model dirt series": "via @lucasdirt",
    "floracing": "via @FloRacing",
    "street outlaws": "via @StreetOutlaws",
}

CATEGORY_TAGS = {
    "street": ["StreetRacing", "GrudgeRacing", "NoPrep", "DragRacing"],
    "drag": ["DragRacing", "NHRA", "Sportsman"],
    "dirt": ["DirtRacing", "ShortTrack", "DirtTrack"],
    "nascar": ["NASCAR", "StockCar"],
    "f1": ["Formula1", "F1"],
    "indycar": ["IndyCar", "OpenWheel"],
    "imsa": ["IMSA", "Sportscar"],
}

STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "to", "for", "at", "in", "on", "is",
    "are", "was", "were", "be", "as", "with", "from", "after", "before", "over",
    "out", "into", "this", "that", "these", "those", "his", "her", "their",
    "its", "it's", "than", "then", "just", "also", "says", "said", "via",
    "record", "title", "grabs", "takes", "wins", "won", "back", "best",
    "brings", "another", "year", "years", "last", "this", "time", "times",
    "fifth", "first", "second", "third", "fourth", "new", "old", "vs",
    "against", "about", "into", "draft", "recap", "source", "link",
}

CREDIT_LINE_RE = re.compile(
    r"(?is)^(\*\*source:\*\*|that's (the story|what|the result|the preview)|"
    r"read it from them|the original |if it isn't in that source|"
    r"we didn't add|nobody in (that|the) (source|feed)|"
    r"that's what .+ published).*"
)

def parse_post(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path} has no YAML front matter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path} front matter is incomplete")
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    paras = []
    for raw in re.split(r"\n\s*\n", body):
        line = " ".join(raw.split()).strip()
        if not line or CREDIT_LINE_RE.match(line):
            continue
        paras.append(line)
    summary = str(meta.get("summary") or "").strip()
    title = str(meta.get("title") or path.stem).strip()
    source = str(meta.get("recap_source") or meta.get("source") or "").strip()
    return {
        "path": path,
        "title": title,
        "date": str(meta.get("date") or ""),
        "category": str(meta.get("category") or ""),
        "summary": summary,
        "source": source,
        "recap_of": str(meta.get("recap_of") or ""),
        "paras": paras,
        "body": body,
    }


def credit_for(source: str) -> str:
    key = re.sub(r"\s+", " ", (source or "").strip().lower())
    if key in KNOWN_CREDITS:
        return KNOWN_CREDITS[key]
    for needle, credit in KNOWN_CREDITS.items():
        if needle and needle in key:
            return credit
    if not source:
        return "via the source"
    short = re.sub(r"\s+(Racing|Blog|News|Official)$", "", source, flags=re.I).strip()
    return f"via {short or source}"


def tighten(text: str, source: str = "") -> str:
    """Drop source-attribution lead-ins so the credit can live at the end.

    Only removes a 'Source says' / 'They wrote:' prefix. Never rewrites facts.
    """
    text = text or ""
    # Do not let a generic 'Name says' pattern eat the previous sentence.
    if source:
        names = [source]
        short = re.sub(r"\s+(Racing|Blog|News|Official)$", "", source, flags=re.I).strip()
        if short and short.lower() != source.lower():
            names.append(short)
        for name in names:
            text = re.sub(rf"\b{re.escape(name)}\s+says\s+", "", text, flags=re.I)
    text = re.sub(r"\bThey wrote:\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[,;:\-–—]\s*", "", text)
    # If we stripped a mid-sentence 'Source says', we may have left
    # 'weekend. Brett …' which is already fine. Fix a doubled period.
    text = re.sub(r"\.\s*\.", ".", text)
    return text


def first_sentences(text: str, n: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    return " ".join(parts[:n]).strip()


def _end_punct(text: str) -> str:
    text = (text or "").strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def fit_x(core: str, credit: str, limit: int = X_LIMIT) -> str:
    suffix = f" {credit} {LINK_PLACEHOLDER}"
    core = tighten(core)
    candidate = _end_punct(core)
    if len(candidate) + len(suffix) <= limit:
        return candidate + suffix
    # Drop the last sentence and try again.
    parts = re.split(r"(?<=[.!?])\s+", core)
    while len(parts) > 1:
        parts = parts[:-1]
        candidate = _end_punct(" ".join(parts))
        if len(candidate) + len(suffix) <= limit:
            return candidate + suffix
    budget = limit - len(suffix) - 1  # leave room for a final period
    trimmed = core[:budget].rsplit(" ", 1)[0].rstrip(",;:-")
    return _end_punct(trimmed) + suffix


def x_post(post: dict, credit: str) -> str:
    summary = tighten(post["summary"], post["source"])
    title = post["title"].strip()
    # Prefer the summary — it is already extractive and punchy.
    if summary:
        return fit_x(summary, credit)
    if title:
        return fit_x(title, credit)
    if post["paras"]:
        return fit_x(post["paras"][0], credit)
    return fit_x("Draft recap", credit)


def facebook_post(post: dict, credit: str) -> str:
    text = tighten(post["summary"], post["source"]) or " ".join(post["paras"][:2])
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    lines = sentences[:3]
    if len(lines) < 2 and post["title"] and (not lines or lines[0].lower().rstrip(".") != post["title"].lower().rstrip(".")):
        lines.insert(0, post["title"].rstrip("."))
    if len(lines) < 2 and post["paras"]:
        for para in post["paras"]:
            if para not in lines:
                lines.append(para)
            if len(lines) >= 3:
                break
    lines = lines[:3]
    if not lines:
        lines = [post["title"] or "Draft recap"]
    lines.append(f"{credit} — {LINK_PLACEHOLDER}")
    return "\n\n".join(lines)


def tagify(token: str) -> str | None:
    token = re.sub(r"^[#@$]+", "", token)
    token = re.sub(r"[^A-Za-z0-9]", "", token)
    if len(token) < 3 or token.lower() in STOP_WORDS or token.isdigit():
        return None
    if token.isupper() and len(token) <= 12:
        return token
    return token[0].upper() + token[1:]



def _phrase_tag(pattern: str, label: str | None, text: str) -> str | None:
    m = re.search(pattern, text, flags=re.I)
    if not m:
        return None
    if label:
        return label
    raw = m.group(0)
    if raw.startswith("$"):
        # $30,000 / $30K -> 30K
        digits = re.sub(r"[^0-9]", "", raw)
        if digits.endswith("000") and len(digits) <= 6:
            return digits[:-3] + "K"
        return digits + "K" if not raw.lower().endswith("k") else re.sub(r"[^0-9A-Za-z]", "", raw)
    return re.sub(r"[^A-Za-z0-9]", "", raw).upper()


NAME_SKIP = {
    "champion", "equipment", "racing", "modifieds", "weekend", "blog",
    "record", "failure", "title", "finals", "showdown", "career",
    "action", "event", "preview", "source", "draft", "news", "article",
    "episode", "recap", "post", "feed", "story", "win", "wins", "time",
    "times", "year", "years", "day", "days", "north", "south", "east",
    "west", "carolina", "official", "series",
}


def proper_names(text: str) -> list[str]:
    """Pull short proper names from sentence-case recap text, not Title Case titles."""
    names: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        # Split lists so "Fred, Witty, and Reece" stays three names, not one blob.
        clauses = re.split(r",|\s+and\s+", sentence)
        for ci, clause in enumerate(clauses):
            words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-]*", clause)
            # A clause that is only a name (common in comma lists) is always fair game.
            list_item = len(words) <= 3 and words and all(
                re.match(r"^[A-Z]", w) or w.lower() == "the" for w in words
            )
            i = 0
            while i < len(words):
                w = words[i]
                starts_cap = bool(re.match(r"^[A-Z]", w)) or bool(re.match(r"^[0-9]+[A-Z]", w))
                is_code = bool(re.search(r"\d", w)) or (w.isupper() and len(w) >= 3)
                next_the = (
                    i + 2 < len(words)
                    and words[i + 1].lower() == "the"
                    and re.match(r"^[A-Z]", words[i + 2])
                )
                next_cap = i + 1 < len(words) and bool(re.match(r"^[A-Z]", words[i + 1]))
                sentence_initial = ci == 0 and i == 0 and not list_item
                if starts_cap and (not sentence_initial or next_cap or next_the or is_code or list_item):
                    if next_the:
                        chunk = [w, words[i + 1], words[i + 2]]
                        i += 3
                    elif next_cap:
                        # Two-word names only. A longer cap run is usually a title, not a hashtag.
                        run = 1
                        while i + run < len(words) and re.match(r"^[A-Z]", words[i + run]):
                            run += 1
                        if run == 2:
                            chunk = [w, words[i + 1]]
                            i += 2
                        else:
                            i += run
                            continue
                    else:
                        chunk = [w]
                        i += 1
                    if any(c.lower() in NAME_SKIP for c in chunk if c.lower() != "the"):
                        continue
                    joined = " ".join(chunk)
                    if len(re.sub(r"[^A-Za-z0-9]", "", joined)) > 22:
                        continue
                    names.append(joined)
                    continue
                i += 1
    return names


def hashtags(post: dict, count: int = 7) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    blob = " ".join([post["title"], post["summary"], " ".join(post["paras"])])

    def add(raw: str | None) -> None:
        if not raw:
            return
        tag = tagify(raw)
        if not tag:
            return
        # Drop source suffixes and overlong blends ("1320VideoBlog", giant phrases).
        tag = re.sub(r"(Blog|Racing|News|Official)$", "", tag)
        if len(tag) < 3 or len(tag) > 22:
            return
        if tag.lower() in NAME_SKIP or tag.lower() in STOP_WORDS:
            return
        key = tag.lower()
        if key in seen or any(key == s[1:].lower() for s in tags):
            return
        # If we already have a longer tag that starts with this one, skip the short dupe
        # unless this is a 3-4 letter code.
        if len(tag) > 4 and any(s[1:].lower().startswith(key) and s[1:].lower() != key for s in tags):
            return
        seen.add(key)
        tags.append("#" + tag)

    for pattern, label in [
        (r"stick[ -]?shift", "StickShift"),
        (r"small[ -]?tire", "SmallTire"),
        (r"talkin['’]?\s*shift", "TalkinShift"),
        (r"world short track", "WorldShortTrack"),
        (r"ump modified", "UMPModifieds"),
        (r"the dirt track", "TheDirtTrack"),
        (r"no[ -]?prep", "NoPrep"),
        (r"power wheelie", "PowerWheelie"),
        (r"sct\s*nashville", "SCTNashville"),
        (r"fl2k\d*", None),
        (r"\$\s*\d+(?:,\d{3})*(?:k|K)?", None),
    ]:
        add(_phrase_tag(pattern, label, blob))

    # Event codes and acronyms (FL2K26, UMP, SCT, NHRA) from anywhere.
    for tok in re.findall(r"\b(FL2K\d+|[A-Z]{3,}\d*|\$\d+K)\b", blob):
        add(tok.replace("$", ""))

    # Source name is high priority so it is not crowded out by first names.
    if post["source"]:
        short = re.sub(r"\s+(Racing|Blog|News|Official)$", "", post["source"], flags=re.I).strip()
        add(re.sub(r"\s+", "", short))

    names = proper_names(" ".join([post["summary"], " ".join(post["paras"])]))
    names = sorted(names, key=lambda n: (0 if " " in n else 1))
    for name in names:
        add(re.sub(r"\s+", "", name))

    for tag in CATEGORY_TAGS.get(post["category"], []):
        add(tag)

    for pad in CATEGORY_TAGS.get(post["category"], ["Racing"]):
        if len(tags) >= 5:
            break
        add(pad)
    if len(tags) < 5:
        add("Racing")
    # Prefer 5-8 tags.
    if len(tags) > 8:
        tags = tags[:8]
    return tags


def instagram_post(post: dict, credit: str) -> str:
    chunks: list[str] = []
    if post["paras"]:
        # Keep 1-2 body paragraphs; they already stay on source facts.
        chunks.extend(post["paras"][:2])
    elif post["summary"]:
        chunks.append(tighten(post["summary"], post["source"]))
    else:
        chunks.append(post["title"])
    chunks.append(f"{credit}\n{LINK_PLACEHOLDER}")
    caption = "\n\n".join(chunks).strip()
    tags = hashtags(post)
    if tags:
        caption += "\n\n" + " ".join(tags)
    return caption


def render_one(post: dict) -> str:
    credit = credit_for(post["source"])
    x = x_post(post, credit)
    fb = facebook_post(post, credit)
    ig = instagram_post(post, credit)
    rel = post["path"]
    try:
        rel = post["path"].resolve().relative_to(ROOT)
    except ValueError:
        rel = post["path"]
    src_line = f"Source: {post['source']}" if post["source"] else "Source: (none listed in front matter)"
    if post["recap_of"]:
        src_line += f" — {post['recap_of']}"
    lines = [
        f"## {post['title']}",
        "",
        f"Recap: `{rel}`  ",
        src_line,
        "",
        f"### X ({len(x)} characters)",
        "",
        x,
        "",
        "### Facebook",
        "",
        fb,
        "",
        "### Instagram / TikTok",
        "",
        ig,
        "",
    ]
    if len(x) > X_LIMIT:
        lines.append(f"_Warning: the X draft is {len(x)} characters, over the 280 limit. Trim before posting._")
        lines.append("")
    return "\n".join(lines)


def render_file(posts: list[dict]) -> str:
    today = date.today().strftime("%-d %b %Y") if sys.platform != "win32" else date.today().isoformat()
    header = [
        f"# Social drafts — {today} (America/Chicago)",
        "",
        "Drafts only. Nothing in this file has been posted. Every line is taken "
        "from the recap (itself drafted from the source feed). "
        f"`{LINK_PLACEHOLDER}` is a placeholder for the Speed-Demon News article URL "
        "once a recap is published.",
        "",
        "This file was generated by `python social_posts.py`. It does not post anywhere.",
        "",
        "---",
        "",
    ]
    parts = [render_one(p).rstrip() for p in posts]
    return "\n".join(header) + "\n\n---\n\n".join(parts) + "\n"


def default_out_path(posts: list[dict]) -> Path:
    SOCIAL.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    if len(posts) == 1:
        stem = posts[0]["path"].stem
        return SOCIAL / f"{stem}-social.md"
    return SOCIAL / f"{today}-recaps.md"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Draft X, Facebook, and Instagram/TikTok copy from a recap. Local only — does not post."
    )
    parser.add_argument(
        "posts",
        nargs="+",
        metavar="post.md",
        help="Path to a recap Markdown file (content/posts/…)",
    )
    parser.add_argument(
        "-o",
        "--out",
        help="Write drafts to this path (default: social/<slug>-social.md)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print drafts only; do not write a file",
    )
    args = parser.parse_args()

    loaded: list[dict] = []
    for raw in args.posts:
        path = Path(raw)
        if not path.is_file():
            alt = POSTS / raw
            if alt.is_file():
                path = alt
        if not path.is_file():
            print(f"Could not find recap file: {raw}", file=sys.stderr)
            return 1
        try:
            loaded.append(parse_post(path))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    text = render_file(loaded)
    if not args.stdout:
        out = Path(args.out) if args.out else default_out_path(loaded)
        if not out.is_absolute():
            out = (ROOT / out) if not out.parent.parts or out.parts[0] != "social" else ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        try:
            shown = out.resolve().relative_to(ROOT)
        except ValueError:
            shown = out
        print(f"Wrote {shown}  (drafts only; nothing was posted)")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
