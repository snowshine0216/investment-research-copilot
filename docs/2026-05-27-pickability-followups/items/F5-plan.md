# F5 — §2 macro research excerpt depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "first non-empty line" extraction in `gold_cmd._summary_from_theme_report` with a deterministic skip-rule + paragraph-accumulator extractor so memo §2 `本周宏观研究要点` renders substantive paragraph-shaped excerpts for all 7 theme reports (per ADR 0008 and spec F5).

**Architecture:** Add a private helper `_first_prose_paragraph(prose, *, max_chars)` co-located in `src/irc/commands/gold_cmd.py`. The helper iterates `prose.splitlines()`, applies three skip predicates (markdown `##`+ subheadings, pure bold-only `**foo**`/`__foo__` lines via `re.fullmatch`, blank lines BEFORE first prose line), accumulates non-skip lines (stripping bullet markers `- / * / +` on every accepted line) until one of three terminators fires (≥3 sentence terminators, ≥150 chars accumulated, blank line AFTER ≥1 prose line in buffer), then truncates at `max_chars=400` (raised from 220) with an `…` suffix when over cap. `_summary_from_theme_report` becomes a 4-line wrapper that delegates to the helper. No new module; helper stays private (grill Q6 — `news_summaries._summary_for_theme` consumes WHOLE prose, not first paragraph; YAGNI).

**Tech Stack:** Python 3.12+, `re` (stdlib), pytest. No new dependencies. No LLM, no AkShare, no I/O — pure-Python deterministic logic.

---

## Constraints / Non-goals (DO NOT VIOLATE)

- DO NOT redesign the LLM prompt for theme research (`memo_synthesis`); deferred to `F5-followup-prompt-eval` (SKIPPED entry already exists per grill Q9).
- DO NOT introduce a 5-week eval bench (deferred — same SKIPPED entry).
- DO NOT modify `extract_prose_from_report_md` in `src/irc/research/persistence.py` (out of scope — landed in F4, locked by ADR 0007 §3a).
- DO NOT touch the `<!-- IRC_MACRO_LINES_BEGIN/END -->` or `<!-- IRC_GOLD_EVIDENCE_BEGIN/END -->` markers — §2 / §3 content goes between EXISTING markers, no new marker block.
- DO NOT change the `gold_regime.json["evidence"]` schema — only the renderer behavior (longer `.summary` strings) changes.
- DO NOT change the public signature of `macro_pillar.render_macro_section_body` or `macro_pillar.render_gold_evidence_body`.
- DO NOT change the public signature of `_summary_from_theme_report` (existing callsite passes only `report`; the `max_chars` kwarg keeps its default — only the default value changes from 220 → 400).
- DO NOT create a new module `src/irc/research/excerpt.py` (grill Q6 explicitly rejected this).
- DO NOT consolidate with `news_summaries._summary_for_theme` (grill Q6 — different consumer contract).
- DO NOT strip inline `[N]` citation markers from the excerpt (grill Q3 — leave them in; affects citation_id needlessly otherwise).
- DO NOT add new `[ref:...]` citation rows (extractor change is content-only; macro evidence row count stays identical pre/post F5 — only `.summary` content per row changes).
- DO NOT modify `src/irc/templates/config/llm.yaml` or `src/irc/memo/synthesizer.py` prompts.
- DO NOT push the branch (orchestrator handles pushes per MASTER-PLAN run-level shape).

## File Structure

**Modify:**
- `src/irc/commands/gold_cmd.py` (currently 332 lines) — add private `_first_prose_paragraph` (~25 lines including docstring) and `_BOLD_ONLY_RE` / `_UNDERSCORE_BOLD_RE` module-level regex constants (frozen, no module-level mutable state). Rewrite `_summary_from_theme_report` (lines 146–171) as a thin delegator. Net diff ~+35 lines / -15 lines = ~+20 net.
- `tests/commands/test_gold_cmd.py` (currently 131 lines) — append a new test section `# ─── F5: _summary_from_theme_report / _first_prose_paragraph ──` with ~8 unit tests + 1 §2-renderer smoke test. Net diff ~+180 lines.

**Do NOT create:**
- No new test file. The grill (Q6) said the helper stays private in `gold_cmd.py`; tests for it live alongside the existing `gold_cmd` tests.
- No new source module.

---

## Task 0: Cut the sub-branch off the feature branch

**Files:** (no edits, branch only)

- [ ] **Step 0.1: Verify base branch and clean tree**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
git status
git branch --show-current
```
Expected: working tree clean; current branch `autodev/pickability-followups-feature`.

- [ ] **Step 0.2: Cut the F5 sub-branch**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
git checkout -b claude/pickability-followups-F5
git branch --show-current
```
Expected output: `claude/pickability-followups-F5`.

---

## Task 1: Red tests for the skip rule

**Files:**
- Test: `tests/commands/test_gold_cmd.py` (append at end of file)

The skip rule has three predicates (per spec AC #1 and ADR 0008 §1):
- `stripped.startswith("##")` — markdown subheading at any depth (`##`, `###`, `####`, …)
- `re.fullmatch(r"\*\*[^*]+\*\*", stripped)` — pure bold-only line, no trailing prose
- `re.fullmatch(r"__[^_]+__", stripped)` — pure underscore-bold-only line
- Empty line BEFORE any prose line has entered the buffer (skip, not terminate)

- [ ] **Step 1.1: Append the import block and §2 of tests for skip rules**

Append to `tests/commands/test_gold_cmd.py` (end of file, after line 131):

```python


# ─── F5: _summary_from_theme_report / _first_prose_paragraph ──────────────


def _make_report(report_md: str, *, theme: str = "us_monetary") -> "ThemeReport":
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
```

- [ ] **Step 1.2: Run the new skip-rule tests — expect FAIL**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run pytest tests/commands/test_gold_cmd.py -v -k "skip" 2>&1 | tail -40
```
Expected: at least 4 of the 5 new tests FAIL. The existing extractor takes the first non-empty line including `##` subheadings and pure bold lines verbatim, so e.g. `test_summary_skips_double_hash_subheading` fails because `out.startswith("## ")` is True.

(`test_summary_does_not_skip_bold_with_trailing_prose` may already pass since the existing code returns the whole line as-is including `**政策优化信号**：…`. That's fine — it still acts as a regression guard once the skip predicate lands.)

---

## Task 2: Red tests for the paragraph accumulator

**Files:**
- Test: `tests/commands/test_gold_cmd.py` (append)

The accumulator terminators (per spec AC #2 and ADR 0008 §1):
- (i) ≥3 sentence-ending punctuation marks in `{".", "。", "！", "!", "?", "？"}`
- (ii) accumulated buffer ≥150 visible chars (excluding leading/trailing whitespace)
- (iii) blank line encountered AFTER ≥1 prose line in buffer (NOT before — grill Q5)
- Hard cap: truncate at `max_chars=400` (default raised from 220, per ADR 0008 §2)
- Bullet markers `- `, `* `, `+ ` stripped on EVERY accepted line (grill Q10)

- [ ] **Step 2.1: Append accumulator tests**

Append to `tests/commands/test_gold_cmd.py`:

```python


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


def test_summary_returns_empty_sentinel_when_all_lines_are_skipped() -> None:
    """Edge case: prose body is ONLY subheadings + pure-bold lines + blank
    lines. The accumulator finds no prose; the function returns the
    legacy `（报告为空）` sentinel for graceful empty rendering."""
    from irc.commands.gold_cmd import _summary_from_theme_report
    report = _make_report(
        "## Section A\n"
        "**Bold only line one**\n"
        "\n"
        "### Section B\n"
        "**Bold only line two**\n"
    )
    out = _summary_from_theme_report(report)
    assert out == "（报告为空）"


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
```

- [ ] **Step 2.2: Run the accumulator tests — expect FAIL**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run pytest tests/commands/test_gold_cmd.py -v -k "summary" 2>&1 | tail -50
```
Expected: most of the 8 accumulator tests FAIL. The current extractor returns the first line only, so multi-sentence assertions like `test_summary_accumulates_until_three_sentence_terminators` fail (the result is only `First sentence.`, not all three).

(`test_summary_returns_failure_string_when_report_failed` and `test_summary_returns_empty_sentinel_when_all_lines_are_skipped` may already pass — they cover the legacy branches; they act as regression guards.)

---

## Task 3: Green — implement the skip-rule + paragraph accumulator

**Files:**
- Modify: `src/irc/commands/gold_cmd.py` (lines 146–171 + add module-level constants near line 32)

- [ ] **Step 3.1: Add the module-level regex + sentence-terminator constants**

Edit `src/irc/commands/gold_cmd.py`. After the existing `_TILT_ORDER` tuple (around line 36) and BEFORE `_combine_tilts`, insert:

```python


# F5: paragraph-accumulator constants (per ADR 0008).
#
# `_BOLD_ONLY_RE` matches lines whose stripped form is ENTIRELY wrapped in
# `**...**` with NO trailing prose. Pure bold subheadings (e.g.
# `**1. Bond Market Pressure...**`) skip; bold + trailing prose (e.g.
# `**政策优化信号**：本周国常会…`) DOES NOT skip — the trailing colon and
# prose disqualifies the fullmatch. Same shape for underscore-bold.
import re as _re

_BOLD_ONLY_RE = _re.compile(r"\*\*[^*]+\*\*")
_UNDERSCORE_BOLD_RE = _re.compile(r"__[^_]+__")

# Sentence terminators counted toward the ≥3-terminator stop rule.
_SENTENCE_TERMINATORS: frozenset[str] = frozenset({".", "。", "！", "!", "?", "？"})

# Paragraph accumulator stop thresholds (per ADR 0008 §1).
_PARAGRAPH_CHAR_FLOOR: int = 150
_PARAGRAPH_TERMINATOR_FLOOR: int = 3
```

(The `import re as _re` is intentionally module-private — the existing imports at top of file don't bring in `re`. Placing it here keeps the F5 surface visually together.)

- [ ] **Step 3.2: Add `_first_prose_paragraph` helper**

Edit `src/irc/commands/gold_cmd.py`. Replace the existing `_summary_from_theme_report` block (current lines 146–171) with the following two functions:

```python
def _is_skip_line(stripped: str, *, buffer_has_prose: bool) -> bool:
    """Return True if this stripped line should be skipped during the
    paragraph extraction. See ADR 0008 §1 "Skip rule".

    - `##`-prefixed lines (markdown subheading at any depth) ALWAYS skip.
    - Pure bold-only lines (`**foo**` / `__foo__`) ALWAYS skip.
    - Empty lines skip only when no prose line is in the buffer yet;
      they terminate accumulation (not skipped) once buffer is non-empty.
    """
    if not stripped:
        return not buffer_has_prose
    if stripped.startswith("##"):
        return True
    if _BOLD_ONLY_RE.fullmatch(stripped):
        return True
    if _UNDERSCORE_BOLD_RE.fullmatch(stripped):
        return True
    return False


def _strip_bullet_marker(stripped: str) -> str:
    """Strip a leading `- `, `* `, or `+ ` bullet marker. Per grill Q10
    this runs on EVERY accepted accumulator line so bullet-list reports
    (e.g. geopolitics) reach the 150-char floor with content not markers."""
    if stripped.startswith(("- ", "* ", "+ ")):
        return stripped[2:].lstrip()
    return stripped


def _truncate_at_cap(text: str, *, max_chars: int) -> str:
    """If `text` exceeds `max_chars`, truncate to `max_chars - 1` visible
    chars and append a single `…` (horizontal-ellipsis). Otherwise return
    `text` unchanged. Per ADR 0008 §2."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _first_prose_paragraph(prose: str, *, max_chars: int) -> str:
    """Extract the first prose paragraph from a stripped theme-report body.

    Algorithm (locked by ADR 0008 §1):
      1. Walk lines top-to-bottom.
      2. For each stripped line, apply `_is_skip_line`; skipped lines do
         not enter the buffer.
      3. Once a non-skip prose line is found, strip its bullet marker and
         append to the buffer.
      4. Continue accumulating non-skip lines (bullets stripped) until any
         terminator fires:
         (i)  buffer's sentence-terminator count ≥ `_PARAGRAPH_TERMINATOR_FLOOR`
         (ii) buffer's len ≥ `_PARAGRAPH_CHAR_FLOOR`
         (iii) a blank line is encountered AFTER ≥1 prose line is in the buffer
      5. Truncate at `max_chars` with `…` suffix per `_truncate_at_cap`.
      6. Return the buffer joined by single ASCII space. If no prose line
         was ever found, return the empty string (caller maps to the
         `（报告为空）` sentinel).

    Pure function — no I/O.
    """
    buffer: list[str] = []
    char_count = 0
    terminator_count = 0
    for line in prose.splitlines():
        stripped = line.strip()
        if _is_skip_line(stripped, buffer_has_prose=bool(buffer)):
            continue
        if not stripped:
            # Blank line + buffer has prose → terminate.
            break
        accepted = _strip_bullet_marker(stripped)
        if not accepted:
            # Bullet marker stripped down to empty — treat as skip.
            continue
        buffer.append(accepted)
        char_count += len(accepted) + (1 if len(buffer) > 1 else 0)
        terminator_count += sum(1 for ch in accepted if ch in _SENTENCE_TERMINATORS)
        if terminator_count >= _PARAGRAPH_TERMINATOR_FLOOR:
            break
        if char_count >= _PARAGRAPH_CHAR_FLOOR:
            break
    if not buffer:
        return ""
    joined = " ".join(buffer)
    return _truncate_at_cap(joined, max_chars=max_chars)


def _summary_from_theme_report(report: ThemeReport, *, max_chars: int = 400) -> str:
    """Extract a paragraph-shaped summary from a ThemeReport.

    Per ADR 0008: skip-rule + paragraph accumulator. Default `max_chars`
    raised to 400 (was 220) so paragraph-shaped excerpts have room. The
    kwarg is preserved as a test override.

    Returns the failure_reason verbatim when the report failed; returns
    the legacy `（报告为空）` sentinel when no prose line is found.
    """
    if report.failure_reason:
        return f"研究采集失败：{report.failure_reason}"
    prose = extract_prose_from_report_md(report.report_md or "")
    paragraph = _first_prose_paragraph(prose, max_chars=max_chars)
    if not paragraph:
        return "（报告为空）"
    return paragraph
```

Notes for the implementer:
- The four helpers (`_is_skip_line`, `_strip_bullet_marker`, `_truncate_at_cap`, `_first_prose_paragraph`) are all < 20 lines, all pure. They satisfy CLAUDE.md "Functions < 20 lines" and "Pure functions" rules.
- `char_count` adds `+1` for the ASCII space that will appear between this line and the previous one (when len(buffer) > 1). This makes the 150-char floor reflect the JOINED buffer length, not the raw concatenation. Strictly correct but the diff between the two definitions is at most 5 chars — tests treat the floor as `≥ 150` with no exact-equality assertion.
- `terminator_count` is updated AFTER append so a line whose contribution pushes the count to 3 terminates immediately AFTER including itself in the buffer (matches test `test_summary_accumulates_until_three_sentence_terminators` which expects "Third sentence." to be present and "Fourth sentence" absent).

- [ ] **Step 3.3: Run the F5 tests — expect ALL PASS**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run pytest tests/commands/test_gold_cmd.py -v -k "summary or skip" 2>&1 | tail -40
```
Expected: all 13 new tests (5 skip + 8 accumulator) PASS.

- [ ] **Step 3.4: Run the whole `tests/commands/test_gold_cmd.py` to verify no regression**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run pytest tests/commands/test_gold_cmd.py -v 2>&1 | tail -30
```
Expected: all tests pass (5 pre-existing + 13 new). No regressions in the geopolitical-stress / regime / TIPS tests.

---

## Task 4: Smoke test for §2 macro_pillar renderer with longer excerpts

**Files:**
- Test: `tests/commands/test_gold_cmd.py` (append one more test)

The grill (Q8, Q11) confirmed `macro_pillar.render_macro_section_body` and `render_gold_evidence_body` consume `ThemeReportRef.summary` verbatim — no schema change needed. AC #16 (citation universe integrity) requires we verify §2/§3 `[ref:...]` markers still resolve when summaries are longer (and therefore citation_ids churn). The integration test below builds a synthetic `ThemeReport` set, runs the build_theme_refs → build_macro_evidence → render_macro_section_body path, and asserts the §2 body contains a paragraph-shaped excerpt (not a subheading-only excerpt) for each theme.

- [ ] **Step 4.1: Append the smoke test**

Append to `tests/commands/test_gold_cmd.py`:

```python


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


def test_macro_pillar_renders_empty_sentinel_for_skip_only_report() -> None:
    """Edge case: a theme report whose prose is only subheadings + bold
    lines renders the legacy `（报告为空）` sentinel in §2. The
    citation_id is still minted (the row exists in gold_regime.json) — F5
    does not delete rows, only changes content."""
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
    assert refs[0].summary == "（报告为空）"
    # Renderer still produces a valid §2 body with marker (no crash).
    evidence = build_macro_evidence((), refs)
    by_src = evidence_by_source_key(evidence)
    body = render_macro_section_body((), refs, by_src)
    assert "（报告为空）" in body
    ev = by_src["research:us_monetary"]
    assert f"[ref:{ev.citation_id}]" in body
```

- [ ] **Step 4.2: Run the smoke tests**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run pytest tests/commands/test_gold_cmd.py -v -k "macro_pillar" 2>&1 | tail -20
```
Expected: both new smoke tests PASS.

---

## Task 5: Verify citation gate / numeric-audit pillar unchanged

**Files:** (read-only verification)

Per AC #16 (grill Q11): inline `[N]` markers from the theme report body (e.g. `…manpower [2].`) MAY appear in the new longer excerpts but they are CONTENT — they do NOT affect the citation gate. The citation gate scans for `\[ref:[0-9a-f]{16}\]` (16-hex-char ADR 0001 format), not for `\[N\]`. This task is a one-shot verification that the existing `tests/memo/test_numeric_audit.py` and `tests/memo/test_citation_selector.py` still pass without modification.

- [ ] **Step 5.1: Run the memo audit + selector tests**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run pytest tests/memo/test_numeric_audit.py tests/memo/test_citation_selector.py -v 2>&1 | tail -30
```
Expected: all tests pass. (These tests don't exercise the §2 extractor at all — they test the audit + selector against synthetic memo bodies. The F5 change does not regress them.)

- [ ] **Step 5.2: Run the macro_pillar tests**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run pytest tests/memo/test_macro_pillar.py -v 2>&1 | tail -20
```
Expected: all 6 pre-existing macro_pillar tests pass. F5 does not change `macro_pillar.py`; only the `.summary` content it consumes changes.

---

## Task 6: Run the full memo + commands test suite

**Files:** (none — verification only)

- [ ] **Step 6.1: Run the full sweep**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run pytest tests/commands tests/memo -v 2>&1 | tail -40
```
Expected: all tests PASS. No regressions across the 30+ command tests or 30+ memo tests.

- [ ] **Step 6.2: Ruff lint check**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run ruff check src tests 2>&1 | tail -10
```
Expected: `All checks passed!` or zero NEW findings. If `ruff` reports pre-existing warnings unrelated to F5, leave them alone.

---

## Task 7: Optional sanity check — regenerate today's memo

**Files:** (no edits — runtime smoke only)

This is a manual visual check, not a regression test. Confirms that §2 of `outputs/2026-05-27/memo.md` visibly improves (was rendering subheadings for 4 of 7 themes pre-F5).

- [ ] **Step 7.1: Re-run gold + memo against today's snapshot**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run irc run --only gold 2>&1 | tail -5
uv run irc run --only memo 2>&1 | tail -5
```
Expected: both stages exit 0. No new errors.

- [ ] **Step 7.2: Inspect §2 of the regenerated memo**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
sed -n '/IRC_MACRO_LINES_BEGIN/,/IRC_MACRO_LINES_END/p' outputs/2026-05-27/memo.md
```
Expected visual outcome (per spec AC #6):
- At least 6 of the 7 theme excerpts contain ≥3 sentence-ending punctuation marks OR are ≥150 chars long.
- The 7th theme (worst case) contains at minimum ≥1 sentence-ending punctuation mark; never a bare subheading like `### Section`.
- Each bullet still ends with exactly one `[ref:...]` marker (16-hex).

If §2 still shows a bare subheading for any theme, the skip-rule predicate has missed a shape — open the source theme file at `data/research/<theme>.md`, find the offending line, and check whether it matches `startswith("##")`, the bold regex, or neither. If neither, that's a regression scope decision — out of plan; raise it with the orchestrator.

---

## Task 8: Commit and report

**Files:** (no edits — git only)

- [ ] **Step 8.1: Inspect the diff**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
git status
git diff --stat
```
Expected:
- Modified: `src/irc/commands/gold_cmd.py` (~+40 / -15 lines)
- Modified: `tests/commands/test_gold_cmd.py` (~+200 lines)
- No other files touched.

- [ ] **Step 8.2: Stage and commit**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
git add src/irc/commands/gold_cmd.py tests/commands/test_gold_cmd.py
git commit -m "$(cat <<'EOF'
feat(gold/memo §2): skip-rule + paragraph accumulator for theme excerpts

`_summary_from_theme_report` previously returned the FIRST non-empty line of
the theme report body. For 4 of 7 themes that first line was a `###` or
`**bold**` subheading, leaving memo §2 `本周宏观研究要点` rendering label
fragments instead of substantive prose.

This change replaces the extractor with the deterministic skip-rule +
paragraph-accumulator algorithm locked by ADR 0008:

- Skip `##`+ markdown subheadings and pure-bold (`**foo**` / `__foo__`)
  lines; do NOT skip bold + trailing prose (`**政策优化信号**：…`).
- Accumulate non-skip lines (bullet markers stripped on every line) until
  ≥3 sentence terminators, ≥150 chars, or a blank line AFTER ≥1 prose
  line in buffer.
- Hard cap raised 220 → 400 chars with `…` truncation suffix.

ThesisEvidence rows still mint citation_ids from `(source, summary[:64],
date)`; macro-theme ids churn once on this deploy (documented in ADR 0008
§3). Cross-stage `[ref:...]` integrity preserved by construction — §2 and
§3 read the same `evidence_by_source` map.

LLM `memo_synthesis` prompt redesign + 5-week eval bench remain deferred
to `F5-followup-prompt-eval` (SKIPPED.md).

Spec: docs/2026-05-27-pickability-followups/items/F5-spec.md
ADR:  docs/adr/0008-macro-research-excerpt-depth.md
EOF
)"
```
Expected: commit succeeds; pre-commit hooks (if any) pass. Do NOT push — orchestrator handles pushes per MASTER-PLAN.

- [ ] **Step 8.3: Verify the commit**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
git log -1 --stat
```
Expected: one new commit on `claude/pickability-followups-F5` with the two modified files and the body above.

---

## Self-review checklist (for the implementing agent)

After Task 8 completes, sanity-check before declaring done:

- [ ] All 15 new tests in `tests/commands/test_gold_cmd.py` are present and passing (5 skip-rule + 8 accumulator + 2 macro_pillar smoke).
- [ ] `_first_prose_paragraph` is PRIVATE (single leading underscore, not exported) and lives in `gold_cmd.py` — no new module.
- [ ] `_summary_from_theme_report` signature unchanged externally: `(report: ThemeReport, *, max_chars: int = 400) -> str`. Only the default value changed (220 → 400).
- [ ] `macro_pillar.py` is UNMODIFIED — only the content of `.summary` strings flowing through it changed.
- [ ] `extract_prose_from_report_md` in `research/persistence.py` is UNMODIFIED.
- [ ] No edits to `src/irc/templates/config/llm.yaml`, `src/irc/memo/synthesizer.py`, or any marker constants.
- [ ] The `_BOLD_ONLY_RE` / `_UNDERSCORE_BOLD_RE` constants use `re.fullmatch` semantics (via `.fullmatch()` call inside `_is_skip_line`), not `re.match` or `re.search` — the grill Q2 distinction between `**foo**` (skip) vs `**foo**：…` (do not skip) depends on this.
- [ ] Bullet markers stripped on EVERY accepted line (not just the first) — required by grill Q10 / `test_summary_strips_bullet_markers_on_first_and_continuation_lines`.
- [ ] `uv run ruff check src tests` reports no NEW findings.
- [ ] `uv run pytest tests/commands tests/memo` is fully green.
- [ ] Branch is `claude/pickability-followups-F5`, off `autodev/pickability-followups-feature`.
- [ ] Commit lands but is NOT pushed.
