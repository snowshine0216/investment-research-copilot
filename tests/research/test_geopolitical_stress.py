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


def test_war_token_does_not_match_forward_warning_warrant():
    """Regression: bare-substring matching on 'war' used to silently fire on
    'forward', 'warning', 'warrant' — all common in gold/macro research text.
    The word-boundary regex must reject these without producing a stress hit."""
    r = _report(report_md=(
        "Forward guidance from the Fed. Earnings warning from the issuer. "
        "Warrant outstanding. Hardware shipments steady."
    ))
    assert geopolitical_stress_from_theme_report(r) == GEOPOLITICAL_STRESS_DEFAULT


def test_war_token_matches_actual_war_word():
    """The fix above must not regress the happy path — the literal word 'war'
    (and 'wars'/'wartime'/'warring') still trigger stress."""
    r = _report(report_md="The war continues into its third year.")
    assert geopolitical_stress_from_theme_report(r) > GEOPOLITICAL_STRESS_DEFAULT


def test_agreement_substring_in_disagreement_is_not_a_calm_hit():
    """Regression: the English 'agreement' token was dropped because it
    would silently fire on 'disagreement' (counter-signal). Calm should
    not move when only 'disagreement' is present."""
    r = _report(report_md="There is a disagreement between the parties.")
    assert geopolitical_stress_from_theme_report(r) == GEOPOLITICAL_STRESS_DEFAULT
