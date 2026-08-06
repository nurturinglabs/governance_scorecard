"""
config.py — single source of truth for the Data Governance Scorecard.

Every other module (data.py, components/*, synthetic/generate.py) imports its
knobs from here. Nothing below should be duplicated as a literal anywhere else.

Adapting to the real Snowflake schema is a config edit, not a code edit:
change SNOWFLAKE + COLUMNS and the rest of the app follows.
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from pathlib import Path

# --------------------------------------------------------------------------- #
# Run mode — the ONLY switch that flips the backend. No other code change.
# --------------------------------------------------------------------------- #
# "local"     -> data.py reads synthetic/*.parquet
# "csv"       -> data.py reads the two CSV_* exports below (no Snowflake, no
#                synthetic generator — point it at a real tracker export)
# "snowflake" -> data.py runs session.sql(...).to_pandas() in SiS
RUN_MODE = os.environ.get("GOV_RUN_MODE", "local").lower()

# --------------------------------------------------------------------------- #
# Paths (local mode)
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent
SYNTHETIC_DIR = PROJECT_ROOT / "synthetic"
FACT_PARQUET = SYNTHETIC_DIR / "governance_score_history.parquet"

# --------------------------------------------------------------------------- #
# Snowflake objects (snowflake mode) — [CONFIRM] the real names.
# --------------------------------------------------------------------------- #
SNOWFLAKE = {
    "history_table": "GOVERNANCE.PUBLIC.GOVERNANCE_SCORE_HISTORY",  # [CONFIRM]
    # If a pre-built rollup/agg table exists, name it here and data.py will
    # read it instead of computing rollups on the fly. None -> compute in SQL.
    "agg_table": None,  # [CONFIRM]
    "warehouse": None,  # SiS uses the app's warehouse; set only if overriding
}

# --------------------------------------------------------------------------- #
# CSV source (RUN_MODE="csv") — two plain CSV exports instead of Snowflake or
# the synthetic parquet: one pre-aggregated at PRODUCT grain (one row per
# product per week — the authoritative product number; the app does not
# re-derive it by rolling up tables), one at TABLE grain (one row per table
# per week, for the drill-down page). `python -m synthetic.generate` also
# writes demo copies of both here so csv mode has something to point at.
#
# `*_columns` maps the app's canonical column name -> the CSV's literal
# header text — edit the values to match your file, not the keys. Each score
# metric's own header is its `csv_column` in SCORE_METRICS below.
# --------------------------------------------------------------------------- #
CSV_DIR = PROJECT_ROOT / "csv_data"
CSV = {
    "products_file": CSV_DIR / "products.csv",
    "tables_file": CSV_DIR / "tables.csv",
    "products_columns": {
        "snapshot_date": "Date",
        "data_product": "Data_Product",
    },
    "tables_columns": {
        "snapshot_date": "Date",
        "data_product": "Data_Product",
        "schema_name": "Schema",
        "table_name": "TABLE_NAME",
    },
}

# --------------------------------------------------------------------------- #
# Logical -> physical column mapping.
# data.py refers to columns via COLUMNS["score"] etc., never by raw name, so a
# schema difference is fixed here in one place.
# --------------------------------------------------------------------------- #
COLUMNS = {
    "data_product": "data_product",
    "database": "database_name",
    "schema": "schema_name",
    "table": "table_name",
    "table_fqn": "table_fqn",          # stable id: DB.SCHEMA.TABLE
    "snapshot_date": "snapshot_date",
    "weight": "weight",                # row count / criticality (weighted rollup)
}

# --------------------------------------------------------------------------- #
# Hierarchy — two levels, one screen parametrized by grain.
#   products -> tables (database level is collapsed away; tables roll up
#   directly under their product, spanning all of the product's databases).
# grain_col  = column that identifies a row at this level's CHILD entity
# child_page = the page you drill INTO from here (None = terminal)
# drillable  = whether rows drill further
# --------------------------------------------------------------------------- #
LEVELS = {
    "products": {
        "label": "All products",
        "grain_col": COLUMNS["data_product"],   # rows = data products
        "child_page": "tables",
        "drillable": True,
    },
    "tables": {
        "label": "Product",
        "grain_col": COLUMNS["table_fqn"],       # rows = tables (terminal)
        "child_page": None,
        "drillable": False,
    },
}
LEVEL_ORDER = ["products", "tables"]

# --------------------------------------------------------------------------- #
# Scoring knobs — real decisions, not placeholders.
# --------------------------------------------------------------------------- #
# A table at or above THRESHOLD "passes". Governance teams move this goalpost;
# it is read everywhere (KPIs, pass_rate rollup, below-threshold counts).
THRESHOLD = 70

# How a table-level score rolls up to database / product:
#   "average"   -> simple mean of child scores
#   "weighted"  -> mean weighted by COLUMNS["weight"]
#   "pass_rate" -> % of child tables with score >= THRESHOLD
# [CONFIRM] which one — it changes what the trend line MEANS.
ROLLUP_METHOD = "average"

# --------------------------------------------------------------------------- #
# Score bands -> color + label. Single source for heatmap cells, KPI coloring,
# and drill-list score coloring. Ordered high -> low; band_for() picks the first
# whose `min` the score meets.
# --------------------------------------------------------------------------- #
SCORE_BANDS = [
    {"min": 85, "color": "#6FA83C", "text": "#16330A", "label": "Strong"},
    {"min": 75, "color": "#AFD07A", "text": "#24400A", "label": "Healthy"},
    {"min": 65, "color": "#F2B04A", "text": "#4A2B02", "label": "At risk"},
    {"min": 0,  "color": "#EF6C63", "text": "#4A0F0C", "label": "Failing"},
]


def band_for(score: float | int) -> dict:
    """Return the SCORE_BANDS entry a score falls into."""
    for band in SCORE_BANDS:
        if score >= band["min"]:
            return band
    return SCORE_BANDS[-1]


# --------------------------------------------------------------------------- #
# Scope exclusion — staging / temp / backup tables are usually NOT meant to be
# governed and drag a database's number down if scored. Exclusion is visible and
# configurable, never silent.
#   - EXCLUDE_GLOBS  : fnmatch patterns for local (Python) filtering
#   - EXCLUDE_REGEX  : Snowflake RLIKE pattern (avoids LIKE underscore-wildcard
#                      pitfalls) for pushing the filter into SQL
# --------------------------------------------------------------------------- #
SCOPE_EXCLUDE = {
    "enabled": True,
    "globs": ["*_STG", "*_TMP", "*_BKP", "*_TEST", "*_SCRATCH"],
    "regex": r"_(STG|TMP|BKP|TEST|SCRATCH)$",
}
_EXCLUDE_RE = re.compile(SCOPE_EXCLUDE["regex"], re.IGNORECASE)


def is_excluded(table_name: str) -> bool:
    """True if a bare table name should be excluded from scoring."""
    if not SCOPE_EXCLUDE["enabled"]:
        return False
    return bool(_EXCLUDE_RE.search(table_name or ""))


# --------------------------------------------------------------------------- #
# Score metrics — the fact table tracks several INDEPENDENT weekly scores per
# table (metadata quality, role/ownership hygiene, activity, ...), not one
# composite "governance score". The app-wide score selector (top of every page)
# picks one of these; every KPI, chart, heatmap, and list reads that metric's
# column. Add a metric here and it appears in the selector automatically — no
# other code change needed.
#
# `components` optionally names per-dimension points columns (label, max,
# column) that explain *why* the worst table scores low on this metric, feeding
# the leaf breakdown card — the same idea as the old COMPONENT_WEIGHTS, just
# scoped to one metric. Leave it None until those columns are confirmed in the
# real table; data.py then degrades the breakdown card to the worst table's own
# trend instead of inventing a decomposition that doesn't exist.
#
# `csv_column` is this metric's literal header in the CSV_* exports above
# (RUN_MODE="csv" only). The picker at the top of the page only ever offers a
# metric whose `column` is actually present in the loaded data (see
# data.available_metrics()) — so a metric can be listed here "ahead of" the
# data having it yet, or a CSV can carry more score columns than are listed
# here and the extras are simply never offered. Either way, adding/removing a
# metric is the only edit needed to change what's pickable.
# --------------------------------------------------------------------------- #
SCORE_METRICS = [
    {"key": "metadata", "label": "Metadata score", "column": "metadata_score", "csv_column": "Metadata_SCORE", "components": None},
    {"key": "role",     "label": "Role score",     "column": "role_score",     "csv_column": "Role_SCORE",     "components": None},
    {"key": "act",      "label": "Activity score", "column": "act_score",     "csv_column": "ACT_SCORE",      "components": None},
]
DEFAULT_SCORE_METRIC = SCORE_METRICS[0]["key"]


def score_metric(key: str | None) -> dict:
    """Look up a SCORE_METRICS entry by key; falls back to the default metric
    for None/unknown keys so callers never have to null-check."""
    for m in SCORE_METRICS:
        if m["key"] == key:
            return m
    return score_metric(DEFAULT_SCORE_METRIC) if key != DEFAULT_SCORE_METRIC else SCORE_METRICS[0]

# --------------------------------------------------------------------------- #
# Trend windows
# --------------------------------------------------------------------------- #
TREND_WEEKS = 12     # trend line
HEATMAP_WEEKS = 10   # entity x week heatmap

# --------------------------------------------------------------------------- #
# Synthetic-data generation (local mode only). Deterministic given SEED.
# --------------------------------------------------------------------------- #
SYNTHETIC = {
    "seed": 20260724,
    # Anchor to a fixed most-recent Friday so parquet is reproducible across runs
    # regardless of the machine date. Set to None to use the latest Friday <= today.
    "anchor_friday": date(2026, 7, 24),
    "weeks": 12,
    "databases_per_product": 4,     # 6 products x 4 = 24 databases
    "tables_per_database": (12, 22),  # inclusive range, sampled per database
    "inject_gaps": True,            # drop a few (table, week) rows to exercise
                                    # honest gap rendering in the heatmap
    # (name, trajectory, baseline_quality 0-1). Baseline drives the mean of the
    # "soft" dimensions; trajectory drifts them week over week.
    "products": [
        ("Reference & Security Master", "rising",   0.86),
        ("Investments Data Warehouse",  "stable",   0.82),
        ("General Account Mart",        "rising",   0.76),
        ("ALM Analytics",               "rising",   0.72),
        ("Spread Lending DB",           "decaying", 0.68),
        ("Recon & Controls",            "decaying", 0.62),
    ],
    # short code per product -> used to name its databases (CODE_CORE, CODE_MART…)
    "product_codes": {
        "Reference & Security Master": "REF",
        "Investments Data Warehouse":  "INVDW",
        "General Account Mart":        "GA",
        "ALM Analytics":               "ALM",
        "Spread Lending DB":           "SPRLEND",
        "Recon & Controls":            "RECON",
    },
    "db_suffixes": ["CORE", "MART", "STAGING", "ARCHIVE"],
    "schemas": ["PUBLIC", "CURATED", "RAW"],
    "table_nouns": [
        "POSITIONS", "SECURITY_MASTER", "CASHFLOWS", "FUNDING_AGREEMENTS",
        "FHLB_ADVANCES", "ALM_LADDER", "COUNTERPARTY", "RATINGS_HISTORY",
        "BOOK_VALUE", "ACCRUAL_SCHEDULE", "TRANSACTIONS", "HOLDINGS",
        "BENCHMARKS", "YIELD_CURVE", "SPREAD_MATRIX", "COLLATERAL",
        "EXPOSURES", "LIQUIDITY", "MATURITY_LADDER", "PRICING",
    ],
    "table_suffixes": ["_FACT", "_DIM", "_SNAPSHOT", "_DAILY", "_HIST", ""],
    "staging_suffixes": ["_STG", "_TMP", "_BKP"],
}


def recent_fridays(n: int, anchor: date | None = None) -> list[date]:
    """Return the n most recent Fridays (ascending) ending on/at `anchor`.

    If `anchor` isn't a Friday, snaps back to the latest Friday <= anchor.
    """
    anchor = anchor or SYNTHETIC["anchor_friday"] or date.today()
    # Monday=0 .. Sunday=6; Friday=4
    back = (anchor.weekday() - 4) % 7
    last_friday = anchor - timedelta(days=back)
    return [last_friday - timedelta(weeks=(n - 1 - i)) for i in range(n)]
