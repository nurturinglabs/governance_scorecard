## Data Governance Scorecard

A Streamlit-in-Snowflake app that replaces the manual weekly Excel pull of
per-table governance scores. It tracks the score **trend** over time across a
three-level hierarchy — data product → database → table — with drill-down and an
actionable per-table breakdown at the leaf.

One screen, parametrized by grain, drives all three levels. Local vs Snowflake is
a single config flag; nothing outside `data.py` knows which backend is live.

### Run locally (no Snowflake needed)

```bash
pip install -r requirements.txt
python -m synthetic.generate       # writes synthetic/governance_score_history.parquet
streamlit run app.py               # RUN_MODE defaults to "local"
```

Verify without a browser:

```bash
python smoke_test.py               # data layer + headless AppTest across all levels
```

### Deploy to Streamlit-in-Snowflake

1. Set `GOV_RUN_MODE=snowflake` (or edit `config.RUN_MODE`).
2. Confirm `config.SNOWFLAKE["history_table"]` and `config.COLUMNS` match the real
   table (see **Handoff** below).
3. Upload the app to a SiS stage / create the Streamlit object. The synthetic
   folder and `smoke_test.py` are dev-only and not required at runtime.

No other code changes. `data.py` loads the fact via `_snowflake.py`
(`get_active_session().sql(...)`); all rollups run in the same pandas code as
local, so the two modes cannot disagree.

### Structure

```
governance_scorecard/
  app.py                 entry: sidebar + nav state + render_level() (the one screen)
  config.py              single source of truth for every knob
  data.py                THE SEAM — one loader dispatched by RUN_MODE, shared rollups
  _snowflake.py          Snowflake fact loader (only Snowflake-aware module)
  theme.py               theming + score-color helpers (streamlit_kit optional)
  components/
    breadcrumb.py        clickable ancestors that re-scope the screen
    kpi_row.py           four metric cards with WoW deltas
    trend_chart.py       focus-entity score line + threshold rule
    heatmap.py           entity x week score heatmap (the "trend for every child" view)
    drill_list.py        sortable child list, sparklines, row-select to drill
    breakdown_card.py    leaf-only worst-table score decomposition
  synthetic/
    generate.py          deterministic dummy data generator (local mode)
  smoke_test.py          browser-free verification
  requirements.txt
  .streamlit/config.toml theme
```

### The knobs (all in `config.py`)

- `RUN_MODE` — `local` | `snowflake` (the only backend switch).
- `THRESHOLD` — pass/fail line; read everywhere (KPIs, pass_rate, below counts).
- `ROLLUP_METHOD` — `average` | `weighted` | `pass_rate`; changes what the trend
  line *means*. Overridable live from the sidebar.
- `SCORE_METRICS` — the independent weekly scores the fact tracks (metadata,
  role, activity, …) — there is no single composite. Each entry is `{key,
  label, column, components}`; add one and it appears in the top-of-page score
  selector automatically. `components` optionally names per-dimension points
  columns that explain the leaf breakdown card's worst-table decomposition —
  leave `None` until those columns are confirmed and the card degrades to the
  worst table's own trend.
- `SCORE_BANDS` — score→color; single source for heatmap, KPIs, breakdown bars.
- `SCOPE_EXCLUDE` — staging/temp/backup tables excluded from scoring so they don't
  drag a governed database down. Visible and configurable, never silent.
- `COLUMNS` — logical→physical column map; adapting to the real schema is an edit
  here, not a code change.

### Handoff — confirm before pointing at production

1. `config.SNOWFLAKE["history_table"]` — the real history table name.
2. `config.COLUMNS` — physical column names (grain assumed: one row per table per
   weekly `snapshot_date`).
3. `config.SCORE_METRICS` — the real score columns (metadata/role/activity/etc.)
   and their labels; the selector at the top of the page lists exactly these.
4. `ROLLUP_METHOD` — which rollup the governance team wants.
5. Whether per-dimension component columns exist for each metric's breakdown
   card; if not, leave that metric's `components` as `None`.

### Notes

- A skipped weekly snapshot renders as a gap in the heatmap, never a fabricated
  point.
- Sidebar overrides for threshold and rollup are passed as explicit arguments so
  Streamlit's cache invalidates correctly when you change them.
- The synthetic data is deterministic (seeded) and bakes in signal for a demo:
  rising and decaying products, unowned tables, a scope-excluded staging set, and
  a clear worst table for the breakdown card.
