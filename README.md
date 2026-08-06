## Data Governance Scorecard

A Streamlit-in-Snowflake app that replaces the manual weekly Excel pull of
per-table governance scores. It tracks several **independent weekly score
metrics** (metadata quality, role/ownership hygiene, activity, …) across a
two-level hierarchy — data product → table — with a full-width heatmap as the
primary view and a worst-table breakdown at the leaf.

Two pages, one score-metric selector at the top of every page that drives
everything below it (KPIs, trend, heatmap). Local / CSV / Snowflake is a
single config flag; nothing outside `data.py` knows which backend is live.

### Run locally (no Snowflake needed)

```bash
pip install -r requirements.txt
python -m synthetic.generate       # writes synthetic/*.parquet AND csv_data/*.csv
streamlit run app.py               # RUN_MODE defaults to "local"
```

Verify without a browser:

```bash
python smoke_test.py               # data layer (all metrics + csv mode) + headless AppTest
```

### Run against CSV exports (no Snowflake, no synthetic generator)

Point the app at two plain CSVs instead — one pre-aggregated at **product**
grain, one at **table** grain:

```
csv_data/products.csv   Date, Data_Product, <one column per score metric>
csv_data/tables.csv     Date, Data_Product, Schema, TABLE_NAME, <one column per score metric>
```

1. `export GOV_RUN_MODE=csv` (or edit `config.RUN_MODE`).
2. Point `config.CSV["products_file"]` / `["tables_file"]` at your files (defaults
   to `csv_data/products.csv` / `csv_data/tables.csv`).
3. Match your file's real headers in `config.CSV["products_columns"]` /
   `["tables_columns"]`, and each score's header in its
   `SCORE_METRICS[*]["csv_column"]`.
4. `streamlit run app.py`

`python -m synthetic.generate` writes demo copies of both files so csv mode
has something to point at immediately.

products.csv is treated as **authoritative**: the products page reads its
score straight from the file rather than re-deriving it by rolling up
tables.csv, so a business team's own product-level number is never
second-guessed by the app. Table counts (tables tracked, below-threshold
tables) still come from tables.csv either way, since products.csv doesn't
carry them. `ROLLUP_METHOD` still applies to the *portfolio* trend (which
averages the products) and to the tables page, but no longer recomputes a
product's own score.

Want to see more (or fewer) scores? Add or remove an entry in
`config.SCORE_METRICS` — the top-of-page selector only ever offers a metric
whose column is actually present in the loaded file, so a CSV can carry more
score columns than are currently configured (they're just ignored) or a
metric can be configured ahead of the CSV having it yet (it's hidden until it
does).

### Deploy to Streamlit-in-Snowflake

The shipped package (`dist/governance_scorecard_sis.zip`) currently deploys
**csv-backed** — `config.RUN_MODE` defaults to `"csv"` in that zip specifically
(not `"local"`, since there's no `synthetic/` folder in it) and it bundles
`csv_data/products.csv` + `csv_data/tables.csv` as an interim source. That's
so the app is live and usable in Snowsight *before* the real Snowflake table
exists — swap in real CSV exports by re-running the packaging steps below
with your own files in `csv_data/`, or cut over to Snowflake once the table's
ready (see the next section).

1. Upload the files listed below to a SiS stage / create the Streamlit object
   with `MAIN_FILE='app.py'`.
2. That's it for csv mode — the zip's `config.py` already defaults to `"csv"`.

#### Cutting over to Snowflake later

1. Set the `GOV_RUN_MODE=snowflake` environment variable on the Streamlit app
   (Snowsight app settings), or edit `config.RUN_MODE`'s default directly.
2. Confirm `config.SNOWFLAKE["history_table"]`, `config.COLUMNS`, and
   `config.SCORE_METRICS[*]["column"]` match the real table (see **Handoff**
   below).

No other code changes either way. `data.py` loads the fact via
`_snowflake.py` (`get_active_session().sql(...)`) or the CSV loader; all
rollups run in the same pandas code regardless of mode, so they cannot
disagree.

#### Files required for the SiS package

Everything the app imports at runtime, and nothing else — a ready-made zip
of exactly this set is at `dist/governance_scorecard_sis.zip` (rebuild it by
zipping this list after any code change; see the note below).

```
app.py                        entry point — set as the object's MAIN_FILE
config.py                     RUN_MODE defaults to "csv" in this package (see above)
data.py
_snowflake.py
theme.py
components/__init__.py
components/breakdown_card.py
components/heatmap.py
components/kpi_row.py
components/trend_chart.py
environment.yml               conda deps (pandas/numpy/pyarrow/altair) — SiS
                              already provides streamlit + snowflake-snowpark-python
.streamlit/config.toml        theme — app runs without it but loses the navy/gold styling
csv_data/products.csv         current data source — replace with your own export any time
csv_data/tables.csv           current data source — replace with your own export any time
```

**Not required at runtime** — leave these out of the SiS package:

- `synthetic/` — local-mode demo data generator, not read in csv or snowflake mode
- `csv_data/` — drop this once you cut over to `RUN_MODE="snowflake"`
- `smoke_test.py` — dev-only verification
- `requirements.txt` — pip; SiS resolves packages from `environment.yml` (conda) instead
- `README.md`, `dist/`, `.gitignore`, `.git/` — repo/doc scaffolding, not imported by the app

If you add a new file that `app.py`/`data.py`/`components/*` import, it
belongs in the "required" list above and in the zip; if you only add
something under `synthetic/`, `csv_data/`, or a new dev script, it does not.

### Structure

```
governance_scorecard/
  app.py                 entry: sidebar + score-metric selector + the two pages
  config.py              single source of truth for every knob
  data.py                THE SEAM — backend loaders dispatched by RUN_MODE, shared rollups
  _snowflake.py           Snowflake fact loader (only Snowflake-aware module)
  theme.py                design tokens + global CSS + score-color/sparkline helpers
  components/
    kpi_row.py            four metric cards with WoW deltas + score sparkline
    heatmap.py             the hero view — entity x week grid, clickable rows on page 1
    breakdown_card.py      leaf-only worst-table score decomposition ("Biggest drag")
    trend_chart.py          Altair fallback chart (breakdown card only, when a metric
                            has no configured components)
  synthetic/
    generate.py            deterministic dummy data generator — writes parquet AND
                           the demo csv_data/*.csv exports
  csv_data/                RUN_MODE="csv" source files (gitignored, regenerable)
  smoke_test.py            browser-free verification (all metrics + csv mode + AppTest)
  requirements.txt
  environment.yml          conda deps for Streamlit-in-Snowflake (RUN_MODE="snowflake")
  .streamlit/config.toml   theme
```

### The knobs (all in `config.py`)

- `RUN_MODE` — `local` | `csv` | `snowflake` (the only backend switch).
- `THRESHOLD` — pass/fail line; read everywhere (KPIs, pass_rate, below counts).
- `ROLLUP_METHOD` — `average` | `weighted` | `pass_rate`; changes what the trend
  line *means*. Overridable live from the sidebar.
- `SCORE_METRICS` — the independent weekly scores the fact tracks. Each entry is
  `{key, label, column, csv_column, components}`; add one and it appears in the
  top-of-page score selector automatically (once its column exists in the
  loaded data — see `data.available_metrics()`). `components` optionally names
  per-dimension points columns that explain the leaf breakdown card's
  worst-table decomposition — leave `None` until those columns are confirmed
  and the card degrades to the worst table's own trend.
- `CSV` — file paths + header maps for `RUN_MODE="csv"` (see above).
- `SCORE_BANDS` — score→color; single source for heatmap, KPIs, breakdown bars.
- `SCOPE_EXCLUDE` — staging/temp/backup tables excluded from scoring so they don't
  drag a product down. Visible and configurable, never silent.
- `COLUMNS` — logical→physical column map for local/snowflake mode; adapting to
  the real schema is an edit here, not a code change.

### Handoff — confirm before pointing at production

1. `config.SNOWFLAKE["history_table"]` — the real history table name.
2. `config.COLUMNS` — physical column names (grain assumed: one row per table per
   weekly `snapshot_date`).
3. `config.SCORE_METRICS` — the real score columns (metadata/role/activity/etc.),
   their labels, and (for csv mode) their `csv_column` headers.
4. `ROLLUP_METHOD` — which rollup the governance team wants.
5. Whether per-dimension component columns exist for each metric's breakdown
   card; if not, leave that metric's `components` as `None`.

### Notes

- A skipped weekly snapshot renders as a gap in the heatmap, never a fabricated
  point — this holds for csv mode too: a (product, week) missing from
  products.csv is an honest gap, not silently filled by a rollup guess.
- Sidebar overrides for threshold and rollup, and the top-of-page score-metric
  selector, are passed as explicit arguments so Streamlit's cache invalidates
  correctly when you change them.
- Owner/assignee is not tracked or displayed anywhere in the app.
- The synthetic data is deterministic (seeded) and bakes in signal for a demo:
  rising and decaying products, a scope-excluded staging set, and a clear
  worst table per metric for the breakdown card.
