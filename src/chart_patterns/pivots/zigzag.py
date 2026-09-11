from typing import Literal

import pandas as pd

from .models import Pivot


def zigzag_pivots(series: pd.Series, threshold_pct: float) -> list[Pivot]:
    """Detect alternating peak/trough pivots by tracking price swings that exceed
    `threshold_pct` from the last confirmed extreme.

    A pivot is only confirmed once price reverses by the threshold from it, so the
    trailing (most recent) extreme is deliberately left out if it hasn't been
    confirmed yet — that's the defining behavior of the ZigZag indicator, not a bug.
    """
    if threshold_pct <= 0:
        raise ValueError("threshold_pct must be positive")

    values = series.to_numpy(dtype=float)
    n = len(values)
    if n == 0:
        return []

    def make_pivot(pos: int, price: float, pivot_type: Literal["peak", "trough"]) -> Pivot:
        return Pivot(index=pos, timestamp=series.index[pos], price=price, type=pivot_type)

    pivots: list[Pivot] = []

    # Phase 1 — bootstrap: neither swing direction is known yet, so track the running
    # min/max from the start until price has broken `threshold_pct` away from one of
    # them. That running extreme is itself the first confirmed pivot.
    running_max_pos = running_min_pos = 0
    running_max_price = running_min_price = values[0]
    direction: str | None = None
    extreme_pos = 0
    extreme_price = values[0]

    for i in range(1, n):
        price = values[i]
        if price > running_max_price:
            running_max_pos, running_max_price = i, price
        if price < running_min_price:
            running_min_pos, running_min_price = i, price

        up_pct = (price - running_min_price) / running_min_price * 100
        down_pct = (running_max_price - price) / running_max_price * 100
        triggered_up = up_pct >= threshold_pct and running_min_pos < i
        triggered_down = down_pct >= threshold_pct and running_max_pos < i

        if triggered_up and triggered_down:
            # Both breached at once: anchor on whichever extreme was set more
            # recently, since price must have touched it last before reversing.
            if running_min_pos > running_max_pos:
                triggered_down = False
            else:
                triggered_up = False

        if triggered_up:
            direction = "up"
            pivots.append(make_pivot(running_min_pos, running_min_price, "trough"))
            extreme_pos, extreme_price = i, price
            break
        if triggered_down:
            direction = "down"
            pivots.append(make_pivot(running_max_pos, running_max_price, "peak"))
            extreme_pos, extreme_price = i, price
            break
    else:
        return pivots  # price never broke out of the noise band; no confirmed pivots

    # Phase 2 — steady state: alternate, confirming a pivot each time price reverses
    # by `threshold_pct` from the current running extreme.
    for i in range(i + 1, n):
        price = values[i]
        if direction == "up":
            if price >= extreme_price:
                extreme_pos, extreme_price = i, price
            elif (extreme_price - price) / extreme_price * 100 >= threshold_pct:
                pivots.append(make_pivot(extreme_pos, extreme_price, "peak"))
                direction = "down"
                extreme_pos, extreme_price = i, price
        else:
            if price <= extreme_price:
                extreme_pos, extreme_price = i, price
            elif (price - extreme_price) / extreme_price * 100 >= threshold_pct:
                pivots.append(make_pivot(extreme_pos, extreme_price, "trough"))
                direction = "up"
                extreme_pos, extreme_price = i, price

    return pivots
