"""KPI row — a single bordered strip, four columns divided by hairlines (no
accent bars, no icon circles). A delta shows only when it's a real nonzero
number, and the below-threshold cell's delta is inverse-colored (fewer below
is "up" even though the number fell). The score cell (first column) carries
an inline sparkline of its own trend."""

from __future__ import annotations

import streamlit as st

import theme


def _cell_html(card: dict, spark_html: str | None = None) -> str:
    value = card["value"] if card["value"] is not None else "—"
    delta_html = ""
    d = theme.delta_str(card.get("delta"))
    if d is not None:
        # arrow reflects the raw sign of the change; the CSS class (color)
        # reflects whether that change is good or bad, which for an inverse
        # metric (e.g. below-threshold count) can point opposite ways —
        # a rising below-threshold count is an UP arrow in DOWN (red) color.
        cls = theme.delta_class(card["delta"], inverse=card.get("inverse", False))
        arrow = "▲" if card["delta"] > 0 else "▼"
        delta_html = f"<div class='gov-kpi-s {cls}'>{arrow} {d} WoW</div>"
    sub_html = f"<div class='gov-kpi-s'>{card['sub']}</div>" if card.get("sub") else ""

    value_row = f"<div class='gov-kpi-v'>{value}</div>"
    if spark_html:
        value_row = (
            "<div style='display:flex;align-items:center;justify-content:space-between;gap:8px;'>"
            f"<div class='gov-kpi-v'>{value}</div>{spark_html}</div>")

    return (
        "<div class='gov-kpi-cell'>"
        f"<div class='gov-kpi-l'>{card['label']}</div>"
        f"{value_row}{delta_html}{sub_html}"
        "</div>")


def render(cards: list[dict], trend_series: list[float] | None = None) -> None:
    """Render the KPI strip. `trend_series` (weekly scores, oldest -> newest),
    if given, draws a sparkline into the first (score) cell only."""
    spark = None
    if trend_series and len([s for s in trend_series if s is not None]) >= 2:
        spark = theme.sparkline_svg(trend_series)
    parts = [_cell_html(c, spark if i == 0 else None) for i, c in enumerate(cards)]
    html = (f"<div class='gov-kpi-strip'><div class='gov-kpi-grid'>"
            f"{''.join(parts)}</div></div>")
    st.markdown(html, unsafe_allow_html=True)
