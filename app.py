"""
app.py — Data Governance Scorecard (Streamlit-in-Snowflake).

Two pages, session-state routed:
    Page 1 — Products : all data products, KPIs, portfolio trend, and the
                         hero heatmap — clickable rows drill into a product.
    Page 2 — Tables    : the tables inside one product (drilled straight from
                         product -> table, no database level), KPIs scoped to
                         the product, its trend, the biggest-drag breakdown
                         card, and the hero heatmap (terminal — no drill).

The heatmap is the primary view on both pages: score (the `now` column),
trend (left-to-right), and status (color) are all readable directly off it,
so there is no separate ranked list/table underneath it.

Local vs Snowflake is decided entirely by config.RUN_MODE; nothing in this file
knows which backend is live.
"""

from __future__ import annotations

import streamlit as st

import config
import data
import theme
from components import heatmap, kpi_row

st.set_page_config(page_title="Data Governance Scorecard", page_icon=None, layout="wide")
theme.apply_theme()

# --------------------------------------------------------------------------- #
# Navigation state — "products" (page 1) or "tables" (page 2, scoped to a
# selected product).
# --------------------------------------------------------------------------- #
st.session_state.setdefault("page", "products")
st.session_state.setdefault("product", None)


# --------------------------------------------------------------------------- #
# Sidebar — as-of week + governance knobs (shared by both pages, override
# config live). Threshold/rollup are passed explicitly into every data.* call
# so Streamlit's cache invalidates correctly when they change.
# --------------------------------------------------------------------------- #
def sidebar() -> dict:
    with st.sidebar:
        st.markdown("### Data Governance Scorecard")
        st.caption(f"Mode: `{config.RUN_MODE}`")

        snaps = data.available_snapshots()
        labels = {s: s.strftime("%b %d, %Y") for s in snaps}
        as_of = st.select_slider(
            "As of (Friday)", options=snaps, value=snaps[-1],
            format_func=lambda s: labels[s])

        st.divider()
        st.caption("Scoring")
        threshold = st.slider("Pass threshold", 40, 95, config.THRESHOLD, 1,
                              help="Tables at or above this score pass.")
        rollup = st.selectbox(
            "Rollup method", ["average", "weighted", "pass_rate"],
            index=["average", "weighted", "pass_rate"].index(config.ROLLUP_METHOD),
            help="How table scores roll up to product.")

    return {"as_of": as_of, "threshold": threshold, "rollup": rollup}


# --------------------------------------------------------------------------- #
# Score-metric selector — prominent, top of page, shared by both pages. Every
# KPI, chart, heatmap, and list on the page reads whichever metric is picked
# here (config.SCORE_METRICS), so it lives above the page content, not tucked
# in the sidebar.
# --------------------------------------------------------------------------- #
def metric_selector() -> str:
    metrics = data.available_metrics()
    if not metrics:
        st.error("No configured score column (config.SCORE_METRICS) was found "
                "in the loaded data. Check config.SCORE_METRICS[*]['column'] "
                "against the source.")
        st.stop()
    # short display labels for the pills only ("Metadata score" -> "Metadata")
    # — the full label is still used everywhere else (KPI cell, heatmap title)
    short = {m["label"]: m["label"].removesuffix(" score") for m in metrics}
    labels = [short[m["label"]] for m in metrics]
    label_to_key = {short[m["label"]]: m["key"] for m in metrics}
    default_label = short[metrics[0]["label"]]

    vcol, scol = st.columns([1, 11], vertical_alignment="center")
    with vcol:
        st.markdown("<span class='gov-viewing-l'>Viewing</span>", unsafe_allow_html=True)
    with scol:
        chosen = st.segmented_control(
            "Viewing score", options=labels, default=default_label, required=True,
            label_visibility="collapsed", key="score_metric_label")
    return label_to_key.get(chosen, metrics[0]["key"])


# --------------------------------------------------------------------------- #
# Page 1 — Products
# --------------------------------------------------------------------------- #
def render_products_page(opts: dict) -> None:
    as_of, thr, method, metric = opts["as_of"], opts["threshold"], opts["rollup"], opts["metric"]
    metric_label = config.score_metric(metric)["label"]

    st.markdown(theme.page_title("All products"), unsafe_allow_html=True)

    trend = data.get_trend("products", None, as_of, config.TREND_WEEKS, thr, method, metric)
    kpi_row.render(data.get_kpis("products", None, as_of, thr, method, metric),
                   trend_series=trend["score"].tolist())
    st.write("")

    heat = data.get_heatmap("products", None, as_of, config.HEATMAP_WEEKS, thr, method, metric)
    selected = heatmap.render(
        heat, title=f"{metric_label} by product", clickable=True,
        tooltip=lambda r: f"{r['tables']} tables · {r['below']} below threshold",
        key_prefix="hm_product")

    if selected is not None:
        st.session_state.page = "tables"
        st.session_state.product = selected
        st.rerun()


# --------------------------------------------------------------------------- #
# Page 2 — Tables in {product}
# --------------------------------------------------------------------------- #
def render_tables_page(product: str, opts: dict) -> None:
    as_of, thr, method, metric = opts["as_of"], opts["threshold"], opts["rollup"], opts["metric"]
    metric_label = config.score_metric(metric)["label"]

    if st.button("‹ All products", key="back_to_products", type="tertiary"):
        st.session_state.page = "products"
        st.session_state.product = None
        st.rerun()

    kpis = data.get_kpis("tables", product, as_of, thr, method, metric)
    n_tables = kpis[1]["value"]
    st.markdown(theme.page_title(product, sub=f"{n_tables} tables" if n_tables is not None else None),
               unsafe_allow_html=True)

    trend = data.get_trend("tables", product, as_of, config.TREND_WEEKS, thr, method, metric)
    kpi_row.render(kpis, trend_series=trend["score"].tolist())
    st.write("")

    heat = data.get_heatmap("tables", product, as_of, config.HEATMAP_WEEKS, thr, method, metric)
    heatmap.render(heat, title=f"{metric_label} by table", clickable=False, key_prefix="hm_table")


def render_header(opts: dict) -> None:
    badges = [
        f"As of {opts['as_of'].strftime('%b %d')}",
        f"Pass ≥ {opts['threshold']}",
        opts["rollup"].replace("_", " ").capitalize(),
    ]
    st.markdown(
        theme.app_header("Data Governance Scorecard",
                         tagline="Weekly quality and ownership tracking",
                         badges=badges),
        unsafe_allow_html=True)


def main() -> None:
    opts = sidebar()
    render_header(opts)
    opts["metric"] = metric_selector()
    if st.session_state.page == "tables" and st.session_state.product:
        render_tables_page(st.session_state.product, opts)
    else:
        render_products_page(opts)


main()
