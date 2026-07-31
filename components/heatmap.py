"""Heatmap — entity (rows) x week (cols) score grid, as a custom HTML/CSS grid
(not Altair) so row labels stay pixel-aligned and cells stay tight. Missing
(entity, week) pairs render as an honest hatched gap, never a fabricated value.
"""

from __future__ import annotations

import streamlit as st

import config
import theme

_SNAP = config.COLUMNS["snapshot_date"]


def _legend_html() -> str:
    chips = []
    labels = ["<65", "65–74", "75–84", "85+"]
    colors = [b["color"] for b in reversed(config.SCORE_BANDS)]
    for lbl, col in zip(labels, colors):
        chips.append(
            f"<span><i style='background:{col}'></i>{lbl}</span>")
    return "<div class='gov-hm-legend'>" + "".join(chips) + "</div>"


def _week_header_html(dates) -> str:
    cells = ["<div class='gov-hm-corner'></div>"]
    n = len(dates)
    for i, d in enumerate(dates):
        if i == 0:
            label = f"−{n - 1}w" if n > 1 else "now"
        elif i == n - 1:
            label = "now"
        else:
            label = ""
        cells.append(f"<div class='gov-hm-wk'>{label}</div>")
    return "".join(cells)


def render(hm: dict, threshold: int, title: str = "Score by entity") -> None:
    dates = hm["dates"]
    data = hm["data"]
    order = hm["order"]

    meta = f"{len(dates)} weeks" if dates else "no data"
    st.markdown(theme.section_header(title, meta), unsafe_allow_html=True)
    st.markdown(_legend_html(), unsafe_allow_html=True)

    if data.empty or not order:
        st.caption("No data in this window.")
        return

    # label -> {date -> score}
    by_entity: dict[str, dict] = {}
    for _, r in data.iterrows():
        by_entity.setdefault(r["label"], {})[r[_SNAP]] = r["score"]

    n_cols = len(dates)
    grid = [f"<div class='gov-hm' style=\"grid-template-columns:170px repeat({n_cols},48px);\">"]
    grid.append(_week_header_html(dates))

    for label in order:
        grid.append(f"<div class='gov-hm-row gov-mono'>{label}</div>")
        scores = by_entity.get(label, {})
        for d in dates:
            score = scores.get(d)
            if score is None:
                grid.append("<div class='gov-hm-cell gap'></div>")
            else:
                bg = theme.score_color(score)
                fg = theme.score_text_color(score)
                grid.append(
                    f"<div class='gov-hm-cell' style='background:{bg};color:{fg};'>"
                    f"{round(score)}</div>")
    grid.append("</div>")
    st.markdown("".join(grid), unsafe_allow_html=True)
