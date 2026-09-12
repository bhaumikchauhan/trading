from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from chart_patterns.config.models import HeadAndShouldersConfig
from chart_patterns.patterns import find_candidates, find_head_and_shoulders_candidates
from chart_patterns.pivots.models import Pivot

CONFIG = HeadAndShouldersConfig(
    shoulder_height_similarity_pct=5.0,
    min_head_prominence_pct=3.0,
    max_neckline_slope_pct=5.0,
    max_time_separation_bars=180,
    min_time_separation_bars=10,
)


def _pivot(index: int, price: float, pivot_type: str) -> Pivot:
    return Pivot(
        index=index,
        timestamp=datetime(2025, 1, 1) + timedelta(days=index),
        price=price,
        type=pivot_type,
    )


def _clear_pattern() -> list[Pivot]:
    return [
        _pivot(0, 100.0, "peak"),  # left shoulder
        _pivot(10, 90.0, "trough"),  # left neckline point
        _pivot(20, 110.0, "peak"),  # head
        _pivot(30, 91.0, "trough"),  # right neckline point
        _pivot(40, 100.5, "peak"),  # right shoulder
    ]


def test_finds_clear_head_and_shoulders():
    pivots = _clear_pattern()

    candidates = find_head_and_shoulders_candidates(pivots, CONFIG)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern_type == "head_and_shoulders"
    assert candidate.pivots == pivots
    assert candidate.start_index == 0
    assert candidate.end_index == 40
    assert 0.0 <= candidate.confidence_score <= 1.0


def test_identical_shoulders_and_flat_neckline_and_prominent_head_score_near_maximum():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(10, 80.0, "trough"),
        _pivot(20, 130.0, "peak"),  # very prominent head -> caps at 1.0
        _pivot(30, 80.0, "trough"),  # identical neckline troughs -> neckline score 1.0
        _pivot(40, 100.0, "peak"),  # identical shoulders -> shoulder score 1.0
    ]

    candidates = find_head_and_shoulders_candidates(pivots, CONFIG)

    assert len(candidates) == 1
    assert candidates[0].confidence_score == 1.0


def test_rejects_shoulders_too_different_in_height():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(10, 90.0, "trough"),
        # Head stays comfortably above both shoulders (so this isn't caught by the
        # head-prominence check first) while the shoulders themselves differ by 20%,
        # past the 5% tolerance.
        _pivot(20, 130.0, "peak"),
        _pivot(30, 91.0, "trough"),
        _pivot(40, 120.0, "peak"),
    ]

    assert find_head_and_shoulders_candidates(pivots, CONFIG) == []


def test_rejects_head_not_prominent_enough():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(10, 90.0, "trough"),
        _pivot(20, 101.0, "peak"),  # only 1% above the shoulders, below the 3% minimum
        _pivot(30, 91.0, "trough"),
        _pivot(40, 100.5, "peak"),
    ]

    assert find_head_and_shoulders_candidates(pivots, CONFIG) == []


def test_rejects_steep_neckline():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(10, 70.0, "trough"),
        _pivot(20, 110.0, "peak"),
        _pivot(30, 91.0, "trough"),  # 30% above the left trough, past the 5% tolerance
        _pivot(40, 100.5, "peak"),
    ]

    assert find_head_and_shoulders_candidates(pivots, CONFIG) == []


def test_rejects_span_too_short():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(2, 90.0, "trough"),
        _pivot(4, 110.0, "peak"),
        _pivot(6, 91.0, "trough"),
        _pivot(8, 100.5, "peak"),  # only 8 bars span, below the 10-bar minimum
    ]

    assert find_head_and_shoulders_candidates(pivots, CONFIG) == []


def test_rejects_span_too_long():
    pivots = [
        _pivot(0, 100.0, "peak"),
        _pivot(50, 90.0, "trough"),
        _pivot(100, 110.0, "peak"),
        _pivot(150, 91.0, "trough"),
        _pivot(200, 100.5, "peak"),  # 200 bars span, above the 180-bar maximum
    ]

    assert find_head_and_shoulders_candidates(pivots, CONFIG) == []


def test_ignores_window_with_wrong_pivot_types():
    pivots = [
        _pivot(0, 90.0, "trough"),
        _pivot(10, 100.0, "peak"),
        _pivot(20, 80.0, "trough"),
        _pivot(30, 100.0, "peak"),
        _pivot(40, 90.0, "trough"),
    ]

    assert find_head_and_shoulders_candidates(pivots, CONFIG) == []


def test_registry_dispatch_matches_direct_call():
    pivots = _clear_pattern()

    assert find_candidates(
        "head_and_shoulders", pivots, CONFIG
    ) == find_head_and_shoulders_candidates(pivots, CONFIG)


def test_config_rejects_inverted_time_separation():
    with pytest.raises(ValidationError, match="min_time_separation_bars must be less than"):
        HeadAndShouldersConfig(
            shoulder_height_similarity_pct=5.0,
            min_head_prominence_pct=3.0,
            max_neckline_slope_pct=5.0,
            max_time_separation_bars=10,
            min_time_separation_bars=180,
        )
