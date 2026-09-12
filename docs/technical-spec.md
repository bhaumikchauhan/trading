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
│       ├── smoothing/            # atr.py (done); savgol, kernel_regression continuous smoothers (future)
│       ├── pivots/               # Pivot model + all pivot detection: zigzag (default), extrema (§8 note)
│       ├── patterns/             # Candidate model, registry, one module per pattern (double_top done)
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
  method: fixed        # "fixed" or "atr" — see §8.1
  threshold_pct: 3.0    # used directly when method: fixed; fallback for method: atr
  atr:
    period: 14
    multiplier: 2.5
savgol:
  window_length: 11
  polyorder: 2
```

Each pattern config maps to a corresponding Pydantic model (e.g.
`DoubleTopConfig`) so invalid YAML fails fast at load time rather than producing
silent bad matches. Per functional-spec's recall-first principle, tolerance
tuning during backtesting (§7) means editing these YAML files, not code.

### 6.1 ATR-Based ZigZag Threshold (`smoothing/atr.py`)

A single global `threshold_pct` miscalibrates across symbols: a stock that
typically moves 1%/day gets buried in noise-level pivots at a 3% threshold no
different-looking than a stock that typically moves 5%/day. `atr_threshold_pct(df,
period, multiplier)` computes a per-symbol threshold instead:

1. `average_true_range(df, period)` — standard rolling-mean True Range (`max(high-low,
   |high-prev_close|, |low-prev_close|)`, averaged over `period` bars, `min_periods=period`
   so early bars are `NaN` rather than a misleadingly-partial average).
2. Convert to a percentage of price (`ATR / close × 100`) and take the **median**
   across the whole window — not the latest value or the mean — so the
   threshold reflects the symbol's typical volatility rather than reacting to
   one recent spike or a single unusually quiet patch.
3. Multiply by a configurable `multiplier` (default 2.5) to convert "typical
   bar-to-bar range" into a sensible swing-confirmation threshold.

Verified on real data: `NIFTYBEES` (a low-volatility index ETF) → 4.83%;
`ANIKINDS-BE`/`E2E` (volatile small-caps) → 13–15%. `zigzag_pivots()` itself is
completely unchanged — it still just takes one `threshold_pct: float`; ATR only
changes *how that number is chosen* per symbol, computed once per symbol in
`cli/main.py::scan` before calling it. If a symbol has fewer bars than the
configured ATR `period`, `atr_threshold_pct` raises `ValueError` and `scan`
falls back to `ZigZagConfig.threshold_pct` for that symbol rather than
crashing or skipping it.

**Explicitly does not address** the non-adjacent/multi-scale pivot matching gap
(functional-spec §5.6): that problem is *within one symbol* (a stock can have
both week-scale and multi-month-scale genuine structure at the same time), while
ATR calibration addresses *between-symbol* miscalibration. They're independent,
both-useful fixes, not alternatives to each other.

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
  pivots.detect_pivots(method="zigzag") ──▶ List[Pivot]        (ZigZag: default, implemented)
        │                                    ▲
        │                          smoothing.savgol/kernel ──▶ smoothed series
        │                                    │
        │                          pivots.detect_pivots(method="extrema")   (future smoothers, implemented)
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

**Why ZigZag lives under `pivots/`, not `smoothing/`:** the original plan (§1
Scope) treated smoothing and pivot detection as two strictly sequential stages —
smooth the series, then find extrema on it. That holds for Savitzky-Golay and
kernel regression, which really do produce an intermediate continuous series with
no natural notion of a "pivot" until `find_local_extrema()` is run on it. ZigZag
doesn't fit that shape: by definition, it *only* produces pivots — there is no
separate continuous "ZigZag line" independent of the confirmed peak/trough
sequence (chart platforms draw the ZigZag line by literally connecting
consecutive pivots). Implementing it as `pivots/zigzag.py::zigzag_pivots()`
(price series in, `list[Pivot]` out) reflects what it actually computes, rather
than forcing an artificial intermediate "smoothed series" through an unrelated
`smoothing/zigzag.py` module. `pivots.detect_pivots(series, method=...)` is the
one entry point pattern matchers use regardless of which path produced the
pivots.

See [pivot-detection.md](pivot-detection.md) for a full algorithm walkthrough
(including a hand-traced worked example) of everything in `pivots/` and
`viz/charts.py::plot_pivots`.

## 9. Pattern Matcher Framework

Implemented in `src/chart_patterns/patterns/` as:

```python
# models.py
class Candidate(BaseModel):
    pattern_type: str
    pivots: list[Pivot]
    confidence_score: float  # Field(ge=0, le=1)
    metrics: dict[str, float]
    symbol: str | None = None
    timeframe: str | None = None
    # start_index/end_index/start_timestamp/end_timestamp as properties over pivots[0]/pivots[-1]

# registry.py
PatternMatcherFn = Callable[[list[Pivot], Any], list[Candidate]]

def register_pattern(name: str) -> Callable[[PatternMatcherFn], PatternMatcherFn]: ...
def find_candidates(pattern_name: str, pivots: list[Pivot], config: Any) -> list[Candidate]: ...
```

This ended up as a plain function + dict-registry convention rather than the
`Protocol` class originally sketched here — the same call made for
`pivots.detect_pivots` (§8's rationale note applies equally here): with one
pattern implemented so far, a formal interface class would be pure ceremony.
Each pattern module (e.g. `double_top.py::find_double_top_candidates`) is a
plain function decorated `@register_pattern("double_top")`; `config`'s type is
`Any` at the registry boundary specifically so each matcher can declare its own
concrete config type (`DoubleTopConfig`, etc.) in its own signature without
mypy rejecting the registration on parameter-type variance grounds.

- The registry lets new pattern modules plug in without editing the core
  pipeline loop — satisfies functional-spec 5.4. Registration happens as a side
  effect of `patterns/__init__.py` importing each pattern module, so importing
  `chart_patterns.patterns` is what populates the registry.
- Each matcher only depends on `list[Pivot]` and its own YAML-backed config
  object — no cross-pattern coupling, no direct DataFrame access (keeps unit
  tests fast: synthetic pivot lists, no need to fabricate OHLCV data per test).
- Overlapping candidates (e.g. a 5-pivot peak-trough-peak-trough-peak sequence
  satisfying the double-top rule twice) are all returned by design — recall
  first, per the project's stated goal. Deduplication is functional-spec 7.3's
  job, not the matcher's.
- `viz/charts.py::plot_pivots` takes an optional `candidates: list[Candidate]`
  and shades each one's span (`axvspan` between `start_index`/`end_index`) with
  a `pattern_type (confidence)` annotation — this is how double-top candidates
  found in real `candle_db` data were visually verified (functional-spec 6.1.5,
  10.1).

### 9.1 Double Bottom and Head and Shoulders (added after Double Top)

- **Double Bottom is not implemented as "double top on negated prices."**
  Functional-spec 6.2.1 suggested reuse via inversion, but negating prices
  breaks the percentage-difference math every matcher relies on (percentages
  are computed against a positive-price denominator; negating flips signs
  inconsistently rather than just mirroring the comparison). Instead,
  `double_bottom.py::find_double_bottom_candidates` is a structurally parallel,
  independent function — same shape of logic (3-pivot window, two filters, a
  weighted confidence score), mirrored by hand: `depth_similarity_pct` instead
  of `height_similarity_pct`, `min_peak_prominence_pct` instead of
  `min_trough_depth_pct`. This also keeps each pattern independently readable
  and testable, consistent with the one-file-per-pattern registry design.
- **Head and Shoulders** extends the same 3-pivot-window idea to a 5-pivot
  window (`peak, trough, peak, trough, peak`) with three independent
  geometric checks — head prominence over the higher shoulder, shoulder-height
  similarity, and neckline slope (the two troughs' price difference, not a
  fitted line — see functional-spec 6.3.3) — combined into confidence via a
  0.4/0.35/0.25 weighting (shoulder symmetry weighted highest since it's the
  most visually defining trait, neckline flatness lowest since it's the most
  secondary confirmation). It deliberately does **not** require the left and
  right halves to span similar bar-counts — real head and shoulders patterns
  are routinely asymmetric in time even when symmetric in price, and adding a
  symmetry constraint would cost recall for no accuracy benefit backed by the
  pattern's actual definition.
- Both were verified the same way as Double Top: unit tests with hand-built
  pivot sequences isolating each rejection rule, plus a real-data check via
  `chart-patterns scan --pattern double_bottom` / `--pattern head_and_shoulders`
  against `candle_db`. A zoomed-in QA chart on a real `head_and_shoulders`
  candidate (`21STCENMGM`, Feb–Apr 2021) showed a textbook shape — sharp head
  well above two roughly-matched shoulders, near-flat neckline.

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
- `typer` CLI, `src/chart_patterns/cli/main.py`, entry point `chart-patterns`
  (`pyproject.toml` `[project.scripts]` → `chart_patterns:main` →
  `cli.app()`). One command implemented so far:
  - `scan [SYMBOL...] [--all-symbols] [--start] [--end] [--pattern] [--min-confidence] [--save-charts] [--save-csv] [--quiet]`
    — runs `zigzag_pivots` + `find_candidates` against real `candle_db` data per
    symbol, prints each candidate's pivots/metrics/confidence to console (sorted
    highest-confidence first, grouped by pattern), saves a `plot_pivots` QA
    chart, and writes every result to CSV under `output/scans/`. This is a
    manual-verification tool (functional-spec 9.2), not the labeled-dataset
    `backtest` harness planned for functional-spec §8 — deliberately not named
    `backtest` to avoid implying it computes precision/recall against ground
    truth, which it doesn't (there is no labeled dataset yet).
  - `SYMBOL...` is optional; `--all-symbols` loads every symbol from
    `data/all_symbols.csv` (2,729 symbols) instead. A full-universe scan for one
    pattern with `--no-save-charts` completes in ~9s — no need for the
    `memory=True` `candle_db` acceleration mode (§5.1) at this scale; revisit if
    scanning `--pattern all` or many patterns across the full universe proves
    slow in practice.
  - `--pattern all` scans every pattern the registry knows about
    (`patterns.list_registered_patterns()`, new — a thin `sorted(_PATTERN_MATCHERS)`
    wrapper) instead of one. Pivots are computed once per symbol and reused
    across patterns; console output and the QA chart group/aggregate across all
    scanned patterns for that symbol.
  - `--quiet` prints one summary line per symbol (bars/pivots/candidate counts
    per pattern) instead of full per-candidate detail — necessary once
    `--all-symbols` is combined with `--pattern all`, or console output for a
    2,729-symbol run becomes unusable. Full detail is always in the CSV
    regardless of `--quiet`.
  - Two, and only two, log lines go through `custom_logger.logger` (so they
    land in the `output/*.log` file, not just console, independent of
    `--quiet`): `Scanning {i}/{total}: {symbol}` right before each symbol is
    fetched, and one `Scan summary: {pattern}={count}, ... (total=N candidates
    across M symbol(s))` after the loop. Deliberately not logging per-candidate
    — that level of detail belongs to `typer.echo`/the CSV, not the log file.
  - CSV output: one row per candidate
    (`symbol, pattern, candidate_number, confidence_score, start_date, end_date,
    pivots, metrics`), `pivots`/`metrics` flattened to a single delimited string
    each rather than variable-width columns (different patterns have different
    pivot counts — 3 for double top/bottom, 5 for head and shoulders). Filename
    is `<symbol-or-N>_<pattern-or-mul_pattern>.csv` under `output/scans/`: the
    first segment is the literal symbol when exactly one was scanned, or the
    symbol *count* otherwise; the second is the pattern name when exactly one
    was scanned, or the literal `mul_pattern` otherwise. Per-symbol chart
    filenames follow the same `mul_pattern` convention for the second segment
    but always use the literal symbol for the first (one chart is always one
    symbol, so there's never a count to substitute there).
  - Still planned, not yet built: a `backtest` command once §8's labeled
    dataset and evaluation harness exist, and a standalone `plot` command
    (currently `scan`'s `--save-charts` covers this need).
  - **Typer gotcha hit in practice:** a `Typer()` app with exactly one
    `@app.command()` and no `@app.callback()` auto-flattens — it silently
    accepts the command name as a positional argument instead of dispatching
    to it (`chart-patterns scan RELIANCE` would treat `"scan"` as a symbol).
    Fixed by adding a no-op `@app.callback()`, which forces Typer to keep
    requiring the subcommand name. This will matter again if a second command
    is ever removed and one is left alone.
  - `plot_pivots` passes `warn_too_much_data=len(plot_df) + 1` to `mpf.plot` —
    without it, mplfinance's density warning fires on nearly every real
    (non-test) call, since this project's charts are routinely multi-year
    daily history.
  - **Same `mpf.plot(kwarg=None)` gotcha, second occurrence:** a symbol with
    zero detected pivots (e.g. a low-volatility liquid fund like `ABSLLIQUID`,
    which barely moves) produces an empty `addplots` list, and
    `"addplot": addplots or None` passed `addplot=None` straight through —
    `mpf.plot` rejects that exactly like it rejected `title=None`. Both kwargs
    are now only added to `plot_kwargs` when truthy/not-`None`, never set to
    `None` explicitly. Caught by running the real `scan --all-symbols` CLI,
    not by the test suite — `test_plot_pivots_handles_zero_pivots` now covers
    it directly.

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
| 2026-09-12 | ATR-based ZigZag thresholding added (§6.1): `smoothing/atr.py` (`average_true_range`, `atr_threshold_pct`), `ZigZagConfig.method: fixed \| atr` with a `threshold_pct` fallback for thin-history symbols. First real code in `smoothing/`, which previously only had a placeholder `__init__.py`. Wired into `scan`, which now prints the threshold used per symbol. Verified per-symbol calibration on real data; explicitly does not address the separate §5.6 non-adjacent-pivot gap (between-symbol vs. within-symbol problem). |
| 2026-09-12 | Fixed a real crash found via `scan --all-symbols`: `ABSLLIQUID` (a near-flat liquid fund) hit zero detected pivots, and `plot_pivots` passed `addplot=None` to `mpf.plot`, which rejects it the same way it rejects `title=None`. Both kwargs are now omitted rather than set to `None`; added `test_plot_pivots_handles_zero_pivots` as a regression test. |
| 2026-09-12 | `scan` gained two `custom_logger` log lines (§11): per-symbol `Scanning i/total` progress and a final `Scan summary` with per-pattern candidate counts — kept deliberately minimal (no per-candidate logging), independent of `--quiet` since logging and console-verbosity are separate concerns. |
| 2026-09-12 | `scan` CLI extended (§11): `--all-symbols` (`data/all_symbols.csv`, 2,729 symbols, ~9s full-universe single-pattern scan with `--no-save-charts`), `--pattern all` via new `patterns.list_registered_patterns()`, CSV output under `output/scans/` (`<symbol-or-N>_<pattern-or-mul_pattern>.csv`), `--quiet`. Added `tests/unit/test_cli.py` for the pure-logic pieces (filename-stem convention, symbol-file parsing, pivot/metric string formatting) — the `scan` command itself still isn't unit-tested since it depends on the real `candle_db`, consistent with §10's stated approach of manual verification for DB-dependent behavior. |
| 2026-09-12 | Double Bottom and Head and Shoulders pattern matchers added (§9.1): `DoubleBottomConfig`/`HeadAndShouldersConfig`, `configs/patterns/{double_bottom,head_and_shoulders}.yaml`, both registered and covered by unit tests plus a real-data `chart-patterns scan` check. Double Bottom implemented as an independent mirror rather than a price-negation trick (negation breaks the percentage math); Head and Shoulders deliberately has no time-symmetry constraint between its two halves. |
| 2026-09-11 | `chart-patterns scan` CLI added (§11) for manually verifying pattern matches against real `candle_db` data: prints ranked candidates with full pivot/metric detail, saves a QA chart per symbol. Hit and fixed a real Typer gotcha (single-command apps auto-flatten and swallow the subcommand name unless a `@app.callback()` is present) and suppressed mplfinance's too-much-data warning (routine at this project's multi-year chart sizes) via `warn_too_much_data`. |
| 2026-09-11 | Double Top pattern matcher implemented (§9): `patterns/models.py::Candidate`, `patterns/registry.py` (`register_pattern`/`find_candidates`), `patterns/double_top.py::find_double_top_candidates` (0.6 height-similarity / 0.4 trough-depth weighted confidence score). Ended up function+dict-registry, not the `Protocol` class originally sketched here — same rationale as `pivots.detect_pivots`. `plot_pivots` extended with an optional `candidates` overlay. Verified against a synthetic integration fixture and, manually, against 200 real symbols from `candle_db` (5,801 candidates at the default generous tolerances) with a QA chart rendered for a real instance. Along the way, fixed a real bug: `plot_pivots(title=None)` crashed because `mpf.plot` rejects `title=None` outright (needs the kwarg omitted, not set to `None`) — only surfaced once a test called `plot_pivots` without an explicit title. |
| 2026-09-11 | Added [pivot-detection.md](pivot-detection.md), a detailed implementation deep-dive (algorithm walkthroughs, a hand-traced worked example, every class/function, edge cases) for `pivots/` and `viz/charts.py`. |
| 2026-09-11 | Pivot detection implemented in `src/chart_patterns/pivots/`: `zigzag.py` (`zigzag_pivots`, the default threshold-based method, hand-traced and verified against real `ANIKINDS-BE` history), `extrema.py` (`find_local_extrema` via `scipy.signal.argrelextrema`, plus `_enforce_alternation` for the consecutive-same-type edge case, for future Savgol/kernel-regression smoothers), `models.py` (`Pivot`), unified via `detector.py::detect_pivots()`. Revised §8's pipeline diagram and added a rationale note: ZigZag is implemented directly under `pivots/` rather than `smoothing/`, since it has no separate continuous output distinct from its pivots. Also added `viz/charts.py::plot_pivots` (mplfinance candlesticks + pivot markers, Agg backend) ahead of schedule (originally §10) since it was the fastest way to visually verify pivot detection. |
| 2026-09-11 | Project scaffolded: `git init`; `uv init --app --package` (Python 3.11, `uv_build` backend); runtime deps (pandas, numpy, scipy, pydantic, pyyaml, typer, matplotlib, mplfinance, pyarrow) added, `dev` group (pytest, pytest-cov, ruff, mypy) added, `ml` extra (scikit-learn, xgboost, lightgbm) registered but not installed. `src/chart_patterns/` created with one subpackage per pipeline stage (§3). Added `src/chart_patterns/paths.py` (`PROJECT_ROOT`, resolved by walking up to the nearest `pyproject.toml`) so relocated modules keep resolving `data/`/`output/` at the repo root regardless of package depth. Moved `candle_db.py` → `src/chart_patterns/data/candle_db.py` and `custom_logger.py` → `src/chart_patterns/custom_logger.py`, updating their path resolution and imports accordingly; verified against the real `data/candles.db` post-move. Added starter YAML configs (§6) and a pytest smoke test. Ruff configured with `select = ["E", "F", "I"]` (not the full opinionated default) and `line-length = 120`, with a per-file `E501` ignore for `candle_db.py` — its blind-except/naive-datetime patterns and long lines are pre-existing, intentional choices in provided code, not addressed by scaffolding. Fixed a real gitignore gap: the `data/*.db` pattern missed the 266MB `candles.db.2023_2025` backup (doesn't end in `.db`); changed to `data/*.db*`. |
