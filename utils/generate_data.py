"""Regenerate the demo data in data/ with dates relative to today.

Run on the morning of a demo so every date stays fresh:
    .venv/bin/python utils/generate_data.py
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
TODAY = date.today()
BOARD_WEEKDAY = 3      # Thursday
PACK_LEAD_DAYS = 7     # pack goes to the Company Secretary a week before (keep in sync with data.RAG_WINDOW_DAYS)


def _first_weekday_on_or_after(day: date, weekday: int) -> date:
    return day + timedelta(days=(weekday - day.weekday()) % 7)


BOARD_DATE = _first_weekday_on_or_after(TODAY + timedelta(days=12), BOARD_WEEKDAY)
PACK_DUE = BOARD_DATE - timedelta(days=PACK_LEAD_DAYS)


def weekday_on(offset: int) -> date:
    """TODAY + offset, moved off weekends.

    Weekends move back to the Friday, so overdue items stay overdue and future deadlines
    don't slip; the exception is a future date whose Friday would fall before today
    (only possible when run at a weekend), which moves forward to the Monday instead.
    """
    day = TODAY + timedelta(days=offset)
    if day.weekday() >= 5:
        friday = day - timedelta(days=day.weekday() - 4)
        day = friday if (offset < 0 or friday >= TODAY) else day + timedelta(days=7 - day.weekday())
    return day


def d(offset: int) -> str:
    """ISO date for TODAY + offset, always on a weekday."""
    return weekday_on(offset).isoformat()


def prev_business_day(day: date) -> date:
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def business_day(n: int) -> date:
    """n-th business day from today (0 = today, or the next weekday if today is a weekend)."""
    day = TODAY
    while day.weekday() >= 5:
        day += timedelta(days=1)
    count = 0
    while count < n:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return day


def nice(day: date) -> str:
    return f"{day:%A} {day.day} {day:%B}"


# ---------------------------------------------------------------------------
# Board pack — pack due to Company Secretary a week before the (Thursday) meeting.
# Red flags: one section overdue (CISO), one at risk (CRO: not started, due soon).
# ---------------------------------------------------------------------------
def board_pack() -> pd.DataFrame:
    m = BOARD_DATE.isoformat()
    rows = [
        ("CEO report", "CEO", 7, "In progress"),
        ("Previous minutes & matters arising", "Company Secretary", -3, "Approved"),
        ("Finance report & management accounts", "CFO", 2, "In progress"),
        ("FY27 budget & reforecast", "CFO", 5, "In progress"),
        ("Risk & compliance report", "CRO", 3, "Not started"),                     # at risk
        ("Regulatory horizon scan", "CRO", 7, "In progress"),
        ("Product & technology roadmap", "CTO", 6, "Submitted"),
        ("Information security & resilience", "CISO", -2, "Not started"),          # overdue
        ("People & culture update", "Head of People", 4, "Submitted"),
        ("Legal & governance update", "General Counsel", 5, "Approved"),
        ("Commercial pipeline & revenue", "Chief Revenue Officer", 7, "In progress"),
        ("Audit Committee report", "Audit Committee Chair", 6, "Submitted"),
    ]
    # Overdue sections stay relative to today; future ones never fall after the pack deadline
    return pd.DataFrame(
        [{"section": s, "owner": o, "due_date": (weekday_on(off) if off < 0 else min(weekday_on(off), PACK_DUE)).isoformat(),
          "status": st, "meeting_date": m} for s, o, off, st in rows]
    )


# ---------------------------------------------------------------------------
# Action log. Red flags: five other owners' actions past due (two Board ones badly); Business Operations' own are on track.
# ---------------------------------------------------------------------------
def actions() -> pd.DataFrame:
    rows = [
        ("Circulate revised FY27 hiring plan to Board", "Head of People", "Board", -80, -20, "In progress"),
        ("Present options for EU data residency", "CTO", "Board", -80, -10, "Open"),
        ("Commission external review of sanctions screening model", "CRO", "Board", -80, -35, "Open"),
        ("Update Board skills matrix", "Company Secretary", "Board", -80, -40, "Done"),
        ("Share competitor pricing benchmark", "Chief Revenue Officer", "Board", -80, 14, "In progress"),
        ("Finalise Series C data room index", "CFO", "Board", -80, -5, "In progress"),
        ("Agree FY27 OKR framework with ExCo", "CEO", "Offsite", -45, -12, "Done"),
        ("Draft hybrid working policy refresh", "Head of People", "Offsite", -45, 3, "Open"),
        ("Map customer onboarding journey end-to-end", "VP Customer Success", "Offsite", -45, 10, "In progress"),
        ("Scope partner channel programme for APAC", "Chief Revenue Officer", "Offsite", -45, 21, "Open"),
        ("Define product analytics north-star metric", "CPO", "Offsite", -45, -8, "In progress"),
        ("Publish engineering career framework", "CTO", "Offsite", -45, 5, "In progress"),
        ("Share Q3 results recap with all staff", "CEO", "All-hands", -30, -16, "Done"),
        ("Launch internal mobility pilot", "Head of People", "All-hands", -30, 12, "Open"),
        ("Post FAQ on new expenses tool", "CFO", "All-hands", -30, -18, "Done"),
        ("Fix meeting-room booking issues reported at all-hands", "Business Operations", "All-hands", -30, -9, "Done"),
        ("Organise end-of-year celebration", "Business Operations", "All-hands", -30, 25, "In progress"),
        ("Approve renewal of transaction-monitoring data supplier", "CFO", "ExCo", -14, 2, "Open"),
        ("Complete DORA ICT third-party register", "General Counsel", "ExCo", -14, 4, "In progress"),
        ("Review pricing for tier-1 bank RFP", "Chief Revenue Officer", "ExCo", -14, 3, "In progress"),
        ("Prepare FCA Consumer Duty attestation pack", "CRO", "ExCo", -14, 9, "Open"),
        ("Close out pen-test critical findings", "CISO", "ExCo", -7, 4, "In progress"),
        ("Confirm Q1 headcount approvals", "CFO", "ExCo", -7, 6, "Open"),
        ("Refresh customer reference list for sales", "VP Customer Success", "ExCo", -7, 8, "Done"),
        ("Book venue for Q1 leadership offsite", "Business Operations", "ExCo", -7, 15, "Open"),
    ]
    return pd.DataFrame(
        [
            {"action": a, "owner": o, "source": s, "raised_date": d(r), "due_date": d(due), "status": st}
            for a, o, s, r, due, st in rows
        ]
    )


# ---------------------------------------------------------------------------
# CEO diary — next 2 weeks (10 business days + Board day).
# Red flags: one double-booking, no-agenda investor/customer meetings.
# ---------------------------------------------------------------------------
def calendar() -> pd.DataFrame:
    # (business-day index, start, end, title, category, has_agenda, location)
    rows = [
        (0, "08:30", "09:00", "Weekly priorities review", "Internal", True, "Office"),
        (0, "09:00", "10:30", "ExCo weekly", "Internal", True, "Office – Boardroom"),
        (0, "11:00", "12:00", "Tier-1 bank RFP strategy", "Customer", True, "Office"),
        (0, "13:00", "13:45", "Final interview – VP Engineering", "Hiring", True, "Video call"),
        (0, "14:00", "15:00", "Lead investor quarterly check-in", "Investor", False, "Video call"),
        (0, "15:30", "16:30", "Compliance product deep-dive", "Internal", True, "Office"),
        (1, "08:00", "10:00", "Deep work – CEO board report", "Focus", False, "Office"),
        (1, "10:30", "11:30", "Customer QBR – European challenger bank", "Customer", True, "Video call"),
        (1, "12:30", "13:30", "Lunch with prospective NED", "Hiring", False, "Restaurant, City of London"),
        (1, "15:00", "16:00", "1:1 CFO", "Internal", True, "Office"),
        (2, "06:45", "08:15", "Train London → Edinburgh (outbound)", "Travel", False, "London King's Cross"),
        (2, "09:30", "10:00", "Leadership sync", "Internal", True, "Video call"),
        (2, "11:30", "13:00", "Customer workshop – building society", "Customer", True, "Client office, Edinburgh"),
        (2, "15:00", "16:00", "Fintech scale-up panel", "External/Industry", False, "Conference venue, Edinburgh"),
        (2, "17:00", "21:30", "Train Edinburgh → London (return)", "Travel", False, "Edinburgh Waverley"),
        (3, "09:00", "10:00", "1:1 CRO", "Internal", True, "Office"),
        (3, "10:00", "11:00", "Series C – growth fund intro", "Investor", False, "Investor office, Mayfair"),
        (3, "10:30", "11:15", "Candidate call – Head of Data", "Hiring", False, "Video call"),    # CONFLICT
        (3, "14:00", "16:00", "Deep work – strategy paper", "Focus", False, "Office"),
        (4, "09:00", "09:30", "1:1 Head of People", "Internal", True, "Office"),
        (4, "10:00", "11:00", "Partner call – cloud provider", "Customer", False, "Video call"),
        (4, "16:00", "17:00", "All-hands", "Internal", True, "Office – Town hall"),
        (5, "09:00", "10:30", "ExCo weekly", "Internal", True, "Office – Boardroom"),
        (5, "11:00", "12:00", "Board pack review with Company Secretary", "Internal", True, "Office"),
        (5, "13:00", "14:00", "Payments platform prospect – demo", "Customer", True, "Video call"),
        (5, "15:00", "16:00", "Existing investor – board observer catch-up", "Investor", False, "Video call"),
        (6, "06:15", "07:30", "Flight LHR → AMS", "Travel", False, "Heathrow T2"),
        (6, "08:45", "10:15", "Customer visit – Dutch retail bank", "Customer", True, "Client office, Amsterdam"),
        (6, "12:00", "13:30", "RegTech round-table lunch", "Customer", False, "Amsterdam"),
        (6, "14:30", "15:30", "1:1 CTO", "Internal", True, "Video call"),
        (6, "18:30", "19:45", "Flight AMS → LHR", "Travel", False, "Schiphol"),
        (7, "08:00", "10:00", "Deep work – Board deck final edits", "Focus", False, "Office"),
        (7, "10:00", "11:00", "Interview – Chief Product Officer", "Hiring", True, "Office"),
        (7, "11:00", "12:00", "Audit Committee pre-meet", "Internal", True, "Office – Boardroom"),
        (7, "14:00", "15:00", "Analyst briefing – industry research firm", "Investor", False, "Video call"),
        (8, "09:00", "10:00", "1:1 General Counsel", "Internal", True, "Office"),
        (8, "10:00", "11:30", "Board pre-brief with Chair", "Internal", False, "Chair's office"),
        (8, "13:00", "14:00", "Customer escalation – onboarding delays", "Customer", False, "Video call"),
        (9, "09:00", "11:00", "Deep work – Board rehearsal", "Focus", False, "Office"),
        (9, "11:30", "12:30", "Fund LP update call", "Investor", True, "Video call"),
        (9, "15:00", "16:00", "Weekly priorities review", "Internal", True, "Office"),
    ]
    out = [
        {
            "date": business_day(i).isoformat(),
            "start": s, "end": e, "title": t, "category": c, "has_agenda": a, "location": loc,
        }
        for i, s, e, t, c, a, loc in rows
    ]
    out.append({
        "date": BOARD_DATE.isoformat(), "start": "09:30", "end": "13:30", "title": "Board meeting",
        "category": "Internal", "has_agenda": True, "location": "Office – Boardroom",
    })
    return pd.DataFrame(out).sort_values(["date", "start"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Office tickets. Red flags: one repeat issue (Wi-Fi, IT supplier), a couple of stale tickets.
# ---------------------------------------------------------------------------
CLEANING = "Sparkle Facilities Ltd"
COFFEE = "Bean & Leaf Coffee Co"
PRINT = "PrintRight Managed Print"
IT_SUPPORT = "Northgate IT Services"
CATERING = "Harvest Table Catering"
PLANTS = "GreenSpace Plants"
SECURITY = "Sentinel Security"


def tickets() -> pd.DataFrame:
    # supplier links a ticket to a contracted supplier (blank = in-house / landlord)
    rows = [
        ("Air conditioning too hot on 3rd floor", -21, "Building management", "Resolved", 4, ""),
        ("Boardroom screen won't connect to laptops", -9, "IT", "Open", 2, IT_SUPPORT),
        ("Wi-Fi dropping in meeting rooms", -16, "IT", "In progress", 5, IT_SUPPORT),
        ("Kitchen dishwasher leaking", -4, "Supplier", "Open", 2, CATERING),
        ("Lift out of service", -2, "Building management", "In progress", 1, ""),
        ("New starter laptops not ready for Monday", -3, "IT", "Open", 1, ""),
        ("Printer on 2nd floor jammed", -12, "Supplier", "Resolved", 3, PRINT),
        ("Access card not working for new joiners", -6, "Building management", "Resolved", 2, SECURITY),
        ("Meeting room booking panel offline", -30, "IT", "Resolved", 2, IT_SUPPORT),
        ("Bike store lock broken", -25, "Building management", "Open", 1, ""),
        ("Coffee machine out of order", -1, "Supplier", "Open", 1, COFFEE),
        ("Toilet on 3rd floor blocked", -5, "Building management", "Resolved", 1, ""),
        ("Cleaning missed on Fridays", -18, "Supplier", "Resolved", 3, CLEANING),
        ("VPN slow for remote staff", -10, "IT", "Resolved", 1, ""),
        ("Water dispenser filter overdue", -40, "Supplier", "Open", 1, ""),
    ]
    return pd.DataFrame(
        [{"issue": i, "raised_date": d(r), "assigned_to": a, "status": s, "repeat_count": n, "supplier": sup}
         for i, r, a, s, n, sup in rows]
    )


# ---------------------------------------------------------------------------
# Events. Headline: the Christmas party — RSVP deadline in 3 days, a quarter of invitees
# still pending, budget >90% committed. Business Operations' checklist tasks are on track.
# ---------------------------------------------------------------------------
XMAS = "Christmas party 2026"
TEAM_LUNCH = "Ops & Finance team lunch"
ALL_HANDS = "Q4 all-hands & drinks"
CLIENT_DINNER = "Client dinner – Tier-1 UK bank"
OFFSITE = "Q1 ExCo offsite"
SUMMER = "Summer social 2026"


def events() -> pd.DataFrame:
    # (event, type, date, venue, invited, yes, no, pending, rsvp_deadline, final_numbers_due, budget, committed, status)
    rows = [
        (XMAS, "Christmas party", 31, "The Glasshouse, Shoreditch", 210, 140, 20, 50, 3, 8, 18000, 16900, "Planning"),
        (TEAM_LUNCH, "Team lunch", (business_day(3) - TODAY).days, "Lantern Kitchen, Moorgate", 18, 16, 2, 0, 1, 2, 900, 610, "Confirmed"),
        (ALL_HANDS, "All-hands", (business_day(4) - TODAY).days, "Office – Town hall",
         205, 178, 27, 0, 2, 3, 2500, 1950, "Confirmed"),
        (CLIENT_DINNER, "Client dinner", 9, "The Vault Room, Bank", 12, 10, 1, 1, 5, 7, 3000, 2850, "Planning"),
        (OFFSITE, "ExCo offsite", 64, "Hartwell Manor, Surrey", 10, 9, 0, 1, 20, 35, 12000, 4500, "Planning"),
        (SUMMER, "Summer social", -130, "Rooftop terrace, South Bank", 195, 150, 45, 0, -145, -140, 9000, 8650,
         "Completed"),
    ]
    out = []
    for e, t, dt, v, inv, y, n, p, rd, fn, b, c, s in rows:
        final = weekday_on(fn)
        rsvp = weekday_on(rd)
        if rsvp >= final:  # both snapped to the same Friday: RSVPs must close first
            rsvp = prev_business_day(final)
        out.append({"event": e, "type": t, "date": d(dt), "venue": v, "invited": inv, "rsvp_yes": y, "rsvp_no": n,
                    "rsvp_pending": p, "rsvp_deadline": rsvp.isoformat(), "final_numbers_due": final.isoformat(),
                    "budget_gbp": b, "committed_gbp": c, "status": s})
    return pd.DataFrame(out)


def event_checklist() -> pd.DataFrame:
    # (event, task, owner, due offset, done)
    rows = [
        (XMAS, "Venue booked", "Business Operations", -40, True),
        (XMAS, "Deposit paid", "Finance", -30, True),
        (XMAS, "Invites sent", "Business Operations", -21, True),
        (XMAS, "Catering confirmed", "Business Operations", 5, False),
        (XMAS, "Dietary requirements collected", "Business Operations", 3, False),
        (XMAS, "AV/music booked", "Business Operations", -2, True),
        (XMAS, "Accessibility checked", "Head of People", 4, False),
        (XMAS, "Transport/late-night travel", "Business Operations", 14, False),
        (XMAS, "Photographer", "Marketing", -1, True),
        (XMAS, "Risk assessment", "Business Operations", 10, False),
        (TEAM_LUNCH, "Venue booked", "Business Operations", -7, True),
        (TEAM_LUNCH, "Invites sent", "Business Operations", -6, True),
        (TEAM_LUNCH, "Dietary requirements collected", "Business Operations", 1, True),
        (TEAM_LUNCH, "Catering confirmed", "Business Operations", 3, False),
        (ALL_HANDS, "Invites sent", "Internal Comms", -10, True),
        (ALL_HANDS, "AV/music booked", "IT", -3, True),
        (ALL_HANDS, "Catering confirmed", "Business Operations", 2, False),
        (ALL_HANDS, "Dietary requirements collected", "Business Operations", 2, False),
        (ALL_HANDS, "Accessibility checked", "Head of People", 3, False),
        (CLIENT_DINNER, "Venue booked", "Executive Assistant", -10, True),
        (CLIENT_DINNER, "Deposit paid", "Finance", -1, True),
        (CLIENT_DINNER, "Invites sent", "Chief Revenue Officer", -8, True),
        (CLIENT_DINNER, "Dietary requirements collected", "Executive Assistant", 5, False),
        (CLIENT_DINNER, "Transport/late-night travel", "Executive Assistant", 7, False),
        (OFFSITE, "Venue booked", "Business Operations", 15, False),
        (OFFSITE, "Deposit paid", "Finance", 20, False),
        (OFFSITE, "Invites sent", "Business Operations", -5, True),
        (OFFSITE, "Transport/late-night travel", "Business Operations", 40, False),
        (OFFSITE, "Risk assessment", "Business Operations", 50, False),
        (SUMMER, "Venue booked", "Business Operations", -200, True),
        (SUMMER, "Invites sent", "Business Operations", -170, True),
        (SUMMER, "Catering confirmed", "Business Operations", -140, True),
        (SUMMER, "Risk assessment", "Business Operations", -135, True),
    ]
    return pd.DataFrame([{"event": e, "task": t, "owner": o, "due_date": d(off), "done": done}
                         for e, t, o, off, done in rows])


def event_dietary() -> pd.DataFrame:
    counts = {
        XMAS: {"Vegetarian": 22, "Vegan": 9, "Halal": 11, "Gluten-free": 6, "Nut allergy": 3},
        TEAM_LUNCH: {"Vegetarian": 3, "Vegan": 1, "Halal": 1, "Gluten-free": 0, "Nut allergy": 0},
        ALL_HANDS: {"Vegetarian": 18, "Vegan": 6, "Halal": 9, "Gluten-free": 4, "Nut allergy": 2},
        CLIENT_DINNER: {"Vegetarian": 1, "Vegan": 0, "Halal": 1, "Gluten-free": 1, "Nut allergy": 0},
        OFFSITE: {"Vegetarian": 1, "Vegan": 0, "Halal": 0, "Gluten-free": 0, "Nut allergy": 1},
    }
    return pd.DataFrame([{"event": e, "requirement": r, "count": n}
                         for e, reqs in counts.items() for r, n in reqs.items()])


# ---------------------------------------------------------------------------
# Visitors (clients, regulators, candidates) over the next 3 weeks. Near-term visits are fully
# ready; later ones still in prep.
# ---------------------------------------------------------------------------
def visits() -> pd.DataFrame:
    T, F = True, False
    # (business day, time, org, count, host, purpose, room,
    #  room_booked, passes, nda, catering, welcome_screen, wifi, host_briefed)
    rows = [
        (0, "14:00", "Tier-1 UK bank", 4, "Chief Revenue Officer", "Product demo", "Boardroom",
         T, T, T, T, T, T, T),
        (1, "10:00", "EU neobank", 3, "CPO", "Due diligence", "Meeting room 3",
         T, T, T, T, T, T, T),
        (2, "15:00", "Regulator liaison", 2, "CRO", "Due diligence", "Meeting room 1",
         T, T, T, T, T, T, T),
        (5, "09:30", "UK building society", 5, "VP Customer Success", "QBR", "Boardroom",
         T, T, T, T, T, T, T),
        (7, "11:00", "Global card scheme", 3, "CEO", "Partnership", "Boardroom",
         T, F, T, F, F, F, F),
        (9, "13:00", "Big-four audit firm", 4, "CFO", "Due diligence", "Meeting room 2",
         T, F, T, F, F, F, T),
        (11, "10:00", "Head of Data candidate", 1, "Head of People", "Interview panel", "Meeting room 4",
         T, F, F, F, F, F, F),
        (14, "14:30", "Dutch retail bank", 6, "Chief Revenue Officer", "QBR", "Boardroom",
         F, F, T, F, F, F, F),
    ]
    cols = ["room_booked", "building_passes_registered", "nda_signed", "catering_ordered",
            "welcome_screen_set", "guest_wifi_issued", "host_briefed"]
    return pd.DataFrame([
        {"date": business_day(bd).isoformat(), "time": tm, "visitor_org": org, "visitor_count": n, "host": h,
         "purpose": p, "room": room, **dict(zip(cols, checks))}
        for bd, tm, org, n, h, p, room, *checks in rows
    ])


# ---------------------------------------------------------------------------
# CEO travel. This week's trip is fully ready; later trips still in prep.
# ---------------------------------------------------------------------------
def travel() -> pd.DataFrame:
    T, F = True, False
    # (trip, start, end, destination, purpose, transport, hotel, itinerary, expenses_card, return_confirmed)
    rows = [
        ("Edinburgh customer day", business_day(2), business_day(2), "Edinburgh",
         "Building society workshop; fintech scale-up panel", T, F, T, T, T),
        ("Amsterdam customer visit", business_day(6), business_day(6), "Amsterdam",
         "Dutch retail bank visit; RegTech round-table", T, F, F, T, T),
        ("Manchester partner summit", business_day(14), business_day(15), "Manchester",
         "Partner summit keynote; customer dinner", T, T, T, T, T),
        ("New York investor roadshow", business_day(18), business_day(21), "New York",
         "Series C investor meetings", F, F, F, T, F),
    ]
    return pd.DataFrame([
        {"trip": t, "start_date": s.isoformat(), "end_date": e.isoformat(), "destination": dest, "purpose": p,
         "transport_booked": tb, "hotel_booked": hb, "itinerary_sent": it, "expenses_card": ec,
         "return_confirmed": rc}
        for t, s, e, dest, p, tb, hb, it, ec, rc in rows
    ])


# ---------------------------------------------------------------------------
# Supplies & suppliers. Red flags: items at/below reorder level, two contracts
# ending within 60 days, IT support with a repeat ticket, spend over budget.
# ---------------------------------------------------------------------------
def supplies() -> pd.DataFrame:
    rows = [
        ("Coffee beans (kg)", 6, 10, COFFEE, -12),
        ("Milk – oat & dairy (L)", 30, 24, COFFEE, -2),
        ("Printer toner cartridges", 2, 4, PRINT, -45),
        ("A4 paper (reams)", 40, 20, PRINT, -20),
        ("Hand soap refills", 12, 10, CLEANING, -15),
        ("Paper towels (cases)", 3, 5, CLEANING, -25),
        ("Bin liners (rolls)", 18, 10, CLEANING, -30),
        ("Visitor lanyards", 25, 30, SECURITY, -60),
        ("Meeting-room bottled water (cases)", 8, 6, CATERING, -7),
        ("Plant feed", 4, 2, PLANTS, -90),
    ]
    return pd.DataFrame([{"item": i, "stock": s, "reorder_level": r, "supplier": sup, "last_ordered": d(lo)}
                         for i, s, r, sup, lo in rows])


def suppliers(ticket_df: pd.DataFrame) -> pd.DataFrame:
    open_t = ticket_df[ticket_df["status"] != "Resolved"]
    rows = [
        (CLEANING, "Cleaning", 120, 4200, 2),
        (COFFEE, "Coffee", 300, 1100, 4),
        (PRINT, "Printers", 75, 650, 3),
        (IT_SUPPORT, "IT support", 200, 5200, 2),
        (CATERING, "Catering", 50, 2400, 4),
        (PLANTS, "Plants", 38, 380, 5),
        (SECURITY, "Security", 400, 1600, 4),
    ]
    return pd.DataFrame([
        {"supplier": s, "service": svc, "contract_end": d(end), "monthly_cost_gbp": cost,
         "open_issues": int((open_t["supplier"] == s).sum()), "satisfaction": sat}
        for s, svc, end, cost, sat in rows
    ])


# ---------------------------------------------------------------------------
# Health & safety. All in date (risk assessment reviewed recently); a few due soon.
# ---------------------------------------------------------------------------
def hs_checks() -> pd.DataFrame:
    rows = [
        ("Fire alarm test", -3, 7, "Building management"),
        ("Fire drill / evacuation", -60, 180, "Business Operations"),
        ("Fire warden training", -200, 365, "Business Operations"),
        ("First aider certificates", -900, 1095, "Head of People"),
        ("PAT testing", -340, 365, "Supplier"),                                # due soon
        ("Office risk assessment review", -21, 365, "Business Operations"),
        ("DSE workstation assessments", -120, 365, "Head of People"),
        ("Emergency lighting test", -20, 30, "Building management"),
        ("First aid kit restock", -50, 90, "Business Operations"),
        ("Legionella water check", -60, 90, "Building management"),
    ]
    # Anchor on the next-due date (kept off weekends) and work back to when it was last done
    out = []
    for c, ld, f, o in rows:
        next_due = weekday_on(ld + f)
        out.append({"check": c, "last_done": (next_due - timedelta(days=f)).isoformat(), "frequency_days": f, "owner": o})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Automation backlog — total ≈ 20 hours/month.
# ---------------------------------------------------------------------------
def automations() -> pd.DataFrame:
    rows = [
        ("Board/ExCo minutes & action extraction", "Transcript → actions with owners and dates", "Claude", 5.0, "Piloting"),
        ("Chasing board pack submissions", "Automatic reminders at T-7/T-5/T-3 with status links", "Power Automate", 3.0, "Live"),
        ("CEO weekly diary brief", "Monday summary of conflicts, missing agendas, travel", "Claude", 2.5, "Idea"),
        ("Inbox triage for CEO office", "Route invoices, intros and events to folders", "Outlook rules", 2.0, "Live"),
        ("Facilities ticket logging", "Teams form → ticket list with repeat-issue detection", "Power Automate", 2.5, "Piloting"),
        ("H&S compliance tracker", "Next-due dates and owner nudges", "Excel", 1.5, "Live"),
        ("Drafting replies to routine requests", "First drafts for travel, room and supplier emails", "Copilot", 2.0, "Idea"),
        ("New-starter onboarding logistics", "Agent books kit, desk, access card and induction", "Abundly", 1.5, "Idea"),
    ]
    return pd.DataFrame(
        [{"process": p, "fix": f, "tool": t, "hours_saved_per_month": h, "status": s} for p, f, t, h, s in rows]
    )


# ---------------------------------------------------------------------------
# Sample ExCo transcript + cached extraction.
# ---------------------------------------------------------------------------
def transcript_and_actions() -> tuple[str, list[dict]]:
    meeting = business_day(0)
    fri = business_day(4)
    wed_next = business_day(7)
    pack_due = PACK_DUE
    thu = business_day(3)
    end_month = (TODAY.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    text = f"""ExCo Weekly Meeting — {nice(meeting)}
Attendees: CEO (chair), CFO, CTO, CRO, Head of People, General Counsel, Chief Revenue Officer, Business Operations Coordinator (notes)

CEO: Morning, everyone. We're {(BOARD_DATE - meeting).days} days out from the Board, so let's keep this tight. First, the Board pack. Where are we?

Business Operations Coordinator: Three sections are still outstanding — finance, risk and compliance, and information security. Pack goes to the Company Secretary on {nice(pack_due)}.

CFO: Finance is close. The management accounts are done; I'm still finishing the reforecast commentary. I'll have the finance section submitted by {nice(fri)}.

CRO: Risk is behind, honestly. We're waiting on the sanctions screening model review. I'll get a draft of the risk and compliance report to the Coordinator by {nice(thu)}, and flag anything unresolved.

CEO: Good. Information security?

CTO: The CISO is out this week, but I'll make sure the pen-test close-out summary is in the pack. I'll own that and deliver it by {nice(fri)}.

CEO: Next, hiring. Where are we on the VP Engineering offer?

Head of People: Final interview was today. If the panel agrees, I'll send the offer by {nice(wed_next)}.

CEO: Thanks. Commercial — the tier-1 bank RFP?

Chief Revenue Officer: Pricing is the sticking point. I need CFO sign-off on the discount floor. Can we agree that this week?

CFO: Send me the model and I'll sign off by {nice(thu)}.

Chief Revenue Officer: Will do. I'll submit the final RFP response by {nice(wed_next)}.

CEO: Legal — DORA?

General Counsel: The ICT third-party register is about seventy percent complete. I'll have it finished by {nice(end_month)}.

CEO: Quick temperature check on the onboarding escalation from last week. Are we on top of it?

Chief Revenue Officer: Customer Success has a recovery plan in place and the client is calmer. No Board-level risk, but I'll keep it on the commercial slide so nobody is surprised.

CFO: Agreed. It's also worth noting cash runway is unchanged from last month, so no surprises there either.

CEO: Good. One more thing from me: the third-floor air conditioning. That's the fourth complaint. Can ops escalate it with building management and come back with a fix date by {nice(fri)}?

Business Operations Coordinator: Yes, I'll escalate today and report back by {nice(fri)}.

CEO: Great. I'll circulate the summary and actions by end of day. Thanks, all.
"""

    acts = [
        ("Submit finance section of Board pack", "CFO", fri),
        ("Send draft risk & compliance report to Business Operations Coordinator", "CRO", thu),
        ("Deliver pen-test close-out summary for Board pack", "CTO", fri),
        ("Send VP Engineering offer (subject to panel agreement)", "Head of People", wed_next),
        ("Sign off discount floor for tier-1 bank RFP", "CFO", thu),
        ("Submit final tier-1 bank RFP response", "Chief Revenue Officer", wed_next),
        ("Complete DORA ICT third-party register", "General Counsel", end_month),
        ("Escalate 3rd-floor air conditioning and report fix date", "Business Operations Coordinator", fri),
    ]
    return text, [
        {"action": a, "owner": o, "due_date": dd.isoformat(), "source": "ExCo"} for a, o, dd in acts
    ]


def write_ai_fallbacks() -> None:
    """Cached outputs for the AI features, built from the CSVs just written."""
    import logging
    import sys

    logging.getLogger("streamlit").setLevel(logging.ERROR)
    sys.path.insert(0, str(DATA.parent))
    from utils import fallbacks  # noqa: PLC0415 — needs the fresh CSVs on disk

    brief = fallbacks.build_sample_brief()
    (DATA / "sample_brief.md").write_text(brief)
    answers = fallbacks.build_canned_answers()
    (DATA / "sample_answers.json").write_text(json.dumps(answers, indent=2, ensure_ascii=False))
    print(f"sample_brief.md: {len(brief.split())} words; sample_answers.json: {len(answers)} answers")


def main() -> None:
    DATA.mkdir(exist_ok=True)
    ticket_df = tickets()
    for name, fn in {
        "board_pack": board_pack, "actions": actions, "calendar": calendar,
        "tickets": lambda: ticket_df, "hs_checks": hs_checks, "automations": automations,
        "events": events, "event_checklist": event_checklist, "event_dietary": event_dietary,
        "visits": visits, "travel": travel, "supplies": supplies, "suppliers": lambda: suppliers(ticket_df),
    }.items():
        df = fn()
        df.to_csv(DATA / f"{name}.csv", index=False)
        print(f"{name}.csv: {len(df)} rows")
    text, acts = transcript_and_actions()
    (DATA / "sample_transcript.txt").write_text(text)
    (DATA / "sample_actions.json").write_text(json.dumps({"meeting": "ExCo weekly", "actions": acts}, indent=2))
    print(f"sample_transcript.txt: {len(text.split())} words; sample_actions.json: {len(acts)} actions")
    write_ai_fallbacks()
    (DATA / "demo_date.txt").write_text(TODAY.isoformat())
    print(f"Today {TODAY} · Board meeting {BOARD_DATE} ({BOARD_DATE:%A})")


if __name__ == "__main__":
    main()
