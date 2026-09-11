from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from chart_patterns.config.models import DoubleTopConfig
from chart_patterns.patterns import Candidate, find_candidates, find_double_top_candidates
from chart_patterns.pivots.models import Pivot

CONFIG = DoubleTopConfig(
    height_similarity_pct=3.0,
    min_trough_depth_pct=2.0,
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


def test_finds_clear_double_top():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(10, 90.0, "trough"),
        _pivot(20, 100.5, "peak"),
    ]

    candidates = find_double_top_candidates(pivots, CONFIG)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern_type == "double_top"
    assert candidate.pivots == pivots
    assert candidate.start_index == 0
    assert candidate.end_index == 20
    assert 0.0 <= candidate.confidence_score <= 1.0


def test_identical_peaks_and_deep_trough_score_near_maximum():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(10, 80.0, "trough"),  # 20% deep, far past the 2% minimum -> depth score caps at 1.0
        _pivot(20, 100.0, "peak"),  # identical heights -> height score is exactly 1.0
    ]

    candidates = find_double_top_candidates(pivots, CONFIG)

    assert len(candidates) == 1
    assert candidates[0].confidence_score == 1.0


def test_rejects_peaks_too_different_in_height():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(10, 90.0, "trough"),
        _pivot(20, 110.0, "peak"),  # 10% taller, past the 3% tolerance
    ]

    assert find_double_top_candidates(pivots, CONFIG) == []


def test_rejects_trough_too_shallow():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(10, 99.5, "trough"),  # 0.5% deep, below the 2% minimum
        _pivot(20, 100.0, "peak"),
    ]

    assert find_double_top_candidates(pivots, CONFIG) == []


def test_rejects_peaks_too_close_together():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(2, 90.0, "trough"),
        _pivot(4, 100.0, "peak"),  # only 4 bars apart, below the 5-bar minimum
    ]

    assert find_double_top_candidates(pivots, CONFIG) == []


def test_rejects_peaks_too_far_apart():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(60, 90.0, "trough"),
        _pivot(130, 100.0, "peak"),  # 130 bars apart, above the 120-bar maximum
    ]

    assert find_double_top_candidates(pivots, CONFIG) == []


def test_ignores_trough_peak_trough_window():
    pivots = [
        _pivot(0, 90.0, "trough"),
        _pivot(10, 100.0, "peak"),
        _pivot(20, 90.0, "trough"),
    ]

    assert find_double_top_candidates(pivots, CONFIG) == []


def test_overlapping_windows_each_produce_a_candidate():
    # peak-trough-peak-trough-peak: two valid double-top windows share the middle peak.
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(10, 90.0, "trough"),
        _pivot(20, 100.0, "peak"),
        _pivot(30, 90.0, "trough"),
        _pivot(40, 100.0, "peak"),
    ]

    candidates = find_double_top_candidates(pivots, CONFIG)

    assert len(candidates) == 2
    assert [c.start_index for c in candidates] == [0, 20]


def test_registry_dispatch_matches_direct_call():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(10, 90.0, "trough"),
        _pivot(20, 100.5, "peak"),
    ]

    assert find_candidates("double_top", pivots, CONFIG) == find_double_top_candidates(
        pivots, CONFIG
    )


def test_registry_rejects_unknown_pattern():
    with pytest.raises(ValueError, match="No pattern matcher registered"):
        find_candidates("not_a_real_pattern", [], CONFIG)


def test_candidate_rejects_empty_pivots():
    with pytest.raises(ValidationError, match="at least one pivot"):
        Candidate(pattern_type="double_top", pivots=[], confidence_score=0.5)


def test_candidate_rejects_out_of_range_confidence():
    pivot = _pivot(0, 100.0, "peak")
    with pytest.raises(ValidationError):
        Candidate(pattern_type="double_top", pivots=[pivot], confidence_score=1.5)
