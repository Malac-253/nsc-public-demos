from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import (
    Announcement,
    Attendance,
    Comment,
    Event,
    Expense,
    ExpenseShare,
    ICON_CHOICES,
    COLOR_CHOICES,
    InfoPage,
    ItineraryActivity,
    Membership,
    Notification,
    Poll,
    PollOption,
    Post,
    PostImage,
    PostVideo,
    PostReaction,
    Settlement,
    TaskItem,
    TaskList,
    Trip,
    UserProfile,
    Vote,
)
from .splits import member_balances, preview_split, raw_pairwise_debts, simplify_debts, tag_totals


def _text_blocks(body: str):
    paragraphs = []
    bullets: list[str] = []
    for block in (body or "").split("\n"):
        line = block.strip()
        if line.startswith("- "):
            bullets.append(line[2:])
            continue
        if bullets:
            paragraphs.append({"kind": "list", "items": bullets})
            bullets = []
        if line:
            paragraphs.append({"kind": "p", "text": line})
    if bullets:
        paragraphs.append({"kind": "list", "items": bullets})
    return paragraphs


def _trip(request) -> Trip:
    return get_object_or_404(Trip.objects.select_related("party"), is_active=True)


def _me(request, trip: Trip) -> Membership:
    return get_object_or_404(Membership, party=trip.party, user=request.user)


def _profile(request) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return profile


def _feed_return_path(request, post_id: int | None = None) -> str:
    """Build a feed URL that restores scroll to a specific post (via #post-id)."""
    nxt = request.POST.get("next") or request.GET.get("next") or reverse("feed")
    base = nxt.split("#")[0]
    if post_id:
        return f"{base}#post-{post_id}"
    return base


def _redirect_feed(request, post_id: int | None = None):
    return redirect(_feed_return_path(request, post_id))


def _notify_everyone(trip: Trip, text: str, *, actor: Membership | None = None, link_path: str = ""):
    members = trip.party.memberships.exclude(is_ai=True)
    if actor:
        members = members.exclude(pk=actor.pk)
    Notification.objects.bulk_create([
        Notification(trip=trip, recipient=m, actor=actor, text=text, link_path=link_path)
        for m in members
    ])


@login_required
def member_link(request, member_id: int):
    """One link everywhere: your own icon -> settings, anyone else's -> their posts."""
    trip = _trip(request)
    me = _me(request, trip)
    target = get_object_or_404(Membership, pk=member_id, party=trip.party)
    if target.id == me.id:
        return redirect("settings")
    return redirect(f"{reverse('feed')}?member={target.id}")


@login_required
def notifications_list(request):
    trip = _trip(request)
    me = _me(request, trip)
    if request.method == "POST" and request.POST.get("action") == "mark_all_read":
        Notification.objects.filter(recipient=me, read_at__isnull=True).update(read_at=timezone.now())
        return redirect("notifications")
    notifs = Notification.objects.filter(recipient=me).select_related("actor")
    return render(request, "party/notifications.html", {"notifs": notifs})


@login_required
def notif_open(request, notif_id: int):
    trip = _trip(request)
    me = _me(request, trip)
    n = get_object_or_404(Notification, pk=notif_id, recipient=me)
    if not n.read_at:
        n.read_at = timezone.now()
        n.save(update_fields=["read_at"])
    return redirect(n.link_path or "notifications")


# ---------------------------------------------------------------- trips home

@login_required
def trips_home(request):
    """Landing screen: every trip you're a part of."""
    profile = _profile(request)
    memberships = request.user.memberships.select_related("party")
    trips = Trip.objects.filter(party__in=[m.party_id for m in memberships]).order_by("-start_date")

    # Primary-trip skip: jump straight to the trip until it's over.
    if profile.primary_trip and not profile.primary_trip.is_over:
        return redirect("home")

    return render(request, "party/trips_home.html", {
        "trips": trips,
        "profile": profile,
    })


@login_required
def choose_trip(request, trip_id: int):
    """Tapping a trip badge — maybe prompt to set as primary."""
    profile = _profile(request)
    trip = get_object_or_404(Trip, pk=trip_id, party__memberships__user=request.user)
    if request.method == "POST":
        answer = request.POST.get("primary")
        profile.primary_prompt_answered = True
        if answer == "yes":
            profile.primary_trip = trip
        profile.save()
        return redirect("home")
    if profile.primary_prompt_answered:
        return redirect("home")
    return render(request, "party/primary_prompt.html", {"chosen_trip": trip})


# ---------------------------------------------------------------- trip pages

@login_required
def home(request):
    trip = _trip(request)
    me = _me(request, trip)
    profile = _profile(request)
    if not profile.icon_prompt_done or not me.icon:
        return redirect("settings")
    members = trip.party.memberships.exclude(is_ai=True).select_related("user", "plus_one_of").order_by("role", "display_name")
    days = (trip.end_date - trip.start_date).days
    today = timezone.localdate()
    progress = None
    if trip.start_date <= today <= trip.end_date and days:
        progress = int(((today - trip.start_date).days / days) * 100)
    return render(request, "party/home.html", {
        "members": members,
        "trip_progress": progress,
        "recent_posts": trip.posts.select_related("author")[:3],
        "menu_pages": trip.info_pages.filter(kind=InfoPage.KIND_RECIPE)[:3],
    })


@login_required
def itinerary(request):
    trip = _trip(request)
    _me(request, trip)
    attendances = list(trip.attendances.select_related("member").order_by("arrive"))
    activities_by_day: dict = {}
    for act in trip.activities.all():
        activities_by_day.setdefault(act.date, []).append(act)
    day_count = (trip.end_date - trip.start_date).days + 1
    days = []
    for offset in range(day_count):
        day = trip.start_date + timezone.timedelta(days=offset)
        arriving = [a.member for a in attendances if (a.arrive or trip.start_date) == day]
        departing = [a.member for a in attendances if (a.depart or trip.end_date) == day]
        days.append({
            "date": day,
            "day_num": offset + 1,
            "arriving": arriving,
            "departing": departing,
            "activities": activities_by_day.get(day, []),
        })
    return render(request, "party/itinerary.html", {
        "days": days,
        "today": timezone.localdate(),
    })


@login_required
def schedule(request):
    """Center-bar chart: who's here on which days (editable)."""
    trip = _trip(request)
    me = _me(request, trip)
    members = list(trip.party.memberships.exclude(is_ai=True).select_related("user").order_by("display_name"))
    att = {a.member_id: a for a in trip.attendances.all()}

    if request.method == "POST":
        target_id = int(request.POST.get("member_id", me.id))
        target = get_object_or_404(Membership, pk=target_id, party=trip.party)
        if target.id != me.id and not me.is_staff_role:
            messages.error(request, "Only admins and moderators can edit someone else's stay.")
            return redirect("schedule")
        a, _ = Attendance.objects.get_or_create(trip=trip, member=target)
        try:
            arrive = dt.date.fromisoformat(request.POST.get("arrive", ""))
            depart = dt.date.fromisoformat(request.POST.get("depart", ""))
        except ValueError:
            messages.error(request, "Pick both dates.")
            return redirect("schedule")
        arrive = max(arrive, trip.start_date)
        depart = min(depart, trip.end_date)
        if depart < arrive:
            messages.error(request, "Departure can't be before arrival.")
            return redirect("schedule")
        a.arrive, a.depart = arrive, depart
        a.note = request.POST.get("note", a.note)[:200]
        a.save()
        if request.POST.get("travel_note") is not None and (target.id == me.id or me.is_staff_role):
            target.travel_note = request.POST["travel_note"][:300]
            target.save(update_fields=["travel_note"])
        messages.success(request, f"Updated {target.display_name}'s stay.")
        return redirect("schedule")

    day_count = (trip.end_date - trip.start_date).days + 1
    day_list = [trip.start_date + dt.timedelta(days=i) for i in range(day_count)]
    rows = []
    for m in members:
        a = att.get(m.id)
        arrive = (a.arrive if a and a.arrive else trip.start_date)
        depart = (a.depart if a and a.depart else trip.end_date)
        start_idx = max((arrive - trip.start_date).days, 0)
        end_idx = min((depart - trip.start_date).days, day_count - 1)
        rows.append({
            "member": m,
            "arrive": arrive,
            "depart": depart,
            "note": a.note if a else "",
            "start_pct": int(start_idx / day_count * 100),
            "width_pct": int((end_idx - start_idx + 1) / day_count * 100),
            "nights": max((depart - arrive).days, 0),
            "travel_note": m.travel_note if m.can_see_travel_note(me) else "",
            "editable": (m.id == me.id) or me.is_staff_role,
        })
    return render(request, "party/schedule.html", {
        "rows": rows,
        "day_list": day_list,
        "today": timezone.localdate(),
    })


@login_required
def stay(request):
    trip = _trip(request)
    me = _me(request, trip)
    return render(request, "party/stay.html", {
        "photos": trip.photos.all(),
        "roommates": me.roommates(),
        "area_blocks": _text_blocks(trip.area_guide),
        "can_edit": me.is_staff_role,
    })


@login_required
def experience(request):
    """The 'Brock Trip 2026' hero — trip story + the Berkeley Springs area guide."""
    trip = _trip(request)
    me = _me(request, trip)
    return render(request, "party/experience.html", {
        "trip": trip,
        "area_blocks": _text_blocks(trip.area_guide),
        "house_blocks": _text_blocks(trip.house_notes),
        "can_edit": me.is_staff_role,
    })


@login_required
def trip_edit(request):
    trip = _trip(request)
    me = _me(request, trip)
    if not me.is_staff_role:
        raise Http404
    fields = [
        "name", "tagline", "listing_title", "listing_summary", "address", "host_name",
        "guests", "bedrooms", "beds", "baths", "check_in_note", "checkout_note",
        "wifi_info", "lock_code", "house_notes", "area_guide",
    ]
    if request.method == "POST":
        for f in fields:
            if f in request.POST:
                value = request.POST.get(f, "").strip()
                field = Trip._meta.get_field(f)
                if field.get_internal_type() == "PositiveSmallIntegerField":
                    value = int(value) if value.isdigit() else getattr(trip, f)
                setattr(trip, f, value)
        trip.save()
        messages.success(request, "Trip details updated.")
        return redirect("experience")
    return render(request, "party/trip_edit.html", {"trip": trip, "fields": fields})


# ---------------------------------------------------------------- budget

TAG_MAP = dict(Expense.TAG_CHOICES)


def _parse_detail(request, members) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    for m in members:
        raw = request.POST.get(f"detail_{m.id}", "").strip()
        if raw:
            try:
                out[m.id] = Decimal(raw)
            except InvalidOperation:
                pass
    return out


def _parse_participants(request, members: list) -> list:
    """Members included on this expense (defaults to everyone if none checked)."""
    picked = [m for m in members if request.POST.get(f"include_{m.id}")]
    return picked or list(members)


def _can_edit_expense(me: Membership, exp: Expense) -> bool:
    return exp.payer_id == me.id or me.role == Membership.ROLE_ADMIN


def _expense_to_pending(exp: Expense, members: list) -> dict:
    """Serialize an existing expense into the session draft shape."""
    shares = list(exp.shares.all())
    participants = [s.member_id for s in shares if not s.excluded]
    if not participants:
        participants = [m.id for m in members]
    detail: dict[str, str] = {}
    n = len(participants)
    if exp.split_method == Expense.SPLIT_PERCENT and exp.amount:
        for s in shares:
            if not s.excluded:
                pct = (s.amount / exp.amount * 100).quantize(Decimal("0.01"))
                detail[str(s.member_id)] = str(pct)
    elif exp.split_method == Expense.SPLIT_CUSTOM:
        for s in shares:
            if not s.excluded:
                detail[str(s.member_id)] = str(s.amount)
    elif exp.split_method == Expense.SPLIT_ADJUST and n:
        baseline = (exp.amount / Decimal(n)).quantize(Decimal("0.01"))
        for s in shares:
            if not s.excluded:
                detail[str(s.member_id)] = str((s.amount - baseline).quantize(Decimal("0.01")))
    elif exp.split_method == Expense.SPLIT_SHARES:
        for s in shares:
            if not s.excluded:
                detail[str(s.member_id)] = str(int(s.amount)) if s.amount == int(s.amount) else str(s.amount)
    return {
        "editing_id": exp.id,
        "title": exp.title,
        "amount": str(exp.amount),
        "payer_id": exp.payer_id,
        "method": exp.split_method,
        "tags": exp.tags or [],
        "is_pre_trip": exp.is_pre_trip,
        "participants": participants,
        "row_color": exp.row_color or "",
        "detail": detail,
    }


@login_required
def budget(request):
    trip = _trip(request)
    me = _me(request, trip)
    members = list(trip.party.memberships.exclude(is_ai=True).select_related("user"))
    balances = member_balances(trip)
    my_balance = balances.get(me.id, Decimal("0"))

    expense_rows = []
    for exp in trip.expenses.select_related("payer").prefetch_related("shares__member"):
        my_share_obj = next((s for s in exp.shares.all() if s.member_id == me.id), None)
        mine = my_share_obj.amount if my_share_obj and not my_share_obj.excluded else None
        expense_rows.append({
            "exp": exp,
            "my_share": mine,
            "excluded": my_share_obj.excluded if my_share_obj else False,
            "tag_labels": [TAG_MAP.get(t, t) for t in (exp.tags or [])],
            "can_edit": _can_edit_expense(me, exp),
        })

    balance_rows = None
    if me.is_staff_role:
        balance_rows = sorted(
            ({"member": m, "balance": balances.get(m.id, Decimal("0"))} for m in members),
            key=lambda r: r["balance"],
        )

    return render(request, "party/budget.html", {
        "expense_rows": expense_rows,
        "my_balance": my_balance,
        "balance_rows": balance_rows,
        "split_choices": Expense.SPLIT_CHOICES,
        "tag_choices": Expense.TAG_CHOICES,
        "members": members,
        "tag_rows": tag_totals(trip),
        "total_spent": sum((e.amount for e in trip.expenses.all()), Decimal("0")),
    })


@login_required
def budget_charts(request):
    """Where the money went — full breakdown by tag and by person."""
    trip = _trip(request)
    me = _me(request, trip)
    members = list(trip.party.memberships.exclude(is_ai=True).select_related("user"))
    balances = member_balances(trip)
    person_rows = sorted(
        (
            {
                "member": m,
                "paid": sum((e.amount for e in trip.expenses.filter(payer=m)), Decimal("0")),
                "balance": balances.get(m.id, Decimal("0")),
            }
            for m in members
        ),
        key=lambda r: r["paid"], reverse=True,
    )
    return render(request, "party/budget_charts.html", {
        "tag_rows": tag_totals(trip),
        "person_rows": person_rows,
        "total_spent": sum((e.amount for e in trip.expenses.all()), Decimal("0")),
    })


@login_required
def budget_add(request):
    """Full-screen add-expense form (opened from the budget + FAB)."""
    trip = _trip(request)
    me = _me(request, trip)
    members = list(trip.party.memberships.exclude(is_ai=True).select_related("user"))

    draft = None
    if request.GET.get("edit") and request.session.get("pending_expense"):
        draft = request.session["pending_expense"]
    elif request.method != "POST":
        request.session.pop("pending_expense", None)

    member_fields = []
    for m in members:
        included = True
        detail_val = ""
        if draft:
            included = m.id in draft.get("participants", [x.id for x in members])
            detail_val = draft.get("detail", {}).get(str(m.id), "")
        member_fields.append({"member": m, "included": included, "detail_val": detail_val})

    if request.method == "POST" and request.POST.get("action") == "add":
        title = request.POST.get("title", "").strip()
        try:
            amount = Decimal(request.POST.get("amount", "0"))
        except InvalidOperation:
            amount = Decimal("0")
        if not title or amount <= 0:
            messages.error(request, "Give the expense a name and an amount.")
            return redirect("budget_add")
        method = request.POST.get("split_method", Expense.SPLIT_EQUAL)
        payer_id = int(request.POST.get("payer", me.id))
        participants = _parse_participants(request, members)
        detail = _parse_detail(request, participants)
        row_color = request.POST.get("row_color", "").strip()
        if row_color and not row_color.startswith("#"):
            row_color = ""
        pending_data = {
            "title": title,
            "amount": str(amount),
            "payer_id": payer_id,
            "method": method,
            "tags": request.POST.getlist("tags"),
            "is_pre_trip": bool(request.POST.get("is_pre_trip")),
            "detail": {str(k): str(v) for k, v in detail.items()},
            "participants": [m.id for m in participants],
            "row_color": row_color,
        }
        prev = request.session.get("pending_expense") or {}
        if prev.get("editing_id"):
            pending_data["editing_id"] = prev["editing_id"]
        request.session["pending_expense"] = pending_data
        return redirect("budget_confirm")

    row_color_choices = [
        ("#2f7d4f", "Forest green"), ("#5d7f35", "Fern"),
        ("#c47a3d", "Amber"), ("#c9a441", "Gold"),
        ("#3f7fbf", "River blue"), ("#4d8f8b", "Moss teal"),
        ("#b0533b", "Clay red"), ("#7a5fa0", "Dusk purple"),
        ("#6b4d2e", "Bark brown"),
    ]
    return render(request, "party/budget_add.html", {
        "members": members,
        "member_fields": member_fields,
        "split_choices": Expense.SPLIT_CHOICES,
        "tag_choices": Expense.TAG_CHOICES,
        "row_color_choices": row_color_choices,
        "draft": draft,
        "editing": bool(draft and draft.get("editing_id")),
    })


@login_required
def budget_edit(request, expense_id: int):
    """Load an existing expense into the add/confirm flow for editing."""
    trip = _trip(request)
    me = _me(request, trip)
    exp = get_object_or_404(
        Expense.objects.prefetch_related("shares"),
        pk=expense_id, trip=trip,
    )
    if not _can_edit_expense(me, exp):
        raise Http404
    members = list(trip.party.memberships.exclude(is_ai=True).select_related("user"))
    request.session["pending_expense"] = _expense_to_pending(exp, members)
    return redirect(f"{reverse('budget_add')}?edit=1")


@login_required
def budget_confirm(request):
    """Preview screen: 'does this information look good?'"""
    trip = _trip(request)
    me = _me(request, trip)
    pending = request.session.get("pending_expense")
    if not pending:
        return redirect("budget")
    members = list(trip.party.memberships.exclude(is_ai=True).select_related("user"))
    payer = next((m for m in members if m.id == pending["payer_id"]), me)
    participant_ids = set(pending.get("participants") or [m.id for m in members])
    participants = [m for m in members if m.id in participant_ids]
    excluded = [m for m in members if m.id not in participant_ids]

    exp = Expense(
        trip=trip, payer=payer, title=pending["title"],
        amount=Decimal(pending["amount"]),
        split_method=pending["method"],
        is_pre_trip=pending["is_pre_trip"],
    )
    detail = {int(k): Decimal(v) for k, v in pending.get("detail", {}).items()}
    shares, note = preview_split(exp, participants, pending["method"], detail)
    if excluded:
        names = ", ".join(m.shown_name for m in excluded)
        note = f"{note} Not included: {names}."
    member_map = {m.id: m for m in members}
    share_rows = [
        {"member": member_map[mid], "amount": amt}
        for mid, amt in shares.items() if amt > 0
    ]
    share_rows.sort(key=lambda r: r["amount"], reverse=True)

    if request.method == "POST":
        if request.POST.get("action") == "confirm":
            editing_id = pending.get("editing_id")
            if editing_id:
                exp = get_object_or_404(Expense, pk=editing_id, trip=trip)
                if not _can_edit_expense(me, exp):
                    raise Http404
                exp.title = pending["title"]
                exp.amount = Decimal(pending["amount"])
                exp.payer_id = pending["payer_id"]
                exp.split_method = pending["method"]
                exp.is_pre_trip = pending["is_pre_trip"]
                exp.tags = pending["tags"]
                exp.split_note = note
                exp.row_color = pending.get("row_color", "")
                exp.save()
                exp.shares.all().delete()
                share_objs = [
                    ExpenseShare(expense=exp, member_id=mid, amount=amt)
                    for mid, amt in shares.items()
                ]
                for m in excluded:
                    share_objs.append(ExpenseShare(expense=exp, member=m, amount=Decimal("0"), excluded=True))
                ExpenseShare.objects.bulk_create(share_objs)
                del request.session["pending_expense"]
                messages.success(request, f"Updated {exp.title} — {note}")
                return redirect("budget")
            exp.incurred_on = timezone.localdate()
            exp.tags = pending["tags"]
            exp.split_note = note
            exp.row_color = pending.get("row_color", "")
            exp.save()
            share_objs = [
                ExpenseShare(expense=exp, member_id=mid, amount=amt)
                for mid, amt in shares.items()
            ]
            for m in excluded:
                share_objs.append(ExpenseShare(expense=exp, member=m, amount=Decimal("0"), excluded=True))
            ExpenseShare.objects.bulk_create(share_objs)
            del request.session["pending_expense"]
            messages.success(request, f"Added {exp.title} — {note}")
            return redirect("budget")
        if request.POST.get("action") == "cancel":
            return redirect(f"{reverse('budget_add')}?edit=1")
        return redirect("budget")

    return render(request, "party/budget_confirm.html", {
        "pending": pending,
        "payer": payer,
        "note": note,
        "share_rows": share_rows,
        "excluded": excluded,
        "tag_labels": [TAG_MAP.get(t, t) for t in pending["tags"]],
        "editing": bool(pending.get("editing_id")),
    })


@login_required
def budget_delete(request, expense_id: int):
    trip = _trip(request)
    me = _me(request, trip)
    exp = get_object_or_404(Expense, pk=expense_id, trip=trip)
    if not _can_edit_expense(me, exp):
        raise Http404
    if request.method == "POST":
        title = exp.title
        exp.delete()
        messages.success(request, f"Deleted “{title}.”")
        return redirect("budget")
    return redirect("budget")


@login_required
def budget_backup(request):
    """Admin-only: snapshot every expense/settlement to a JSON file — a durable
    backup independent of the database, saved to media storage and downloadable
    on demand (works with either the local disk or an S3 backend)."""
    import json
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from django.http import HttpResponse

    trip = _trip(request)
    me = _me(request, trip)
    if me.role != Membership.ROLE_ADMIN:
        raise Http404

    def money(x):
        return str(x) if x is not None else None

    expenses = []
    for exp in trip.expenses.select_related("payer").prefetch_related("shares__member"):
        expenses.append({
            "id": exp.id, "title": exp.title, "amount": money(exp.amount),
            "payer": exp.payer.display_name, "split_method": exp.split_method,
            "tags": exp.tags, "incurred_on": str(exp.incurred_on) if exp.incurred_on else None,
            "shares": [
                {"member": s.member.display_name, "amount": money(s.amount), "excluded": s.excluded}
                for s in exp.shares.all()
            ],
        })
    settlements = [
        {
            "from": s.from_member.display_name, "to": s.to_member.display_name,
            "amount": money(s.amount), "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in trip.settlements.select_related("from_member", "to_member")
    ]
    payload = {
        "generated_at": timezone.now().isoformat(),
        "trip": trip.name,
        "expenses": expenses,
        "settlements": settlements,
    }
    data = json.dumps(payload, indent=2, default=str)
    fname = f"backups/expenses-{timezone.now():%Y%m%d-%H%M%S}.json"
    try:
        default_storage.save(fname, ContentFile(data.encode("utf-8")))
    except Exception:
        pass  # storage backend unavailable — still let the admin download the copy below
    resp = HttpResponse(data, content_type="application/json")
    resp["Content-Disposition"] = f'attachment; filename="{fname.rsplit("/", 1)[-1]}"'
    return resp


@login_required
def settle_screen(request):
    trip = _trip(request)
    me = _me(request, trip)
    members = list(trip.party.memberships.exclude(is_ai=True).select_related("user"))
    member_map = {m.id: m for m in members}
    balances = member_balances(trip)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "claim":
            to_member = get_object_or_404(Membership, pk=int(request.POST["to_member"]), party=trip.party)
            amount = Decimal(request.POST["amount"])
            Settlement.objects.create(
                trip=trip, from_member=me,
                to_member=to_member,
                amount=amount,
                proof=request.FILES.get("proof"),
            )
            Notification.notify(
                trip, to_member, f"{me.shown_name} says they paid you ${amount}.",
                actor=me, link_path=reverse("settle"),
            )
            messages.success(request, "Marked as paid — waiting for them to confirm.")
        elif action == "confirm":
            s = get_object_or_404(Settlement, pk=request.POST["settlement_id"], to_member=me)
            s.status = Settlement.STATUS_CONFIRMED
            s.confirmed_at = timezone.now()
            s.save(update_fields=["status", "confirmed_at"])
            Notification.notify(
                trip, s.from_member, f"{me.shown_name} confirmed your ${s.amount} payment.",
                actor=me, link_path=reverse("settle"),
            )
            messages.success(request, "Payment confirmed.")
        elif action == "toggle_simplify" and me.role == Membership.ROLE_ADMIN:
            trip.simplify_debts = not trip.simplify_debts
            trip.save(update_fields=["simplify_debts"])
        return redirect("settle")

    plan_rows = []
    raw_plan_rows = []
    if trip.simplify_debts:
        for from_id, to_id, amt in simplify_debts(balances):
            plan_rows.append({
                "from_member": member_map[from_id],
                "to_member": member_map[to_id],
                "amount": amt,
                "mine": from_id == me.id or to_id == me.id,
            })
    else:
        for from_id, to_id, amt in raw_pairwise_debts(trip):
            raw_plan_rows.append({
                "from_member": member_map[from_id],
                "to_member": member_map[to_id],
                "amount": amt,
                "mine": from_id == me.id or to_id == me.id,
            })

    balance_rows = sorted(
        ({"member": m, "balance": balances.get(m.id, Decimal("0"))} for m in members),
        key=lambda r: r["balance"],
        reverse=True,
    )

    return render(request, "party/settle.html", {
        "my_balance": balances.get(me.id, Decimal("0")),
        "members": members,
        "settlements": trip.settlements.select_related("from_member", "to_member")[:20],
        "plan_rows": plan_rows,
        "raw_plan_rows": raw_plan_rows,
        "balance_rows": balance_rows,
        "is_admin": me.role == Membership.ROLE_ADMIN,
    })


@login_required
def receipt(request, member_id: int | None = None):
    """Receipt-style ledger: group receipt, my receipt, or (admin) anyone's."""
    trip = _trip(request)
    me = _me(request, trip)
    scope = "group"
    target = None
    if member_id is not None:
        target = get_object_or_404(Membership, pk=member_id, party=trip.party)
        if target.id != me.id and me.role != Membership.ROLE_ADMIN:
            raise Http404
        scope = "member"

    rows = []
    total = Decimal("0")
    expenses = trip.expenses.select_related("payer").prefetch_related("shares__member").order_by("incurred_on", "id")
    for exp in expenses:
        my_share = None
        is_yours = False
        if scope == "member":
            share = next((s.amount for s in exp.shares.all() if s.member_id == target.id), None)
            if share is None or share == 0:
                continue
            amount = share
            is_yours = True
        else:
            amount = exp.amount
            share = next((s for s in exp.shares.all() if s.member_id == me.id and not s.excluded), None)
            if share:
                my_share = share.amount
            is_yours = exp.payer_id == me.id
        total += amount
        rows.append({
            "exp": exp,
            "amount": amount,
            "my_share": my_share,
            "is_yours": is_yours,
            "tag_labels": [TAG_MAP.get(t, t) for t in (exp.tags or [])],
        })
    members = trip.party.memberships.exclude(is_ai=True).all() if me.role == Membership.ROLE_ADMIN else None
    return render(request, "party/receipt.html", {
        "scope": scope,
        "target": target,
        "rows": rows,
        "total": total,
        "receipt_members": members,
    })


# ---------------------------------------------------------------- information

@login_required
def info(request):
    trip = _trip(request)
    me = _me(request, trip)
    lists = trip.task_lists.prefetch_related("items")
    pages = [p for p in trip.info_pages.all() if p.visible_to(me)]
    recipes = [p for p in pages if p.kind == InfoPage.KIND_RECIPE]
    notes = [p for p in pages if p.kind == InfoPage.KIND_NOTE]
    locations = [p for p in pages if p.kind == InfoPage.KIND_LOCATION]
    movies = [p for p in pages if p.kind == InfoPage.KIND_MOVIE]
    return render(request, "party/info.html", {
        "lists": lists,
        "recipes": recipes,
        "notes": notes,
        "locations": locations,
        "movies": movies,
        "is_staff": me.is_staff_role,
    })


@login_required
def list_new(request):
    trip = _trip(request)
    me = _me(request, trip)
    if not me.is_staff_role:
        raise Http404
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        kind = request.POST.get("kind", TaskList.KIND_TASKS)
        if not name:
            messages.error(request, "Give the list a title.")
            return redirect("list_new")
        tl = TaskList.objects.create(
            trip=trip, name=name, kind=kind, created_by=me, updated_by=me,
        )
        for i, raw in enumerate(request.POST.get("items", "").splitlines()):
            text = raw.strip()
            if text:
                TaskItem.objects.create(task_list=tl, text=text, order=i)
        if request.POST.get("announce"):
            Post.objects.create(
                trip=trip, author=me, kind=Post.KIND_BLAST,
                title=f"New list: {tl.name}",
                text="A new list just went up — check it out and pitch in.",
                internal_path=f"/info/lists/{tl.id}/",
                link_label="Open the list",
            )
        messages.success(request, f"Created “{tl.name}.”")
        return redirect("list_detail", list_id=tl.id)
    return render(request, "party/list_new.html", {"kind_choices": TaskList.KIND_CHOICES})


@login_required
def list_detail(request, list_id: int):
    trip = _trip(request)
    me = _me(request, trip)
    tl = get_object_or_404(
        TaskList.objects.prefetch_related("items__done_by", "items__updated_by"),
        pk=list_id, trip=trip,
    )
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle":
            item = get_object_or_404(TaskItem, pk=request.POST["item_id"], task_list=tl)
            item.done = not item.done
            item.done_by = me if item.done else None
            item.updated_by = me
            item.updated_at = timezone.now()
            item.save(update_fields=["done", "done_by", "updated_by", "updated_at"])
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({
                    "done": item.done,
                    "by": item.updated_by.shown_name,
                })
            return redirect("list_detail", list_id=tl.id)
        if not me.is_staff_role:
            raise Http404
        if action == "rename":
            tl.name = request.POST.get("name", tl.name).strip() or tl.name
            tl.updated_by = me
            tl.save(update_fields=["name", "updated_by", "updated_at"])
        elif action == "add_item":
            text = request.POST.get("text", "").strip()
            if text:
                TaskItem.objects.create(task_list=tl, text=text, order=tl.items.count())
                tl.updated_by = me
                tl.save(update_fields=["updated_by", "updated_at"])
        elif action == "remove_item":
            TaskItem.objects.filter(pk=request.POST.get("item_id"), task_list=tl).delete()
            tl.updated_by = me
            tl.save(update_fields=["updated_by", "updated_at"])
        elif action == "resurface":
            Post.objects.create(
                trip=trip, author=me, kind=Post.KIND_BLAST,
                title=f"Resurfacing: {tl.name}",
                text="Bumping this back up — take a look and update anything that's changed.",
                internal_path=f"/info/lists/{tl.id}/",
                link_label="Open the list",
            )
            messages.success(request, "Posted to the feed.")
        return redirect("list_detail", list_id=tl.id)
    return render(request, "party/list_detail.html", {"tl": tl, "is_staff": me.is_staff_role})


@login_required
def info_new(request):
    """Anyone can add a note; admins/mods can add lists, menu recipes, and suggestion pages."""
    trip = _trip(request)
    me = _me(request, trip)
    kind = request.GET.get("kind", InfoPage.KIND_NOTE)
    if kind != InfoPage.KIND_NOTE and not me.is_staff_role:
        raise Http404
    if request.method == "POST":
        import re
        title = request.POST.get("title", "").strip()
        kind = request.POST.get("kind", InfoPage.KIND_NOTE)
        if kind != InfoPage.KIND_NOTE and not me.is_staff_role:
            raise Http404
        if not title:
            messages.error(request, "Give it a title.")
            return redirect(f"/info/new/?kind={kind}")
        slug_base = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-") or "note"
        slug = slug_base
        n = 1
        while InfoPage.objects.filter(trip=trip, slug=slug).exists():
            n += 1
            slug = f"{slug_base}-{n}"
        page = InfoPage.objects.create(
            trip=trip, slug=slug, title=title,
            subtitle=request.POST.get("subtitle", "").strip(),
            kind=kind, body=request.POST.get("body", "").strip(),
            created_by=me, updated_by=me,
        )
        if request.POST.get("announce"):
            Post.objects.create(
                trip=trip, author=me, kind=Post.KIND_BLAST,
                title=f"New note: {page.title}",
                text="Added a new note — worth a look.",
                internal_path=f"/info/{page.slug}/",
                link_label="Read it",
            )
        messages.success(request, f"Added “{page.title}.”")
        return redirect("info_page", slug=page.slug)
    return render(request, "party/info_new.html", {
        "kind": kind, "kind_choices": InfoPage.KIND_CHOICES, "is_staff": me.is_staff_role,
    })


@login_required
def info_page(request, slug: str):
    trip = _trip(request)
    me = _me(request, trip)
    page = get_object_or_404(InfoPage, trip=trip, slug=slug)
    if not page.visible_to(me):
        raise Http404
    if request.method == "POST" and request.POST.get("action") == "resurface":
        Post.objects.create(
            trip=trip, author=me, kind=Post.KIND_BLAST,
            title=f"Resurfacing: {page.title}",
            text="Bumping this back up in case anyone missed it.",
            internal_path=f"/info/{page.slug}/",
            link_label="Read it",
        )
        messages.success(request, "Posted to the feed.")
        return redirect("info_page", slug=page.slug)
    return render(request, "party/info_page.html", {
        "page": page, "blocks": _text_blocks(page.body), "can_edit": page.visible_to(me) and me.is_staff_role,
    })


@login_required
def info_page_edit(request, slug: str):
    """Admins & moderators can edit any info page's article body, add links, etc."""
    trip = _trip(request)
    me = _me(request, trip)
    page = get_object_or_404(InfoPage, trip=trip, slug=slug)
    if not me.is_staff_role:
        raise Http404
    if request.method == "POST":
        page.title = request.POST.get("title", page.title).strip() or page.title
        page.subtitle = request.POST.get("subtitle", "").strip()
        page.body = request.POST.get("body", "").strip()
        page.link_url = request.POST.get("link_url", "").strip()
        page.link_label = request.POST.get("link_label", "").strip()
        page.updated_by = me
        page.save()
        messages.success(request, f"Updated “{page.title}.”")
        return redirect("info_page", slug=page.slug)
    return render(request, "party/info_page_edit.html", {"page": page})


@login_required
def tools(request):
    trip = _trip(request)
    _me(request, trip)
    return render(request, "party/tools.html", {})


@login_required
def picker_tool(request):
    """Random party member picker — spins client-side, optional per-person weight."""
    trip = _trip(request)
    _me(request, trip)
    members = list(trip.party.memberships.exclude(is_ai=True).select_related("user").order_by("display_name"))
    return render(request, "party/picker.html", {"members": members})


# ---------------------------------------------------------------- feed

@login_required
def feed(request):
    trip = _trip(request)
    me = _me(request, trip)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "comment":
            post = get_object_or_404(Post, pk=request.POST["post_id"], trip=trip)
            text = request.POST.get("text", "").strip()
            if text:
                Comment.objects.create(post=post, author=me, text=text)
                if post.author_id != me.id:
                    Notification.notify(
                        trip, post.author, f"{me.shown_name} commented on your post.",
                        actor=me, link_path=f"{reverse('feed')}?member={post.author_id}",
                    )
            return _redirect_feed(request, int(request.POST["post_id"]))
        if action == "announce" and me.is_staff_role:
            audience_id = request.POST.get("audience") or None
            Announcement.objects.create(
                trip=trip, author=me,
                text=request.POST["text"].strip(),
                audience_id=audience_id,
                pinned=bool(request.POST.get("pinned")),
            )
            if audience_id:
                target = get_object_or_404(Membership, pk=audience_id, party=trip.party)
                Notification.notify(trip, target, f"{me.shown_name} sent you a notice: {request.POST['text'].strip()[:80]}", actor=me, link_path=reverse("feed"))
            else:
                _notify_everyone(trip, f"Announcement: {request.POST['text'].strip()[:80]}", actor=me, link_path=reverse("feed"))
            messages.success(request, "Announcement posted.")
            return redirect("feed")
        if action in ("archive_post", "delete_post"):
            post = get_object_or_404(Post, pk=request.POST["post_id"], trip=trip)
            is_own = post.author_id == me.id
            if action == "archive_post" and (is_own or me.is_staff_role):
                post.archived = True
                post.save(update_fields=["archived"])
                messages.success(request, "Post archived.")
            elif action == "delete_post" and (is_own or me.role == Membership.ROLE_ADMIN):
                post.delete()
                messages.success(request, "Post deleted.")
            return _redirect_feed(request)
        if action == "set_poll_stage":
            post = get_object_or_404(Post, pk=request.POST["post_id"], trip=trip)
            if post.poll and (me.role == Membership.ROLE_ADMIN or post.poll.author_id == me.id):
                new_stage = request.POST.get("stage", "")
                if new_stage in (Poll.STAGE_SUGGEST, Poll.STAGE_VOTE, Poll.STAGE_CLOSED):
                    post.poll.stage = new_stage
                    post.poll.save(update_fields=["stage"])
            return _redirect_feed(request, post.id)

    posts = trip.posts.filter(archived=False).select_related("author", "poll").prefetch_related(
        "comments__author", "extra_images", "videos", "poll__options__votes", "reactions",
    )
    member_filter = request.GET.get("member")
    filtered_member = None
    if member_filter:
        from django.db.models import Q
        filtered_member = get_object_or_404(Membership, pk=member_filter, party=trip.party)
        # Show their own posts *and* posts they've weighed in on, so a profile
        # view surfaces the full trail of what they've said, not just what they authored.
        posts = posts.filter(Q(author=filtered_member) | Q(comments__author=filtered_member)).distinct()
    kind = request.GET.get("kind", "")
    if kind in dict(Post.KIND_CHOICES):
        posts = posts.filter(kind=kind)

    member_count = trip.party.memberships.exclude(is_ai=True).count()
    palette = ["#2f7d4f", "#c47a3d", "#3f7fbf", "#7a5fa0", "#b0533b", "#4d8f8b", "#c9a441", "#5d7f35"]
    posts = list(posts)
    for post in posts:
        all_reactions = list(post.reactions.all())
        post.my_reaction_set = {r.emoji for r in all_reactions if r.member_id == me.id}
        counts: dict[str, int] = {}
        for r in all_reactions:
            counts[r.emoji] = counts.get(r.emoji, 0) + 1
        post.reaction_counts = counts
        if post.poll_id:
            voter_ids = post.poll.voter_ids()
            post.poll_total_members = member_count
            post.poll_voted_count = len(voter_ids)
            post.poll_i_voted = me.id in voter_ids
            # Inline options preview for voting stage
            if post.poll.stage in (Poll.STAGE_VOTE, Poll.STAGE_CLOSED):
                total = post.poll.total_votes()
                post.poll_preview_options = [
                    {
                        "text": opt.text,
                        "count": opt.votes.count(),
                        "pct": int(opt.votes.count() / total * 100) if total else 0,
                        "color": palette[i % len(palette)],
                    }
                    for i, opt in enumerate(post.poll.options.all()[:5])
                ]
            else:
                post.poll_preview_options = []
        post.can_archive = post.author_id == me.id or me.is_staff_role
        post.can_delete = post.author_id == me.id or me.role == Membership.ROLE_ADMIN
        post.highlight_author = bool(filtered_member and post.author_id == filtered_member.id)
        if filtered_member:
            for c in post.comments.all():
                c.is_highlighted = c.author_id == filtered_member.id

    members = trip.party.memberships.exclude(is_ai=True).all()
    return render(request, "party/feed.html", {
        "posts": posts,
        "members": members,
        "filtered_member": filtered_member,
        "active_kind": kind,
        "reaction_choices": PostReaction.EMOJI_CHOICES,
    })


@login_required
def feed_new(request):
    """Create a post (multi-image, link button, bg color) or a poll."""
    trip = _trip(request)
    me = _me(request, trip)

    if request.method == "POST":
        what = request.POST.get("what", "post")
        if what == "poll":
            two_stage = bool(request.POST.get("two_stage"))
            close_mode = request.POST.get("close_mode", "trip_end")
            closes_at = None
            if close_mode == "hour":
                closes_at = timezone.now() + dt.timedelta(hours=1)
            elif close_mode == "custom":
                raw = request.POST.get("closes_at", "")
                try:
                    closes_at = dt.datetime.fromisoformat(raw)
                except ValueError:
                    closes_at = None
            elif close_mode == "trip_end":
                closes_at = trip.default_poll_close
            poll = Poll.objects.create(
                trip=trip, author=me,
                question=request.POST["question"].strip(),
                anonymous=bool(request.POST.get("anonymous")),
                multiple_choice=bool(request.POST.get("multiple_choice")),
                two_stage=two_stage,
                stage=Poll.STAGE_SUGGEST if two_stage else Poll.STAGE_VOTE,
                closes_at=closes_at,
            )
            for i, raw in enumerate(request.POST.get("options", "").splitlines()):
                text = raw.strip()
                if text:
                    PollOption.objects.create(poll=poll, text=text, order=i, suggested_by=me)
            Post.objects.create(
                trip=trip, author=me, kind=Post.KIND_POLL,
                title=poll.question, poll=poll,
                bg_color=request.POST.get("bg_color", ""),
            )
            messages.success(request, "Poll posted to the feed.")
            return redirect("poll_detail", poll_id=poll.id)

        event = None
        new_event_name = request.POST.get("new_event_name", "").strip()
        if new_event_name:
            event = Event.objects.create(trip=trip, name=new_event_name, created_by=me)
        elif request.POST.get("event_id"):
            event = Event.objects.filter(trip=trip, pk=request.POST["event_id"]).first()

        post = Post.objects.create(
            trip=trip, author=me,
            kind=request.POST.get("kind", Post.KIND_BLAST),
            title=request.POST.get("title", "").strip(),
            text=request.POST.get("text", "").strip(),
            image=request.FILES.get("image"),
            link_url=request.POST.get("link_url", "").strip(),
            link_label=request.POST.get("link_label", "").strip() or "Open link",
            bg_color=request.POST.get("bg_color", ""),
            suggested_by_note=request.POST.get("suggested_by_note", "").strip(),
            event=event,
        )
        for f in request.FILES.getlist("more_images")[:8]:
            PostImage.objects.create(post=post, image=f)
        for i, f in enumerate(request.FILES.getlist("videos")[:3]):
            PostVideo.objects.create(post=post, video=f, order=i)
        if post.videos.exists() and post.kind == Post.KIND_BLAST:
            post.kind = Post.KIND_PHOTO
            post.save(update_fields=["kind"])
        messages.success(request, "Posted to the feed.")
        return redirect(f"{reverse('feed')}#post-{post.id}")

    return render(request, "party/feed_new.html", {
        "kind_choices": [k for k in Post.KIND_CHOICES if k[0] != Post.KIND_POLL],
        "bg_choices": Post.BG_CHOICES,
        "trip": trip,
        "events": trip.events.all(),
    })


@login_required
def react(request):
    """Toggle an emoji reaction on a post (AJAX-friendly)."""
    trip = _trip(request)
    me = _me(request, trip)
    if request.method != "POST":
        raise Http404
    post = get_object_or_404(Post, pk=request.POST.get("post_id"), trip=trip)
    emoji = request.POST.get("emoji", "")
    if emoji not in dict(PostReaction.EMOJI_CHOICES):
        raise Http404
    existing = PostReaction.objects.filter(post=post, member=me, emoji=emoji).first()
    if existing:
        existing.delete()
        mine = False
    else:
        PostReaction.objects.create(post=post, member=me, emoji=emoji)
        mine = True
        if post.author_id != me.id:
            Notification.notify(
                trip, post.author, f"{me.shown_name} reacted {emoji} to your post.",
                actor=me, link_path=f"{reverse('feed')}?member={post.author_id}",
            )
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "mine": mine,
            "emoji": emoji,
            "summary": post.reaction_summary(),
        })
    return _redirect_feed(request, post.id)


@login_required
def photos(request):
    """Live photo & video wall: every media posted, newest first."""
    trip = _trip(request)
    _me(request, trip)
    posts = trip.posts.filter(archived=False).select_related("author", "event").prefetch_related(
        "extra_images", "videos",
    )
    event_filter = request.GET.get("event")
    filtered_event = None
    if event_filter:
        filtered_event = get_object_or_404(Event, pk=event_filter, trip=trip)
        posts = posts.filter(event=filtered_event)
    entries = []
    for post in posts:
        for item in post.all_media():
            entries.append({"post": post, **item})
    entries.sort(key=lambda e: e["post"].created_at, reverse=True)
    return render(request, "party/photos.html", {
        "entries": entries,
        "events": trip.events.all(),
        "filtered_event": filtered_event,
    })


@login_required
def events_list(request):
    """Admin/mod-managed list of named happenings that photos/videos tag into."""
    trip = _trip(request)
    me = _me(request, trip)
    if request.method == "POST" and me.is_staff_role:
        name = request.POST.get("name", "").strip()
        if name:
            raw_date = request.POST.get("date", "")
            event_date = None
            if raw_date:
                try:
                    event_date = dt.date.fromisoformat(raw_date)
                except ValueError:
                    event_date = None
            Event.objects.create(trip=trip, name=name, date=event_date, created_by=me)
            messages.success(request, f"Created event “{name}.”")
        return redirect("events_list")
    rows = []
    for ev in trip.events.all():
        count = sum(len(p.all_media()) for p in ev.posts.filter(archived=False).prefetch_related("extra_images", "videos"))
        rows.append({"event": ev, "media_count": count})
    return render(request, "party/events.html", {"rows": rows, "is_staff": me.is_staff_role})


@login_required
def poll_detail(request, poll_id: int):
    trip = _trip(request)
    me = _me(request, trip)
    poll = get_object_or_404(
        Poll.objects.prefetch_related("options__votes__member", "options__suggested_by"),
        pk=poll_id, trip=trip,
    )

    if poll.is_expired and poll.stage != Poll.STAGE_CLOSED:
        poll.stage = Poll.STAGE_CLOSED
        poll.save(update_fields=["stage"])

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "vote" and poll.stage == Poll.STAGE_VOTE:
            option = get_object_or_404(PollOption, pk=request.POST["option_id"], poll=poll)
            if poll.two_stage and option.suggested_by_id == me.id:
                messages.error(request, "You can't vote for your own suggestion.")
                return redirect("poll_detail", poll_id=poll.id)
            if not poll.multiple_choice:
                Vote.objects.filter(option__poll=poll, member=me).delete()
            Vote.objects.get_or_create(option=option, member=me)
        elif action == "suggest" and poll.stage == Poll.STAGE_SUGGEST:
            text = request.POST.get("text", "").strip()
            if text:
                PollOption.objects.create(
                    poll=poll, text=text, suggested_by=me,
                    order=poll.options.count(),
                )
                messages.success(request, "Suggestion added.")
        elif action == "advance" and (me.id == poll.author_id or me.is_staff_role):
            if poll.stage == Poll.STAGE_SUGGEST:
                poll.stage = Poll.STAGE_VOTE
            elif poll.stage == Poll.STAGE_VOTE:
                poll.stage = Poll.STAGE_CLOSED
            poll.save(update_fields=["stage"])
        return redirect("poll_detail", poll_id=poll.id)

    total = poll.total_votes()
    my_votes = set(Vote.objects.filter(option__poll=poll, member=me).values_list("option_id", flat=True))
    palette = ["#2f7d4f", "#c47a3d", "#3f7fbf", "#7a5fa0", "#b0533b", "#4d8f8b", "#c9a441", "#5d7f35"]
    options = []
    for i, opt in enumerate(poll.options.all()):
        votes = list(opt.votes.all())
        options.append({
            "opt": opt,
            "count": len(votes),
            "pct": int(len(votes) / total * 100) if total else 0,
            "voters": None if poll.anonymous else [v.member for v in votes],
            "mine": opt.id in my_votes,
            "own_suggestion": poll.two_stage and opt.suggested_by_id == me.id,
            "color": palette[i % len(palette)],
        })

    members_voted = members_total = None
    not_voted = []
    if not poll.anonymous and poll.stage != Poll.STAGE_SUGGEST:
        all_members = list(trip.party.memberships.exclude(is_ai=True).all())
        voter_ids = poll.voter_ids()
        members_total = len(all_members)
        members_voted = len(voter_ids)
        not_voted = [m for m in all_members if m.id not in voter_ids][:6]

    feed_post = Post.objects.filter(trip=trip, poll=poll).first()

    return render(request, "party/poll_detail.html", {
        "poll": poll,
        "feed_post": feed_post,
        "options": options,
        "total": total,
        "can_advance": me.id == poll.author_id or me.is_staff_role,
        "members_voted": members_voted,
        "members_total": members_total,
        "not_voted": not_voted,
    })


# ---------------------------------------------------------------- party & prefs

@login_required
def party(request):
    trip = _trip(request)
    me = _me(request, trip)

    if request.method == "POST" and me.role == Membership.ROLE_ADMIN:
        action = request.POST.get("action")
        if action == "set_role":
            target = get_object_or_404(Membership, pk=request.POST["member_id"], party=trip.party)
            new_role = request.POST.get("role", "")
            # Admin can only promote/demote to moderator or member — can't touch themselves
            # or other admins, and can't grant admin status via this UI.
            if (target.pk != me.pk
                    and target.role != Membership.ROLE_ADMIN
                    and new_role in (Membership.ROLE_MODERATOR, Membership.ROLE_MEMBER)):
                target.role = new_role
                target.save(update_fields=["role"])
                Notification.notify(trip, target, f"You're now a {target.get_role_display()}.", actor=me, link_path=reverse("party"))
                messages.success(request, f"{target.shown_name} is now {target.get_role_display()}.")
        return redirect("party")

    att = {a.member_id: a for a in trip.attendances.all()}
    day_count = max((trip.end_date - trip.start_date).days + 1, 1)
    rows = []
    for m in trip.party.memberships.exclude(is_ai=True).select_related("user", "plus_one_of").order_by("role", "display_name"):
        a = att.get(m.id)
        arrive = (a.arrive if a and a.arrive else trip.start_date)
        depart = (a.depart if a and a.depart else trip.end_date)
        start_idx = max((arrive - trip.start_date).days, 0)
        end_idx = min((depart - trip.start_date).days, day_count - 1)
        rows.append({
            "m": m,
            "arrive": arrive,
            "depart": depart,
            "start_pct": int(start_idx / day_count * 100),
            "width_pct": int((end_idx - start_idx + 1) / day_count * 100),
            "travel_note": m.travel_note if m.can_see_travel_note(me) else "",
        })
    return render(request, "party/party.html", {"rows": rows, "is_admin": me.role == Membership.ROLE_ADMIN})


@login_required
def settings_page(request):
    trip = _trip(request)
    me = _me(request, trip)
    profile = _profile(request)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "identity":
            icon = request.POST.get("icon", "")
            color = request.POST.get("color", "")
            if icon in dict(ICON_CHOICES):
                me.icon = icon
            if color in dict(COLOR_CHOICES):
                me.color = color
            me.save(update_fields=["icon", "color"])
            profile.icon_prompt_done = True
            profile.save(update_fields=["icon_prompt_done"])
            messages.success(request, "Your trail icon is set.")
            return redirect("home")
        if action == "sounds":
            profile.sounds_on = bool(request.POST.get("sounds_on"))
            profile.save(update_fields=["sounds_on"])
            messages.success(request, "Sound preference saved.")
            return redirect("settings")
        if action == "name":
            name = request.POST.get("display_name", "").strip()
            nickname = request.POST.get("nickname", "").strip()
            if name:
                me.display_name = name[:80]
            me.nickname = nickname[:60]
            me.save(update_fields=["display_name", "nickname"])
            messages.success(request, "Your trail identity is updated.")
            return redirect("settings")
        if action == "reset_primary":
            profile.primary_trip = None
            profile.primary_prompt_answered = False
            profile.save(update_fields=["primary_trip", "primary_prompt_answered"])
            messages.success(request, "Primary trip cleared — you'll see the trips screen again.")
            return redirect("trips_home")

    taken = {
        m.icon: m.display_name
        for m in trip.party.memberships.exclude(is_ai=True).exclude(pk=me.pk).exclude(icon="")
    }
    return render(request, "party/settings.html", {
        "profile": profile,
        "icon_choices": ICON_CHOICES,
        "color_choices": COLOR_CHOICES,
        "taken_icons": taken,
        "needs_icon": not profile.icon_prompt_done or not me.icon,
    })
