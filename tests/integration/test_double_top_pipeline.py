import pandas as pd
import pytest

from chart_patterns.config.models import DoubleTopConfig
from chart_patterns.patterns import find_candidates
from chart_patterns.pivots import zigzag_pivots
from chart_patterns.viz import plot_pivots

# Hand-traced with threshold_pct=5 (see docs/pivot-detection.md §4.4 for the method):
# trough@0(100) -> peak@4(120) -> trough@9(95) -> peak@15(121), trailing swing unconfirmed.
# Peaks 4 and 15 are within 1% of each other with a >20%-deep trough between them: a
# textbook double top.
CLOSE_VALUES = [
    100, 105, 110, 115, 120, 115, 110, 105, 100, 95,
    100, 105, 110, 115, 120, 121, 115, 110, 105, 100, 95,
]

CONFIG = DoubleTopConfig(
    height_similarity_pct=3.0,
    min_trough_depth_pct=2.0,
    max_time_separation_bars=120,
    min_time_separation_bars=5,
)


def _ohlcv_df() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(CLOSE_VALUES), freq="D")
    close = pd.Series(CLOSE_VALUES, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000.0,
        },
        index=index,
    )


def test_full_pipeline_detects_double_top_from_ohlcv(tmp_path):
    df = _ohlcv_df()

    pivots = zigzag_pivots(df["close"], threshold_pct=5.0)
    assert [(p.index, p.type) for p in pivots] == [
        (0, "trough"),
        (4, "peak"),
        (9, "trough"),
        (15, "peak"),
    ]

    candidates = find_candidates("double_top", pivots, CONFIG)
    assert len(candidates) == 1

    candidate = candidates[0]
    assert candidate.start_index == 4
    assert candidate.end_index == 15
    # height_score = 1 - 0.8333/3.0 = 0.7222; depth_score caps at 1.0 (21.5% deep, well past
    # the 2% minimum); confidence = 0.6*0.7222 + 0.4*1.0.
    assert candidate.confidence_score == pytest.approx(0.8333, abs=1e-4)

    save_path = tmp_path / "double_top.png"
    plot_pivots(df, pivots, candidates=candidates, save_path=str(save_path))
    assert save_path.exists()
