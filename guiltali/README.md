# Guiltali — Brock Trip 2026

The first working **Guiltali** prototype: a private group-trip coordination app,
deployed for the real **Brock Trip 2026** (July 16–21, 12 people).
Splitwise-meets-Uber-Eats energy: mobile-first, bottom tab bar, Airbnb-inspired
theme with nature/hiking notes.

**This is a real multi-page Django app, not a static demo** — people log in,
enter expenses, claim rooms, check off grocery sections, vote in polls, and
post to the board.

## What's inside

| Tab | Features |
|-----|----------|
| **Trip** (home) | Hero card with trip progress bar, the 12-person party roster with roles (Admin / Moderator / Party Member), quick links, dietary notes |
| **Trip → Timeline** | Google-Calendar-style day-by-day scrubber; arrivals/departures (Kayla Fri→Mon) |
| **Trip → Stay** | Airbnb quick-access card (listing link, dates, Wi-Fi, lock code, checkout), room claiming with organizer-priced comfort tiers |
| **Money** | Splitwise-parity: add expenses (with receipts), split algorithms (equal / by-nights-present / room-comfort), plain-language algorithm descriptions, two-sided "I paid → confirm received" settlement, admin/mod-only full tabs |
| **Tasks** | Grocery list split into 3 assigned sections (from the trip meal plan, Eden-allergy-safe), generic task lists, animated check-offs |
| **Polls** | Create polls in-app (anonymous or named, single/multi choice), each poll gets its own page, animated live result bars |
| **Board** | Text blasts, suggestions, photo uploads, comments (post-style, not chat), pinned admin announcements incl. per-person targeting |

## Domain model (generalized on purpose)

`Party → Trip → Membership / Attendance / Expense / Room / TaskList / Poll / Post`

Nothing is Brock-specific except the seed data — roommate chores or a
Devil's-Path-style hike fit the same shapes. This is the Guiltali kernel
prototype: one party, one trip today; many guilds, many events later.

## Run locally

```bash
cd guiltali
python -m venv .venv
.venv\Scripts\activate          # Windows (source .venv/bin/activate elsewhere)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_brock_trip   # prints everyone's passwords once
python manage.py runserver 0.0.0.0:8000
```

Then open `http://<your-lan-ip>:8000` on your phone (same Wi-Fi) to test mobile.

## Deploy to Render (free)

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, point at the repo — `render.yaml` does the rest
   (build installs deps, collects static, migrates, seeds).
3. Copy the seeded passwords from the first deploy log and text them to the party.

> Free-tier note: the instance sleeps after idle and the SQLite disk is
> ephemeral (data resets on deploy). For trip-week durability, attach Render's
> free Postgres and set `DATABASE_URL` (stub already in `render.yaml`).

## Accounts

Seeded by `seed_brock_trip`: `malachi` (admin, also Django superuser),
`sabah` + `clarence` (moderators), and the rest of the party as members.
Passwords are generated randomly and printed once at seed time; change any of
them in `/admin/`.
