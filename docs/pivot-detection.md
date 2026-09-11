# Pivot / Extrema Detection — Implementation Deep Dive

This is a reference document, not a living/status doc like
[functional-spec.md](functional-spec.md) or [technical-spec.md](technical-spec.md).
It exists to explain, in detail, how `src/chart_patterns/pivots/` and
`src/chart_patterns/viz/charts.py` actually work — the algorithms, every
class/function, their edge cases, and why each design choice was made. If the
code changes, this doc should be updated alongside it, but it won't be
reorganized as a task tracker the way the other two docs are.

## 1. What this module does and why

Every pattern in this project (double top, head & shoulders, cup & handle, …) is
defined in terms of a short sequence of turning points — peaks and troughs —
not the raw bar-by-bar price series. A head and shoulders top, for instance, is
just "peak, trough, higher peak, trough, peak" with some height/time
constraints. Before any pattern rule can run, the raw OHLCV series has to be
collapsed down to that compact sequence of turning points. That collapsing step
is what this module does.

The output of every function here is the same shape: a `list[Pivot]`, ordered by
position, strictly alternating `peak`/`trough`. That invariant (strict
alternation, ordered by position) is what every future pattern matcher in
`src/chart_patterns/patterns/` will be written against, so it's enforced here
once rather than re-checked in every pattern.

## 2. Module layout

| File | Contains | Role |
|---|---|---|
| `pivots/models.py` | `Pivot` | The one data structure everything else in this module produces and consumes |
| `pivots/zigzag.py` | `zigzag_pivots()` | Default/primary pivot detector — percentage-threshold swing detection directly on a price series |
| `pivots/extrema.py` | `find_local_extrema()`, `_enforce_alternation()` | Neighbor-comparison pivot detector for already-smoothed continuous series (Savitzky-Golay / kernel regression, not yet built) |
| `pivots/detector.py` | `detect_pivots()` | Single dispatch entry point pattern matchers call, so they don't need to know which algorithm is behind a given method name |
| `pivots/__init__.py` | re-exports | `Pivot`, `detect_pivots`, `zigzag_pivots`, `find_local_extrema` |
| `viz/charts.py` | `plot_pivots()` | Renders a candlestick chart with detected pivots marked, for visually sanity-checking the above against real data |

## 3. The `Pivot` class

```python
class Pivot(BaseModel):
    index: int
    timestamp: datetime
    price: float
    type: Literal["peak", "trough"]
```

A Pydantic model, matching the rest of the project's convention of validating
data at module boundaries (config, domain models) rather than trusting raw
dicts/tuples everywhere.

| Field | Meaning |
|---|---|
| `index` | **Positional** (0-based) location of this pivot within whatever `pandas.Series` it was detected from — *not* a timestamp or a DataFrame `.loc` label. This is deliberate: pattern rules need to reason about bar-count separation (e.g. `DoubleTopConfig.max_time_separation_bars`), which is a positional/integer concept, not a calendar one. |
| `timestamp` | The actual date/time of that bar, carried along for display, filtering, and output — pulled from `series.index[pos]`. |
| `price` | The price value at the pivot (whatever series was passed in — typically `close`). |
| `type` | `"peak"` or `"trough"`. Pydantic's `Literal` means constructing a `Pivot` with any other string raises a validation error immediately, rather than a typo like `"Peak"` silently breaking every downstream comparison. |

Because `type` is constrained to exactly two values and every detector below
guarantees alternation, a `list[Pivot]` always reads like
`peak, trough, peak, trough, …` or `trough, peak, trough, …` — never two of the
same type in a row.

## 4. `zigzag_pivots()` — the default detector

### 4.1 The core idea

ZigZag doesn't smooth the series and then look for turning points as a second
step — it *is* the turning-point detector. It walks through the price series
tracking a "current swing," and only confirms a pivot once price has reversed
by at least `threshold_pct` away from the current extreme of that swing. Until
that reversal happens, the extreme keeps sliding forward as new, more extreme
prices arrive.

This has a direct, sometimes counter-intuitive consequence: **the most recent
extreme in the data is usually not reported as a pivot**, because it hasn't
been confirmed yet — price hasn't reversed away from it by the threshold. This
is correct behavior, not a bug: you genuinely cannot know a high is "the" swing
high until price has come down from it by a meaningful amount.

### 4.2 Why it lives in two phases

The function has two loops because the very first pivot is a special case: at
the start of the series, there is no "current swing direction" yet to measure a
reversal against. So:

- **Phase 1 (bootstrap)** — runs from bar 1 until price has moved
  `threshold_pct` away from either the running minimum or running maximum seen
  since bar 0. Whichever extreme triggers that first breakout *is* the first
  confirmed pivot (a trough if price broke out upward, a peak if it broke out
  downward). This phase can also end with **no** pivots at all, if price never
  moves far enough from its start to break out (e.g. a flat or barely-moving
  series) — in that case the function returns an empty list.
- **Phase 2 (steady state)** — once a direction is established, this is the
  "normal" ZigZag loop: keep extending the current extreme while price moves
  further in the current direction; confirm a pivot and flip direction the
  moment price reverses by `threshold_pct` from that extreme.

### 4.3 Walking through the actual code

```python
if threshold_pct <= 0:
    raise ValueError("threshold_pct must be positive")
```
A non-positive threshold has no sane meaning (it would confirm a pivot on every
single bar, or never at all for zero), so it's rejected immediately rather than
silently producing nonsense output.

**Phase 1**, for each bar `i` from 1 onward:
```python
if price > running_max_price:
    running_max_pos, running_max_price = i, price
if price < running_min_price:
    running_min_pos, running_min_price = i, price

up_pct = (price - running_min_price) / running_min_price * 100
down_pct = (running_max_price - price) / running_max_price * 100
triggered_up = up_pct >= threshold_pct and running_min_pos < i
triggered_down = down_pct >= threshold_pct and running_max_pos < i
```
`up_pct` asks "how far has price rallied off the lowest point seen so far?";
`down_pct` asks the mirror question off the highest point. The `running_min_pos
< i` / `running_max_pos < i` guards exist so that a bar which *is itself* the
new running extreme can't trigger against its own value (that would always be a
0% move and is meaningless).

```python
if triggered_up and triggered_down:
    if running_min_pos > running_max_pos:
        triggered_down = False
    else:
        triggered_up = False
```
It's possible (if the series has swung widely) for both conditions to be true
on the same bar. The tie-break picks whichever extreme was set **more
recently** — the reasoning being that price must have touched the more recent
extreme last, so that's the one it's actually reversing away from right now.

Once one direction triggers, that extreme is appended as the first `Pivot` and
the loop breaks into phase 2:
```python
if triggered_up:
    direction = "up"
    pivots.append(make_pivot(running_min_pos, running_min_price, "trough"))
    extreme_pos, extreme_price = i, price
    break
```

**Phase 2**, once direction is known:
```python
if direction == "up":
    if price >= extreme_price:
        extreme_pos, extreme_price = i, price
    elif (extreme_price - price) / extreme_price * 100 >= threshold_pct:
        pivots.append(make_pivot(extreme_pos, extreme_price, "peak"))
        direction = "down"
        extreme_pos, extreme_price = i, price
```
While trending up, every new high becomes the new candidate extreme. The moment
price has dropped `threshold_pct` off that candidate, the candidate is locked
in as a confirmed peak, direction flips to `"down"`, and the current bar
becomes the new (trough) candidate extreme. The `else` branch mirrors this for
a downtrend confirming a trough.

### 4.4 Worked example (this is the exact case covered by the unit tests)

Input series (threshold = 5%):

```
idx:   0    1    2    3    4    5    6    7    8    9   10   11   12   13   14   15   16   17   18   19   20   21   22
price: 100  105  110  115  120  115  110  105  100  95   100  105  110  115  120  125  130  125  120  115  110  105  100
```

Trace:
- Bars 0→1: price rises to 105, which is +5.0% off the running min (100 at bar
  0) → **breakout confirmed immediately at bar 1**. The running min (bar 0,
  price 100) becomes the first pivot: **trough @ index 0, price 100**.
  Direction = up, extreme = bar 1 (105).
- Bars 2–4: price keeps rising (110, 115, 120) — extreme keeps advancing to bar
  4, price 120.
- Bar 5: price drops to 115 — that's only a 4.17% pullback from 120, below the
  5% threshold, so nothing confirms yet; the extreme candidate stays at bar 4.
- Bar 6: price is 110 — an 8.33% pullback from 120 → **confirmed: peak @ index
  4, price 120**. Direction flips to down, new extreme = bar 6 (110).
- Bars 7–9: price keeps falling (105, 100, 95) — extreme advances to bar 9,
  price 95.
- Bar 10: price rallies to 100 — a 5.26% rally off 95 → **confirmed: trough @
  index 9, price 95**. Direction flips to up, new extreme = bar 10 (100).
- Bars 11–16: price climbs all the way to 130 (bar 16) — extreme keeps
  advancing.
- Bar 17: price is 125 — only a 3.85% pullback from 130, not enough.
- Bar 18: price is 120 — a 7.69% pullback from 130 → **confirmed: peak @ index
  16, price 130**. Direction flips to down, new extreme = bar 18 (120).
- Bars 19–22: price keeps falling to 100 but never rallies back — the series
  ends with this swing **unconfirmed**, so no fifth pivot is emitted.

Final result:
```
(0, 100.0, trough), (4, 120.0, peak), (9, 95.0, trough), (16, 130.0, peak)
```

This exact sequence is asserted in
`tests/unit/test_pivots.py::test_zigzag_pivots_alternate_and_match_hand_traced_expectation`.
It was also visually confirmed by running `zigzag_pivots` against real
`ANIKINDS-BE` history and rendering it with `plot_pivots` — the markers land
exactly on the visible swing highs/lows in the candlestick chart.

### 4.5 Edge cases handled

| Case | Behavior |
|---|---|
| `threshold_pct <= 0` | Raises `ValueError` immediately |
| Empty series | Returns `[]` |
| Flat series (price never moves) | Phase 1 never breaks out → returns `[]` |
| Both up/down breakout trigger on the same bar (phase 1 only) | Resolved by recency tie-break (§4.3) |
| Trailing/most-recent swing not yet reversed | Correctly left unconfirmed and omitted — this is how ZigZag is supposed to behave, not a bug |

## 5. `find_local_extrema()` — for smoothed continuous series

This is a different algorithm for a different situation: it doesn't use a
percentage threshold at all. It compares each point to its `order` neighbors on
each side and calls it a peak/trough if it's strictly greater/less than all of
them (via `scipy.signal.argrelextrema`).

This only makes sense once the series has already been smoothed (Savitzky-Golay
or kernel regression, per `smoothing/`, not yet built) — on raw, noisy price,
neighbor-comparison would flag an enormous number of one-bar wiggles as
"pivots." It exists now, ahead of those smoothers, so the pivot layer's public
interface (`detect_pivots(method=...)`) is already stable before those
smoothers are wired in.

```python
peak_positions = argrelextrema(values, np.greater, order=order)[0]
trough_positions = argrelextrema(values, np.less, order=order)[0]
```
Two independent passes — one for strict local maxima, one for strict local
minima — are merged and sorted by position.

### 5.1 `_enforce_alternation()` — the plateau edge case

Because `find_local_extrema` finds peaks and troughs independently, it's
possible (near a plateau or a double-top-shaped bump in the smoothed line) to
get two peaks in a row with no trough between them, which violates the
alternation invariant every pattern matcher depends on. `_enforce_alternation`
walks the merged, sorted list and, whenever two consecutive pivots share a
type, keeps only the more extreme one (the higher of two peaks, the lower of
two troughs) and drops the other:

```python
if pivot.type == result[-1].type:
    is_more_extreme = (
        pivot.price > result[-1].price if pivot.type == "peak"
        else pivot.price < result[-1].price
    )
    if is_more_extreme:
        result[-1] = pivot
else:
    result.append(pivot)
```

`zigzag_pivots` never needs this — by construction, it can only ever confirm a
peak after a trough and vice versa, so alternation is automatic there.

## 6. `detect_pivots()` — the unified entry point

```python
def detect_pivots(series: pd.Series, method: str = "zigzag", **kwargs) -> list[Pivot]:
    if method == "zigzag":
        return zigzag_pivots(series, threshold_pct=kwargs["threshold_pct"])
    if method == "extrema":
        return find_local_extrema(series, order=kwargs.get("order", 3))
    raise ValueError(f"Unknown pivot detection method: {method!r}")
```

This is intentionally a thin dispatcher, not a `Protocol`/strategy-class
hierarchy — there are only two algorithms and their parameter shapes differ
(`threshold_pct` vs. `order`), so a simple `if/elif` on a method-name string is
more readable than an abstraction with only two implementations. Every future
pattern matcher will call `detect_pivots(...)`, not `zigzag_pivots`/
`find_local_extrema` directly, so the method actually in use is a config
concern, not something baked into each pattern.

## 7. `plot_pivots()` — visual QA

```python
def plot_pivots(df, pivots, *, title=None, save_path=None):
```

Lives in `viz/charts.py`. Given an OHLCV `DataFrame` (canonical shape:
`DatetimeIndex`, lowercase `open/high/low/close/volume` columns) and the
`list[Pivot]` detected from a series positionally aligned with that same
`DataFrame`, it renders an `mplfinance` candlestick chart with:

- a red downward triangle (`▽`... rendered as `v` marker) at every peak
- a green upward triangle (`^`) at every trough

Implementation notes:
- `matplotlib.use("Agg")` is set at import time. This project's use of this
  function is producing PNGs for QA/CLI output, not interactive windows, so a
  non-interactive backend avoids any dependency on a display/Tk being
  available (relevant for CI and headless runs).
- Peak/trough markers are built as two full-length `pd.Series` of `NaN`, with
  the pivot's price written in at `pivot.index` (`peak_markers.iloc[pivot.index]
  = pivot.price`) — this is exactly why `Pivot.index` is a **positional**
  integer rather than a timestamp: `.iloc` needs a position, and it has to line
  up with the row position in `df`, which only works if the series `pivots`
  was detected from is the same series (or positionally aligned with) `df`.
  Passing a `df` that isn't aligned with what pivots were detected from will
  silently plot markers on the wrong bars.
- Only the marker series that actually has at least one non-NaN value gets
  added to the plot (`if peak_markers.notna().any()`), so a chart with only
  troughs (e.g. mid-swing) doesn't render an empty, warning-triggering overlay.

This was built now (ahead of functional-spec's original §10 schedule) because
it was the fastest way to actually verify `zigzag_pivots` against real data —
and doing so caught a real bug (see commit history / technical-spec change
log): an early version never confirmed the very first swing point as a pivot.

## 8. How this feeds into pattern matching (what comes next)

Every pattern matcher in the upcoming `src/chart_patterns/patterns/` package
will have the shape (per technical-spec §9):

```python
def find_candidates(pivots: list[Pivot], config: PatternConfig) -> list[Candidate]
```

They will never see raw OHLCV data or care which detector produced the pivots
— only the alternating `list[Pivot]` this module guarantees. For example, a
double top is just: find `peak, trough, peak` in the list where the two peak
prices are within `DoubleTopConfig.height_similarity_pct` of each other, the
trough is at least `min_trough_depth_pct` below them, and the bar distance
between the two peaks (`peak2.index - peak1.index`) falls between
`min_time_separation_bars` and `max_time_separation_bars`.

## 9. Tests

| Test | What it proves |
|---|---|
| `test_zigzag_pivots_alternate_and_match_hand_traced_expectation` | The full worked example in §4.4, asserted exactly |
| `test_zigzag_pivots_rejects_non_positive_threshold` | Input validation |
| `test_zigzag_pivots_empty_series_returns_empty_list` | Empty-input edge case |
| `test_zigzag_pivots_flat_series_has_no_confirmed_pivots` | No-breakout edge case |
| `test_find_local_extrema_on_simple_wave` | Basic neighbor-comparison correctness |
| `test_enforce_alternation_keeps_more_extreme_of_consecutive_same_type` | The plateau edge case in §5.1 |
| `test_detect_pivots_dispatches_to_zigzag` / `_extrema` / `_rejects_unknown_method` | The dispatcher in §6 |
| `test_plot_pivots_saves_a_file` | `plot_pivots` runs end-to-end and produces a non-empty file |

Run with: `uv run pytest tests/unit/test_pivots.py tests/unit/test_viz.py -v`
