from datetime import timedelta

import plotly.graph_objects as go
import streamlit as st

from utils import data, ui

ui.setup("CEO Week")
export_slot = ui.header("CEO Week", "Where the CEO's time is going, and what in the diary needs fixing")

# ----------------------------------------------------------------- period
this_mon, this_sun = data.week_bounds()
periods = {
    "This week": (this_mon, this_sun),
    "Next week": (this_mon + timedelta(days=7), this_sun + timedelta(days=7)),
    "Next 2 weeks": (data.today(), this_sun + timedelta(days=7)),
}
choice = st.segmented_control("Period", list(periods), default="This week", label_visibility="collapsed") \
    or "This week"
start, end = periods[choice]
st.caption(f"{start:%a %-d %b} – {end:%a %-d %b}")

split = data.time_split(start, end)
flags = data.calendar_flags(start, end)
flag_counts = flags["flag"].value_counts()
customer = split.set_index("category").loc["Customer"]

# ----------------------------------------------------------------- KPI tiles
c = st.columns(5)
c[0].metric("Customer time", f"{customer.actual:.0%}",
            delta=f"{round((customer.actual - customer.target) * 100):+d} pts vs {customer.target:.0%} target",
            border=True, help="Share of booked hours (excluding travel) spent with customers")
c[1].metric("Conflicts", int(flag_counts.get("Conflict", 0)), border=True,
            help="Two entries overlapping in the diary")
c[2].metric("No agenda", int(flag_counts.get("No agenda", 0)), border=True,
            help="Meetings without an agenda (focus time and travel excluded)")
c[3].metric("Travel gaps", int(flag_counts.get("Travel gap", 0)), border=True,
            help=f"Less than {data.TRAVEL_BUFFER_MIN} min between travel and an in-person meeting")
c[4].metric("Back-to-back", int(flag_counts.get("Back-to-back", 0)), border=True,
            help="Meetings with no break in between")

# ----------------------------------------------------------------- time split chart
order = split.sort_values("target")  # largest target at the top of a horizontal chart
fig = go.Figure()
fig.add_bar(
    y=order["category"], x=order["actual"], orientation="h", name="Actual",
    marker=dict(color=ui.ACCENT, cornerradius=4, line=dict(width=0)),
    text=[f"{v:.0%}" for v in order["actual"]], textposition="outside", cliponaxis=False,
    customdata=order[["hours", "target"]].values,
    hovertemplate="<b>%{y}</b><br>Actual %{x:.0%} (%{customdata[0]:.1f} h)"
                  "<br>Target %{customdata[1]:.0%}<extra></extra>",
)
fig.add_scatter(
    y=order["category"], x=order["target"], mode="markers", name="Target",
    marker=dict(symbol="line-ns", size=26, line=dict(width=3, color=ui.MUTED)),
    hovertemplate="<b>%{y}</b><br>Target %{x:.0%}<extra></extra>",
)
ui.style_chart(fig, "Time split by category vs target", height=320)
fig.update_layout(bargap=0.4)
fig.update_xaxes(tickformat=".0%", range=[0, max(split["actual"].max(), split["target"].max()) * 1.25])
ui.show_chart(fig)

# ----------------------------------------------------------------- diary flags
st.header("Diary flags")
kinds = ["Conflict", "Travel gap", "No agenda", "Back-to-back"]
shown = st.pills("Show", kinds, selection_mode="multi", default=kinds, label_visibility="collapsed")
view = flags[flags["flag"].isin(shown or kinds)]
if view.empty:
    st.success("Nothing to fix in this period.")
else:
    st.dataframe(
        view, hide_index=True, width="stretch",
        column_config={
            "date": st.column_config.DateColumn("Date", format="ddd D MMM"),
            "time": "Time",
            "flag": st.column_config.TextColumn("Flag", width=120),
            "meeting": st.column_config.TextColumn("Meeting", width="medium"),
            "detail": st.column_config.TextColumn("Detail", width="large"),
        },
    )

diary = data.calendar_between(start, end)[
    ["date", "start", "end", "title", "category", "has_agenda", "location"]]
with st.expander(f"Full diary · {len(diary)} entries"):
    st.dataframe(
        diary, hide_index=True, width="stretch",
        column_config={
            "date": st.column_config.DateColumn("Date", format="ddd D MMM"),
            "start": "Start", "end": "End",
            "title": st.column_config.TextColumn("Title", width="large"),
            "category": "Category",
            "has_agenda": st.column_config.CheckboxColumn("Agenda"),
            "location": "Location",
        },
    )

# ----------------------------------------------------------------- travel
st.header("Travel")
ui.flag_list(["Travel"], f"Every trip in the next {data.TRAVEL_WINDOW_DAYS} days is fully ready.")
trips = data.travel_view()
trips = trips[trips["end_date"] >= data.today()]
st.dataframe(
    trips.assign(
        flag=["⚠️ Not ready" if 0 <= n <= data.TRAVEL_WINDOW_DAYS and r < 1 else ""
              for n, r in zip(trips["days_to_trip"], trips["readiness"])],
        missing=trips["missing"].replace("", "—"),
        readiness=(trips["readiness"] * 100).round(),
    )[["flag", "trip", "start_date", "end_date", "destination", "purpose", "readiness", "missing"]],
    hide_index=True, width="stretch",
    column_config={
        "flag": st.column_config.TextColumn("Flag", width=130),
        "trip": st.column_config.TextColumn("Trip", width=210),
        "start_date": st.column_config.DateColumn("Out", format="ddd D MMM"),
        "end_date": st.column_config.DateColumn("Back", format="ddd D MMM"),
        "destination": "Destination",
        "purpose": st.column_config.TextColumn("Purpose", width=340),
        "readiness": st.column_config.ProgressColumn("Readiness", min_value=0, max_value=100, format="%d%%"),
        "missing": st.column_config.TextColumn("Still to do", width=380),
    },
)
st.caption(f"Readiness = share of checks done ({', '.join(data.TRAVEL_CHECKS.values())}); "
           f"hotel isn't counted for same-day trips. Flagged if a trip within {data.TRAVEL_WINDOW_DAYS} days "
           "is below 100%.")

ui.export_button(export_slot, {
    "Time split": split.rename(columns={"actual": "actual_share", "target": "target_share"}),
    "Diary flags": flags,
    "Diary": diary,
    "Travel": data.travel_view().assign(readiness=lambda d: (d["readiness"] * 100).round().astype(int))
    .rename(columns={"readiness": "readiness_pct"}),
}, "ceo_week")
