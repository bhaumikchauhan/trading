import pytest
from pydantic import ValidationError

from chart_patterns.config import (
    DoubleBottomConfig,
    DoubleTopConfig,
    HeadAndShouldersConfig,
    load_logging_config,
    load_pattern_config,
    load_smoothing_config,
)
from chart_patterns.config.models import SavgolConfig


def test_load_smoothing_config_from_real_file():
    config = load_smoothing_config()
    assert config.zigzag.threshold_pct == 3.0
    assert config.savgol.window_length == 11
    assert config.savgol.polyorder == 2


def test_load_logging_config_from_real_file():
    config = load_logging_config()
    assert config.level == "INFO"


def test_load_double_top_config_from_real_file():
    config = load_pattern_config("double_top")
    assert isinstance(config, DoubleTopConfig)
    assert config.height_similarity_pct == 3.0
    assert config.min_time_separation_bars < config.max_time_separation_bars


def test_load_double_bottom_config_from_real_file():
    config = load_pattern_config("double_bottom")
    assert isinstance(config, DoubleBottomConfig)
    assert config.depth_similarity_pct == 3.0
    assert config.min_time_separation_bars < config.max_time_separation_bars


def test_load_head_and_shoulders_config_from_real_file():
    config = load_pattern_config("head_and_shoulders")
    assert isinstance(config, HeadAndShouldersConfig)
    assert config.shoulder_height_similarity_pct == 5.0
    assert config.min_time_separation_bars < config.max_time_separation_bars


def test_unknown_pattern_name_raises():
    with pytest.raises(ValueError, match="No config model registered"):
        load_pattern_config("not_a_real_pattern")


def test_double_top_rejects_inverted_time_separation():
    with pytest.raises(ValidationError, match="min_time_separation_bars must be less than"):
        DoubleTopConfig(
            height_similarity_pct=3.0,
            min_trough_depth_pct=2.0,
            max_time_separation_bars=5,
            min_time_separation_bars=120,
        )


def test_double_top_rejects_non_positive_tolerance():
    with pytest.raises(ValidationError):
        DoubleTopConfig(
            height_similarity_pct=0,
            min_trough_depth_pct=2.0,
            max_time_separation_bars=120,
            min_time_separation_bars=5,
        )


def test_savgol_rejects_even_window_length():
    with pytest.raises(ValidationError, match="must be odd"):
        SavgolConfig(window_length=10, polyorder=2)


def test_savgol_rejects_polyorder_ge_window_length():
    with pytest.raises(ValidationError, match="polyorder must be less than"):
        SavgolConfig(window_length=5, polyorder=5)
