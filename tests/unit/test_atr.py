import pandas as pd
import pytest

from chart_patterns.smoothing import atr_threshold_pct, average_true_range

# Hand-computed True Range per bar:
#   bar0: high-low=2 (no prev close)               -> TR=2
#   bar1: max(12-9, |12-9|, |9-9|)   = max(3,3,0)   -> TR=3
#   bar2: max(11-9, |11-11|, |9-11|) = max(2,0,2)   -> TR=2
#   bar3: max(13-10, |13-10|, |10-10|) = max(3,3,0) -> TR=3
#   bar4: max(14-11, |14-12|, |11-12|) = max(3,2,1) -> TR=3
# 3-period rolling mean (min_periods=3): [NaN, NaN, 2.333, 2.667, 2.667]
HIGH = [10, 12, 11, 13, 14]
LOW = [8, 9, 9, 10, 11]
CLOSE = [9, 11, 10, 12, 13]


def _ohlc_df(high=HIGH, low=LOW, close=CLOSE) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(high), freq="D")
    return pd.DataFrame({"high": high, "low": low, "close": close}, index=index, dtype=float)


def test_average_true_range_matches_hand_computed_values():
    atr = average_true_range(_ohlc_df(), period=3)

    assert atr.iloc[:2].isna().all()
    assert atr.iloc[2] == pytest.approx(2.3333, abs=1e-3)
    assert atr.iloc[3] == pytest.approx(2.6667, abs=1e-3)
    assert atr.iloc[4] == pytest.approx(2.6667, abs=1e-3)


def test_atr_threshold_pct_is_median_atr_pct_times_multiplier():
    # ATR% at the 3 valid bars: 2.333/10*100=23.33, 2.667/12*100=22.22, 2.667/13*100=20.51
    # median = 22.22
    threshold = atr_threshold_pct(_ohlc_df(), period=3, multiplier=1.0)
    assert threshold == pytest.approx(22.22, abs=0.05)

    doubled = atr_threshold_pct(_ohlc_df(), period=3, multiplier=2.0)
    assert doubled == pytest.approx(threshold * 2, abs=1e-6)


def test_atr_threshold_pct_raises_when_not_enough_bars():
    short_df = _ohlc_df(high=HIGH[:2], low=LOW[:2], close=CLOSE[:2])
    with pytest.raises(ValueError, match="Not enough bars"):
        atr_threshold_pct(short_df, period=3, multiplier=1.0)


def test_higher_volatility_series_produces_higher_threshold():
    calm = _ohlc_df()
    volatile_high = [h * 1.5 for h in HIGH]
    volatile_low = [low_ * 0.5 for low_ in LOW]
    volatile = _ohlc_df(high=volatile_high, low=volatile_low, close=CLOSE)

    assert atr_threshold_pct(volatile, period=3) > atr_threshold_pct(calm, period=3)
