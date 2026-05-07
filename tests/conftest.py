from __future__ import annotations
from pathlib import Path
import pytest


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Empty temporary repo root with inputs/ and config/ ready to populate."""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    return tmp_path
