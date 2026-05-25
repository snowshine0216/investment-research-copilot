from __future__ import annotations

from irc.memo.macro_pillar import (
    GOLD_EVIDENCE_MARKER_BEGIN,
    GOLD_EVIDENCE_MARKER_END,
    MACRO_SECTION_MARKER_BEGIN,
    MACRO_SECTION_MARKER_END,
    MacroSnapshot,
    ThemeReportRef,
    build_macro_evidence,
    evidence_by_source_key,
    render_gold_evidence_body,
    render_macro_section_body,
)


def _snaps() -> tuple[MacroSnapshot, ...]:
    return (
        MacroSnapshot("real_yield_10y_tips", "美国10Y TIPS 实际利率", 2.18, "%", "2026-05-21"),
        MacroSnapshot("DXY", "美元指数 DXY", 99.34, "", "2026-05-21"),
        MacroSnapshot("vix", "VIX 波动率指数", 16.76, "", "2026-05-21"),
        MacroSnapshot("inflation_5y5y", "5Y5Y 通胀预期", 2.26, "%", "2026-05-22"),
    )


def _themes() -> tuple[ThemeReportRef, ...]:
    return (
        ThemeReportRef(
            "us_monetary", "美国货币政策",
            "Fed Chair transition to Warsh; rate-cut expectations dimming.",
            "2026-05-25",
        ),
        ThemeReportRef(
            "geopolitics", "地缘政治",
            "Russia-Belarus nuclear drills; Xi-Trump summit on Iran/Taiwan.",
            "2026-05-25",
        ),
        ThemeReportRef(
            "gold_drivers", "黄金驱动因素",
            "Central bank purchases continue; ETF flows positive.",
            "2026-05-25",
        ),
    )


def test_build_macro_evidence_emits_one_per_input() -> None:
    evidence = build_macro_evidence(_snaps(), _themes())
    assert len(evidence) == 4 + 3
    # Citation ids are 16-hex deterministic.
    for ev in evidence:
        assert len(ev.citation_id) == 16
        assert all(c in "0123456789abcdef" for c in ev.citation_id)


def test_macro_evidence_scope_and_owner() -> None:
    evidence = build_macro_evidence(_snaps(), _themes())
    for ev in evidence:
        assert ev.scope == "asset_class_macro"
        assert ev.owner_instrument_id == "macro"


def test_render_macro_section_body_contains_ref_markers() -> None:
    snaps = _snaps()
    themes = _themes()
    evidence = build_macro_evidence(snaps, themes)
    by_src = evidence_by_source_key(evidence)
    body = render_macro_section_body(snaps, themes, by_src)
    assert MACRO_SECTION_MARKER_BEGIN in body
    assert MACRO_SECTION_MARKER_END in body
    # Every datapoint / theme bullet must carry exactly one [ref:...] marker.
    for snap in snaps:
        assert f"{snap.value:g}{snap.unit}" in body
        ref_id = by_src[snap.series_id].citation_id
        assert f"[ref:{ref_id}]" in body
    for theme in themes:
        ref_id = by_src[f"research:{theme.theme}"].citation_id
        assert f"[ref:{ref_id}]" in body


def test_render_gold_evidence_filters_to_gold_relevant_sources() -> None:
    snaps = _snaps()
    themes = _themes()
    evidence = build_macro_evidence(snaps, themes)
    by_src = evidence_by_source_key(evidence)
    body = render_gold_evidence_body(snaps, themes, by_src)
    assert GOLD_EVIDENCE_MARKER_BEGIN in body
    assert GOLD_EVIDENCE_MARKER_END in body
    # Only real_yield + DXY snapshots and gold_drivers/geopolitics themes
    # by default.
    assert "real_yield_10y_tips" not in body  # series_id is internal; display name shown
    assert "实际利率" in body
    assert "美元指数" in body
    assert "VIX" not in body  # not gold-relevant by default
    assert "通胀预期" not in body
    assert "黄金驱动因素" in body
    assert "地缘政治" in body
    assert "美国货币政策" not in body


def test_empty_inputs_render_fallback_text() -> None:
    body = render_macro_section_body((), (), {})
    assert "数据采集失败" in body
    assert MACRO_SECTION_MARKER_BEGIN not in body  # no markers if no evidence


def test_gold_evidence_empty_when_no_relevant_data() -> None:
    body = render_gold_evidence_body((), (), {})
    assert body == ""
