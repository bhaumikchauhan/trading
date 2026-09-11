from collections.abc import Callable
from typing import Any

from ..pivots.models import Pivot
from .models import Candidate

PatternMatcherFn = Callable[[list[Pivot], Any], list[Candidate]]

_PATTERN_MATCHERS: dict[str, PatternMatcherFn] = {}


def register_pattern(name: str) -> Callable[[PatternMatcherFn], PatternMatcherFn]:
    """Class/function decorator so new pattern matchers plug in without the core
    pipeline needing to import each one by name (functional-spec §5.4).
    """

    def decorator(func: PatternMatcherFn) -> PatternMatcherFn:
        _PATTERN_MATCHERS[name] = func
        return func

    return decorator


def find_candidates(pattern_name: str, pivots: list[Pivot], config: Any) -> list[Candidate]:
    if pattern_name not in _PATTERN_MATCHERS:
        raise ValueError(
            f"No pattern matcher registered for {pattern_name!r}. "
            f"Known patterns: {sorted(_PATTERN_MATCHERS)}"
        )
    return _PATTERN_MATCHERS[pattern_name](pivots, config)
