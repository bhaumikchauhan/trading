# Chart Pattern Recognition — Technical Specification

_Living document — updated as architecture decisions are made or revised. Companion
to [functional-spec.md](functional-spec.md), which tracks task status; this document
tracks the *how*._

## 1. Scope & Assumptions

| Area | Decision | Notes |
|---|---|---|
| Initial market/timeframe | Equities, daily bars | Architecture should not hard-code this, but it's the design/tuning target for v1 |
| Historical OHLCV source | `candle_db.py` (existing SQLite read/write layer, provided) | Schema and API documented in §5; we wrap it, we don't replace it |
| App-owned persistence | SQLite (candidates, backtest results, labels) + Parquet (large/derived data caches) | See §5.5 |
| Language | Python | |
| Python version | 3.11+ | Default choice for modern typing features + performance; `candle_db.py` has no version pins observed so this is not constrained by it |
| Env/dependency manager | uv | pyproject.toml + uv.lock |
| Config format | YAML, validated via Pydantic models | All smoothing/pattern tolerances live here, not hard-coded |
| Scale target | ~10k LOC mid-size application | Drives the project-structure and testing decisions below (src-layout, module boundaries, pytest, typed interfaces) |

Items marked "default" below are reasonable choices made to keep momentum; flag any
you want changed and this document will be updated.

## 2. Technology Stack

| Concern | Library | Why |
|---|---|---|
| Data handling | pandas, numpy | Standard vectorized OHLCV manipulation |
| Extrema/signal processing | scipy (`signal.argrelextrema`, `signal.savgol_filter`) | Pivot detection, Savitzky-Golay smoothing |
| Kernel regression smoothing | statsmodels (optional, deferred) | Only needed for the lower-priority kernel-regression smoother (functional-spec 3.3) |
| Config validation & domain models | pydantic v2 | Validates YAML config at load time; also used for Pivot/Candidate/BacktestResult data models |
| Config files | PyYAML | Human-editable tolerance/threshold files |
| CLI | typer | Thin CLI over the pipeline (`run`, `backtest`, `plot` commands) |
| App-owned relational storage | sqlite3 (stdlib) or SQLAlchemy core | Candidates, backtest runs, labeled dataset — separate DB file from the user's OHLCV DB |
| Columnar cache | pyarrow (Parquet) | Derived/large intermediate data (e.g. exported candidate sets, smoothed-series caches) |
| Charting/QA visualization | matplotlib + mplfinance | Candlestick rendering with pivot/pattern overlays for manual verification |
| Testing | pytest, pytest-cov | Unit + integration tests, coverage reporting |
| Lint/format | ruff | Single tool replacing flake8/isort/black |
| Type checking | mypy (recommended, not blocking) | Useful given ~10k LOC target and heavy use of interfaces |
| ML phase (future, extra dependency group) | scikit-learn, xgboost or lightgbm | Only installed when ML phase (functional-spec §11) begins |

No deep-learning/CNN dependencies are included now — that path (functional-spec
11.6) is a stretch goal and would be scoped separately if pursued.

## 3. Project Structure

```
chart_patterns/
├── pyproject.toml
├── uv.lock
├── README.md
├── docs/
│   ├── functional-spec.md
│   └── technical-spec.md
├── configs/
│   ├── smoothing.yaml
│   ├── logging.yaml
│   └── patterns/
│       ├── double_top.yaml
│       ├── double_bottom.yaml
│       ├── head_and_shoulders.yaml
│       ├── inverse_head_and_shoulders.yaml
│       └── cup_and_handle.yaml
├── src/
│   └── chart_patterns/
│       ├── __init__.py
│       ├── config/              # YAML loading + Pydantic validation
│       ├── data/                 # DataSource interface + adapters, OHLCV model
│       ├── smoothing/            # Smoother interface: zigzag, savgol, kernel_regression
│       ├── pivots/               # Extrema detection, Pivot model
│       ├── patterns/             # PatternMatcher interface, registry, one module per pattern
│       ├── scoring/              # Confidence scoring, ranking, dedup
│       ├── backtest/             # Evaluation harness, precision/recall/F-beta metrics
│       ├── alerts/                # Candidate -> alert model, output sinks
│       ├── viz/                   # Chart rendering for QA
│       ├── ml/                    # Phase 2 (feature engineering, training, inference)
│       ├── cli/                   # Typer app entrypoint
│       └── logging_config.py
├── tests/
│   ├── unit/                     # Per-module tests, synthetic pivot sequences for pattern rules
│   ├── integration/              # Full pipeline over fixture data
│   └── fixtures/
└── notebooks/                     # Exploratory analysis, not shipped code
```

`src/` layout (rather than a flat package at repo root) is used so tests always
import the installed package, not accidentally the working directory — standard
practice at this project size.

`candle_db.py` currently lives at the repo root (with `data/candles.db` etc.).
When `src/` is scaffolded, it should move to
`src/chart_patterns/data/candle_db.py` and `data/` stays at the repo root as the
actual database location (referenced via `DEFAULT_DB_PATH`, adjusted for the new
relative position) — a mechanical move, no logic changes expected.

## 4. Environment & Tooling

- `uv init` / `uv add <pkg>` manage dependencies; `uv.lock` is committed for
  reproducibility.
- Dependency groups in `pyproject.toml`: default (runtime), `dev` (pytest, ruff,
  mypy), `ml` (scikit-learn, xgboost/lightgbm — not installed until Phase 2 starts).
- `ruff check` + `ruff format` run via CI once CI is set up (functional-spec 1.7).
- Git is not yet initialized in this directory (confirm before `git init`).

## 5. Data Architecture

### 5.1 Source Database: `candle_db.py`

Historical OHLCV data is already implemented in [`candle_db.py`](../candle_db.py)
at the repo root, backed by SQLite. This is the source of truth for OHLCV and is
used as-is — the pipeline wraps it rather than reimplementing data access.

**Schema — `candles` table (`data/candles.db`, ~3.19M rows / 2,591 symbols in the
current data file, daily bars spanning 2020-01-01 to 2026-08-19):**

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| symbol | TEXT NOT NULL | e.g. `"ANIKINDS-BE"` (NSE-style symbol) |
| timestamp | TEXT NOT NULL | ISO 8601, bar timestamp (currently always midnight — daily bars) |
| date | TEXT NOT NULL | ISO date, derived from `timestamp`; used for date-range filtering |
| open, high, low, close | REAL | |
| volume | REAL | |
| extra | TEXT (JSON) | Arbitrary extra fields not in the core OHLCV set — observed to carry `oi` (open interest) in the current data. Any DataFrame column beyond `CORE_COLUMNS` gets folded in here automatically on insert |

Constraints/indexes: `UNIQUE(symbol, timestamp)` (upsert key), plus indexes on
`(symbol, timestamp)`, `date`, and `symbol` — so both per-symbol history queries
and cross-symbol date-slice queries are index-backed.

**Note:** the schema has no `timeframe` column — one physical table holds bars of
whatever granularity was inserted (daily, in the current data). Multi-timeframe
support (functional-spec 2.5) will be handled by resampling daily bars in pandas
after read, not by the DB, unless/until intraday data is loaded into a separate
table or file.

**Existing API surface (all in `candle_db.py`):**

| Function | Purpose |
|---|---|
| `initialize_database(db_path=None, memory=False)` | Creates table/indexes if missing |
| `insert_candle_df(df, symbol, db_path=None, memory=False)` | Upsert (`INSERT OR REPLACE`) from a DataFrame; auto-splits core OHLCV columns vs. `extra` JSON |
| `get_history(symbol, start=None, end=None, db_path=None, memory=False)` | Primary read path — per-symbol, optionally date-bounded, ordered by timestamp. **This is what the pipeline's data-loading stage calls.** |
| `get_date_data(date, ...)` | All symbols for one date (cross-sectional) |
| `get_symbols_for_date(date, ...)` | Symbol list available on a given date |
| `get_all_data(db_path=None, parse_dates=True, memory=False)` | Full-table read — expensive at 3M+ rows, for exports/analysis only, not per-run pipeline use |
| `export_history_to_csv(...)`, `export_symbol_counts(...)` | Analysis/export utilities |

**In-memory acceleration mode:** every read/write function accepts `memory=True`.
When set, it opens a SQLite shared-cache in-memory database (URI
`file:mem_<md5(db_path)>?mode=memory&cache=shared`), seeded once per process via
`sqlite3.Connection.backup()` from the on-disk file, and reused across
thread-local connections keyed by the resolved path (`_MEMORY_INITIALIZED`,
`_THREAD_LOCAL`). This avoids repeated disk I/O for read-heavy workloads.
**Recommendation:** the backtest harness (functional-spec §8), which re-reads the
same historical range across many symbols/patterns/tolerance-tuning iterations,
should run with `memory=True`; a single live/CLI `run` over one symbol can use
the default disk mode.

`candle_db.py` logs via `from custom_logger import logger`
([`custom_logger.py`](../custom_logger.py), provided) — a module-level singleton
`logging.Logger` named `"strategy_output"`, writing to console and to a
timestamped file under `output/` (`output/strategy_output_<YYYYmmdd_HHMMSS>.log`),
created fresh on import. See §11 for how the rest of the app adopts this same
logger rather than running a second logging setup in parallel.

### 5.2 OHLCV Model

A single canonical in-memory representation is used from the pipeline's
data-loading stage onward:

| Field | Type | Notes |
|---|---|---|
| symbol | str | |
| timestamp | datetime | Parsed from `candles.timestamp` |
| open, high, low, close | float | |
| volume | float | |

Series of bars are represented as a `pandas.DataFrame` (indexed by timestamp),
matching what `get_history()` already returns — this is what smoothing/pivot
code (scipy, rolling windows) operates on efficiently. The `id`, `date`, and
`extra` columns from the raw table are dropped/ignored at this boundary unless a
specific pattern or feature explicitly needs `extra` (e.g. `oi` as a future
ML/volume-pattern feature).

### 5.3 DataSource Interface

Downstream pipeline stages (smoothing, pivots, pattern matching) depend on a
small protocol, not directly on `candle_db.py`, so the data source can be swapped
(a different symbol universe, a future intraday table, tests) without touching
pipeline code:

```python
class OHLCVSource(Protocol):
    def get_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame: ...
```

- `CandleDBSource` — the real adapter; a thin wrapper calling
  `candle_db.get_history(symbol, start, end, memory=...)` and normalizing the
  result to the canonical OHLCV model (§5.2).
- `CSVOHLCVSource` — for unit/integration test fixtures that shouldn't depend on
  the real database.

### 5.4 Data Validation

`candle_db.py` already normalizes/coerces values on write (`_normalize_core_value`,
`_normalize_timestamp`) but does not validate for gaps, duplicate dates, or
non-monotonic sequences on read. The pipeline's ingestion layer (functional-spec
2.4) adds that check *after* `get_history()`, since it's a concern specific to
what pattern detection needs (a clean, gap-flagged daily series), not a general
property of the stored data.

### 5.5 App-Owned Persistence

Two separate concerns, deliberately not mixed into `candle_db.py`'s `candles.db`:

| Data | Store | Why |
|---|---|---|
| Candidates found per run, backtest run results, labeled dataset annotations | New SQLite DB (e.g. `data/chart_patterns_app.db`) | Structured, queryable across runs, small enough for SQLite; kept as a separate file/module from `candle_db.py` so OHLCV storage and app-output storage evolve independently |
| Large/derived intermediate data (e.g. cached smoothed series, exported candidate sets for offline notebooks) | Parquet files under `data/cache/` | Columnar, fast for pandas round-trips, easy to version/discard |

This app-owned SQLite database is new code (not yet built); it does not reuse
`candle_db.py`'s schema, only (optionally) similar connection-handling
conventions for consistency.

## 6. Configuration System

All tunable thresholds live in YAML, loaded and validated through Pydantic models
at startup — never hard-coded in pattern logic. Example:

```yaml
# configs/patterns/double_top.yaml
double_top:
  height_similarity_pct: 3.0      # max % difference allowed between the two peaks
  min_trough_depth_pct: 2.0       # trough must retrace at least this % from peak
  max_time_separation_bars: 120   # widen for recall; tightened later only via data
  min_time_separation_bars: 5
```

```yaml
# configs/smoothing.yaml
zigzag:
  threshold_pct: 3.0
savgol:
  window_length: 11
  polyorder: 2
```

Each pattern config maps to a corresponding Pydantic model (e.g.
`DoubleTopConfig`) so invalid YAML fails fast at load time rather than producing
silent bad matches. Per functional-spec's recall-first principle, tolerance
tuning during backtesting (§7) means editing these YAML files, not code.

## 7. Core Domain Models

| Model | Key fields | Purpose |
|---|---|---|
| `Pivot` | index, timestamp, price, type (`peak`/`trough`) | Output of pivot detection; input to all pattern matchers |
| `Candidate` | pattern_type, pivots, symbol, timeframe, start/end timestamp, confidence_score, metrics (dict) | Output of a pattern matcher; input to scoring/ranking and alerts |
| `BacktestResult` | pattern_type, precision, recall, f_beta, run metadata | Output of the evaluation harness (§ functional-spec 8) |
| `LabeledExample` | symbol, timeframe, pattern_type, pivot span, is_true_positive | Hand-labeled ground truth used to tune tolerances |

## 8. Pipeline Architecture

```
OHLCVSource.get_bars()
        │
        ▼
  Smoother (zigzag/savgol/kernel) ──▶ smoothed series
        │
        ▼
  Pivot detector ──▶ List[Pivot]
        │
        ▼
  PatternMatcher registry (one matcher per pattern type, sliding window over pivots)
        │
        ▼
  List[Candidate] (each with a confidence_score)
        │
        ▼
  Scoring/ranking + dedup ──▶ ranked candidates
        │
        ▼
  Alerts (console/file sink) ── + optional ML re-ranking later
```

Each stage is a pure function/class over the previous stage's output — no stage
reaches back into an earlier one's internals. This is what makes the ML scorer
(functional-spec §11) a drop-in addition later: it only ever consumes `Candidate`
objects, it doesn't change how candidates are produced.

## 9. Pattern Matcher Framework

```python
class PatternMatcher(Protocol):
    pattern_type: str
    def find_candidates(self, pivots: list[Pivot], config: PatternConfig) -> list[Candidate]: ...
```

- A registry (`@register_pattern("double_top")`) lets new pattern modules plug in
  without editing the core pipeline loop — satisfies functional-spec 5.4.
- Each matcher only depends on `list[Pivot]` and its own YAML-backed config
  object — no cross-pattern coupling, no direct DataFrame access (keeps unit
  tests fast: synthetic pivot lists, no need to fabricate OHLCV data per test).

## 10. Testing Strategy

| Level | Approach |
|---|---|
| Pattern rule unit tests | Hand-built synthetic `Pivot` lists (clear positive, clear negative, boundary cases) — no smoothing/data layer involved |
| Smoothing/pivot unit tests | Small synthetic price series with known expected pivots |
| Integration tests | Small CSV fixture through the full pipeline (source → smoothing → pivots → patterns → candidates) |
| Backtest regression | Labeled dataset (functional-spec 8.1) re-run in CI-equivalent fashion to catch recall regressions |
| Coverage target | Meaningful coverage on `patterns/`, `smoothing/`, `pivots/` (core logic); lower priority on `viz/`, `cli/` |

## 11. Logging & CLI

- Reuse the existing `custom_logger.logger` singleton everywhere (`candle_db.py`
  already depends on it) instead of introducing a second, parallel logging setup
  — all pipeline modules do `from custom_logger import logger`, no per-module
  `getLogger(__name__)`. This keeps one console+file sink for the whole app, at
  the cost of not being able to set per-module log levels independently — an
  acceptable tradeoff at this project size, and revisitable if it becomes a
  problem.
- `configs/logging.yaml` (from §6/§3) is scaled back to just the one knob this
  logger actually exposes: level (`configure_logger(level=...)`). No
  `dictConfig` layer is being added on top of it.
- Two pre-existing details worth deciding on before wider use, not architectural
  blockers: (1) the startup line `"🔁 OpenAlgo Python Bot is running."` in
  `custom_logger.py` is leftover from the source project this file was adapted
  from and should be updated/removed so app logs don't reference an unrelated
  bot; (2) a new timestamped log file is created in `output/` on every process
  start — fine for a long-running strategy runner, but the CLI's `run`/`plot`
  commands will be invoked often during development, so `output/` will
  accumulate many small log files unless a retention/cleanup convention is
  added later.
- `typer` CLI exposes: `run` (execute pipeline for a symbol/date range, print or
  save ranked candidates), `backtest` (run the evaluation harness), `plot`
  (render a chart with pivots/candidate overlays for manual QA).

## 12. Backtesting & Metrics

- Recall-weighted evaluation: track precision, recall, and an F-beta score with
  beta > 1 (recall weighted higher), per pattern type, against the labeled
  dataset — mirrors the functional-spec's recall-first mandate.
- Tolerance tuning is a loop: run backtest → inspect missed true positives →
  widen the relevant YAML tolerance → re-run — never a one-shot hand-tuning.

## 13. Visualization

- `mplfinance` for candlestick rendering with pivot markers and pattern-span
  overlays (e.g. shaded region + labeled shoulders/neckline for H&S). Used
  throughout development for manual verification, not just as a final feature.

## 14. ML Phase (Future, Not Built Now)

- Feature vectors derived purely from existing `Candidate.metrics` plus added
  volume-based features — no new data pipeline required.
- `scikit-learn` for baseline models/evaluation utilities; `xgboost` or
  `lightgbm` for the gradient-boosted classifier itself.
- Sits strictly after scoring/ranking in the pipeline (§8) as a re-ranker/filter,
  consistent with functional-spec 11.4 — it never gets to suppress a candidate
  the rule layer didn't already surface.

## 15. Non-Functional Notes

- Favor vectorized pandas/numpy operations in the smoothing and pivot-detection
  stages; avoid per-bar Python loops where a vectorized equivalent exists, given
  backtests will run over long daily histories.
- Type hints throughout `src/chart_patterns/`; Pydantic models double as runtime
  validation at data/config boundaries and as documentation of shapes passed
  between pipeline stages.

## 16. Open Decisions / To Confirm Later

| Item | Default taken | Revisit when |
|---|---|---|
| Python version | 3.11+ | No constraint observed from `candle_db.py` |
| SQLite access in-app (raw sqlite3 vs SQLAlchemy) | Raw `sqlite3`, matching `candle_db.py`'s style | If the app-owned DB (§5.5) grows complex enough to want an ORM/query builder |
| `custom_logger.py` leftover startup message/emoji ("OpenAlgo Python Bot is running") | Left as-is for now | Before this app is used beyond development — cosmetic, but misleading in shared logs |
| Log file accumulation in `output/` (one timestamped file per process start) | No retention policy yet | If `output/` grows unmanageably during frequent CLI use in development |
| Multi-timeframe data | Not in current schema (one row grain per DB) | If intraday data is added later; likely a separate table/file rather than a schema change to `candles` |
| CI provider | Not set up | functional-spec 1.7 |
| mplfinance vs plain matplotlib | mplfinance (candlestick-native) | If it proves awkward for overlay annotations, fall back to matplotlib |

## Change Log

| Date | Change |
|---|---|
| 2026-09-11 | Initial technical specification created. |
| 2026-09-11 | Documented actual `candle_db.py` SQLite schema, API, and in-memory acceleration mode (§5); resolved SQLite access-style decision; flagged missing `custom_logger` dependency. |
| 2026-09-11 | `custom_logger.py` provided — logging plan (§11) updated to reuse its singleton logger instead of a new `dictConfig`/YAML-driven setup; flagged its leftover bot-branding message and per-run log file accumulation as minor cleanup items. |
| 2026-09-11 | Config loader implemented per §6: `src/chart_patterns/config/models.py` (Pydantic models `ZigZagConfig`, `SavgolConfig`, `SmoothingConfig`, `LoggingConfig`, `DoubleTopConfig`, each with cross-field validation — e.g. Savitzky-Golay window must be odd and exceed `polyorder`, a pattern's min/max time-separation bounds must be ordered) and `loader.py` (`load_smoothing_config`, `load_logging_config`, `load_pattern_config`). Patterns are looked up via a small `{name: model}` registry dict in `loader.py`, seeded with just `double_top` for now — the same shape the pattern-matcher registry (§9) will use once matchers exist, so both registries can eventually be populated together per pattern. |
| 2026-09-11 | Project scaffolded: `git init`; `uv init --app --package` (Python 3.11, `uv_build` backend); runtime deps (pandas, numpy, scipy, pydantic, pyyaml, typer, matplotlib, mplfinance, pyarrow) added, `dev` group (pytest, pytest-cov, ruff, mypy) added, `ml` extra (scikit-learn, xgboost, lightgbm) registered but not installed. `src/chart_patterns/` created with one subpackage per pipeline stage (§3). Added `src/chart_patterns/paths.py` (`PROJECT_ROOT`, resolved by walking up to the nearest `pyproject.toml`) so relocated modules keep resolving `data/`/`output/` at the repo root regardless of package depth. Moved `candle_db.py` → `src/chart_patterns/data/candle_db.py` and `custom_logger.py` → `src/chart_patterns/custom_logger.py`, updating their path resolution and imports accordingly; verified against the real `data/candles.db` post-move. Added starter YAML configs (§6) and a pytest smoke test. Ruff configured with `select = ["E", "F", "I"]` (not the full opinionated default) and `line-length = 120`, with a per-file `E501` ignore for `candle_db.py` — its blind-except/naive-datetime patterns and long lines are pre-existing, intentional choices in provided code, not addressed by scaffolding. Fixed a real gitignore gap: the `data/*.db` pattern missed the 266MB `candles.db.2023_2025` backup (doesn't end in `.db`); changed to `data/*.db*`. |
