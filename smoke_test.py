"""
smoke_test.py — fast, browser-free verification that the app works.

Runs the data layer across both levels (products -> tables) and both score
metrics, then executes the whole app headlessly via Streamlit's AppTest
harness: page 1 (products, hero heatmap, no ranked list), the score-metric
selector, clicking a heatmap row to drill into a product, page 2 (tables,
hero heatmap, no ranked list), and the sidebar threshold/rollup controls.
Exits non-zero on any failure.

    python smoke_test.py
"""

from __future__ import annotations

import logging
import sys
import warnings

logging.getLogger("streamlit").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")


def _data_layer() -> None:
    import config
    import data
    aof = data.latest_snapshot()
    assert len(data.available_snapshots()) >= 2

    metrics = [m["key"] for m in config.SCORE_METRICS]
    assert len(metrics) >= 2, "expected multiple configurable score metrics"

    for metric in metrics:
        kpis = data.get_kpis("products", None, aof, metric=metric)
        assert len(kpis) == 4
        ch = data.get_children("products", None, aof, metric=metric)
        assert not ch.empty and {"entity", "score", "wow", "series"} <= set(ch.columns)

    prod = data.get_children("products", None, aof, metric=metrics[0]).iloc[-1]["entity"]
    tch = data.get_children("tables", prod, aof, metric=metrics[0])
    assert not tch.empty
    assert "top_gap" in tch.columns
    assert "owner" not in tch.columns, "owner details should have been removed"

    # switching metric must actually change the numbers (independent columns)
    scores_by_metric = {m: data.get_trend("products", None, aof, metric=m)["score"].iloc[-1]
                        for m in metrics}
    assert len(set(round(v) for v in scores_by_metric.values())) >= 2, scores_by_metric

    # rollup methods must differ (within one metric)
    scores_by_method = {m: data.get_trend("products", None, aof, method=m)["score"].iloc[-1]
                        for m in ("average", "weighted", "pass_rate")}
    assert len(set(round(v) for v in scores_by_method.values())) >= 2, scores_by_method
    print(f"  data layer ok — {len(metrics)} score metrics, "
          f"rollup scores {({k: round(v) for k, v in scores_by_method.items()})}")


def _csv_mode() -> None:
    """RUN_MODE="csv" — reads csv_data/products.csv + csv_data/tables.csv
    (written by `python -m synthetic.generate`). Monkeypatches config.RUN_MODE
    and clears data.py's raw-load caches around the check rather than
    spawning a subprocess, since RUN_MODE is read at call time, not import
    time — see data._load_raw() / _load_raw_products()."""
    import config
    import data

    config.RUN_MODE = "csv"
    data._load_raw.cache_clear()
    data._load_raw_products.cache_clear()
    try:
        metrics = [m["key"] for m in data.available_metrics()]
        assert metrics, "no score metrics available from csv_data/"
        aof = data.latest_snapshot()

        heat = data.get_heatmap("products", None, aof, metric=metrics[0])
        assert heat["rows"], "products heatmap empty in csv mode"
        prod = heat["rows"][0]["entity"]
        heatmap_score = next(r["score"] for _, r in heat["data"].iterrows()
                             if r["entity"] == prod and r[data.SNAP] == aof) \
            if not heat["data"].empty else None

        tkpis = data.get_kpis("tables", prod, aof, metric=metrics[0])
        assert len(tkpis) == 4
        tch = data.get_children("tables", prod, aof, metric=metrics[0])
        assert not tch.empty
        assert "top_gap" in tch.columns

        # the product score must be IDENTICAL whether read from the page-1
        # heatmap (products.csv) or the page-2 KPI card for that product —
        # both should be the authoritative products.csv value, never a
        # silently-differing rollup of tables.csv.
        if heatmap_score is not None and tkpis[0]["value"] is not None:
            assert round(heatmap_score) == tkpis[0]["value"], \
                (heatmap_score, tkpis[0]["value"])

        print(f"  csv mode ok — {len(metrics)} metrics, {len(heat['rows'])} products "
              "from csv_data/, product score agrees page 1 <-> page 2")
    finally:
        config.RUN_MODE = "local"
        data._load_raw.cache_clear()
        data._load_raw_products.cache_clear()


def _app() -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("app.py", default_timeout=45)
    at.run()
    assert not at.exception, at.exception
    md = "\n".join(m.value for m in at.markdown)
    assert "gov-kpi-strip" in md, "KPI strip missing"
    assert "gov-hm-strip" in md, "hero heatmap missing"
    assert "gov-row" not in md, "ranked product list should have been removed"
    assert "gov-tbl" not in md, "tables table should have been removed"
    assert len(at.segmented_control) == 1, "score-metric selector missing"
    assert len(at.button) >= 1, "no heatmap row (drill) buttons rendered"
    print(f"  products page ok — {len(at.button)} heatmap drill buttons, "
          "score selector present, no ranked list")

    # Switch the score metric and confirm the page re-renders without error.
    at.segmented_control[0].set_value("Role").run()
    assert not at.exception, at.exception
    md = "\n".join(m.value for m in at.markdown)
    assert "Role score" in md, "KPI card did not switch to the selected metric"
    print("  score-metric switch ok — KPI/heatmap follow the selector")
    at.segmented_control[0].set_value("Metadata").run()

    # Click a heatmap row (the real drill affordance, not a session_state shortcut).
    row_btn = next(b for b in at.button if b.label == "Recon & Controls")
    row_btn.click().run()
    assert not at.exception, at.exception
    assert at.session_state["page"] == "tables"
    assert at.session_state["product"] == "Recon & Controls"
    md = "\n".join(m.value for m in at.markdown)
    assert "Biggest drag" not in md, "breakdown card should have been removed"
    assert "gov-hm-strip" in md, "tables heatmap missing"
    assert "gov-tbl" not in md, "tables table should have been removed"
    assert "gov-row" not in md, "ranked list should have been removed"
    print("  clicking a heatmap row drills into the product's tables page (no ranked list)")

    at = AppTest.from_file("app.py", default_timeout=45)
    at.run()
    at.selectbox[0].set_value("pass_rate").run()
    at.slider[0].set_value(80).run()
    assert not at.exception, at.exception
    print("  sidebar controls ok — rollup + threshold switch cleanly")


def main() -> int:
    print("data layer:")
    _data_layer()
    print("csv mode:")
    _csv_mode()
    print("app (headless AppTest):")
    _app()
    print("\nALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
