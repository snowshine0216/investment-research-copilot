"""Provider-degradation gate (item 003, 2026-05-19).

Adversarial review §A4: research_status.json showed brave_news timeout
on 4 themes (us_monetary, us_fiscal_politics, geopolitics, gold_drivers)
but the pipeline published anyway. When ≥2 critical themes lose a
provider, the run should emit a WARN so the memo can surface the
degradation.
"""
from __future__ import annotations

from irc.research.quality_gate import evaluate_research_quality
from irc.research.theme_research import ThemeReport


def _report(
    theme: str,
    *,
    failure: str = "",
    provider_failures: tuple[str, ...] = (),
    locale: str = "en",
) -> ThemeReport:
    return ThemeReport(
        theme=theme,
        query="q",
        locale=locale,
        report_md="body",
        citations=[],
        failure_reason=failure,
        provider_failures=provider_failures,
    )


def _full_run(**overrides) -> list[ThemeReport]:
    """Seven themes, all healthy by default. Pass overrides like
    {'us_monetary': dict(provider_failures=('brave: timeout',))} to
    inject degradation on specific themes."""
    base = {
        "us_monetary": {}, "us_fiscal_politics": {},
        "cn_monetary": {}, "cn_equity_property_policy": {"locale": "zh"},
        "geopolitics": {}, "gold_drivers": {},
        "holdings_sector": {"locale": "zh"},
    }
    for theme, ov in overrides.items():
        base.setdefault(theme, {}).update(ov)
    return [_report(theme=t, **kw) for t, kw in base.items()]


def test_zero_degradation_passes_clean() -> None:
    verdict = evaluate_research_quality(_full_run())
    assert verdict.passed
    assert not verdict.warning
    assert verdict.degraded_themes == ()


def test_one_critical_degraded_still_passes_clean() -> None:
    """One degraded critical theme is normal noise; we only warn at ≥2."""
    verdict = evaluate_research_quality(_full_run(
        gold_drivers={"provider_failures": ("brave_news: timeout",)},
    ))
    assert verdict.passed
    assert not verdict.warning
    assert verdict.degraded_themes == ("gold_drivers",)


def test_two_critical_degraded_emits_warn_with_named_themes() -> None:
    verdict = evaluate_research_quality(_full_run(
        gold_drivers={"provider_failures": ("brave_news: timeout",)},
        us_monetary={"provider_failures": ("brave_news: timeout",)},
    ))
    assert verdict.passed
    assert verdict.warning
    assert "gold_drivers" in verdict.degraded_themes
    assert "us_monetary" in verdict.degraded_themes
    assert any("critical themes degraded" in r for r in verdict.reasons)


def test_non_critical_theme_degradation_does_not_warn() -> None:
    """us_fiscal_politics and geopolitics are not in _CRITICAL_THEMES;
    losing their providers should NOT trigger the critical-degradation
    warn even if both are down (overall success rate is the existing
    signal for that case)."""
    verdict = evaluate_research_quality(_full_run(
        us_fiscal_politics={"provider_failures": ("brave_news: timeout",)},
        geopolitics={"provider_failures": ("brave_news: timeout",)},
    ))
    assert verdict.passed
    assert not verdict.warning


def test_holdings_sector_filter_empty_counts_as_degradation() -> None:
    """Item 001 marks holdings_sector failed when the relevance filter
    drops every citation. That failure_reason is the signal."""
    verdict = evaluate_research_quality(_full_run(
        holdings_sector={"failure": "no relevant sources after relevance filter"},
        cn_monetary={"provider_failures": ("bocha: 500",)},
    ))
    # The dead-locale check fires when ALL zh themes fail. Here only
    # holdings_sector failed (failure_reason); cn_monetary is still ok
    # (just had a provider issue). Should warn, not fail.
    assert verdict.passed
    assert verdict.warning
    assert "holdings_sector" in verdict.degraded_themes
    assert "cn_monetary" in verdict.degraded_themes
