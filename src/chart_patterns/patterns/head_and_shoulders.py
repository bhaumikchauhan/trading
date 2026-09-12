from ..config.models import HeadAndShouldersConfig
from ..pivots.models import Pivot
from .models import Candidate
from .registry import register_pattern

# Shoulder symmetry is the primary visual signature; head prominence confirms
# there's actually a "head" rather than three similar peaks; neckline flatness is
# a secondary confirmation, so it's weighted least.
SHOULDER_WEIGHT = 0.4
HEAD_WEIGHT = 0.35
NECKLINE_WEIGHT = 0.25


@register_pattern("head_and_shoulders")
def find_head_and_shoulders_candidates(
    pivots: list[Pivot], config: HeadAndShouldersConfig
) -> list[Candidate]:
    """Scan every consecutive (peak, trough, peak, trough, peak) quintuple for a
    head and shoulders top: a middle peak (head) clearly higher than two outer
    peaks (shoulders) of similar height, with the two troughs forming a
    roughly flat neckline.

    Deliberately does not require left/right time symmetry — real head and
    shoulders patterns are frequently asymmetric, and this project is tuned for
    recall over strict textbook geometry. Returns overlapping candidates
    untouched, same as find_double_top_candidates.
    """
    candidates: list[Candidate] = []

    for i in range(len(pivots) - 4):
        left_shoulder, left_trough, head, right_trough, right_shoulder = pivots[i : i + 5]
        if (
            left_shoulder.type != "peak"
            or left_trough.type != "trough"
            or head.type != "peak"
            or right_trough.type != "trough"
            or right_shoulder.type != "peak"
        ):
            continue

        bars_span = right_shoulder.index - left_shoulder.index
        if not (
            config.min_time_separation_bars <= bars_span <= config.max_time_separation_bars
        ):
            continue

        higher_shoulder_price = max(left_shoulder.price, right_shoulder.price)
        head_prominence_pct = (
            (head.price - higher_shoulder_price) / higher_shoulder_price * 100
        )
        if head_prominence_pct < config.min_head_prominence_pct:
            continue

        shoulder_height_diff_pct = (
            abs(left_shoulder.price - right_shoulder.price)
            / min(left_shoulder.price, right_shoulder.price)
            * 100
        )
        if shoulder_height_diff_pct > config.shoulder_height_similarity_pct:
            continue

        neckline_slope_pct = (
            abs(right_trough.price - left_trough.price)
            / min(left_trough.price, right_trough.price)
            * 100
        )
        if neckline_slope_pct > config.max_neckline_slope_pct:
            continue

        shoulder_score = 1 - shoulder_height_diff_pct / config.shoulder_height_similarity_pct
        head_score = min(head_prominence_pct / (2 * config.min_head_prominence_pct), 1.0)
        neckline_score = 1 - neckline_slope_pct / config.max_neckline_slope_pct
        confidence = round(
            SHOULDER_WEIGHT * shoulder_score
            + HEAD_WEIGHT * head_score
            + NECKLINE_WEIGHT * neckline_score,
            4,
        )

        candidates.append(
            Candidate(
                pattern_type="head_and_shoulders",
                pivots=[left_shoulder, left_trough, head, right_trough, right_shoulder],
                confidence_score=confidence,
                metrics={
                    "shoulder_height_diff_pct": round(shoulder_height_diff_pct, 4),
                    "head_prominence_pct": round(head_prominence_pct, 4),
                    "neckline_slope_pct": round(neckline_slope_pct, 4),
                    "bars_span": float(bars_span),
                },
            )
        )

    return candidates
