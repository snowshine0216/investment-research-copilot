"""Allocation runner tests against current YAML contract.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/007-spec.md
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from evals.allocation.runner import run


def _valid_payload() -> dict:
    return {
        "generated_at": "2026-05-17T08:00:00+08:00",
        "gold_tilt": "neutral",
        "target_weights_per_class": {"cn_etf": 0.5, "global_etf": 0.5},
        "selected_instruments": [
            {"instrument_id": "510300", "target_weight": 0.25},
            {"instrument_id": "510500", "target_weight": 0.25},
            {"instrument_id": "VTI", "target_weight": 0.25},
            {"instrument_id": "VXUS", "target_weight": 0.25},
        ],
        "dropped_due_to_correlation": [],
        "diagnostics": {},
    }


def _seed(repo_root: Path, date_iso: str, payload: dict | None) -> Path:
    out = repo_root / "outputs" / date_iso
    out.mkdir(parents=True, exist_ok=True)
    if payload is not None:
        (out / "proposed_allocation.yaml").write_text(
            yaml.safe_dump(payload, sort_keys=False), encoding="utf-8",
        )
    return out


def test_allocation_runner_fails_when_input_missing(tmp_path: Path) -> None:
    rc = run(tmp_path)
    assert rc == 2
    candidates = list((tmp_path / "outputs").rglob("evals/allocation/report.json"))
    assert candidates
    body = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"


def test_allocation_runner_passes_against_valid_yaml(tmp_path: Path) -> None:
    date_iso = "2026-05-17"
    _seed(tmp_path, date_iso, _valid_payload())
    rc = run(tmp_path)
    assert rc == 0
    body = json.loads(
        (tmp_path / "outputs" / date_iso / "evals" / "allocation" / "report.json")
        .read_text(encoding="utf-8")
    )
    assert {m["name"] for m in body["metrics"]} == {"weight_sum_deviation", "effective_n"}
    assert all(m["status"] == "PASS" for m in body["metrics"])
    assert "Phase 2" in body["notes"]


def test_allocation_runner_fails_when_weights_do_not_sum_to_one(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["target_weights_per_class"] = {"cn_etf": 0.3, "global_etf": 0.5}
    _seed(tmp_path, "2026-05-17", payload)
    rc = run(tmp_path)
    assert rc == 2
    body = json.loads(
        (tmp_path / "outputs" / "2026-05-17" / "evals" / "allocation" / "report.json")
        .read_text(encoding="utf-8")
    )
    dev = next(m for m in body["metrics"] if m["name"] == "weight_sum_deviation")
    assert dev["status"] == "FAIL"


def test_allocation_runner_writes_under_artifact_date(tmp_path: Path) -> None:
    date_iso = "2026-05-14"
    _seed(tmp_path, date_iso, _valid_payload())
    run(tmp_path)
    assert (tmp_path / "outputs" / date_iso / "evals" / "allocation" / "report.json").exists()
