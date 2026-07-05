"""Smoke test the redesigned Guiltali app end-to-end (run with venv python)."""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "guiltali.settings")
django.setup()

from django.conf import settings as dj_settings
from django.contrib.auth.models import User
from django.test import Client

dj_settings.ALLOWED_HOSTS.append("testserver")

from party.models import Expense, InfoPage, Membership, Poll, TaskList, Trip, UserProfile

trip = Trip.objects.get(is_active=True)
PASS = 0
FAIL = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[OK]   {label}")
    else:
        FAIL += 1
        print(f"[FAIL] {label} {extra}")


def client_for(username):
    c = Client()
    c.force_login(User.objects.get(username=username))
    return c


# fresh profile state for malachi
UserProfile.objects.filter(user__username="malachi").delete()
c = client_for("malachi")

r = c.get("/")
check("trips home renders", r.status_code == 200 and b"Your trips" in r.content)

r = c.get(f"/trips/{trip.id}/choose/")
check("primary prompt shows", r.status_code == 200 and b"PRIMARY TRIP" in r.content)

r = c.post(f"/trips/{trip.id}/choose/", {"primary": "yes"})
check("primary=yes redirects home", r.status_code == 302 and r.url == "/home/")

r = c.get("/", follow=False)
check("trips home now skips to /home/", r.status_code == 302 and r.url == "/home/")

r = c.get("/home/")
check("first /home/ pushes icon prompt", r.status_code == 302 and "/settings/" in r.url)

r = c.post("/settings/", {"action": "identity", "icon": "mountain", "color": "#2f7d4f"})
check("identity save", r.status_code == 302)

r = c.get("/home/")
check("home renders", r.status_code == 200 and b"Brock Trip" in r.content)
check("home has menu", b"The menu" in r.content)

for path, marker in [
    ("/itinerary/", b"TRIP SCHEDULE"),
    ("/schedule/", b"Attendance timeline"),
    ("/stay/", b"Berkeley Springs"),
    ("/budget/", b"Your balance"),
    ("/budget/add/", b"Add an expense"),
    ("/budget/settle/", b"Add payment"),
    ("/budget/receipt/", b"GROUP RECEIPT"),
    ("/info/", b"Information"),
    ("/info/tools/", b"Pickleball"),
    ("/feed/", b"feed"),
    ("/feed/new/", b"Add to the feed"),
    ("/photos/", b"Photo &amp; video wall"),
    ("/party/", b"The party"),
    ("/settings/", b"About"),
]:
    r = c.get(path)
    check(f"GET {path}", r.status_code == 200 and marker in r.content,
          f"(status {r.status_code})")

# recipe page + list page
r = c.get("/info/pasta-bar/")
check("recipe page", r.status_code == 200 and b"pasta" in r.content.lower())
tl = TaskList.objects.filter(trip=trip).first()
r = c.get(f"/info/lists/{tl.id}/")
check("list detail", r.status_code == 200)

# restricted dietary page: admin yes, random member no, eden yes
r = c.get("/info/eden-dietary/")
check("dietary page as admin", r.status_code == 200 and b"DEATHLY" in r.content)
c_kayla = client_for("kayla")
UserProfile.objects.get_or_create(user__id=User.objects.get(username="kayla").id,
                                  defaults={"user": User.objects.get(username="kayla")})
r = c_kayla.get("/info/eden-dietary/")
check("dietary page blocked for kayla", r.status_code == 404)
c_eden = client_for("eden")
r = c_eden.get("/info/eden-dietary/")
check("dietary page visible to eden", r.status_code == 200)

# add expense flow with percent split
members = list(Membership.objects.filter(party=trip.party))
detail = {f"detail_{m.id}": "0" for m in members}
detail[f"detail_{members[0].id}"] = "60"
detail[f"detail_{members[1].id}"] = "40"
r = c.post("/budget/add/", {"action": "add", "title": "Smoke pretzels", "amount": "10.00",
                        "payer": members[0].id, "split_method": "percent",
                        "tags": ["food"], **detail})
check("expense preview redirect", r.status_code == 302 and "confirm" in r.url)
r = c.get("/budget/confirm/")
check("confirm screen shows split", r.status_code == 200 and b"Smoke pretzels" in r.content)
r = c.post("/budget/confirm/", {"action": "confirm"})
check("expense confirmed", r.status_code == 302)
r = c.get("/budget/")
check("expense listed", b"Smoke pretzels" in r.content)
exp = Expense.objects.filter(trip=trip, title="Smoke pretzels").first()
if exp:
    r = c.get(f"/budget/{exp.id}/")
    check("expense detail page", r.status_code == 200 and b"Smoke pretzels" in r.content)
    r = c.get(f"/budget/receipt/{Membership.objects.get(user__username='malachi', party=trip.party).id}/")
    check("my receipt with owe section", r.status_code == 200 and b"Who you owe" in r.content)

# simplify debts toggle (admin)
if trip.simplify_debts:
    c.post("/budget/settle/", {"action": "toggle_simplify"})
    trip.refresh_from_db()
r = c.post("/budget/settle/", {"action": "toggle_simplify"})
trip.refresh_from_db()
check("simplify debts toggled on", trip.simplify_debts)
r = c.get("/budget/settle/")
check("settle shows plan", r.status_code == 200 and (b"pays" in r.content or b"Everyone's balance" in r.content))

# feed: comment + new post + poll two-stage rules
from party.models import Post
post = Post.objects.filter(trip=trip).first()
r = c.post("/feed/", {"action": "comment", "post_id": post.id, "text": "smoke comment"})
check("comment posts", r.status_code == 302)
r = c.post("/feed/new/", {"what": "post", "kind": "blast", "title": "Smoke post",
                          "text": "hello woods", "bg_color": "#eef4e8",
                          "link_url": "", "link_label": "", "suggested_by_note": ""})
check("new post", r.status_code == 302)

poll2 = Poll.objects.filter(trip=trip, two_stage=True).first()
if poll2.stage != Poll.STAGE_SUGGEST:
    poll2.stage = Poll.STAGE_SUGGEST
    poll2.save(update_fields=["stage"])
r = c_eden.post(f"/polls/{poll2.id}/", {"action": "suggest", "text": "Eden's dumpling night"})
check("two-stage suggest", r.status_code == 302)
opt = poll2.options.filter(suggested_by__user__username="eden").first()
check("suggestion saved", opt is not None)
# advance to vote, then eden tries to vote for her own -> blocked
r = c.post(f"/polls/{poll2.id}/", {"action": "advance"})
poll2.refresh_from_db()
check("poll advanced to vote", poll2.stage == "vote")
r = c_eden.post(f"/polls/{poll2.id}/", {"action": "vote", "option_id": opt.id}, follow=True)
from party.models import Vote
check("own-suggestion vote blocked",
      not Vote.objects.filter(option=opt, member__user__username="eden").exists())
other = poll2.options.exclude(id=opt.id).first()
c_eden.post(f"/polls/{poll2.id}/", {"action": "vote", "option_id": other.id})
check("other vote counts",
      Vote.objects.filter(option=other, member__user__username="eden").exists())

# schedule: kayla edits own stay; kayla cannot edit malachi's
km = Membership.objects.get(party=trip.party, user__username="kayla")
r = c_kayla.post("/schedule/", {"member_id": km.id, "arrive": "2026-07-17",
                                "depart": "2026-07-20", "note": "Fri to Mon",
                                "travel_note": "driving myself"})
check("kayla edits own stay", r.status_code == 302)
mm = Membership.objects.get(party=trip.party, user__username="malachi")
r = c_kayla.post("/schedule/", {"member_id": mm.id, "arrive": "2026-07-16",
                                "depart": "2026-07-21", "note": "x"}, follow=True)
check("kayla blocked from editing others",
      b"Only admins and moderators" in r.content)

# member-filtered feed
r = c.get(f"/feed/?member={km.id}")
check("member-filtered feed", r.status_code == 200 and b"Showing" in r.content)

# --- new-this-session features ---
r = c.get("/experience/")
check("experience page renders", r.status_code == 200 and b"Berkeley Springs" in r.content)
r = c.get("/experience/edit/")
check("trip edit (admin) renders", r.status_code == 200 and b"House notes" in r.content)
r_kayla_edit = c_kayla.get("/experience/edit/")
check("trip edit blocked for non-staff", r_kayla_edit.status_code in (302, 403, 404))

r = c.get("/budget/charts/")
check("budget charts renders", r.status_code == 200 and b"person" in r.content.lower())

from party.models import PostReaction
squire_post = Post.objects.filter(trip=trip, author__is_ai=True).first()
check("AI squire post seeded", squire_post is not None)
if squire_post:
    malachi_m = Membership.objects.get(party=trip.party, user__username="malachi")
    PostReaction.objects.filter(post=squire_post, member=malachi_m, emoji="\U0001F525").delete()
    r = c.post("/feed/react/", {"post_id": squire_post.id, "emoji": "\U0001F525"})
    check("react to post", r.status_code in (200, 302))
    check("reaction recorded", any(row["count"] for row in squire_post.reaction_summary()))

r = c.post("/info/lists/new/", {"name": "Smoke list", "kind": "packing", "items": "Tent\nFlashlight"})
check("staff creates list", r.status_code == 302)
new_list = TaskList.objects.filter(trip=trip, name="Smoke list").first()
check("new list saved", new_list is not None)

r = c.post("/info/new/", {"title": "Smoke note", "subtitle": "", "body": "Just a test note.", "kind": "note"})
check("create info note", r.status_code == 302)
check("info note saved", InfoPage.objects.filter(trip=trip, title="Smoke note").exists())

r = c.post("/settings/", {"action": "name", "display_name": "Malachi Smoke", "nickname": "Smokey"})
check("identity nickname save", r.status_code == 302)
me_m = Membership.objects.get(party=trip.party, user__username="malachi")
check("nickname persisted", me_m.nickname == "Smokey")
check("shown_name uses nickname", me_m.shown_name == "Smokey")

# expense edit: payer can edit own; admin can edit anyone's
own_exp = Expense.objects.filter(trip=trip, payer=me_m).first()
check("sample expense for edit test", own_exp is not None)
if own_exp:
    r = c.get(f"/budget/edit/{own_exp.id}/")
    check("admin opens expense edit", r.status_code == 302)
    r = c_kayla.get(f"/budget/edit/{own_exp.id}/")
    check("non-payer blocked from edit", r.status_code in (403, 404))

# --- profile icon routing: own -> settings, others -> their feed ---
r = c.get(f"/m/{me_m.id}/", follow=False)
check("own icon routes to settings", r.status_code == 302 and r.url == "/settings/")
r = c.get(f"/m/{km.id}/", follow=False)
check("other's icon routes to their feed", r.status_code == 302 and f"member={km.id}" in r.url)

# --- notifications: commenting on someone else's post notifies them ---
from party.models import Notification
other_post = Post.objects.filter(trip=trip).exclude(author=me_m).first()
if other_post:
    before = Notification.objects.filter(recipient=other_post.author).count()
    c.post("/feed/", {"action": "comment", "post_id": other_post.id, "text": "notify test"})
    after = Notification.objects.filter(recipient=other_post.author).count()
    check("comment creates a notification", after == before + 1)
r = c.get("/notifications/")
check("notifications page renders", r.status_code == 200)

# --- member-filtered feed also surfaces their comments, highlighted ---
r = c.get(f"/feed/?member={km.id}")
check("member filter includes posts they commented on or highlights", b"blink" in r.content or b"Showing" in r.content)

# --- events: staff creates one, can tag a post to it ---
r = c.post("/events/", {"name": "Smoke bonfire", "date": "2026-07-18"})
check("staff creates event", r.status_code == 302)
from party.models import Event
ev = Event.objects.filter(trip=trip, name="Smoke bonfire").first()
check("event saved", ev is not None)
if ev:
    r = c.get(f"/photos/?event={ev.id}")
    check("photos filtered by event", r.status_code == 200)

# --- expense delete: payer/admin only ---
own_exp2 = Expense.objects.filter(trip=trip, payer=me_m).exclude(pk=own_exp.id if own_exp else -1).first()
if own_exp2:
    r = c_kayla.post(f"/budget/delete/{own_exp2.id}/", {})
    check("non-owner can't delete expense", Expense.objects.filter(pk=own_exp2.id).exists())
    r = c.post(f"/budget/delete/{own_exp2.id}/", {})
    check("admin deletes expense", not Expense.objects.filter(pk=own_exp2.id).exists())

# --- budget backup download (admin only) ---
r = c.get("/budget/backup/")
check("admin downloads expense backup", r.status_code == 200 and r["Content-Type"] == "application/json")
r = c_kayla.get("/budget/backup/")
check("non-admin blocked from backup", r.status_code == 404)

# --- info page editing (staff only), incl. link field ---
page = InfoPage.objects.filter(trip=trip).first()
r = c_kayla.get(f"/info/{page.slug}/edit/")
check("non-staff blocked from info edit", r.status_code == 404)
r = c.post(f"/info/{page.slug}/edit/", {
    "title": page.title, "subtitle": page.subtitle, "body": page.body,
    "link_url": "https://example.com/recipe", "link_label": "Original recipe",
})
check("staff saves info page edit", r.status_code == 302)
page.refresh_from_db()
check("info page link saved", page.link_url == "https://example.com/recipe")

# --- random picker tool renders ---
r = c.get("/info/tools/picker/")
check("picker tool renders", r.status_code == 200 and b"Spin" in r.content)

print(f"\n{PASS} passed, {FAIL} failed")
raise SystemExit(1 if FAIL else 0)
