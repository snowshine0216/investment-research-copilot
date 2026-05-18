"""Gold_score runner tests against current producer contract.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/006-spec.md
"""
from __future__ import annotations

import json
from pathlib import Path

from evals.gold_score.runner import run


def _valid_regime() -> dict:
    return {
        "regime": "trending", "vol_ratio": 1.1, "adx": 22.0, "trend_sign": 1,
        "score": 60.0, "tilt": "neutral_plus", "zone": "A",
        "scenario": "reflation", "scenario_triggers": ["t1"],
    }


def _seed(repo_root: Path, date_iso: str, *, regime: dict | None, band: bool) -> Path:
    out = repo_root / "outputs" / date_iso
    out.mkdir(parents=True, exist_ok=True)
    if regime is not None:
        (out / "gold_regime.json").write_text(
            json.dumps(regime, ensure_ascii=False), encoding="utf-8",
        )
    if band:
        (out / "gold_band.yaml").write_text("score: 60\n", encoding="utf-8")
    return out


def test_gold_score_runner_fails_when_input_missing(tmp_path: Path) -> None:
    rc = run(tmp_path)
    assert rc == 2
    candidates = list((tmp_path / "outputs").rglob("evals/gold_score/report.json"))
    assert candidates
    body = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"


def test_gold_score_runner_fails_when_band_missing(tmp_path: Path) -> None:
    """Locator requires both files in the contract; partial set must FAIL."""
    _seed(tmp_path, "2026-05-17", regime=_valid_regime(), band=False)
    rc = run(tmp_path)
    assert rc == 2


def test_gold_score_runner_passes_against_valid_regime(tmp_path: Path) -> None:
    date_iso = "2026-05-17"
    _seed(tmp_path, date_iso, regime=_valid_regime(), band=True)
    rc = run(tmp_path)
    assert rc == 0
    body = json.loads(
        (tmp_path / "outputs" / date_iso / "evals" / "gold_score" / "report.json")
        .read_text(encoding="utf-8")
    )
    assert {m["name"] for m in body["metrics"]} == {
        "gold_regime_schema_completeness",
        "gold_tilt_valid_enum",
        "gold_score_in_range",
    }
    assert all(m["status"] == "PASS" for m in body["metrics"])
    assert "Phase 2" in body["notes"]


def test_gold_score_runner_fails_on_invalid_tilt(tmp_path: Path) -> None:
    regime = _valid_regime()
    regime["tilt"] = "very_overweight"  # not a valid enum
    _seed(tmp_path, "2026-05-17", regime=regime, band=True)
    rc = run(tmp_path)
    assert rc == 2
    body = json.loads(
        (tmp_path / "outputs" / "2026-05-17" / "evals" / "gold_score" / "report.json")
        .read_text(encoding="utf-8")
    )
    tilt_metric = next(m for m in body["metrics"] if m["name"] == "gold_tilt_valid_enum")
    assert tilt_metric["status"] == "FAIL"


def test_gold_score_runner_fails_on_partial_schema(tmp_path: Path) -> None:
    regime = {"regime": "trending", "tilt": "neutral", "score": 50.0}  # 3 / 9
    _seed(tmp_path, "2026-05-17", regime=regime, band=True)
    rc = run(tmp_path)
    assert rc == 2
    body = json.loads(
        (tmp_path / "outputs" / "2026-05-17" / "evals" / "gold_score" / "report.json")
        .read_text(encoding="utf-8")
    )
    schema_metric = next(m for m in body["metrics"] if m["name"] == "gold_regime_schema_completeness")
    assert schema_metric["status"] == "FAIL"


def test_gold_score_runner_writes_under_artifact_date(tmp_path: Path) -> None:
    date_iso = "2026-05-14"
    _seed(tmp_path, date_iso, regime=_valid_regime(), band=True)
    run(tmp_path)
    assert (tmp_path / "outputs" / date_iso / "evals" / "gold_score" / "report.json").exists()
