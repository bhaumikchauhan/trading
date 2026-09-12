import pandas as pd


def average_true_range(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Rolling Average True Range over `df`'s high/low/close columns.

    True Range accounts for gaps (not just the current bar's high-low) by also
    comparing against the previous close; the first bar has no previous close,
    so it falls back to a plain high-low range.
    """
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean()


def atr_threshold_pct(df: pd.DataFrame, period: int = 14, multiplier: float = 2.0) -> float:
    """A single volatility-scaled ZigZag threshold_pct for this symbol: `multiplier`
    times the median ATR-as-a-percentage-of-close over the given history.

    Using the median (not the latest value or the mean) keeps the threshold
    representative of the symbol's typical volatility across the whole window
    rather than reacting to one recent spike or a single quiet patch.
    """
    atr = average_true_range(df, period=period)
    atr_pct = ((atr / df["close"]) * 100).dropna()
    if atr_pct.empty:
        raise ValueError(f"Not enough bars ({len(df)}) to compute a {period}-period ATR")
    return float(atr_pct.median()) * multiplier
