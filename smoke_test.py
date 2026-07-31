"""
smoke_test.py — fast, browser-free verification that the app works.

Runs the data layer across both levels (products -> tables) and both score
metrics, then executes the whole app headlessly via Streamlit's AppTest
harness: page 1 (products), the score-metric selector, drill into a product
via session state, page 2 (tables) with the breakdown card, and the sidebar
threshold/rollup controls. Exits non-zero on any failure.

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
    assert {"owner", "top_gap"} <= set(tch.columns)

    bd = data.get_worst_breakdown(prod, aof, metric=metrics[0])
    assert bd["found"]

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


def _app() -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("app.py", default_timeout=45)
    at.run()
    assert not at.exception, at.exception
    md = "\n".join(m.value for m in at.markdown)
    assert "gov-kpis" in md, "KPI cards missing"
    assert "gov-row" in md, "product rows missing"
    assert len(at.segmented_control) == 1, "score-metric selector missing"
    assert len(at.button) >= 1, "no drill buttons rendered"
    print(f"  products page ok — {len(at.button)} drill buttons, score selector present")

    # Switch the score metric and confirm the page re-renders without error.
    at.segmented_control[0].set_value("Role score").run()
    assert not at.exception, at.exception
    md = "\n".join(m.value for m in at.markdown)
    assert "Role score" in md, "KPI card did not switch to the selected metric"
    print("  score-metric switch ok — KPI/heatmap follow the selector")

    # Drill into a product via session state (mirrors clicking "View tables →").
    at.session_state["page"] = "tables"
    at.session_state["product"] = "Recon & Controls"
    at.run()
    assert not at.exception, at.exception
    md = "\n".join(m.value for m in at.markdown)
    assert "Biggest drag" in md, "breakdown card missing"
    assert "gov-tbl" in md, "tables list missing"
    print("  tables page ok — breakdown card + tables list rendered")

    at = AppTest.from_file("app.py", default_timeout=45)
    at.run()
    at.selectbox[0].set_value("pass_rate").run()
    at.slider[0].set_value(80).run()
    assert not at.exception, at.exception
    print("  sidebar controls ok — rollup + threshold switch cleanly")


def main() -> int:
    print("data layer:")
    _data_layer()
    print("app (headless AppTest):")
    _app()
    print("\nALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
