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


def test_monitor_plist_fires_at_1215() -> None:
    """com.irc.monitor.plist must fire once daily at 12:15 (Hour 12, Minute 15)."""
    text = (_OPS / "com.irc.monitor.plist").read_text(encoding="utf-8")
    assert "<integer>12</integer>" in text, "monitor plist missing 12:00 Hour entry"
    assert "<integer>15</integer>" in text, "monitor plist missing :15 Minute entry"


def test_monitor_plist_has_no_legacy_0900_1300_fires() -> None:
    """The single-daily 12:15 schedule replaced the old 09:00 + 13:00 pair; neither
    legacy Hour entry may remain."""
    text = (_OPS / "com.irc.monitor.plist").read_text(encoding="utf-8")
    assert "<integer>9</integer>" not in text, "monitor plist must not fire at 09:00"
    assert "<integer>13</integer>" not in text, "monitor plist must not fire at 13:00"


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


def test_run_monitor_sh_has_monitor_json_idempotency_guard() -> None:
    """run-monitor.sh must key its once-per-day skip on monitor.json — the LAST
    atomic write in _write_outputs — so a partial output set (report.html written,
    crash before monitor.json) is NOT mistaken for a completed run."""
    text = (_OPS / "run-monitor.sh").read_text(encoding="utf-8")
    assert "monitor.json" in text, (
        "run-monitor.sh must check for monitor.json as its idempotency sentinel"
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
    # Make lib-run.sh available under tmp_path/ops/launchd/ so the `source` line
    # in wrappers (resolved relative to cd "$REPO_ROOT" == tmp_path) can find it.
    lib_dst = tmp_path / "ops" / "launchd"
    lib_dst.mkdir(parents=True, exist_ok=True)
    lib_src = _OPS / "lib-run.sh"
    if lib_src.exists():
        (lib_dst / "lib-run.sh").write_text(lib_src.read_text(encoding="utf-8"), encoding="utf-8")
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


def test_monitor_wrapper_skips_when_monitor_json_exists(tmp_path: Path) -> None:
    """run-monitor.sh must skip (exit 0) when monitor.json (the completion
    sentinel) already exists."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    wrapper = _template_wrapper(_OPS / "run-monitor.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN)
    day = _GATE_OPEN[0]
    report_dir = tmp_path / "outputs" / day / "monitor"
    report_dir.mkdir(parents=True)
    (report_dir / "monitor.json").write_text("{}", encoding="utf-8")
    result = _run_wrapper(wrapper, {"PATH": f"{date_bin}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 0
    assert _read_argv(argv_log) == [], "must skip when monitor.json already exists"
    assert "skipping" in _read_run_log(tmp_path, "run-monitor")


def test_monitor_wrapper_does_not_skip_on_partial_output(tmp_path: Path) -> None:
    """Regression: a partial output set (report.html present but monitor.json
    absent — a crash between the two atomic writes) must NOT trigger the
    once-per-day skip; the wrapper must re-run `irc monitor`."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    wrapper = _template_wrapper(_OPS / "run-monitor.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN)
    day = _GATE_OPEN[0]
    report_dir = tmp_path / "outputs" / day / "monitor"
    report_dir.mkdir(parents=True)
    (report_dir / "report.html").write_text("<html></html>", encoding="utf-8")
    result = _run_wrapper(wrapper, {"PATH": f"{date_bin}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 0
    invocations = _read_argv(argv_log)
    assert any("monitor" in ln for ln in invocations), (
        "wrapper must re-run irc monitor when only report.html (not monitor.json) exists"
    )


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


# ---------------------------------------------------------------------------
# Wrapper integration: watchdog timeout-kill + single-instance lock (item 001)
# ---------------------------------------------------------------------------


def _make_sleepy_uv_stub(tmp_path: Path, monitor_sleep: int) -> tuple[Path, Path]:
    """A stub `uv` whose `irc monitor` sleeps <monitor_sleep>s (to be killed by
    the watchdog) but whose `notify-status` returns instantly with exit 0.
    Records every argv line to stub_argv.log."""
    argv_log = tmp_path / "stub_argv.log"
    stub = tmp_path / "uv"
    stub.write_text(
        textwrap.dedent(f"""\
            #!/bin/bash
            echo "$@" >> {argv_log}
            for arg in "$@"; do
              if [ "$arg" = "notify-status" ]; then exit 0; fi
            done
            # irc monitor / irc monitor snapshot: sleep so the watchdog has
            # something to kill.
            sleep {monitor_sleep}
            exit 0
        """),
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub, argv_log


def test_monitor_wrapper_watchdog_kills_and_notifies_124(tmp_path: Path) -> None:
    """A monitor run that overruns IRC_MONITOR_TIMEOUT is killed by the watchdog,
    and the wrapper calls notify-status with --last-exit-code 124 (spec §4.1)."""
    stub, argv_log = _make_sleepy_uv_stub(tmp_path, monitor_sleep=30)
    wrapper = _template_wrapper(_OPS / "run-monitor.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN)
    result = _run_wrapper(
        wrapper,
        {
            "PATH": f"{date_bin}{os.pathsep}{os.environ['PATH']}",
            "IRC_MONITOR_TIMEOUT": "1",
            "IRC_WATCHDOG_POLL": "0.2",
        },
    )
    assert result.returncode == 124, (
        f"wrapper must exit 124 on watchdog kill; got {result.returncode}. "
        f"log:\n{_read_run_log(tmp_path, 'run-monitor')}"
    )
    invocations = _read_argv(argv_log)
    notify = [ln for ln in invocations if "notify-status" in ln]
    assert notify, f"notify-status must be called after a timeout. argv: {invocations}"
    assert any("--last-exit-code 124" in ln for ln in notify), (
        f"notify-status must receive --last-exit-code 124. notify calls: {notify}"
    )


def test_fundamentals_wrapper_watchdog_kills_and_exits_124_without_notify(
    tmp_path: Path,
) -> None:
    """A snapshot run that overruns IRC_SNAPSHOT_TIMEOUT is killed (exit 124),
    and NO notify-status is called (protective-only asymmetry, spec §4.2)."""
    stub, argv_log = _make_sleepy_uv_stub(tmp_path, monitor_sleep=30)
    wrapper = _template_wrapper(_OPS / "run-fundamentals.sh", tmp_path, stub)
    result = _run_wrapper(
        wrapper,
        {"IRC_SNAPSHOT_TIMEOUT": "1", "IRC_WATCHDOG_POLL": "0.2"},
    )
    assert result.returncode == 124, (
        f"snapshot wrapper must exit 124 on watchdog kill; got {result.returncode}. "
        f"log:\n{_read_run_log(tmp_path, 'run-fundamentals')}"
    )
    invocations = _read_argv(argv_log)
    assert not any("notify-status" in ln for ln in invocations), (
        f"run-fundamentals.sh must NOT call notify-status (protective-only). argv: {invocations}"
    )


def test_fundamentals_wrapper_skips_when_snapshot_lock_held(tmp_path: Path) -> None:
    """When .snapshot.lock is held by a LIVE pid, the wrapper skips (exit 0) and
    never runs the snapshot (spec §4.2 / §4.3 per-wrapper locks)."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    wrapper = _template_wrapper(_OPS / "run-fundamentals.sh", tmp_path, stub)
    lock = tmp_path / "outputs" / "_logs" / ".snapshot.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(str(os.getpid()), encoding="utf-8")
    result = _run_wrapper(wrapper)
    assert result.returncode == 0, result.stderr
    assert not any("snapshot" in ln for ln in _read_argv(argv_log)), (
        f"snapshot must NOT run while .snapshot.lock is held. argv: {_read_argv(argv_log)}"
    )


def test_monitor_wrapper_skips_when_lock_held(tmp_path: Path) -> None:
    """When .monitor.lock is held by a LIVE pid, the wrapper skips (exit 0) and
    never calls `uv run irc monitor` (spec §4.1: silent skip-on-contention)."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    wrapper = _template_wrapper(_OPS / "run-monitor.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN)
    # Pre-create the lock dir held by THIS process (alive for the call duration).
    lock = tmp_path / "outputs" / "_logs" / ".monitor.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(str(os.getpid()), encoding="utf-8")
    result = _run_wrapper(wrapper, {"PATH": f"{date_bin}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 0, result.stderr
    invocations = _read_argv(argv_log)
    assert not any(
        "monitor" in ln and "notify-status" not in ln and "snapshot" not in ln
        for ln in invocations
    ), f"uv must NOT be called for `irc monitor` while the lock is held. argv: {invocations}"
