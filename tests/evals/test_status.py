from __future__ import annotations
from evals._shared.status import classify_status, worst_status, Status


def test_classify_pass():
    th = {"warn_below": 0.95, "fail_below": 0.80}
    assert classify_status(value=0.99, thresholds=th, direction="higher_is_better") == "PASS"
    assert classify_status(value=0.90, thresholds=th, direction="higher_is_better") == "WARN"
    assert classify_status(value=0.70, thresholds=th, direction="higher_is_better") == "FAIL"


def test_classify_lower_is_better():
    th = {"warn_above": 0.05, "fail_above": 0.20}
    assert classify_status(value=0.01, thresholds=th, direction="lower_is_better") == "PASS"
    assert classify_status(value=0.10, thresholds=th, direction="lower_is_better") == "WARN"
    assert classify_status(value=0.30, thresholds=th, direction="lower_is_better") == "FAIL"


def test_worst_status():
    assert worst_status(["PASS", "WARN", "PASS"]) == "WARN"
    assert worst_status(["PASS", "WARN", "FAIL"]) == "FAIL"
    assert worst_status([]) == "PASS"


def test_status_literal_includes_skipped():
    import typing
    from evals._shared.status import Status
    assert "SKIPPED" in typing.get_args(Status)


def test_worst_status_unchanged_ranks_only_pass_warn_fail():
    # worst_status must NOT be passed SKIPPED; it ranks only PASS/WARN/FAIL.
    assert worst_status(["PASS", "FAIL"]) == "FAIL"
    assert worst_status(["PASS", "WARN"]) == "WARN"
