from __future__ import annotations
from datetime import datetime, timedelta, timezone
from evals._shared.report_schema import StageReport
from irc.monitor.eval.staleness import resolve_health, STALE_AFTER_DAYS

_TZ = timezone(timedelta(hours=8))
_NOW = datetime(2026, 6, 16, 12, 0, tzinfo=_TZ)


def _report(overall: str, *, ran_at: datetime) -> StageReport:
    return StageReport(stage="monitor_impact", ran_at=ran_at.isoformat(),
                       based_on=[], metrics=[], overall=overall)


def test_stale_after_days_default_is_14():
    assert STALE_AFTER_DAYS == 14


def test_absent_report_is_unknown_absent():
    h = resolve_health(None, now=_NOW, stale_after_days=14)
    assert h.status == "UNKNOWN" and "absent" in h.reasons[0]


def test_skipped_report_is_unknown_skipped():
    h = resolve_health(_report("SKIPPED", ran_at=_NOW), now=_NOW, stale_after_days=14)
    assert h.status == "UNKNOWN" and "skipped" in h.reasons[0]


def test_stale_report_is_unknown_stale():
    old = _NOW - timedelta(days=20)
    h = resolve_health(_report("PASS", ran_at=old), now=_NOW, stale_after_days=14)
    assert h.status == "UNKNOWN" and "stale" in h.reasons[0]


def test_fresh_pass_passes_through():
    h = resolve_health(_report("PASS", ran_at=_NOW), now=_NOW, stale_after_days=14)
    assert h.status == "PASS"


def test_fresh_fail_passes_through():
    h = resolve_health(_report("FAIL", ran_at=_NOW), now=_NOW, stale_after_days=14)
    assert h.status == "FAIL"


def test_naive_ran_at_does_not_raise_and_gives_correct_staleness():
    # A ran_at without tz offset (naive ISO string) must not crash with TypeError.
    # A naive ran_at that is recent → PASS passthrough; one that is old → UNKNOWN stale.
    naive_recent = datetime(2026, 6, 16, 9, 0)   # no tzinfo
    rep_recent = StageReport(stage="monitor_impact",
                             ran_at=naive_recent.isoformat(),
                             based_on=[], metrics=[], overall="PASS")
    h = resolve_health(rep_recent, now=_NOW, stale_after_days=14)
    assert h.status == "PASS"   # no TypeError, correct result

    naive_old = datetime(2026, 5, 1, 9, 0)       # naive, clearly stale
    rep_old = StageReport(stage="monitor_impact",
                          ran_at=naive_old.isoformat(),
                          based_on=[], metrics=[], overall="PASS")
    h2 = resolve_health(rep_old, now=_NOW, stale_after_days=14)
    assert h2.status == "UNKNOWN" and "stale" in h2.reasons[0]
