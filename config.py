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
# Run mode — the ONLY switch that flips local <-> Snowflake. No other change.
# --------------------------------------------------------------------------- #
# "local"     -> data.py reads synthetic/*.parquet
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
    "score": "governance_score",       # the composite 0-100
    "owner": "owner",
    "weight": "weight",                # row count / criticality (weighted rollup)
    # Optional per-dimension component columns (feed the breakdown card).
    # If these do NOT exist in the real table, set the ones that are missing to
    # None; data.py degrades the breakdown card gracefully (see COMPONENT_WEIGHTS).
    "pct_docs": "pct_columns_documented",
    "freshness_status": "freshness_status",
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
    {"min": 85, "color": "#639922", "text": "#173404", "label": "Strong"},
    {"min": 75, "color": "#97C459", "text": "#173404", "label": "Healthy"},
    {"min": 65, "color": "#EF9F27", "text": "#4A1B0C", "label": "At risk"},
    {"min": 0,  "color": "#E24B4A", "text": "#4A1B0C", "label": "Failing"},
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
# Governance dimensions -> max points. Feeds the leaf-level breakdown card.
# Points across dimensions must sum to 100 so the composite score is explainable
# as ownership + descriptions + freshness + classification + quality.
#
# `column` maps each dimension to its per-dimension points column. If the real
# table has no component columns, set every `column` to None: data.py then hides
# the per-dimension bars and the breakdown card falls back to the worst table's
# trend + raw score. Do NOT invent columns that don't exist.
# --------------------------------------------------------------------------- #
COMPONENT_WEIGHTS = [
    {"key": "ownership",      "label": "Ownership",       "max": 20, "column": "ownership_pts",      "icon": "user"},
    {"key": "descriptions",   "label": "Descriptions",    "max": 25, "column": "description_pts",    "icon": "file-text"},
    {"key": "freshness",      "label": "Freshness / SLA", "max": 20, "column": "freshness_pts",      "icon": "clock"},
    {"key": "classification", "label": "Classification",  "max": 15, "column": "classification_pts", "icon": "shield"},
    {"key": "quality",        "label": "Quality tests",   "max": 20, "column": "quality_pts",        "icon": "check"},
]
assert sum(c["max"] for c in COMPONENT_WEIGHTS) == 100, "component maxes must sum to 100"

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
    "owner_pool": ["k.burie", "i.botvinnik", "a.schulz", "m.nguyen", "r.patel"],
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
