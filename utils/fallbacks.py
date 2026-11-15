"""Deterministic, data-driven fallbacks used when the AI service isn't available.

utils/generate_data.py writes these to data/sample_brief.md and data/sample_answers.json,
so the cached outputs always match the CSVs they were generated alongside.
"""
from __future__ import annotations

from datetime import timedelta

from utils import data

SUGGESTED_QUESTIONS = [
    "What's at risk for the Board meeting?",
    "Which owners have the most overdue actions?",
    "How much of the CEO's time is with customers this week?",
    "Are we ready for the Christmas party?",
]


def _d(d) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def build_sample_brief() -> str:
    t = data.today()
    board = data.next_board_date()
    pack = data.board_pack_rag()
    red_pack = pack[pack["rag"] == "Red"]
    not_started = pack[(pack["status"] == "Not started") & (pack["rag"] != "Red")]
    overdue = data.overdue_actions()
    long_overdue = overdue[(t - overdue["due_date"]).apply(lambda x: x.days) > 14]
    hs = data.hs_rag()
    hs_red = hs[hs["rag"] == "Red"]
    tickets = data.tickets_view()
    repeats = tickets[(tickets["status"] != "Resolved") & tickets["repeat_issue"]]
    mon, sun = data.week_bounds()
    split = data.time_split(mon, sun).set_index("category")
    cust = split.loc["Customer"]
    flags = data.calendar_flags(mon, sun)
    conflicts = flags[flags["flag"] == "Conflict"]
    no_agenda = flags[(flags["flag"] == "No agenda")]
    pack_deadline = board - timedelta(days=data.RAG_WINDOW_DAYS)
    ev = data.upcoming_events()
    headline_events = ev[(ev["pending_share"] > data.RSVP_PENDING_SHARE)
                         & (ev["days_to_rsvp_deadline"] <= data.RSVP_WINDOW_DAYS)]
    visits = data.visits_view()
    visits_soon = visits[visits["days_to_visit"].between(0, data.VISIT_WINDOW_DAYS) & (visits["readiness"] < 1)]
    sup = data.suppliers_view()
    trips = data.travel_view()
    trips_soon = trips[trips["days_to_trip"].between(0, data.TRAVEL_WINDOW_DAYS) & (trips["readiness"] < 1)]
    ending = sup[sup["contract_ending"]].sort_values("contract_end")
    spend = sup["monthly_cost_gbp"].sum()

    lines = [
        f"# CEO Weekly Brief — week of {_d(mon)}",
        f"*Prepared by Business Operations · {_d(t)}*",
        "",
        "## Headline",
        f"Board is in **{(board - t).days} days** ({_d(board)}). The pack is {len(pack) - len(pack[~pack['status'].isin(data.DONE_PACK)])}"
        f"/{len(pack)} in, with **{len(red_pack)} sections overdue**. {len(overdue)} actions are past due and "
        f"customer time is **{cust.actual:.0%}** against a {cust.target:.0%} target.",
        "",
        "## Red flags",
    ]
    for r in red_pack.itertuples():
        lines.append(f"- **Board pack:** {r.section} ({r.owner}) is {data._days(-r.days_to_due)} late, status {r.status.lower()}.")
    if len(not_started):
        lines.append(f"- **Board pack:** {', '.join(not_started['section'])} not yet started; pack closes {_d(pack_deadline)}.")
    for r in long_overdue.itertuples():
        lines.append(f"- **Action:** {r.action} ({r.owner}, {r.source}) — {(t - r.due_date).days} days overdue.")
    for r in hs_red.itertuples():
        lines.append(f"- **Health & safety:** {r.check} overdue by {data._days(-r.days_until_due)} ({r.owner}).")
    if len(repeats):
        lines.append(f"- **Office:** {len(repeats)} repeat facilities issues, worst is "
                     f"{repeats.sort_values('repeat_count').iloc[-1]['issue'].lower()} "
                     f"(reported {repeats['repeat_count'].max()}×).")
    for r in trips_soon.itertuples():
        lines.append(f"- **Travel:** {r.trip} ({_d(r.start_date)}) is {r.readiness:.0%} ready — missing {r.missing}.")
    for r in headline_events.itertuples():
        lines.append(f"- **Events:** {r.event} ({_d(r.date)}) — {r.rsvp_pending} of {r.invited} RSVPs pending, "
                     f"deadline {_d(r.rsvp_deadline)}; final numbers due to the venue {_d(r.final_numbers_due)}; "
                     f"{r.budget_used:.0%} of £{r.budget_gbp:,.0f} budget committed.")
    if len(visits_soon):
        lines.append("- **Visitors:** " + "; ".join(
            f"{r.visitor_org} ({_d(r.date)}) is {r.readiness:.0%} ready, missing {r.missing}"
            for r in visits_soon.itertuples()) + ".")
    if len(ending):
        lines.append("- **Suppliers:** " + "; ".join(
            f"{r.supplier} ({r.service.lower()}) contract ends {_d(r.contract_end)}" for r in ending.itertuples())
            + f". Office running costs are £{spend:,.0f}/month vs £{data.OFFICE_MONTHLY_BUDGET:,.0f} budget.")

    lines += ["", "## Decisions needed"]
    if len(red_pack):
        lines.append(f"- Extend the deadline for {' and '.join(red_pack['owner'])} to {_d(pack_deadline)}, "
                     "or ask them for a holding paper now?")
    for r in conflicts.itertuples():
        lines.append(f"- {_d(r.date)}: **{r.meeting}** clashes with {r.detail.removeprefix('Overlaps ')} — which one moves?")
    if cust.actual < cust.target:
        lines.append(f"- Customer time is {cust.actual:.0%} vs {cust.target:.0%}: swap one internal meeting next week "
                     "for a customer visit?")
    if len(hs_red):
        lines.append("- Approve booking overdue H&S items this week (first-aid training, fire alarm test, risk assessment).")
    for r in headline_events[headline_events["budget_used"] > data.BUDGET_ALERT_SHARE].itertuples():
        lines.append(f"- {r.event} is {r.budget_used:.0%} committed with {r.rsvp_pending} RSVPs pending — "
                     "cap numbers at the current budget, or approve a contingency?")
    if len(ending):
        lines.append(f"- Renew or re-tender {' and '.join(ending['supplier'])} before "
                     f"{'their contracts end' if len(ending) > 1 else 'the contract ends'}?")

    lines += ["", "## Week ahead"]
    days: dict = {}
    cal = data.calendar_between(t, sun)
    for day, rows in cal.groupby("date"):
        key = rows[rows["category"].isin({"Customer", "Investor", "Travel"}) | rows["title"].str.contains("Board")]
        days.setdefault(day, []).extend(f"{r.start} {r.title}" for r in key.itertuples())
    for r in visits[(visits["date"] >= t) & (visits["date"] <= sun)].itertuples():
        days.setdefault(r.date, []).append(f"{r.time} visitor: {r.visitor_org} ({r.purpose})")
    for r in ev[ev["date"] <= sun].itertuples():
        days.setdefault(r.date, []).append(f"{r.event}")
    for day in sorted(days):
        if days[day]:
            lines.append(f"- **{_d(day)}:** {'; '.join(sorted(days[day], key=lambda x: x[:5] if x[2:3] == ':' else '99'))}")
    if len(no_agenda):
        lines.append(f"- {len(no_agenda)} meetings this week still have no agenda — Business Operations is chasing.")
    return "\n".join(lines) + "\n"


def build_canned_answers() -> dict[str, str]:
    t = data.today()
    board = data.next_board_date()
    pack = data.board_pack_rag()
    outstanding = pack[pack["rag"] != "Green"].sort_values("due_date")
    board_actions = data.overdue_actions()
    board_actions = board_actions[board_actions["source"] == "Board"]

    risk = [f"The Board is on {_d(board)} ({(board - t).days} days away). "
            f"{len(outstanding)} of {len(pack)} pack sections are still outstanding:"]
    for r in outstanding.itertuples():
        state = f"{data._days(-r.days_to_due)} late" if r.days_to_due < 0 else f"due {_d(r.due_date)}"
        risk.append(f"- **{r.section}** ({r.owner}) — {r.status.lower()}, {state} · {r.rag}")
    if len(board_actions):
        risk.append(f"\nThere are also {len(board_actions)} overdue actions from the last Board, which members "
                    "are likely to ask about:")
        risk += [f"- {r.action} ({r.owner}, {(t - r.due_date).days} days overdue)" for r in board_actions.itertuples()]

    od = data.overdue_actions()
    by_owner = od.groupby("owner").size().sort_values(ascending=False)
    owners = [f"{len(od)} actions are overdue across {len(by_owner)} owners:"]
    for owner, n in by_owner.items():
        items = od[od["owner"] == owner]
        worst = (t - items["due_date"].min()).days
        owners.append(f"- **{owner}** — {n} overdue (oldest {data._days(worst)}): "
                      + "; ".join(items["action"]))

    mon, sun = data.week_bounds()
    split = data.time_split(mon, sun).set_index("category")
    cust = split.loc["Customer"]
    total = split["hours"].sum()
    cust_meetings = data.calendar_between(mon, sun)
    cust_meetings = cust_meetings[cust_meetings["category"] == "Customer"]
    time = [f"**{cust.actual:.0%}** of the CEO's booked time this week ({cust.hours:g} of {total:g} hours, "
            f"excluding travel) is with customers — {abs(cust.actual - cust.target) * 100:.0f} points "
            f"{'below' if cust.actual < cust.target else 'above'} the {cust.target:.0%} target. "
            f"Internal meetings take the biggest share at {split.loc['Internal', 'actual']:.0%}.",
            "", "Customer meetings this week:"]
    time += [f"- {_d(r.date)} {r.start} — {r.title}" for r in cust_meetings.itertuples()]

    ev = data.events_view()
    xmas = ev[ev["type"] == "Christmas party"].sort_values("date").iloc[-1]
    diet = data.load_event_dietary()
    diet = diet[(diet["event"] == xmas["event"]) & (diet["count"] > 0)]
    cl = data.checklist_view()
    cl = cl[cl["event"] == xmas["event"]]
    late = cl[cl["overdue"]]
    party = [f"Mostly, but the next five days matter. **{xmas['event']}** is on {_d(xmas['date'])} at "
             f"{xmas['venue']} ({xmas['days_to_event']} days away).",
             f"- **RSVPs:** {xmas['rsvp_yes']} yes, {xmas['rsvp_no']} no, **{xmas['rsvp_pending']} pending** "
             f"({xmas['pending_share']:.0%} of {xmas['invited']}) — deadline {_d(xmas['rsvp_deadline'])}",
             f"- **Final numbers** due to the venue {_d(xmas['final_numbers_due'])}",
             f"- **Budget:** £{xmas['committed_gbp']:,.0f} of £{xmas['budget_gbp']:,.0f} committed "
             f"({xmas['budget_used']:.0%}), about £{xmas['cost_per_head']:,.0f} per confirmed guest",
             f"- **Checklist:** {xmas['tasks_done']} of {xmas['tasks']} tasks done"
             + (f"; overdue: {', '.join(late['task'])}" if len(late) else ""),
             "- **Dietary:** " + ", ".join(f"{r.requirement.lower()} {r.count}" for r in diet.itertuples())]

    return dict(zip(SUGGESTED_QUESTIONS, ["\n".join(risk), "\n".join(owners), "\n".join(time), "\n".join(party)]))


def rsvp_template(event: str) -> dict[str, str]:
    r = data.events_view().set_index("event").loc[event]
    body = (
        "Hi all,\n\n"
        f"A friendly reminder that {event} is on {_d(r['date'])} at {r['venue']}, and we'd love to know "
        f"if you can make it. If you haven't replied yet, please RSVP by {_d(r['rsvp_deadline'])} — "
        f"the venue needs our final numbers on {_d(r['final_numbers_due'])}.\n\n"
        "A quick yes or no either way really helps, and please let us know about any dietary or "
        "accessibility needs when you reply.\n\n"
        "Thanks,\nBusiness Operations"
    )
    return {"subject": f"RSVP by {_d(r['rsvp_deadline'])}: {event}", "body": body}


def visitor_pack_template(idx: int) -> dict[str, str]:
    r = data.visits_view().loc[idx]
    agenda = "\n".join(f"- {a}" for a in data.VISIT_AGENDAS[r["purpose"]])
    body = (
        f"Dear {r['visitor_org']} team,\n\n"
        f"We're looking forward to welcoming you on {r['date']:%A} {r['date'].day} {r['date']:%B} at {r['time']} "
        f"for your {r['purpose'].lower()}.\n\n"
        f"Address: {data.OFFICE_ADDRESS}\n\n"
        f"Arriving: {data.ARRIVAL_NOTES}\n\n"
        f"Our {r['host']} will meet you in reception and take you up to your meeting room ({r['room']}).\n\n"
        f"Agenda:\n{agenda}\n\n"
        "If anything changes or you have access requirements, just reply to this email.\n\n"
        "Kind regards,\nBusiness Operations"
    )
    return {"subject": f"Your visit on {_d(r['date'])}: welcome pack", "body": body}


def chase_template(action: str, owner: str, source: str, due, status: str) -> dict[str, str]:
    t = data.today()
    days = (t - due).days
    board = data.next_board_date()
    board_line = (f" I'd like to give the CEO an update before the Board on {_d(board)}."
                  if source == "Board" else "")
    body = (
        f"Hi {owner},\n\n"
        f"Hope your week's going well. A quick nudge on \"{action}\" from the {source} — it was due on "
        f"{_d(due)} ({days} day{'s' if days != 1 else ''} ago) and is showing as {status.lower()} in the action log.\n\n"
        f"Could you let me know where it's got to, and a realistic new date if it needs one?{board_line} "
        "If anything is blocking it, I'm happy to help line up the right people.\n\n"
        "Thanks,\nBusiness Operations"
    )
    return {"subject": f"Quick check-in: {action}", "body": body}
