#!/usr/bin/env python3
"""Create an original Markdown post in content/posts (local only)."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "content" / "posts"


def load_categories() -> list[str]:
    data = yaml.safe_load((ROOT / "feeds.yaml").read_text(encoding="utf-8"))
    return [c["id"] for c in data.get("categories", [])]


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "post"


def prompt(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or (default or "")


def write_post(title: str, category: str, summary: str, body: str, post_date: str, image: str) -> Path:
    POSTS.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)
    filename = f"{post_date}-{slug}.md"
    path = POSTS / filename
    n = 2
    while path.exists():
        path = POSTS / f"{post_date}-{slug}-{n}.md"
        n += 1
    image_line = image if image else ""
    # Use a small manual front matter block so the file stays easy to edit.
    lines = [
        "---",
        f'title: "{title.replace(chr(34), chr(39))}"',
        f"date: {post_date}",
        f"category: {category}",
        f'summary: "{summary.replace(chr(34), chr(39))}"' if summary else "summary:",
        f"image: {image_line}",
        "---",
        "",
        body.rstrip() + "\n",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    categories = load_categories()
    parser = argparse.ArgumentParser(
        description="Create a Markdown post in content/posts. Local only; does not publish."
    )
    parser.add_argument("--title")
    parser.add_argument("--category", choices=categories)
    parser.add_argument("--summary", default="")
    parser.add_argument("--date", default="", help="YYYY-MM-DD (defaults to today)")
    parser.add_argument("--image", default="", help="Optional image URL or filename in content/images")
    parser.add_argument("--body", default="", help="Post body. If omitted, read stdin or open a prompt.")
    args = parser.parse_args()

    interactive = not args.title
    title = args.title or prompt("Title")
    if not title:
        print("A title is required.", file=sys.stderr)
        return 1
    default_cat = "drag"
    if args.category:
        category = args.category
    elif interactive:
        print("Categories: " + ", ".join(categories))
        category = prompt("Category", default_cat)
    else:
        category = default_cat
    if category not in categories:
        print(f"Unknown category {category!r}. Use one of: {', '.join(categories)}", file=sys.stderr)
        return 1
    post_date = args.date or (prompt("Date YYYY-MM-DD", date.today().isoformat()) if interactive else date.today().isoformat())
    try:
        datetime.strptime(post_date, "%Y-%m-%d")
    except ValueError:
        print("Date must be YYYY-MM-DD.", file=sys.stderr)
        return 1
    summary = args.summary if args.summary or not interactive else prompt("Summary (optional)")
    image = args.image if args.image or not interactive else prompt("Image URL or content/images filename (optional)")
    if args.body:
        body = args.body
    elif not sys.stdin.isatty():
        body = sys.stdin.read()
    elif interactive:
        print("Body (end with a line containing only '.'):")
        lines = []
        while True:
            line = input()
            if line.strip() == ".":
                break
            lines.append(line)
        body = "\n".join(lines)
    else:
        body = ""
    if not body.strip():
        body = "Draft body — replace this text."
    path = write_post(title, category, summary, body, post_date, image)
    print(f"Wrote {path.relative_to(ROOT)}")
    print("Rebuild with: python build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
