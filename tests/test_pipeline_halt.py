from __future__ import annotations
from pathlib import Path
from irc.pipeline_halt import write_halted, write_halted_structured, HaltReason


def test_write_halted_creates_md(tmp_path: Path):
    write_halted(repo_root=tmp_path, date="2026-05-07", stage="scoring",
                  reason="sanity_check rho ≤ 0", remediation="Re-tune factor weights or check data feed.")
    p = tmp_path / "outputs/2026-05-07/PIPELINE_HALTED.md"
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "scoring" in content
    assert "rho" in content
    assert "Re-tune" in content


def test_halt_reason_round_trips_through_sidecar(tmp_path: Path):
    reason = HaltReason(
        kind="akshare_empty",
        stage="ingest",
        detail="every fetch returned 0 rows",
        stats={"price_attempts": 198, "price_successes": 0,
               "nav_attempts": 50, "nav_successes": 0},
        first_error="requests.ConnectionError: HTTPSConnectionPool(...): Max retries exceeded",
    )
    sidecar = tmp_path / ".halt_reason.json"
    HaltReason.write_sidecar(sidecar, reason)
    loaded = HaltReason.read_sidecar(sidecar)
    assert loaded == reason


def test_halt_reason_read_sidecar_returns_none_when_missing(tmp_path: Path):
    assert HaltReason.read_sidecar(tmp_path / "missing.json") is None


def test_halt_reason_read_sidecar_returns_none_on_corrupt_json(tmp_path: Path):
    sidecar = tmp_path / ".halt_reason.json"
    sidecar.write_text("{not valid json", encoding="utf-8")
    assert HaltReason.read_sidecar(sidecar) is None


def test_halt_reason_truncates_first_error():
    long_msg = "x" * 1000
    reason = HaltReason(kind="akshare_unreachable", stage="ingest",
                        detail="preflight failed", first_error=long_msg)
    assert reason.first_error is not None
    assert len(reason.first_error) <= 500


def test_write_halted_structured_renders_all_fields(tmp_path: Path):
    reason = HaltReason(
        kind="akshare_empty",
        stage="ingest",
        detail="every akshare fetch returned 0 rows",
        stats={"price_attempts": 198, "price_successes": 0,
               "nav_attempts": 50, "nav_successes": 0},
        first_error="requests.ConnectionError: Max retries exceeded with url: ...",
    )
    write_halted_structured(repo_root=tmp_path, date="2026-05-17", reason=reason)
    body = (tmp_path / "outputs/2026-05-17/PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "ingest" in body
    assert "akshare_empty" in body
    assert "every akshare fetch returned 0 rows" in body
    assert "price_attempts" in body and "198" in body
    assert "price_successes" in body and "0" in body
    assert "requests.ConnectionError" in body
    assert "Diagnostics" in body


def test_write_halted_structured_omits_stats_section_when_empty(tmp_path: Path):
    reason = HaltReason(
        kind="akshare_unreachable", stage="ingest",
        detail="preflight canary failed",
        first_error="ConnectionResetError: [Errno 54] Connection reset by peer",
    )
    write_halted_structured(repo_root=tmp_path, date="2026-05-17", reason=reason)
    body = (tmp_path / "outputs/2026-05-17/PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "akshare_unreachable" in body
    assert "preflight canary failed" in body
    assert "ConnectionResetError" in body
    assert "| Metric | Value |" not in body  # no stats table


def test_write_halted_structured_includes_remediation_for_known_kind(tmp_path: Path):
    reason = HaltReason(kind="akshare_unreachable", stage="ingest",
                        detail="preflight canary failed")
    write_halted_structured(repo_root=tmp_path, date="2026-05-17", reason=reason)
    body = (tmp_path / "outputs/2026-05-17/PIPELINE_HALTED.md").read_text(encoding="utf-8")
    assert "network" in body.lower() or "connectivity" in body.lower()

