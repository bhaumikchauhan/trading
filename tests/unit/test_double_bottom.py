from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from chart_patterns.config.models import DoubleBottomConfig
from chart_patterns.patterns import find_candidates, find_double_bottom_candidates
from chart_patterns.pivots.models import Pivot

CONFIG = DoubleBottomConfig(
    depth_similarity_pct=3.0,
    min_peak_prominence_pct=2.0,
    max_time_separation_bars=120,
    min_time_separation_bars=5,
)


def _pivot(index: int, price: float, pivot_type: str) -> Pivot:
    return Pivot(
        index=index,
        timestamp=datetime(2025, 1, 1) + timedelta(days=index),
        price=price,
        type=pivot_type,
    )


def test_finds_clear_double_bottom():
    pivots = [
        _pivot(0, 100.0, "trough"),
        _pivot(10, 110.0, "peak"),
        _pivot(20, 100.5, "trough"),
    ]

    candidates = find_double_bottom_candidates(pivots, CONFIG)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern_type == "double_bottom"
    assert candidate.pivots == pivots
    assert candidate.start_index == 0
    assert candidate.end_index == 20
    assert 0.0 <= candidate.confidence_score <= 1.0


def test_identical_troughs_and_prominent_peak_score_near_maximum():
    pivots = [
        _pivot(0, 100.0, "trough"),
        _pivot(10, 125.0, "peak"),  # 25% prominence, far past the 2% minimum -> caps at 1.0
        _pivot(20, 100.0, "trough"),  # identical depths -> depth score is exactly 1.0
    ]

    candidates = find_double_bottom_candidates(pivots, CONFIG)

    assert len(candidates) == 1
    assert candidates[0].confidence_score == 1.0


def test_rejects_troughs_too_different_in_depth():
    pivots = [
        _pivot(0, 100.0, "trough"),
        _pivot(10, 110.0, "peak"),
        _pivot(20, 90.0, "trough"),  # 10% lower, past the 3% tolerance
    ]

    assert find_double_bottom_candidates(pivots, CONFIG) == []


def test_rejects_peak_too_unprominent():
    pivots = [
        _pivot(0, 100.0, "trough"),
        _pivot(10, 100.5, "peak"),  # 0.5% prominence, below the 2% minimum
        _pivot(20, 100.0, "trough"),
    ]

    assert find_double_bottom_candidates(pivots, CONFIG) == []


def test_rejects_troughs_too_close_together():
    pivots = [
        _pivot(0, 100.0, "trough"),
        _pivot(2, 110.0, "peak"),
        _pivot(4, 100.0, "trough"),  # only 4 bars apart, below the 5-bar minimum
    ]

    assert find_double_bottom_candidates(pivots, CONFIG) == []


def test_rejects_troughs_too_far_apart():
    pivots = [
        _pivot(0, 100.0, "trough"),
        _pivot(60, 110.0, "peak"),
        _pivot(130, 100.0, "trough"),  # 130 bars apart, above the 120-bar maximum
    ]

    assert find_double_bottom_candidates(pivots, CONFIG) == []


def test_ignores_peak_trough_peak_window():
    pivots = [
        _pivot(0, 110.0, "peak"),
        _pivot(10, 100.0, "trough"),
        _pivot(20, 110.0, "peak"),
    ]

    assert find_double_bottom_candidates(pivots, CONFIG) == []


def test_overlapping_windows_each_produce_a_candidate():
    # trough-peak-trough-peak-trough: two valid double-bottom windows share the middle trough.
    pivots = [
        _pivot(0, 100.0, "trough"),
        _pivot(10, 110.0, "peak"),
        _pivot(20, 100.0, "trough"),
        _pivot(30, 110.0, "peak"),
        _pivot(40, 100.0, "trough"),
    ]

    candidates = find_double_bottom_candidates(pivots, CONFIG)

    assert len(candidates) == 2
    assert [c.start_index for c in candidates] == [0, 20]


def test_registry_dispatch_matches_direct_call():
    pivots = [
        _pivot(0, 100.0, "trough"),
        _pivot(10, 110.0, "peak"),
        _pivot(20, 100.5, "trough"),
    ]

    assert find_candidates("double_bottom", pivots, CONFIG) == find_double_bottom_candidates(
        pivots, CONFIG
    )


def test_config_rejects_inverted_time_separation():
    with pytest.raises(ValidationError, match="min_time_separation_bars must be less than"):
        DoubleBottomConfig(
            depth_similarity_pct=3.0,
            min_peak_prominence_pct=2.0,
            max_time_separation_bars=5,
            min_time_separation_bars=120,
        )
