"""Regression tests for the weekly launchd agent (com.irc.weekly).

The weekly full pipeline lost its schedule when com.irc.weekly-full was
removed in the monitor migration (2026-06-15); these tests pin the restored
wrapper/plist to the run-monitor.sh pattern: lib-run.sh lock + watchdog,
fresh per-run log, /dev/null launchd log paths (com.apple.provenance trap),
decision_report.json completion sentinel, notify-status --run-kind weekly.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]
_OPS = _REPO_ROOT / "ops" / "launchd"


def _wrapper() -> str:
    return (_OPS / "run-weekly.sh").read_text(encoding="utf-8")


def _plist() -> str:
    return (_OPS / "com.irc.weekly.plist").read_text(encoding="utf-8")


def test_weekly_wrapper_parses() -> None:
    subprocess.run(["bash", "-n", str(_OPS / "run-weekly.sh")], check=True)


def test_weekly_wrapper_uses_lock_watchdog_and_notify() -> None:
    text = _wrapper()
    assert "source ops/launchd/lib-run.sh" in text
    assert 'acquire_lock "outputs/_logs/.weekly.lock"' in text
    assert 'run_with_watchdog "${IRC_WEEKLY_TIMEOUT:-' in text
    assert "notify-status --run-kind weekly" in text


def test_weekly_wrapper_idempotency_sentinel_is_decision_report() -> None:
    """decision_report.json is the LAST stage's output — the only artifact
    proving the whole 9-stage chain completed."""
    text = _wrapper()
    assert 'SENTINEL="outputs/$TODAY/decision_report.json"' in text


def test_weekly_wrapper_writes_own_fresh_log() -> None:
    text = _wrapper()
    assert "outputs/_logs/run-weekly." in text
    assert "run-weekly.*.log" in text  # 14-day prune


def test_weekly_plist_fires_saturday_morning_and_logs_to_devnull() -> None:
    text = _plist()
    assert "<string>com.irc.weekly</string>" in text
    assert "run-weekly.sh" in text
    assert "<key>Weekday</key><integer>6</integer>" in text
    assert "<key>Hour</key><integer>9</integer>" in text
    assert text.count("<string>/dev/null</string>") == 2
    assert "<key>RunAtLoad</key>" in text


def test_install_and_uninstall_know_the_weekly_agent() -> None:
    install = (_OPS / "install.sh").read_text(encoding="utf-8")
    uninstall = (_OPS / "uninstall.sh").read_text(encoding="utf-8")
    assert "com.irc.weekly" in install
    assert "run-weekly.sh" in install
    assert "com.irc.weekly" in uninstall
    assert "run-weekly.sh" in uninstall


def test_uninstall_covers_every_installed_agent() -> None:
    """Pre-existing gap: uninstall.sh lagged install.sh (flow-capture was
    installable but not uninstallable). Keep the two label sets in sync."""
    uninstall = (_OPS / "uninstall.sh").read_text(encoding="utf-8")
    for label in ("com.irc.monitor", "com.irc.fundamentals-quarterly",
                  "com.irc.flow-capture", "com.irc.weekly"):
        assert label in uninstall, f"uninstall.sh missing {label}"


def test_weekly_wrapper_appends_best_effort_live_llm_eval_refresh() -> None:
    """OD-3 / report v4 item 001: two live eval runs, each watchdog-bounded and
    individually || echo-guarded; the wrapper's exit code stays the pipeline rc.
    The `env` prefix is LOAD-BEARING (RD-3): run_with_watchdog execs "$@" — a
    bare IRC_RUN_LIVE_LLM_EVAL=1 word would be exec'd as a command NAME
    (rc 127, silently masked by the best-effort guard) because bash parses
    assignments before word expansion. Pin the exact env form."""
    text = _wrapper()
    assert text.count(
        'run_with_watchdog "${IRC_WEEKLY_EVAL_TIMEOUT:-900}" env IRC_RUN_LIVE_LLM_EVAL=1'
    ) == 2
    assert "irc eval monitor_impact" in text
    assert "irc eval monitor_narrative" in text


def test_weekly_eval_refresh_after_notify_and_never_changes_wrapper_rc() -> None:
    """Placement (open question 6): after notify-status (a hung eval can never
    delay paging), before exit "$rc" (eval outcomes never touch the rc). The
    sentinel/lock early-exits precede the append point, so a skipped day skips
    the evals too (criterion 13)."""
    text = _wrapper()
    notify_pos = text.index("notify-status --run-kind weekly")
    impact_pos = text.index("irc eval monitor_impact")
    narrative_pos = text.index("irc eval monitor_narrative")
    exit_pos = text.rindex('exit "$rc"')
    assert notify_pos < impact_pos < narrative_pos < exit_pos
    assert text.rstrip().endswith('exit "$rc"')
    assert text.index('SENTINEL=') < impact_pos
    assert text.index('acquire_lock "outputs/_logs/.weekly.lock"') < impact_pos
