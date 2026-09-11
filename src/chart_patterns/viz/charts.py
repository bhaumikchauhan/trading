import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd

from ..patterns.models import Candidate
from ..pivots.models import Pivot


def plot_pivots(
    df: pd.DataFrame,
    pivots: list[Pivot],
    *,
    candidates: list[Candidate] | None = None,
    title: str | None = None,
    save_path: str | None = None,
):
    """Render a candlestick chart with detected pivots (and, optionally, matched
    pattern candidates) overlaid, for manual QA. `df` must be in the canonical
    OHLCV shape (DatetimeIndex, lowercase open/high/low/close/volume columns) and
    `pivots`/`candidates` must have been detected from a series positionally
    aligned with `df` (each Pivot.index is used as a row position into `df`).
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

    plot_kwargs = {
        "type": "candle",
        "style": "yahoo",
        "addplot": addplots or None,
        # This project's charts are routinely multi-year daily history; mplfinance's
        # density warning would fire on nearly every real (non-test) call otherwise.
        "warn_too_much_data": len(plot_df) + 1,
    }
    if title is not None:
        plot_kwargs["title"] = title

    fig, axes = mpf.plot(plot_df, returnfig=True, **plot_kwargs)
    if candidates:
        price_ax = axes[0]
        for candidate in candidates:
            price_ax.axvspan(
                candidate.start_index, candidate.end_index, color="orange", alpha=0.15
            )
            price_ax.annotate(
                f"{candidate.pattern_type} ({candidate.confidence_score:.2f})",
                xy=((candidate.start_index + candidate.end_index) / 2, candidate.pivots[0].price),
                xytext=(0, 10),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color="darkorange",
            )

    if save_path:
        fig.savefig(save_path)
    plt.close(fig)
    return fig
