"""KPI row — custom HTML cards for the four metrics data.get_kpis() returns.

No st.metric: a delta pill renders only when the delta is a real nonzero
number, and the below-threshold card's pill is inverse-colored (fewer below
is "up" even though the number fell). The score card (first card) can carry
an inline sparkline of its own trend — this replaces the standalone trend
chart so the heatmap can take the full page width below it.
"""

from __future__ import annotations

import streamlit as st

import theme


def _card_html(card: dict, spark_html: str | None = None) -> str:
    value = card["value"] if card["value"] is not None else "—"
    delta_html = ""
    d = theme.delta_str(card.get("delta"))
    if d is not None:
        cls = theme.delta_class(card["delta"], inverse=card.get("inverse", False))
        arrow = "▲" if cls == "up" else "▼"
        delta_html = f"<div class='gov-kpi-d {cls}'>{arrow} {d} WoW</div>"
    sub_html = f"<div class='gov-kpi-sub'>{card['sub']}</div>" if card.get("sub") else ""
    top_row = f"<div class='gov-kpi-v'>{value}</div>"
    if spark_html:
        top_row = (
            "<div style='display:flex;align-items:flex-end;justify-content:space-between;gap:8px;'>"
            f"<div class='gov-kpi-v'>{value}</div>{spark_html}</div>")
    return (
        "<div class='gov-kpi'>"
        f"<div class='gov-kpi-l'>{card['label']}</div>"
        f"{top_row}"
        f"{delta_html}{sub_html}"
        "</div>")


def render(cards: list[dict], trend_series: list[float] | None = None) -> None:
    """Render the KPI cards. `trend_series` (weekly scores, oldest -> newest),
    if given, draws a sparkline into the first (score) card only."""
    spark = None
    if trend_series and len([s for s in trend_series if s is not None]) >= 2:
        spark = theme.sparkline_svg(trend_series, w=90, h=28)
    parts = [_card_html(c, spark if i == 0 else None) for i, c in enumerate(cards)]
    st.markdown("<div class='gov-kpis'>" + "".join(parts) + "</div>", unsafe_allow_html=True)
