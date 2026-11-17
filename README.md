# Speed-Demon News

A racing news site rebuilt with one command. Headlines come from public RSS/Atom feeds. Original articles are Markdown files. It does not create accounts, post to social media, or talk to a paid service.

The site name is **Speed-Demon News**. **Willseys Wonderland** is the team page and sits first in the top nav; the homepage opens with a band that points there. The news pile leads with Outlaw Racing (the Grudge Board), then drag strip / NHRA, dirt, NASCAR, and IMSA. The live site is on GitHub Pages at [https://0626-coder.github.io/speed-demon-news/](https://0626-coder.github.io/speed-demon-news/). No custom domain has been purchased.

The site is built for someone with little daily spare time: fetch headlines automatically, write a post only when you want to, and host it later for free.

## What you get

- Homepage of latest headlines. A **Willseys Wonderland** band sits at the top of the news column. **Outlaw Racing (Grudge Board)** is featured next, and outlaw stories are ranked first in the main grid. The top nav is **Willseys Wonderland**, **Latest**, **Live** (red dot), **Follow**, and **About**. Categories live in a left sidebar.
- News pages (home and every category) use a full-width layout: sticky sidebar filters on the left, a multi-column headline grid on the right. On phones, filters collapse into a **Filters** button that opens a drawer.
- Sidebar filters: Category (Outlaw Racing first, then Drag, Dirt, NASCAR, IMSA — also real pages for SEO and no-JS), Dirt class (sprints, late models, modifieds, midgets/USAC, micros, stock cars, karts), Source, Type (Articles / Videos / Our stories), Date (Today, This week, All), a search box, and an Engines / Tech toggle. Filtering is client-side. A compact **Follow the crew** block sits under the filters.
- YouTube items as cards with a thumbnail and channel name; click to lazy-load a YouTube embed, or open the video on YouTube
- Original articles mixed into the homepage and the matching category; recap drafts stay unpublished until approved
- **Willseys Wonderland** (`/willseys-wonderland/`), the team adventures page: a photo and video gallery driven by `content/wonderland.yaml` and optional Markdown posts in `content/wonderland/`
- **Live page** with lazy-loaded YouTube livestream players for 1320Video, DRAG LENS, Lens 660, and BoostedGT, plus official where-to-watch links for NHRA, DIRTVision, and FloRacing
- **Follow page** (`/follow/`) with official social accounts grouped Outlaw Racing first, then Drag, Dirt, and the rest. Add people in `content/follow.yaml`.
- About page, basic SEO (title, meta description, Open Graph), `sitemap.xml`, `robots.txt`, and an RSS feed of this site's aggregated items
- Merch page for shirts and hats, hidden until you flip `merch.enabled` on in `site.yaml`
- Dark, mobile-friendly, a little grittier, no trackers

## Folder structure

```
racing-news-site/
  build.py              One-command rebuild (fetch feeds + render pages)
  build.sh              Same thing, using .venv when it exists
  new_post.py           CLI to create a Markdown post
  admin.py              Local-only form (127.0.0.1:8090) that writes the same files
  write_recap.py        Draft a recap from one feed item (stays draft until approved)
  social_posts.py       Draft X / Facebook / Instagram copy from a recap (does not post)
  social/                Social drafts for recaps (not posted)
  serve.py              Local preview server for public/
  requirements.txt
  site.yaml             Site name, tagline, base URL, merch on/off flag
  feeds.yaml            Feed URLs and categories — add a series here later
  content/
    posts/              Original articles (Markdown + front matter)
    images/             Optional local images referenced by posts
    merch.yaml          Merch catalog (shirts and hats). Page stays hidden until enabled
    live.yaml           Live page channels and official where-to-watch links
    follow.yaml         Follow page accounts and official social URLs
    wonderland.yaml     Willseys Wonderland gallery entries
    wonderland/         Optional Markdown adventure posts for the team page
  templates/            Jinja HTML templates
  static/               CSS, scripts, logo, and team media in static/wonderland/
  public/               Generated site (safe to delete; rebuild recreates it)
```

## How to build

From this folder, once:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then, whenever you want fresh headlines or after you add a post:

```bash
python build.py
```

or:

```bash
./build.sh
```

A plain `./build.sh` (or `python build.py`) writes links for **http://127.0.0.1:8080/**, even though `site.yaml` holds the public GitHub Pages URL. That keeps the local preview and the box refresh routine working without extra flags.

Preview locally (does not deploy):

```bash
python serve.py
```

Open http://127.0.0.1:8080/

To build the way the live site does — links under `/speed-demon-news/` — run:

```bash
./build.sh --prod
```

You can also set `SDN_BUILD=prod`, or override the URL with `SDN_BASE_URL` and `SDN_BASE_PATH`. `--local` forces preview URLs even if those are set. GitHub Actions uses `--prod` automatically.

The live site rebuilds itself three times a day (see below). You do not need to babysit it.

## How to post an original article

Create a Markdown file in `content/posts` with this front matter:

```markdown
---
title: "Your headline"
date: 2026-11-11
category: drag
summary: "One or two sentences."
image:
---

Your article in Markdown. Do not paste a full article from another site.
```

`category` must be one of: `street` (Outlaw Racing; the public URL is `/category/outlaw-racing/`), `drag`, `dirt`, `nascar`, `imsa`.

`image` is optional. Use a full `https://…` URL, or a filename that lives in `content/images/`.

Two helpers, both local only:

```bash
python new_post.py
```

```bash
python admin.py
```

The admin form binds to **127.0.0.1:8090** only. It writes a file under `content/posts`. It does not publish anything. Run `python build.py` after you save, then refresh the preview.

### Draft recaps from a source item

`python write_recap.py` turns one feed article or YouTube video (title + feed description only) into a Markdown recap in `content/posts`. The voice is casual. It only uses names, cars, results, and drama that actually appear in the source, and it credits and links that source at the top and bottom. Posts are `draft: true` by default, and `build.py` skips drafts until you change that to `false`.

```bash
python write_recap.py --list
python write_recap.py --url "https://example.com/story"
python write_recap.py --source "1320Video Blog" --query "FL2K"
```

### Social drafts from a recap

`python social_posts.py content/posts/your-recap.md` turns one recap into an X draft (under 280 characters), a short Facebook post, and an Instagram/TikTok caption with hashtags. It credits the source and uses `[link]` as a placeholder for the Speed-Demon News article URL. It does not post anywhere. The three sample recaps have hand-written drafts in `social/2026-11-15-recaps.md`.

```bash
python social_posts.py content/posts/your-recap.md
python social_posts.py content/posts/a.md content/posts/b.md -o social/out.md
```


## Merch page (hidden for now)

There is a merch page at `/merch/` for Speed-Demon News shirts and hats, but it stays **off** until the designs are ready. With `merch.enabled: false` (the default in `site.yaml`), a normal rebuild does **not** write the page into `public/`, does **not** link it in the nav or footer, and does **not** list it in `sitemap.xml`. The scheduled 3×/day rebuild uses a normal build, so it stays hidden.

### Preview it locally

This builds the merch page without putting it in the nav, footer, or sitemap. Write to a temp folder so `public/` stays in the hidden state the live preview server uses:

```bash
./build.sh --preview-merch --output /tmp/sdn-merch-preview
python serve.py --directory /tmp/sdn-merch-preview --port 8081
```

Then open http://127.0.0.1:8081/merch/  (stop that server when you are done; leave `python serve.py` on port 8080 for the normal site).

You can also set `PREVIEW_MERCH=1` instead of passing `--preview-merch`. If you omit `--output`, the merch page is written into `public/merch/` still unlinked — useful if you want to peek at http://127.0.0.1:8080/merch/ — but a later normal `./build.sh` will remove it again.

### Turn it on

When the shirts and hats are ready, set this in `site.yaml` and rebuild:

```yaml
merch:
  enabled: true
```

```bash
./build.sh
```

Merch then appears in the nav (just before About), in the footer, at `/merch/`, and in `sitemap.xml`.

### Add items

Edit `content/merch.yaml`. Each item uses:

| Field | What it is |
| --- | --- |
| `name` | Product name, or `Shirt design coming soon` / `Hat design coming soon` for placeholders |
| `type` | `shirt`, `hat`, or `other` |
| `image` | Optional filename in `content/images/`, a path relative to the project root, or a full `https://` URL. Leave blank to use the default shirt or hat art |
| `price` | Optional, like `$28` or `28`. Leave blank on placeholders — prices are not shown then |
| `buy_url` | Optional checkout or product-page link. Leave blank until that item is for sale |
| `placeholder` | `true` for coming-soon cards (the default when `buy_url` is empty). Set `false` once the item is real |

Kicker, headline, lede, and the “designs drop soon” note at the bottom of the page are also in that file. Rebuild after you edit it.


## Live page

The public Live page is at `/live/` (nav item **Live**, after Latest, with a red pulsing dot). It is in the footer and in `sitemap.xml`.

### Outlaw Racing livestreams (first)

The first section embeds YouTube live players for 1320Video, DRAG LENS, Lens 660, and BoostedGT. Nothing loads from YouTube until you click **Watch live / latest** on a card. The player uses the privacy-enhanced embed:

```
https://www.youtube-nocookie.com/embed/live_stream?channel=CHANNEL_ID
```

If the channel is not live, YouTube's player shows an offline or upcoming state. Under each card are the channel's three latest videos from the current feed pull, plus links to that channel's YouTube `/live` and `/streams` pages.

### Track — where to watch (second)

NHRA national-event coverage is on FOX or FS1 and the FOX One app for the 2026 Mission Foods season. NHRA.tv is the official stream for those national events (paid). Some Lucas Oil Drag Racing Series divisionals stream free on NHRA.tv and the official NHRA YouTube page. Those streams are not embedded. The page links the official 2026 schedule and the official announcements instead of listing dates.

Dirt streaming is the same idea: official links only, no embeds, no invented dates.

- **DIRTVision** — official live home for World of Outlaws Sprint Cars and Late Models, Super DIRTcar Series, ASCS, and DIRTcar Summer Nationals
- **FloRacing** — official streaming home for the Lucas Oil Late Model Dirt Series presented by FloRacing, High Limit Racing, and USAC

FloRacing's NHRA national-event deal starts in **2027**, so it is not listed as a 2026 NHRA stream.

### Add or change a channel

Edit `content/live.yaml` and rebuild. YouTube channels use:

| Field | What it is |
| --- | --- |
| `name` | Channel name as it should appear |
| `youtube_channel_id` | The `UC…` id (required for the player). Must be a 24-character YouTube channel id |
| `handle` | Optional `@handle` without the at-sign, used for `/live` and `/streams` links |
| `category` | One of the site category ids, usually `street` (shown as Outlaw Racing) |
| `section` | `street` (first block, Outlaw Racing livestreams) or `other` (Other live channels) |
| `note` | Short, factual blurb |
| `watch_url` | Optional. Use this instead of a channel id for a link-only card |
| `enabled` | `false` to hide without deleting |

Official TV or paid-stream cards go under `watch:` with `name`, `category`, `note`, and a `links:` list of `{label, url}` (https only). Put extra YouTube channels in `other_channels:` (same fields as `channels:`).


## Follow page

The public Follow page is at `/follow/` (nav item **Follow**, after Live). A short **Follow the crew** list also appears in the homepage and category sidebars. The page is in the footer and in `sitemap.xml`.

To add someone, edit `content/follow.yaml` and rebuild. Only add URLs you have confirmed belong to that person or team. Do not guess handles.

| Field | What it is |
| --- | --- |
| `name` | Display name |
| `category` | Site category id: `street` (Outlaw Racing), `drag`, `dirt`, `nascar`, or `imsa` |
| `note` | Optional short, factual blurb |
| `featured` | `true` to include the account in the sidebar highlights |
| `platforms` | A map of platform keys to full `https://` URLs. Supported keys: `youtube`, `x`, `instagram`, `facebook`, `tiktok`. Leave a platform out if you cannot verify it |
| `enabled` | `false` to hide without deleting |

Cards are grouped by category, Outlaw Racing first. Every link opens in a new tab with `rel="noopener noreferrer"`.

## Willseys Wonderland

The team page is at `/willseys-wonderland/` and is the first item in the top nav. The homepage opens with a Willseys Wonderland band (the latest adventure, or a “First adventure coming soon” card) and a button to that page. It is in the footer and in `sitemap.xml`.

There is no invented media and no stock photography. Until real photos or video are added, the page shows only the coming-soon card.

### Add photos or video

1. Put media files in `static/wonderland/`.
2. Add an entry to `content/wonderland.yaml` (or a Markdown file in `content/wonderland/`).
3. Rebuild with `./build.sh` (or push to `main` for the live site).

The bot will do those steps when you upload media.

**File guidance**

- Photos: JPG, PNG, or WebP, preferably under 5 MB. The build resizes images to a maximum of 1,600 pixels on the long edge and writes a 640px thumbnail (Pillow is in `requirements.txt`).
- Video: MP4 (H.264), preferably under 50 MB. GitHub will reject files over 100 MB. Longer clips are better as a YouTube link.
- YouTube: a video id, or a full watch / youtu.be / shorts / embed URL. The player lazy-loads with the privacy-enhanced embed, same as the rest of the site.

YAML adventure fields: `date` (YYYY-MM-DD), `title`, optional `caption`, optional `tags`, optional `cover` (defaults to the first image), and `media` (a list of `{type, src, alt?, caption?}`). `type` is `image`, `video`, or `youtube`. Set `enabled: false` to hide an entry without deleting it.

Markdown posts in `content/wonderland/` use the same front matter plus a write-up in the body. Those get their own page at `/willseys-wonderland/<slug>/` and are listed newest first with the YAML entries.

Photos open in a lightbox. Local video plays in an HTML5 `<video>` player. YouTube items use the same click-to-load embed as the news cards.




## Feeds on this site

Each of these was checked with curl and returned real feed items before being added. YouTube's public channel RSS (`https://www.youtube.com/feeds/videos.xml?channel_id=...`) can 404 or 500 intermittently; the builder retries those feeds. The build script drops a feed for that run if it still fails, and keeps the rest.

**Outlaw Racing (featured) — "Grudge Board"**

The homepage featured news section, just under the Willseys Wonderland band. Outlaw Racing is the first category in the sidebar, right after All. The public URL is `/category/outlaw-racing/`. The old `/category/street/` address redirects there.

- 1320Video (YouTube, channel ID `UC0PXqiud6dbwOAk8RvslgpQ`) — https://www.youtube.com/feeds/videos.xml?channel_id=UC0PXqiud6dbwOAk8RvslgpQ — also https://www.youtube.com/@1320video
- 1320Video Blog — https://1320video.com/blogs/news.atom
- DRAG LENS (YouTube, channel ID `UCNgmfWYknbb-qhzQXQkHuLQ`) — https://www.youtube.com/feeds/videos.xml?channel_id=UCNgmfWYknbb-qhzQXQkHuLQ — also https://www.youtube.com/@DragLens. The name "660 Drag Lens" matched two real channels, so both DRAG LENS and Lens 660 are included.
- Lens 660 (YouTube, channel ID `UC_5FQcJ-B9sbm7NCc86KTYA`) — https://www.youtube.com/feeds/videos.xml?channel_id=UC_5FQcJ-B9sbm7NCc86KTYA — also https://www.youtube.com/@Lens660
- Grudge Races — https://grudgeraces.com/feed
- No Prep Racing — https://www.noprep.com/feed
- BoostedGT (YouTube, channel ID `UCBuSoDJ-ICag5E2Pjlck8zA`) — https://www.youtube.com/feeds/videos.xml?channel_id=UCBuSoDJ-ICag5E2Pjlck8zA — Ryan Martin's channel; the official RSS returned items

**Drag Racing / NHRA — "On the Tree"**

Second on the homepage, after the Grudge Board.

- Drag Illustrated — https://dragillustrated.com/feed
- Competition Plus — https://competitionplus.com/feed
- Dragzine — https://www.dragzine.com/feed
- BangShift — https://bangshift.com/feed
- EngineLabs — https://www.enginelabs.com/feed (also tagged Engines / Tech)
- Chevy Hardcore — https://www.chevyhardcore.com/feed (also tagged Engines / Tech)

**Dirt Track — "On the Cushion"**

- World of Outlaws — https://worldofoutlaws.com/feed
- DIRTcar Racing — https://dirtcar.com/category/news/feed
- Super DIRTcar Series — https://superdirtcarseries.com/feed (big-block modifieds)
- Racing News Dirt — https://racingnews.co/category/dirt/feed
- SPEED SPORT Dirt Late Models — https://speedsport.com/news/short-track/dirt-late-models/feed
- SPEED SPORT Short Track — https://speedsport.com/news/short-track/feed
- IMCA — https://www.imca.com/feed
- American Sprint Car Series — https://ascsracing.com/feed (sprint / 360)
- STL Racing — https://stlracing.com/feed
- Eldora Speedway — https://www.eldoraspeedway.com/feed
- eKartingNews — https://www.ekartingnews.com/feed (karts)

**NASCAR and IMSA**

Working feeds: Frontstretch, Motorsport.com NASCAR, Crash.net NASCAR, Motorsport.com IMSA, and Sportscar365. Formula 1 and IndyCar categories and their feeds were removed from the site.

Headline cards use the title, date, source name, and a short excerpt taken from the feed’s summary/description only. Video cards add a thumbnail and the channel name. Full articles and full videos stay at the source. Every aggregated card links out.

To add or remove a feed later, edit `feeds.yaml` and rebuild.

## Feeds that failed (dropped)

These were tried and did **not** return usable feed items:

- NHRA official news RSS (for example `https://www.nhra.com/nhra/news/rss` and nearby `/feed` and `/rss` URLs) — HTML pages, not a feed
- NASCAR.com official RSS (`https://www.nascar.com/rss/` and `/feed`) — bot challenge (HTTP 403)
- Jayski (`https://www.jayski.com/feed`) — same 403 challenge
- IndyCar official `https://www.indycar.com/news/rss/` — an HTML news archive, not a feed
- IMSA.com `/feed` and `/news/feed` — 404
- `https://www.nhraracer.com/feed` — 404
- `https://blog.nhraracer.com/feed` — TLS error
- `https://www.hotrod.com/feed` and `/rss` — HTML or 404
- `https://www.superchevy.com/feed` — redirected to a MotorTrend HTML homepage
- `https://www.competitionplus.com/feed` (with www) — HTTP 500; the non-www URL above works and is the one in use
- Dirt On Dirt, Sprint Car News, and several other dirt-track `/feed` guesses — 404, TLS errors, or empty

Additional misses from this pass:

- Midwest Street Cars YouTube (`@MidwestStreetCarsAuto`, channel ID `UCDcO1v4kh3l6B4sQiaXJAYw`) — official channel confirmed; public RSS 404'd after retries
- Street Car Takeover YouTube (`@StreetCarTakeoverOfficial`, channel ID `UCkIoIhpY90KwYX-lDxD16Jg`) — official channel confirmed; RSS 404/500 after retries
- Farmtruck and AZN YouTube (`@farmtruckandazn`, channel ID `UCH6D3V-FAfyoC5_6gXUs9lQ`) — official channel confirmed; RSS 404 after retries
- World of Outlaws, DIRTcar Racing, USAC, and IMCA YouTube channel IDs were confirmed, but their official RSS feeds 404/500'd in this environment after retries (the same YouTube RSS endpoint worked for 1320video, DRAG LENS, Lens 660, and BoostedGT)
- Lucas Oil Late Model Dirt Series website `/feed` — 404/500; a candidate YouTube ID also 404'd
- USAC Racing website `/feed` — 404
- Kickin' the Cushion — no working site or YouTube RSS found (host TLS errors; handles did not resolve)
- DirtonDirt — still no public RSS (site and `/feed` / blog RSS guesses failed)
- Dirt Track Digest, Racing America, FloRacing `/feed` — bot wall, HTML, or 406
- Official Street Outlaws / No Prep Kings YouTube under the obvious handles resolved to unrelated channels or 404s (do not use `@noprepkings` — that one is RC cars)
- Official Discovery/MotorTrend Street Outlaws channel was not confirmed as a dedicated public RSS

If an official series feed or YouTube RSS comes back later, add it in `feeds.yaml`.

## Social-only pages (not included)

Instagram, Facebook, and TikTok do not offer public feeds, and they were not scraped. These matter to the outlaw racing and dirt scenes but cannot be pulled in automatically. Official links we have confirmed are listed on the Follow page instead of being scraped:

- 1320Video on Instagram and Facebook (the YouTube channel and the 1320video.com blog *are* included)
- Street Outlaws / No Prep Kings official Instagram, Facebook, and TikTok
- Midwest Street Cars and Street Car Takeover social pages (their sites had no working `/feed`; YouTube RSS did not return items here)
- Farmtruck and AZN on Instagram/Facebook
- DRAG LENS / Lens 660 Instagram or Facebook pages, if any
- DirtonDirt and Kickin' the Cushion social pages
- Most grudge and no-prep organizers who post only to Instagram or Facebook

**X accounts (noted only — no X integration was built):** looked up with the X read tools. Candidates that look real: [@1320Video](https://x.com/1320Video), [@StreetOutlaws](https://x.com/StreetOutlaws) (verified), [@WorldofOutlaws](https://x.com/WorldofOutlaws), [@SPEEDSPORT](https://x.com/SPEEDSPORT), [@DirtonDirt](https://x.com/DirtonDirt), [@lucasdirt](https://x.com/lucasdirt), [@FloRacing](https://x.com/FloRacing). Handles that did not match the racing org, or were not found: `BoostedGT` (unrelated tiny account), `FarmtruckAZN`, `NoPrepKings`, `DragLens`, `Lens660`, `GrudgeRaces`, plus `DIRTcar` / `USACRacing` which do not look like the official series accounts.


## Live site (GitHub Pages)

The site is public at **https://0626-coder.github.io/speed-demon-news/**. The repository is [0626-coder/speed-demon-news](https://github.com/0626-coder/speed-demon-news).

`site.yaml` holds the public address:

- `base_url: https://0626-coder.github.io/speed-demon-news`
- `base_path: /speed-demon-news`

Local builds ignore those values (see “How to build” above). Production builds use them so CSS, JS, images, nav, RSS, sitemap, and canonical/OG URLs all work under the `/speed-demon-news/` subpath.

A GitHub Actions workflow named **Build and deploy** (`.github/workflows/pages.yml`) installs Python, runs `python build.py --prod`, and publishes the `public/` folder to GitHub Pages. It runs:

- on every push to `main`
- when started by hand (`workflow_dispatch`)
- on a schedule three times a day: `0 13,18,23 * * *` UTC, which is 7am / 12pm / 5pm America/Chicago during CST, and 8am / 1pm / 6pm during CDT

Willseys Wonderland is public at `/willseys-wonderland/`. The Follow page is public at `/follow/`. The Live page is public at `/live/`. The merch page stays hidden until `merch.enabled` is true in `site.yaml`. Draft posts in `content/posts` (`draft: true`) stay in the repo source but are not rendered on the site.

No custom domain is attached. A domain can be added later at a registrar if you want one; nothing has been purchased.

Do not commit secrets. There are none in this project. `.venv/`, `__pycache__/`, `.feed-cache/`, `public/`, screenshots, and `*.log` are gitignored. GitHub Actions keeps its own feed-cache between runs.

## Site name and domains

The site is named **Speed-Demon News**. `site_name` in `site.yaml` is set, and `site_name_is_placeholder` is `false`. The About page no longer carries a placeholder notice.

A domain check was run on 15 Nov 2026 (America/Chicago). DNS on this machine is not trustworthy (names resolve to a sinkhole address, `198.18.0.1`), so registry RDAP was the signal. WHOIS port 43 has been blocked here in the past. **This is not a guarantee a name is free to register.** Recheck at a registrar before buying anything. Nothing was purchased.

| Name | Lookup | Result |
| --- | --- | --- |
| speeddemonnews.com | Verisign RDAP (`rdap.verisign.com`) | HTTP 404, empty RDAP body — no registration record (appears unregistered). A known registered control, google.com, returned HTTP 200. |
| speed-demonnews.com | Verisign RDAP | HTTP 404, empty RDAP body — no registration record (appears unregistered). |
| speeddemon.news | Identity Digital RDAP (the IANA-listed server for `.news`) | HTTP 404, `errorCode` 404, title "Object not found" — no registration record (appears unregistered). A known registered control, google.news, returned HTTP 200. |

Older working-title options from the first draft (Grid & Tree, The Track Brief, and the rest) were only placeholders and are no longer in use.
