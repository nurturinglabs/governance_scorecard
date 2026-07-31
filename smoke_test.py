"""
smoke_test.py — fast, browser-free verification that the app works.

Runs the data layer across both levels (products -> tables) and executes the
whole app headlessly via Streamlit's AppTest harness: page 1 (products), drill
into a product via session state, page 2 (tables) with the breakdown card,
and the sidebar threshold/rollup controls. Exits non-zero on any failure.

    python smoke_test.py
"""

from __future__ import annotations

import logging
import sys
import warnings

logging.getLogger("streamlit").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")


def _data_layer() -> None:
    import data
    aof = data.latest_snapshot()
    assert len(data.available_snapshots()) >= 2
    kpis = data.get_kpis("products", None, aof)
    assert len(kpis) == 4

    ch = data.get_children("products", None, aof)
    assert not ch.empty and {"entity", "score", "wow", "series"} <= set(ch.columns)
    prod = ch.iloc[-1]["entity"]

    tch = data.get_children("tables", prod, aof)
    assert not tch.empty
    assert {"owner", "top_gap"} <= set(tch.columns)

    bd = data.get_worst_breakdown(prod, aof)
    assert bd["found"]

    # rollup methods must differ
    scores = {m: data.get_trend("products", None, aof, method=m)["score"].iloc[-1]
              for m in ("average", "weighted", "pass_rate")}
    assert len(set(round(v) for v in scores.values())) >= 2, scores
    print(f"  data layer ok — rollup scores {({k: round(v) for k, v in scores.items()})}")


def _app() -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("app.py", default_timeout=45)
    at.run()
    assert not at.exception, at.exception
    md = "\n".join(m.value for m in at.markdown)
    assert "gov-kpis" in md, "KPI cards missing"
    assert "gov-row" in md, "product rows missing"
    assert len(at.button) >= 1, "no drill buttons rendered"
    print(f"  products page ok — {len(at.button)} drill buttons")

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
