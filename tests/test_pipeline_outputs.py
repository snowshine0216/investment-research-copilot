from __future__ import annotations
from pathlib import Path
from irc.pipeline_outputs import STAGE_REQUIRED_OUTPUTS, missing_outputs


def test_manifest_covers_all_writing_stages():
    # Ingest is intentionally excluded (covered by freshness check).
    # Research is intentionally excluded (optional, off by default).
    must_have = {"discover", "score", "gold", "allocate", "plan", "opportunity", "memo"}
    assert must_have.issubset(set(STAGE_REQUIRED_OUTPUTS.keys()))


def test_missing_outputs_returns_empty_when_all_present(tmp_path: Path):
    (tmp_path / "scoring.json").write_text("{}", encoding="utf-8")
    assert missing_outputs(tmp_path, "score") == ()


def test_missing_outputs_returns_missing_names(tmp_path: Path):
    # gold requires gold_regime.json AND gold_band.yaml
    (tmp_path / "gold_regime.json").write_text("{}", encoding="utf-8")
    result = missing_outputs(tmp_path, "gold")
    assert result == ("gold_band.yaml",)


def test_missing_outputs_returns_all_when_none_present(tmp_path: Path):
    result = missing_outputs(tmp_path, "opportunity")
    assert set(result) == {
        "opportunity_report.json",
        "thesis_cards.yaml",
        "discipline_report.md",
    }


def test_unknown_stage_returns_empty(tmp_path: Path):
    # Stages we deliberately don't validate (ingest, research) must not error.
    assert missing_outputs(tmp_path, "ingest") == ()
    assert missing_outputs(tmp_path, "research") == ()
    assert missing_outputs(tmp_path, "nonexistent") == ()


def test_memo_satisfied_by_memo_md(tmp_path: Path):
    (tmp_path / "memo.md").write_text("memo body", encoding="utf-8")
    assert missing_outputs(tmp_path, "memo") == ()


def test_memo_satisfied_by_memo_blocked_md(tmp_path: Path):
    # Audit-block is a valid memo outcome — do not flag as missing.
    (tmp_path / "memo_blocked.md").write_text("blocked body", encoding="utf-8")
    assert missing_outputs(tmp_path, "memo") == ()


def test_memo_flagged_when_neither_present(tmp_path: Path):
    result = missing_outputs(tmp_path, "memo")
    assert result == ("memo.md or memo_blocked.md",)
