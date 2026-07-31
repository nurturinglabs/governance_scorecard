"""
data.py — THE PORT SEAM.

Public functions return pandas DataFrames / dicts with identical shapes in both
run modes. RUN_MODE decides only how the raw table-grain fact is *loaded*:
    local     -> read synthetic/*.parquet
    snowflake -> session.sql(...).to_pandas()  (see _snowflake.py)

Everything after loading — scope filtering, exclusion, rollups, KPIs, drill rows,
heatmap, breakdown — is backend-agnostic and lives here, so the two modes can
never disagree. Components and app.py call these functions and never touch SQL,
a Snowpark session, or a raw column name.

The fact carries several INDEPENDENT weekly score metrics (config.SCORE_METRICS),
not one composite. Every public function takes an explicit `metric` argument
(the SCORE_METRICS key) alongside threshold/rollup — all three default to config
so the cache key reflects them and the page-level selector invalidates cleanly.
"""

from __future__ import annotations

import functools

import pandas as pd

import config

C = config.COLUMNS
PRODUCT, DB, SCHEMA, TABLE = C["data_product"], C["database"], C["schema"], C["table"]
FQN, SNAP = C["table_fqn"], C["snapshot_date"]
OWNER, WEIGHT = C["owner"], C["weight"]

# Streamlit caching, but degrade to a no-op when run outside a Streamlit runtime
# (e.g. the headless smoke test) so importing this module never requires a script
# run context.
try:
    import streamlit as st
    _cache = st.cache_data(show_spinner=False)
except Exception:  # pragma: no cover
    def _cache(fn):
        return fn


# --------------------------------------------------------------------------- #
# Raw fact loading (the only backend-specific step)
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def _load_raw() -> pd.DataFrame:
    if config.RUN_MODE == "snowflake":
        from _snowflake import load_fact  # lazy: snowpark only in SiS
        df = load_fact()
    else:
        df = pd.read_parquet(config.FACT_PARQUET)
    df[SNAP] = pd.to_datetime(df[SNAP])
    return df


def _fact() -> pd.DataFrame:
    """Scored table-grain fact: exclusion applied, staging tables removed."""
    df = _load_raw()
    if config.SCOPE_EXCLUDE["enabled"]:
        keep = ~df[TABLE].map(config.is_excluded)
        df = df[keep]
    return df


def _as_ts(as_of) -> pd.Timestamp:
    return pd.Timestamp(as_of).normalize()


def _component_columns(metric: str) -> list[dict]:
    """This metric's configured component entries whose column actually exists
    in the fact. Empty (not an error) until real per-dimension columns are
    confirmed — callers degrade gracefully rather than invent a breakdown."""
    comps = config.score_metric(metric).get("components") or []
    cols = set(_load_raw().columns)
    return [c for c in comps if c.get("column") and c["column"] in cols]


# --------------------------------------------------------------------------- #
# Scope + rollup (shared)
# --------------------------------------------------------------------------- #
def _scope(df: pd.DataFrame, level: str, parent_id) -> pd.DataFrame:
    if level == "products":
        return df
    if level == "tables":
        return df[df[PRODUCT] == parent_id]
    raise ValueError(f"unknown level: {level}")


def _rollup(df: pd.DataFrame, keys: list[str], threshold: int, method: str,
           score_col: str) -> pd.DataFrame:
    """Aggregate table-grain scores to `keys` grain per ROLLUP_METHOD.

    Returns keys + [score, n_tables, n_below]. Works at any grain, including the
    table grain (n_tables == 1, score == the row's own score).
    """
    if df.empty:
        return pd.DataFrame(columns=keys + ["score", "n_tables", "n_below"])
    tmp = df[keys + [score_col, WEIGHT]].copy()
    tmp["_below"] = (tmp[score_col] < threshold).astype(int)
    tmp["_sw"] = tmp[score_col] * tmp[WEIGHT]
    g = tmp.groupby(keys, as_index=False, dropna=False).agg(
        n_tables=(score_col, "size"),
        n_below=("_below", "sum"),
        _sum=(score_col, "sum"),
        _sumsw=("_sw", "sum"),
        _sumw=(WEIGHT, "sum"),
    )
    if method == "weighted":
        g["score"] = g["_sumsw"] / g["_sumw"].replace(0, pd.NA)
    elif method == "pass_rate":
        g["score"] = 100.0 * (g["n_tables"] - g["n_below"]) / g["n_tables"]
    else:  # average
        g["score"] = g["_sum"] / g["n_tables"]
    g["score"] = g["score"].round(1)
    return g[keys + ["score", "n_tables", "n_below"]]


def _defaults(threshold, method, metric):
    return (config.THRESHOLD if threshold is None else int(threshold),
            config.ROLLUP_METHOD if method is None else method,
            config.DEFAULT_SCORE_METRIC if metric is None else metric)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
@_cache
def available_snapshots() -> list[pd.Timestamp]:
    return sorted(_fact()[SNAP].unique())


@_cache
def latest_snapshot() -> pd.Timestamp:
    return max(available_snapshots())


@_cache
def get_scope() -> pd.DataFrame:
    """Distinct product/database tree (for nav + breadcrumb labels)."""
    f = _fact()
    return (f[[PRODUCT, DB]].drop_duplicates()
            .sort_values([PRODUCT, DB]).reset_index(drop=True))


@_cache
def get_trend(level: str, parent_id, as_of, weeks: int = None,
              threshold: int = None, method: str = None, metric: str = None) -> pd.DataFrame:
    """Focus-entity score per week, up to as_of. Columns: snapshot_date, score."""
    weeks = weeks or config.TREND_WEEKS
    thr, method, metric = _defaults(threshold, method, metric)
    score_col = config.score_metric(metric)["column"]
    sc = _scope(_fact(), level, parent_id)
    r = _rollup(sc, [SNAP], thr, method, score_col).sort_values(SNAP)
    r = r[r[SNAP] <= _as_ts(as_of)].tail(weeks)
    return r[[SNAP, "score"]].reset_index(drop=True)


def _child_weekly(level: str, parent_id, as_of, weeks: int, thr: int, method: str, score_col: str):
    """Per-child weekly rollup within the window. Returns (df, child_col, dates)."""
    child_col = config.LEVELS[level]["grain_col"]
    sc = _scope(_fact(), level, parent_id)
    wk = _rollup(sc, [child_col, SNAP], thr, method, score_col)
    dates = sorted(d for d in wk[SNAP].unique() if d <= _as_ts(as_of))[-weeks:]
    wk = wk[wk[SNAP].isin(dates)]
    return wk, child_col, dates


@_cache
def get_heatmap(level: str, parent_id, as_of, weeks: int = None,
                threshold: int = None, method: str = None, metric: str = None) -> dict:
    """Long-form entity x week scores + a y-axis order (worst-latest sorting)."""
    weeks = weeks or config.HEATMAP_WEEKS
    thr, method, metric = _defaults(threshold, method, metric)
    score_col = config.score_metric(metric)["column"]
    wk, child_col, dates = _child_weekly(level, parent_id, as_of, weeks, thr, method, score_col)
    if wk.empty:
        return {"data": pd.DataFrame(columns=["entity", "label", SNAP, "score"]),
                "order": [], "dates": []}
    labels = _labels(level, wk[child_col].unique())
    wk = wk.rename(columns={child_col: "entity"})
    wk["label"] = wk["entity"].map(labels)
    latest = _as_ts(as_of)
    order = (wk[wk[SNAP] == latest].sort_values("score")[["label"]]["label"].tolist()
             or wk.sort_values("score")["label"].unique().tolist())
    return {"data": wk[["entity", "label", SNAP, "score"]], "order": order, "dates": dates}


def _labels(level: str, entities) -> dict:
    """Display labels for entity ids (short table name for the leaf fqns)."""
    if level == "tables":
        return {e: str(e).split(".")[-1] for e in entities}
    return {e: str(e) for e in entities}


@_cache
def get_children(level: str, parent_id, as_of, weeks: int = None,
                 threshold: int = None, method: str = None, metric: str = None) -> pd.DataFrame:
    """One row per child entity: current score, WoW, sparkline series, counts,
    and (leaf only) owner / top gap. Sorted worst-first at the leaf, best-first
    above it."""
    weeks = weeks or config.HEATMAP_WEEKS
    thr, method, metric = _defaults(threshold, method, metric)
    score_col = config.score_metric(metric)["column"]
    wk, child_col, dates = _child_weekly(level, parent_id, as_of, weeks, thr, method, score_col)
    labels = _labels(level, wk[child_col].unique()) if not wk.empty else {}
    latest = _as_ts(as_of)
    prev = dates[-2] if len(dates) >= 2 else None

    rows = []
    for ent, g in wk.groupby(child_col):
        g = g.sort_values(SNAP)
        cur_row = g[g[SNAP] == latest]
        cur = float(cur_row["score"].iloc[0]) if not cur_row.empty else None
        prv = None
        if prev is not None:
            pr = g[g[SNAP] == prev]
            prv = float(pr["score"].iloc[0]) if not pr.empty else None
        series = [round(float(s), 1) for s in g["score"].tolist()]  # sparkline
        n_tables = int(cur_row["n_tables"].iloc[0]) if not cur_row.empty else 0
        n_below = int(cur_row["n_below"].iloc[0]) if not cur_row.empty else 0
        rows.append({
            "entity": ent,
            "label": labels.get(ent, str(ent)),
            "score": None if cur is None else round(cur),
            "wow": None if (cur is None or prv is None) else round(cur - prv),
            "series": series,
            "n_tables": n_tables,
            "n_below": n_below,
        })

    out = pd.DataFrame(rows)
    if level == "tables":
        out = _attach_leaf_detail(out, parent_id, latest, metric)
        out = out.sort_values("score", na_position="last").reset_index(drop=True)
    else:
        out = out.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
    return out


def _attach_leaf_detail(out: pd.DataFrame, product_id, as_of, metric: str) -> pd.DataFrame:
    """Add owner and a short 'top gap' string per table, for the given metric."""
    f = _fact()
    snap = f[(f[PRODUCT] == product_id) & (f[SNAP] == as_of)].set_index(FQN)
    comps = _component_columns(metric)
    owners, gaps = [], []
    for ent in out["entity"]:
        if ent in snap.index:
            r = snap.loc[ent]
            owners.append(None if pd.isna(r.get(OWNER)) else str(r.get(OWNER)))
            gaps.append(_top_gap(r, comps))
        else:
            owners.append(None)
            gaps.append("no snapshot")
    out["owner"] = owners
    out["top_gap"] = gaps
    return out


def _top_gap(row, comps: list[dict]) -> str:
    """Human 'top gap' from missing ownership / the weakest configured
    components (empty until real per-dimension columns are confirmed)."""
    flags = []
    if OWNER in row.index and pd.isna(row.get(OWNER)):
        flags.append("no owner")
    ratios = sorted(((c, row[c["column"]] / c["max"]) for c in comps), key=lambda x: x[1])
    for c, r in ratios:
        if r >= 0.75 or len(flags) >= 2:
            break
        flags.append(f"low {c['label'].lower()}")
    return " · ".join(flags[:2]) if flags else "—"


@_cache
def get_kpis(level: str, parent_id, as_of, threshold: int = None,
             method: str = None, metric: str = None) -> list[dict]:
    """Four KPI cards for the level. Each: label, value, delta, inverse, sub."""
    thr, method, metric = _defaults(threshold, method, metric)
    score_col = config.score_metric(metric)["column"]
    sc = _scope(_fact(), level, parent_id)
    latest = _as_ts(as_of)
    dates = sorted(d for d in sc[SNAP].unique() if d <= latest)
    prev = dates[-2] if len(dates) >= 2 else None

    trend = _rollup(sc, [SNAP], thr, method, score_col)
    cur = _pick(trend, latest)
    prv = _pick(trend, prev)
    snap_now = sc[sc[SNAP] == latest]
    snap_prev = sc[sc[SNAP] == prev] if prev is not None else snap_now.iloc[0:0]
    below_now = int((snap_now[score_col] < thr).sum())
    below_prev = int((snap_prev[score_col] < thr).sum()) if not snap_prev.empty else None

    score_card = {"label": config.score_metric(metric)["label"], "value": _int(cur),
                  "delta": _sub(cur, prv), "inverse": False, "sub": None}
    below_card = {"label": f"Below threshold <{thr}", "value": below_now,
                  "delta": _sub(below_now, below_prev), "inverse": True, "sub": None}

    if level == "products":
        return [score_card,
                {"label": "Data products", "value": snap_now[PRODUCT].nunique(),
                 "delta": None, "inverse": False,
                 "sub": f"{snap_now[DB].nunique()} databases"},
                {"label": "Tables tracked", "value": int(len(snap_now)),
                 "delta": None, "inverse": False, "sub": "scored"},
                below_card]
    # tables (product-scoped leaf list)
    weak = _weakest_dimension(snap_now, metric)
    return [score_card,
            {"label": "Tables", "value": int(len(snap_now)),
             "delta": None, "inverse": False, "sub": "in this product"},
            below_card,
            {"label": "Weakest dimension", "value": weak["label"],
             "delta": None, "inverse": False, "sub": weak["sub"]}]


def _weakest_dimension(snap: pd.DataFrame, metric: str) -> dict:
    comps = _component_columns(metric)
    if snap.empty or not comps:
        return {"label": "—", "sub": None}
    worst, worst_ratio = None, 2.0
    for c in comps:
        ratio = (snap[c["column"]] / c["max"]).mean()
        if ratio < worst_ratio:
            worst_ratio, worst = ratio, c
    return {"label": worst["label"], "sub": f"avg {round(worst_ratio * 100)}%"}


@_cache
def get_worst_breakdown(product_id, as_of, threshold: int = None,
                        method: str = None, metric: str = None) -> dict:
    """Worst scored table in a product on the selected metric, + its component
    breakdown (leaf card)."""
    thr, _, metric = _defaults(threshold, None, metric)
    score_col = config.score_metric(metric)["column"]
    f = _fact()
    latest = _as_ts(as_of)
    snap = f[(f[PRODUCT] == product_id) & (f[SNAP] == latest)]
    if snap.empty:
        return {"found": False}
    row = snap.sort_values(score_col).iloc[0]
    comps = _component_columns(metric)
    result = {
        "found": True,
        "fqn": row[FQN],
        "label": str(row[FQN]).split(".")[-1],
        "score": int(row[score_col]),
        "owner": None if pd.isna(row.get(OWNER)) else str(row.get(OWNER)),
        "threshold": thr,
        "has_components": bool(comps),
    }
    if comps:
        result["components"] = [
            {"label": c["label"], "pts": int(row[c["column"]]), "max": c["max"],
             "ratio": float(row[c["column"]]) / c["max"], "icon": c.get("icon")}
            for c in comps
        ]
    else:  # graceful fallback: worst table trend (no confirmed component columns)
        hist = (f[f[FQN] == row[FQN]].sort_values(SNAP).tail(config.HEATMAP_WEEKS))
        result["series"] = [round(float(s)) for s in hist[score_col].tolist()]
    return result


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _pick(trend: pd.DataFrame, when):
    if when is None or trend.empty:
        return None
    r = trend[trend[SNAP] == when]
    return float(r["score"].iloc[0]) if not r.empty else None


def _sub(a, b):
    if a is None or b is None:
        return None
    return round(a - b)


def _int(x):
    return None if x is None else round(x)
