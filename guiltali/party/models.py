"""Guiltali domain models.

Generalized bones (per Rec 42-new): Party -> Trip(Event) -> Member,
Expense, Task, Poll, Post. One party + one trip for the Brock Trip 2026
demo, but nothing here is single-trip-specific — roommate chores or a
Devil's-Path-style hike fit the same shapes.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


ICON_CHOICES = [
    ("leaf", "Leaf"), ("fire", "Campfire"), ("water", "Water drop"),
    ("bark", "Bark"), ("stone", "Stone"), ("mushroom", "Mushroom"),
    ("sun", "Sun"), ("pine", "Pine tree"), ("acorn", "Acorn"),
    ("mountain", "Mountain"), ("flower", "Flower"), ("tent", "Tent"),
    ("lantern", "Lantern"), ("compass", "Compass"), ("star", "Star"),
]

COLOR_CHOICES = [
    ("#2f7d4f", "Forest green"), ("#6b4d2e", "Bark brown"),
    ("#c9a441", "Golden"), ("#3f7fbf", "River blue"),
    ("#b0533b", "Clay red"), ("#7a5fa0", "Dusk purple"),
    ("#c47a3d", "Amber"), ("#4d8f8b", "Moss teal"),
    ("#96694b", "Timber"), ("#5d7f35", "Fern"),
]


class Party(models.Model):
    """A guild/party — the container for people and events."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "parties"

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """Per-user app preferences (primary trip, sounds)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="guiltali_profile")
    primary_trip = models.ForeignKey(
        "Trip", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="If set, the trips home screen is skipped until the trip ends.",
    )
    primary_prompt_answered = models.BooleanField(default=False)
    sounds_on = models.BooleanField(default=True)
    icon_prompt_done = models.BooleanField(default=False)

    def __str__(self):
        return f"prefs for {self.user.username}"


class Membership(models.Model):
    ROLE_ADMIN = "admin"
    ROLE_MODERATOR = "moderator"
    ROLE_MEMBER = "member"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_MODERATOR, "Moderator"),
        (ROLE_MEMBER, "Party Member"),
    ]

    VIS_EVERYONE = "everyone"
    VIS_MODS = "mods"
    VIS_ADMINS = "admins"
    VIS_CHOICES = [
        (VIS_EVERYONE, "Everyone on the trip"),
        (VIS_MODS, "Admins & moderators"),
        (VIS_ADMINS, "Admins only"),
    ]

    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    display_name = models.CharField(max_length=80, help_text="Real first + last name.")
    nickname = models.CharField(
        max_length=60, blank=True,
        help_text="If set, shown big everywhere instead of the real name (real name shows tiny underneath).",
    )
    alias = models.CharField(
        max_length=80, blank=True,
        help_text="Stylized title, e.g. 'The Quartermaster'. Shown alongside the name.",
    )
    is_ai = models.BooleanField(default=False, help_text="Marks the Party AI Squire suggestion account.")
    plus_one_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="plus_ones",
        help_text="Set when this member is someone's plus-one.",
    )
    dietary_notes = models.TextField(blank=True, help_text="Member-entered dietary restrictions / allergies.")
    emoji = models.CharField(max_length=8, blank=True, default="")
    icon = models.CharField(max_length=16, choices=ICON_CHOICES, blank=True, default="")
    color = models.CharField(max_length=9, choices=COLOR_CHOICES, blank=True, default="")
    travel_note = models.CharField(
        max_length=300, blank=True,
        help_text="Perceived travel plans, e.g. 'driving down Thursday night with Grant'.",
    )
    travel_note_visibility = models.CharField(max_length=10, choices=VIS_CHOICES, default=VIS_MODS)

    class Meta:
        unique_together = [("party", "user")]

    def __str__(self):
        return f"{self.display_name} ({self.get_role_display()})"

    @property
    def is_staff_role(self) -> bool:
        return self.role in (self.ROLE_ADMIN, self.ROLE_MODERATOR)

    @property
    def icon_url(self) -> str:
        from django.templatetags.static import static as static_url
        return static_url(f"img/icons/{self.icon or 'leaf'}.png")

    @property
    def swatch(self) -> str:
        return self.color or "#2f7d4f"

    @property
    def shown_name(self) -> str:
        return self.nickname or self.display_name

    @property
    def real_name_sub(self) -> str:
        """Shown as a tiny sub-line only when a nickname is in use."""
        return self.display_name if self.nickname else ""

    def roommates(self) -> "list[Membership]":
        claim = getattr(self, "room_claim", None)
        if not claim:
            return []
        return [
            c.member for c in claim.room.claims.select_related("member")
            if c.member_id != self.id
        ]

    def can_see_travel_note(self, viewer: "Membership") -> bool:
        if not self.travel_note:
            return False
        if viewer.id == self.id or viewer.role == self.ROLE_ADMIN:
            return True
        if self.travel_note_visibility == self.VIS_EVERYONE:
            return True
        if self.travel_note_visibility == self.VIS_MODS and viewer.is_staff_role:
            return True
        return False


class Trip(models.Model):
    """An event window for a party (the Brock Trip, a hike, a chore cycle)."""

    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="trips")
    name = models.CharField(max_length=160)
    slug = models.SlugField(unique=True)
    tagline = models.CharField(max_length=240, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    location_name = models.CharField(max_length=200, blank=True)
    listing_url = models.URLField(blank=True, help_text="Airbnb / lodging link")
    address = models.CharField(max_length=240, blank=True, help_text="Full street address (copyable in-app).")
    listing_title = models.CharField(max_length=200, blank=True, help_text="e.g. 'Home in Berkeley Springs'")
    listing_summary = models.TextField(blank=True, help_text="Description copied from the listing.")
    host_name = models.CharField(max_length=120, blank=True)
    guests = models.PositiveSmallIntegerField(null=True, blank=True)
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    beds = models.PositiveSmallIntegerField(null=True, blank=True)
    baths = models.PositiveSmallIntegerField(null=True, blank=True)
    check_in_note = models.CharField(max_length=200, blank=True, help_text="e.g. 'Check-in 4 PM — keypad'")
    check_out_note = models.CharField(max_length=200, blank=True)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    simplify_debts = models.BooleanField(
        default=False,
        help_text="When on, the settle screen shows the minimal set of payments instead of raw pairwise tabs.",
    )
    wifi_info = models.CharField(max_length=200, blank=True)
    lock_code = models.CharField(max_length=80, blank=True)
    checkout_note = models.CharField(max_length=240, blank=True)
    house_notes = models.TextField(blank=True)
    area_guide = models.TextField(
        blank=True,
        help_text="Local area guide (spas, national parks, etc). Same '- ' list formatting as InfoPage.",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    @property
    def is_over(self) -> bool:
        from django.utils import timezone
        return timezone.localdate() > self.end_date

    @property
    def day_range_label(self) -> str:
        return f"{self.start_date.strftime('%a')}–{self.end_date.strftime('%a')}"

    @property
    def default_poll_close(self):
        import datetime as _dt
        return _dt.datetime.combine(self.end_date + _dt.timedelta(days=2), _dt.time(20, 0))


class TripPhoto(models.Model):
    """Gallery photo for the stay (main picture + gallery, Airbnb-style)."""

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="trip_photos/", null=True, blank=True)
    static_path = models.CharField(
        max_length=200, blank=True,
        help_text="Alternative to an upload: path under static/, e.g. 'img/brock-cabin.jpg'.",
    )
    caption = models.CharField(max_length=200, blank=True)
    is_cover = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-is_cover", "order", "id"]

    def url(self) -> str:
        if self.image:
            return self.image.url
        from django.templatetags.static import static as static_url
        return static_url(self.static_path)


class ItineraryActivity(models.Model):
    """One scheduled block on the trail-style trip timeline."""

    KIND_TRAVEL = "travel"
    KIND_HIKE = "hike"
    KIND_MEAL = "meal"
    KIND_WATER = "water"
    KIND_SOCIAL = "social"
    KIND_FREE = "free"
    KIND_CHORE = "chore"
    KIND_CHOICES = [
        (KIND_TRAVEL, "Travel"),
        (KIND_HIKE, "Hike"),
        (KIND_MEAL, "Meal"),
        (KIND_WATER, "Water"),
        (KIND_SOCIAL, "Social"),
        (KIND_FREE, "Free time"),
        (KIND_CHORE, "Chore"),
    ]
    KIND_ICONS = {
        KIND_TRAVEL: "🚗",
        KIND_HIKE: "🥾",
        KIND_MEAL: "🍽️",
        KIND_WATER: "🏊",
        KIND_SOCIAL: "🔥",
        KIND_FREE: "🌤️",
        KIND_CHORE: "🧹",
    }

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="activities")
    date = models.DateField()
    time = models.TimeField(null=True, blank=True, help_text="Leave blank for an all-day block.")
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=KIND_FREE)
    title = models.CharField(max_length=160)
    description = models.CharField(max_length=300, blank=True)
    distance_note = models.CharField(
        max_length=80, blank=True,
        help_text="e.g. '4.2 mi · 900 ft gain' — shown as a small badge for hikes.",
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["date", "order", "time"]
        verbose_name_plural = "itinerary activities"

    def __str__(self):
        return f"{self.date} · {self.title}"

    @property
    def icon(self) -> str:
        return self.KIND_ICONS.get(self.kind, "📍")


class Attendance(models.Model):
    """When each member arrives/leaves — feeds partial-stay cost splits."""

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="attendances")
    member = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="attendances")
    arrive = models.DateField(null=True, blank=True)
    depart = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = [("trip", "member")]

    def nights(self) -> int:
        a = self.arrive or self.trip.start_date
        d = self.depart or self.trip.end_date
        return max((d - a).days, 0)


class Announcement(models.Model):
    """Notification bar items — admin/moderator only."""

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="announcements")
    author = models.ForeignKey(Membership, on_delete=models.CASCADE)
    text = models.CharField(max_length=400)
    audience = models.ForeignKey(
        Membership, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="targeted_announcements",
        help_text="Optional: aim this at one member (e.g. 'Eden: check the grocery list').",
    )
    pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pinned", "-created_at"]

    def __str__(self):
        return self.text[:60]


class Expense(models.Model):
    SPLIT_EQUAL = "equal"
    SPLIT_PERCENT = "percent"
    SPLIT_SHARES = "shares"
    SPLIT_PRESENT = "present"
    SPLIT_CUSTOM = "custom"
    SPLIT_ADJUST = "adjust"
    SPLIT_CHOICES = [
        (SPLIT_EQUAL, "Split equally"),
        (SPLIT_PERCENT, "Split by percentages"),
        (SPLIT_SHARES, "Split by shares"),
        (SPLIT_PRESENT, "Split by nights present"),
        (SPLIT_CUSTOM, "Exact amounts"),
        (SPLIT_ADJUST, "Split with adjustments"),
    ]

    TAG_CHOICES = [
        ("food", "Food"), ("travel", "Travel & gas"), ("lodging", "Lodging"),
        ("fun", "Fun & leisure"), ("gear", "Gear & supplies"),
        ("accident", "Accident"), ("misc", "Misc"),
    ]

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="expenses")
    payer = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="expenses_paid")
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=9, decimal_places=2)
    tags = models.JSONField(default=list, blank=True, help_text="List of tag slugs, e.g. ['food','fun'].")
    incurred_on = models.DateField(null=True, blank=True)
    is_pre_trip = models.BooleanField(default=False)
    split_method = models.CharField(max_length=16, choices=SPLIT_CHOICES, default=SPLIT_EQUAL)
    split_note = models.CharField(
        max_length=300, blank=True,
        help_text="Plain-language description of the algorithm used (shown to members).",
    )
    locked = models.BooleanField(default=False, help_text="Admin locked the split in.")
    receipt = models.ImageField(upload_to="receipts/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} (${self.amount})"


class ExpenseShare(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="shares")
    member = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="expense_shares")
    amount = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0"))
    excluded = models.BooleanField(default=False)

    class Meta:
        unique_together = [("expense", "member")]


class Settlement(models.Model):
    """Two-sided 'I paid you' -> 'confirmed received' handshake."""

    STATUS_CLAIMED = "claimed"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CHOICES = [(STATUS_CLAIMED, "Marked as paid"), (STATUS_CONFIRMED, "Confirmed received")]

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="settlements")
    from_member = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="settlements_out")
    to_member = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="settlements_in")
    amount = models.DecimalField(max_digits=9, decimal_places=2)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_CLAIMED)
    proof = models.ImageField(upload_to="settlement_proof/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class Room(models.Model):
    """Bedroom groups (houseing.txt): fixed assignments, comfort adjustments sum to ~0.

    Assignments are decided ahead of time (not claimed in-app) — each member
    only ever sees their own roommates, never the full room list.
    """

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=120)
    capacity = models.PositiveSmallIntegerField(default=2)
    comfort_note = models.CharField(max_length=240, blank=True)
    price_per_person = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Organizer-set per-person price. Leave blank to use equal split.",
    )

    def __str__(self):
        return f"{self.name} (sleeps {self.capacity})"

    def occupants(self):
        return self.claims.select_related("member")

    def spots_left(self) -> int:
        return max(self.capacity - self.claims.count(), 0)


class RoomClaim(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="claims")
    member = models.OneToOneField(Membership, on_delete=models.CASCADE, related_name="room_claim")
    claimed_at = models.DateTimeField(auto_now_add=True)


class TaskList(models.Model):
    """A named list (e.g. 'Grocery — Section A', 'Packing list')."""

    KIND_TASKS = "tasks"
    KIND_PACKING = "packing"
    KIND_GROCERY = "grocery"
    KIND_CHOICES = [
        (KIND_TASKS, "Tasks"),
        (KIND_PACKING, "Packing list"),
        (KIND_GROCERY, "Grocery list"),
    ]

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="task_lists")
    name = models.CharField(max_length=140)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=KIND_TASKS)
    assigned_to = models.ManyToManyField(Membership, blank=True, related_name="assigned_lists")
    note = models.CharField(max_length=300, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        Membership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_by = models.ForeignKey(
        Membership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name

    def progress(self) -> tuple[int, int]:
        items = list(self.items.all())
        return sum(1 for i in items if i.done), len(items)

    @property
    def done_count(self) -> int:
        return sum(1 for i in self.items.all() if i.done)


class TaskItem(models.Model):
    task_list = models.ForeignKey(TaskList, on_delete=models.CASCADE, related_name="items")
    text = models.CharField(max_length=240)
    quantity = models.CharField(max_length=60, blank=True)
    done = models.BooleanField(default=False)
    done_by = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_by = models.ForeignKey(
        Membership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="Whoever last checked or unchecked this item.",
    )
    updated_at = models.DateTimeField(null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text


class Poll(models.Model):
    STAGE_SUGGEST = "suggest"
    STAGE_VOTE = "vote"
    STAGE_CLOSED = "closed"
    STAGE_CHOICES = [
        (STAGE_SUGGEST, "Collecting suggestions"),
        (STAGE_VOTE, "Voting"),
        (STAGE_CLOSED, "Closed"),
    ]

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="polls")
    author = models.ForeignKey(Membership, on_delete=models.CASCADE)
    question = models.CharField(max_length=300)
    anonymous = models.BooleanField(default=False)
    multiple_choice = models.BooleanField(default=False)
    two_stage = models.BooleanField(
        default=False,
        help_text="Stage 1: everyone suggests options. Stage 2: everyone votes (not on their own).",
    )
    stage = models.CharField(max_length=8, choices=STAGE_CHOICES, default=STAGE_VOTE)
    closes_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Defaults to 2 days after the trip ends if left blank.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.question

    def total_votes(self) -> int:
        return Vote.objects.filter(option__poll=self).count()

    def voter_ids(self) -> set[int]:
        return set(Vote.objects.filter(option__poll=self).values_list("member_id", flat=True))

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone
        return bool(self.closes_at) and timezone.now() >= self.closes_at


class PollOption(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=200)
    suggested_by = models.ForeignKey(
        Membership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text


class Vote(models.Model):
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name="votes")
    member = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="votes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("option", "member")]


class Post(models.Model):
    """Text blasts + suggestions + photos — post/comment style, not chat."""

    KIND_BLAST = "blast"
    KIND_SUGGESTION = "suggestion"
    KIND_PHOTO = "photo"
    KIND_POLL = "poll"
    KIND_CHOICES = [
        (KIND_BLAST, "Note"),
        (KIND_SUGGESTION, "Suggestion"),
        (KIND_PHOTO, "Photo"),
        (KIND_POLL, "Poll"),
    ]

    BG_CHOICES = [
        ("", "Default"), ("#eef4e8", "Meadow"), ("#f6ecd9", "Sand"),
        ("#e8f0f4", "Sky"), ("#f4e8ee", "Berry"), ("#efe9df", "Parchment"),
    ]

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="posts")
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=KIND_BLAST)
    title = models.CharField(max_length=160, blank=True)
    text = models.TextField(blank=True)
    image = models.ImageField(upload_to="posts/", null=True, blank=True)
    link_url = models.URLField(blank=True, help_text="Rendered as a button on the post.")
    link_label = models.CharField(max_length=80, blank=True)
    internal_path = models.CharField(
        max_length=200, blank=True,
        help_text="In-app link, e.g. '/info/' — rendered as a button.",
    )
    bg_color = models.CharField(max_length=9, choices=BG_CHOICES, blank=True, default="")
    suggested_by_note = models.CharField(
        max_length=120, blank=True,
        help_text="e.g. 'Cooper's suggestion' when someone posts on another's behalf.",
    )
    poll = models.OneToOneField(
        Poll, null=True, blank=True, on_delete=models.SET_NULL, related_name="feed_post",
        help_text="Polls surface in the feed through their linked post.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_kind_display()}] {self.text[:50]}"

    def all_images(self):
        out = []
        if self.image:
            out.append(self.image)
        out.extend(pi.image for pi in self.extra_images.all())
        return out

    def reaction_summary(self):
        """[{'emoji': '🔥', 'count': 2}, ...] ordered by count desc."""
        counts: dict[str, int] = {}
        for r in self.reactions.all():
            counts[r.emoji] = counts.get(r.emoji, 0) + 1
        return sorted(
            ({"emoji": e, "count": c} for e, c in counts.items()),
            key=lambda r: -r["count"],
        )


class PostImage(models.Model):
    """Extra images on a post (multi-picture slider)."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="extra_images")
    image = models.ImageField(upload_to="posts/")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(Membership, on_delete=models.CASCADE)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class InfoPage(models.Model):
    """A page in the Information area: recipes, house notes, restricted info.

    Restricted pages are visible to admins, moderators, and any member in
    `allowed_members` (e.g. Eden's dietary details for Eden + Ethan).
    """

    KIND_RECIPE = "recipe"
    KIND_NOTE = "note"
    KIND_LOCATION = "location"
    KIND_MOVIE = "movie"
    KIND_CHOICES = [
        (KIND_RECIPE, "Recipe"), (KIND_NOTE, "Note"),
        (KIND_LOCATION, "Location suggestions"), (KIND_MOVIE, "Movie suggestions"),
    ]

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="info_pages")
    slug = models.SlugField()
    title = models.CharField(max_length=160)
    subtitle = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default=KIND_NOTE)
    body = models.TextField(help_text="Plain text; blank lines split paragraphs, lines starting with '- ' become list items.")
    restricted = models.BooleanField(default=False)
    allowed_members = models.ManyToManyField(
        Membership, blank=True, related_name="visible_info_pages",
        help_text="Members (besides admins/mods) who can see a restricted page.",
    )
    order = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_by = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("trip", "slug")]

    def __str__(self):
        return self.title

    def visible_to(self, member: Membership) -> bool:
        if not self.restricted:
            return True
        if member.is_staff_role:
            return True
        return self.allowed_members.filter(pk=member.pk).exists()


class PostReaction(models.Model):
    EMOJI_CHOICES = [
        ("👍", "Thumbs up"), ("👎", "Thumbs down"), ("❤️", "Love it"),
        ("😂", "Funny"), ("🔥", "Fire"), ("⛺", "Camping mood"),
    ]

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reactions")
    member = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="reactions")
    emoji = models.CharField(max_length=8, choices=EMOJI_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("post", "member", "emoji")]
