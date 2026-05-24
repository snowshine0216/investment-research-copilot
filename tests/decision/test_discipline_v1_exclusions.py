"""Item 006 Slice H4 — §1.2 footnote regression check (criterion 23)."""
from __future__ import annotations

from pathlib import Path


def test_diagnosis_doc_v1_footnote_intact() -> None:
    """Criterion 23: §1.2 footnote in docs/diagnosis-thesis-cards-evidence-gap.md
    must contain the canonical phrase 'systematic exclusion of US-heavy'
    or 'documents the systematic exclusion of US-heavy active CN funds'.
    """
    diagnosis = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "diagnosis-thesis-cards-evidence-gap.md"
    )
    assert diagnosis.exists(), (
        f"H4 §1.2 footnote regressed: {diagnosis} does not exist"
    )
    text = diagnosis.read_text(encoding="utf-8")
    canonical_phrases = (
        "systematic exclusion of US-heavy",
        "V1 systematic exclusion",
    )
    matched = [p for p in canonical_phrases if p in text]
    assert matched, (
        "H4 §1.2 footnote regressed: none of the canonical phrases "
        f"{canonical_phrases} were found in {diagnosis}"
    )
