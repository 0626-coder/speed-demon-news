#!/usr/bin/env python3
"""Local-only form for creating Markdown posts. Binds to 127.0.0.1 only."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import yaml
from flask import Flask, redirect, render_template_string, request

# Import the writer from the CLI tool so both paths stay in sync.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from new_post import load_categories, write_post  # noqa: E402

HOST = "127.0.0.1"
PORT = 8090
ROOT = Path(__file__).resolve().parent

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>New post — local only</title>
  <style>
    :root { color-scheme: dark; }
    body { font-family: "Segoe UI", system-ui, sans-serif; background: #0a0b0d; color: #f3f1ea; margin: 0; }
    main { max-width: 40rem; margin: 2rem auto; padding: 0 1rem 3rem; }
    h1 { font-size: 1.6rem; }
    .note { border: 1px solid #ffb000; background: rgba(255,176,0,.08); padding: .8rem 1rem; border-radius: 10px; }
    label { display: block; margin: 1rem 0 .3rem; font-weight: 650; }
    input, select, textarea { width: 100%; box-sizing: border-box; background: #16181d; color: inherit; border: 1px solid #2a2d34; border-radius: 8px; padding: .55rem .7rem; font: inherit; }
    textarea { min-height: 16rem; }
    button { margin-top: 1.2rem; background: #ffb000; color: #1a1200; border: 0; font-weight: 700; padding: .6rem 1rem; border-radius: 999px; cursor: pointer; }
    .ok { background: #132016; border: 1px solid #3dff6e; padding: .8rem 1rem; border-radius: 10px; }
    code { color: #ffb000; }
  </style>
</head>
<body>
  <main>
    <h1>New original post</h1>
    <p class="note">This form is local only (<code>127.0.0.1:{{ port }}</code>). It writes a Markdown file under <code>content/posts</code>. It does not publish or deploy anything. After saving, run <code>python build.py</code> and refresh the static site.</p>
    {% if saved %}
    <p class="ok">Wrote <code>{{ saved }}</code>. Rebuild with <code>python build.py</code> to see it on the site.</p>
    {% endif %}
    {% if error %}<p class="note">{{ error }}</p>{% endif %}
    <form method="post">
      <label for="title">Title</label>
      <input id="title" name="title" required value="{{ title }}">
      <label for="date">Date</label>
      <input id="date" name="date" type="date" required value="{{ date }}">
      <label for="category">Category</label>
      <select id="category" name="category">
        {% for cat in categories %}
        <option value="{{ cat }}" {% if cat == category %}selected{% endif %}>{{ cat }}</option>
        {% endfor %}
      </select>
      <label for="summary">Summary</label>
      <input id="summary" name="summary" value="{{ summary }}">
      <label for="image">Image (URL or filename in content/images)</label>
      <input id="image" name="image" value="{{ image }}">
      <label for="body">Body (Markdown)</label>
      <textarea id="body" name="body" required>{{ body }}</textarea>
      <button type="submit">Save Markdown file</button>
    </form>
  </main>
</body>
</html>
"""

app = Flask(__name__)


@app.get("/")
def form():
    return render_template_string(
        PAGE,
        port=PORT,
        categories=load_categories(),
        title="",
        date=date.today().isoformat(),
        category="drag",
        summary="",
        image="",
        body="",
        saved="",
        error="",
    )


@app.post("/")
def save():
    title = request.form.get("title", "").strip()
    post_date = request.form.get("date", date.today().isoformat()).strip()
    category = request.form.get("category", "drag").strip()
    summary = request.form.get("summary", "").strip()
    image = request.form.get("image", "").strip()
    body = request.form.get("body", "").strip()
    categories = load_categories()
    error = ""
    saved = ""
    if not title or not body:
        error = "Title and body are required."
    elif category not in categories:
        error = "Pick a valid category."
    else:
        path = write_post(title, category, summary, body, post_date, image)
        saved = str(path.relative_to(ROOT))
    return render_template_string(
        PAGE,
        port=PORT,
        categories=categories,
        title=title,
        date=post_date,
        category=category,
        summary=summary,
        image=image,
        body=body,
        saved=saved,
        error=error,
    )


def main() -> int:
    print(f"Local admin form: http://{HOST}:{PORT}")
    print("This process binds only to localhost and never deploys.")
    app.run(host=HOST, port=PORT, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
