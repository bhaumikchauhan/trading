import pandas as pd
import pytest

from chart_patterns.pivots import Pivot, detect_pivots, find_local_extrema, zigzag_pivots
from chart_patterns.pivots.extrema import _enforce_alternation


def _series(values: list[float]) -> pd.Series:
    index = pd.date_range("2025-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=index)


# Hand-traced with threshold_pct=5: rises 100->120 (peak), falls to 95 (trough),
# rises to 130 (peak), then falls again without confirming a final trough (the
# trailing swing is correctly left unconfirmed).
ZIGZAG_VALUES = [
    100, 105, 110, 115, 120, 115, 110, 105, 100, 95,
    100, 105, 110, 115, 120, 125, 130, 125, 120, 115,
    110, 105, 100,
]


def test_zigzag_pivots_alternate_and_match_hand_traced_expectation():
    pivots = zigzag_pivots(_series(ZIGZAG_VALUES), threshold_pct=5)

    assert [(p.index, p.price, p.type) for p in pivots] == [
        (0, 100.0, "trough"),
        (4, 120.0, "peak"),
        (9, 95.0, "trough"),
        (16, 130.0, "peak"),
    ]


def test_zigzag_pivots_rejects_non_positive_threshold():
    with pytest.raises(ValueError, match="threshold_pct must be positive"):
        zigzag_pivots(_series(ZIGZAG_VALUES), threshold_pct=0)


def test_zigzag_pivots_empty_series_returns_empty_list():
    assert zigzag_pivots(_series([]), threshold_pct=5) == []


def test_zigzag_pivots_flat_series_has_no_confirmed_pivots():
    assert zigzag_pivots(_series([100] * 10), threshold_pct=5) == []


def test_find_local_extrema_on_simple_wave():
    values = [1, 2, 3, 2, 1, 0, -1, 0, 1, 2, 3, 2, 1]
    pivots = find_local_extrema(_series(values), order=1)

    assert [(p.index, p.type) for p in pivots] == [
        (2, "peak"),
        (6, "trough"),
        (10, "peak"),
    ]


def test_enforce_alternation_keeps_more_extreme_of_consecutive_same_type():
    index = pd.date_range("2025-01-01", periods=4, freq="D")
    pivots = [
        Pivot(index=0, timestamp=index[0], price=100, type="peak"),
        Pivot(index=1, timestamp=index[1], price=105, type="peak"),  # higher, should win
        Pivot(index=2, timestamp=index[2], price=90, type="trough"),
        Pivot(index=3, timestamp=index[3], price=95, type="trough"),  # higher, should lose
    ]

    result = _enforce_alternation(pivots)

    assert [(p.index, p.type) for p in result] == [(1, "peak"), (2, "trough")]


def test_detect_pivots_dispatches_to_zigzag():
    series = _series(ZIGZAG_VALUES)
    assert detect_pivots(series, method="zigzag", threshold_pct=5) == zigzag_pivots(
        series, threshold_pct=5
    )


def test_detect_pivots_dispatches_to_extrema():
    values = [1, 2, 3, 2, 1, 0, -1, 0, 1, 2, 3, 2, 1]
    series = _series(values)
    assert detect_pivots(series, method="extrema", order=1) == find_local_extrema(
        series, order=1
    )


def test_detect_pivots_rejects_unknown_method():
    with pytest.raises(ValueError, match="Unknown pivot detection method"):
        detect_pivots(_series(ZIGZAG_VALUES), method="not_a_method")
