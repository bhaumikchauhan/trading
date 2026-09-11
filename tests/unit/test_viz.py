import pandas as pd

from chart_patterns.pivots import zigzag_pivots
from chart_patterns.viz import plot_pivots

VALUES = [
    100, 105, 110, 115, 120, 115, 110, 105, 100, 95,
    100, 105, 110, 115, 120, 125, 130, 125, 120, 115,
    110, 105, 100,
]


def _ohlcv_df() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(VALUES), freq="D")
    close = pd.Series(VALUES, index=index, dtype=float)
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


def test_plot_pivots_saves_a_file(tmp_path):
    df = _ohlcv_df()
    pivots = zigzag_pivots(df["close"], threshold_pct=5)

    save_path = tmp_path / "chart.png"
    plot_pivots(df, pivots, title="test", save_path=str(save_path))

    assert save_path.exists()
    assert save_path.stat().st_size > 0
