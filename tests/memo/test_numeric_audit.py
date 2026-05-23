from __future__ import annotations

from irc.memo.numeric_audit import (
    find_prose_data_contradictions,
    render_findings_block,
)


_EVIDENCE_EXPENSIVE_000105 = (
    "[000105 建信安心回报债券A] 状态=expensive/normal/intact/strong "
    "opportunity=core_dca score=51.4 cost_grade=85 risk=47 quality=87"
)

_EVIDENCE_CHEAP_000105 = (
    "[000105 建信安心回报债券A] 状态=cheap/normal/intact/strong "
    "opportunity=core_dca score=51.4 cost_grade=85 risk=47 quality=87"
)


def test_finds_cheap_prose_when_state_is_expensive():
    # The 2026-05-18 audit's exact failure mode.
    prose = (
        "信用债条目 000105 估值便宜，可优先承接本期增量资金。"
    )
    findings = find_prose_data_contradictions(prose, [_EVIDENCE_EXPENSIVE_000105])
    assert len(findings) == 1
    f = findings[0]
    assert f.instrument_id == "000105"
    assert f.kind == "cheap_claim_vs_state"
    assert "估值便宜" in f.prose_excerpt


def test_no_finding_when_prose_agrees_with_state():
    prose = "信用债条目 000105 估值便宜，可优先承接本期增量资金。"
    findings = find_prose_data_contradictions(prose, [_EVIDENCE_CHEAP_000105])
    assert findings == []


def test_finds_expensive_prose_when_state_is_cheap():
    prose = "000105 估值偏高，赔率不佳。"
    findings = find_prose_data_contradictions(prose, [_EVIDENCE_CHEAP_000105])
    assert len(findings) == 1
    assert findings[0].kind == "expensive_claim_vs_state"


def test_no_finding_when_phrase_is_far_from_id():
    # 300 characters of separation — outside the 200-char proximity window.
    prose = ("000105 是信用债。" + "占位文字" * 80 + "估值便宜，可考虑配置。")
    findings = find_prose_data_contradictions(prose, [_EVIDENCE_EXPENSIVE_000105])
    assert findings == []


def test_handles_evidence_without_instrument_id():
    # Gold-regime line has no [<id> ...] prefix; should be skipped silently.
    prose = "000105 估值便宜。"
    pool = ["[gold] regime=range_bound zone=normal tilt=neutral", _EVIDENCE_EXPENSIVE_000105]
    findings = find_prose_data_contradictions(prose, pool)
    assert len(findings) == 1


def test_render_findings_block_empty_returns_empty_string():
    assert render_findings_block([]) == ""


def test_render_findings_block_includes_kind_and_excerpt():
    findings = find_prose_data_contradictions(
        "000105 估值便宜。", [_EVIDENCE_EXPENSIVE_000105],
    )
    rendered = render_findings_block(findings)
    assert "自动数值审核" in rendered
    assert "000105" in rendered
    assert "cheap_claim_vs_state" in rendered


# ── Item 007 D1c — find_uncited_conclusions stub ──────────────────────────────


def test_find_uncited_conclusions_empty_instrument_aliases_raises() -> None:
    """Item 007 D1c — empty alias map indicates build_alias_maps did not
    run; the function refuses to silent-no-op the audit."""
    import pytest
    from irc.memo.numeric_audit import find_uncited_conclusions
    with pytest.raises(RuntimeError) as exc:
        find_uncited_conclusions(
            prose="some prose mentioning 005827",
            cited_map={},
            instrument_aliases={},
            constituent_aliases={},
            constituent_cited_map={},
        )
    msg = str(exc.value)
    assert "empty instrument_aliases" in msg
    assert "D1c" in msg


def test_find_uncited_conclusions_non_empty_aliases_does_not_raise() -> None:
    """Non-empty instrument_aliases must pass the guard. Empty
    constituent_aliases is permitted (a publishable run may have zero
    active funds)."""
    from irc.memo.numeric_audit import find_uncited_conclusions
    result = find_uncited_conclusions(
        prose="some prose",
        cited_map={},
        instrument_aliases={"005827": "005827"},
        constituent_aliases={},
        constituent_cited_map={},
    )
    # Item 007 ships the stub; the body is item 009's territory.
    assert result == []
