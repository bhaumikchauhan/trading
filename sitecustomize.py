import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path


def ensure_dependencies():
    root = Path(__file__).resolve().parent
    pyproject = root / "pyproject.toml"

    if not pyproject.exists():
        return

    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)

    dependencies = data.get("project", {}).get("dependencies", [])
    if not dependencies:
        return

    required = []
    for dependency in dependencies:
        package_name = dependency.split("=", 1)[0].split(">", 1)[0].split("<", 1)[0].split("[", 1)[0].strip()
        required.append(package_name)

    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if not missing:
        return

    python_executable = sys.executable
    subprocess.check_call(
        [python_executable, "-m", "pip", "install", *dependencies],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


ensure_dependencies()
