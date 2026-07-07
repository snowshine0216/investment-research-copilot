from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import date
from pathlib import Path

import httpx
import respx
from click.testing import CliRunner

from irc.cli import main
from irc.commands import notify_cmd
from irc.notify.classify import classify_run_outcome
from irc.notify.types import NotificationDecision

# ---- shell script paths ----
_OPS = Path(__file__).parents[2] / "ops" / "launchd"


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


# ---- shell script validation (P0-2 / P0-3 / P1-2) ----

def test_all_shell_scripts_pass_bash_syntax_check():
    """All wrapper/install/uninstall scripts must pass bash -n."""
    scripts = list(_OPS.glob("*.sh"))
    assert scripts, "expected *.sh in ops/launchd"
    for script in scripts:
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"bash -n failed for {script.name}:\n{result.stderr}"
        )


def test_wrapper_scripts_contain_uv_bin_placeholder():
    """P0-2: checked-in wrappers must use the __UV_BIN__ placeholder and invoke uv
    via "$UV_BIN" (machine-agnostic), never a bare `uv run` from PATH."""
    for name in ("run-monitor.sh", "run-fundamentals.sh"):
        text = (_OPS / name).read_text(encoding="utf-8")
        assert "__UV_BIN__" in text, f"{name} missing __UV_BIN__ placeholder"
        # Strip comments first: a doc line may *mention* `uv run` (e.g. the
        # provenance-xattr note) without the wrapper actually calling it.
        code = "\n".join(
            ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
        )
        assert "uv run" not in code, f"{name} must not call 'uv run' directly"
        assert '"$UV_BIN" run' in code, f'{name} must invoke uv via "$UV_BIN"'


def test_install_sh_aborts_if_uv_absent():
    """P0-2: install.sh must exit non-zero with a clear message when uv is missing."""
    text = (_OPS / "install.sh").read_text(encoding="utf-8")
    assert "command -v uv" in text, "install.sh must check 'command -v uv'"
    assert "exit 1" in text, "install.sh must exit 1 when uv is absent"


# NOTE: the P0-3 background-watchdog test (IRC_RUN_TIMEOUT / kill -TERM / rc=124)
# was removed with the `run-daily.sh` / `run-weekly-full.sh` wrappers in the
# single-daily-12:15 schedule rework. The surviving wrappers (`run-monitor.sh`,
# `run-fundamentals.sh`) run bounded jobs (a daily brief / a snapshot refresh),
# not the open-ended `irc run` pipeline the watchdog guarded, and neither
# implements a timeout. notify-status still maps exit 124 → "timeout" defensively.


# ---- P1-2: holiday grep anchor ----

def test_holiday_grep_anchored_regex_does_not_match_comment():
    """P1-2: the anchored regex must NOT match a date that appears inside a comment."""
    today = "2026-10-01"
    # Python equivalent of the POSIX ERE used in run-monitor.sh:
    #   ^[-[:space:]]*[\"']?${TODAY}[\"']?[[:space:]]*$
    py_pattern = r"^[-\s]*[\"']?" + re.escape(today) + r"[\"']?\s*$"

    # Should NOT match a comment line containing the date
    comment_line = "# updated 2026-10-01 by user"
    assert not re.match(py_pattern, comment_line), (
        "anchored regex must not match date inside a comment"
    )

    # Should match a plain list entry
    assert re.match(py_pattern, "- 2026-10-01"), "must match bare list entry"
    assert re.match(py_pattern, "'2026-10-01'"), "must match quoted entry"
    assert re.match(py_pattern, "  2026-10-01  "), "must match padded entry"


def test_run_monitor_sh_uses_anchored_grep():
    """P1-2: run-monitor.sh (the surviving holiday-gated wrapper) must use the
    anchored -Eq grep pattern, not bare grep -q."""
    text = (_OPS / "run-monitor.sh").read_text(encoding="utf-8")
    assert "grep -Eq" in text, "run-monitor.sh must use grep -Eq for anchored holiday match"
    assert 'grep -q "$TODAY"' not in text, (
        "run-monitor.sh must not use unanchored grep -q for holiday check"
    )


def test_lib_run_sh_defines_both_functions():
    """spec §6.3: ops/launchd/lib-run.sh must define both acquire_lock and
    run_with_watchdog (the entire public interface, spec §3)."""
    text = (_OPS / "lib-run.sh").read_text(encoding="utf-8")
    assert "acquire_lock()" in text, "lib-run.sh must define acquire_lock()"
    assert "run_with_watchdog()" in text, "lib-run.sh must define run_with_watchdog()"


# ---- Task 8: edge health gathering per run-kind + flow-capture outcome ----

_HFIX = Path(__file__).parents[1] / "notify" / "fixtures" / "health"


def _read_fix(name: str) -> str:
    return (_HFIX / name).read_text(encoding="utf-8")


def _seed_monitor(root: Path, day: str, trace: str = "eval_trace.json") -> None:
    md = root / "outputs" / day / "monitor"
    md.mkdir(parents=True)
    (md / "monitor.json").write_text("{}", encoding="utf-8")
    (md / "eval_trace.json").write_text(_read_fix(trace), encoding="utf-8")
    dd = root / "data" / "monitor"
    dd.mkdir(parents=True)
    (dd / "fund_flow_series.json").write_text(_read_fix("fund_flow_series.json"), encoding="utf-8")


def _seed_rotation(root: Path, day: str, fixture: str) -> None:
    rot = root / "outputs" / day / "rotation"
    rot.mkdir(parents=True)
    (rot / "rotation_radar.json").write_text(_read_fix(fixture), encoding="utf-8")


def test_build_monitor_health_attaches_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 7))
    _seed_monitor(tmp_path, "2026-07-07")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="monitor", last_exit_code=0)
    assert outcome.health is not None
    texts = " · ".join(i.text for i in outcome.health.items)
    assert "板块PE: STALE-1" in texts
    assert "滞后>3td" in texts


def test_build_monitor_health_dark_degrades(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 7))
    _seed_monitor(tmp_path, "2026-07-07", trace="eval_trace_dark.json")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="monitor", last_exit_code=0)
    d = classify_run_outcome(outcome, notify_on_clean=False)
    assert d.severity == "degraded"
    assert d.should_notify is True
    assert "DARK" in d.body


def test_build_monitor_health_corrupt_trace_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 7))
    md = tmp_path / "outputs" / "2026-07-07" / "monitor"
    md.mkdir(parents=True)
    (md / "monitor.json").write_text("{}", encoding="utf-8")
    (md / "eval_trace.json").write_text("{bad json", encoding="utf-8")
    (tmp_path / "data" / "monitor").mkdir(parents=True)
    (tmp_path / "data" / "monitor" / "fund_flow_series.json").write_text("{}", encoding="utf-8")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="monitor", last_exit_code=0)
    d = classify_run_outcome(outcome)
    assert "health unknown" in d.body


def test_build_weekly_health_dxy_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 7))
    out = tmp_path / "outputs" / "2026-07-07"
    out.mkdir(parents=True)
    (out / "decision_report.json").write_text(
        json.dumps({"summary": {"actionable_buy_count": 0, "trim_count": 0,
                                 "exit_count": 0, "review_count": 0}}), encoding="utf-8")
    (out / "gold_regime.json").write_text(_read_fix("gold_regime.json"), encoding="utf-8")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="weekly", last_exit_code=0)
    d = classify_run_outcome(outcome)
    assert "DXY 滞后 21d" in d.body


def test_flow_capture_abstain_is_degraded(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 5))
    _seed_rotation(tmp_path, "2026-07-05", "rotation_radar_abstain.json")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="flow-capture", last_exit_code=0)
    d = classify_run_outcome(outcome, notify_on_clean=False)
    assert d.severity == "degraded"
    assert "弃权" in d.body and "连续第 1 日" in d.body


def test_flow_capture_recovery_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 6))
    _seed_rotation(tmp_path, "2026-07-05", "rotation_radar_abstain.json")
    _seed_rotation(tmp_path, "2026-07-06", "rotation_radar_ok.json")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="flow-capture", last_exit_code=0)
    assert outcome.recovery_notice == "轮动雷达恢复 ok (200 boards) — 此前弃权 1 日"
    d = classify_run_outcome(outcome, notify_on_clean=False)
    assert d.severity == "clean"
    assert d.should_notify is True


def test_flow_capture_silent_when_ok_after_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 6))
    _seed_rotation(tmp_path, "2026-07-05", "rotation_radar_ok.json")
    _seed_rotation(tmp_path, "2026-07-06", "rotation_radar_ok.json")
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="flow-capture", last_exit_code=0)
    d = classify_run_outcome(outcome, notify_on_clean=False)
    assert d.should_notify is False  # ok-after-ok, no recovery, no page


def test_flow_capture_missing_radar_is_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 5))
    (tmp_path / "outputs" / "2026-07-05").mkdir(parents=True)  # dir but no rotation_radar.json
    outcome = notify_cmd._build_outcome(tmp_path, run_kind="flow-capture", last_exit_code=0)
    d = classify_run_outcome(outcome)
    assert d.severity == "failed"


def test_flow_capture_coverage_counts_newest_equal_today():
    flow = {"A": [["2026-07-07", 1.0]], "B": [["2026-07-06", 2.0]], "C": [["2026-07-07", 3.0]]}
    assert notify_cmd._flow_capture_coverage(flow, date(2026, 7, 7)) == (2, 3)


def test_notify_status_run_kind_lists_flow_capture():
    result = CliRunner().invoke(main, ["notify-status", "--help"])
    assert "flow-capture" in result.output


def test_notify_status_flow_capture_missing_dir_exits_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(notify_cmd, "_china_today", lambda: date(2026, 7, 5))
    monkeypatch.setattr(notify_cmd, "_send_macos", lambda d: None)  # no real osascript
    monkeypatch.delenv("IRC_FEISHU_WEBHOOK_URL", raising=False)
    result = CliRunner().invoke(
        main,
        ["notify-status", "--run-kind", "flow-capture", "--last-exit-code", "0",
         "--repo-root", str(tmp_path), "--no-notify-on-clean"],
    )
    assert result.exit_code == 0, result.output
