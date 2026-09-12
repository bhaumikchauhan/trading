from datetime import datetime

from chart_patterns.cli.main import (
    _format_metrics,
    _format_pivots,
    _load_all_symbols,
    _output_stem,
)
from chart_patterns.patterns import Candidate
from chart_patterns.pivots import Pivot


def test_output_stem_single_symbol_single_pattern():
    assert _output_stem(["RELIANCE"], ["double_top"], "double_top") == "RELIANCE_double_top"


def test_output_stem_multiple_symbols_single_pattern():
    symbols = [f"SYM{i}" for i in range(1000)]
    assert _output_stem(symbols, ["double_top"], "double_top") == "1000_double_top"


def test_output_stem_single_symbol_multiple_patterns():
    patterns = ["double_top", "double_bottom", "head_and_shoulders"]
    assert _output_stem(["RELIANCE"], patterns, "all") == "RELIANCE_mul_pattern"


def test_output_stem_multiple_symbols_multiple_patterns():
    symbols = ["RELIANCE", "TCS"]
    patterns = ["double_top", "double_bottom"]
    assert _output_stem(symbols, patterns, "all") == "2_mul_pattern"


def test_load_all_symbols_skips_blank_lines_and_strips_whitespace(tmp_path):
    csv_path = tmp_path / "symbols.csv"
    csv_path.write_text("RELIANCE\n\n  TCS  \nINFY\n", encoding="utf-8")

    assert _load_all_symbols(csv_path) == ["RELIANCE", "TCS", "INFY"]


def _candidate() -> Candidate:
    pivots = [
        Pivot(index=0, timestamp=datetime(2025, 1, 1), price=100.0, type="peak"),
        Pivot(index=5, timestamp=datetime(2025, 1, 6), price=90.0, type="trough"),
        Pivot(index=10, timestamp=datetime(2025, 1, 11), price=101.0, type="peak"),
    ]
    return Candidate(
        pattern_type="double_top",
        pivots=pivots,
        confidence_score=0.83,
        metrics={"height_diff_pct": 1.0, "trough_depth_pct": 10.5},
    )


def test_format_pivots_matches_expected_shape():
    assert _format_pivots(_candidate()) == (
        "peak@2025-01-01@100.00 | trough@2025-01-06@90.00 | peak@2025-01-11@101.00"
    )


def test_format_metrics_matches_expected_shape():
    assert _format_metrics(_candidate()) == "height_diff_pct=1.00, trough_depth_pct=10.50"
