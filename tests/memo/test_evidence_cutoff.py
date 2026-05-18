from __future__ import annotations

from irc.memo.pipeline import extract_evidence_cutoff
from irc.commands.memo_cmd import _compose_risk_notes


def test_extract_evidence_cutoff_returns_max_date() -> None:
    refs = [
        "akshare:nav_history:000105:2026-05-15",
        "akshare:nav_history:518880:2026-05-10",
        "akshare:nav_history:512960:2026-05-17",
    ]
    assert extract_evidence_cutoff(refs) == "2026-05-17"


def test_extract_evidence_cutoff_returns_none_when_no_dates() -> None:
    refs = ["theme_research:gold:macro_lookup", "static:cmb:account_meta"]
    assert extract_evidence_cutoff(refs) is None


def test_extract_evidence_cutoff_handles_empty_pool() -> None:
    assert extract_evidence_cutoff([]) is None


def test_extract_evidence_cutoff_ignores_non_iso_numbers() -> None:
    # A trailing year-like number is not an ISO date — should not match.
    refs = ["akshare:fund_em:110022:as_of_2026"]
    assert extract_evidence_cutoff(refs) is None


def test_compose_risk_notes_uses_cutoff_when_available() -> None:
    notes = _compose_risk_notes("2026-05-15")
    timeliness = notes[-1]
    assert "2026-05-15" in timeliness
    assert "境内" in timeliness  # detailed disclosure, not boilerplate
    assert "通常为T+1" not in timeliness  # boilerplate replaced


def test_compose_risk_notes_falls_back_when_cutoff_none() -> None:
    notes = _compose_risk_notes(None)
    timeliness = notes[-1]
    assert "通常为T+1" in timeliness
    assert "2026" not in timeliness
