from __future__ import annotations
from irc.research.quality_gate import QualityVerdict, evaluate_research_quality
from irc.research.theme_research import ThemeReport


def _ok(theme: str, locale: str = "en", n: int = 4) -> ThemeReport:
    # Use simple objects for citations — just need them to be truthy
    from irc.research.synthesize import Citation
    return ThemeReport(
        theme=theme, query="q", locale=locale, report_md="x",
        citations=[Citation(index=i + 1, title="t", url=f"https://x/{i}") for i in range(n)],
        failure_reason="",
    )


def _failed(theme: str, locale: str = "en", reason: str = "no sources") -> ThemeReport:
    return ThemeReport(
        theme=theme, query="q", locale=locale, report_md="",
        citations=[], failure_reason=reason,
    )


def test_passes_when_all_themes_succeed():
    reports = [_ok(t) for t in ("us_monetary", "cn_monetary")]
    v = evaluate_research_quality(reports)
    assert v.passed
    assert v.exit_code == 0


def test_fails_when_entire_locale_dead():
    # All zh themes failed → zh locale unusable → critical.
    reports = [
        _ok("us_monetary", locale="en"),
        _failed("cn_monetary", locale="zh", reason="bocha 403 quota"),
        _failed("cn_equity_property_policy", locale="zh", reason="bocha 403 quota"),
        _failed("holdings_sector", locale="zh", reason="bocha 403 quota"),
    ]
    v = evaluate_research_quality(reports)
    assert not v.passed
    assert v.exit_code == 2
    assert "zh" in "\n".join(v.reasons).lower()


def test_fails_when_success_rate_below_floor():
    reports = [_failed(t) for t in ("us_monetary", "cn_monetary", "geopolitics")] + [_ok("gold_drivers")]
    v = evaluate_research_quality(reports)
    assert not v.passed
    # 1/4 = 25% success — below the 50% floor.
    assert any("success rate" in r.lower() for r in v.reasons)


def test_warns_when_success_rate_in_warn_band():
    # 5/7 = ~71%, between 50% (fail) and 80% (warn).
    reports = [_ok(t) for t in ("us_monetary", "us_fiscal_politics", "geopolitics", "gold_drivers", "cn_monetary")]
    reports += [_failed("cn_equity_property_policy"), _failed("holdings_sector")]
    v = evaluate_research_quality(reports)
    assert v.passed  # warn does not block
    assert v.exit_code == 0
    assert v.warning


def test_fails_when_no_reports():
    v = evaluate_research_quality([])
    assert not v.passed
    assert v.exit_code == 2
