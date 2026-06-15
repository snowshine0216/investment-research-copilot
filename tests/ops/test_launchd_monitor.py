"""Content-assertion tests for the monitor and fundamentals-quarterly launchd artifacts.

These tests validate file/plist/script CONTENT — they do NOT execute launchctl,
install.sh, or uninstall.sh (those are deploy-time steps the user performs after
landing the branch). All assertions are grep/text checks on the source files.
"""
from __future__ import annotations

import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
_OPS = _REPO_ROOT / "ops" / "launchd"

# ---------------------------------------------------------------------------
# Plist content assertions
# ---------------------------------------------------------------------------


def test_monitor_plist_label() -> None:
    """com.irc.monitor.plist must declare the correct label."""
    text = (_OPS / "com.irc.monitor.plist").read_text(encoding="utf-8")
    assert "<string>com.irc.monitor</string>" in text


def test_monitor_plist_fires_at_0900() -> None:
    """com.irc.monitor.plist must fire at Hour 9 (09:00 primary)."""
    text = (_OPS / "com.irc.monitor.plist").read_text(encoding="utf-8")
    assert "<integer>9</integer>" in text, (
        "monitor plist missing 09:00 Hour entry"
    )


def test_monitor_plist_fires_at_1300() -> None:
    """com.irc.monitor.plist must fire at Hour 13 (13:00 retry)."""
    text = (_OPS / "com.irc.monitor.plist").read_text(encoding="utf-8")
    assert "<integer>13</integer>" in text, (
        "monitor plist missing 13:00 Hour entry"
    )


def test_monitor_plist_no_weekend_fires() -> None:
    """com.irc.monitor.plist must not schedule weekend fires (Weekday 6 or 7)."""
    text = (_OPS / "com.irc.monitor.plist").read_text(encoding="utf-8")
    # Weekend = launchd Weekday 6 (Sat) or 7 (Sun)
    assert "<integer>6</integer>" not in text, "monitor plist must not fire on Saturday"
    assert "<integer>7</integer>" not in text, "monitor plist must not fire on Sunday"


def test_monitor_plist_logs_to_devnull() -> None:
    """com.irc.monitor.plist must route both stdout and stderr to /dev/null
    (com.apple.provenance reopen-denial fix)."""
    text = (_OPS / "com.irc.monitor.plist").read_text(encoding="utf-8")
    assert text.count("<string>/dev/null</string>") >= 2, (
        "com.irc.monitor.plist: StandardOutPath and StandardErrorPath must both be /dev/null"
    )


def test_monitor_plist_run_at_load_false() -> None:
    """com.irc.monitor.plist must not run at load (RunAtLoad false)."""
    text = (_OPS / "com.irc.monitor.plist").read_text(encoding="utf-8")
    assert "<false/>" in text, "com.irc.monitor.plist RunAtLoad must be false"


def test_fundamentals_quarterly_plist_label() -> None:
    """com.irc.fundamentals-quarterly.plist must declare the correct label."""
    text = (_OPS / "com.irc.fundamentals-quarterly.plist").read_text(encoding="utf-8")
    assert "<string>com.irc.fundamentals-quarterly</string>" in text


def test_fundamentals_quarterly_plist_fires_quarterly() -> None:
    """com.irc.fundamentals-quarterly.plist must fire in months 1, 4, 7, and 10."""
    text = (_OPS / "com.irc.fundamentals-quarterly.plist").read_text(encoding="utf-8")
    for month in (1, 4, 7, 10):
        assert f"<integer>{month}</integer>" in text, (
            f"fundamentals-quarterly plist missing Month {month}"
        )


def test_fundamentals_quarterly_plist_fires_on_day_1() -> None:
    """com.irc.fundamentals-quarterly.plist must fire on Day 1."""
    text = (_OPS / "com.irc.fundamentals-quarterly.plist").read_text(encoding="utf-8")
    assert "<key>Day</key>" in text


def test_fundamentals_quarterly_plist_fires_at_0800() -> None:
    """com.irc.fundamentals-quarterly.plist must fire at Hour 8 (08:00)."""
    text = (_OPS / "com.irc.fundamentals-quarterly.plist").read_text(encoding="utf-8")
    assert "<integer>8</integer>" in text, (
        "fundamentals-quarterly plist missing 08:00 Hour entry"
    )


def test_fundamentals_quarterly_plist_logs_to_devnull() -> None:
    """com.irc.fundamentals-quarterly.plist must route both channels to /dev/null."""
    text = (_OPS / "com.irc.fundamentals-quarterly.plist").read_text(encoding="utf-8")
    assert text.count("<string>/dev/null</string>") >= 2, (
        "com.irc.fundamentals-quarterly.plist: both StandardOutPath and "
        "StandardErrorPath must be /dev/null"
    )


# ---------------------------------------------------------------------------
# Wrapper script content assertions
# ---------------------------------------------------------------------------


def test_run_monitor_sh_redirects_to_devnull() -> None:
    """run-monitor.sh must route launchd channels to /dev/null via exec redirect
    (provenance-xattr fix): it writes its own log and execs stdout/stderr there."""
    text = (_OPS / "run-monitor.sh").read_text(encoding="utf-8")
    # The wrapper should redirect to its own log file (not /dev/null in the script).
    # The plist is what points launchd to /dev/null; the wrapper execs to its own log.
    assert "exec >> " in text, "run-monitor.sh must redirect its own output to a log file"
    assert "/dev/null" not in text or "2>/dev/null" in text, (
        "run-monitor.sh must not send its own output to /dev/null; "
        "it should write a per-run log"
    )


def test_run_monitor_sh_has_trading_day_gate() -> None:
    """run-monitor.sh must include a trading-day gate that skips weekends."""
    text = (_OPS / "run-monitor.sh").read_text(encoding="utf-8")
    assert "DOW" in text and 'date +%u' in text, (
        "run-monitor.sh must check day-of-week via TZ=Asia/Shanghai date +%u"
    )
    assert "weekend" in text.lower(), "run-monitor.sh must log a 'weekend' skip message"


def test_run_monitor_sh_has_report_idempotency_guard() -> None:
    """run-monitor.sh must skip if report.html already exists (retry-only idempotency)."""
    text = (_OPS / "run-monitor.sh").read_text(encoding="utf-8")
    assert "report.html" in text, (
        "run-monitor.sh must check for report.html as its idempotency sentinel"
    )


def test_run_monitor_sh_calls_notify_status_with_monitor_kind() -> None:
    """run-monitor.sh must call notify-status --run-kind monitor."""
    text = (_OPS / "run-monitor.sh").read_text(encoding="utf-8")
    assert "notify-status" in text and "--run-kind monitor" in text, (
        "run-monitor.sh must invoke notify-status --run-kind monitor"
    )


def test_run_monitor_sh_passes() -> None:
    """run-monitor.sh must pass bash -n syntax check."""
    result = subprocess.run(
        ["bash", "-n", str(_OPS / "run-monitor.sh")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"run-monitor.sh bash -n failed:\n{result.stderr}"
    )


def test_run_fundamentals_sh_calls_irc_monitor_snapshot() -> None:
    """run-fundamentals.sh must call `irc monitor snapshot` (typed per-fund path)."""
    text = (_OPS / "run-fundamentals.sh").read_text(encoding="utf-8")
    assert "irc monitor snapshot" in text, (
        "run-fundamentals.sh must call `irc monitor snapshot` (not broad-index path)"
    )


def test_run_fundamentals_sh_logs_to_own_file() -> None:
    """run-fundamentals.sh must write its own per-run log (exec redirect)."""
    text = (_OPS / "run-fundamentals.sh").read_text(encoding="utf-8")
    assert "exec >> " in text, "run-fundamentals.sh must redirect output to a per-run log"


def test_run_fundamentals_sh_passes() -> None:
    """run-fundamentals.sh must pass bash -n syntax check."""
    result = subprocess.run(
        ["bash", "-n", str(_OPS / "run-fundamentals.sh")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"run-fundamentals.sh bash -n failed:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# install.sh / uninstall.sh array content assertions
# ---------------------------------------------------------------------------


def test_install_sh_labels_contain_monitor() -> None:
    """install.sh LABELS must include com.irc.monitor."""
    text = (_OPS / "install.sh").read_text(encoding="utf-8")
    assert "com.irc.monitor" in text


def test_install_sh_labels_contain_fundamentals_quarterly() -> None:
    """install.sh LABELS must include com.irc.fundamentals-quarterly."""
    text = (_OPS / "install.sh").read_text(encoding="utf-8")
    assert "com.irc.fundamentals-quarterly" in text


def test_install_sh_no_longer_references_com_irc_daily() -> None:
    """install.sh must not reference the removed com.irc.daily job in its arrays."""
    text = (_OPS / "install.sh").read_text(encoding="utf-8")
    # com.irc.daily must not appear as a LABELS/WRAPPERS array entry
    import re
    array_match = re.search(r'LABELS=\([^)]*\)', text)
    if array_match:
        assert "com.irc.daily" not in array_match.group(), (
            "install.sh LABELS array must not include com.irc.daily"
        )


def test_install_sh_cold_start_snapshot() -> None:
    """install.sh must invoke `irc monitor snapshot` as a cold-start bootstrap."""
    text = (_OPS / "install.sh").read_text(encoding="utf-8")
    assert "irc monitor snapshot" in text, (
        "install.sh must call `irc monitor snapshot` for cold-start bootstrap"
    )


def test_install_sh_tz_warning_references_new_times() -> None:
    """install.sh TZ warning must mention 09:00/13:00 (not the old 17:30)."""
    text = (_OPS / "install.sh").read_text(encoding="utf-8")
    assert "+0800" in text, "install.sh must still check for UTC+8 offset"
    assert "WARNING" in text, "install.sh must still emit a WARNING when TZ != +0800"


def test_uninstall_sh_labels_contain_monitor() -> None:
    """uninstall.sh LABELS must include com.irc.monitor."""
    text = (_OPS / "uninstall.sh").read_text(encoding="utf-8")
    assert "com.irc.monitor" in text


def test_uninstall_sh_labels_contain_fundamentals_quarterly() -> None:
    """uninstall.sh LABELS must include com.irc.fundamentals-quarterly."""
    text = (_OPS / "uninstall.sh").read_text(encoding="utf-8")
    assert "com.irc.fundamentals-quarterly" in text


# ---------------------------------------------------------------------------
# Plist XML validity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "plist_name",
    ["com.irc.monitor.plist", "com.irc.fundamentals-quarterly.plist"],
)
def test_plist_is_valid_xml(plist_name: str) -> None:
    """New plists must be valid XML (plutil -lint)."""
    result = subprocess.run(
        ["plutil", "-lint", str(_OPS / plist_name)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"{plist_name} failed plutil -lint:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Wrapper integration: monitor idempotency + gate (content-level)
# ---------------------------------------------------------------------------


def _make_stub(tmp_path: Path, exit_code: int) -> tuple[Path, Path]:
    argv_log = tmp_path / "stub_argv.log"
    stub = tmp_path / "uv"
    stub.write_text(
        textwrap.dedent(f"""\
            #!/bin/bash
            echo "$@" >> {argv_log}
            for arg in "$@"; do
              if [ "$arg" = "notify-status" ]; then exit 0; fi
            done
            exit {exit_code}
        """),
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub, argv_log


def _template_wrapper(src: Path, tmp_path: Path, stub: Path) -> Path:
    text = src.read_text(encoding="utf-8")
    text = text.replace("__UV_BIN__", str(stub))
    text = text.replace("__REPO_ROOT__", str(tmp_path))
    out = tmp_path / src.name
    out.write_text(text, encoding="utf-8")
    out.chmod(out.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return out


def _make_date_stub(tmp_path: Path, day: str, dow: str) -> Path:
    bin_dir = tmp_path / "datebin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "date"
    stub.write_text(
        textwrap.dedent(f"""\
            #!/bin/bash
            case "$1" in
              "+%Y-%m-%d") echo "{day}" ;;
              "+%u") echo "{dow}" ;;
              *) exec /bin/date "$@" ;;
            esac
        """),
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _run_wrapper(wrapper: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    merged = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        ["bash", str(wrapper)],
        capture_output=True,
        text=True,
        timeout=30,
        env=merged,
    )


def _read_argv(argv_log: Path) -> list[str]:
    if not argv_log.exists():
        return []
    return [ln for ln in argv_log.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _read_run_log(tmp_path: Path, prefix: str) -> str:
    log_dir = tmp_path / "outputs" / "_logs"
    if not log_dir.exists():
        return ""
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted(log_dir.glob(f"{prefix}.*.log"))
    )


_GATE_OPEN = ("2026-06-10", "3")   # Wednesday
_GATE_CLOSED = ("2026-06-14", "6")  # Saturday


def test_monitor_wrapper_skips_weekend(tmp_path: Path) -> None:
    """run-monitor.sh must exit 0 without calling uv on a CN weekend."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    wrapper = _template_wrapper(_OPS / "run-monitor.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_CLOSED)
    result = _run_wrapper(wrapper, {"PATH": f"{date_bin}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 0
    assert _read_argv(argv_log) == [], "gate must not call uv on a weekend"
    assert "weekend" in _read_run_log(tmp_path, "run-monitor")


def test_monitor_wrapper_skips_when_report_exists(tmp_path: Path) -> None:
    """run-monitor.sh must skip (exit 0) when report.html already exists."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    wrapper = _template_wrapper(_OPS / "run-monitor.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN)
    day = _GATE_OPEN[0]
    report_dir = tmp_path / "outputs" / day / "monitor"
    report_dir.mkdir(parents=True)
    (report_dir / "report.html").write_text("<html></html>", encoding="utf-8")
    result = _run_wrapper(wrapper, {"PATH": f"{date_bin}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 0
    assert _read_argv(argv_log) == [], "must skip when report.html already exists"
    assert "skipping" in _read_run_log(tmp_path, "run-monitor")


def test_monitor_wrapper_calls_notify_after_run(tmp_path: Path) -> None:
    """run-monitor.sh must call notify-status --run-kind monitor after irc monitor."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    wrapper = _template_wrapper(_OPS / "run-monitor.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN)
    _run_wrapper(wrapper, {"PATH": f"{date_bin}{os.pathsep}{os.environ['PATH']}"})
    invocations = _read_argv(argv_log)
    notify_calls = [ln for ln in invocations if "notify-status" in ln]
    assert notify_calls, "run-monitor.sh must call notify-status"
    assert any("--run-kind" in c and "monitor" in c for c in notify_calls), (
        f"notify-status not called with --run-kind monitor. Calls: {notify_calls}"
    )
