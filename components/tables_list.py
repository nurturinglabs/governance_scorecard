"""Page-2 tables list — a single pure-HTML table (fast even at 40–60 rows,
terminal: no further drill). Sorted worst-first by data.get_children so the
tables needing attention surface at the top."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import theme


def _wow_html(wow) -> str:
    if not wow:
        return "<span style='color:#8a94a3'>0</span>"
    color = theme.UP if wow > 0 else theme.DOWN
    return f"<span style='color:{color}'>{wow:+d}</span>"


def _owner_html(owner) -> str:
    if not owner:
        return "<span class='gov-unowned'>⚠ unassigned</span>"
    return f"<span class='gov-mono' style='color:#5f6b7a'>{owner}</span>"


def _row_html(row: pd.Series) -> str:
    score = row["score"]
    score_num = "" if score is None else int(score)
    color = theme.score_color(score)
    spark = theme.sparkline_svg(row["series"])
    return (
        "<tr>"
        f"<td class='gov-mono'>{row['label']}</td>"
        f"<td style='text-align:right;font-weight:600;color:{color}'>{score_num}</td>"
        f"<td style='text-align:right'>{_wow_html(row['wow'])}</td>"
        f"<td>{spark}</td>"
        f"<td>{_owner_html(row['owner'])}</td>"
        f"<td style='color:#5f6b7a'>{row['top_gap']}</td>"
        "</tr>")


def render(df: pd.DataFrame, title: str = "Tables") -> None:
    st.markdown(theme.section_header(title, f"{len(df)} tables · worst first"),
                unsafe_allow_html=True)
    if df.empty:
        st.caption("No tables in this product for the selected week.")
        return
    rows = "".join(_row_html(r) for _, r in df.iterrows())
    html = (
        "<table class='gov-tbl'><thead><tr>"
        "<th>Table</th><th style='text-align:right'>Score</th>"
        "<th style='text-align:right'>WoW</th><th>Trend</th>"
        "<th>Owner</th><th>Top gap</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>")
    st.markdown(html, unsafe_allow_html=True)
