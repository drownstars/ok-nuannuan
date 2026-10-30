"""Keep temporary test data inside the project, including a fresh checkout."""
from pathlib import Path


def pytest_configure(config):
    (Path(__file__).resolve().parents[1] / '.cache/tmp').mkdir(parents=True, exist_ok=True)
