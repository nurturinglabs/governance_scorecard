"""Breakdown card (page 2 only) — decomposes the worst-scored table in the
product into its governance components so the view says *why* it's low, not
just *that* it is. Falls back to the worst table's trend when component
columns aren't available (see config.COMPONENT_WEIGHTS)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import config
import theme
from components import trend_chart


def _bar(label: str, pts: int, mx: int, ratio: float) -> str:
    pct = round(ratio * 100)
    col = theme.ratio_color(ratio)
    return (
        "<div class='gov-bd-row'>"
        f"<span style='font-size:13px;color:#7a2b1a;'>{label}</span>"
        "<span class='bar'>"
        f"<i style='width:{pct}%;background:{col};'></i></span>"
        f"<span style='font-size:12px;color:#7a2b1a;text-align:right;'>{pts} / {mx}</span>"
        "</div>")


def render(bd: dict) -> None:
    if not bd.get("found"):
        return

    if bd.get("has_components"):
        bars = "".join(_bar(c["label"], c["pts"], c["max"], c["ratio"])
                       for c in bd["components"])
        html = (
            "<div class='gov-drag'>"
            "<div style='display:flex;align-items:center;gap:8px;margin-bottom:2px;'>"
            "<span class='t'>Biggest drag · "
            f"<span class='gov-mono'>{bd['label']}</span></span>"
            f"<span style='margin-left:auto;font-size:20px;font-weight:600;color:#993c1d;'>{bd['score']}</span>"
            "</div>"
            f"<div style='font-size:12px;color:#993c1d;opacity:0.8;margin:2px 0 10px;'>"
            f"why this table scores low, vs max points</div>"
            f"{bars}</div>")
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div class='gov-drag'><span class='t'>Biggest drag · "
            f"<span class='gov-mono'>{bd['label']}</span></span> "
            f"<span style='color:#993c1d;'>score {bd['score']}</span></div>",
            unsafe_allow_html=True)
        series = bd.get("series", [])
        if series:
            d = pd.DataFrame({config.COLUMNS["snapshot_date"]: range(len(series)),
                              "score": series})
            trend_chart.render(d, bd["threshold"], title="Worst table trend")
