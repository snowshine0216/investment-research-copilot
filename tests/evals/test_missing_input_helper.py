from __future__ import annotations

import json
from pathlib import Path

from evals._shared.missing_input import (
    EVAL_RC_FAIL,
    missing_input_report,
    write_missing_input_report,
)


def test_missing_input_report_marks_fail_with_reason():
    report = missing_input_report(
        stage="research",
        reason="data/research/research_status.json is missing",
        based_on_path="data/research/research_status.json",
    )
    assert report.overall == "FAIL"
    assert report.stage == "research"
    assert report.based_on == ["data/research/research_status.json"]
    assert report.metrics == []
    # ran_at must be ISO-8601 in +08:00 (Beijing) to match other runners.
    assert report.ran_at.endswith("+08:00")


def test_eval_rc_fail_is_two_to_match_existing_convention():
    # Existing runners return 2 for FAIL, 1 for WARN, 0 for PASS.
    assert EVAL_RC_FAIL == 2


def test_write_missing_input_report_emits_json_with_fail_overall(tmp_path: Path):
    report = missing_input_report(
        stage="triggers",
        reason="trigger watch data unavailable",
        based_on_path=None,
    )
    out = write_missing_input_report(tmp_path, report, date_str="2026-05-15")
    assert out.exists()
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"
    assert body["stage"] == "triggers"
    # based_on may be empty list, never absent.
    assert body["based_on"] == []


def test_eval_rc_skipped_is_3():
    from evals._shared.missing_input import EVAL_RC_SKIPPED
    assert EVAL_RC_SKIPPED == 3


def test_skipped_report_has_overall_skipped():
    from evals._shared.missing_input import skipped_report
    r = skipped_report("monitor_impact", "env absent; not executed")
    assert r.stage == "monitor_impact"
    assert r.overall == "SKIPPED"
    assert "env absent" in r.notes
    assert r.metrics == []
