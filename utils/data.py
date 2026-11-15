"""Shared data loading, KPI calculations and red-flag detection for every page."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PAGES = {
    "board": ("pages/1_Board_Readiness.py", "Board Readiness"),
    "ceo": ("pages/2_CEO_Week.py", "CEO Week"),
    "office": ("pages/3_Office_and_Events.py", "Office & Events"),
    "automation": ("pages/4_Automation_Backlog.py", "Automation Backlog"),
}

CUSTOMER_TIME_TARGET = 0.30
DONE_PACK = {"Submitted", "Approved"}
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def today() -> date:
    """The demo's "today": the date the data was generated (data/demo_date.txt), so dates in the
    data, the AI cache keys and the cached results all stay consistent after deployment."""
    try:
        return date.fromisoformat((DATA_DIR / "demo_date.txt").read_text().strip())
    except (OSError, ValueError):
        return date.today()


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _read(name: str, date_cols: list[str]) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / name)
    for c in date_cols:
        df[c] = pd.to_datetime(df[c]).dt.date
    return df


@st.cache_data
def load_board_pack() -> pd.DataFrame:
    return _read("board_pack.csv", ["due_date", "meeting_date"])


@st.cache_data
def load_actions() -> pd.DataFrame:
    return _read("actions.csv", ["raised_date", "due_date"])


@st.cache_data
def load_calendar() -> pd.DataFrame:
    df = _read("calendar.csv", ["date"])
    df["has_agenda"] = df["has_agenda"].astype(str).str.lower().eq("true")
    start = pd.to_timedelta(df["start"] + ":00")
    end = pd.to_timedelta(df["end"] + ":00")
    df["hours"] = (end - start).dt.total_seconds() / 3600
    return df


def _bools(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        df[c] = df[c].astype(str).str.lower().eq("true")
    return df


@st.cache_data
def load_tickets() -> pd.DataFrame:
    df = _read("tickets.csv", ["raised_date"])
    df["supplier"] = df["supplier"].fillna("") if "supplier" in df else ""
    df["age_days"] = [(today() - d).days for d in df["raised_date"]]
    return df


@st.cache_data
def load_hs_checks() -> pd.DataFrame:
    df = _read("hs_checks.csv", ["last_done"])
    df["next_due"] = [d + timedelta(days=int(f)) for d, f in zip(df["last_done"], df["frequency_days"])]
    df["days_until_due"] = [(d - today()).days for d in df["next_due"]]
    return df


@st.cache_data
def load_automations() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "automations.csv")


@st.cache_data
def load_events() -> pd.DataFrame:
    return _read("events.csv", ["date", "rsvp_deadline", "final_numbers_due"])


@st.cache_data
def load_event_checklist() -> pd.DataFrame:
    return _bools(_read("event_checklist.csv", ["due_date"]), ["done"])


@st.cache_data
def load_event_dietary() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "event_dietary.csv")


VISIT_CHECKS = {
    "room_booked": "Room booked",
    "building_passes_registered": "Building passes",
    "nda_signed": "NDA signed",
    "catering_ordered": "Catering",
    "welcome_screen_set": "Welcome screen",
    "guest_wifi_issued": "Guest Wi-Fi",
    "host_briefed": "Host briefed",
}


@st.cache_data
def load_visits() -> pd.DataFrame:
    return _bools(_read("visits.csv", ["date"]), list(VISIT_CHECKS))


TRAVEL_CHECKS = {
    "transport_booked": "Transport",
    "hotel_booked": "Hotel",
    "itinerary_sent": "Itinerary sent",
    "expenses_card": "Expenses card",
    "return_confirmed": "Return confirmed",
}


@st.cache_data
def load_travel() -> pd.DataFrame:
    return _bools(_read("travel.csv", ["start_date", "end_date"]), list(TRAVEL_CHECKS))


@st.cache_data
def load_supplies() -> pd.DataFrame:
    return _read("supplies.csv", ["last_ordered"])


@st.cache_data
def load_suppliers() -> pd.DataFrame:
    return _read("suppliers.csv", ["contract_end"])


# ---------------------------------------------------------------------------
# Derived views
# ---------------------------------------------------------------------------
def next_board_date() -> date:
    return load_board_pack()["meeting_date"].min()


def overdue_actions() -> pd.DataFrame:
    a = load_actions()
    return a[(a["status"] != "Done") & (a["due_date"] < today())]


def week_bounds(ref: date | None = None) -> tuple[date, date]:
    ref = ref or today()
    monday = ref - timedelta(days=ref.weekday())
    return monday, monday + timedelta(days=6)


def customer_time_share(ref: date | None = None) -> float:
    """Share of the CEO's booked (non-travel) hours this week spent with customers."""
    cal = load_calendar()
    start, end = week_bounds(ref)
    week = cal[(cal["date"] >= start) & (cal["date"] <= end) & (cal["category"] != "Travel")]
    total = week["hours"].sum()
    return float(week.loc[week["category"] == "Customer", "hours"].sum() / total) if total else 0.0


def open_tickets() -> pd.DataFrame:
    t = load_tickets()
    return t[t["status"] != "Resolved"]


def calendar_conflicts() -> list[tuple[pd.Series, pd.Series]]:
    """Pairs of overlapping diary entries on the same day."""
    pairs = []
    for _, day in load_calendar().sort_values(["date", "start"]).groupby("date"):
        rows = list(day.itertuples(index=False))
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if b.start < a.end and a.start < b.end:
                    pairs.append((a, b))
    return pairs


# ---------------------------------------------------------------------------
# "Needs your attention" — every red flag across every dataset
# ---------------------------------------------------------------------------
def _fmt(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def _days(n: int) -> str:
    return f"{n} day{'s' if n != 1 else ''}"


def _in(n: int) -> str:
    return {0: "today", 1: "tomorrow"}.get(n, f"in {n} days")


def attention_items() -> pd.DataFrame:
    t = today()
    items: list[dict] = []

    def add(severity, page, area, title, detail, when):
        items.append({"severity": severity, "page": page, "area": area,
                      "title": title, "detail": detail, "when": when})

    # Board pack
    for r in load_board_pack().itertuples():
        if r.status in DONE_PACK:
            continue
        days = (r.due_date - t).days
        if days < 0:
            add("Critical", "board", "Board pack", f"{r.section} is overdue",
                f"{r.owner} · {r.status} · due {_fmt(r.due_date)} ({_days(-days)} late)", r.due_date)
        elif r.status == "Not started" and days <= 5:
            add("High", "board", "Board pack", f"{r.section} not started",
                f"{r.owner} · due {_fmt(r.due_date)} (in {_days(days)})", r.due_date)

    # Actions
    for r in overdue_actions().itertuples():
        late = (t - r.due_date).days
        add("Critical" if late > 14 else "High", "board", f"{r.source} action", r.action,
            f"{r.owner} · {r.status} · {_days(late)} overdue", r.due_date)

    # CEO diary
    for a, b in calendar_conflicts():
        add("High", "ceo", "CEO diary", f"Double-booked: {a.title} / {b.title}",
            f"{_fmt(a.date)} · {a.start}–{a.end} overlaps {b.start}–{b.end}", a.date)
    horizon = t + timedelta(days=7)
    for r in load_calendar().itertuples():
        if (not r.has_agenda and r.category in {"Customer", "Investor"}
                and t <= r.date <= horizon):
            add("Medium", "ceo", "CEO diary", f"No agenda: {r.title}",
                f"{r.category} · {_fmt(r.date)} {r.start}", r.date)

    # Travel
    for r in travel_view().itertuples():
        if 0 <= r.days_to_trip <= TRAVEL_WINDOW_DAYS and r.readiness < 1:
            add("High", "ceo", "Travel", f"{r.trip} {r.readiness:.0%} ready",
                f"{_fmt(r.start_date)} · {r.destination} · missing: {r.missing}", r.start_date)

    # Facilities
    for r in open_tickets().itertuples():
        if r.repeat_count >= 3:
            add("High", "office", "Facilities", f"Repeat issue: {r.issue}",
                f"Reported {r.repeat_count}× · {r.assigned_to} · {r.status}", t)
        elif r.age_days > 21:
            add("Medium", "office", "Facilities", f"Stale ticket: {r.issue}",
                f"Open {_days(r.age_days)} · {r.assigned_to}", t)

    # Health & safety
    for r in load_hs_checks().itertuples():
        if r.days_until_due < 0:
            add("Critical", "office", "Health & safety", f"{r.check} overdue",
                f"{r.owner} · was due {_fmt(r.next_due)} ({_days(-r.days_until_due)} late)", r.next_due)
        elif r.days_until_due <= 30:
            add("Medium", "office", "Health & safety", f"{r.check} due soon",
                f"{r.owner} · due {_fmt(r.next_due)}", r.next_due)

    # Events
    for r in upcoming_events().itertuples():
        if 0 <= r.days_to_rsvp_deadline <= RSVP_WINDOW_DAYS and r.pending_share > RSVP_PENDING_SHARE:
            add("High", "office", "Events", f"{r.event}: {r.rsvp_pending} RSVPs still pending",
                f"{r.pending_share:.0%} of {r.invited} invited haven't replied · RSVP deadline "
                f"{_fmt(r.rsvp_deadline)} ({_in(r.days_to_rsvp_deadline)})", r.rsvp_deadline)
        if r.rsvp_pending > 0 and 0 <= r.days_to_final_numbers <= FINAL_NUMBERS_WINDOW_DAYS:
            add("High", "office", "Events",
                f"{r.event}: final numbers due to venue",
                f"{r.venue} · due {_fmt(r.final_numbers_due)} ({_in(r.days_to_final_numbers)}) · "
                f"{r.rsvp_yes} confirmed, {r.rsvp_pending} pending", r.final_numbers_due)
        if r.budget_used > BUDGET_ALERT_SHARE:
            add("High" if r.budget_used > 1 else "Medium", "office", "Events",
                f"{r.event}: {r.budget_used:.0%} of budget committed",
                f"£{r.committed_gbp:,.0f} of £{r.budget_gbp:,.0f} · £{r.budget_gbp - r.committed_gbp:,.0f} left "
                f"with {r.rsvp_pending} RSVP{'s' if r.rsvp_pending != 1 else ''} pending", r.date)
    late_tasks = checklist_view()
    for event, rows in late_tasks[late_tasks["overdue"]].groupby("event"):
        n = len(rows)
        add("High", "office", "Events", f"{event}: {n} overdue checklist task{'s' if n != 1 else ''}",
            "; ".join(f"{r.task} ({r.owner}, {_days(-r.days_to_due)} late)" for r in rows.itertuples()),
            rows["due_date"].min())

    # Visitors
    for r in visits_view().itertuples():
        if 0 <= r.days_to_visit <= VISIT_WINDOW_DAYS and r.readiness < 1:
            add("Critical" if not (r.nda_signed and r.room_booked) else "High", "office", "Visitors",
                f"{r.visitor_org} visit {r.readiness:.0%} ready",
                f"{_fmt(r.date)} {r.time} · host {r.host} · missing: {r.missing}", r.date)

    # Supplies & suppliers
    low = supplies_view()
    low = low[low["reorder"]]
    if len(low):
        add("Medium", "office", "Supplies", f"{len(low)} supplies at or below reorder level",
            "; ".join(f"{r.item}: {r.stock} left (reorder at {r.reorder_level})" for r in low.itertuples()), t)
    sup = suppliers_view()
    for r in sup[sup["contract_ending"]].itertuples():
        add("High" if r.days_to_contract_end <= 30 else "Medium", "office", "Suppliers",
            f"{r.supplier} contract ends in {_days(r.days_to_contract_end)}",
            f"{r.service} · ends {_fmt(r.contract_end)} · £{r.monthly_cost_gbp:,.0f}/month · "
            f"satisfaction {r.satisfaction}/5", r.contract_end)
    for r in sup[sup["repeat_tickets"] > 0].itertuples():
        add("High", "office", "Suppliers", f"{r.supplier}: repeat facilities tickets",
            f"{r.service} · {r.repeat_issues} · satisfaction {r.satisfaction}/5", t)
    spend = int(sup["monthly_cost_gbp"].sum())
    if spend > OFFICE_MONTHLY_BUDGET:
        add("Medium", "office", "Suppliers", "Office running costs over budget",
            f"£{spend:,.0f}/month vs £{OFFICE_MONTHLY_BUDGET:,.0f} budget "
            f"(+£{spend - OFFICE_MONTHLY_BUDGET:,.0f}, {spend / OFFICE_MONTHLY_BUDGET - 1:.0%} over)", t)

    # Automation
    auto = load_automations()
    ideas = auto[auto["status"] == "Idea"]
    if len(ideas):
        add("Low", "automation", "Automation",
            f"{len(ideas)} ideas not yet piloted",
            f"{ideas['hours_saved_per_month'].sum():g} hours/month still on the table", t)

    df = pd.DataFrame(items)
    if df.empty:
        return df
    df["rank"] = df["severity"].map(SEVERITY_ORDER)
    return df.sort_values(["rank", "when"]).drop(columns="rank").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Board readiness helpers
# ---------------------------------------------------------------------------
RAG_WINDOW_DAYS = 7  # pack goes to the Company Secretary a week before the meeting


def board_pack_rag() -> pd.DataFrame:
    """Board pack with a RAG column.

    Green: Submitted/Approved. Red: not submitted and either past its own due date or
    inside the final 5 days before the meeting. Amber: anything else still outstanding.
    """
    df = load_board_pack().copy()
    t = today()
    days_to_meeting = (df["meeting_date"] - t).apply(lambda x: x.days)
    late = df["due_date"] < t
    df["rag"] = "Amber"
    df.loc[~df["status"].isin(DONE_PACK) & (late | (days_to_meeting <= RAG_WINDOW_DAYS)), "rag"] = "Red"
    df.loc[df["status"].isin(DONE_PACK), "rag"] = "Green"
    df["days_to_due"] = [(d - t).days for d in df["due_date"]]
    return df


AGEING_BUCKETS = ["Not yet due", "1–7 days", "8–14 days", "15–30 days", "30+ days"]


def actions_with_ageing() -> pd.DataFrame:
    df = load_actions().copy()
    t = today()
    df["days_overdue"] = [max((t - d).days, 0) if s != "Done" else 0
                          for d, s in zip(df["due_date"], df["status"])]

    def bucket(n: int) -> str:
        if n <= 0:
            return AGEING_BUCKETS[0]
        if n <= 7:
            return AGEING_BUCKETS[1]
        if n <= 14:
            return AGEING_BUCKETS[2]
        if n <= 30:
            return AGEING_BUCKETS[3]
        return AGEING_BUCKETS[4]

    df["ageing"] = df["days_overdue"].apply(bucket)
    return df


def to_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    """Write several DataFrames to one .xlsx with readable column widths."""
    from io import BytesIO

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.sheets[name[:31]]
            for i, col in enumerate(df.columns, start=1):
                width = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)]) + 2
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(width, 60)
            ws.freeze_panes = "A2"
    return buf.getvalue()


# ---------------------------------------------------------------------------
# CEO week helpers
# ---------------------------------------------------------------------------
CATEGORY_TARGETS = {"Customer": 0.30, "Internal": 0.20, "Focus": 0.20, "Investor": 0.15, "Hiring": 0.10,
                    "External/Industry": 0.05}  # panels, conferences, industry bodies — not customer time
TRAVEL_BUFFER_MIN = 90  # minimum buffer between travel and a meeting
NO_AGENDA_EXEMPT = {"Focus", "Travel"}


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def calendar_between(start: date, end: date) -> pd.DataFrame:
    cal = load_calendar()
    return cal[(cal["date"] >= start) & (cal["date"] <= end)]


def time_split(start: date, end: date) -> pd.DataFrame:
    """Hours and share by category (travel excluded), alongside the target share."""
    cal = calendar_between(start, end)
    cal = cal[cal["category"] != "Travel"]
    hours = cal.groupby("category")["hours"].sum().reindex(list(CATEGORY_TARGETS), fill_value=0.0)
    total = hours.sum()
    return pd.DataFrame({
        "category": hours.index,
        "hours": hours.values,
        "actual": (hours / total).values if total else 0.0,
        "target": [CATEGORY_TARGETS[c] for c in hours.index],
    })


def calendar_flags(start: date, end: date) -> pd.DataFrame:
    """Every diary problem in the window: conflicts, back-to-backs, travel squeezes, missing agendas."""
    cal = calendar_between(start, end).sort_values(["date", "start"])
    flags: list[dict] = []

    def add(kind, r, detail):
        flags.append({"date": r.date, "time": f"{r.start}–{r.end}", "flag": kind,
                      "meeting": r.title, "detail": detail})

    for _, day in cal.groupby("date"):
        rows = list(day.itertuples(index=False))
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                gap = _minutes(b.start) - _minutes(a.end)
                overlap = b.start < a.end and a.start < b.end
                if overlap:
                    add("Conflict", a, f"Overlaps {b.title} ({b.start}–{b.end})")
                elif "Travel" in (a.category, b.category):
                    in_person = b if a.category == "Travel" else a
                    if in_person.category != "Travel" and 0 <= gap < TRAVEL_BUFFER_MIN \
                            and "Video" not in str(in_person.location):
                        add("Travel gap", a, f"Only {gap} min before {b.title} ({b.start}, {b.location})")
                elif gap == 0 and not {a.category, b.category} & {"Focus"}:
                    add("Back-to-back", a, f"No break before {b.title} ({b.start})")

    for r in cal.itertuples(index=False):
        if not r.has_agenda and r.category not in NO_AGENDA_EXEMPT:
            add("No agenda", r, f"{r.category} · {r.location}")

    order = {"Conflict": 0, "Travel gap": 1, "No agenda": 2, "Back-to-back": 3}
    df = pd.DataFrame(flags, columns=["date", "time", "flag", "meeting", "detail"])
    return df.assign(_o=df["flag"].map(order)).sort_values(["date", "time", "_o"]).drop(columns="_o")


# ---------------------------------------------------------------------------
# Office health helpers
# ---------------------------------------------------------------------------
REPEAT_THRESHOLD = 3
HS_AMBER_DAYS = 30


def tickets_view() -> pd.DataFrame:
    df = load_tickets().copy()
    df["days_open"] = df["age_days"].where(df["status"] != "Resolved")
    df["repeat_issue"] = df["repeat_count"] >= REPEAT_THRESHOLD
    return df


def hs_rag() -> pd.DataFrame:
    df = load_hs_checks().copy()
    df["rag"] = "Green"
    df.loc[df["days_until_due"] <= HS_AMBER_DAYS, "rag"] = "Amber"
    df.loc[df["days_until_due"] < 0, "rag"] = "Red"
    return df


# ---------------------------------------------------------------------------
# Events helpers
# ---------------------------------------------------------------------------
RSVP_PENDING_SHARE = 0.20      # flag if more than this share is still pending…
RSVP_WINDOW_DAYS = 3           # …within this many days of the RSVP deadline
FINAL_NUMBERS_WINDOW_DAYS = 5  # flag when the venue needs confirmed numbers this soon
BUDGET_ALERT_SHARE = 0.90      # flag when this share of an event budget is committed


def checklist_view() -> pd.DataFrame:
    df = load_event_checklist().copy()
    t = today()
    df["days_to_due"] = [(d - t).days for d in df["due_date"]]
    df["overdue"] = ~df["done"] & (df["days_to_due"] < 0)
    return df


def events_view() -> pd.DataFrame:
    """Events with countdowns, RSVP shares, budget use and checklist completion."""
    t = today()
    df = load_events().copy()
    tasks = checklist_view().groupby("event").agg(
        tasks=("task", "size"), tasks_done=("done", "sum"), tasks_overdue=("overdue", "sum"))
    df = df.merge(tasks, left_on="event", right_index=True, how="left")
    for c in ("tasks", "tasks_done", "tasks_overdue"):
        df[c] = df[c].fillna(0).astype(int)
    df["days_to_event"] = [(d - t).days for d in df["date"]]
    df["days_to_rsvp_deadline"] = [(d - t).days for d in df["rsvp_deadline"]]
    df["days_to_final_numbers"] = [(d - t).days for d in df["final_numbers_due"]]
    df["pending_share"] = df["rsvp_pending"] / df["invited"]
    df["budget_used"] = df["committed_gbp"] / df["budget_gbp"]
    df["cost_per_head"] = (df["committed_gbp"] / df["rsvp_yes"].where(df["rsvp_yes"] > 0)).round(2)
    df["checklist_done"] = (df["tasks_done"] / df["tasks"].where(df["tasks"] > 0)).fillna(0.0)
    return df.sort_values("date").reset_index(drop=True)


def upcoming_events() -> pd.DataFrame:
    ev = events_view()
    return ev[ev["days_to_event"] >= 0].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Visitor helpers
# ---------------------------------------------------------------------------
VISIT_WINDOW_DAYS = 2  # flag any visit this close that isn't 100% ready
OFFICE_ADDRESS = "3rd Floor, 21 Copper Row, London EC2A 4LT"  # fictional
ARRIVAL_NOTES = (
    "Reception is on the ground floor; please bring photo ID to collect building passes. "
    "Nearest stations: Liverpool Street (6 min walk) and Moorgate (8 min). "
    "Guest Wi-Fi details will be on the welcome screen in your meeting room."
)
VISIT_AGENDAS = {
    "Product demo": ["Welcome and introductions", "Your priorities and success criteria",
                     "Live product demo", "Q&A and next steps"],
    "Due diligence": ["Welcome and introductions", "Company and control-environment overview",
                      "Document walkthrough and Q&A", "Follow-up requests and next steps"],
    "QBR": ["Welcome and introductions", "Quarter in review: service performance",
            "Roadmap update", "Priorities for next quarter"],
    "Partnership": ["Welcome and introductions", "Shared opportunity and goals",
                    "Commercial and technical fit", "Agreed next steps"],
    "Interview panel": ["Welcome and office tour", "Panel interview",
                        "Meet the team", "Close and next steps"],
}


def visits_view() -> pd.DataFrame:
    """Visits with a readiness % and the checks still missing, soonest first."""
    t = today()
    df = load_visits().copy()
    checks = df[list(VISIT_CHECKS)]
    df["readiness"] = checks.mean(axis=1)
    df["missing"] = [", ".join(VISIT_CHECKS[c] for c in VISIT_CHECKS if not row[c])
                     for _, row in checks.iterrows()]
    df["days_to_visit"] = [(d - t).days for d in df["date"]]
    return df.sort_values(["date", "time"]).reset_index(drop=True)


def visits_this_week() -> pd.DataFrame:
    mon, sun = week_bounds()
    v = visits_view()
    return v[(v["date"] >= mon) & (v["date"] <= sun)]


# ---------------------------------------------------------------------------
# Supplies & supplier helpers
# ---------------------------------------------------------------------------
CONTRACT_WINDOW_DAYS = 60
OFFICE_MONTHLY_BUDGET = 15000  # £ per month across contracted office suppliers


def supplies_view() -> pd.DataFrame:
    df = load_supplies().copy()
    df["reorder"] = df["stock"] <= df["reorder_level"]
    df["days_since_order"] = [(today() - d).days for d in df["last_ordered"]]
    return df


def supplier_tickets() -> pd.DataFrame:
    """Facilities tickets linked to a contracted supplier."""
    tv = tickets_view()
    return tv[tv["supplier"] != ""]


def suppliers_view() -> pd.DataFrame:
    df = load_suppliers().copy()
    df["days_to_contract_end"] = [(d - today()).days for d in df["contract_end"]]
    df["contract_ending"] = df["days_to_contract_end"].between(0, CONTRACT_WINDOW_DAYS)
    linked = supplier_tickets()
    repeats = linked[(linked["status"] != "Resolved") & linked["repeat_issue"]]
    df["repeat_tickets"] = [int((repeats["supplier"] == s).sum()) for s in df["supplier"]]
    df["repeat_issues"] = [
        "; ".join(f"{r.issue} (×{r.repeat_count})" for r in repeats[repeats["supplier"] == s].itertuples())
        for s in df["supplier"]
    ]
    return df


# ---------------------------------------------------------------------------
# Travel helpers
# ---------------------------------------------------------------------------
TRAVEL_WINDOW_DAYS = 7  # flag any trip this close that isn't 100% ready


def travel_view() -> pd.DataFrame:
    """Trips with readiness %. A hotel isn't needed (so isn't counted) for same-day trips."""
    t = today()
    df = load_travel().copy()
    df["nights"] = [(e - s).days for s, e in zip(df["start_date"], df["end_date"])]
    ready, missing = [], []
    for _, r in df.iterrows():
        needed = [c for c in TRAVEL_CHECKS if not (c == "hotel_booked" and r["nights"] == 0)]
        ready.append(sum(bool(r[c]) for c in needed) / len(needed))
        missing.append(", ".join(TRAVEL_CHECKS[c] for c in needed if not r[c]))
    df["readiness"] = ready
    df["missing"] = missing
    df["days_to_trip"] = [(s - t).days for s in df["start_date"]]
    return df.sort_values("start_date").reset_index(drop=True)
