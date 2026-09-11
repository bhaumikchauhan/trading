from chart_patterns.data import candle_db
from chart_patterns.paths import PROJECT_ROOT


def test_project_root_resolves_to_repo_root():
    assert (PROJECT_ROOT / "pyproject.toml").exists()


def test_candle_db_points_at_repo_root_data_dir():
    assert candle_db.DB_DIR == str(PROJECT_ROOT / "data")
