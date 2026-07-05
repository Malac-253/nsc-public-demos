# NSC Public Demos

A collection of standalone demos from Project "Night School Club". Each demo lives in its own folder and can be opened directly in a browser — no build step required.

## Quick start

Open [`index.html`](index.html) in your browser to browse available demos, or open any demo file directly.

```bash
# From the repo root — opens the demo index (macOS)
open index.html

# Or serve locally if you prefer HTTP
npx serve .
```

Then visit `http://localhost:3000` (or whatever port `serve` prints).

## Demos

| Demo | Description | Path |
|------|-------------|------|
| **Crawl Trails** | A transit-style route view for a night-out crawl — venues, lines, transfers, and live “cars” along the way. | [`crawltrails/malachi_dance_crawl.html`](crawltrails/malachi_dance_crawl.html) |
| **Guiltali — Brock Trip 2026** | A deployable multi-page group-trip app (Django): logins, expenses + split algorithms, rooms, grocery tasks, polls, board. See its README for local run + Render deploy. | [`guiltali/`](guiltali/README.md) |

## Adding a demo

1. Create a folder for the demo (e.g. `my-demo/`).
2. Add your standalone HTML (or other static assets).
3. Link it from [`index.html`](index.html) and add a row to the table above.

Demos should be self-contained and viewable without a bundler or backend.
