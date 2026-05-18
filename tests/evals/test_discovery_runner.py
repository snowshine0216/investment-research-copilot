"""Discovery runner tests against the current CSV contract.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/005-spec.md
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from evals.discovery.runner import run


_CSV_COLUMNS: tuple[str, ...] = (
    "instrument_id", "ticker", "market", "name_cn", "asset_class", "currency",
    "tracked_index", "venue_required", "role", "reason_text", "cited_refs", "relaxed",
)


def _watchlist(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col in _CSV_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[list(_CSV_COLUMNS)]


def _write_csv(repo_root: Path, date_iso: str, df: pd.DataFrame) -> Path:
    out = repo_root / "outputs" / date_iso
    out.mkdir(parents=True, exist_ok=True)
    path = out / "discovered_watchlist.csv"
    df.to_csv(path, index=False)
    return path


def test_discovery_runner_fails_when_input_missing(tmp_path: Path) -> None:
    rc = run(tmp_path)
    assert rc == 2
    candidates = list((tmp_path / "outputs").rglob("evals/discovery/report.json"))
    assert candidates, "runner must write a FAIL report under the run date"
    body = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"


def test_discovery_runner_reads_dated_csv(tmp_path: Path) -> None:
    rows = [
        {"instrument_id": f"X{i}", "ticker": f"T{i}", "role": "core",
         "cited_refs": "ref-a,ref-b"}
        for i in range(10)
    ]
    date_iso = "2026-05-17"
    _write_csv(tmp_path, date_iso, _watchlist(rows))
    rc = run(tmp_path)
    assert rc in (0, 1)
    report_path = tmp_path / "outputs" / date_iso / "evals" / "discovery" / "report.json"
    assert report_path.exists()
    body = json.loads(report_path.read_text(encoding="utf-8"))
    assert {m["name"] for m in body["metrics"]} == {
        "candidates_per_role_min",
        "filter_integrity",
        "dedup",
        "llm_reason_grounding",
    }


def test_discovery_runner_fails_when_required_column_missing(tmp_path: Path) -> None:
    """A schema mismatch must surface as FAIL with the missing column named,
    not as a silently-degraded 1.0 metric."""
    rows = [{"ticker": "T1", "role": "core", "cited_refs": "ref"}]
    df = pd.DataFrame(rows)  # missing instrument_id intentionally
    _write_csv(tmp_path, "2026-05-17", df)
    rc = run(tmp_path)
    assert rc == 2
    body = json.loads(
        (tmp_path / "outputs" / "2026-05-17" / "evals" / "discovery" / "report.json")
        .read_text(encoding="utf-8")
    )
    assert body["overall"] == "FAIL"
    assert "instrument_id" in body["notes"]


def test_discovery_runner_prefers_today_over_yesterday(tmp_path: Path, monkeypatch) -> None:
    import evals._shared.locator as loc
    fixed = "2026-05-18"
    monkeypatch.setattr(loc, "_today_iso", lambda: fixed)
    today_rows = [
        {"instrument_id": f"X{i}", "ticker": f"T{i}", "role": "core", "cited_refs": "ref"}
        for i in range(10)
    ]
    yesterday_rows = [{"instrument_id": "STALE", "ticker": "STALE", "role": "core",
                       "cited_refs": "ref"}]
    _write_csv(tmp_path, "2026-05-17", _watchlist(yesterday_rows))
    _write_csv(tmp_path, fixed, _watchlist(today_rows))
    rc = run(tmp_path)
    assert rc in (0, 1)
    today_report = tmp_path / "outputs" / fixed / "evals" / "discovery" / "report.json"
    yesterday_report = tmp_path / "outputs" / "2026-05-17" / "evals" / "discovery" / "report.json"
    assert today_report.exists()
    assert not yesterday_report.exists()
