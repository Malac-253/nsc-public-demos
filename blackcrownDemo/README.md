# Black Crown — static demo

Frozen HTML snapshot of the Black Crown LiveFlyer site for GitHub Pages.

## Local preview

Open `index.html` in a browser, or from this folder:

```bash
npx --yes serve .
```

## GitHub Pages

Point Pages at this folder (or the `blackcrownDemo` path in `nsc-public-demos`).
Links and images use relative paths, so it works under a project subpath. `.nojekyll` is included so GitHub won’t run Jekyll on the HTML.

## Refresh from the live server

With `runserver` on `:8077` and lot images in `nsc/amote-core/media`:

```bash
python export_from_live.py
```

## Structure

- `index.html` — home
- `lots/`, `about/`, `buy/`, … — site pages
- `lot/<public_ref>/` — one HTML page per lot
- `media/` — images and other assets
