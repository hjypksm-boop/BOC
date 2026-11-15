"""Pre-generate every AI result the demo might show, so clicks are instant on the day.

Run on the morning of the demo, after refreshing the data:
    .venv/bin/python utils/generate_data.py
    .venv/bin/python utils/warm_up.py

Results are saved in .ai_cache/ and picked up by the app straight away (no restart needed).
They're keyed on the data and its pinned demo date (data/demo_date.txt), so re-run it if you
regenerate the data, then commit .ai_cache/ so the deployed app works without a key. Takes a few minutes on
Groq's free tier, which allows ~8k tokens per minute; the script waits out rate limits itself.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.getLogger("streamlit").setLevel(logging.ERROR)

import groq  # noqa: E402

from utils import ai, data, fallbacks  # noqa: E402

MAX_ATTEMPTS = 4


def run(label: str, fn) -> bool:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        start = time.time()
        try:
            fn()
            print(f"  ✓ {label} ({time.time() - start:.1f}s)")
            return True
        except groq.RateLimitError:
            if attempt == MAX_ATTEMPTS:
                break
            print(f"    rate limited, waiting 30s… ({label})")
            time.sleep(30)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {label}: {type(e).__name__}: {str(e)[:200]}")
            return False
    print(f"  ✗ {label}: still rate limited after {MAX_ATTEMPTS} attempts")
    return False


def main() -> None:
    key = ai.get_api_key()
    if not key:
        sys.exit("No GROQ_API_KEY in .streamlit/secrets.toml — nothing to warm up (the app will use cached fallbacks).")

    context = ai.build_context()
    jobs: list[tuple[str, callable]] = [
        ("Transcript → actions", lambda: ai._extract(
            (data.DATA_DIR / "sample_transcript.txt").read_text(), key, data.today().isoformat())),
    ]
    for r in data.overdue_actions().itertuples():
        jobs.append((f"Chase: {r.action[:50]}", lambda r=r: ai._chase(
            ai.chase_payload(r.action, r.owner, r.source, r.due_date, r.status), key)))
    for r in data.upcoming_events().itertuples():
        if r.rsvp_pending:
            jobs.append((f"RSVP reminder: {r.event}", lambda e=r.event: ai._rsvp(ai.rsvp_payload(e), key)))
    for idx, r in data.visits_view().iterrows():
        jobs.append((f"Visitor pack: {r.visitor_org}", lambda i=idx: ai._visitor_pack(ai.visit_payload(i), key)))
    jobs.append(("CEO weekly brief",lambda: ai._brief(ai.build_context(brief=True), fallbacks.build_sample_brief(), key)))
    for q in fallbacks.SUGGESTED_QUESTIONS:
        jobs.append((f"Ask: {q}", lambda q=q: ai._ask_fresh(q, context, key)))

    print(f"Warming {len(jobs)} AI results with {ai.get_model()}…")
    ok = sum(run(label, fn) for label, fn in jobs)

    if "--quiet" not in sys.argv:
        print("\n" + "=" * 70 + "\nREVIEW: what the CEO will see (re-run after deleting .ai_cache/ to regenerate)\n" + "=" * 70)
        for label, fn in jobs:
            if label == "CEO weekly brief" or label.startswith("Ask:"):
                try:
                    print(f"\n### {label}\n{fn()}")
                except Exception:  # noqa: BLE001
                    pass
    print(f"\n{ok}/{len(jobs)} ready." + ("" if ok == len(jobs) else
          " Anything that failed will still work in the app — it'll call live or fall back."))


if __name__ == "__main__":
    main()
