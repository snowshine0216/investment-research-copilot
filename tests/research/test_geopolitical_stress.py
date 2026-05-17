from __future__ import annotations
from irc.research.theme_research import ThemeReport
from irc.research.geopolitical_stress import (
    geopolitical_stress_from_theme_report,
    GEOPOLITICAL_STRESS_DEFAULT,
)


def _report(report_md: str = "", failure_reason: str = "") -> ThemeReport:
    return ThemeReport(
        theme="geopolitics", query="q", locale="en",
        report_md=report_md, citations=[], failure_reason=failure_reason,
    )


def test_none_returns_default():
    assert geopolitical_stress_from_theme_report(None) == GEOPOLITICAL_STRESS_DEFAULT


def test_failed_report_returns_default():
    r = _report(failure_reason="no_results")
    assert geopolitical_stress_from_theme_report(r) == GEOPOLITICAL_STRESS_DEFAULT


def test_empty_report_returns_default():
    r = _report(report_md="   ")
    assert geopolitical_stress_from_theme_report(r) == GEOPOLITICAL_STRESS_DEFAULT


def test_stress_keywords_push_score_above_default():
    r = _report(report_md=(
        "Russia escalated the war this week. New sanctions on China. "
        "Tariff hike announced. Strike in the Red Sea. "
        "Conflict 冲突 制裁 升级."
    ))
    assert geopolitical_stress_from_theme_report(r) > GEOPOLITICAL_STRESS_DEFAULT


def test_calm_keywords_pull_score_below_default():
    r = _report(report_md=(
        "Peace talks resumed. Ceasefire holding. Agreement signed. "
        "缓和 协议 停火."
    ))
    assert geopolitical_stress_from_theme_report(r) < GEOPOLITICAL_STRESS_DEFAULT


def test_score_clipped_to_unit_interval():
    r = _report(report_md=("war sanction tariff strike conflict " * 50))
    assert 0.0 <= geopolitical_stress_from_theme_report(r) <= 1.0


def test_neutral_report_returns_default():
    r = _report(report_md="Markets closed flat on quiet trading.")
    assert geopolitical_stress_from_theme_report(r) == GEOPOLITICAL_STRESS_DEFAULT
