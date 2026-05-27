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


# ---------------------------------------------------------------------------
# Citation-contamination regression (Finding 1, round 2 PR review)
# ---------------------------------------------------------------------------

def test_stress_keywords_in_citation_titles_do_not_inflate_score():
    """Regression: geopolitical_stress_from_theme_report must strip citation
    titles before counting stress/calm hits.

    A report with neutral prose but stress-laden citation titles (e.g.
    'Russia-Ukraine war sanction tariff strike') must score at the default,
    not above it.  Pre-fix, the function passed raw report_md (including the
    '## Citations' section) to _count_hits, causing citation titles to inflate
    the geo_stress value flowing into compute_gold_score.

    Constructing the report string as format_report_markdown would produce it —
    i.e. the full persisted form with heading + prose + ## Citations footer.
    """
    from irc.research.persistence import format_report_markdown
    from irc.research.synthesize import Citation
    from irc.research.theme_research import ThemeReport

    # Neutral prose — should produce default score.
    # Deliberately avoids any stress OR calm tokens (no "war", "sanction",
    # "peace", "diplomat", etc.) so the prose itself contributes net=0 hits.
    prose = "Gold prices rose amid uncertainty about interest rate decisions."
    # Citation titles saturated with stress keywords
    citations = [
        Citation(index=1, title="Russia-Ukraine war escalation sanction tariff", url="https://a.com"),
        Citation(index=2, title="Strike attack missile conflict invasion", url="https://b.com"),
        Citation(index=3, title="制裁 冲突 战争 升级 导弹", url="https://c.com"),
    ]
    report = ThemeReport(
        theme="geopolitics", query="q", locale="en",
        report_md=prose,
        citations=citations,
        failure_reason="",
    )
    # Build the persisted form (heading + prose + ## Citations section)
    persisted_md = format_report_markdown(report)

    # Wrap in a ThemeReport with report_md = persisted form (as load_theme_reports produces)
    persisted_report = ThemeReport(
        theme="geopolitics", query="q", locale="en",
        report_md=persisted_md,
        citations=citations,
        failure_reason="",
    )
    score = geopolitical_stress_from_theme_report(persisted_report)
    assert score == GEOPOLITICAL_STRESS_DEFAULT, (
        f"Expected {GEOPOLITICAL_STRESS_DEFAULT} (neutral prose only), got {score}. "
        "Citation titles are leaking into stress keyword counting."
    )
