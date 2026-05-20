from __future__ import annotations
from pathlib import Path
from irc.pipeline_halt import HaltReason, write_halted_structured


def test_missing_required_outputs_remediation_mentions_files(tmp_path: Path):
    reason = HaltReason(
        kind="missing_required_outputs",
        stage="opportunity",
        detail="stage exited 0 but did not produce: opportunity_report.json",
        stats={},
        first_error=None,
    )
    write_halted_structured(repo_root=tmp_path, date="2026-05-20", reason=reason)
    body = (tmp_path / "outputs" / "2026-05-20" / "PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "did not produce" in body
    assert "opportunity_report.json" in body
    # New, specific remediation language (added in this task):
    assert "expected output artifact(s) were not written" in body
