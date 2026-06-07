"""Shared pytest fixtures."""
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to tests/fixtures/, where per-source captured payloads live."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_data_dir(tmp_path) -> Path:
    """Isolated data/ directory for tests that read or write to it."""
    d = tmp_path / "data"
    (d / "raw").mkdir(parents=True)
    (d / "overrides").mkdir(parents=True)
    return d
