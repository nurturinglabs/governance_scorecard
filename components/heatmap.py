"""Heatmap — entity (rows) x week (cols) score grid, the hero view on both
pages (score, trend, and status all read directly off it, so the ranked
list/table was redundant and has been removed).

Products-page rows are clickable (drill into that product): a real st.button
for the label, right-aligned, with a trailing chevron that appears on row
hover. Tables-page rows are terminal: a plain two-line label (table name +
its top gap) instead of a button. Each row is rendered as its own
`st.columns` block — label + weekly cell strip side by side — so the label
and cells stay vertically centered together without a separate alignment
pass. Missing (entity, week) pairs render as an honest hatched gap, never a
fabricated value.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

import config
import theme

_SNAP = config.COLUMNS["snapshot_date"]
_COL_RATIO = [2.4, 6]


def _legend_html() -> str:
    chips = []
    labels = ["<65", "65–74", "75–84", "85+"]
    colors = [b["color"] for b in reversed(config.SCORE_BANDS)]
    for lbl, col in zip(labels, colors):
        chips.append(f"<span><i style='background:{col}'></i>{lbl}</span>")
    return "<div class='gov-hm-legend'>" + "".join(chips) + "</div>"


def _week_header_html(dates) -> str:
    n = len(dates)
    out = f"<div class='gov-hm-strip' style=\"grid-template-columns:repeat({n},1fr);\">"
    for i in range(n):
        if i == 0:
            lbl = f"−{n - 1}w" if n > 1 else "now"
        elif i == n - 1:
            lbl = "now"
        else:
            lbl = ""
        out += f"<div class='gov-hm-wk'>{lbl}</div>"
    return out + "</div>"


def _cells_grid_html(label: str, dates, lookup: dict) -> str:
    out = f"<div class='gov-hm-strip' style=\"grid-template-columns:repeat({len(dates)},1fr);\">"
    for d in dates:
        score = lookup.get((label, d))
        if score is None:
            out += "<div class='gov-hm-cell gap'></div>"
        else:
            bg = theme.score_color(score)
            fg = theme.score_text_color(score)
            out += f"<div class='gov-hm-cell' style='background:{bg};color:{fg};'>{round(score)}</div>"
    return out + "</div>"


def _cells_html(label: str, dates, lookup: dict, chevron: bool) -> str:
    grid = _cells_grid_html(label, dates, lookup)
    if not chevron:
        return grid
    return (f"<div class='gov-hm-rowwrap'>{grid}"
            "<span class='gov-hm-chevron'>&#8250;</span></div>")


def _table_label_html(label: str, top_gap: str | None) -> str:
    flag = bool(top_gap) and top_gap != "—"
    sub_class = "gov-hm-tsub flag" if flag else "gov-hm-tsub"
    sub = top_gap or "—"
    return (f"<div class='gov-hm-label2'><div class='gov-hm-tname'>{label}</div>"
            f"<div class='{sub_class}'>{sub}</div></div>")


def render(hm: dict, title: str = "Score by entity", clickable: bool = False,
          tooltip: Callable[[dict], str] | None = None, key_prefix: str = "hm") -> str | None:
    """Render the hero heatmap. If `clickable`, each row label is a real
    st.button (right-aligned, chevron on row hover) and the clicked entity id
    is returned; `tooltip(row)` becomes that button's hover help text.
    Otherwise (terminal, tables page) each row gets a plain two-line label —
    table name plus its top gap — read straight off `row["top_gap"]`."""
    dates = hm["dates"]
    rows = hm["rows"]

    meta = f"{len(dates)} weeks" if dates else "no data"
    st.markdown(theme.section_header(title, meta), unsafe_allow_html=True)
    st.markdown(_legend_html(), unsafe_allow_html=True)

    if not rows:
        st.caption("No data in this window.")
        return None

    lookup = {(r["label"], r[_SNAP]): r["score"] for _, r in hm["data"].iterrows()}

    head = st.columns(_COL_RATIO, vertical_alignment="center")
    with head[1]:
        st.markdown(_week_header_html(dates), unsafe_allow_html=True)

    selected = None
    for row in rows:
        c = st.columns(_COL_RATIO, vertical_alignment="center")
        with c[0]:
            if clickable:
                help_text = tooltip(row) if tooltip else None
                if st.button(row["label"], key=f"{key_prefix}_{row['entity']}",
                            type="tertiary", use_container_width=True, help=help_text):
                    selected = row["entity"]
            else:
                st.markdown(_table_label_html(row["label"], row.get("top_gap")),
                           unsafe_allow_html=True)
        with c[1]:
            st.markdown(_cells_html(row["label"], dates, lookup, chevron=clickable),
                       unsafe_allow_html=True)

    return selected
