from pathlib import Path

import yaml
from pydantic import BaseModel

from ..paths import PROJECT_ROOT
from .models import DoubleTopConfig, LoggingConfig, SmoothingConfig

CONFIG_DIR = PROJECT_ROOT / "configs"

# One entry per pattern with a config file — grows as patterns are implemented
# (functional-spec §6), mirroring the pattern-matcher registry planned for
# technical-spec §9.
_PATTERN_CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "double_top": DoubleTopConfig,
}


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_smoothing_config(path: Path | None = None) -> SmoothingConfig:
    path = path or CONFIG_DIR / "smoothing.yaml"
    return SmoothingConfig.model_validate(_load_yaml(path))


def load_logging_config(path: Path | None = None) -> LoggingConfig:
    path = path or CONFIG_DIR / "logging.yaml"
    return LoggingConfig.model_validate(_load_yaml(path))


def load_pattern_config(pattern_name: str, path: Path | None = None) -> BaseModel:
    if pattern_name not in _PATTERN_CONFIG_MODELS:
        raise ValueError(
            f"No config model registered for pattern {pattern_name!r}. "
            f"Known patterns: {sorted(_PATTERN_CONFIG_MODELS)}"
        )
    path = path or CONFIG_DIR / "patterns" / f"{pattern_name}.yaml"
    data = _load_yaml(path)
    if pattern_name not in data:
        raise ValueError(f"{path} is missing its top-level {pattern_name!r} key")
    model = _PATTERN_CONFIG_MODELS[pattern_name]
    return model.model_validate(data[pattern_name])
