# tests/scoring/test_news_summaries.py
from __future__ import annotations

import pandas as pd
import pytest

from irc.research.persistence import format_report_markdown
from irc.research.synthesize import Citation
from irc.research.theme_research import ThemeReport
from irc.scoring.factors.thesis_news import score_thesis_news
from irc.scoring.news_summaries import (
    THEMES_BY_ASSET_CLASS,
    build_news_summaries,
    themes_for_instrument,
)


# ---- themes_for_instrument: per real asset_class ----

@pytest.mark.parametrize(
    "asset_class, expected",
    [
        ("gold", ("geopolitics", "gold_drivers", "us_monetary")),
        ("cn_equity_fund", ("cn_equity_property_policy", "cn_monetary", "holdings_sector")),
        ("cn_etf", ("cn_equity_property_policy", "cn_monetary", "holdings_sector")),
        ("cn_bond_fund", ("cn_monetary",)),
        (
            "hk_etf",
            ("cn_equity_property_policy", "cn_monetary", "geopolitics", "holdings_sector"),
        ),
        ("us_etf", ("geopolitics", "us_fiscal_politics", "us_monetary")),
        ("qdii_global", ("geopolitics", "us_fiscal_politics", "us_monetary")),
    ],
)
def test_themes_for_instrument_real_asset_classes(asset_class, expected):
    assert themes_for_instrument(asset_class) == expected


def test_themes_for_instrument_unknown_returns_empty_tuple():
    assert themes_for_instrument("not_a_real_class") == ()
    assert themes_for_instrument("") == ()


def test_themes_for_instrument_returns_sorted_ascending():
    for asset_class in THEMES_BY_ASSET_CLASS:
        themes = themes_for_instrument(asset_class)
        assert list(themes) == sorted(themes), (
            f"{asset_class} mapping must be sorted ASC for determinism"
        )


def test_themes_by_asset_class_is_immutable():
    with pytest.raises(TypeError):
        THEMES_BY_ASSET_CLASS["cn_etf"] = ("anything",)  # type: ignore[index]


# ---- build_news_summaries: empty input ----

def _watchlist(*rows: dict) -> pd.DataFrame:
    """Tiny helper: build a watchlist DataFrame for tests."""
    return pd.DataFrame(list(rows))


def _report(theme: str, report_md: str = "", failure_reason: str = "") -> ThemeReport:
    return ThemeReport(
        theme=theme,
        query="",
        locale="EN",
        report_md=report_md,
        citations=[],
        failure_reason=failure_reason,
        provider_failures=(),
    )


def test_build_news_summaries_empty_reports_and_empty_watchlist():
    out = build_news_summaries(reports={}, watchlist=_watchlist())
    assert out == {}


def test_build_news_summaries_empty_reports_populated_watchlist():
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports={}, watchlist=wl)
    # Key present, but value is empty tuple (gold has mapped themes, none populated)
    assert out == {"518880": ()}


def test_build_news_summaries_gold_uses_mapped_themes():
    reports = {
        "us_monetary": _report("us_monetary", "Fed signals patience on hikes."),
        "gold_drivers": _report("gold_drivers", "Strong demand for gold ETFs."),
        "geopolitics": _report("geopolitics", "Middle East tensions rise."),
        "cn_monetary": _report("cn_monetary", "PBoC unrelated text."),
    }
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    # Sorted ASC by theme name: geopolitics, gold_drivers, us_monetary
    assert out == {
        "518880": (
            "Middle East tensions rise.",
            "Strong demand for gold ETFs.",
            "Fed signals patience on hikes.",
        ),
    }


def test_build_news_summaries_qdii_global_themes():
    reports = {
        "us_monetary": _report("us_monetary", "Fed text."),
        "us_fiscal_politics": _report("us_fiscal_politics", "Fiscal text."),
        "geopolitics": _report("geopolitics", "Geopolitics text."),
    }
    wl = _watchlist({"instrument_id": "QD0001", "asset_class": "qdii_global"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    # Sorted ASC: geopolitics, us_fiscal_politics, us_monetary
    assert out == {
        "QD0001": ("Geopolitics text.", "Fiscal text.", "Fed text."),
    }


def test_build_news_summaries_skips_failed_reports_silently():
    reports = {
        "us_monetary": _report("us_monetary", "", failure_reason="provider 503"),
        "gold_drivers": _report("gold_drivers", "Real gold-drivers prose."),
        "geopolitics": _report("geopolitics", "Real geopolitics prose."),
    }
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    # us_monetary skipped (failure_reason set); only the two populated themes survive.
    assert out == {"518880": ("Real geopolitics prose.", "Real gold-drivers prose.")}


def test_build_news_summaries_skips_empty_report_md():
    reports = {
        "us_monetary": _report("us_monetary", ""),  # empty prose, no failure_reason
        "gold_drivers": _report("gold_drivers", "Real gold-drivers prose."),
        "geopolitics": _report("geopolitics", "Real geopolitics prose."),
    }
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    assert out == {"518880": ("Real geopolitics prose.", "Real gold-drivers prose.")}


def test_build_news_summaries_unknown_asset_class_gives_empty_tuple():
    reports = {"us_monetary": _report("us_monetary", "anything")}
    wl = _watchlist({"instrument_id": "X1", "asset_class": "totally_new_class"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    assert out == {"X1": ()}


def test_build_news_summaries_mixed_watchlist_keys_every_row():
    reports = {
        "cn_monetary": _report("cn_monetary", "PBoC text."),
        "gold_drivers": _report("gold_drivers", "Gold text."),
        "geopolitics": _report("geopolitics", "Geo text."),
        "us_monetary": _report("us_monetary", "Fed text."),
    }
    wl = _watchlist(
        {"instrument_id": "511880", "asset_class": "cn_bond_fund"},
        {"instrument_id": "518880", "asset_class": "gold"},
        {"instrument_id": "MM01", "asset_class": "totally_new_class"},
    )
    out = build_news_summaries(reports=reports, watchlist=wl)
    assert out == {
        "511880": ("PBoC text.",),
        "518880": ("Geo text.", "Gold text.", "Fed text."),
        "MM01": (),
    }


def test_build_news_summaries_is_deterministic_two_calls_equal():
    reports = {
        "us_monetary": _report("us_monetary", "Fed text."),
        "gold_drivers": _report("gold_drivers", "Gold text."),
        "geopolitics": _report("geopolitics", "Geo text."),
        "cn_monetary": _report("cn_monetary", "PBoC text."),
    }
    wl = _watchlist(
        {"instrument_id": "518880", "asset_class": "gold"},
        {"instrument_id": "511880", "asset_class": "cn_bond_fund"},
    )
    a = build_news_summaries(reports=reports, watchlist=wl)
    b = build_news_summaries(reports=reports, watchlist=wl)
    assert a == b
    # Stronger: the serialised form must be byte-identical too (sorted tuples
    # protect against dict-ordering drift in the per-instrument value).
    import json
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_score_cmd_run_score_passes_non_empty_news_summaries_when_research_exists(
    tmp_path, monkeypatch,
):
    """Plumbing AC #1 + AC #10: when data/research/research_status.json exists
    with at least one populated theme report, score_cmd.run_score must call
    run_scoring with a non-empty news_summaries dict (not {}).
    """
    import json
    from pathlib import Path

    import pandas as pd

    # 1) Stage a minimal repo skeleton under tmp_path: configs, watchlist,
    #    research outputs, and a DuckDB file.
    repo_root = tmp_path
    (repo_root / "outputs" / "2099-01-01").mkdir(parents=True)
    (repo_root / "data" / "research").mkdir(parents=True)
    (repo_root / "data").mkdir(exist_ok=True)
    (repo_root / "config").mkdir(exist_ok=True)

    # Minimal watchlist with one gold row (gold maps to three themes).
    watchlist_df = pd.DataFrame([{
        "instrument_id": "518880",
        "ticker": "518880",
        "name_cn": "黄金ETF",
        "asset_class": "gold",
        "market": "cn_on_exchange",
        "tracked_index": "",
        "cited_refs": "",
        "role": "satellite",
    }])
    watchlist_df.to_csv(
        repo_root / "outputs" / "2099-01-01" / "discovered_watchlist.csv",
        index=False,
    )

    # Stage one populated theme report (gold_drivers).
    theme_md = repo_root / "data" / "research" / "gold_drivers.md"
    theme_md.write_text("# gold_drivers\n\nStrong demand for gold.\n", encoding="utf-8")
    status = {
        "generated_at_iso": "2099-01-01T00:00:00+00:00",
        "overall": "pass",
        "theme_count": 1,
        "failure_count": 0,
        "themes": [{
            "theme": "gold_drivers",
            "query": "",
            "locale": "EN",
            "report_path": "data/research/gold_drivers.md",
            "citation_count": 0,
            "citations": [],
            "failure_reason": "",
            "provider_failures": [],
        }],
    }
    (repo_root / "data" / "research" / "research_status.json").write_text(
        json.dumps(status, ensure_ascii=False), encoding="utf-8",
    )

    # 2) Pin today() to the staged date and stub the I/O surface so the test
    #    stays pure-function-shaped (no DuckDB, no LLM).
    from irc.commands import score_cmd

    monkeypatch.setattr(score_cmd, "_today", lambda: "2099-01-01")
    monkeypatch.setattr(score_cmd, "_macro_summary", lambda con: "")

    class _StubCon:
        def execute(self, *a, **kw):  # pragma: no cover - safety net
            class _R:
                def fetchall(self_inner): return []
            return _R()
        def close(self): pass

    monkeypatch.setattr(score_cmd, "connect", lambda path: _StubCon())
    monkeypatch.setattr(score_cmd, "ensure_schema", lambda con: None)
    monkeypatch.setattr(
        score_cmd, "load_scoring_metrics",
        lambda con, ids: pd.DataFrame([{"instrument_id": iid} for iid in ids]),
    )
    monkeypatch.setattr(score_cmd, "resolve_route", lambda task, llm_cfg: None)

    # Intercept run_scoring to capture the news_summaries kwarg.
    captured: dict = {}

    def _fake_run_scoring(**kwargs):
        captured.update(kwargs)
        return {"scores": [{
            "instrument_id": "518880",
            "composite_score": 50.0,
            "action": "hold",
            "conviction": "low",
            "factor_breakdown": {},
            "data_completeness": 0.0,
            "missing_data": [],
            "weights_version": "v1",
        }]}, []

    monkeypatch.setattr(score_cmd, "run_scoring", _fake_run_scoring)

    # 3) Use the real load_repo_configs from the project repo; copy the
    #    config tree into tmp_path so loader resolves.
    import shutil
    project_root = Path(__file__).resolve().parents[2]
    shutil.copytree(project_root / "config", repo_root / "config", dirs_exist_ok=True)
    shutil.copytree(project_root / "inputs", repo_root / "inputs", dirs_exist_ok=True)

    rc = score_cmd.run_score(str(repo_root))
    assert rc == 0
    assert "news_summaries" in captured
    ns = captured["news_summaries"]
    # AC #1: dict is non-empty (every watchlist row gets a key).
    assert ns, f"news_summaries should be non-empty when research exists; got {ns!r}"
    # AC #1 specifically: the gold row resolves to a non-empty tuple
    # because gold_drivers is populated.
    assert ns["518880"], (
        f"gold row should map to non-empty news prose; got {ns['518880']!r}"
    )
    assert any("Strong demand for gold" in s for s in ns["518880"])


def test_score_cmd_run_score_logs_news_coverage(tmp_path, monkeypatch, capsys):
    """Observability: score_cmd MUST emit a single coverage line so an
    operator can tell whether build_news_summaries produced non-empty
    tuples for any instruments. Without it, a missing or broken research
    stage silently degrades thesis_news to all-50 with no signal.

    Format: `news coverage: <k>/<N> instruments` (k = non-empty, N = total).
    """
    import json
    from pathlib import Path

    import pandas as pd

    repo_root = tmp_path
    (repo_root / "outputs" / "2099-01-01").mkdir(parents=True)
    (repo_root / "data" / "research").mkdir(parents=True)
    (repo_root / "config").mkdir(exist_ok=True)

    watchlist_df = pd.DataFrame([{
        "instrument_id": "518880",
        "ticker": "518880",
        "name_cn": "黄金ETF",
        "asset_class": "gold",
        "market": "cn_on_exchange",
        "tracked_index": "",
        "cited_refs": "",
        "role": "satellite",
    }])
    watchlist_df.to_csv(
        repo_root / "outputs" / "2099-01-01" / "discovered_watchlist.csv",
        index=False,
    )

    theme_md = repo_root / "data" / "research" / "gold_drivers.md"
    theme_md.write_text("# gold_drivers\n\nStrong demand for gold.\n", encoding="utf-8")
    status = {
        "generated_at_iso": "2099-01-01T00:00:00+00:00",
        "overall": "pass",
        "theme_count": 1,
        "failure_count": 0,
        "themes": [{
            "theme": "gold_drivers",
            "query": "",
            "locale": "EN",
            "report_path": "data/research/gold_drivers.md",
            "citation_count": 0,
            "citations": [],
            "failure_reason": "",
            "provider_failures": [],
        }],
    }
    (repo_root / "data" / "research" / "research_status.json").write_text(
        json.dumps(status, ensure_ascii=False), encoding="utf-8",
    )

    from irc.commands import score_cmd

    monkeypatch.setattr(score_cmd, "_today", lambda: "2099-01-01")
    monkeypatch.setattr(score_cmd, "_macro_summary", lambda con: "")

    class _StubCon:
        def execute(self, *a, **kw):  # pragma: no cover
            class _R:
                def fetchall(self_inner): return []
            return _R()
        def close(self): pass

    monkeypatch.setattr(score_cmd, "connect", lambda path: _StubCon())
    monkeypatch.setattr(score_cmd, "ensure_schema", lambda con: None)
    monkeypatch.setattr(
        score_cmd, "load_scoring_metrics",
        lambda con, ids: pd.DataFrame([{"instrument_id": iid} for iid in ids]),
    )
    monkeypatch.setattr(score_cmd, "resolve_route", lambda task, llm_cfg: None)
    monkeypatch.setattr(
        score_cmd, "run_scoring",
        lambda **kw: ({"scores": [{
            "instrument_id": "518880",
            "composite_score": 50.0,
            "action": "hold",
            "conviction": "low",
            "factor_breakdown": {},
            "data_completeness": 0.0,
            "missing_data": [],
            "weights_version": "v1",
        }]}, []),
    )

    import shutil
    project_root = Path(__file__).resolve().parents[2]
    shutil.copytree(project_root / "config", repo_root / "config", dirs_exist_ok=True)
    shutil.copytree(project_root / "inputs", repo_root / "inputs", dirs_exist_ok=True)

    rc = score_cmd.run_score(str(repo_root))
    assert rc == 0
    out = capsys.readouterr().out
    assert "news coverage:" in out, (
        f"expected 'news coverage:' line in stdout; got: {out!r}"
    )
    assert "1/1" in out, (
        f"expected '1/1 instruments' (the gold row has populated news); got: {out!r}"
    )


# ---- Regression: prose-only extraction — citation titles must NOT pollute keyword scoring ----

def _report_with_full_markdown(theme: str, prose: str, citation_titles: list[str]) -> ThemeReport:
    """Build a ThemeReport whose report_md is the FULL format_report_markdown output.

    The citations have keyword-matchable titles so that, if _summary_for_theme
    returns the raw report_md verbatim, those titles flow into score_thesis_news
    and incorrectly inflate the score.
    """
    citations = [
        Citation(index=i + 1, title=title, url=f"https://example.com/{i}")
        for i, title in enumerate(citation_titles)
    ]
    # Start with bare-prose ThemeReport (no citations in report_md yet)
    bare = ThemeReport(
        theme=theme,
        query="",
        locale="EN",
        report_md=prose,
        citations=citations,
        failure_reason="",
        provider_failures=(),
    )
    # format_report_markdown wraps the prose with # heading + ## Citations footer
    full_md = format_report_markdown(bare)
    # Return the report whose report_md is the persisted (full markdown) form —
    # exactly what load_theme_reports returns after reading from disk.
    return ThemeReport(
        theme=theme,
        query="",
        locale="EN",
        report_md=full_md,
        citations=citations,
        failure_reason="",
        provider_failures=(),
    )


def test_build_news_summaries_strips_header_and_citation_footer():
    """Regression: ADR 0007 §2 — keyword rubric must score prose only.

    When report_md is the full format_report_markdown output (heading + prose
    + ## Citations footer), build_news_summaries must strip the header and
    citation footer so that keyword matches in citation titles/URLs do NOT
    contaminate score_thesis_news.

    Setup: neutral prose ("Central bank meeting scheduled next month.")
    but citation titles containing positive keywords ("buy", "support",
    "selloff"). If _summary_for_theme returns raw report_md, score_thesis_news
    would match those citation-title words and produce a score well above 50.
    After the fix, the summary contains prose only → catalyst_count=0, risk_count=0
    → score=50.0.
    """
    # Neutral prose — no positive or negative keywords.
    neutral_prose = "Central bank meeting scheduled next month."
    # Citation titles stuffed with positive + negative keywords so that if
    # citation text leaks into the summary, the rubric scores falsely.
    keyword_rich_titles = [
        "Goldman buy recommendation: strong support for gold rally",
        "Market selloff fears: outflow from emerging markets",
        "Analyst support for demand growth in gold sector",
        "Buy signal: rally expected after Fed patience statement",
    ]
    report = _report_with_full_markdown(
        theme="gold_drivers",
        prose=neutral_prose,
        citation_titles=keyword_rich_titles,
    )
    reports = {"gold_drivers": report}
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})

    summaries_dict = build_news_summaries(reports=reports, watchlist=wl)

    # Exactly one summary string for the gold_drivers theme.
    assert "518880" in summaries_dict
    news_tuple = summaries_dict["518880"]
    # The tuple must be non-empty (report is not failed/empty).
    assert news_tuple, f"Expected non-empty summaries; got {news_tuple!r}"

    # Core assertion: no citation title text must appear in any summary string.
    for summary in news_tuple:
        assert "Goldman" not in summary, (
            f"Citation title leaked into summary: {summary!r}"
        )
        assert "buy recommendation" not in summary.lower(), (
            f"Citation keyword 'buy recommendation' leaked into summary: {summary!r}"
        )
        assert "## Citations" not in summary, (
            f"Citations section header leaked into summary: {summary!r}"
        )
        assert "https://example.com" not in summary, (
            f"Citation URL leaked into summary: {summary!r}"
        )

    # Score must be neutral (50.0) because the prose has no keywords.
    factor_score = score_thesis_news(news_tuple, raw_refs=())
    assert factor_score.score == 50.0, (
        f"Expected neutral score 50.0 from prose-only content; "
        f"got {factor_score.score} (catalyst_count={factor_score.components.get('catalyst_count')}, "
        f"momentum={factor_score.components.get('momentum')}). "
        f"Citation title keywords must not flow into scoring."
    )
