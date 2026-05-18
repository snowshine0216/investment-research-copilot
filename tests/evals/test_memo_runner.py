"""Memo runner tests against current producer contract.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/009-spec.md
"""
from __future__ import annotations

import json
from pathlib import Path

from evals.memo.runner import run


_FULL_MEMO = (
    "## TL;DR\n.\n"
    "## 1. 当前组合\n.\n"
    "## 2. 推荐动作\n.\n"
    "## 3. 推导\n.\n"
    "## 4. 因子分解\n.\n"
    "## 5. 风险与证伪\n.\n"
    "## 6. 数据完整性\n.\n"
    "## 7. 用户覆盖记录\n.\n"
)


def _seed(
    repo_root: Path,
    date_iso: str,
    *,
    memo: str | None,
    traceability: dict | None,
) -> Path:
    out = repo_root / "outputs" / date_iso
    out.mkdir(parents=True, exist_ok=True)
    if memo is not None:
        (out / "memo.md").write_text(memo, encoding="utf-8")
    if traceability is not None:
        (out / "memo_traceability.json").write_text(
            json.dumps(traceability), encoding="utf-8",
        )
    return out


def test_memo_runner_fails_when_input_missing(tmp_path: Path) -> None:
    rc = run(tmp_path)
    assert rc == 2
    candidates = list((tmp_path / "outputs").rglob("evals/memo/report.json"))
    assert candidates
    body = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"


def test_memo_runner_fails_when_traceability_missing(tmp_path: Path) -> None:
    """Locator requires both files; partial set must FAIL."""
    _seed(tmp_path, "2026-05-17", memo=_FULL_MEMO, traceability=None)
    rc = run(tmp_path)
    assert rc == 2


def test_memo_runner_passes_against_valid_memo(tmp_path: Path) -> None:
    date_iso = "2026-05-17"
    _seed(tmp_path, date_iso, memo=_FULL_MEMO,
          traceability={"n_refs_provided": 10, "n_refs_quoted_verbatim": 10, "n_refs": 10})
    rc = run(tmp_path)
    assert rc == 0
    body = json.loads(
        (tmp_path / "outputs" / date_iso / "evals" / "memo" / "report.json")
        .read_text(encoding="utf-8")
    )
    assert {m["name"] for m in body["metrics"]} == {"seven_sections_present", "verbatim_ref_rate"}
    assert all(m["status"] == "PASS" for m in body["metrics"])
    assert "Phase 2" in body["notes"]


def test_memo_runner_fails_on_missing_sections(tmp_path: Path) -> None:
    partial = "## TL;DR\n.\n## 1. 当前组合\n.\n"  # 2 of 8 sections
    _seed(tmp_path, "2026-05-17", memo=partial,
          traceability={"n_refs_provided": 0, "n_refs_quoted_verbatim": 0, "n_refs": 0})
    rc = run(tmp_path)
    assert rc == 2
    body = json.loads(
        (tmp_path / "outputs" / "2026-05-17" / "evals" / "memo" / "report.json")
        .read_text(encoding="utf-8")
    )
    sec = next(m for m in body["metrics"] if m["name"] == "seven_sections_present")
    assert sec["status"] == "FAIL"


def test_memo_runner_fails_on_low_verbatim_rate(tmp_path: Path) -> None:
    _seed(tmp_path, "2026-05-17", memo=_FULL_MEMO,
          traceability={"n_refs_provided": 10, "n_refs_quoted_verbatim": 3, "n_refs": 10})
    rc = run(tmp_path)
    assert rc == 2
    body = json.loads(
        (tmp_path / "outputs" / "2026-05-17" / "evals" / "memo" / "report.json")
        .read_text(encoding="utf-8")
    )
    ref = next(m for m in body["metrics"] if m["name"] == "verbatim_ref_rate")
    assert ref["status"] == "FAIL"
