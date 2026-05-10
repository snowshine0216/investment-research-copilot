from __future__ import annotations

from pathlib import Path
import pytest
from irc.config_loader import _resolve_schema


def test_unknown_schema_raises_keyerror(tmp_path: Path):
    repo_root = tmp_path
    unknown_file = repo_root / "unknown" / "path.yaml"
    with pytest.raises(KeyError):
        _resolve_schema(repo_root, unknown_file)
