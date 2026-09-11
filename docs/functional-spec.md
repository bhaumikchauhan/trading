# Chart Pattern Recognition — Functional Specification

_Living document — updated as planning and implementation progress._

## Purpose

Detect classical technical-analysis chart patterns (head & shoulders, cup & handle,
double top/bottom, triangles, wedges, etc.) from OHLCV price data, using a
recall-first rule-based pipeline that can later be sharpened for precision by an
optional ML scoring layer. Approach follows the pivot-sequence method validated by
Lo, Mamaysky & Wang (2000): smooth → find extrema → match geometric rules over the
extrema sequence → score candidates → (optionally) filter with ML → rank alerts.

**Guiding principle:** minimize false negatives (never silently miss a real
pattern). False positives are acceptable and are expected to be pruned later by
tolerance tuning, scoring, and the optional ML layer — never by tightening rules
in a way that risks dropping true patterns.

## Status Legend

| Status | Meaning |
|---|---|
| Not Started | Not yet begun |
| In Progress | Actively being worked on |
| Blocked | Waiting on a decision/dependency |
| Done | Complete and verified |

## Progress Summary

| # | High-Level Task | Status |
|---|---|---|
| 1 | Project Infrastructure | In Progress |
| 2 | Data Ingestion Layer | Not Started |
| 3 | Smoothing Layer | Not Started |
| 4 | Pivot / Extrema Detection | Not Started |
| 5 | Rule-Based Pattern Matcher Framework | Not Started |
| 6 | Pattern Implementations | Not Started |
| 7 | Candidate Scoring & Ranking | Not Started |
| 8 | Backtesting & Validation Framework | Not Started |
| 9 | Alerting / Output Layer | Not Started |
| 10 | Visualization & Reporting | Not Started |
| 11 | ML Scorer (Optional / Future Phase) | Not Started |

---

## 1. Project Infrastructure

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 1.1 | Initialize repository (git init, .gitignore, README) | Done | `git init` done; `.gitignore` covers venv, caches, DB files (incl. the untracked `candles.db.2023_2025` backup), logs, local Claude settings |
| 1.2 | Define folder structure (src, tests, data, configs, docs, notebooks) | Done | `src/chart_patterns/` src-layout package with one subpackage per pipeline stage; `tests/{unit,integration,fixtures}`; `configs/{,patterns/}` |
| 1.3 | Dependency management setup (env/package manager) | Done | `uv`; `pyproject.toml` with runtime deps, `dev` dependency group, and a deferred `ml` optional-dependency group (not installed until Phase 2) |
| 1.4 | Testing framework setup | Done | `pytest` wired via `[tool.pytest.ini_options]`; smoke test passing (`tests/unit/test_project_setup.py`) |
| 1.5 | Logging setup | Done | Reusing provided `custom_logger.py` singleton logger (see technical-spec §11) rather than a new logging stack; two minor cleanup items tracked in technical-spec's Open Decisions |
| 1.6 | Config management for tunable parameters (smoothing thresholds, pattern tolerances) | Done | `src/chart_patterns/config/`: Pydantic models (`SmoothingConfig`, `LoggingConfig`, `DoubleTopConfig`) + loaders reading the YAML files, with validation (e.g. odd Savitzky-Golay window, ordered time-separation bounds, positive tolerances). A small per-pattern model registry mirrors the pattern-matcher registry planned for §9 of the technical doc |
| 1.7 | CI setup (lint + test on push) | Not Started | `ruff` + `pytest` run clean locally; no CI workflow file yet |

## 2. Data Ingestion Layer

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 2.1 | Define OHLCV schema/interface (timestamp, open, high, low, close, volume) | Not Started | |
| 2.2 | Implement historical data loader (CSV/local file) | Not Started | First adapter — needed for backtesting |
| 2.3 | Implement live/streaming market feed adapter | Not Started | Deferred until historical pipeline works |
| 2.4 | Data validation (gaps, duplicate timestamps, missing bars, non-monotonic time) | Not Started | |
| 2.5 | Multi-timeframe support (resampling e.g. 1m → 1h/1d) | Not Started | |
| 2.6 | Historical data caching/storage format | Not Started | |

## 3. Smoothing Layer

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 3.1 | Implement ZigZag filter with configurable % / ATR-based threshold | Not Started | Primary/default method |
| 3.2 | Implement Savitzky-Golay filter as alternative smoothing strategy | Not Started | Pluggable |
| 3.3 | Implement kernel regression smoothing (per Lo/Mamaysky/Wang) as alternative | Not Started | Pluggable, lower priority |
| 3.4 | Smoothing strategy interface so methods are swappable via config | Not Started | |
| 3.5 | Per-instrument/timeframe smoothing parameter tuning | Not Started | |
| 3.6 | Unit tests / visual checks of smoothing output against hand-checked examples | Not Started | |

## 4. Pivot / Extrema Detection

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 4.1 | Implement local extrema detection on smoothed series | Not Started | e.g. rolling-window comparison or argrelextrema |
| 4.2 | Normalize pivots into compact sequence: (index, timestamp, price, type: peak/trough) | Not Started | Core data structure used by all pattern matchers |
| 4.3 | Handle edge cases: consecutive same-type pivots, flat/plateau extrema, series start/end | Not Started | |
| 4.4 | Visualization utility: plot price + smoothed line + detected pivots | Not Started | Needed for manual QA throughout project |

## 5. Rule-Based Pattern Matcher Framework

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 5.1 | Define common pattern-matcher interface (input: pivot sequence → output: candidates) | Not Started | |
| 5.2 | Define tolerance/config schema per pattern (height similarity %, time symmetry %, depth ratio, etc.) | Not Started | Must be easy to widen for recall tuning |
| 5.3 | Define candidate pattern data model (pattern type, pivots involved, time span, confidence score, metadata) | Not Started | |
| 5.4 | Pattern registry so new pattern matchers can be plugged in without touching core pipeline | Not Started | |
| 5.5 | Overlap/duplicate handling across sliding windows of pivots | Not Started | Same pivots may trigger multiple candidate windows |

## 6. Pattern Implementations

Build order: simplest/most symmetric pattern first, end-to-end with backtest, before
generalizing. Each pattern sub-list follows the same shape: define rule → implement →
synthetic-data unit tests → tolerance tuning against labeled data → confidence score.

### 6.1 Double Top (reference implementation, build first)

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 6.1.1 | Encode geometric rule: 2 peaks of similar height separated by a meaningful trough | Not Started | |
| 6.1.2 | Define tolerances: height-similarity %, min trough depth, max/min time separation | Not Started | |
| 6.1.3 | Implement confidence score (e.g. based on height-similarity + trough depth) | Not Started | |
| 6.1.4 | Unit tests with synthetic pivot sequences (clear positives, clear negatives, edge cases) | Not Started | |
| 6.1.5 | Validate end-to-end on real historical data sample | Not Started | First full pipeline run |

### 6.2 Double Bottom

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 6.2.1 | Mirror double-top rule (trough-peak-trough) | Not Started | Should reuse double-top logic via inversion |
| 6.2.2 | Unit tests | Not Started | |

### 6.3 Head and Shoulders (top)

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 6.3.1 | Encode geometric rule: 5 pivots (peak-trough-peak-trough-peak), middle peak highest | Not Started | |
| 6.3.2 | Define tolerances: shoulder height similarity %, neckline slope tolerance, head prominence | Not Started | |
| 6.3.3 | Neckline construction (line through the two troughs) and breakout condition (optional) | Not Started | |
| 6.3.4 | Confidence score (shoulder symmetry, head prominence, neckline cleanliness) | Not Started | |
| 6.3.5 | Unit tests with synthetic data | Not Started | |

### 6.4 Inverse Head and Shoulders

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 6.4.1 | Mirror head-and-shoulders rule | Not Started | Reuse via inversion |
| 6.4.2 | Unit tests | Not Started | |

### 6.5 Cup and Handle

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 6.5.1 | Encode rounded-trough ("cup") detection rule (smooth U-shape, similar rim heights) | Not Started | Harder than 5-pivot patterns — needs shape-based check, not just pivot ordering |
| 6.5.2 | Encode "handle" detection: shallower, shorter pullback near cup's right rim | Not Started | |
| 6.5.3 | Define tolerances: cup depth/duration ratio, handle depth/duration ratio, rim symmetry | Not Started | |
| 6.5.4 | Confidence score | Not Started | |
| 6.5.5 | Unit tests with synthetic data | Not Started | |

### 6.6 Future Patterns (backlog, order TBD)

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 6.6.1 | Ascending / Descending / Symmetrical Triangle | Not Started | |
| 6.6.2 | Rising / Falling Wedge | Not Started | |
| 6.6.3 | Bull / Bear Flag and Pennant | Not Started | |
| 6.6.4 | Rectangle / Range-bound consolidation | Not Started | |
| 6.6.5 | Triple Top / Triple Bottom | Not Started | |

## 7. Candidate Scoring & Ranking

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 7.1 | Define per-pattern scoring formula (weighted geometric-closeness metrics) | Not Started | |
| 7.2 | Normalize scores to a common 0–1 confidence scale across pattern types | Not Started | |
| 7.3 | Deduplication logic for overlapping candidates (same pivots, multiple pattern types or windows) | Not Started | |
| 7.4 | Ranking output (sorted candidate list per run) | Not Started | |

## 8. Backtesting & Validation Framework

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 8.1 | Curate hand-labeled historical dataset of true pattern instances | Not Started | Critical — drives tolerance tuning |
| 8.2 | Build evaluation harness: precision/recall/F-beta (recall-weighted) per pattern | Not Started | |
| 8.3 | Tolerance-tuning loop: widen rule tolerances until labeled true positives are captured | Not Started | Recall-first per project goal |
| 8.4 | Regression test suite to catch recall degradation as rules evolve | Not Started | |
| 8.5 | False-positive rate tracking (accepted but monitored, not optimized away at recall's expense) | Not Started | |

## 9. Alerting / Output Layer

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 9.1 | Define alert data model and ranked-output format (JSON/CSV) | Not Started | |
| 9.2 | Output sink: console/file | Not Started | First target |
| 9.3 | Output sink: webhook/email/Slack | Not Started | Later, once core detection is solid |
| 9.4 | Deduplication/cooldown so the same pattern instance doesn't re-alert every bar | Not Started | |

## 10. Visualization & Reporting

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 10.1 | Chart rendering with detected pivots + pattern overlay for manual QA | Not Started | Used continuously during development |
| 10.2 | Per-run summary report (candidates found, scores, pattern breakdown) | Not Started | |

## 11. ML Scorer (Optional / Future Phase)

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 11.1 | Feature engineering from candidate geometry + volume | Not Started | Only starts once real candidate data exists |
| 11.2 | Labeling workflow to confirm/reject candidates for training data | Not Started | |
| 11.3 | Train baseline gradient-boosted tree classifier (XGBoost/LightGBM) | Not Started | |
| 11.4 | Integrate as post-filter/ranker on top of rule-based candidates (never as primary detector) | Not Started | Mistakes here cost precision, not recall |
| 11.5 | Evaluate precision improvement while confirming recall is not degraded | Not Started | |
| 11.6 | (Stretch) CNN-on-chart-image classifier exploration | Not Started | Higher effort/infra; only if tabular approach plateaus |

---

## Change Log

| Date | Change |
|---|---|
| 2026-09-11 | Initial functional specification created. |
| 2026-09-11 | Project scaffolding complete (task 1.1–1.6): git repo, uv-managed src-layout package, pytest/ruff wired up, starter YAML configs, `candle_db.py`/`custom_logger.py` relocated into the package. See technical-spec for details. |
| 2026-09-11 | Config loader implemented (task 1.6 → Done): Pydantic-validated loaders for smoothing, logging, and double-top pattern config, with unit tests covering both the real YAML files and validation failure cases. |
