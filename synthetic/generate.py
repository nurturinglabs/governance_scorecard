"""
synthetic/generate.py — deterministic synthetic score history.

Emits one parquet at config.FACT_PARQUET with the SAME columns the real
Snowflake history table is expected to have, at the SAME grain:
    one row per table per weekly snapshot_date.

Local mode reads this through the exact data.py API used against Snowflake, so
the whole app is demoable end to end with zero credentials.

The fact tracks several INDEPENDENT weekly scores per table (config.SCORE_METRICS:
metadata / role / activity, each 0-100) — there is no single composite score.
Each metric drifts on its own noise stream so they don't move in lockstep, while
still following the product's overall trajectory (rising/stable/decaying).

Baked-in signal (so the app has stories to show):
  * products that visibly rise or decay week over week, on every metric
  * a spread of below-threshold tables per metric
  * tables with MISSING owners (drags role_score down specifically)
  * staging tables (…_STG/_TMP/_BKP) that SCOPE_EXCLUDE should catch

Run from the project root:
    python -m synthetic.generate
or:
    python synthetic/generate.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running as a bare script (python synthetic/generate.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

S = config.SYNTHETIC
METRICS = config.SCORE_METRICS  # [{"key","label","column","components"}, ...]


def _rng_for(*parts: str) -> np.random.Generator:
    """Stable independent RNG stream keyed by name parts + global seed.

    Hashing names (rather than positional counters) means adding an entity
    doesn't reshuffle everyone else's numbers.
    """
    key = "|".join(parts).encode()
    h = int(hashlib.sha256(key).hexdigest()[:12], 16)
    return np.random.default_rng((h ^ S["seed"]) & 0xFFFFFFFF)


def _clamp01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _trajectory_drift(kind: str, p: float) -> float:
    """Signed drift added to a metric's attainment at progress p in [0,1]."""
    if kind == "rising":
        return 0.13 * p
    if kind == "decaying":
        return -0.10 * p
    return 0.0  # stable


def build_entities() -> list[dict]:
    """Build the product -> database -> table tree with per-table profiles."""
    entities: list[dict] = []

    for product, trajectory, baseline in S["products"]:
        code = S["product_codes"][product]

        for suffix in S["db_suffixes"][: S["databases_per_product"]]:
            db_name = f"{code}_{suffix}"
            is_staging_db = suffix == "STAGING"
            db_rng = _rng_for("db", db_name)
            n_tables = int(db_rng.integers(S["tables_per_database"][0],
                                           S["tables_per_database"][1] + 1))

            used_names: set[str] = set()
            for _ in range(n_tables):
                trng = db_rng  # draw table shape from the db stream for stability
                noun = S["table_nouns"][int(trng.integers(0, len(S["table_nouns"])))]
                suf = S["table_suffixes"][int(trng.integers(0, len(S["table_suffixes"])))]
                name = f"{noun}{suf}"

                # Staging leftovers. STAGING databases are mostly (~60%) staging
                # but keep some governed tables so they never fully exclude;
                # curated DBs occasionally harbour a stray _STG — the real-world
                # case where it quietly drags a governed database's score down.
                staging_prob = 0.60 if is_staging_db else 0.05
                make_staging = trng.random() < staging_prob
                if make_staging:
                    st = S["staging_suffixes"][int(trng.integers(0, len(S["staging_suffixes"])))]
                    name = f"{noun}{st}"

                # de-dup within a database
                base = name
                k = 2
                while name in used_names:
                    name = f"{base}_{k}"
                    k += 1
                used_names.add(name)
                is_staging = any(name.endswith(x) for x in S["staging_suffixes"])

                schema = S["schemas"][int(trng.integers(0, len(S["schemas"])))]
                fqn = f"{db_name}.{schema}.{name}"
                prng = _rng_for("tbl", fqn)
                jitter = lambda spread=0.12: float(prng.normal(0, spread))  # noqa: E731

                # Ownership: binary. Staging tables usually unowned; otherwise
                # ownership probability tracks the product baseline.
                if is_staging:
                    has_owner = prng.random() < 0.15
                else:
                    has_owner = prng.random() < (0.55 + 0.4 * baseline)
                owner = (S["owner_pool"][int(prng.integers(0, len(S["owner_pool"])))]
                         if has_owner else None)

                # Per-metric baselines (attainment 0..1), independent of each
                # other so metadata/role/activity tell different stories on
                # the same table. All still centre on the product's baseline
                # maturity, with per-table jitter.
                if is_staging:
                    a_metadata0 = _clamp01(0.15 + jitter(0.07))
                    a_role0 = _clamp01(0.10 + jitter(0.06))
                    a_act0 = _clamp01(0.82 + jitter(0.10))
                else:
                    a_metadata0 = _clamp01(baseline + jitter())
                    a_role0 = _clamp01((0.78 if has_owner else 0.30) + 0.15 * baseline + jitter(0.08))
                    a_act0 = _clamp01(0.70 + 0.2 * baseline + jitter(0.10))

                # weight = table size (row count), lognormal-ish, for weighted rollup
                weight = int(10 ** float(prng.uniform(3.0, 6.8)))

                entities.append({
                    "data_product": product,
                    "database_name": db_name,
                    "schema_name": schema,
                    "table_name": name,
                    "table_fqn": fqn,
                    "owner": owner,
                    "weight": weight,
                    "trajectory": trajectory,
                    "is_staging": is_staging,
                    "a_metadata0": a_metadata0,
                    "a_role0": a_role0,
                    "a_act0": a_act0,
                })

    return entities


def build_history(entities: list[dict]) -> pd.DataFrame:
    fridays = config.recent_fridays(S["weeks"])
    n = len(fridays)

    rows: list[dict] = []
    for e in entities:
        for i, snap in enumerate(fridays):
            p = i / (n - 1) if n > 1 else 1.0
            drift = _trajectory_drift(e["trajectory"], p)

            row = {
                "data_product": e["data_product"],
                "database_name": e["database_name"],
                "schema_name": e["schema_name"],
                "table_name": e["table_name"],
                "table_fqn": e["table_fqn"],
                "snapshot_date": snap,
                "owner": e["owner"],
                "weight": e["weight"],
            }
            for m in METRICS:
                srng = _rng_for("series", m["key"], e["table_fqn"])
                baseline0 = e[f"a_{m['key']}0"]
                attainment = _clamp01(baseline0 + drift + float(srng.normal(0, 0.018)))
                row[m["column"]] = int(round(attainment * 100))
            rows.append(row)

    df = pd.DataFrame(rows)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df


def inject_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """Drop a few (table, week) rows so the heatmap must render honest gaps
    rather than fabricated points. Deterministic."""
    if not S["inject_gaps"]:
        return df
    grng = _rng_for("gaps")
    fqns = df["table_fqn"].unique()
    victims = grng.choice(fqns, size=min(3, len(fqns)), replace=False)
    dates = sorted(df["snapshot_date"].unique())
    drop_idx = pd.Index([], dtype="int64")
    for fqn in victims:
        # skip one mid-series week and (for one table) the latest week
        weeks_to_drop = [dates[len(dates) // 2]]
        if fqn == victims[0]:
            weeks_to_drop.append(dates[-1])
        mask = (df["table_fqn"] == fqn) & (df["snapshot_date"].isin(weeks_to_drop))
        drop_idx = drop_idx.union(df.index[mask])
    return df.drop(index=drop_idx).reset_index(drop=True)


def summarize(df: pd.DataFrame) -> None:
    latest = df["snapshot_date"].max()
    cur = df[df["snapshot_date"] == latest]
    scored = cur[~cur["table_name"].map(config.is_excluded)]
    print(f"\nrows: {len(df):,}   tables: {df['table_fqn'].nunique():,}   "
          f"weeks: {df['snapshot_date'].nunique()}   "
          f"products: {df['data_product'].nunique()}   "
          f"databases: {df['database_name'].nunique()}")
    print(f"excluded (scope): {cur['table_name'].map(config.is_excluded).sum()} "
          f"of {len(cur)} tables at latest snapshot")
    print(f"unowned tables (scored): {scored['owner'].isna().sum()}")

    for m in METRICS:
        col = m["column"]
        print(f"\n{m['label']} (threshold {config.THRESHOLD}):")
        print(f"  below threshold (scored): {(scored[col] < config.THRESHOLD).sum()} of {len(scored)}")
        prod = (scored.groupby("data_product")[col]
                .mean().round(1).sort_values(ascending=False))
        for name, val in prod.items():
            print(f"    {val:5.1f}  {name}")
        worst = scored.sort_values(col).iloc[0]
        print(f"  worst table: {worst['table_fqn']}  {col}={worst[col]}  owner={worst['owner']}")


def main() -> None:
    config.SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    entities = build_entities()
    df = build_history(entities)
    df = inject_gaps(df)
    # deterministic ordering
    df = df.sort_values(["data_product", "database_name", "table_name",
                         "snapshot_date"]).reset_index(drop=True)
    df.to_parquet(config.FACT_PARQUET, index=False)
    print(f"wrote {config.FACT_PARQUET}")
    summarize(df)


if __name__ == "__main__":
    main()
