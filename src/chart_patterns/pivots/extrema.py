from typing import Literal

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

from .models import Pivot


def find_local_extrema(series: pd.Series, order: int = 3) -> list[Pivot]:
    """Find local peaks/troughs on an already-smoothed series by comparing each
    point to its `order` neighbors on each side.

    Unlike `zigzag_pivots`, this has no notion of a percentage threshold — it
    relies on the input already being smooth enough that neighbor-comparison
    doesn't just flag every minor wiggle. Intended for use with the Savitzky-Golay
    / kernel-regression smoothers, not raw price.
    """
    values = series.to_numpy(dtype=float)
    if len(values) == 0:
        return []

    peak_positions = argrelextrema(values, np.greater, order=order)[0]
    trough_positions = argrelextrema(values, np.less, order=order)[0]

    candidates: list[tuple[int, Literal["peak", "trough"]]] = [
        (pos, "peak") for pos in peak_positions
    ] + [(pos, "trough") for pos in trough_positions]
    candidates.sort(key=lambda c: c[0])

    pivots = [
        Pivot(index=pos, timestamp=series.index[pos], price=values[pos], type=pivot_type)
        for pos, pivot_type in candidates
    ]
    return _enforce_alternation(pivots)


def _enforce_alternation(pivots: list[Pivot]) -> list[Pivot]:
    """Collapse consecutive same-type pivots (possible near plateaus) down to the
    single most extreme one, so the sequence strictly alternates peak/trough —
    an invariant every pattern matcher relies on.
    """
    if not pivots:
        return []

    result = [pivots[0]]
    for pivot in pivots[1:]:
        if pivot.type == result[-1].type:
            is_more_extreme = (
                pivot.price > result[-1].price
                if pivot.type == "peak"
                else pivot.price < result[-1].price
            )
            if is_more_extreme:
                result[-1] = pivot
        else:
            result.append(pivot)
    return result
