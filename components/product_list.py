"""Page-1 product list — styled rows (name, sparkline, score bar, WoW, tables,
below-threshold) each paired with a real "View tables →" button so the drill
is a functioning Streamlit control, not just a picture of one."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import theme

_HEADER = (
    "<div class='gov-row hdr'>"
    "<span>Product</span><span>Trend</span><span>Score</span>"
    "<span>WoW</span><span>Tables</span><span>Below</span></div>")


def _wow_html(wow) -> str:
    if wow is None or wow == 0:
        return "<span style='color:#8a94a3;'>0</span>"
    cls = "up" if wow > 0 else "down"
    color = theme.UP if cls == "up" else theme.DOWN
    return f"<span style='color:{color};'>{wow:+d}</span>"


def _row_html(row: pd.Series) -> str:
    score = row["score"]
    score_num = "—" if score is None else str(int(score))
    pct = 0 if score is None else max(0, min(100, round(score)))
    bar_color = theme.score_color(score)
    spark = theme.sparkline_svg(row["series"])
    return (
        "<div class='gov-row'>"
        f"<span class='name'>{row['label']}</span>"
        f"<span>{spark}</span>"
        "<span style='display:flex;align-items:center;gap:6px;'>"
        f"<span class='gov-scorebar' style='flex:1;'><i style='width:{pct}%;background:{bar_color};'></i></span>"
        f"<span style='font-weight:600;min-width:22px;'>{score_num}</span></span>"
        f"<span>{_wow_html(row['wow'])}</span>"
        f"<span>{row['n_tables']}</span>"
        f"<span>{row['n_below']}</span>"
        "</div>")


def render(df: pd.DataFrame, title: str = "Products") -> str | None:
    """Render the product list. Returns the clicked product's entity id, else None."""
    st.markdown(theme.section_header(title, "click a row to drill in"),
                unsafe_allow_html=True)
    st.markdown(_HEADER, unsafe_allow_html=True)

    selected = None
    for i, row in df.iterrows():
        left, right = st.columns([11, 2], gap="small", vertical_alignment="center")
        with left:
            st.markdown(_row_html(row), unsafe_allow_html=True)
        with right:
            if st.button("View tables →", key=f"drill_product_{i}", type="tertiary"):
                selected = row["entity"]
    return selected
