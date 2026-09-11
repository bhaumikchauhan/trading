import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd

from ..pivots.models import Pivot


def plot_pivots(
    df: pd.DataFrame,
    pivots: list[Pivot],
    *,
    title: str | None = None,
    save_path: str | None = None,
):
    """Render a candlestick chart with detected pivots overlaid, for manual QA of
    pivot detection. `df` must be in the canonical OHLCV shape (DatetimeIndex,
    lowercase open/high/low/close/volume columns) and `pivots` must have been
    detected from a series positionally aligned with `df` (each Pivot.index is
    used as a row position into `df`).
    """
    plot_df = df.rename(columns=str.capitalize)[["Open", "High", "Low", "Close", "Volume"]]

    peak_markers = pd.Series(np.nan, index=plot_df.index)
    trough_markers = pd.Series(np.nan, index=plot_df.index)
    for pivot in pivots:
        if pivot.type == "peak":
            peak_markers.iloc[pivot.index] = pivot.price
        else:
            trough_markers.iloc[pivot.index] = pivot.price

    addplots = []
    if peak_markers.notna().any():
        addplots.append(
            mpf.make_addplot(peak_markers, type="scatter", markersize=80, marker="v", color="red")
        )
    if trough_markers.notna().any():
        addplots.append(
            mpf.make_addplot(
                trough_markers, type="scatter", markersize=80, marker="^", color="green"
            )
        )

    fig, _ = mpf.plot(
        plot_df,
        type="candle",
        style="yahoo",
        addplot=addplots or None,
        title=title,
        returnfig=True,
    )
    if save_path:
        fig.savefig(save_path)
    plt.close(fig)
    return fig
