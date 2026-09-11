from ..config.models import DoubleTopConfig
from ..pivots.models import Pivot
from .models import Candidate
from .registry import register_pattern

# Height similarity is the primary visual signature of a double top; trough depth
# mainly confirms a genuine pullback rather than a minor wiggle, so it's weighted less.
HEIGHT_WEIGHT = 0.6
DEPTH_WEIGHT = 0.4


@register_pattern("double_top")
def find_double_top_candidates(
    pivots: list[Pivot], config: DoubleTopConfig
) -> list[Candidate]:
    """Scan every consecutive (peak, trough, peak) triple for a double top.

    Overlapping windows (e.g. peak-trough-peak-trough-peak) can each independently
    satisfy the rule and are all returned — recall-first per the project's stated
    goal; deduplicating overlapping candidates is a downstream scoring/ranking
    concern (functional-spec §7.3), not this matcher's job.
    """
    candidates: list[Candidate] = []

    for i in range(len(pivots) - 2):
        peak1, trough, peak2 = pivots[i], pivots[i + 1], pivots[i + 2]
        if peak1.type != "peak" or trough.type != "trough" or peak2.type != "peak":
            continue

        bars_between = peak2.index - peak1.index
        if not (
            config.min_time_separation_bars <= bars_between <= config.max_time_separation_bars
        ):
            continue

        height_diff_pct = abs(peak1.price - peak2.price) / min(peak1.price, peak2.price) * 100
        if height_diff_pct > config.height_similarity_pct:
            continue

        higher_peak_price = max(peak1.price, peak2.price)
        trough_depth_pct = (higher_peak_price - trough.price) / higher_peak_price * 100
        if trough_depth_pct < config.min_trough_depth_pct:
            continue

        height_score = 1 - height_diff_pct / config.height_similarity_pct
        depth_score = min(trough_depth_pct / (2 * config.min_trough_depth_pct), 1.0)
        confidence = round(HEIGHT_WEIGHT * height_score + DEPTH_WEIGHT * depth_score, 4)

        candidates.append(
            Candidate(
                pattern_type="double_top",
                pivots=[peak1, trough, peak2],
                confidence_score=confidence,
                metrics={
                    "height_diff_pct": round(height_diff_pct, 4),
                    "trough_depth_pct": round(trough_depth_pct, 4),
                    "bars_between_peaks": float(bars_between),
                },
            )
        )

    return candidates
