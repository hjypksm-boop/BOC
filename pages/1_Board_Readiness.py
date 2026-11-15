import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import ai, data, documents, ui

ui.setup("Board Readiness")
ACCENT, MUTED, RAG_ICON = ui.ACCENT, ui.MUTED, ui.RAG_ICON

board_date = data.next_board_date()
export_slot = ui.header(
    "Board Readiness",
    f"Next Board meeting: {board_date:%A} {board_date.day} {board_date:%B %Y} · "
    f"{(board_date - data.today()).days} days away",
)

# ===================================================================== Board pack
st.header("Board pack tracker")
pack = data.board_pack_rag()
rag_counts = pack["rag"].value_counts()
submitted = pack["status"].isin(data.DONE_PACK).sum()

c = st.columns(3)
c[0].metric("Sections in", f"{submitted} / {len(pack)}", border=True)
c[1].metric("Red", int(rag_counts.get("Red", 0)), border=True,
            help=f"Not submitted and either past due or inside the final {data.RAG_WINDOW_DAYS} days before the meeting")
c[2].metric("Amber", int(rag_counts.get("Amber", 0)), border=True,
            help="Outstanding but still inside its deadline")

pack_view = (
    pack.assign(
        _order=pack["rag"].map({"Red": 0, "Amber": 1, "Green": 2}),
        RAG=pack["rag"].map(RAG_ICON),
    )
    .sort_values(["_order", "due_date"])
    [["RAG", "section", "owner", "status", "due_date", "days_to_due"]]
)
st.dataframe(
    pack_view,
    hide_index=True,
    width="stretch",
    column_config={
        "section": "Section",
        "owner": st.column_config.TextColumn("Owner", width=180),
        "status": "Status",
        "due_date": st.column_config.DateColumn("Due", format="ddd D MMM"),
        "days_to_due": st.column_config.NumberColumn("Days to due", help="Negative = overdue"),
    },
)
st.caption(f"RAG rule: Green = submitted or approved · Red = not submitted and past due, or within "
           f"{data.RAG_WINDOW_DAYS} days of the meeting · Amber = outstanding, still in time.")

# ===================================================================== Action log
st.header("Action log")
acts = data.actions_with_ageing()

f = st.columns(3)
owners = f[0].multiselect("Owner", sorted(acts["owner"].unique()), placeholder="All owners")
sources = f[1].multiselect("Source", sorted(acts["source"].unique()), placeholder="All sources")
statuses = f[2].multiselect("Status", ["Open", "In progress", "Done"],
                            default=["Open", "In progress"], placeholder="All statuses")

filtered = acts
if owners:
    filtered = filtered[filtered["owner"].isin(owners)]
if sources:
    filtered = filtered[filtered["source"].isin(sources)]
if statuses:
    filtered = filtered[filtered["status"].isin(statuses)]

# Ageing chart: outstanding actions in the current filter, by how overdue they are
outstanding = filtered[filtered["status"] != "Done"]
counts = outstanding["ageing"].value_counts().reindex(data.AGEING_BUCKETS, fill_value=0)
fig = go.Figure(go.Bar(
    x=counts.index, y=counts.values,
    marker=dict(color=[MUTED] + [ACCENT] * (len(counts) - 1), cornerradius=4,
                line=dict(width=0)),
    text=[str(v) if v else "" for v in counts.values], textposition="outside",
    hovertemplate="%{x}: %{y} action(s)<extra></extra>",
))
fig.update_layout(
    title=dict(text="Outstanding actions by days overdue", font=dict(size=15)),
    height=280, margin=dict(l=8, r=8, t=48, b=8), bargap=0.45, showlegend=False,
    yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.15)", zeroline=False,
               rangemode="tozero", dtick=1, title=None),
    xaxis=dict(title=None),
)
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

st.dataframe(
    filtered.sort_values(["days_overdue", "due_date"], ascending=[False, True])
    [["action", "owner", "source", "status", "raised_date", "due_date", "days_overdue"]],
    hide_index=True,
    width="stretch",
    column_config={
        "action": st.column_config.TextColumn("Action", width="large"),
        "owner": st.column_config.TextColumn("Owner", width=180),
        "source": "Source",
        "status": "Status",
        "raised_date": st.column_config.DateColumn("Raised", format="D MMM"),
        "due_date": st.column_config.DateColumn("Due", format="D MMM"),
        "days_overdue": st.column_config.NumberColumn("Days overdue"),
    },
)
st.caption(f"{len(filtered)} of {len(acts)} actions shown.")

# --------------------------------------------------------------------- chase overdue actions
overdue_rows = filtered[(filtered["status"] != "Done") & (filtered["days_overdue"] > 0)] \
    .sort_values("days_overdue", ascending=False)
st.subheader(f"Chase overdue actions · {len(overdue_rows)}")
if overdue_rows.empty:
    st.caption("Nothing overdue in the current filter.")

for idx, r in overdue_rows.iterrows():
    key = f"chase_{idx}"
    with st.container(border=True):
        st.markdown(
            f"<p class='item-title'>{r.action}</p>"
            f"<p class='item-detail'>{r.owner} · {r.source} · {r.status} · "
            f"{data._days(r.days_overdue)} overdue</p>",
            unsafe_allow_html=True,
        )
        if key not in st.session_state:
            if st.button("Draft chase", key=f"btn_{key}", icon=":material/edit_note:"):
                with st.spinner("Drafting…"):
                    st.session_state[key], _ = ai.draft_chase(r.action, r.owner, r.source, r.due_date, r.status)
                st.rerun()
        else:
            draft = st.session_state[key]
            subject = st.text_input("Subject", draft["subject"], key=f"subj_{key}")
            body = st.text_area("Email", draft["body"], height=200, key=f"body_{key}")
            with st.container(horizontal=True):
                st.link_button("Open in email", documents.mailto(subject, body), icon=":material/mail:",
                               type="primary")
                if st.button("Discard", key=f"discard_{key}", type="tertiary"):
                    for k in (key, f"subj_{key}", f"body_{key}"):
                        st.session_state.pop(k, None)
                    st.rerun()

# ===================================================================== AI extraction
st.header("AI: Transcript → Actions")
st.write("Paste a meeting transcript and AI pulls out every commitment with an owner and a deadline, "
         "ready to drop into the action log.")

transcript = st.text_area(
    "Meeting transcript",
    value=(data.DATA_DIR / "sample_transcript.txt").read_text(),
    height=260,
)
if st.button("Extract actions", type="primary"):
    with st.spinner("Reading the transcript…"):
        st.session_state["extracted"], _ = ai.extract_actions(transcript)

extracted = pd.DataFrame(st.session_state.get("extracted", []))
if not extracted.empty:
    extracted["due_date"] = pd.to_datetime(extracted["due_date"], errors="coerce").dt.date
    st.dataframe(
        extracted,
        hide_index=True,
        width="stretch",
        column_config={
            "action": st.column_config.TextColumn("Action", width="large"),
            "owner": st.column_config.TextColumn("Owner", width=180),
            "due_date": st.column_config.DateColumn("Due", format="ddd D MMM"),
            "source": "Source",
        },
    )
    st.caption(f"{len(extracted)} actions extracted.")

# ===================================================================== Export
sheets = {
    "Board pack": pack_view.assign(RAG=pack_view["RAG"].str.split(" ").str[-1]),
    "Action log": filtered.drop(columns=["ageing"]),
}
if not extracted.empty:
    sheets["Extracted actions"] = extracted
ui.export_button(export_slot, sheets, "board_readiness")
