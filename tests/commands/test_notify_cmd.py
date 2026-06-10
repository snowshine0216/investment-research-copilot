from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import respx
from click.testing import CliRunner

from irc.cli import main
from irc.commands import notify_cmd
from irc.notify.types import NotificationDecision


def _write_outputs(root: Path, date_str: str, summary: dict) -> Path:
    out = root / "outputs" / date_str
    out.mkdir(parents=True)
    report = {"overall_status": "ok", "summary": summary}
    (out / "decision_report.json").write_text(json.dumps(report), encoding="utf-8")
    return out


# ---- pure-ish builder helpers (no network/osascript) ----

def test_load_holidays_absent_file_is_empty_set(tmp_path: Path):
    assert notify_cmd._load_holidays(tmp_path) == set()


def test_load_holidays_reads_yaml_list(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "cn_market_holidays.yaml").write_text(
        "- 2026-10-01\n- 2026-10-02\n", encoding="utf-8"
    )
    from datetime import date

    holidays = notify_cmd._load_holidays(tmp_path)
    assert date(2026, 10, 1) in holidays
    assert date(2026, 10, 2) in holidays


def test_build_outcome_missing_today_dir(tmp_path: Path, monkeypatch):
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2099, 1, 1))
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.today_dir_exists is False


def test_build_outcome_reads_summary_counts(tmp_path: Path, monkeypatch):
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    _write_outputs(
        tmp_path, "2026-06-10",
        {"actionable_buy_count": 2, "trim_count": 1, "exit_count": 0, "review_count": 0},
    )
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.today_dir_exists is True
    assert outcome.actionable_buy_count == 2
    assert outcome.trim_count == 1


# ---- P0-1: missing sell-side keys must default to None, not 0 ----

def test_build_outcome_missing_sell_keys_default_to_none(tmp_path: Path, monkeypatch):
    """P0-1: summary without trim/exit/review keys → None, not 0 (ADR 0015)."""
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    # Only actionable_buy_count present; the three sell-side keys are absent.
    _write_outputs(tmp_path, "2026-06-10", {"actionable_buy_count": 0})
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.trim_count is None, "missing trim_count key must default to None"
    assert outcome.exit_count is None, "missing exit_count key must default to None"
    assert outcome.review_count is None, "missing review_count key must default to None"


def test_build_outcome_missing_sell_keys_classify_as_action_unknown(tmp_path: Path, monkeypatch):
    """P0-1: outcome from summary without sell-side keys → severity action/unknown."""
    from datetime import date

    from irc.notify.classify import classify_run_outcome

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    _write_outputs(tmp_path, "2026-06-10", {"actionable_buy_count": 0})
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    decision = classify_run_outcome(outcome)
    assert decision.severity == "action"
    assert "unknown" in decision.body.lower()


# ---- P0-4: malformed cn_market_holidays.yaml → warn + return set(), no raise ----

def test_load_holidays_malformed_yaml_returns_empty_set(tmp_path: Path, caplog):
    """P0-4: malformed YAML → warning logged, empty set returned, no exception."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "cn_market_holidays.yaml").write_text(
        "- 2026-10-01\n  bad: indent: :\n", encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING):
        result = notify_cmd._load_holidays(tmp_path)
    assert result == set()
    assert any("holiday" in r.getMessage().lower() or "yaml" in r.getMessage().lower()
               for r in caplog.records)


def test_load_holidays_invalid_date_value_returns_empty_set(tmp_path: Path, caplog):
    """P0-4: YAML that parses but contains non-date strings → warning, empty set."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "cn_market_holidays.yaml").write_text(
        "- not-a-date\n", encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING):
        result = notify_cmd._load_holidays(tmp_path)
    assert result == set()


# ---- P1-1: corrupt decision_report.json → None sentinel → severity failed ----

def test_read_summary_returns_none_on_json_decode_error(tmp_path: Path):
    """P1-1: _read_summary returns None (not {}) on malformed JSON."""
    path = tmp_path / "decision_report.json"
    path.write_text("{bad json", encoding="utf-8")
    result = notify_cmd._read_summary(path)
    assert result is None


def test_build_outcome_corrupt_report_is_unreadable(tmp_path: Path, monkeypatch):
    """P1-1: corrupt decision_report.json → outcome.decision_report_unreadable is True."""
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    out = tmp_path / "outputs" / "2026-06-10"
    out.mkdir(parents=True)
    (out / "decision_report.json").write_text("{bad json", encoding="utf-8")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.decision_report_unreadable is True


def test_build_outcome_corrupt_report_classifies_failed(tmp_path: Path, monkeypatch):
    """P1-1: corrupt report → severity failed with 'unreadable' in body."""
    from datetime import date

    from irc.notify.classify import classify_run_outcome

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    out = tmp_path / "outputs" / "2026-06-10"
    out.mkdir(parents=True)
    (out / "decision_report.json").write_text("{bad json", encoding="utf-8")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    decision = classify_run_outcome(outcome)
    assert decision.severity == "failed"
    assert "unreadable" in decision.body.lower()


def test_build_outcome_missing_report_still_works(tmp_path: Path, monkeypatch):
    """P1-1: absent report (file missing) → not corrupt; sell-side counts are None."""
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    out = tmp_path / "outputs" / "2026-06-10"
    out.mkdir(parents=True)
    # no decision_report.json at all
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.decision_report_unreadable is False
    assert outcome.trim_count is None


def test_build_outcome_preserves_null_sell_counts(tmp_path: Path, monkeypatch):
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    _write_outputs(
        tmp_path, "2026-06-10",
        {"actionable_buy_count": 0, "trim_count": None, "exit_count": None, "review_count": None},
    )
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.trim_count is None


def test_build_outcome_detects_halt_and_stale(tmp_path: Path, monkeypatch):
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    out = _write_outputs(tmp_path, "2026-06-10", {"actionable_buy_count": 0})
    (out / "PIPELINE_HALTED.md").write_text("halt", encoding="utf-8")
    (out / "STALE_INGEST.md").write_text("stale", encoding="utf-8")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="daily", last_exit_code=0)
    assert outcome.pipeline_halted is True
    assert outcome.stale_ingest is True


# ---- dispatch: both channels stubbed (AC8) ----

def test_dispatch_continues_when_macos_fails(monkeypatch, caplog):
    decision = NotificationDecision(True, "action", "t", "b")
    monkeypatch.setattr(
        notify_cmd, "_send_macos",
        lambda d: (_ for _ in ()).throw(RuntimeError("osascript boom")),
    )
    posted = {}
    monkeypatch.setattr(notify_cmd, "_send_feishu", lambda d, url: posted.update(sent=True))
    monkeypatch.setenv("IRC_FEISHU_WEBHOOK_URL", "https://hook.example/abc")
    with caplog.at_level(logging.WARNING):
        rc = notify_cmd._dispatch(decision)
    assert rc != 0  # transport failure => non-zero
    assert posted == {"sent": True}  # feishu still attempted


def test_dispatch_feishu_skipped_when_env_unset(monkeypatch):
    decision = NotificationDecision(True, "action", "t", "b")
    monkeypatch.setattr(notify_cmd, "_send_macos", lambda d: None)
    called = {"feishu": False}
    monkeypatch.setattr(
        notify_cmd, "_send_feishu", lambda d, url: called.__setitem__("feishu", True)
    )
    monkeypatch.delenv("IRC_FEISHU_WEBHOOK_URL", raising=False)
    rc = notify_cmd._dispatch(decision)
    assert rc == 0
    assert called["feishu"] is False


def test_dispatch_skips_everything_when_should_not_notify(monkeypatch):
    decision = NotificationDecision(False, "clean", "t", "b")
    called = {"macos": False}
    monkeypatch.setattr(notify_cmd, "_send_macos", lambda d: called.__setitem__("macos", True))
    monkeypatch.setattr(notify_cmd, "_send_feishu", lambda d, url: None)
    rc = notify_cmd._dispatch(decision)
    assert rc == 0
    assert called["macos"] is False


# ---- Feishu URL never logged in full (AC7) ----

@respx.mock
def test_feishu_post_does_not_log_full_url(caplog):
    """AC7: the webhook token must not appear in any log record from ANY logger.

    This test captures at root scope (not just the app logger) to catch library
    loggers such as httpx / httpcore that propagate to root, which would reach
    the RichHandler → stderr → launchd StandardErrorPath log files.
    """
    url = "https://open.feishu.cn/hook/SECRET-TOKEN-1234"
    respx.post(url).mock(return_value=httpx.Response(200, json={"code": 0}))
    decision = NotificationDecision(True, "action", "t", "b")
    with caplog.at_level(logging.INFO):  # root scope — catches ALL loggers
        notify_cmd._send_feishu(decision, url)
    for record in caplog.records:
        assert "SECRET-TOKEN-1234" not in record.getMessage(), (
            f"Token leaked in logger={record.name!r}: {record.getMessage()!r}"
        )


# ---- CLI smoke (AC5) ----

def test_notify_status_help_lists_options():
    result = CliRunner().invoke(main, ["notify-status", "--help"])
    assert result.exit_code == 0
    for opt in ("--run-kind", "--last-exit-code", "--repo-root", "--notify-on-clean"):
        assert opt in result.output


def test_notify_status_clean_suppressed_exits_zero_no_network(tmp_path, monkeypatch):
    from datetime import date

    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 6, 10))
    monkeypatch.setattr(notify_cmd, "_send_macos", lambda d: None)  # avoid real osascript
    monkeypatch.delenv("IRC_FEISHU_WEBHOOK_URL", raising=False)
    _write_outputs(
        tmp_path, "2026-06-10",
        {"actionable_buy_count": 0, "trim_count": 0, "exit_count": 0, "review_count": 0},
    )
    result = CliRunner().invoke(
        main,
        ["notify-status", "--run-kind", "daily", "--last-exit-code", "0",
         "--repo-root", str(tmp_path), "--no-notify-on-clean"],
    )
    assert result.exit_code == 0, result.output
