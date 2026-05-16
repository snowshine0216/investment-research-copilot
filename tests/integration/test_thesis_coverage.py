# tests/integration/test_thesis_coverage.py
from __future__ import annotations

import json
from pathlib import Path

import pytest


_REQUIRED_COVERAGE_RATIO = 0.40
_OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"


@pytest.mark.integration
def test_thesis_coverage_meets_threshold():
    """After Tasks 9-11, at least 40% of rows must have a real thesis_state."""
    candidates = sorted(_OUTPUTS_DIR.glob("*/opportunity_report.json"))
    if not candidates:
        pytest.skip("no opportunity_report.json found; run `irc opportunity` first")
    report_path = candidates[-1]  # latest date
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = report.get("rows", [])
    if not rows:
        pytest.skip("opportunity_report.json has no rows")
    real = sum(1 for r in rows if r.get("thesis_state") != "evidence_insufficient")
    ratio = real / len(rows)
    assert ratio >= _REQUIRED_COVERAGE_RATIO, (
        f"thesis coverage {ratio:.0%} < {_REQUIRED_COVERAGE_RATIO:.0%} "
        f"({real}/{len(rows)}) in {report_path}"
    )


@pytest.mark.integration
def test_no_all_evidence_insufficient_valuation():
    """After Tasks 1-3, no instrument should have evidence_insufficient valuation."""
    candidates = sorted(_OUTPUTS_DIR.glob("*/opportunity_report.json"))
    if not candidates:
        pytest.skip("no opportunity_report.json found")
    report_path = candidates[-1]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = report.get("rows", [])
    if not rows:
        pytest.skip("empty")
    insuf = sum(1 for r in rows if r.get("valuation_state") == "evidence_insufficient")
    assert insuf == 0, f"{insuf}/{len(rows)} instruments still have evidence_insufficient valuation"
