from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.gold_cmd import run_gold


@pytest.fixture
def repo_with_gold_data(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    from irc.data.duckdb_helper import connect, ensure_schema
    from irc.data.manifest import ManifestEntry, write_manifest
    con = connect(tmp_path / "data" / "local.duckdb")
    ensure_schema(con)
    base = date(2026, 5, 7)
    for i in range(180):
        d = base - timedelta(days=180 - i)
        con.execute(
            "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["518880", d.isoformat(), 4.20, 4.25, 4.18, 4.20 + i * 0.005, 1e7,
             "2026-05-07T10:00:00+08:00", "openbb",
             f"openbb:prices:518880:{d.isoformat()}"],
        )
    # Macro series
    for s, v in (("DGS10", 4.0), ("DXY", 104.0), ("real_yield_10y_tips", 1.25)):
        con.execute(
            "INSERT INTO macro_series VALUES (?, ?, ?, ?, ?, ?)",
            [s, base.isoformat(), v, "2026-05-07T10:00:00+08:00", "openbb",
             f"openbb:macro_series:{s}:{base.isoformat()}"],
        )
    con.close()
    # Write a fresh akshare manifest so the freshness gate passes by default.
    fresh_ts = datetime.now(timezone.utc).isoformat()
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=fresh_ts,
        schema_version="v1", record_counts={"prices": 180},
    ))
    return tmp_path


def test_gold_writes_regime_and_band(repo_with_gold_data: Path):
    rc = run_gold(repo_root=str(repo_with_gold_data))
    assert rc == 0
    out_dir = next(p for p in (repo_with_gold_data / "outputs").iterdir())
    assert (out_dir / "gold_regime.json").exists()
    assert (out_dir / "gold_band.yaml").exists()


def test_gold_refuses_to_run_when_ingest_is_stale(repo_with_gold_data: Path, monkeypatch):
    """When data/_manifest/akshare.json is >24h old, gold exits without producing
    artifacts and writes STALE_INGEST.md."""
    from datetime import datetime, timedelta, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    repo = repo_with_gold_data
    # Overwrite the manifest with a stale timestamp.
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(repo / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))

    monkeypatch.delenv("IRC_ALLOW_STALE", raising=False)
    rc = run_gold(str(repo))
    assert rc == 1
    markers = list((repo / "outputs").rglob("STALE_INGEST.md"))
    assert len(markers) == 1


def test_gold_allow_stale_env_proceeds(repo_with_gold_data: Path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from irc.data.manifest import ManifestEntry, write_manifest

    repo = repo_with_gold_data
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    write_manifest(repo / "data", ManifestEntry(
        source="akshare", last_run_at=stale,
        schema_version="v1", record_counts={"prices": 100},
    ))
    monkeypatch.setenv("IRC_ALLOW_STALE", "1")
    rc = run_gold(str(repo))
    assert rc == 0  # proceeds with stale data
    assert (repo / "outputs" / next(iter((repo / "outputs").iterdir())).name
            / "STALE_INGEST.md").exists()


def test_gold_uses_geopolitical_stress_from_theme_report(monkeypatch, repo_with_gold_data: Path):
    """When a stressful geopolitics theme report exists in data/research/,
    gold_cmd uses a stress score above the hardcoded 0.4 default."""
    from irc.research.theme_research import ThemeReport

    captured: dict[str, float] = {}
    stress_report = ThemeReport(
        theme="geopolitics", query="q", locale="en",
        report_md="war war sanction tariff strike conflict",
        citations=[], failure_reason="",
    )

    monkeypatch.setattr(
        "irc.commands.gold_cmd.load_theme_reports",
        lambda root: {"geopolitics": stress_report},
    )

    def capture_score(inputs, cfg):
        captured["stress"] = inputs.geopolitical_stress_0to1
        from irc.scoring.gold_score import compute_gold_score as real_fn
        return real_fn(inputs, cfg)

    monkeypatch.setattr("irc.commands.gold_cmd.compute_gold_score", capture_score)

    rc = run_gold(repo_root=str(repo_with_gold_data))
    assert rc == 0
    assert captured["stress"] > 0.4


def test_gold_prefers_real_tips_series_over_nominal_proxy(
    monkeypatch, repo_with_gold_data: Path,
) -> None:
    captured: dict[str, float] = {}

    def capture_score(inputs, cfg):
        captured["real_yield"] = inputs.real_yield_10y_tips
        return 50.0

    monkeypatch.setattr("irc.commands.gold_cmd.compute_gold_score", capture_score)

    rc = run_gold(repo_root=str(repo_with_gold_data))

    assert rc == 0
    assert captured["real_yield"] == 1.25


# ─── F5: _summary_from_theme_report / _first_prose_paragraph ──────────────


def _make_report(report_md: str, *, theme: str = "us_monetary"):  # -> ThemeReport
    """Helper: build a minimal ThemeReport carrying the supplied prose body.

    The body is wrapped with the canonical `# <theme>` heading + an empty
    `## Citations` footer so that `extract_prose_from_report_md` (called by
    `_summary_from_theme_report`) strips them and hands the raw body
    untouched to the new accumulator.
    """
    from irc.research.theme_research import ThemeReport
    wrapped = f"# {theme}\n\n{report_md}\n\n## Citations\n"
    return ThemeReport(
        theme=theme, query="q", locale="en",
        report_md=wrapped, citations=[], failure_reason="",
    )


def test_summary_skips_double_hash_subheading() -> None:
    """`## Key Risks` (markdown subheading) must NOT be returned as the
    excerpt. The accumulator should walk past it to the next prose line."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    report = _make_report(
        "## Key Risks\n"
        "The Fed signalled a pause this week. "
        "Markets repriced cuts. Bonds rallied."
    )
    out = _summary_from_theme_report(report)
    assert not out.startswith("## ")
    assert not out.startswith("Key Risks")
    assert "Fed signalled a pause" in out


def test_summary_skips_triple_hash_subheading() -> None:
    """`### subsubheading` (deeper markdown level) must also skip."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    report = _make_report(
        "### 央行最近一周货币政策操作与表态\n"
        "本周央行公开市场净投放 5000 亿元。"
        "MLF 利率维持不变。降准窗口暂未打开。"
    )
    out = _summary_from_theme_report(report)
    assert not out.startswith("###")
    assert not out.startswith("央行最近一周货币政策操作与表态")
    assert "公开市场净投放" in out


def test_summary_skips_pure_bold_line() -> None:
    """`**1. Bond Market Pressure and Policy Response**` is pure bold —
    skip. The fullmatch regex must reject any trailing chars."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    report = _make_report(
        "**1. Bond Market Pressure and Policy Response**\n"
        "Treasuries sold off 18bp on the week. "
        "The auction tailed. Demand metrics weakened."
    )
    out = _summary_from_theme_report(report)
    assert "1. Bond Market Pressure" not in out
    assert "Treasuries sold off" in out


def test_summary_does_not_skip_bold_with_trailing_prose() -> None:
    """`**政策优化信号**：…` is bold marker + trailing prose — must NOT
    skip (per grill Q2 regex refinement)."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    report = _make_report(
        "**政策优化信号**：本周国常会强调稳增长。"
        "财政加码预期上升。地产政策边际放松。"
    )
    out = _summary_from_theme_report(report)
    assert "政策优化信号" in out
    assert "稳增长" in out


def test_summary_skips_pure_underscore_bold_line() -> None:
    """`__Section Title__` (underscore-bold) is also a pure-bold heading."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    report = _make_report(
        "__Section Title__\n"
        "Real yields fell 8bp this week. DXY weakened. "
        "Gold caught a bid into Friday."
    )
    out = _summary_from_theme_report(report)
    assert "Section Title" not in out
    assert "Real yields fell" in out


def test_summary_accumulates_until_three_sentence_terminators() -> None:
    """After the first prose line, keep collecting non-skip lines until
    we have collected ≥3 sentence-ending punctuation marks total."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    # Three short lines, each ending in '.' — total 3 terminators.
    # Joined with single ASCII space.
    report = _make_report(
        "First sentence.\n"
        "Second sentence.\n"
        "Third sentence.\n"
        "Fourth sentence we should NOT see."
    )
    out = _summary_from_theme_report(report)
    assert "First sentence." in out
    assert "Second sentence." in out
    assert "Third sentence." in out
    assert "Fourth sentence" not in out


def test_summary_accumulates_until_150_chars_floor() -> None:
    """If the prose has no sentence terminators (or fewer than 3),
    accumulation continues until ≥150 visible chars have been collected.
    Test with no terminators at all — uses the 150-char floor."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    # 6 lines of 30 chars each = 180 chars total (joined with 5 spaces).
    # Each is 30 chars of A's; no sentence terminator.
    line = "A" * 30
    body = "\n".join([line] * 6)
    report = _make_report(body)
    out = _summary_from_theme_report(report)
    # Buffer hits the 150-char floor between line 5 (150 chars + 4 spaces
    # = 154) and line 6 (it stops AT >= 150, so probably 5 lines x 30
    # + 4 spaces = 154 chars). Don't be precise about exact stop; just
    # assert the floor was respected and the truncation didn't fire.
    assert len(out) >= 150
    assert "…" not in out  # under 400-char cap


def test_summary_stops_at_blank_line_after_first_prose() -> None:
    """A blank line AFTER ≥1 prose line in buffer terminates accumulation.
    A blank line BEFORE the first prose line is skipped (grill Q5)."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    # Leading blank lines are NOT terminators (they get skipped because
    # the buffer is empty). After the first prose line ("本文论述…"),
    # a blank line terminates and the trailing paragraph is dropped.
    report = _make_report(
        "\n"
        "\n"
        "本文论述央行的政策路径。\n"
        "\n"
        "下一段不应出现在摘录里。"
    )
    out = _summary_from_theme_report(report)
    assert "本文论述央行的政策路径" in out
    assert "下一段不应出现在摘录里" not in out


def test_summary_truncates_at_400_char_cap_with_ellipsis() -> None:
    """Default `max_chars=400`. A single very-long line exceeding 400
    chars must be truncated to 400-1 visible chars + a `…` suffix."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    # 500-char single line with no sentence terminators or blank lines.
    line = "X" * 500
    report = _make_report(line)
    out = _summary_from_theme_report(report)
    assert len(out) == 400  # 399 visible chars + 1 horizontal-ellipsis
    assert out.endswith("…")
    # No mid-string ellipsis or broken-word artifacts; the body is
    # uniform X's, so the truncation is clean.
    assert out[:399] == "X" * 399


def test_summary_strips_bullet_markers_on_first_and_continuation_lines() -> None:
    """Bullet markers `- `, `* `, `+ ` are stripped on the first prose line
    AND on continuation lines (per grill Q10 — bullet-list reports need
    accumulation to reach the 150-char floor)."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    report = _make_report(
        "- 俄乌局势升级，制裁加码。\n"
        "* 中东油价波动。\n"
        "+ 台海风险维持高位。"
    )
    out = _summary_from_theme_report(report)
    # Markers gone, content joined with single ASCII space.
    assert not out.startswith("-")
    assert not out.startswith("*")
    assert "- 俄乌" not in out
    assert "* 中东" not in out
    assert "+ 台海" not in out
    assert "俄乌局势升级" in out
    assert "中东油价波动" in out
    assert "台海风险维持高位" in out


def test_summary_returns_overskip_sentinel_when_lines_exist_but_all_skipped() -> None:
    """F5 P0 fix: when the prose body is populated but every line is
    a subheading or pure-bold line, return the DISTINCT over-skip sentinel
    so the user/operator can tell this from a truly-empty report. The legacy
    `（报告为空）` would mask renderer/skip-rule bugs as 'no content'."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    report = _make_report(
        "## Section A\n"
        "**Bold only line one**\n"
        "\n"
        "### Section B\n"
        "**Bold only line two**\n"
    )
    out = _summary_from_theme_report(report)
    assert out == "（报告内容均为标题/小节，未找到正文段落）"


def test_summary_returns_empty_sentinel_when_prose_is_truly_empty() -> None:
    """F5 P0 fix: truly-empty prose (e.g. only the `# heading` and
    `## Citations` footer that F4's extract_prose_from_report_md strips
    out) returns `（报告为空）`. Distinct from the over-skip sentinel above."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    report = _make_report("")  # report_md becomes empty after extract_prose
    out = _summary_from_theme_report(report)
    assert out == "（报告为空）"


def test_summary_strips_llm_source_citation_markers_from_excerpt() -> None:
    """F5 P0 fix: LLM source-citation markers like `[1]`, `[12]` inside the
    prose collide visually with the memo's downstream footnote numerals.
    Strip them so neither the 150-char floor nor the 400-char cap can land
    inside one of these brackets."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    report = _make_report(
        "美联储维持利率不变 [1]，市场押注年内降息 [2]。"
        "通胀放缓至 3.2% [3]，符合预期 [4]。"
    )
    out = _summary_from_theme_report(report)
    assert "[1]" not in out
    assert "[2]" not in out
    assert "[3]" not in out
    assert "[4]" not in out
    assert "美联储维持利率不变" in out
    assert "符合预期" in out


def test_summary_returns_failure_string_when_report_failed() -> None:
    """The existing failure-reason branch is untouched."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    from irc.research.theme_research import ThemeReport
    report = ThemeReport(
        theme="us_monetary", query="q", locale="en",
        report_md="", citations=[],
        failure_reason="search provider 503",
    )
    out = _summary_from_theme_report(report)
    assert out == "研究采集失败：search provider 503"


def test_summary_renders_multi_sentence_prose_for_real_world_shape() -> None:
    """Sanity-check with the shape of a real `us_monetary` report from
    `data/research/`. The first prose line is a real sentence (no
    skip needed), and the accumulator should pull in the next 1-2
    sentences to hit either the 3-terminator or 150-char rule."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    body = (
        "The Federal Reserve held the policy rate steady this week as "
        "Chair-designate Warsh signalled a more hawkish stance than "
        "Powell. Treasury yields rose across the curve. The 10Y reached "
        "4.55% intraday. Equity markets ignored the move."
    )
    report = _make_report(body, theme="us_monetary")
    out = _summary_from_theme_report(report)
    # Should contain real content with ≥3 sentence terminators.
    terminators = sum(out.count(c) for c in ".。!！?？")
    assert terminators >= 3, f"got {terminators} terminators in: {out!r}"
    assert "Federal Reserve" in out


def test_macro_pillar_renders_paragraph_shaped_excerpt_post_f5() -> None:
    """End-to-end smoke: feed a multi-paragraph theme report through the
    F5 extractor → build_macro_evidence → render_macro_section_body, then
    assert the §2 body has substantive prose (not just a subheading)
    and a valid `[ref:...]` marker for the theme."""
    from irc.commands.gold_cmd import _build_theme_refs
    from irc.memo.macro_pillar import (
        MACRO_SECTION_MARKER_BEGIN,
        MACRO_SECTION_MARKER_END,
        build_macro_evidence,
        evidence_by_source_key,
        render_macro_section_body,
    )
    # A report whose body starts with a `### subheading` followed by real
    # prose — the exact failure shape spec F5 fixes.
    report = _make_report(
        "### 央行最近一周货币政策操作与表态\n"
        "本周央行公开市场净投放 5000 亿元。"
        "MLF 利率维持不变。降准窗口暂未打开。",
        theme="cn_monetary",
    )
    reports = {"cn_monetary": report}
    refs = _build_theme_refs(reports, today="2026-05-27")
    assert len(refs) == 1
    ref = refs[0]
    # F5 contract: subheading is NOT in the rendered excerpt.
    assert "央行最近一周货币政策操作与表态" not in ref.summary
    assert "公开市场净投放" in ref.summary
    # Citation universe integrity: render → marker present, points at the
    # correct citation_id.
    evidence = build_macro_evidence((), refs)
    by_src = evidence_by_source_key(evidence)
    body = render_macro_section_body((), refs, by_src)
    assert MACRO_SECTION_MARKER_BEGIN in body
    assert MACRO_SECTION_MARKER_END in body
    ev = by_src["research:cn_monetary"]
    assert f"[ref:{ev.citation_id}]" in body
    # `[ref:...]` format invariant (ADR 0001).
    import re
    assert re.search(r"\[ref:[0-9a-f]{16}\]", body) is not None


def test_macro_pillar_renders_overskip_sentinel_for_skip_only_report() -> None:
    """Edge case: a theme report whose prose is only subheadings + bold
    lines renders the DISTINCT over-skip sentinel in §2 (per F5 P0 fix).
    The citation_id is still minted (the row exists in gold_regime.json)
    — F5 does not delete rows, only changes content."""
    from irc.commands.gold_cmd import _build_theme_refs
    from irc.memo.macro_pillar import (
        build_macro_evidence,
        evidence_by_source_key,
        render_macro_section_body,
    )
    report = _make_report(
        "## Section A\n"
        "**Pure bold heading only**\n"
        "### Section B\n",
        theme="us_monetary",
    )
    reports = {"us_monetary": report}
    refs = _build_theme_refs(reports, today="2026-05-27")
    assert refs[0].summary == "（报告内容均为标题/小节，未找到正文段落）"
    # Renderer still produces a valid §2 body with marker (no crash).
    evidence = build_macro_evidence((), refs)
    by_src = evidence_by_source_key(evidence)
    body = render_macro_section_body((), refs, by_src)
    assert "（报告内容均为标题/小节，未找到正文段落）" in body
    ev = by_src["research:us_monetary"]
    assert f"[ref:{ev.citation_id}]" in body
