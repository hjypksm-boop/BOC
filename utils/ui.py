"""Shared look and feel: one accent colour, RAG labels, chart styling, Excel export."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import data

ACCENT = "#C2410C"
ACCENT_MID = "#E07A45"
ACCENT_LIGHT = "#F2B48F"
MUTED = "#9CA3AF"
RAG_ICON = {"Red": "🔴 Red", "Amber": "🟠 Amber", "Green": "🟢 Green"}
RAG_ORDER = {"Red": 0, "Amber": 1, "Green": 2}
OVERDUE_RED = "#DC2626"
RSVP_COLOURS = {"Yes": ACCENT, "No": MUTED, "Pending": ACCENT_LIGHT}

CSS = f"""
<style>
  .pill {{display:inline-block;font-size:0.72rem;font-weight:600;letter-spacing:.03em;
          text-transform:uppercase;padding:1px 8px;border-radius:999px;margin-right:6px;
          border:1px solid rgba(128,128,128,.45);}}
  .pill-Critical {{background:{ACCENT};border-color:{ACCENT};color:#fff;}}
  .pill-High {{border-color:{ACCENT};}}
  .meta {{font-size:0.8rem;opacity:.7;}}
  .item-title {{font-weight:600;margin:2px 0 0;line-height:1.35;}}
  .item-detail {{font-size:0.88rem;opacity:.75;margin:0;}}
  .hero {{border-left:4px solid {ACCENT};padding:4px 0 4px 16px;margin:8px 0 16px;}}
  .hero-value {{font-size:clamp(2.6rem, 9vw, 4.2rem);font-weight:700;line-height:1;}}
  .hero-unit {{font-size:1.1rem;font-weight:500;opacity:.7;margin-left:6px;}}
  .hero-sub {{font-size:0.92rem;opacity:.75;margin-top:6px;}}
  .rsvp-bar {{display:flex;height:10px;border-radius:999px;overflow:hidden;margin:10px 0 4px;
              background:rgba(128,128,128,.15);}}
  .rsvp-bar span {{display:block;height:100%;}}
  .stats {{display:flex;gap:18px;margin-top:10px;}}
  .stat-v {{font-size:1.15rem;font-weight:700;line-height:1.1;}}
  .stat-v.alert {{color:{ACCENT};}}
  .stat-l {{font-size:0.72rem;opacity:.65;text-transform:uppercase;letter-spacing:.03em;}}
  [class*="st-key-tourbox_"] {{border:2px solid {ACCENT} !important;background:rgba(194,65,12,.07);}}
  /* Ask the Tower chips: wrap onto several lines instead of scrolling sideways */
  .st-key-chip [data-testid="stButtonGroup"] > div {{flex-wrap:wrap !important;overflow:visible !important;}}
  .st-key-chip [data-testid="stButtonGroup"] button {{max-width:100%;height:auto;min-height:2rem;
                                                     text-align:left;padding-top:5px;padding-bottom:5px;}}
  .swatch {{display:inline-block;width:9px;height:9px;border-radius:2px;margin:0 4px 0 8px;}}
</style>
"""


def setup(page_title: str) -> None:
    st.set_page_config(page_title=f"{page_title} · Ops Control Tower" if page_title else "Ops Control Tower",
                       layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


def header(title: str, subtitle: str = "") -> st.delta_generator.DeltaGenerator:
    """Title + caption; returns a slot for the export button (filled once tables exist)."""
    st.title(title)
    st.caption(" · ".join(p for p in [subtitle, "Demo · illustrative data only"] if p))
    return st.container()


def flag_card(item, link: bool = False) -> None:
    """One red-flag card (severity pill, area, title, detail), optionally linking to its page."""
    with st.container(border=True):
        st.markdown(
            f"<span class='pill pill-{item.severity}'>{item.severity}</span>"
            f"<span class='meta'>{item.area}</span>"
            f"<p class='item-title'>{item.title}</p>"
            f"<p class='item-detail'>{item.detail}</p>",
            unsafe_allow_html=True,
        )
        if link:
            path, page_name = data.PAGES[item.page]
            st.page_link(path, label=f"Open {page_name} →")


def flag_list(areas: list[str], empty: str = "No red flags here.") -> None:
    """The attention items for some areas, two cards per row."""
    items = data.attention_items()
    items = items[items["area"].isin(areas)] if not items.empty else items
    if items.empty:
        st.success(empty, icon=":material/check_circle:")
        return
    cols = st.columns(2)
    for i, item in enumerate(items.itertuples()):
        with cols[i % 2]:
            flag_card(item)


def export_button(slot, sheets: dict[str, pd.DataFrame], stem: str) -> None:
    with slot:
        st.download_button(
            "Export to Excel",
            data=data.to_excel(sheets),
            file_name=f"{stem}_{date.today():%Y-%m-%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/download:",
        )


def style_chart(fig: go.Figure, title: str, height: int = 300) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=15)),
        height=height, margin=dict(l=8, r=8, t=48, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, title=None),
        hoverlabel=dict(namelength=-1),
    )
    fig.update_xaxes(title=None, gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    fig.update_yaxes(title=None, gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    return fig


def show_chart(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
