import plotly.graph_objects as go
import streamlit as st

from utils import data, ui

ui.setup("Automation Backlog")
export_slot = ui.header("Automation Backlog", "Manual admin we can take off people's plates")

STATUS_ORDER = ["Live", "Piloting", "Idea"]
STATUS_COLOUR = {"Live": ui.ACCENT, "Piloting": ui.ACCENT_MID, "Idea": ui.ACCENT_LIGHT}
WORKING_DAY_HOURS = 7.5

auto = data.load_automations()
total = auto["hours_saved_per_month"].sum()
live = auto.loc[auto["status"] == "Live", "hours_saved_per_month"].sum()

# ----------------------------------------------------------------- hero number
st.markdown(
    f"""<div class="hero">
          <div class="meta">Hours saved per month, across the whole backlog</div>
          <div class="hero-value">{total:g}<span class="hero-unit">hours / month</span></div>
          <div class="hero-sub">≈ {total * 12:,.0f} hours a year · about {total / WORKING_DAY_HOURS:.1f} working days
          every month · {live:g} h already live</div>
        </div>""",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------- status breakdown
by_status = (
    auto.groupby("status")
    .agg(hours=("hours_saved_per_month", "sum"), count=("process", "count"))
    .reindex(STATUS_ORDER, fill_value=0)
)
plot = by_status.iloc[::-1]  # Live at the top
fig = go.Figure(go.Bar(
    y=plot.index, x=plot["hours"], orientation="h",
    marker=dict(color=[STATUS_COLOUR[s] for s in plot.index], cornerradius=4, line=dict(width=0)),
    text=[f"{h:g} h · {n} automation{'s' if n != 1 else ''}" for h, n in zip(plot["hours"], plot["count"])],
    textposition="outside", cliponaxis=False,
    hovertemplate="<b>%{y}</b><br>%{x:g} hours/month<extra></extra>",
))
ui.style_chart(fig, "Hours saved by status", height=240)
fig.update_layout(bargap=0.4, showlegend=False)
fig.update_xaxes(range=[0, by_status["hours"].max() * 1.6], ticksuffix=" h")
ui.show_chart(fig)

# ----------------------------------------------------------------- table
st.header("Backlog")
table = (
    auto.assign(_o=auto["status"].map({s: i for i, s in enumerate(STATUS_ORDER)}))
    .sort_values(["_o", "hours_saved_per_month"], ascending=[True, False])
    .drop(columns="_o")
)
st.dataframe(
    table, hide_index=True, width="stretch",
    column_config={
        "process": st.column_config.TextColumn("Manual process", width=280),
        "fix": st.column_config.TextColumn("Fix", width=360),
        "tool": st.column_config.TextColumn("Tool", width=130),
        "hours_saved_per_month": st.column_config.ProgressColumn(
            "Hours / month", min_value=0, max_value=float(auto["hours_saved_per_month"].max()), format="%.1f"),
        "status": st.column_config.TextColumn("Status", width=90),
    },
)

ui.export_button(export_slot, {
    "Backlog": table,
    "By status": by_status.reset_index(),
}, "automation_backlog")
