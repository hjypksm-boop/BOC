"""AI helpers, running on Groq's hosted models.

Every public function returns (result, source) where source is "live" or "cached".
If no API key is configured, or a call fails for any reason, the caller gets a
fallback (cached file or template) so the demo never breaks.

Without a key, results saved in .ai_cache/ (committed to the repo) are still served,
so the deployed app shows real model output for every warmed-up click.

Secrets (.streamlit/secrets.toml):
    GROQ_API_KEY = "gsk_..."
    GROQ_MODEL   = "openai/gpt-oss-120b"   # optional override
"""
from __future__ import annotations

import functools
import hashlib
import inspect
import json
import re
from datetime import date
from pathlib import Path

import streamlit as st
from groq import Groq

from utils import data, fallbacks

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_MODEL = "openai/gpt-oss-120b"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".ai_cache"


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------
def _secret(name: str) -> str | None:
    try:
        value = st.secrets[name]
    except (KeyError, FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return None
    return value or None


def get_api_key() -> str | None:
    return _secret("GROQ_API_KEY")


def tidy(text: str) -> str:
    """House number style for model text: £18,000 (not £18 000) and 19% (not 19 %)."""
    text = re.sub(r"(?<=\d)[\u00a0\u202f ](?=\d{3}\b)", ",", text)
    return re.sub(r"(?<=\d)[\u00a0\u202f ]%", "%", text)


def _src(api_key: str | None) -> str:
    return "live" if api_key else "cached"


def get_model() -> str:
    return _secret("GROQ_MODEL") or DEFAULT_MODEL


def _ask_llm(api_key: str, system: str, messages: list[dict], schema: dict | None = None,
             max_tokens: int = 1500, reasoning: str = "low") -> str:
    """One chat completion; returns the text. Raises on any failure or truncated output.

    With a schema, the model is put in JSON mode and given the schema in the system prompt;
    the result is checked for the required top-level keys before being returned.
    """
    # max_retries=2: the SDK waits out 429s using Groq's retry-after (free tier is 8k tokens/min)
    client = Groq(api_key=api_key, timeout=60.0, max_retries=2)
    kwargs: dict = {}
    if get_model().startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = reasoning  # low keeps hidden reasoning from eating the token budget
    if schema:
        system += ("\n\nRespond with a single JSON object only, matching this JSON Schema exactly:\n"
                   + json.dumps(schema))
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(
        model=get_model(),
        messages=[{"role": "system", "content": system}, *messages],
        max_tokens=max_tokens,
        **kwargs,
    )
    choice = response.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise RuntimeError(f"Unexpected finish_reason: {choice.finish_reason}")
    text = choice.message.content.strip()
    if schema:
        missing = set(schema["required"]) - set(json.loads(text))
        if missing:
            raise ValueError(f"Response missing keys: {missing}")
    return text


def disk_cached(fn):
    """Cache successful results as JSON files in .ai_cache/, shared by the app and utils/warm_up.py.

    The key covers the function's source, the model and every argument except the API key,
    so changing a prompt, the model or the data produces a fresh call. Failures aren't cached.
    """
    sig = inspect.signature(fn)
    source = inspect.getsource(fn)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        bound = sig.bind(*args, **kwargs)
        keyed = {k: v for k, v in bound.arguments.items() if k != "api_key"}
        raw = json.dumps([fn.__name__, source, _PROMPTS, get_model(), keyed], sort_keys=True, default=str)
        path = CACHE_DIR / f"{fn.__name__}-{hashlib.sha256(raw.encode()).hexdigest()[:24]}.json"
        try:
            return json.loads(path.read_text())["result"]
        except (OSError, ValueError, KeyError):
            pass
        if not bound.arguments.get("api_key"):
            raise LookupError(f"No cached {fn.__name__} result and no API key")
        result = fn(*args, **kwargs)
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"result": result}, ensure_ascii=False))
            tmp.replace(path)
        except OSError:
            pass
        return result

    return wrapper


def build_context(brief: bool = False) -> str:
    """Everything the Tower knows, as compact text for the model.

    brief=True leaves out what the Weekly Brief's draft already carries (the red-flag list and the
    diary beyond this week), keeping that request under Groq's free-tier 8k tokens per minute.
    """
    t = data.today()
    board = data.next_board_date()
    mon, sun = data.week_bounds()
    upcoming = list(data.upcoming_events()["event"])  # noqa: F841 — used in a DataFrame.query
    parts = [
        f"Today: {t:%A %d %B %Y}. Next Board meeting: {board:%A %d %B %Y} ({(board - t).days} days away). "
        f"Board pack sections are due to the Company Secretary {data.RAG_WINDOW_DAYS} days before.",
        f"CEO customer-time target: {data.CUSTOMER_TIME_TARGET:.0%} of booked hours excluding travel.",
        "" if brief else "## Red flags already detected (severity-ranked)\n"
        + data.attention_items()[["severity", "area", "title", "detail"]].to_csv(index=False),
        "## CEO time split this week (share of booked hours excl. travel)\n" + data.time_split(mon, sun).assign(
            hours=lambda d: d["hours"].round(1),
            actual=lambda d: (d["actual"] * 100).round().astype(int).astype(str) + "%",
            target=lambda d: (d["target"] * 100).round().astype(int).astype(str) + "%",
        ).rename(columns={"actual": "actual_share", "target": "target_share"}).to_csv(index=False),
        "## Board pack (with RAG)\n" + data.board_pack_rag().drop(columns="meeting_date").to_csv(index=False),
        "## Action log (open actions; done ones omitted)\n" + data.actions_with_ageing().query("status != 'Done'")
        [["action", "owner", "source", "due_date", "status", "days_overdue"]].to_csv(index=False),
        ("## CEO diary, rest of this week\n" + data.calendar_between(t, sun).drop(columns="hours").to_csv(index=False))
        if brief else
        ("## CEO diary, next two weeks\n" + data.load_calendar().drop(columns="hours").to_csv(index=False)),
        "## CEO travel (readiness = share of checks done; hotel not needed for same-day trips)\n" + data.travel_view()
        .assign(readiness=lambda d: (d["readiness"] * 100).round().astype(int).astype(str) + "%")
        [["trip", "start_date", "end_date", "destination", "purpose", "readiness", "missing"]].to_csv(index=False),
        "## Open facilities tickets\n" + data.tickets_view().query("status != 'Resolved'")
        [["issue", "assigned_to", "status", "days_open", "repeat_count"]].to_csv(index=False),
        "## Health & safety checks\n" + data.hs_rag()[["check", "owner", "next_due", "rag"]].to_csv(index=False),
        "## Upcoming events (budget/committed in GBP; cost_per_head = committed / confirmed yes)\n"
        + data.upcoming_events()[["event", "type", "date", "venue", "status", "invited", "rsvp_yes", "rsvp_no", "rsvp_pending",
          "rsvp_deadline", "final_numbers_due", "budget_gbp", "committed_gbp", "cost_per_head",
          "tasks_done", "tasks", "tasks_overdue"]].to_csv(index=False),
        "## Open event checklist tasks (upcoming events; everything else is done)\n" + data.checklist_view()
        .query("not done and event in @upcoming")[["event", "task", "owner", "due_date", "overdue"]].to_csv(index=False),
        "## Event dietary requirements (counts of confirmed guests)\n" + "\n".join(
            f"{e}: " + ", ".join(f"{r.requirement} {r.count}" for r in g.itertuples() if r.count)
            for e, g in data.load_event_dietary().groupby("event", sort=False)),
        "## Visitors: clients, regulators and candidates (readiness = share of 7 checks done)\n" + data.visits_view().assign(
            readiness=lambda d: (d["readiness"] * 100).round().astype(int).astype(str) + "%",
        )[["date", "time", "visitor_org", "visitor_count", "host", "purpose", "room", "readiness",
           "missing"]].to_csv(index=False),
        "## Office supplies\n" + data.supplies_view()
        [["item", "stock", "reorder_level", "supplier"]].to_csv(index=False),
        f"## Office suppliers (monthly office budget £{data.OFFICE_MONTHLY_BUDGET:,})\n" + data.suppliers_view()
        [["supplier", "service", "contract_end", "days_to_contract_end", "monthly_cost_gbp", "open_issues",
          "repeat_issues", "satisfaction"]].to_csv(index=False),
        "## Automation backlog\n" + data.load_automations()
        [["process", "tool", "hours_saved_per_month", "status"]].to_csv(index=False),
    ]
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# 1. Transcript → actions
# ---------------------------------------------------------------------------
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Short imperative description of the task"},
                    "owner": {"type": "string", "description": "Role or person who committed to it"},
                    "due_date": {"type": "string", "description": "YYYY-MM-DD, or empty string if none given"},
                    "source": {"type": "string", "description": "Meeting type, e.g. ExCo, Board, Offsite, All-hands"},
                },
                "required": ["action", "owner", "due_date", "source"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["actions"],
    "additionalProperties": False,
}

EXTRACT_PROMPT = (
    "You extract action items from executive meeting transcripts for a business operations team. "
    "An action item is a concrete commitment someone made to do something. Ignore discussion, "
    "status updates and opinions that nobody committed to act on. Use the owner's role exactly as "
    "it appears in the transcript. Resolve relative or weekday dates to absolute YYYY-MM-DD dates "
    "using the meeting date given; leave due_date empty if no deadline was stated."
)


def load_cached_actions() -> list[dict]:
    return json.loads((DATA_DIR / "sample_actions.json").read_text())["actions"]


@disk_cached
def _extract(transcript: str, api_key: str, today_iso: str) -> list[dict]:
    text = _ask_llm(
        api_key, EXTRACT_PROMPT,
        [{"role": "user", "content": f"Today's date: {today_iso}\n\n<transcript>\n{transcript}\n</transcript>"}],
        schema=ACTION_SCHEMA,
    )
    return json.loads(text)["actions"]


def extract_actions(transcript: str) -> tuple[list[dict], str]:
    api_key = get_api_key()
    if transcript.strip():
        try:
            return _extract(transcript, api_key, data.today().isoformat()), _src(api_key)
        except Exception:  # noqa: BLE001 — any failure falls back to the cached demo output
            pass
    return load_cached_actions(), "cached"


# ---------------------------------------------------------------------------
# 2. CEO weekly brief
# ---------------------------------------------------------------------------
BRIEF_PROMPT = """You are the Business Operations Coordinator editing the CEO's Monday-morning brief \
for a ~200-person regulated fintech. The CEO has two minutes to read it.

You are given the operational data and a DRAFT brief that was generated from it. Your job is to edit \
the draft into the best possible one-page brief (300-380 words):
- Rewrite the Headline as two sharp sentences: the single most important thing this week, and overall status.
- Keep the 5-7 most serious Red flags, most urgent first, tightly worded.
- Keep 3-5 Decisions needed, phrased crisply as questions. Choose them ONLY from the draft's decisions.
- Keep the Week ahead to the remaining working days, one bullet per day.

Strict accuracy rules, because this goes to the CEO of a compliance company:
- Every fact, number, date, name and option must already appear in the draft or the data.
- Never invent amounts of money, suppliers, deadlines, regulators, options or new dates.
- In the Week ahead, copy times exactly from the draft; never add a time the draft doesn't give.
- Keep the draft's Markdown shape: one "# " title, the italic byline, "## " headings, "- " bullets, **bold**.
- Output the brief only: no preamble, no closing remarks. Plain, calm British English."""


@disk_cached
def _brief(context: str, draft: str, api_key: str) -> str:
    content = f"<data>\n{context}\n</data>\n\n<draft>\n{draft}\n</draft>"
    return _ask_llm(api_key, BRIEF_PROMPT, [{"role": "user", "content": content}], max_tokens=3000,
                    reasoning="medium")


def generate_brief() -> tuple[str, str]:
    api_key = get_api_key()
    try:
        return tidy(_brief(build_context(brief=True), fallbacks.build_sample_brief(), api_key)), _src(api_key)
    except Exception:  # noqa: BLE001
        pass
    return (DATA_DIR / "sample_brief.md").read_text(), "cached"


# ---------------------------------------------------------------------------
# 3. Ask the Tower
# ---------------------------------------------------------------------------
ASK_PROMPT = """You are "the Tower", the operations assistant for the CEO's office at a ~200-person \
regulated fintech. Answer questions using ONLY the data below (Board, actions, diary, facilities, \
health & safety, events, visitors, supplies and suppliers). If the data doesn't answer the \
question, say so briefly and suggest what would. Never invent figures, names or options. \
Use the right table: "actions" means rows in the Action log (not health & safety checks or Board pack \
sections); "most overdue actions" means the highest COUNT of overdue rows. Count rows carefully, and copy \
days-late figures exactly from the data rather than recalculating them. Show shares as whole percentages, \
never decimals or working. Refer to people only by role (e.g. "the CEO"); never use he/she. Stay factual \
and calm; do not dramatise. Only include items relevant to the question. For the Board: every Board pack section \
with RAG Red (overdue, or not started close to the deadline) and every overdue Board-sourced action, nothing else. \
For an event's readiness: RSVPs, budget and EVERY open checklist task with its due date. The Action log has due dates, not start dates; never write "open since". Lead with the answer in one sentence, then give \
supporting detail as a short bullet list with specific names, dates and numbers. Keep it under \
150 words. Markdown is fine; no tables.

<data>
{context}
</data>"""

NO_KEY_ANSWER = ("I can only answer the suggested questions in offline demo mode. "
                 "Add a Groq API key to `.streamlit/secrets.toml` to ask anything.")


def load_canned_answers() -> dict[str, str]:
    return json.loads((DATA_DIR / "sample_answers.json").read_text())


@disk_cached
def _ask_fresh(question: str, context: str, api_key: str) -> str:
    """A question with no prior conversation: cacheable, so suggested questions are instant once warmed."""
    return _ask_llm(api_key, ASK_PROMPT.format(context=context), [{"role": "user", "content": question}],
                    max_tokens=2000, reasoning="medium")


def ask_tower(question: str, history: list[dict]) -> tuple[str, str]:
    """history: prior {role, content} turns (not including this question)."""
    api_key = get_api_key()
    try:
        # Suggested questions are self-contained, so they always use the (warmable) cache
        if not history or question in fallbacks.SUGGESTED_QUESTIONS:
            return tidy(_ask_fresh(question.strip(), build_context(), api_key)), _src(api_key)
    except Exception:  # noqa: BLE001
        pass
    if api_key:
        try:
            messages = [{"role": m["role"], "content": m["content"]} for m in history[-10:]]
            messages.append({"role": "user", "content": question})
            return tidy(_ask_llm(api_key, ASK_PROMPT.format(context=build_context()), messages)), "live"
        except Exception:  # noqa: BLE001
            pass
    return load_canned_answers().get(question, NO_KEY_ANSWER), "cached"


# ---------------------------------------------------------------------------
# 4. Chase emails
# ---------------------------------------------------------------------------
CHASE_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}

CHASE_PROMPT = """You draft short chase emails from the Business Operations Coordinator to senior \
leaders about overdue actions. Tone: warm, polite, direct; peer-to-peer, never scolding. \
Body: 60-110 words, plain text, greeting "Hi <owner role>,", sign off "Thanks,\\nBusiness Operations". \
Ask for a status update and, if needed, a realistic new date; offer help unblocking. \
If the action came from the Board, mention wanting to update the CEO before the next Board meeting. \
Subject: under 60 characters."""


@disk_cached
def _chase(payload: str, api_key: str) -> dict[str, str]:
    return json.loads(_ask_llm(api_key, CHASE_PROMPT, [{"role": "user", "content": payload}], schema=CHASE_SCHEMA))


def chase_payload(action: str, owner: str, source: str, due: date, status: str) -> str:
    return json.dumps({
        "action": action, "owner": owner, "source_meeting": source, "status": status,
        "due_date": due.isoformat(), "days_overdue": (data.today() - due).days,
        "today": data.today().isoformat(), "next_board_meeting": data.next_board_date().isoformat(),
    })


def draft_chase(action: str, owner: str, source: str, due: date, status: str) -> tuple[dict[str, str], str]:
    api_key = get_api_key()
    try:
        return _chase(chase_payload(action, owner, source, due, status), api_key), _src(api_key)
    except Exception:  # noqa: BLE001
        pass
    return fallbacks.chase_template(action, owner, source, due, status), "cached"


# ---------------------------------------------------------------------------
# 5. RSVP reminder
# ---------------------------------------------------------------------------
RSVP_PROMPT = """You draft a short, friendly all-staff reminder from Business Operations to colleagues \
who haven't yet replied to an event invitation. Tone: warm, upbeat, light-touch; never guilt-tripping. \
Body: 70-120 words, plain text, greeting "Hi all,", sign off "Thanks,\\nBusiness Operations". \
Say what the event is, when and where, and the RSVP deadline; explain the venue needs final numbers \
(give that date); ask people to reply yes or no either way, and to include any dietary or accessibility \
needs. Use ONLY the facts given; never invent times, links, names or details. Subject: under 60 characters."""


def _long(d: date) -> str:
    return f"{d:%A} {d.day} {d:%B}"


@disk_cached
def _rsvp(payload: str, api_key: str) -> dict[str, str]:
    return json.loads(_ask_llm(api_key, RSVP_PROMPT, [{"role": "user", "content": payload}], schema=CHASE_SCHEMA))


def rsvp_payload(event: str) -> str:
    r = data.events_view().set_index("event").loc[event]
    return json.dumps({
        "event": event, "type": r["type"], "date": _long(r["date"]), "venue": r["venue"],
        "rsvp_deadline": _long(r["rsvp_deadline"]), "final_numbers_due_to_venue": _long(r["final_numbers_due"]),
        "invited": int(r["invited"]), "not_yet_replied": int(r["rsvp_pending"]), "today": _long(data.today()),
    })


def draft_rsvp_reminder(event: str) -> tuple[dict[str, str], str]:
    api_key = get_api_key()
    try:
        return _rsvp(rsvp_payload(event), api_key), _src(api_key)
    except Exception:  # noqa: BLE001
        pass
    return fallbacks.rsvp_template(event), "cached"


# ---------------------------------------------------------------------------
# 6. Visitor pack
# ---------------------------------------------------------------------------
VISIT_PROMPT = """You draft a welcome email from Business Operations to an external visiting party \
ahead of their visit to our London office. Tone: warm, professional, concise British English. \
Body: 130-200 words, plain text, greeting "Dear <visitor_org> team,", sign off \
"Kind regards,\\nBusiness Operations". Include, in this order: a one-line welcome with the date, time and \
purpose; the office address; the arrival instructions; who will meet them (the host role, by role only) \
and which room; the agenda as "- " bullet lines, using exactly the agenda items given. Use ONLY the facts \
given; never invent names, phone numbers, durations or links. Subject: under 60 characters."""


@disk_cached
def _visitor_pack(payload: str, api_key: str) -> dict[str, str]:
    return json.loads(_ask_llm(api_key, VISIT_PROMPT, [{"role": "user", "content": payload}], schema=CHASE_SCHEMA))


def visit_payload(idx: int) -> str:
    r = data.visits_view().loc[idx]
    return json.dumps({
        "visitor_org": r["visitor_org"], "visitor_count": int(r["visitor_count"]),
        "date": _long(r["date"]), "time": r["time"], "purpose": r["purpose"],
        "host_role": r["host"], "room": r["room"], "office_address": data.OFFICE_ADDRESS,
        "arrival_instructions": data.ARRIVAL_NOTES, "agenda": data.VISIT_AGENDAS[r["purpose"]],
    })


def draft_visitor_pack(idx: int) -> tuple[dict[str, str], str]:
    """idx: row index into data.visits_view()."""
    api_key = get_api_key()
    try:
        return _visitor_pack(visit_payload(idx), api_key), _src(api_key)
    except Exception:  # noqa: BLE001
        pass
    return fallbacks.visitor_pack_template(idx), "cached"


_PROMPTS = hashlib.sha256((EXTRACT_PROMPT + BRIEF_PROMPT + ASK_PROMPT + CHASE_PROMPT + RSVP_PROMPT
                           + VISIT_PROMPT).encode()).hexdigest()[:12]
