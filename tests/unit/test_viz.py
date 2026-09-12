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


def test_plot_pivots_handles_zero_pivots(tmp_path):
    # Regression test: a flat/near-flat series (e.g. a low-volatility liquid
    # fund) can legitimately produce zero pivots. mpf.plot rejects an explicit
    # addplot=None (must be omitted, not None, when there's nothing to plot) —
    # this crashed in practice on a real symbol before being fixed.
    index = pd.date_range("2025-01-01", periods=20, freq="D")
    close = pd.Series([100.0] * 20, index=index)
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1000.0},
        index=index,
    )
    pivots = zigzag_pivots(df["close"], threshold_pct=5)
    assert pivots == []

    save_path = tmp_path / "flat.png"
    plot_pivots(df, pivots, save_path=str(save_path))

    assert save_path.exists()
    assert save_path.stat().st_size > 0
