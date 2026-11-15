import plotly.graph_objects as go
import streamlit as st

from utils import ai, data, documents, ui

ui.setup("Office & Events")
export_slot = ui.header("Office & Events",
                        "Facilities, health & safety, events, visitors and suppliers")
ACCENT, MUTED = ui.ACCENT, ui.MUTED

tickets = data.tickets_view()
hs = data.hs_rag()
open_t = tickets[tickets["status"] != "Resolved"]
events = data.events_view()
upcoming = data.upcoming_events()
checklist = data.checklist_view()
dietary = data.load_event_dietary()
visits = data.visits_view()
supplies = data.supplies_view()
suppliers = data.suppliers_view()


def _d(d) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def _email_draft(key: str) -> None:
    """Editable subject + body with Open-in-email and Discard, for a draft held in session_state[key]."""
    draft = st.session_state[key]
    subject = st.text_input("Subject", draft["subject"], key=f"subj_{key}")
    body = st.text_area("Email", draft["body"], height=260, key=f"body_{key}")
    with st.container(horizontal=True):
        st.link_button("Open in email", documents.mailto(subject, body), icon=":material/mail:", type="primary")
        if st.button("Discard", key=f"discard_{key}", type="tertiary"):
            for k in (key, f"subj_{key}", f"body_{key}"):
                st.session_state.pop(k, None)
            st.rerun()


# ----------------------------------------------------------------- KPI tiles
week_visits = data.visits_this_week()
c = st.columns(4)
c[0].metric("Open tickets", len(open_t), delta=f"{int(open_t['repeat_issue'].sum())} repeat issues",
            delta_color="off", delta_arrow="off", border=True,
            help=f"Repeat = reported {data.REPEAT_THRESHOLD}+ times")
c[1].metric("H&S overdue", int((hs["rag"] == "Red").sum()), delta=f"{(hs['rag'] == 'Amber').sum()} due in 30 days",
            delta_color="off", delta_arrow="off", border=True)
if len(upcoming):
    nxt = upcoming.iloc[0]
    days = int(nxt["days_to_event"])
    c[2].metric("Next event", "Today" if days == 0 else data._days(days),
                delta=nxt["event"], delta_color="off", delta_arrow="off", border=True,
                help=f"{nxt['event']} · {_d(nxt['date'])} at {nxt['venue']}")
else:
    c[2].metric("Next event", "None booked", border=True)
c[3].metric("Visitors this week", len(week_visits),
            delta=f"{int((week_visits['readiness'] < 1).sum())} not fully ready",
            delta_color="off", delta_arrow="off", border=True)

tab_fac, tab_hs, tab_ev, tab_vis, tab_sup = st.tabs(
    ["Facilities", "Health & Safety", "Events", "Visitors", "Supplies & Suppliers"])

# ================================================================= Facilities
with tab_fac:
    st.header("Facilities tickets")
    show_resolved = st.toggle("Include resolved", value=False)
    tv = tickets if show_resolved else open_t
    tv = (
        tv.assign(
            flag=[f"🔁 Repeat ×{n}" if r else "" for n, r in zip(tv["repeat_count"], tv["repeat_issue"])],
            _resolved=tv["status"].eq("Resolved"),
        )
        .sort_values(["_resolved", "repeat_issue", "days_open"], ascending=[True, False, False])
        [["flag", "issue", "assigned_to", "status", "raised_date", "days_open", "repeat_count"]]
    )
    st.dataframe(
        tv, hide_index=True, width="stretch",
        column_config={
            "flag": st.column_config.TextColumn("Flag", width=130),
            "issue": st.column_config.TextColumn("Issue", width="large"),
            "assigned_to": st.column_config.TextColumn("Assigned to", width=180),
            "status": "Status",
            "raised_date": st.column_config.DateColumn("Raised", format="D MMM"),
            "days_open": st.column_config.NumberColumn("Days open", format="%d"),
            "repeat_count": st.column_config.NumberColumn("Times reported"),
        },
    )
    st.caption(f"Repeat issue = reported {data.REPEAT_THRESHOLD} or more times — "
               "a sign the fix isn't sticking and the supplier needs escalating.")

# ================================================================= Health & safety
with tab_hs:
    st.header("Health & safety tracker")
    hv = (
        hs.assign(_o=hs["rag"].map(ui.RAG_ORDER), RAG=hs["rag"].map(ui.RAG_ICON))
        .sort_values(["_o", "days_until_due"])
        [["RAG", "check", "owner", "last_done", "frequency_days", "next_due", "days_until_due"]]
    )
    st.dataframe(
        hv, hide_index=True, width="stretch",
        column_config={
            "check": st.column_config.TextColumn("Check", width="medium"),
            "owner": st.column_config.TextColumn("Owner", width=180),
            "last_done": st.column_config.DateColumn("Last done", format="D MMM YYYY"),
            "frequency_days": st.column_config.NumberColumn("Every (days)"),
            "next_due": st.column_config.DateColumn("Next due", format="ddd D MMM YYYY"),
            "days_until_due": st.column_config.NumberColumn("Days to due", help="Negative = overdue"),
        },
    )
    st.caption(f"RAG rule: Red = overdue · Amber = due within {data.HS_AMBER_DAYS} days · Green = in date.")

# ================================================================= Events
with tab_ev:
    st.header("Upcoming events")
    ui.flag_list(["Events"], "No event red flags.")

    yes_c, no_c, pend_c = (ui.RSVP_COLOURS[k] for k in ("Yes", "No", "Pending"))
    st.markdown(
        f"<span class='meta'>RSVPs:<span class='swatch' style='background:{yes_c}'></span>Yes"
        f"<span class='swatch' style='background:{no_c}'></span>No"
        f"<span class='swatch' style='background:{pend_c}'></span>Pending</span>",
        unsafe_allow_html=True,
    )
    cols = st.columns(3)
    for i, r in enumerate(upcoming.itertuples()):
        bar = "".join(
            f"<span style='width:{n / r.invited:.1%};background:{colour}' title='{label}: {n}'></span>"
            for n, colour, label in ((r.rsvp_yes, yes_c, "Yes"), (r.rsvp_no, no_c, "No"),
                                     (r.rsvp_pending, pend_c, "Pending")) if n
        )
        budget_alert = " alert" if r.budget_used > data.BUDGET_ALERT_SHARE else ""
        tasks_alert = " alert" if r.tasks_overdue else ""
        with cols[i % 3], st.container(border=True):
            st.markdown(
                f"<span class='meta'>{r.type}</span>"
                f"<p class='item-title'>{r.event}</p>"
                f"<p class='item-detail'>{_d(r.date)} · {r.venue}</p>"
                f"<div class='rsvp-bar'>{bar}</div>"
                f"<span class='meta'>{r.rsvp_yes} yes · {r.rsvp_no} no · {r.rsvp_pending} pending · "
                f"{r.invited} invited</span>"
                f"<div class='stats'>"
                f"<div><div class='stat-v'>{r.days_to_event}</div><div class='stat-l'>Days to go</div></div>"
                f"<div><div class='stat-v{budget_alert}'>{r.budget_used:.0%}</div>"
                f"<div class='stat-l'>Budget used</div></div>"
                f"<div><div class='stat-v{tasks_alert}'>{r.checklist_done:.0%}</div>"
                f"<div class='stat-l'>Checklist{f' · {r.tasks_overdue} late' if r.tasks_overdue else ''}"
                f"</div></div></div>",
                unsafe_allow_html=True,
            )

    # --------------------------------------------------------- selected event
    st.subheader("Event detail")
    names = list(upcoming["event"]) or list(events["event"])
    headline = upcoming[upcoming["type"] == "Christmas party"]
    default = names.index(headline.iloc[0]["event"]) if len(headline) else 0
    chosen = st.selectbox("Event", names, index=default)
    ev = events.set_index("event").loc[chosen]

    m = st.columns(4)
    m[0].metric("RSVP deadline", _d(ev["rsvp_deadline"]), delta=data._in(ev["days_to_rsvp_deadline"]),
                delta_color="off", delta_arrow="off", border=True)
    m[1].metric("Final numbers to venue", _d(ev["final_numbers_due"]),
                delta=data._in(ev["days_to_final_numbers"]), delta_color="off", delta_arrow="off", border=True)
    m[2].metric("Committed", f"£{ev['committed_gbp']:,.0f}",
                delta=f"{ev['budget_used']:.0%} of £{ev['budget_gbp']:,.0f} budget",
                delta_color="off", delta_arrow="off", border=True)
    m[3].metric("Cost per head", f"£{ev['cost_per_head']:,.0f}" if ev["rsvp_yes"] else "—",
                delta=f"per confirmed guest ({ev['rsvp_yes']})", delta_color="off", delta_arrow="off",
                border=True, help="Committed spend ÷ confirmed yes RSVPs")

    left, right = st.columns([3, 2], gap="large")
    with left:
        fig = go.Figure()
        for label, n in (("Yes", ev["rsvp_yes"]), ("No", ev["rsvp_no"]), ("Pending", ev["rsvp_pending"])):
            fig.add_bar(y=["RSVPs"], x=[n], name=label, orientation="h",
                        marker=dict(color=ui.RSVP_COLOURS[label], line=dict(width=0)),
                        text=f"{label} {n}" if n else "", textposition="inside", insidetextanchor="middle",
                        hovertemplate=f"{label}: {n} ({n / ev['invited']:.0%})<extra></extra>")
        fig.update_layout(barmode="stack", showlegend=False, bargap=0.35)
        fig.update_yaxes(visible=False)
        fig.update_xaxes(range=[0, ev["invited"]])
        ui.show_chart(ui.style_chart(fig, f"RSVPs · {ev['invited']} invited", height=170))
    with right:
        diet = dietary[dietary["event"] == chosen].sort_values("count")
        if diet.empty:
            st.caption("No dietary requirements recorded.")
        else:
            fig = go.Figure(go.Bar(
                y=diet["requirement"], x=diet["count"], orientation="h",
                marker=dict(color=ACCENT, cornerradius=4, line=dict(width=0)),
                text=diet["count"], textposition="outside", hovertemplate="%{y}: %{x}<extra></extra>",
            ))
            fig.update_layout(showlegend=False, bargap=0.4)
            fig.update_xaxes(rangemode="tozero", range=[0, diet["count"].max() * 1.25])
            ui.show_chart(ui.style_chart(fig, "Dietary requirements", height=230))

    cl = checklist[checklist["event"] == chosen].sort_values(["done", "due_date"])
    cl = cl.assign(state=["✅ Done" if d else ("⚠️ Overdue" if o else "Open")
                          for d, o in zip(cl["done"], cl["overdue"])])
    cl_view = cl[["state", "task", "owner", "due_date", "days_to_due"]]
    late_rows = set(cl.index[cl["overdue"]])
    st.markdown(f"**Checklist** <span class='meta'>· {int(cl['done'].sum())} of {len(cl)} done"
                f"{f' · {len(late_rows)} overdue' if late_rows else ''}</span>", unsafe_allow_html=True)
    st.dataframe(
        cl_view.style.apply(
            lambda row: [f"color:{ui.OVERDUE_RED};font-weight:600" if row.name in late_rows else ""] * len(row),
            axis=1),
        hide_index=True, width="stretch",
        column_config={
            "state": "Status",
            "task": st.column_config.TextColumn("Task", width="medium"),
            "owner": st.column_config.TextColumn("Owner", width=180),
            "due_date": st.column_config.DateColumn("Due", format="ddd D MMM"),
            "days_to_due": st.column_config.NumberColumn("Days to due", help="Negative = overdue"),
        },
    )

    key = f"rsvp_{chosen}"
    if ev["rsvp_pending"] and ev["days_to_event"] >= 0:
        if key not in st.session_state:
            if st.button(f"Draft RSVP reminder · {ev['rsvp_pending']} not replied", icon=":material/edit_note:",
                         type="primary"):
                with st.spinner("Drafting…"):
                    st.session_state[key], _ = ai.draft_rsvp_reminder(chosen)
                st.rerun()
        else:
            with st.container(border=True):
                _email_draft(key)

# ================================================================= Visitors
with tab_vis:
    st.header("Visitors · next 3 weeks")
    ui.flag_list(["Visitors"], "Every visit in the next two days is fully ready.")

    vv = visits[visits["days_to_visit"] >= 0]
    vv_view = vv.assign(
        flag=["⚠️ Not ready" if 0 <= n <= data.VISIT_WINDOW_DAYS and r < 1 else ""
              for n, r in zip(vv["days_to_visit"], vv["readiness"])],
        missing=vv["missing"].replace("", "—"),
        readiness=(vv["readiness"] * 100).round(),
    )[["flag", "date", "time", "visitor_org", "visitor_count", "host", "purpose", "room", "readiness", "missing"]]
    st.dataframe(
        vv_view, hide_index=True, width="stretch",
        column_config={
            "flag": st.column_config.TextColumn("Flag", width=130),
            "date": st.column_config.DateColumn("Date", format="ddd D MMM"),
            "time": "Time",
            "visitor_org": st.column_config.TextColumn("Visitor", width=190),
            "visitor_count": st.column_config.NumberColumn("Guests"),
            "host": st.column_config.TextColumn("Host", width=180),
            "purpose": st.column_config.TextColumn("Purpose", width=150),
            "room": st.column_config.TextColumn("Room", width=130),
            "readiness": st.column_config.ProgressColumn("Readiness", min_value=0, max_value=100, format="%d%%"),
            "missing": st.column_config.TextColumn("Still to do", width=600),
        },
    )
    st.caption(f"Readiness = share of {len(data.VISIT_CHECKS)} checks done ({', '.join(data.VISIT_CHECKS.values())}). "
               f"Flagged if a visit within {data.VISIT_WINDOW_DAYS} days is below 100%.")

    st.subheader("Visitor pack")
    st.write("AI drafts a welcome email with the address, arrival instructions, who'll meet them and the agenda.")
    idx = st.selectbox("Visit", list(vv.index),
                       format_func=lambda i: f"{_d(visits.loc[i, 'date'])} {visits.loc[i, 'time']} · "
                                             f"{visits.loc[i, 'visitor_org']} ({visits.loc[i, 'purpose']})")
    if idx is not None:
        key = f"visit_{idx}"
        if key not in st.session_state:
            if st.button("Generate visitor pack", icon=":material/badge:", type="primary"):
                with st.spinner("Drafting…"):
                    st.session_state[key], _ = ai.draft_visitor_pack(idx)
                st.rerun()
        else:
            with st.container(border=True):
                _email_draft(key)

# ================================================================= Supplies & suppliers
with tab_sup:
    st.header("Supplies & suppliers")
    ui.flag_list(["Supplies", "Suppliers"], "No supply or supplier red flags.")

    spend = int(suppliers["monthly_cost_gbp"].sum())
    budget = data.OFFICE_MONTHLY_BUDGET
    s = st.columns(3)
    s[0].metric("Monthly office spend", f"£{spend:,.0f}", delta=f"£{spend - budget:+,.0f} vs budget",
                delta_color="inverse", border=True)
    s[1].metric("Monthly budget", f"£{budget:,.0f}", delta=f"{spend / budget:.0%} used",
                delta_color="off", delta_arrow="off", border=True)
    s[2].metric("Contracts ending ≤ 60 days", int(suppliers["contract_ending"].sum()), border=True)

    by_svc = suppliers.sort_values("monthly_cost_gbp")
    fig = go.Figure(go.Bar(
        y=by_svc["service"], x=by_svc["monthly_cost_gbp"], orientation="h",
        marker=dict(color=ACCENT, cornerradius=4, line=dict(width=0)),
        text=[f"£{v:,.0f}" for v in by_svc["monthly_cost_gbp"]], textposition="outside",
        customdata=by_svc["supplier"], hovertemplate="%{customdata}: £%{x:,.0f}/month<extra></extra>",
    ))
    fig.update_layout(showlegend=False, bargap=0.35)
    fig.update_xaxes(tickprefix="£", range=[0, by_svc["monthly_cost_gbp"].max() * 1.2])
    ui.show_chart(ui.style_chart(
        fig, f"Monthly spend by service · £{spend:,.0f} total vs £{budget:,.0f} budget", height=300))

    st.subheader("Suppliers")
    sv = suppliers.assign(
        flag=[" · ".join(f for f in (("⏳ Contract ending" if e else ""), ("🔁 Repeat tickets" if rt else "")) if f)
              for e, rt in zip(suppliers["contract_ending"], suppliers["repeat_tickets"])],
        rating=["★" * n + "☆" * (5 - n) for n in suppliers["satisfaction"]],
    ).sort_values(["contract_ending", "repeat_tickets", "days_to_contract_end"], ascending=[False, False, True])
    st.dataframe(
        sv[["flag", "supplier", "service", "contract_end", "days_to_contract_end", "monthly_cost_gbp",
            "open_issues", "repeat_issues", "rating"]],
        hide_index=True, width="stretch",
        column_config={
            "flag": st.column_config.TextColumn("Flag", width=290),
            "supplier": st.column_config.TextColumn("Supplier", width=200),
            "service": "Service",
            "contract_end": st.column_config.DateColumn("Contract ends", format="D MMM YYYY"),
            "days_to_contract_end": st.column_config.NumberColumn("Days left"),
            "monthly_cost_gbp": st.column_config.NumberColumn("£ / month", format="£%,d"),
            "open_issues": st.column_config.NumberColumn("Open issues"),
            "repeat_issues": st.column_config.TextColumn("Repeat tickets", width=320),
            "rating": st.column_config.TextColumn("Satisfaction", width=120),
        },
    )
    linked = data.supplier_tickets()
    with st.expander(f"Facilities tickets linked to suppliers · {len(linked)}"):
        st.dataframe(
            linked.sort_values(["supplier", "repeat_count"], ascending=[True, False])
            [["supplier", "issue", "status", "raised_date", "repeat_count"]],
            hide_index=True, width="stretch",
            column_config={
                "supplier": st.column_config.TextColumn("Supplier", width=200),
                "issue": st.column_config.TextColumn("Issue", width="large"),
                "status": "Status",
                "raised_date": st.column_config.DateColumn("Raised", format="D MMM"),
                "repeat_count": st.column_config.NumberColumn("Times reported"),
            },
        )
    st.caption(f"Flags: contract ends within {data.CONTRACT_WINDOW_DAYS} days · an open linked ticket "
               f"reported {data.REPEAT_THRESHOLD}+ times.")

    st.subheader("Supplies")
    spv = supplies.assign(flag=supplies["reorder"].map({True: "⚠️ Reorder", False: ""})) \
        .sort_values(["reorder", "item"], ascending=[False, True])
    st.dataframe(
        spv[["flag", "item", "stock", "reorder_level", "supplier", "last_ordered", "days_since_order"]],
        hide_index=True, width="stretch",
        column_config={
            "flag": st.column_config.TextColumn("Flag", width=120),
            "item": st.column_config.TextColumn("Item", width="medium"),
            "stock": st.column_config.NumberColumn("In stock"),
            "reorder_level": st.column_config.NumberColumn("Reorder at"),
            "supplier": st.column_config.TextColumn("Supplier", width=200),
            "last_ordered": st.column_config.DateColumn("Last ordered", format="D MMM"),
            "days_since_order": st.column_config.NumberColumn("Days since order"),
        },
    )

# ================================================================= Export (every tab)
visit_export = visits.assign(readiness=(visits["readiness"] * 100).round().astype(int))
ui.export_button(export_slot, {
    "Tickets": tickets.drop(columns=["age_days"]),
    "Health & safety": hv.assign(RAG=hs.loc[hv.index, "rag"]),
    "Events": events.drop(columns=["checklist_done"]).assign(
        pending_share=(events["pending_share"] * 100).round().astype(int),
        budget_used=(events["budget_used"] * 100).round().astype(int),
        checklist_pct=(events["checklist_done"] * 100).round().astype(int),
    ).rename(columns={"pending_share": "pending_pct", "budget_used": "budget_used_pct"}),
    "Event checklist": checklist,
    "Event dietary": dietary,
    "Visitors": visit_export.rename(columns={"readiness": "readiness_pct"}),
    "Supplies": supplies,
    "Suppliers": suppliers,
}, "office_and_events")
