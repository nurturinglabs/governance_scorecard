"""
data.py — THE PORT SEAM.

Public functions return pandas DataFrames / dicts with identical shapes across
run modes. RUN_MODE decides only how the raw table-grain fact is *loaded*:
    local     -> read synthetic/*.parquet
    csv       -> read config.CSV["tables_file"]  (config.CSV["products_file"]
                 too, if present — see _products_fact() below)
    snowflake -> session.sql(...).to_pandas()  (see _snowflake.py)

Everything after loading — scope filtering, exclusion, rollups, KPIs, drill
rows, heatmap — is backend-agnostic and lives here, so the modes can never
disagree. Components and app.py call these functions and never touch SQL, a
Snowpark session, a CSV path, or a raw column name.

The fact carries several INDEPENDENT weekly score metrics (config.SCORE_METRICS),
not one composite. Every public function takes an explicit `metric` argument
(the SCORE_METRICS key) alongside threshold/rollup — all three default to config
so the cache key reflects them and the page-level selector invalidates cleanly.

CSV mode is the one exception to "always roll up from the table-grain fact":
its products.csv is a pre-aggregated, AUTHORITATIVE product-grain source (a
business team's own tracker), so the products page reads it directly instead
of re-deriving product numbers from tables.csv — see _products_fact() and
_focus_trend(). Table counts (n_tables/n_below) still come from tables.csv
either way, since products.csv doesn't carry them.
"""

from __future__ import annotations

import functools

import pandas as pd

import config

C = config.COLUMNS
PRODUCT, DB, SCHEMA, TABLE = C["data_product"], C["database"], C["schema"], C["table"]
FQN, SNAP = C["table_fqn"], C["snapshot_date"]
WEIGHT = C["weight"]

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
def _metric_csv_colmap(metrics_key: str = "column") -> dict:
    """canonical_column -> csv_header for every metric that has a csv_column."""
    return {m["column"]: m["csv_column"] for m in config.SCORE_METRICS if m.get("csv_column")}


def _load_csv(path, base_colmap: dict) -> pd.DataFrame:
    """Read a CSV and rename its headers to canonical column names. `base_colmap`
    is canonical -> csv_header for the non-score columns; score columns are
    added from SCORE_METRICS automatically. Raises clearly if an expected
    header is missing, rather than failing later with a cryptic KeyError."""
    raw = pd.read_csv(path)
    colmap = {**base_colmap, **_metric_csv_colmap()}
    missing = [csv_col for csv_col in colmap.values() if csv_col not in raw.columns]
    if missing:
        raise ValueError(f"{path} is missing expected column(s): {missing}")
    return raw.rename(columns={csv_col: canon for canon, csv_col in colmap.items()})


@functools.lru_cache(maxsize=1)
def _load_raw() -> pd.DataFrame:
    if config.RUN_MODE == "snowflake":
        from _snowflake import load_fact  # lazy: snowpark only in SiS
        df = load_fact()
    elif config.RUN_MODE == "csv":
        df = _load_csv(config.CSV["tables_file"], config.CSV["tables_columns"])
        # this CSV schema has no separate database concept — schema doubles
        # as the "N databases" grouping (see get_kpis' db_label)
        df[DB] = df[SCHEMA]
        df[FQN] = (df[PRODUCT].astype(str) + "." + df[SCHEMA].astype(str)
                  + "." + df[TABLE].astype(str))
        df[WEIGHT] = 1.0  # not tracked in this CSV schema; "weighted" == "average"
    else:
        df = pd.read_parquet(config.FACT_PARQUET)
    df[SNAP] = pd.to_datetime(df[SNAP])
    return df


@functools.lru_cache(maxsize=1)
def _load_raw_products() -> pd.DataFrame | None:
    """Pre-aggregated PRODUCT-grain fact — csv mode only, and only if
    config.CSV["products_file"] is readable. None means "no separate product
    source"; callers then fall back to rolling product numbers up from the
    table-grain fact, exactly as local/snowflake mode always have."""
    if config.RUN_MODE != "csv":
        return None
    df = _load_csv(config.CSV["products_file"], config.CSV["products_columns"])
    df[SNAP] = pd.to_datetime(df[SNAP])
    df[WEIGHT] = 1.0
    return df


def _products_fact() -> pd.DataFrame | None:
    return _load_raw_products()


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


def _focus_trend(level: str, parent_id, thr: int, method: str, score_col: str) -> pd.DataFrame:
    """Weekly [snapshot_date, score] for the FOCUS entity — the whole
    portfolio at level="products", or one product at level="tables" (its
    score_card, regardless of which page you're viewing it from).

    Uses the pre-aggregated products fact directly when one is loaded (csv
    mode): a product's own row there IS its score, no rollup needed, and the
    portfolio number is method-aware rollup of THOSE rows (still meaningful:
    "average" of products, "weighted" falls back to average since csv mode
    doesn't carry weight, "pass_rate" = % of products passing). Otherwise —
    local/snowflake mode, no separate products source — rolls up from the
    table-grain fact exactly as before.
    """
    pf = _products_fact()
    if pf is not None and level in ("products", "tables"):
        sub = pf if level == "products" else pf[pf[PRODUCT] == parent_id]
        return _rollup(sub, [SNAP], thr, method, score_col).sort_values(SNAP)
    sc = _scope(_fact(), level, parent_id)
    return _rollup(sc, [SNAP], thr, method, score_col).sort_values(SNAP)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
@_cache
def available_metrics() -> list[dict]:
    """SCORE_METRICS filtered to those whose column actually exists in the
    loaded table-grain fact — so the page-top selector only ever offers a
    score the current backend (parquet / csv / snowflake) can actually back."""
    cols = set(_load_raw().columns)
    return [m for m in config.SCORE_METRICS if m["column"] in cols]


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
    r = _focus_trend(level, parent_id, thr, method, score_col)
    r = r[r[SNAP] <= _as_ts(as_of)].tail(weeks)
    return r[[SNAP, "score"]].reset_index(drop=True)


def _child_weekly(level: str, parent_id, as_of, weeks: int, thr: int, method: str, score_col: str):
    """Per-child weekly rollup within the window. Returns (df, child_col, dates).

    n_tables/n_below always come from the table-grain fact (a pre-aggregated
    products source, csv mode, doesn't carry them). The "score" column is
    overridden from that products source when one exists AND level=="products"
    — an authoritative product number, not a rollup guess — while any
    (product, week) it doesn't cover renders as an honest gap rather than
    silently falling back to the rollup for just that cell.
    """
    child_col = config.LEVELS[level]["grain_col"]
    sc = _scope(_fact(), level, parent_id)
    wk = _rollup(sc, [child_col, SNAP], thr, method, score_col)

    pf = _products_fact()
    if pf is not None and level == "products":
        score_wk = _rollup(pf, [PRODUCT, SNAP], thr, method, score_col)
        override = score_wk[[PRODUCT, SNAP, "score"]].rename(columns={PRODUCT: child_col})
        wk = wk.drop(columns="score").merge(override, on=[child_col, SNAP], how="left")

    dates = sorted(d for d in wk[SNAP].unique() if d <= _as_ts(as_of))[-weeks:]
    wk = wk[wk[SNAP].isin(dates)]
    return wk, child_col, dates


@_cache
def get_heatmap(level: str, parent_id, as_of, weeks: int = None,
                threshold: int = None, method: str = None, metric: str = None) -> dict:
    """Long-form entity x week scores + a y-axis order (worst-latest sorting)
    + `rows`: one dict per entity in that order, carrying the extras the
    heatmap needs as a row-label tooltip (tables/below for products, top_gap
    for tables) — the heatmap is the hero view, so these extras ride along
    instead of a separate ranked list."""
    weeks = weeks or config.HEATMAP_WEEKS
    thr, method, metric = _defaults(threshold, method, metric)
    score_col = config.score_metric(metric)["column"]
    wk, child_col, dates = _child_weekly(level, parent_id, as_of, weeks, thr, method, score_col)
    if wk.empty:
        return {"data": pd.DataFrame(columns=["entity", "label", SNAP, "score"]),
                "order": [], "dates": [], "rows": []}
    labels = _labels(level, wk[child_col].unique())
    wk = wk.rename(columns={child_col: "entity"})
    wk["label"] = wk["entity"].map(labels)
    latest = _as_ts(as_of)
    order = (wk[wk[SNAP] == latest].sort_values("score")[["label"]]["label"].tolist()
             or wk.sort_values("score")["label"].unique().tolist())

    children = get_children(level, parent_id, as_of, weeks, thr, method, metric)
    by_label = {r["label"]: r for _, r in children.iterrows()}
    rows = []
    for lbl in order:
        c = by_label.get(lbl)
        if c is None:
            continue
        if level == "tables":
            rows.append({"entity": c["entity"], "label": lbl, "top_gap": c["top_gap"]})
        else:
            rows.append({"entity": c["entity"], "label": lbl,
                        "tables": int(c["n_tables"]), "below": int(c["n_below"])})

    return {"data": wk[["entity", "label", SNAP, "score"]], "order": order,
            "dates": dates, "rows": rows}


def _labels(level: str, entities) -> dict:
    """Display labels for entity ids (short table name for the leaf fqns)."""
    if level == "tables":
        return {e: str(e).split(".")[-1] for e in entities}
    return {e: str(e) for e in entities}


@_cache
def get_children(level: str, parent_id, as_of, weeks: int = None,
                 threshold: int = None, method: str = None, metric: str = None) -> pd.DataFrame:
    """One row per child entity: current score, WoW, sparkline series, counts,
    and (leaf only) top gap. Sorted worst-first at the leaf, best-first above it."""
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
    """Add a short 'top gap' string per table, for the given metric."""
    f = _fact()
    snap = f[(f[PRODUCT] == product_id) & (f[SNAP] == as_of)].set_index(FQN)
    comps = _component_columns(metric)
    gaps = []
    for ent in out["entity"]:
        gaps.append(_top_gap(snap.loc[ent], comps) if ent in snap.index else "no snapshot")
    out["top_gap"] = gaps
    return out


def _top_gap(row, comps: list[dict]) -> str:
    """Human 'top gap' from the weakest configured components (empty until
    real per-dimension columns are confirmed)."""
    flags = []
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

    trend = _focus_trend(level, parent_id, thr, method, score_col)
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
        db_label = "schemas" if config.RUN_MODE == "csv" else "databases"
        return [score_card,
                {"label": "Data products", "value": snap_now[PRODUCT].nunique(),
                 "delta": None, "inverse": False,
                 "sub": f"{snap_now[DB].nunique()} {db_label}"},
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
