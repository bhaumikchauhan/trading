from ..config.models import DoubleBottomConfig
from ..pivots.models import Pivot
from .models import Candidate
from .registry import register_pattern

# Depth similarity is the primary visual signature of a double bottom; peak
# prominence mainly confirms a genuine bounce rather than a minor wiggle, so it's
# weighted less. Mirrors double_top.py's HEIGHT_WEIGHT/DEPTH_WEIGHT split.
DEPTH_WEIGHT = 0.6
PROMINENCE_WEIGHT = 0.4


@register_pattern("double_bottom")
def find_double_bottom_candidates(
    pivots: list[Pivot], config: DoubleBottomConfig
) -> list[Candidate]:
    """Scan every consecutive (trough, peak, trough) triple for a double bottom.

    Mirror image of find_double_top_candidates — see that module for the
    rationale on returning overlapping candidates untouched (recall-first).
    """
    candidates: list[Candidate] = []

    for i in range(len(pivots) - 2):
        trough1, peak, trough2 = pivots[i], pivots[i + 1], pivots[i + 2]
        if trough1.type != "trough" or peak.type != "peak" or trough2.type != "trough":
            continue

        bars_between = trough2.index - trough1.index
        if not (
            config.min_time_separation_bars <= bars_between <= config.max_time_separation_bars
        ):
            continue

        depth_diff_pct = (
            abs(trough1.price - trough2.price) / min(trough1.price, trough2.price) * 100
        )
        if depth_diff_pct > config.depth_similarity_pct:
            continue

        shallower_trough_price = max(trough1.price, trough2.price)
        peak_prominence_pct = (peak.price - shallower_trough_price) / shallower_trough_price * 100
        if peak_prominence_pct < config.min_peak_prominence_pct:
            continue

        depth_score = 1 - depth_diff_pct / config.depth_similarity_pct
        prominence_score = min(
            peak_prominence_pct / (2 * config.min_peak_prominence_pct), 1.0
        )
        confidence = round(DEPTH_WEIGHT * depth_score + PROMINENCE_WEIGHT * prominence_score, 4)

        candidates.append(
            Candidate(
                pattern_type="double_bottom",
                pivots=[trough1, peak, trough2],
                confidence_score=confidence,
                metrics={
                    "depth_diff_pct": round(depth_diff_pct, 4),
                    "peak_prominence_pct": round(peak_prominence_pct, 4),
                    "bars_between_troughs": float(bars_between),
                },
            )
        )

    return candidates
