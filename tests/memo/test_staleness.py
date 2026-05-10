# tests/memo/test_staleness.py
from pathlib import Path
from datetime import date
from irc.memo.pipeline import check_inputs_same_date, MixedDateWarning
import pytest


def test_mixed_dates_emits_warning(tmp_path: Path, recwarn):
    inputs = {
        "scoring": tmp_path / "outputs/2026-05-07/scoring.json",
        "gold_band": tmp_path / "outputs/2026-05-06/gold_band.yaml",
        "allocation": tmp_path / "outputs/2026-05-07/proposed_allocation.yaml",
    }
    for p in inputs.values():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
    check_inputs_same_date(inputs, expected=date(2026, 5, 7))
    assert any(issubclass(w.category, MixedDateWarning) for w in recwarn.list)
