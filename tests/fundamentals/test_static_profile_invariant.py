"""F5 static-profile invariant lock — see ADR 0002 §5.

`ak.fund_open_fund_info_em(symbol, indicator="基金概况")` MUST NOT be called
by item 005's production code. Fund profile text is static metadata, not a
time-bound communication; tagging it citation_kind="information" would
silently bypass the freshness intent of the information leg.

Enforcement is upstream at the adapter layer (no downstream gate can
distinguish indicator origin from ThesisEvidence). This test greps the
production module for the literal "基金概况" and asserts zero matches.
"""
from __future__ import annotations

from pathlib import Path


_PRODUCTION_FILE = (
    Path(__file__).resolve().parents[2]
    / "src" / "irc" / "fundamentals" / "akshare_fundamentals.py"
)


def test_static_profile_indicator_not_in_production() -> None:
    body = _PRODUCTION_FILE.read_text(encoding="utf-8")
    # Strict literal grep — comments and docstrings are EXEMPT only because
    # adding a documentation-only mention would still raise a false positive.
    # If a future slice needs to reference "基金概况" in a comment, qualify
    # it as e.g. "indicator='profile'" or "JIJIN_GAIKUANG_RAW" — never the
    # raw literal.
    assert "基金概况" not in body, (
        "F5 violated: production code references the '基金概况' indicator. "
        "See ADR 0002 §5 — static profile text must not satisfy the "
        "citation_kind='information' leg."
    )


def test_static_profile_indicator_not_in_snapshot() -> None:
    snapshot_file = (
        Path(__file__).resolve().parents[2]
        / "src" / "irc" / "fundamentals" / "snapshot.py"
    )
    assert "基金概况" not in snapshot_file.read_text(encoding="utf-8")
