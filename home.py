import streamlit as st

from utils import ai, data, documents, fallbacks, ui

ui.setup("")
SHOW_FIRST = 10

# ---------------------------------------------------------------- guided tour
TOUR = [
    ("Headline numbers",
     "Five tiles give the state of play at a glance: days to the Board, overdue actions, how much of the "
     "CEO's time is with customers, open facilities tickets and hours saved by automation."),
    ("CEO Weekly Brief",
     "One click turns everything below into a one-page Monday brief for the CEO: headline, red flags, "
     "decisions needed and the week ahead. Download it as Word or open it as an email."),
    ("Needs your attention",
     "Every red flag from every page, ranked most urgent first: late Board papers, overdue actions, diary "
     "clashes, H&S checks, events, visits and suppliers. Each card links to the page with the detail."),
    ("Ask the Tower",
     "Ask plain-English questions about the data, or tap a suggested question to start. Answers only use "
     "the data in this app."),
    ("Drill into the detail",
     "Use the sidebar on the left to open each area: Board Readiness, CEO Week, Office & Events and the "
     "Automation Backlog. 'About this demo' explains who built it and why."),
]
st.session_state.setdefault("tour_step", None)


def _tour_go(step: int | None) -> None:
    st.session_state["tour_step"] = step


def tour_callout(step: int) -> None:
    """Show this step's callout if the tour is on it."""
    if st.session_state["tour_step"] != step:
        return
    title, text = TOUR[step]
    last = step == len(TOUR) - 1
    with st.container(border=True, key=f"tourbox_{step}"):
        st.markdown(f"<span class='meta'>Tour · step {step + 1} of {len(TOUR)}</span>"
                    f"<p class='item-title'>{title}</p><p class='item-detail'>{text}</p>",
                    unsafe_allow_html=True)
        with st.container(horizontal=True):
            if step:
                st.button("Back", key=f"tour_back_{step}", on_click=_tour_go, args=(step - 1,),
                          icon=":material/arrow_back:")
            st.button("Finish" if last else "Next", key=f"tour_next_{step}", type="primary",
                      on_click=_tour_go, args=(None if last else step + 1,),
                      icon=":material/check:" if last else ":material/arrow_forward:")
            if not last:
                st.button("End tour", key=f"tour_end_{step}", type="tertiary", on_click=_tour_go, args=(None,))


with st.container(horizontal=True, vertical_alignment="bottom"):
    st.title("Ops Control Tower")
    st.space("stretch")
    if st.session_state["tour_step"] is None:
        st.button("Start tour", icon=":material/tour:", on_click=_tour_go, args=(0,))
st.caption("Demo · illustrative data only")
tour_callout(4)
tour_callout(0)

# ---------------------------------------------------------------- KPI tiles
board_date = data.next_board_date()
days_to_board = (board_date - data.today()).days
overdue = data.overdue_actions()
open_actions = (data.load_actions()["status"] != "Done").sum()
share = data.customer_time_share()
gap_pts = round((share - data.CUSTOMER_TIME_TARGET) * 100)
tickets = data.open_tickets()
repeats = (tickets["repeat_count"] >= 3).sum()
auto = data.load_automations()
hours_total = auto["hours_saved_per_month"].sum()
hours_live = auto.loc[auto["status"] == "Live", "hours_saved_per_month"].sum()

cols = st.columns(5)
cols[0].metric("Days to Board", days_to_board, border=True,
               help=f"Next Board meeting: {board_date:%A} {board_date.day} {board_date:%B}")
cols[1].metric("Overdue actions", len(overdue), delta=f"of {open_actions} open",
               delta_color="off", delta_arrow="off", border=True,
               help="Board, offsite, all-hands and ExCo actions past their due date")
cols[2].metric("Customer time", f"{share:.0%}", delta=f"{gap_pts:+d} pts vs 30% target",
               border=True, help="Share of the CEO's booked hours this week (excl. travel) with customers")
cols[3].metric("Open facilities tickets", len(tickets), delta=f"{repeats} repeat issues",
               delta_color="off", delta_arrow="off", border=True)
cols[4].metric("Hours saved / month", f"{hours_total:g}", delta=f"{hours_live:g} h already live",
               delta_color="off", delta_arrow="off", border=True,
               help="Across all automation ideas, pilots and live fixes")

# ---------------------------------------------------------------- weekly brief
st.write("")
tour_callout(1)
if st.button("Generate CEO Weekly Brief", type="primary", icon=":material/description:"):
    with st.spinner("Writing the brief…"):
        st.session_state["brief"], _ = ai.generate_brief()

if brief := st.session_state.get("brief"):
    with st.container(border=True):
        # Step headings down so the brief sits inside the page rather than competing with it
        st.markdown(brief.replace("\n## ", "\n#### ").replace("# ", "### ", 1))
    title = brief.splitlines()[0].lstrip("# ").strip()
    with st.container(horizontal=True):
        st.download_button(
            "Download .docx", data=documents.markdown_to_docx(brief),
            file_name=f"CEO_Weekly_Brief_{data.today():%Y-%m-%d}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            icon=":material/download:",
        )
        st.link_button("Open as email", documents.mailto(title, documents.markdown_to_plain(brief)),
                       icon=":material/mail:")

left, right = st.columns([3, 2], gap="large")

# ---------------------------------------------------------------- attention list
with left:
    items = data.attention_items()
    counts = items["severity"].value_counts()
    tour_callout(2)
    st.subheader("Needs your attention")
    st.markdown(
        f"<span class='meta'>{counts.get('Critical', 0)} critical · {counts.get('High', 0)} high · "
        f"{counts.get('Medium', 0)} medium · {counts.get('Low', 0)} low — most urgent first</span>",
        unsafe_allow_html=True,
    )

    for item in items.head(SHOW_FIRST).itertuples():
        ui.flag_card(item, link=True)

    if len(items) > SHOW_FIRST:
        with st.expander(f"Show {len(items) - SHOW_FIRST} more"):
            for item in items.iloc[SHOW_FIRST:].itertuples():
                ui.flag_card(item, link=True)

# ---------------------------------------------------------------- Ask the Tower
st.session_state.setdefault("chat", [])


def _use_chip() -> None:
    st.session_state["pending_q"] = st.session_state["chip"]
    st.session_state["chip"] = None


with right:
    tour_callout(3)
    st.subheader("Ask the Tower")
    st.markdown("<span class='meta'>Plain-English questions about the Board, diary, office, events and actions.</span>",
                unsafe_allow_html=True)
    st.pills("Suggested questions", fallbacks.SUGGESTED_QUESTIONS, key="chip",
             on_change=_use_chip, label_visibility="collapsed")
    thread = st.container(height=440, border=True)
    typed = st.chat_input("Ask a question…", key="ask")
    question = typed or st.session_state.pop("pending_q", None)

    if question:
        history = list(st.session_state["chat"])
        st.session_state["chat"].append({"role": "user", "content": question})
        with thread, st.spinner("Checking the data…"):
            answer, _ = ai.ask_tower(question, history)
        st.session_state["chat"].append({"role": "assistant", "content": answer})

    with thread:
        if not st.session_state["chat"]:
            st.caption("Pick a suggested question or type your own below.")
        for msg in st.session_state["chat"]:
            with st.chat_message(msg["role"], avatar=":material/person:" if msg["role"] == "user"
                                 else ":material/cell_tower:"):
                st.markdown(msg["content"])
