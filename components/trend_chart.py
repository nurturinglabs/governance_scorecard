"""Trend chart — focus-entity score over time, zoomed to a tight y-domain so
small real movement reads as a visible slope, with an endpoint label and the
pass threshold drawn as a dashed rule."""

from __future__ import annotations

import math

import altair as alt
import pandas as pd
import streamlit as st

import config
import theme

_SNAP = config.COLUMNS["snapshot_date"]


def _y_domain(scores: pd.Series) -> tuple[float, float]:
    lo = max(0, math.floor(float(scores.min()) - 6))
    hi = min(100, math.ceil(float(scores.max()) + 6))
    if hi - lo < 4:  # keep a visible band even when the series is flat
        lo, hi = max(0, lo - 2), min(100, hi + 2)
    return lo, hi


def build(df: pd.DataFrame, threshold: int, label: str = "Score") -> alt.Chart:
    """Pure chart builder (testable without a Streamlit runtime)."""
    if df.empty:
        return alt.Chart(pd.DataFrame({"x": [], "y": []})).mark_line()

    d = df.rename(columns={_SNAP: "date", "score": "score"})
    y_min, y_max = _y_domain(d["score"])
    last = d.iloc[[-1]].copy()
    last["lbl"] = last["score"].round(0).astype(int).astype(str)

    line = (
        alt.Chart(d)
        .mark_line(color=theme.NAVY, strokeWidth=2.5,
                   point=alt.OverlayMarkDef(color=theme.NAVY, size=35))
        .encode(
            x=alt.X("date:T", title=None,
                    axis=alt.Axis(format="%b %d", labelColor=theme.TEXT_MUTED, grid=False)),
            y=alt.Y("score:Q", title=None,
                    scale=alt.Scale(domain=[y_min, y_max]),
                    axis=alt.Axis(labelColor=theme.TEXT_MUTED, gridColor="#f0f2f5", gridDash=[2, 3])),
            tooltip=[alt.Tooltip("date:T", title="Week"),
                     alt.Tooltip("score:Q", title=label, format=".1f")],
        )
    )
    endpoint = (
        alt.Chart(last)
        .mark_point(color=theme.NAVY, size=60, filled=True)
        .encode(x="date:T", y=alt.Y("score:Q", scale=alt.Scale(domain=[y_min, y_max])))
    )
    endpoint_label = (
        alt.Chart(last)
        .mark_text(align="left", dx=8, dy=-2, color=theme.NAVY, fontSize=13, fontWeight="bold")
        .encode(x="date:T", y=alt.Y("score:Q", scale=alt.Scale(domain=[y_min, y_max])), text="lbl:N")
    )
    rule = (
        alt.Chart(pd.DataFrame({"t": [threshold]}))
        .mark_rule(color=theme.THRESHOLD_COLOR, strokeDash=[4, 4])
        .encode(y=alt.Y("t:Q", scale=alt.Scale(domain=[y_min, y_max])))
    )
    rule_text = (
        alt.Chart(pd.DataFrame({"t": [threshold], "lbl": [f"threshold {threshold}"]}))
        .mark_text(align="left", dx=6, dy=-6, color=theme.THRESHOLD_COLOR, fontSize=11)
        .encode(y=alt.Y("t:Q", scale=alt.Scale(domain=[y_min, y_max])), text="lbl:N")
    )
    return ((rule + rule_text + line + endpoint + endpoint_label)
            .properties(height=200)
            .configure_view(strokeWidth=0)
            .configure_axis(domain=False, tickColor="#f0f2f5"))


def render(df: pd.DataFrame, threshold: int, label: str = "Score",
           title: str = "Score trend") -> None:
    weeks_meta = f"{len(df)} weeks" if not df.empty else None
    with st.container(border=True):
        st.markdown(theme.section_header(title, weeks_meta), unsafe_allow_html=True)
        st.altair_chart(build(df, threshold, label), use_container_width=True)
