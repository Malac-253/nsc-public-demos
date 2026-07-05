"""Seed the Brock Trip 2026 demo data (idempotent).

Creates the party, the 12 members with login accounts, attendance,
rooms (temp data), grocery task lists split three ways (houseing.txt),
a packing list, a welcome announcement, and a sample poll.

Passwords are printed at the end so the admin can text them out.
Override any password later in Django admin.
"""
from __future__ import annotations

import datetime as dt
import secrets
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from party.models import (
    Announcement,
    Attendance,
    Expense,
    ExpenseShare,
    InfoPage,
    ItineraryActivity,
    Membership,
    Party,
    Poll,
    PollOption,
    Post,
    Room,
    RoomClaim,
    TaskItem,
    TaskList,
    Trip,
    TripPhoto,
    UserProfile,
    Vote,
)
from party.splits import preview_split

# (username, display, role, plus_one_of_username, icon, color)
PEOPLE = [
    ("malachi", "Malachi", Membership.ROLE_ADMIN, None, "mountain", "#2f7d4f"),
    ("abby", "Abby", Membership.ROLE_MEMBER, "malachi", "flower", "#7a5fa0"),
    ("sabah", "Sabah", Membership.ROLE_MODERATOR, None, "sun", "#c9a441"),
    ("copper", "Cooper Slack", Membership.ROLE_MEMBER, "sabah", "compass", "#c47a3d"),
    ("christy", "Christy", Membership.ROLE_MEMBER, "sabah", "pine", "#5d7f35"),
    ("ethan", "Ethan Tarpley", Membership.ROLE_MEMBER, None, "fire", "#b0533b"),
    ("eden", "Eden", Membership.ROLE_MEMBER, None, "leaf", "#2f7d4f"),
    ("grant", "Grant", Membership.ROLE_MEMBER, None, "stone", "#96694b"),
    ("trinity", "Trinity", Membership.ROLE_MEMBER, "grant", "star", "#c9a441"),
    ("evan", "Evan Dotson", Membership.ROLE_MEMBER, None, "tent", "#6b4d2e"),
    ("clarence", "Clarence", Membership.ROLE_MODERATOR, None, "lantern", "#4d8f8b"),
    ("collin", "Collin Mathis", Membership.ROLE_MEMBER, None, "acorn", "#6b4d2e"),
    ("kayla", "Kayla Sharkey", Membership.ROLE_MEMBER, None, "water", "#3f7fbf"),
    # Not a real person — posts AI-suggested activities/spas to the feed.
    ("squire", "Party AI Squire", Membership.ROLE_MEMBER, None, "lantern", "#7a2e35"),
]

# Seeded nicknames — shown big everywhere instead of the real name (real name
# shows tiny underneath). Only applied on first creation; members can change
# their own nickname later from Settings, which sticks after that.
NICKNAMES = {"malachi": "The Quartermaster"}

TRAVEL_NOTES = {
    "kayla": ("May only make it for the weekend for financial reasons — will confirm.", Membership.VIS_EVERYONE),
    "grant": ("Driving down Thursday with Trinity; can take 2 more + gear.", Membership.VIS_EVERYONE),
    "clarence": ("Coming straight from work Thursday — may be late, don't wait on dinner.", Membership.VIS_MODS),
    "ethan": ("Flying in, landing ~11am on the 16th — renting a car, grabbing food/a mini-fridge before the house. Leaving early afternoon on the 20th (misses the last night).", Membership.VIS_EVERYONE),
    "eden": ("Traveling with Ethan — same arrival/departure. Needs her own sink/shower kept free of her allergens (see dietary notes).", Membership.VIS_MODS),
    "evan": ("Working full-time up until the trip — has to leave Tuesday morning, the earliest of anyone.", Membership.VIS_EVERYONE),
    "collin": ("Flying into DC — Sabah's picking him up from the airport.", Membership.VIS_EVERYONE),
}

EDEN_DIET = (
    "DEATHLY allergic: fish, sesame (hummus/tahini!), sunflower seeds "
    "(sunflower oil OK), peanuts, and all tree nuts EXCEPT almonds and "
    "pecans. Swaps: almond butter not peanut butter, plain bagels not "
    "everything bagels, ranch not hummus."
)

GROCERY_SECTIONS = {
    "Grocery — Section A (Produce & Fruit)": [
        ("Yellow onions", "18–20"),
        ("Bell peppers", "18"),
        ("Zucchini", "10"),
        ("Mushrooms", "4 lb"),
        ("Carrots", "5 lb"),
        ("Potatoes", "10 lb"),
        ("Spinach (tubs/bags)", "6"),
        ("Lettuce (bags)", "3"),
        ("Avocados", "10–12"),
        ("Limes", "28–32"),
        ("Cilantro (bunches)", "4"),
        ("Garlic (bulbs)", "3"),
        ("Ginger root (large)", "1"),
        ("Watermelons", "2"),
        ("Grapes", "4–5 lb"),
        ("Strawberries / mixed berries", "3–4 lb"),
        ("Bananas", "3 dozen"),
        ("Clementines / oranges", "3 dozen"),
        ("Apples", "2 dozen"),
    ],
    "Grocery — Section B (Proteins, Dairy & Eggs)": [
        ("Italian sausage or ground turkey (pasta)", "3 lb"),
        ("Chicken thighs (curry)", "4 lb"),
        ("Ground beef or turkey (taco bowls)", "4 lb"),
        ("Ham", "3–4 lb"),
        ("Deli turkey / cold cuts", "3–4 lb"),
        ("Tofurky / vegetarian turkey slices", "3 packs"),
        ("Extra-firm tofu (optional)", "4 blocks"),
        ("Chickpeas (cans)", "8"),
        ("Black beans (cans)", "10"),
        ("Eggs", "10–12 dozen"),
        ("Heavy cream / half-and-half", "2 qt"),
        ("Parmesan", "2 lb"),
        ("Shredded Mexican cheese", "3 lb"),
        ("Greek yogurt / sour cream (tubs)", "4"),
        ("Cream cheese", "3–4 packs"),
        ("Butter", "1"),
    ],
    "Grocery — Section C (Dry Goods, Snacks & Drinks)": [
        ("Penne or rigatoni", "6 lb"),
        ("Jasmine/basmati rice", "8–10 lb"),
        ("Plain flour tortillas", "30–36"),
        ("Garlic bread / dinner rolls", "3"),
        ("PLAIN bagels only (no everything/sesame!)", "3 dozen"),
        ("Plain bread", "2–3 loaves"),
        ("English muffins", "2 packs"),
        ("Oatmeal (large)", "2"),
        ("Tortilla chips (large bags)", "4"),
        ("Pretzels (large bags)", "4"),
        ("Plain crackers (boxes)", "3–4"),
        ("Marinara (jars)", "4"),
        ("Coconut milk (cans)", "8"),
        ("Diced tomatoes (cans)", "4"),
        ("Salsa (large tubs)", "3"),
        ("Jam", "2 jars"),
        ("Almond butter (Eden-approved)", "2 jars"),
        ("Ranch dressing (label-checked)", "1–2"),
        ("Hot sauce (label-checked)", "2"),
        ("Almond/pecan trail mix (allergy-checked)", "3–4 bags"),
        ("Almonds", "2 lb"),
        ("Pecans", "2 lb"),
        ("Dried cranberries / raisins", "2 lb"),
        ("Banana chips", "2–3 bags"),
        ("Fruit leather", "2 boxes"),
        ("Granola/protein bars (allergy-checked)", "24–36"),
        ("Jerky (label-checked: no sesame/fish)", "3–4 bags"),
        ("Electrolyte packets", "24–36"),
        ("Bottled water (cases)", "6–8"),
        ("Ginger ale / seltzer", "plenty"),
        ("Orange juice", "2"),
        ("Coffee + tea + creamer", "1 each"),
        ("Ice", "at arrival"),
    ],
}

PACKING = [
    "Hiking shoes/boots", "Rain jacket (forecast is never accurate)",
    "Refillable water bottle", "Day pack", "Sunscreen", "Bug spray",
    "Swimsuit", "Towel", "Warm layer for nights", "Phone charger",
    "Headlamp/flashlight", "Personal meds", "Cash for splits",
    "Games / cards", "Speaker", "Cooler (if you have one)",
]

# (day_offset, time_str_or_None, kind, title, description, distance_note)
ACTIVITIES = [
    (0, "15:00", ItineraryActivity.KIND_TRAVEL, "Arrivals & settle in",
     "Grab keys, claim rooms, unload the cars.", ""),
    (0, "19:00", ItineraryActivity.KIND_MEAL, "Welcome dinner — pasta bar",
     "First night group meal from the grocery run.", ""),
    (1, "08:30", ItineraryActivity.KIND_HIKE, "Morning hike — Overlook Ridge Trail",
     "Moderate loop with valley views. Pack water.", "4.2 mi · 900 ft gain"),
    (1, "14:00", ItineraryActivity.KIND_WATER, "Lake swim & float",
     "Bring towels + sunscreen.", ""),
    (1, "20:30", ItineraryActivity.KIND_SOCIAL, "Campfire & s'mores",
     "String lights go up at dusk.", ""),
    (2, "07:00", ItineraryActivity.KIND_HIKE, "Summit day — Devil's Overlook",
     "The big one this trip — about 6 hrs round trip.", "8.1 mi · 2,100 ft gain"),
    (2, "18:30", ItineraryActivity.KIND_MEAL, "BBQ cookout dinner",
     "Burgers, dogs & Eden-safe sides.", ""),
    (2, "20:30", ItineraryActivity.KIND_SOCIAL, "Games night",
     "Cards, cornhole, whatever's left in the tank.", ""),
    (3, None, ItineraryActivity.KIND_FREE, "Rest day / kayaking",
     "No group plan — trails, lake, or hammock, your call.", ""),
    (3, "11:00", ItineraryActivity.KIND_CHORE, "Grocery restock run",
     "Whoever's driving into town grabs the list.", ""),
    (3, "19:00", ItineraryActivity.KIND_MEAL, "Taco & burrito bowl night",
     "Section C dry goods put to use.", ""),
    (4, "09:00", ItineraryActivity.KIND_HIKE, "Waterfall trail",
     "Easier out-and-back — good last big hike.", "3.5 mi · 400 ft gain"),
    (4, "18:00", ItineraryActivity.KIND_MEAL, "Farewell dinner — curry night",
     "Coconut chickpea curry, using up the fresh veg.", ""),
    (5, "09:00", ItineraryActivity.KIND_CHORE, "Pack up & deep clean",
     "Strip beds, take out trash, sweep — full house effort.", ""),
    (5, "11:00", ItineraryActivity.KIND_TRAVEL, "Checkout & departures",
     "Everyone out by checkout time — see the Stay tab.", ""),
]

# Demo seed no longer creates fake expenses — add real ones in the app (Budget → +).
# To wipe existing demo expenses on Render: python manage.py clear_expenses
EXPENSES: list[tuple] = []

# Cooper's suggestions (from his texts) — posted on his behalf by Malachi
COOPER_SUGGESTIONS = [
    ("The Pawpaw Tunnel", "3,100-ft canal tunnel hike — bring headlamps.",
     "https://wvtourism.com/company/paw-paw-tunnel/"),
    ("Crystal Grottoes Caverns", "Only ~50 min from Berkeley Springs.",
     "https://www.crystalgrottoescaverns.com/"),
    ("Coral Caverns", "About 59 min out — the other cavern option.",
     "https://coralcaverns.com/"),
    ("Cacapon State Park — hike + lake beach", "Hiking plus a lake with a real beach. "
     "Cooper says the beach looks nice.", "https://wvstateparks.com/park/cacapon-resort-state-park/"),
    ("Green Ridge State Forest hiking", "Big trail network just over the Maryland line.",
     "https://dnr.maryland.gov/publiclands/pages/western/greenridge.aspx"),
    ("Canoe / kayak the Cacapon River", "Canoeing and kayaking on the river — no tubing spots though.",
     ""),
]

RECIPES = [
    ("pasta-bar", "Creamy tomato pasta bar", "Night 1 · feeds the full house", (
        "Big-batch creamy tomato pasta with a toppings bar so everyone builds their own bowl.\n"
        "- Boil 6 lb penne in two pots, salt the water hard\n"
        "- Brown 3 lb Italian sausage (or ground turkey) in the big skillet\n"
        "- Add 4 jars marinara + 2 cans diced tomatoes, simmer 10 min\n"
        "- Stir in 2 cups heavy cream off the heat\n"
        "- Toppings bar: parmesan, spinach, mushrooms, garlic bread\n"
        "- Eden-safe as written — check the garlic bread label for sesame"
    )),
    ("curry-night", "Coconut chickpea curry", "Night 5 · farewell dinner", (
        "Uses up the fresh veg before checkout. Mild base, hot sauce on the side.\n"
        "- Saute 4 onions, garlic, and the big ginger root in the stock pot\n"
        "- Bloom curry powder 1 min, then add 8 cans coconut milk\n"
        "- Add 8 cans chickpeas + chicken thighs (separate pot for veggie)\n"
        "- Simmer 25 min; finish with lime + cilantro\n"
        "- Serve over jasmine rice (rice cooker runs two rounds)\n"
        "- Eden-safe: no nuts, no sesame oil — plain coconut milk only"
    )),
    ("taco-bowls", "Taco & burrito bowls", "Night 4 · build-your-own", (
        "Everything goes in the middle of the table, everyone builds a bowl.\n"
        "- Brown 4 lb ground beef/turkey with taco seasoning\n"
        "- Warm black beans with cumin; cook 4 cups rice\n"
        "- Chop: lettuce, avocados (10-12), cilantro, limes\n"
        "- Set out: tortillas, chips, salsa, shredded cheese, yogurt/sour cream\n"
        "- Eden-safe: plain tortillas only, check the seasoning packet"
    )),
]

# Room assignments are already locked in (per the group chat) — nobody
# claims a spot in-app, and each person only ever sees their own roommates.
# room name -> (price_per_person, [usernames sharing it])
ROOM_CLAIMS = {
    "Bedroom 1": (None, ["malachi", "abby"]),
    "Bedroom 2": (None, ["sabah", "copper", "christy"]),
    "Ethan & Eden's room": (None, ["ethan", "eden"]),
    "Grant & Trinity's room": (None, ["grant", "trinity"]),
    "Bunk room": (None, ["evan", "clarence", "collin", "kayla"]),
}

AREA_GUIDE = (
    "Berkeley Springs, WV calls itself \"America's First Spa\" — the mineral "
    "springs have been drawing people in since George Washington's day. Good "
    "home base for a mix of soaking and hiking.\n"
    "- Berkeley Springs State Park bathhouse — historic Roman bath, warm mineral soaking tubs\n"
    "- Berkeley Springs Spa Town — a whole strip of independent day spas, all walkable downtown\n"
    "- Coolfont Resort spa — bigger resort-style spa if the state park is booked\n"
    "- Cacapon Resort State Park — hiking plus a lake beach (Cooper found this one)\n"
    "- Green Ridge State Forest — big trail network just over the Maryland line\n"
    "- The Pawpaw Tunnel — 3,100-ft canal tunnel hike, bring headlamps\n"
    "- Crystal Grottoes Caverns and Coral Caverns — both under an hour away if anyone wants a cave day\n"
    "- Canoeing/kayaking on the Cacapon River — no tubing spots, but the put-in is easy\n"
    "- Lot 12 Public House downtown — the go-to dinner-out spot if nobody wants to cook"
)

# (author_username, caption, image_filename)
BOARD_PHOTOS = [
    ("sabah", "Golden hour at the cabin — forecast keeps saying rain but look at this",
     "brock-cabin.jpg"),
    ("collin", "Made it to the top of Devil's Overlook. View was worth every one of "
               "those 2,100 ft", "brock-waterfall.jpg"),
    ("eden", "Night one, string lights up, everyone accounted for", "brock-campfire.jpg"),
]


class Command(BaseCommand):
    help = "Seed Brock Trip 2026 demo data (idempotent)."

    def handle(self, *args, **options):
        party, _ = Party.objects.get_or_create(
            slug="brock",
            defaults={"name": "The Brock Party",
                      "description": "Fourth annual Brock trip crew."},
        )
        trip, _ = Trip.objects.get_or_create(
            slug="brock-trip-2026",
            defaults=dict(
                party=party,
                name="Brock Trip 2026",
                tagline="Fourth annual · cabin, trails & good company",
                start_date=dt.date(2026, 7, 16),
                end_date=dt.date(2026, 7, 21),
                location_name="Berkeley Springs, West Virginia",
                is_active=True,
            ),
        )
        # Real listing details (idempotent refresh).
        trip.listing_url = "https://www.airbnb.com/rooms/1685072643157452913"
        trip.listing_title = "Home in Berkeley Springs"
        trip.listing_summary = (
            "Pickleball · Spa Suite · Theater · Outdoor Kitchen — entire home "
            "in the West Virginia woods with room for the whole party."
        )
        trip.address = "251 Rock Gap Road, Berkeley Springs, WV 25411"
        trip.host_name = "the Rock Gap hosts"
        trip.guests = 12
        trip.bedrooms = 5
        trip.beds = 12
        trip.baths = 3
        trip.check_in_note = "Check-in: keypad — reach out to the host for the code"
        trip.check_out_note = "Checkout July 21 — see listing for time"
        trip.total_cost = Decimal("2691.36")
        trip.wifi_info = "Network: TBD · Password: TBD"
        trip.lock_code = "TBD — posted before arrival"
        trip.checkout_note = "Checkout July 21 — time TBD (check listing)"
        trip.house_notes = (
            "Remote area: groceries picked up en route (3 assigned sections). "
            "Kitchen is Eden-safe: no fish, sesame, peanuts, sunflower seeds, "
            "or tree nuts except almonds & pecans."
        )
        trip.area_guide = AREA_GUIDE
        trip.save()

        # Stay gallery (main picture + gallery, Airbnb-style)
        for i, (path, caption, cover) in enumerate([
            ("img/brock-cabin.jpg", "Cabin in the pines — sleeps 13", True),
            ("img/stay-pickleball.jpg", "Private pickleball court", False),
            ("img/stay-spa.jpg", "Spa suite with forest views", False),
            ("img/stay-outdoor-kitchen.jpg", "Outdoor kitchen & patio", False),
            ("img/brock-waterfall.jpg", "Waterfall trail nearby", False),
            ("img/brock-campfire.jpg", "Fire pit for camp nights", False),
        ]):
            TripPhoto.objects.get_or_create(
                trip=trip, static_path=path,
                defaults={"caption": caption, "is_cover": cover, "order": i},
            )

        passwords: list[tuple[str, str]] = []
        members: dict[str, Membership] = {}
        for username, display, role, plus_of, icon, color in PEOPLE:
            user, created = User.objects.get_or_create(username=username)
            if created:
                pw = f"{username}-{secrets.token_hex(2)}"
                user.set_password(pw)
                user.first_name = display
                user.is_staff = username == "malachi"
                user.is_superuser = username == "malachi"
                user.save()
                passwords.append((username, pw))
            m, _ = Membership.objects.get_or_create(
                party=party, user=user,
                defaults={"role": role, "display_name": display},
            )
            m.display_name = display
            if not m.icon:
                m.icon = icon
            if not m.color:
                m.color = color
            if not m.nickname and username in NICKNAMES:
                m.nickname = NICKNAMES[username]
            m.is_ai = username == "squire"
            if username in TRAVEL_NOTES and not m.travel_note:
                m.travel_note, m.travel_note_visibility = TRAVEL_NOTES[username]
            m.save()
            members[username] = m
        for username, display, role, plus_of, icon, color in PEOPLE:
            if plus_of:
                m = members[username]
                if m.plus_one_of_id is None:
                    m.plus_one_of = members[plus_of]
                    m.save(update_fields=["plus_one_of"])

        # Mark icon prompt done for all seeded members so they go straight
        # to the home screen instead of being stuck on settings after first login.
        for m in members.values():
            UserProfile.objects.update_or_create(
                user=m.user,
                defaults={"icon_prompt_done": True, "sounds_on": True},
            )

        eden = members["eden"]
        if not eden.dietary_notes:
            eden.dietary_notes = EDEN_DIET
            eden.save(update_fields=["dietary_notes"])

        ATTENDANCE_OVERRIDES = {
            # username: (arrive, depart, note)
            "kayla": (dt.date(2026, 7, 17), dt.date(2026, 7, 20), "Fri → Mon, tentative"),
            "ethan": (dt.date(2026, 7, 16), dt.date(2026, 7, 20), "Flies in ~11am day 1, leaves early afternoon day 5"),
            "eden": (dt.date(2026, 7, 16), dt.date(2026, 7, 20), "Traveling with Ethan"),
            "evan": (trip.start_date, dt.date(2026, 7, 21), "Has to leave Tuesday morning — earliest departure"),
        }
        for username, m in members.items():
            if m.is_ai:
                continue
            arrive, depart, note = ATTENDANCE_OVERRIDES.get(
                username, (trip.start_date, trip.end_date, ""),
            )
            Attendance.objects.get_or_create(
                trip=trip, member=m,
                defaults=dict(arrive=arrive, depart=depart, note=note),
            )

        # Rooms — assignments are already decided; nobody claims a spot in-app.
        # Wipe any stale rooms/claims from earlier seed runs before re-creating.
        RoomClaim.objects.filter(member__party=party).delete()
        Room.objects.filter(trip=trip).exclude(name__in=ROOM_CLAIMS.keys()).delete()
        rooms: dict[str, Room] = {}
        for name, cap, note in [
            ("Bedroom 1", 2, "Malachi & Abby"),
            ("Bedroom 2", 3, "Sabah, Cooper & Christy"),
            ("Ethan & Eden's room", 2, "Traveling together"),
            ("Grant & Trinity's room", 2, "Driving down together Thursday"),
            ("Bunk room", 4, "Evan, Clarence, Collin & Kayla"),
        ]:
            price = ROOM_CLAIMS[name][0]
            room, _ = Room.objects.update_or_create(
                trip=trip, name=name,
                defaults={"capacity": cap, "price_per_person": price, "comfort_note": note},
            )
            rooms[name] = room

        for room_name, (_, usernames) in ROOM_CLAIMS.items():
            for username in usernames:
                RoomClaim.objects.get_or_create(room=rooms[room_name], member=members[username])

        for offset, time_str, kind, title, desc, dist in ACTIVITIES:
            ItineraryActivity.objects.get_or_create(
                trip=trip,
                date=trip.start_date + dt.timedelta(days=offset),
                title=title,
                defaults=dict(
                    time=dt.datetime.strptime(time_str, "%H:%M").time() if time_str else None,
                    kind=kind,
                    description=desc,
                    distance_note=dist,
                ),
            )

        member_list = [m for m in members.values() if not m.is_ai]
        for title, amount, payer_username, method, offset, is_pre_trip, tags in EXPENSES:
            if Expense.objects.filter(trip=trip, title=title).exists():
                Expense.objects.filter(trip=trip, title=title, tags=[]).update(tags=tags)
                continue
            exp = Expense.objects.create(
                trip=trip,
                payer=members[payer_username],
                title=title,
                amount=Decimal(amount),
                incurred_on=trip.start_date + dt.timedelta(days=offset),
                is_pre_trip=is_pre_trip,
                split_method=method,
                tags=tags,
            )
            shares, note = preview_split(exp, member_list, method)
            exp.split_note = note
            exp.save(update_fields=["split_note"])
            ExpenseShare.objects.bulk_create([
                ExpenseShare(expense=exp, member_id=mid, amount=amt)
                for mid, amt in shares.items()
            ])

        static_img = Path(settings.BASE_DIR) / "static" / "img"
        self.stdout.write(f"Media storage: {default_storage.__class__.__name__}")
        # Re-sync demo feed photos every deploy — Postgres survives redeploys but
        # media files on Render's ephemeral disk do not. Replace any stale file so
        # S3 keys stay in sync with the database.
        for author_username, caption, filename in BOARD_PHOTOS:
            author = members[author_username]
            post = Post.objects.filter(
                trip=trip, kind=Post.KIND_PHOTO, author=author, text=caption,
            ).first()
            if not post:
                post = Post.objects.create(
                    trip=trip, author=author, kind=Post.KIND_PHOTO, text=caption,
                )
            src = static_img / filename
            if src.exists():
                if post.image:
                    post.image.delete(save=False)
                post.image.save(filename, ContentFile(src.read_bytes()), save=True)
                self.stdout.write(f"  photo → {post.image.name}")

        for section, items in GROCERY_SECTIONS.items():
            tl, created = TaskList.objects.get_or_create(
                trip=trip, name=section,
                defaults={"kind": TaskList.KIND_GROCERY,
                          "note": "Pick up on your way — remote area!"},
            )
            if created:
                TaskItem.objects.bulk_create([
                    TaskItem(task_list=tl, text=text, quantity=qty, order=i)
                    for i, (text, qty) in enumerate(items)
                ])
        pk_list, created = TaskList.objects.get_or_create(
            trip=trip, name="Packing list",
            defaults={"kind": TaskList.KIND_PACKING},
        )
        if created:
            TaskItem.objects.bulk_create([
                TaskItem(task_list=pk_list, text=t, order=i)
                for i, t in enumerate(PACKING)
            ])

        Announcement.objects.get_or_create(
            trip=trip,
            author=members["malachi"],
            text="Welcome to Brock Trip 2026! Check the grocery list and claim a room.",
            defaults={"pinned": True},
        )
        Announcement.objects.get_or_create(
            trip=trip,
            author=members["malachi"],
            audience=eden,
            text="Eden — remember to check the grocery list and confirm brands.",
        )

        # ---- Information pages: recipes + restricted dietary page ----
        for i, (slug, title, subtitle, body) in enumerate(RECIPES):
            InfoPage.objects.get_or_create(
                trip=trip, slug=slug,
                defaults=dict(title=title, subtitle=subtitle, body=body,
                              kind=InfoPage.KIND_RECIPE, order=i),
            )
        diet_page, _ = InfoPage.objects.get_or_create(
            trip=trip, slug="eden-dietary",
            defaults=dict(
                title="Eden's dietary restrictions",
                subtitle="Read before any grocery run or cooking shift",
                kind=InfoPage.KIND_NOTE,
                restricted=True,
                order=10,
                body=(
                    "This page is visible to admins, moderators, Eden, and Ethan only.\n"
                    "- DEATHLY allergic: fish, sesame (hummus/tahini!), sunflower seeds\n"
                    "- Sunflower oil is OK; sunflower seeds are not\n"
                    "- Peanuts and ALL tree nuts except almonds and pecans\n"
                    "- Swaps: almond butter not peanut butter, plain bagels not everything bagels, ranch not hummus\n"
                    "Label-check everything in Section C before it goes in the cart."
                ),
            ),
        )
        diet_page.allowed_members.add(eden, members["ethan"])

        house_page, _ = InfoPage.objects.get_or_create(
            trip=trip, slug="house-rules",
            defaults=dict(
                title="House notes & checkout",
                subtitle="How we leave the place",
                kind=InfoPage.KIND_NOTE,
                order=11,
                body=(
                    "The house has a keypad check-in, a hot tub spa suite, a theater room, "
                    "an outdoor kitchen, and a private pickleball court.\n"
                    "- Quiet hours after 11 PM — sound carries in the woods\n"
                    "- Last one to bed kills the fire pit and locks up\n"
                    "- Checkout morning: strip beds, trash out, sweep, dishwasher running"
                ),
            ),
        )

        # ---- Dinner polls: one per cook night, one two-stage demo ----
        malachi = members["malachi"]
        dinner_polls: list[Poll] = []
        for question, opts in [
            ("What do we eat night one (Thursday)?",
             ["Creamy tomato pasta bar", "Taco & burrito bowls", "Breakfast for dinner"]),
            ("What do we eat night two (Friday)?",
             ["BBQ cookout", "Coconut chickpea curry", "Big salad + garlic bread night"]),
        ]:
            poll = Poll.objects.filter(trip=trip, question=question).first()
            if not poll:
                poll = Poll.objects.create(trip=trip, author=malachi, question=question)
                for i, opt in enumerate(opts):
                    PollOption.objects.create(poll=poll, text=opt, order=i, suggested_by=malachi)
            dinner_polls.append(poll)

        q3 = "What do we eat night three (Saturday)? Suggest first, vote after."
        poll3 = Poll.objects.filter(trip=trip, question=q3).first()
        if not poll3:
            poll3 = Poll.objects.create(
                trip=trip, author=malachi, question=q3,
                two_stage=True, stage=Poll.STAGE_SUGGEST,
            )
            PollOption.objects.create(poll=poll3, text="Campfire chili + cornbread",
                                      order=0, suggested_by=members["ethan"])
            PollOption.objects.create(poll=poll3, text="Outdoor-kitchen pizza night",
                                      order=1, suggested_by=members["sabah"])
        dinner_polls.append(poll3)

        # Cast a few demo votes on the first poll
        p1 = dinner_polls[0]
        if p1.total_votes() == 0:
            opts = list(p1.options.all())
            for username, idx in [("abby", 0), ("grant", 0), ("eden", 1), ("kayla", 2), ("collin", 0)]:
                Vote.objects.get_or_create(option=opts[idx], member=members[username])

        # Feed posts for each poll (polls live in the feed)
        for poll in dinner_polls:
            Post.objects.get_or_create(
                trip=trip, kind=Post.KIND_POLL, poll=poll,
                defaults=dict(author=poll.author, title=poll.question, bg_color="#f6ecd9"),
            )

        # ---- Auto-generated helper posts (links become buttons) ----
        for title, text, path, label, color in [
            ("Grocery lists are live",
             "Three sections, three cars. Check yours off as you shop — the app tracks who grabbed what.",
             "/info/", "Open the lists", "#eef4e8"),
            ("The menu is posted",
             "Three planned dinners with full cooking instructions, all Eden-safe. Vote in the dinner polls to set the order.",
             "/info/", "See the menu", "#f6ecd9"),
            ("Attendance timeline is up",
             "See who's at the house each day and set your own arrive/depart times.",
             "/schedule/", "Open attendance timeline", "#e8f0f4"),
        ]:
            Post.objects.get_or_create(
                trip=trip, kind=Post.KIND_BLAST, title=title,
                defaults=dict(author=malachi, text=text, internal_path=path,
                              link_label=label, bg_color=color),
            )

        # ---- Cooper's suggestions ----
        for title, text, url in COOPER_SUGGESTIONS:
            Post.objects.get_or_create(
                trip=trip, kind=Post.KIND_SUGGESTION, title=title,
                defaults=dict(
                    author=malachi, text=text,
                    link_url=url, link_label="Look it up" if url else "",
                    suggested_by_note="Cooper's suggestion — posted by Malachi",
                    bg_color="#eef4e8",
                ),
            )

        # ---- Location suggestions: Cooper's picks (hiking, caverns, etc.) ----
        InfoPage.objects.get_or_create(
            trip=trip, slug="coopers-picks",
            defaults=dict(
                title="Cooper's picks",
                subtitle="Hikes, caverns & outdoor spots",
                kind=InfoPage.KIND_LOCATION,
                order=12,
                body=(
                    "Everything Cooper found — suggestions are also posted on the feed.\n"
                    + "\n".join(f"- {t}: {desc}" for t, desc, _ in COOPER_SUGGESTIONS)
                ),
                created_by=malachi, updated_by=malachi,
            ),
        )
        # ---- Location suggestions: spas & bathhouses (AI-curated) ----
        InfoPage.objects.get_or_create(
            trip=trip, slug="area-spas",
            defaults=dict(
                title="Spas & bathhouses",
                subtitle="Berkeley Springs area — relaxation picks",
                kind=InfoPage.KIND_LOCATION,
                order=13,
                body=(
                    "Berkeley Springs is one of the country's oldest spa towns — mineral springs everywhere.\n"
                    "- Berkeley Springs State Park bathhouse — historic Roman bath + warm mineral soaking tubs\n"
                    "- Berkeley Springs Spa Town — walkable strip of independent day spas downtown\n"
                    "- Coolfont Resort spa — resort-style, a few minutes from town (book ahead)"
                ),
                created_by=malachi, updated_by=malachi,
            ),
        )

        # ---- Party AI Squire — auto-suggested spa & area posts ----
        squire = members["squire"]
        for title, text, url in [
            ("Soak it in — Berkeley Springs bathhouse", "The state park bathhouse has the original "
             "Roman bath and warm mineral soaking tubs — an easy half-day between hikes.",
             "https://wvstateparks.com/park/berkeley-springs-state-park/"),
            ("Spa day option: Coolfont Resort", "Bigger resort-style spa a few minutes away if the "
             "state park bathhouse is booked up.", "https://coolfont.com/"),
            ("Dinner-out backup: Lot 12 Public House", "If nobody's up for cooking one night, this is "
             "the highest-rated spot downtown.", "https://www.lot12.com/"),
        ]:
            Post.objects.get_or_create(
                trip=trip, kind=Post.KIND_SUGGESTION, title=title,
                defaults=dict(
                    author=squire, text=text, link_url=url,
                    link_label="Look it up" if url else "",
                    suggested_by_note="Auto-suggested by Party AI Squire",
                    bg_color="#f1dde0",
                ),
            )

        self.stdout.write(self.style.SUCCESS("Brock Trip 2026 seeded."))
        if passwords:
            self.stdout.write("\nNew account passwords (send to each person):")
            for u, p in passwords:
                self.stdout.write(f"  {u:10s}  {p}")
        else:
            self.stdout.write("No new accounts created (already seeded).")
