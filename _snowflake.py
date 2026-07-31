"""
_snowflake.py — raw fact loader for RUN_MODE="snowflake".

The ONLY Snowflake-aware module. Loaded lazily by data.py so local runs never
import Snowpark. It selects the table-grain history, aliasing the real physical
columns (config.COLUMNS + COMPONENT_WEIGHTS) to the canonical names the rest of
the app uses, and pushes scope-exclusion into SQL. All rollups happen in pandas
in data.py, so local and Snowflake numbers are computed by identical code.

NOTE: validate the final SELECT against the real table once its name/columns are
confirmed (see [CONFIRM]s in config.SNOWFLAKE / config.COLUMNS).
"""

from __future__ import annotations

import pandas as pd

import config

C = config.COLUMNS


def _get_session():
    from snowflake.snowpark.context import get_active_session
    return get_active_session()


def _select_sql() -> str:
    src = config.SNOWFLAKE["history_table"]
    # canonical alias -> physical column
    pairs = [
        (C["data_product"], C["data_product"]),
        (C["database"], C["database"]),
        (C["schema"], C["schema"]),
        (C["table"], C["table"]),
        (C["table_fqn"], C["table_fqn"]),
        (C["snapshot_date"], C["snapshot_date"]),
        (C["owner"], C["owner"]),
        (C["weight"], C["weight"]),
    ]
    for m in config.SCORE_METRICS:
        pairs.append((m["column"], m["column"]))
        for comp in (m.get("components") or []):
            if comp.get("column"):
                pairs.append((comp["column"], comp["column"]))

    seen, select = set(), []
    for physical, alias in pairs:
        if alias in seen:
            continue
        seen.add(alias)
        select.append(f'{physical} AS "{alias}"' if physical != alias else physical)

    sql = f"SELECT {', '.join(select)} FROM {src}"
    if config.SCOPE_EXCLUDE["enabled"]:
        # RLIKE avoids LIKE's underscore-wildcard pitfall
        sql += f" WHERE NOT ({C['table']} RLIKE '{config.SCOPE_EXCLUDE['regex']}')"
    return sql


def load_fact() -> pd.DataFrame:
    """Return the table-grain history as a pandas DataFrame with canonical columns."""
    session = _get_session()
    df = session.sql(_select_sql()).to_pandas()
    df[C["snapshot_date"]] = pd.to_datetime(df[C["snapshot_date"]])
    return df
