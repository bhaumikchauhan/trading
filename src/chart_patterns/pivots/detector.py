import pandas as pd

from .extrema import find_local_extrema
from .models import Pivot
from .zigzag import zigzag_pivots


def detect_pivots(series: pd.Series, method: str = "zigzag", **kwargs) -> list[Pivot]:
    """Single entry point pattern matchers use to get pivots from a price series,
    so callers don't need to know which detection algorithm backs a given method.
    """
    if method == "zigzag":
        return zigzag_pivots(series, threshold_pct=kwargs["threshold_pct"])
    if method == "extrema":
        return find_local_extrema(series, order=kwargs.get("order", 3))
    raise ValueError(f"Unknown pivot detection method: {method!r}")
