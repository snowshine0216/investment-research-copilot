from __future__ import annotations
from pathlib import Path
from irc.pipeline_halt import write_halted


def test_write_halted_creates_md(tmp_path: Path):
    write_halted(repo_root=tmp_path, date="2026-05-07", stage="scoring",
                  reason="sanity_check rho ≤ 0", remediation="Re-tune factor weights or check data feed.")
    p = tmp_path / "outputs/2026-05-07/PIPELINE_HALTED.md"
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "scoring" in content
    assert "rho" in content
    assert "Re-tune" in content
