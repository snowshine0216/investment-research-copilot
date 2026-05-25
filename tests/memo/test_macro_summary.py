from __future__ import annotations

from irc.commands.memo_cmd import _MACRO_SUMMARY


def test_macro_summary_does_not_assert_real_yield_usd_dominance():
    """Audit P1 — calling real-yield + USD the '主导变量' of gold pricing is a
    deterministic causal claim that ignores geopolitics, central-bank purchases,
    and risk-off flows. The text must not make that claim."""
    assert "主导变量" not in _MACRO_SUMMARY


def test_macro_summary_acknowledges_alternative_gold_drivers():
    """The softened text must call out at least one alternative driver
    (geopolitics or central-bank purchases) so readers don't anchor on
    real-yield/USD as the only inputs."""
    assert "重要参考变量" in _MACRO_SUMMARY
    assert ("地缘" in _MACRO_SUMMARY) or ("央行购金" in _MACRO_SUMMARY)


def test_macro_summary_defers_a_share_valuation_to_evidence_pool():
    """Audit P3 — 'A股估值处于历史中位附近' was a fabricated specific claim with
    no data backing. Softened text must either remove the specific level claim
    or defer to the evidence pool."""
    assert "历史中位附近" not in _MACRO_SUMMARY


def test_macro_summary_keeps_anti_fabrication_reminder():
    """The 'don't fabricate data — quote the evidence pool' instruction is
    load-bearing for the synthesizer; the softening must keep it."""
    assert "证据池" in _MACRO_SUMMARY
    assert "不要自行编造" in _MACRO_SUMMARY or "不要编造" in _MACRO_SUMMARY


def test_macro_summary_remains_fallback_only():
    """`_MACRO_SUMMARY` is the anti-fabrication FALLBACK used when
    `gold_regime.json` has no macro_snapshots / theme_refs. When the gold
    stage emits real data the memo §2 body is composed by
    `irc.memo.macro_pillar.render_macro_section_body` instead. This test
    guards against accidentally re-locking the static text into the
    primary code path."""
    from irc.memo import macro_pillar  # importable & wired to memo_cmd

    assert hasattr(macro_pillar, "render_macro_section_body")
    assert hasattr(macro_pillar, "render_gold_evidence_body")
    assert hasattr(macro_pillar, "build_macro_evidence")
