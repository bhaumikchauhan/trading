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
| 3 | Smoothing Layer | In Progress |
| 4 | Pivot / Extrema Detection | Done |
| 5 | Rule-Based Pattern Matcher Framework | In Progress |
| 6 | Pattern Implementations | In Progress |
| 7 | Candidate Scoring & Ranking | In Progress |
| 8 | Backtesting & Validation Framework | Not Started |
| 9 | Alerting / Output Layer | In Progress |
| 10 | Visualization & Reporting | In Progress |
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
| 2.4 | Data validation (gaps, duplicate timestamps, missing bars, non-monotonic time) | Not Started | Should also catch bad OHLC bars, not just timestamp issues — confirmed real example: `NIFTYBEES` 2022-01-17 has `open=223.00, high=223.00` vs `close=198.03` (~12% gap, no similar move on adjacent days), almost certainly a bad tick. Harmless to pattern detection today since matchers use `close` only, but would corrupt any future high/low-based check (e.g. cup-and-handle shape fitting) |
| 2.5 | Multi-timeframe support (resampling e.g. 1m → 1h/1d) | Not Started | |
| 2.6 | Historical data caching/storage format | Not Started | |

## 3. Smoothing Layer

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 3.1 | Implement ZigZag filter with configurable % / ATR-based threshold | Done | `pivots/zigzag.py::zigzag_pivots` (lives under `pivots/`, not `smoothing/` — see technical-spec §8 rationale). Fixed % via `configs/smoothing.yaml` (`zigzag.method: fixed`); ATR-based via `smoothing/atr.py::atr_threshold_pct` (`zigzag.method: atr`) — computes `multiplier × median(ATR% over the window)` per symbol, so a volatile small-cap and a quiet ETF each get a threshold scaled to their own typical daily range instead of one global %. Verified: `NIFTYBEES` (quiet) → 4.83%, `ANIKINDS-BE`/`E2E` (volatile) → 13–15%. Falls back to `threshold_pct` if a symbol has too little history for the configured ATR period |
| 3.2 | Implement Savitzky-Golay filter as alternative smoothing strategy | Not Started | Pluggable |
| 3.3 | Implement kernel regression smoothing (per Lo/Mamaysky/Wang) as alternative | Not Started | Pluggable, lower priority |
| 3.4 | Smoothing strategy interface so methods are swappable via config | Not Started | |
| 3.5 | Per-instrument/timeframe smoothing parameter tuning | Not Started | |
| 3.6 | Unit tests / visual checks of smoothing output against hand-checked examples | Not Started | |

## 4. Pivot / Extrema Detection

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 4.1 | Implement local extrema detection on smoothed series | Done | `pivots/extrema.py` (`find_local_extrema`, `scipy.signal.argrelextrema`) for continuously-smoothed series; `pivots/zigzag.py` (`zigzag_pivots`) as the threshold-based primary/default method — see technical-spec §3/§9 note on why ZigZag lives under `pivots/` rather than `smoothing/` |
| 4.2 | Normalize pivots into compact sequence: (index, timestamp, price, type: peak/trough) | Done | `pivots/models.py`: `Pivot` (Pydantic) with `index`, `timestamp`, `price`, `type` |
| 4.3 | Handle edge cases: consecutive same-type pivots, flat/plateau extrema, series start/end | Done | `_enforce_alternation()` collapses consecutive same-type extrema to the more extreme one; ZigZag alternates by construction; empty/flat series return no pivots rather than erroring |
| 4.4 | Visualization utility: plot price + smoothed line + detected pivots | Done | `viz/charts.py::plot_pivots` (mplfinance candlesticks + pivot markers); manually verified against real `ANIKINDS-BE` history |

## 5. Rule-Based Pattern Matcher Framework

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 5.1 | Define common pattern-matcher interface (input: pivot sequence → output: candidates) | Done | A plain function convention (`(pivots, config) -> list[Candidate]`) rather than a class/Protocol hierarchy — same reasoning as `pivots.detect_pivots`: only one implementation so far, a formal interface would be premature |
| 5.2 | Define tolerance/config schema per pattern (height similarity %, time symmetry %, depth ratio, etc.) | Done | Built as part of the config loader task (technical-spec §6): `DoubleTopConfig` |
| 5.3 | Define candidate pattern data model (pattern type, pivots involved, time span, confidence score, metadata) | Done | `patterns/models.py::Candidate` — `start_index`/`end_index`/`start_timestamp`/`end_timestamp` derived as properties from `pivots[0]`/`pivots[-1]` |
| 5.4 | Pattern registry so new pattern matchers can be plugged in without touching core pipeline | Done | `patterns/registry.py`: `@register_pattern(name)` decorator + `find_candidates(pattern_name, pivots, config)` dispatcher, mirroring the config loader's own per-pattern registry |
| 5.5 | Overlap/duplicate handling across sliding windows of pivots | Not Started | Deliberately deferred — `find_double_top_candidates` documents that it returns all overlapping matches by design (recall-first); dedup is this task's job, not the matcher's |
| 5.6 | Non-adjacent / multi-scale pivot matching | Not Started | **Confirmed real recall gap** — see case study below. Deferred; ATR-based thresholding (functional-spec §3.1 / technical-spec) is a related but separate fix and does not resolve this |

### 5.6 Case Study: Confirmed Non-Adjacent Pivot Miss on `E2E`

**How it was found:** manually verifying `head_and_shoulders` output via `chart-patterns scan E2E`, a real, visually obvious head-and-shoulders was spotted on the chart that the scanner had not reported as a candidate:

| Role | Date | Price | Type |
|---|---|---|---|
| Left shoulder | 2025-05-23 | 299.87 | peak |
| Left trough (neckline) | 2025-07-28 | 203.27 | trough |
| Head | 2025-10-07 | 374.35 | peak |
| Right trough (neckline) | 2025-12-29 | 195.52 | trough |
| Right shoulder | 2026-02-19 | 296.34 | peak |

**Step 1 — confirm the 5 points are individually valid.** Extracting exactly these 5 pivots (by their bar position) from the real ZigZag(3%) pivot sequence and running `find_head_and_shoulders_candidates` on *just* that 5-element list produces exactly 1 candidate:

```
confidence = 0.703
metrics: shoulder_height_diff_pct=1.215, head_prominence_pct=24.84,
         neckline_slope_pct=3.99, bars_span=187
```

Every numeric rule passes comfortably (head prominence 24.8% vs. a 3% minimum; shoulders within 1.2% of each other vs. a 5% tolerance; neckline within 4% vs. a 5% tolerance). This rules out a tolerance-tuning problem — the pattern itself is a clean, strong match.

**Step 2 — find why the full scan didn't report it.** Two independent causes, found in this order:

1. `bars_span = 187` exceeded the then-current `max_time_separation_bars = 180` for `head_and_shoulders` — fixed by widening it to 252 (~1 trading year); see the 6.3.2 note and the commit that applied this.
2. Even after that fix, the candidate still isn't found from the *full* pivot list — because these 5 points are not adjacent in it. Between the 5 anchor pivots, the real ZigZag(3%) sequence for this window contains **8, 12, 6, and 8 additional pivots respectively** (55 pivots total across the full window) — each one a legitimate ≥3% swing (e.g. a mid-decline bounce, a small double-top-shaped blip in September, a consolidation in Jan–Feb), not noise. Every pattern matcher in this project only evaluates *consecutive* entries in the pivot list (`pivots[i:i+5]` for head-and-shoulders, `pivots[i:i+3]` for double top/bottom), so this combination is never even tested, regardless of tolerance settings.

**Step 3 — checked whether a coarser ZigZag threshold fixes it.** If a single larger threshold caused all the nested swings to disappear while preserving these 5 exact points, that would be a simple fix. Testing thresholds from 3% to 15% on the same window:

| Threshold | Total pivots in window | All 5 anchors still present? | Are they consecutive? |
|---|---|---|---|
| 3% (default) | 55 | Yes | No |
| 5% | 29 | Yes | No |
| 8% | 15 | No (one anchor point shifts to a neighboring bar) | No |
| 10% | 7 | No | No |
| 12% | 6 | No | No |
| 15% | 6 | No | No |

No threshold in this sweep works: at 3–5%, the anchors are present but still buried among nested swings (a real secondary swing in September and another in Jan–Feb persist even at 8%). Past 8%, the algorithm starts anchoring on different nearby bars entirely, since a coarser threshold changes exactly which local extreme gets confirmed. There is no single global threshold that isolates just this pattern.

**Conclusion:** the matchers' "consecutive pivots only" design is a structural recall gap for any real pattern whose legs contain smaller genuine sub-swings — common for patterns spanning many months, and not specific to head-and-shoulders or to this one symbol. Two candidate fix directions were identified (not yet decided between):

- **(a) Non-adjacent matching:** rewrite matchers to search any qualifying peaks/troughs within the allowed time span rather than requiring list-adjacency. Most thorough; a real rewrite of every matcher plus more false-positive risk to manage via tolerances and task 5.5's still-unbuilt dedup.
- **(b) Multi-resolution scanning:** run pivot detection + matching at several ZigZag thresholds and merge/dedupe results. Reuses every matcher unchanged; cheaper, but the sweep above shows it would not have caught this specific example on its own.

ATR-based per-symbol thresholding (§3.1) was considered as a possible fix and ruled out for this specific problem: it addresses *cross-symbol* miscalibration (stock A is naturally choppier than stock B), not the fact that *one* symbol can have both week-scale and multi-month-scale genuine structure at the same time. It's being implemented anyway as a separate, independently justified improvement.

## 6. Pattern Implementations

Build order: simplest/most symmetric pattern first, end-to-end with backtest, before
generalizing. Each pattern sub-list follows the same shape: define rule → implement →
synthetic-data unit tests → tolerance tuning against labeled data → confidence score.

### 6.1 Double Top (reference implementation, build first)

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 6.1.1 | Encode geometric rule: 2 peaks of similar height separated by a meaningful trough | Done | `patterns/double_top.py::find_double_top_candidates` scans every consecutive (peak, trough, peak) triple |
| 6.1.2 | Define tolerances: height-similarity %, min trough depth, max/min time separation | Done | `DoubleTopConfig` (task 5.2); values in `configs/patterns/double_top.yaml` |
| 6.1.3 | Implement confidence score (e.g. based on height-similarity + trough depth) | Done | Weighted average (0.6 height-similarity + 0.4 trough-depth, depth capped once ≥2× the minimum); see `docs/pivot-detection.md`-style walkthrough in code comments |
| 6.1.4 | Unit tests with synthetic pivot sequences (clear positives, clear negatives, edge cases) | Done | `tests/unit/test_double_top.py` — height/depth/time-separation rejections, non-peak-trough-peak windows, overlapping-window recall behavior, registry dispatch, `Candidate` validation |
| 6.1.5 | Validate end-to-end on real historical data sample | Done | `tests/integration/test_double_top_pipeline.py` (synthetic OHLCV fixture) plus a manual scan of 200 real symbols from `candle_db` (5,801 candidates found — expected given generous recall-first tolerances) with a QA chart rendered for a real double top instance |

### 6.2 Double Bottom

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 6.2.1 | Mirror double-top rule (trough-peak-trough) | Done | `patterns/double_bottom.py::find_double_bottom_candidates` — a structurally parallel, independent implementation rather than a literal price-negation trick (negating prices breaks the percentage-difference math); see technical-spec §9 |
| 6.2.2 | Unit tests | Done | `tests/unit/test_double_bottom.py`, mirroring `test_double_top.py`'s coverage |

### 6.3 Head and Shoulders (top)

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 6.3.1 | Encode geometric rule: 5 pivots (peak-trough-peak-trough-peak), middle peak highest | Done | `patterns/head_and_shoulders.py::find_head_and_shoulders_candidates`; deliberately does not require left/right time symmetry (real H&S patterns are frequently asymmetric) |
| 6.3.2 | Define tolerances: shoulder height similarity %, neckline slope tolerance, head prominence | Done | `HeadAndShouldersConfig` (`shoulder_height_similarity_pct`, `min_head_prominence_pct`, `max_neckline_slope_pct`, time-separation bounds); `configs/patterns/head_and_shoulders.yaml`. `max_time_separation_bars` widened `180 → 252` (~1 trading year) after a real 187-bar `E2E` pattern was rejected purely on span — see task 5.6 for the (separate, unresolved) non-adjacency issue also found on that same example |
| 6.3.3 | Neckline construction (line through the two troughs) and breakout condition (optional) | Done | Simplified to a % slope check between the two neckline troughs rather than fitting an explicit line; breakout condition skipped (out of scope — detecting the pattern shape, not a trade trigger) |
| 6.3.4 | Confidence score (shoulder symmetry, head prominence, neckline cleanliness) | Done | Weighted 0.4 shoulder-symmetry + 0.35 head-prominence + 0.25 neckline-flatness |
| 6.3.5 | Unit tests with synthetic data | Done | `tests/unit/test_head_and_shoulders.py` — shoulder/head/neckline/span rejections isolated individually, registry dispatch, config validation |

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
| 7.1 | Define per-pattern scoring formula (weighted geometric-closeness metrics) | In Progress | Double top's formula done (task 6.1.3); each future pattern needs its own |
| 7.2 | Normalize scores to a common 0–1 confidence scale across pattern types | In Progress | `Candidate.confidence_score` is `Pydantic`-constrained to `[0, 1]` for every pattern; cross-pattern comparability itself isn't tested yet since only one pattern exists |
| 7.3 | Deduplication logic for overlapping candidates (same pivots, multiple pattern types or windows) | Not Started | Double top currently emits overlapping candidates untouched (by design — see task 5.5) |
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
| 9.1 | Define alert data model and ranked-output format (JSON/CSV) | In Progress | CSV output shipped as part of `scan` (see 9.2) — one row per candidate: `symbol, pattern, candidate_number, confidence_score, start_date, end_date, pivots, metrics`. Still not a formal `Alert` domain model — it's `Candidate` rows written straight to CSV, no dedup/cooldown (task 9.4) |
| 9.2 | Output sink: console/file | In Progress | `cli/main.py::scan` prints ranked `Candidate`s to console (or one summary line per symbol with `--quiet`) and now also writes every result to a CSV under `output/scans/`; supports scanning every symbol in `data/all_symbols.csv` via `--all-symbols`, and every registered pattern via `--pattern all`. Also logs (via `custom_logger`, so it lands in the `output/*.log` file too, not just console) a `Scanning i/total: SYMBOL` progress line per symbol and one `Scan summary: <pattern>=<count>, ...` line at the end — deliberately just those two, not per-candidate logging. Still a manual-verification tool, not the formal `Alert` model from task 9.1 |
| 9.3 | Output sink: webhook/email/Slack | Not Started | Later, once core detection is solid |
| 9.4 | Deduplication/cooldown so the same pattern instance doesn't re-alert every bar | Not Started | |

## 10. Visualization & Reporting

| # | Sub-task | Status | Notes |
|---|---|---|---|
| 10.1 | Chart rendering with detected pivots + pattern overlay for manual QA | Done | `viz/charts.py::plot_pivots` now takes an optional `candidates` list and shades each candidate's span with a confidence-labeled annotation; verified on real double-top candidates found in `candle_db` |
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
| 2026-09-12 | ATR-based ZigZag thresholding implemented (task 3.1 → Done, independent of the 5.6 non-adjacency gap — addresses cross-symbol miscalibration, not within-symbol multi-scale nesting): `smoothing/atr.py`, `ZigZagConfig.method: fixed \| atr`. Verified per-symbol calibration on real data (quiet `NIFTYBEES` → 4.83% vs. volatile `ANIKINDS-BE`/`E2E` → 13–15%) and wired into `scan` (now prints the threshold used per symbol). Also caught while doing this: task 3.1 had been marked Not Started despite `zigzag_pivots` existing since the pivot-detection work — corrected. |
| 2026-09-12 | Expanded task 5.6 into a full case study of the confirmed `E2E` non-adjacent pivot miss: isolated-candidate verification (confidence 0.703), the full 3–15% threshold sweep table, and the two candidate fix directions considered (non-adjacent matching vs. multi-resolution scanning) — decision deferred, not yet chosen. |
| 2026-09-12 | Investigated a real missed head-and-shoulders on `E2E` (task 5.6, new): widened `head_and_shoulders.yaml`'s `max_time_separation_bars` 180→252 (fixes the span-only rejection, and surfaced 2 more real candidates on the same symbol as a side effect); documented the deeper, unresolved non-adjacent/multi-scale pivot matching gap that this example also exposed. |
| 2026-09-12 | `scan` now logs (via `custom_logger`) a `Scanning i/total: SYMBOL` progress line per symbol and one final `Scan summary` line with per-pattern candidate counts — intentionally minimal, not per-candidate logging. |
| 2026-09-12 | `chart-patterns scan` extended: `--all-symbols` (reads `data/all_symbols.csv`, 2,729 symbols — full-universe scan for one pattern completes in ~9s with `--no-save-charts`), `--pattern all` (scans every registered pattern via new `list_registered_patterns()`), CSV output under `output/scans/` (one row per candidate), and `--quiet` for large scans. CSV/chart filenames follow `<symbol-or-count>_<pattern-or-mul_pattern>.{csv,png}`. |
| 2026-09-12 | Double Bottom and Head and Shoulders implemented (tasks 6.2, 6.3 → Done): `find_double_bottom_candidates` (structurally parallel to double top, not a price-negation trick) and `find_head_and_shoulders_candidates` (5-pivot, no forced time symmetry, 0.4/0.35/0.25-weighted confidence). New configs `DoubleBottomConfig`/`HeadAndShouldersConfig`. Verified against real `candle_db` data via `chart-patterns scan --pattern ...`; a zoomed QA chart confirmed a textbook head-and-shoulders shape on `21STCENMGM`. |
| 2026-09-11 | Added `chart-patterns scan SYMBOL... [--start] [--end] [--pattern] [--min-confidence]` CLI (task 9.2, in progress): runs the real pipeline against `candle_db`, prints ranked candidates with full pivot/metric detail for manual verification, and saves a QA chart per symbol. This is a manual-verification tool, not the labeled-dataset backtest harness in task 8. |
| 2026-09-11 | Double Top pattern matcher implemented (tasks 5.1–5.4, 6.1 → Done): `Candidate` model, pattern registry, `find_double_top_candidates` with a weighted confidence score, unit + integration tests, and a real-data scan (5,801 candidates across 200 symbols at default tolerances) with a QA chart. `plot_pivots` now overlays candidate spans (task 10.1 → Done). Overlapping-candidate dedup (5.5, 7.3) deliberately deferred. |
| 2026-09-11 | Pivot/extrema detection implemented (task 4 → Done): `zigzag_pivots` (primary/default) and `find_local_extrema` (for future Savgol/kernel-regression smoothers), unified behind `detect_pivots()`; `plot_pivots` QA visualization built alongside (task 10.1, partial). Verified against real `ANIKINDS-BE` history, not just synthetic data. |
