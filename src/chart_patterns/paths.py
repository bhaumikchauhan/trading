"""Repo-root resolution shared by modules that read/write files relative to the project root
(e.g. data/, output/) regardless of how deep they live inside src/chart_patterns/.
"""

from pathlib import Path


def _find_project_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return start.parents[-1]


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
