"""Expense-split algorithms (Rec 42-new + houseing.txt).

Every algorithm returns {membership_id: Decimal amount} and a
plain-language description string that members see.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .models import Attendance, Expense, Membership, Trip

CENT = Decimal("0.01")


def _spread(total: Decimal, weights: dict[int, Decimal]) -> dict[int, Decimal]:
    """Distribute `total` across ids proportionally to weights, cent-exact."""
    wsum = sum(weights.values())
    if not wsum:
        return {mid: Decimal("0.00") for mid in weights}
    out: dict[int, Decimal] = {}
    running = Decimal("0.00")
    ids = list(weights)
    for mid in ids[:-1]:
        share = (total * weights[mid] / wsum).quantize(CENT, rounding=ROUND_HALF_UP)
        out[mid] = share
        running += share
    out[ids[-1]] = (total - running).quantize(CENT)
    return out


def split_equal(expense: Expense, members: list[Membership]) -> tuple[dict[int, Decimal], str]:
    weights = {m.id: Decimal(1) for m in members}
    return _spread(expense.amount, weights), (
        f"Split equally between {len(members)} people."
    )


def split_by_nights(expense: Expense, members: list[Membership]) -> tuple[dict[int, Decimal], str]:
    trip = expense.trip
    att = {a.member_id: a for a in Attendance.objects.filter(trip=trip)}
    total_nights = max((trip.end_date - trip.start_date).days, 1)
    weights = {}
    for m in members:
        a = att.get(m.id)
        nights = a.nights() if a else total_nights
        weights[m.id] = Decimal(max(nights, 0))
    return _spread(expense.amount, weights), (
        "Split proportionally by nights present — people staying fewer "
        "nights pay less."
    )


def split_adjustments(expense: Expense, members: list[Membership],
                      adjustments: dict[int, Decimal] | None = None) -> tuple[dict[int, Decimal], str]:
    """Equal baseline among included people, plus per-person +/- adjustments."""
    adjustments = adjustments or {}
    n = len(members)
    if not n:
        return {}, "No one included on this expense."
    baseline = (expense.amount / Decimal(n)).quantize(CENT, rounding=ROUND_HALF_UP)
    ids = [m.id for m in members]
    out: dict[int, Decimal] = {}
    running = Decimal("0")
    for mid in ids[:-1]:
        share = (baseline + adjustments.get(mid, Decimal("0"))).quantize(CENT, rounding=ROUND_HALF_UP)
        out[mid] = share
        running += share
    out[ids[-1]] = (expense.amount - running).quantize(CENT)
    return out, (
        f"Split equally (${baseline} baseline) among {n} people, with per-person "
        "adjustments (+/− from that baseline)."
    )


def split_percent(expense: Expense, members: list[Membership],
                  percents: dict[int, Decimal] | None = None) -> tuple[dict[int, Decimal], str]:
    """Split by member percentages (must sum to ~100)."""
    percents = percents or {}
    weights = {m.id: percents.get(m.id, Decimal("0")) for m in members}
    if not sum(weights.values()):
        return split_equal(expense, members)
    return _spread(expense.amount, weights), "Split by percentages set when the expense was added."


def split_shares(expense: Expense, members: list[Membership],
                 shares: dict[int, Decimal] | None = None) -> tuple[dict[int, Decimal], str]:
    """Split by share counts (e.g. couples take 2 shares)."""
    shares = shares or {}
    weights = {m.id: shares.get(m.id, Decimal("0")) for m in members}
    if not sum(weights.values()):
        return split_equal(expense, members)
    return _spread(expense.amount, weights), "Split by shares — more shares, bigger slice."


def split_custom(expense: Expense, members: list[Membership],
                 amounts: dict[int, Decimal] | None = None) -> tuple[dict[int, Decimal], str]:
    """Exact amounts per member; any remainder spreads equally."""
    amounts = amounts or {}
    out = {m.id: amounts.get(m.id, Decimal("0")).quantize(CENT) for m in members}
    assigned = sum(out.values())
    remainder = expense.amount - assigned
    if remainder and members:
        spread = _spread(remainder, {m.id: Decimal(1) for m in members})
        for mid, extra in spread.items():
            out[mid] += extra
        return out, "Exact amounts entered, with the remainder split equally."
    return out, "Exact amounts entered for each person."


ALGORITHMS = {
    Expense.SPLIT_EQUAL: split_equal,
    Expense.SPLIT_PRESENT: split_by_nights,
}


def preview_split(expense: Expense, members: list[Membership], method: str,
                  detail: dict[int, Decimal] | None = None):
    """Compute shares. `detail` carries per-member numbers for
    percent / shares / custom / adjust methods."""
    if method == "rooms":
        method = Expense.SPLIT_EQUAL
    if method == Expense.SPLIT_PERCENT:
        return split_percent(expense, members, detail)
    if method == Expense.SPLIT_SHARES:
        return split_shares(expense, members, detail)
    if method == Expense.SPLIT_CUSTOM:
        return split_custom(expense, members, detail)
    if method == Expense.SPLIT_ADJUST:
        return split_adjustments(expense, members, detail)
    fn = ALGORITHMS.get(method, split_equal)
    return fn(expense, members)


def simplify_debts(balances: dict[int, Decimal]) -> list[tuple[int, int, Decimal]]:
    """Min-cash-flow style settlement plan.

    Returns [(from_member_id, to_member_id, amount), ...] such that paying
    these clears every balance with the fewest practical transfers.
    """
    debtors = [[mid, -bal] for mid, bal in balances.items() if bal < -CENT]
    creditors = [[mid, bal] for mid, bal in balances.items() if bal > CENT]
    debtors.sort(key=lambda x: x[1], reverse=True)
    creditors.sort(key=lambda x: x[1], reverse=True)
    plan: list[tuple[int, int, Decimal]] = []
    di = ci = 0
    while di < len(debtors) and ci < len(creditors):
        owe = debtors[di][1]
        get = creditors[ci][1]
        amt = min(owe, get).quantize(CENT)
        if amt > 0:
            plan.append((debtors[di][0], creditors[ci][0], amt))
        debtors[di][1] -= amt
        creditors[ci][1] -= amt
        if debtors[di][1] <= CENT:
            di += 1
        if creditors[ci][1] <= CENT:
            ci += 1
    return plan


def raw_pairwise_debts(trip: Trip) -> list[tuple[int, int, Decimal]]:
    """Directional debts from each expense share (no cross-netting).

    If A owes B $10 and B owes A $5, both edges stay visible — unlike simplify_debts.
    Confirmed settlements reduce the matching from→to edge.
    """
    edges: dict[tuple[int, int], Decimal] = {}
    for exp in trip.expenses.prefetch_related("shares"):
        for share in exp.shares.all():
            if share.excluded or share.member_id == exp.payer_id:
                continue
            key = (share.member_id, exp.payer_id)
            edges[key] = edges.get(key, Decimal("0")) + share.amount
    for s in trip.settlements.filter(status="confirmed"):
        key = (s.from_member_id, s.to_member_id)
        if key not in edges:
            continue
        edges[key] -= s.amount
        if edges[key] <= CENT:
            del edges[key]
    rows = [(f, t, amt.quantize(CENT)) for (f, t), amt in edges.items() if amt > CENT]
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows


PIE_PALETTE = [
    "#2f7d4f", "#c47a3d", "#3f7fbf", "#7a5fa0", "#b0533b",
    "#4d8f8b", "#c9a441", "#5d7f35", "#a83a2a", "#7a2e35",
]


def tag_totals(trip: Trip) -> list[dict]:
    """Spending grouped by tag for the budget chart (with pie-chart slice data)."""
    totals: dict[str, Decimal] = {}
    for exp in trip.expenses.all():
        tags = exp.tags or ["misc"]
        share = exp.amount / Decimal(len(tags))
        for t in tags:
            totals[t] = totals.get(t, Decimal("0")) + share
    label_map = dict(Expense.TAG_CHOICES)
    grand = sum(totals.values()) or Decimal("1")
    rows = [
        {"tag": t, "label": label_map.get(t, t.title()), "amount": amt.quantize(CENT),
         "pct": int(amt / grand * 100)}
        for t, amt in totals.items()
    ]
    rows.sort(key=lambda r: r["amount"], reverse=True)
    cursor = 0.0
    for i, r in enumerate(rows):
        r["color"] = PIE_PALETTE[i % len(PIE_PALETTE)]
        r["pie_start"] = round(cursor, 2)
        cursor += float(r["amount"]) / float(grand) * 100
        r["pie_end"] = round(cursor, 2)
    if rows:
        rows[-1]["pie_end"] = 100
    return rows


def member_owe_explanations(trip: Trip, member_id: int) -> dict:
    """Who a member owes, with itemized share lines and a simplified settlement plan."""
    balances = member_balances(trip)
    members = {m.id: m for m in trip.party.memberships.exclude(is_ai=True)}

    share_lines: dict[int, list[dict]] = {}
    for exp in trip.expenses.prefetch_related("shares"):
        if exp.payer_id == member_id:
            continue
        share = next(
            (s for s in exp.shares.all() if s.member_id == member_id and not s.excluded),
            None,
        )
        if share and share.amount > CENT:
            share_lines.setdefault(exp.payer_id, []).append({
                "title": exp.title,
                "amount": share.amount,
            })

    itemized = []
    for payer_id, lines in share_lines.items():
        total = sum((ln["amount"] for ln in lines), Decimal("0")).quantize(CENT)
        itemized.append({
            "to_member": members[payer_id],
            "amount": total,
            "lines": lines,
        })
    itemized.sort(key=lambda r: r["amount"], reverse=True)

    if trip.simplify_debts:
        plan_src = simplify_debts(balances)
    else:
        plan_src = raw_pairwise_debts(trip)
    simplified = [
        {"to_member": members[to_id], "amount": amt}
        for from_id, to_id, amt in plan_src
        if from_id == member_id
    ]

    return {
        "itemized": itemized,
        "simplified": simplified,
        "my_balance": balances.get(member_id, Decimal("0")),
        "use_simplify": trip.simplify_debts,
    }


def member_balances(trip: Trip) -> dict[int, Decimal]:
    """Net balance per member: positive = is owed money, negative = owes."""
    balances: dict[int, Decimal] = {}
    for exp in trip.expenses.prefetch_related("shares"):
        balances.setdefault(exp.payer_id, Decimal("0"))
        balances[exp.payer_id] += exp.amount
        for share in exp.shares.all():
            if share.excluded:
                continue
            balances.setdefault(share.member_id, Decimal("0"))
            balances[share.member_id] -= share.amount
    for s in trip.settlements.filter(status="confirmed"):
        balances.setdefault(s.from_member_id, Decimal("0"))
        balances.setdefault(s.to_member_id, Decimal("0"))
        balances[s.from_member_id] += s.amount
        balances[s.to_member_id] -= s.amount
    return balances
