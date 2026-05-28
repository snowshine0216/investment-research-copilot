# F6 — Filings evidence role reframe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe the filing-evidence `summary` template from
`{symbol} {fiscal_period} revenue_yoy={raw}` to
`{symbol} {fiscal_period} 财报已披露（口径未核实）`, and switch the
memo-appendix caveat trigger substring in lock-step so the
load-bearing structural role of filing evidence (Policy B rule 3,
dual-coverage gate, `select_citations` data-slot, `_TYPE_RANK`) is
fully preserved while the unverified `revenue_yoy` scalar disappears
from every user-facing surface.

**Architecture:** Producer-side text change at three loci
(`fundamentals/snapshot.py` CN + HK branches; `opportunity/thesis_evidence.py`
legacy `_filing_evidence`) plus a single substring switch at
`memo/pipeline.py::_format_appendix_line`. No schema change to
`ThesisEvidence`; no Policy B logic change; no `_TYPE_RANK` change;
no citation_id minting change (citation_id re-rolls naturally per
ADR 0001 §2 for the rare URL-empty filing path). Belt-and-braces
synthesizer-prompt clause updated in lock-step per ADR 0001 §5.1.

**Tech Stack:** Python 3.12, pydantic frozen dataclasses, pytest,
ruff (line-length 100), `uv run`. Project conventions: TDD red→green,
files <200 lines, functions <20 lines, immutable / pure functions
with effects pushed to thin wrappers.

---

## File map (locked before any code lands)

**Modify (production):**

- `src/irc/opportunity/thesis_evidence.py:75-105` — `_filing_evidence`
  legacy producer; change line 98 summary template only.
- `src/irc/fundamentals/snapshot.py:344` — `_evidence_for_constituent`
  CN branch summary template.
- `src/irc/fundamentals/snapshot.py:395` — `_evidence_for_constituent`
  HK branch summary template.
- `src/irc/memo/pipeline.py:176` — `_format_appendix_line` substring
  trigger swap.
- `src/irc/memo/synthesizer.py:55-56` — `_GUARDRAILS` rule-5
  trailing sentence updated in lock-step (ADR 0001 §5.1).

**Modify (tests — fixture updates only):**

- `tests/memo/test_pipeline_sanitization.py:56-66` — existing
  `test_evidence_appendix_adds_revenue_yoy_caveat_after_verbatim_ref`
  fixture has to use the new trigger substring; the sanitizer-input
  tests at lines 86-108 continue to use the literal `revenue_yoy=`
  string (that path is the sanitizer's job — it strips LLM
  hallucinations regardless of producer output).

**Add (tests — new):**

- `tests/opportunity/test_thesis_evidence.py` — append F6 test
  block at end of file. Asserts producer-side template + absence of
  the old substring; covers AC #1, AC #3 (`_TYPE_RANK` ordering),
  citation-id stability per run.
- `tests/memo/test_pipeline_sanitization.py` — append F6 test
  asserting `_format_appendix_line` fires the warning on the new
  phrase AND no longer fires on a hypothetical legacy
  `revenue_yoy=` ref-line (defensive — the producer no longer emits
  it, but the trigger is the single locus per grill Q2).
- `tests/opportunity/test_policy_b.py` — append F6 regression test
  asserting Policy B rule 3 still considers a filing-typed
  constituent evidence row as the data leg when its summary carries
  the new phrase (AC #2).

**Do NOT touch:**

- `src/irc/opportunity/policy_b.py` — read-only consumer of evidence
  shape, not summary text.
- `src/irc/opportunity/citation_selector.py` — same.
- `src/irc/opportunity/types.py::ThesisEvidence` — no schema change
  (per grill Q2: appendix trigger uses substring match, not a
  structural flag, precisely to avoid this churn).
- `src/irc/fundamentals/{akshare_filing,hkex_client,edgar_client}.py`
  — adapters still produce `FilingDigest.revenue_yoy`; display
  layer is the only place that changes.
- `src/irc/memo/synthesizer.py::sanitize_unverified_revenue_yoy`
  (lives in `pipeline.py`) — kept as belt-and-braces.
- ADRs 0001 / 0003 — grill phase already amended both at commit
  5a832ba; do NOT re-edit.
- Any IRC_*_BEGIN/END marker block.
- `outputs/<date>/` — not modified by this PR. The sanity check in
  Task 9 regenerates `memo.md` and reads the diff manually but does
  not commit it.

---

## Task 0: Cut sub-branch off the feature branch

**Files:** none (branch op only).

- [ ] **Step 0.1: Verify current branch is the feature branch**

```bash
git rev-parse --abbrev-ref HEAD
```

Expected output: `autodev/pickability-followups-feature`

- [ ] **Step 0.2: Verify clean working tree before branching**

```bash
git status --porcelain
```

Expected output: empty (no untracked / staged / modified files).
If non-empty, STOP — investigate before proceeding.

- [ ] **Step 0.3: Cut `claude/pickability-followups-F6` off the feature branch**

```bash
git checkout -b claude/pickability-followups-F6
```

Expected output: `Switched to a new branch 'claude/pickability-followups-F6'`

- [ ] **Step 0.4: Confirm sub-branch is now checked out**

```bash
git rev-parse --abbrev-ref HEAD
```

Expected output: `claude/pickability-followups-F6`

---

## Task 1: Red test — producer-side template at `_filing_evidence` (AC #1, legacy path)

**Files:**
- Modify (test only): `tests/opportunity/test_thesis_evidence.py`
  (append at end of file).

- [ ] **Step 1.1: Append failing test asserting the new template + absence of the old substring**

Append this block at the bottom of
`tests/opportunity/test_thesis_evidence.py` (after the last existing
test):

```python
# ── F6: filing-evidence summary reframe ──────────────────────────────────────

def test_filing_evidence_summary_uses_disclosure_existence_template_legacy() -> None:
    """F6 AC #1 — legacy `_filing_evidence` producer.

    The summary must (a) NOT contain `revenue_yoy=` substring, (b) NOT
    contain `营收同比` substring (the legacy +.1%-formatted phrasing),
    and (c) contain the locked Chinese phrase `财报已披露（口径未核实）`
    with full-width parentheses, prefixed by `{symbol} {fiscal_period}`.
    """
    from irc.opportunity.thesis_evidence import _filing_evidence

    digest = _filing("600519", -0.0771, period="2026Q1")
    out = _filing_evidence((digest,), owner_instrument_id="fund-x")

    assert len(out) == 1
    summary = out[0].summary
    # AC #1 load-bearing assertion: old scalar substring is gone.
    assert "revenue_yoy=" not in summary
    # AC #1 load-bearing assertion: legacy +.1%-formatted phrasing is gone.
    assert "营收同比" not in summary
    # AC #1 load-bearing assertion: new template phrase present, leading
    # with symbol + fiscal_period for stable `summary[:24]` appendix
    # fragment behaviour.
    assert summary == "600519 2026Q1 财报已披露（口径未核实）"


def test_filing_evidence_preserves_structural_role_legacy() -> None:
    """F6 AC #2 + AC #3 — non-summary fields unchanged.

    `_TYPE_RANK` ordering and the filing row's structural role
    (`scope`, `citation_kind`, `type`) MUST be preserved by the
    summary-only reframe. Confirms Policy B rule 3 and the
    dual-coverage gate keep seeing what they expect.
    """
    from irc.opportunity.thesis_evidence import _filing_evidence, _TYPE_RANK

    digest = _filing("000333", 0.18, period="2026Q1")
    out = _filing_evidence((digest,), owner_instrument_id="fund-y")

    assert len(out) == 1
    ev = out[0]
    assert ev.type == "filing"
    assert ev.citation_kind == "data"
    assert ev.scope == "instrument"   # legacy path; active-fund path uses "constituent"
    assert ev.url == digest.source_url
    assert ev.date == digest.filed_at_iso
    # AC #3: filing still ranks first per holding.
    assert _TYPE_RANK["filing"] == 0
    assert _TYPE_RANK["filing"] < _TYPE_RANK["broker"] < _TYPE_RANK["news"]
```

- [ ] **Step 1.2: Run the new tests — they must FAIL red**

```bash
uv run pytest tests/opportunity/test_thesis_evidence.py::test_filing_evidence_summary_uses_disclosure_existence_template_legacy tests/opportunity/test_thesis_evidence.py::test_filing_evidence_preserves_structural_role_legacy -v
```

Expected: both fail. The first fails on the
`summary == "600519 2026Q1 财报已披露（口径未核实）"` assertion
because the current producer emits
`"600519 2026Q1 营收同比 -7.7%。"`. The second test (structural-role
preservation) will PASS pre-change — that is fine; it locks the
contract so we notice if a careless edit drops `citation_kind="data"`.

---

## Task 2: Green — reframe `_filing_evidence` summary template

**Files:**
- Modify: `src/irc/opportunity/thesis_evidence.py:98`.

- [ ] **Step 2.1: Replace the legacy summary template line**

In `src/irc/opportunity/thesis_evidence.py`, change line 98 (inside
the `_filing_evidence` loop):

Before:
```python
            summary=f"{f.symbol} {f.fiscal_period} 营收同比 {f.revenue_yoy:+.1%}。",
```

After:
```python
            summary=f"{f.symbol} {f.fiscal_period} 财报已披露（口径未核实）",
```

Note: full-width parentheses `（）`, trailing period removed (the
new template ends on the closing paren, matching the producer
templates in `snapshot.py` and the ADR 0001 §5 addendum lock).

- [ ] **Step 2.2: Run the legacy-producer tests — they must PASS green**

```bash
uv run pytest tests/opportunity/test_thesis_evidence.py::test_filing_evidence_summary_uses_disclosure_existence_template_legacy tests/opportunity/test_thesis_evidence.py::test_filing_evidence_preserves_structural_role_legacy -v
```

Expected: both pass.

---

## Task 3: Red test — producer-side template at `_evidence_for_constituent` (AC #1, active-fund CN + HK)

**Files:**
- Modify (test only): `tests/opportunity/test_thesis_evidence.py`
  (append after Task 1's tests).

- [ ] **Step 3.1: Append failing test for the active-fund CN branch**

Append at the bottom of
`tests/opportunity/test_thesis_evidence.py`:

```python
def test_evidence_for_constituent_cn_uses_disclosure_existence_template(
    monkeypatch,
) -> None:
    """F6 AC #1 — active-fund CN branch.

    `_evidence_for_constituent` is the only producer of
    `citation_kind="data" AND scope="constituent"` in V1. Its filing
    summary MUST converge to the same locked phrase as the legacy
    producer so Policy B rule 3 + the dual-coverage gate read a
    user-safe summary while the structural role is preserved.
    """
    from irc.fundamentals import snapshot as snap_mod
    from irc.fundamentals.types import FundHolding

    digest = _filing("600519", -0.0771, period="2026Q1")
    monkeypatch.setattr(
        snap_mod, "fetch_cn_filing_digest", lambda sym: digest,
    )
    monkeypatch.setattr(
        snap_mod, "fetch_cn_broker_reports", lambda sym: (),
    )
    monkeypatch.setattr(
        snap_mod, "fetch_cn_stock_news", lambda sym, top_k=3: (),
    )
    holding = FundHolding(
        symbol="600519", name_cn="贵州茅台",
        exchange="SH", weight_pct=8.0,
    )
    evidence, _failures = snap_mod._evidence_for_constituent(
        holding, fund_id="005827",
    )
    filings = [e for e in evidence if e.type == "filing"]
    assert len(filings) == 1
    ev = filings[0]
    assert ev.scope == "constituent"
    assert ev.citation_kind == "data"
    assert "revenue_yoy=" not in ev.summary
    assert ev.summary == "600519 2026Q1 财报已披露（口径未核实）"


def test_evidence_for_constituent_hk_uses_disclosure_existence_template(
    monkeypatch,
) -> None:
    """F6 AC #1 — active-fund HK branch — same template lock."""
    from irc.fundamentals import snapshot as snap_mod
    from irc.fundamentals.types import FundHolding

    digest = _filing("00700", 0.12, period="2026H1")
    monkeypatch.setattr(
        snap_mod, "fetch_hk_filing_digest", lambda sym: digest,
    )
    monkeypatch.setattr(
        snap_mod, "hk_news_adapter_available", lambda: False,
    )
    holding = FundHolding(
        symbol="00700", name_cn="腾讯控股",
        exchange="HK", weight_pct=6.5,
    )
    evidence, _failures = snap_mod._evidence_for_constituent(
        holding, fund_id="005827",
    )
    filings = [e for e in evidence if e.type == "filing"]
    assert len(filings) == 1
    ev = filings[0]
    assert ev.scope == "constituent"
    assert ev.citation_kind == "data"
    assert "revenue_yoy=" not in ev.summary
    assert ev.summary == "00700 2026H1 财报已披露（口径未核实）"
```

NOTE: if the existing `_filing` helper at line 145 of
`test_thesis_evidence.py` does not accept the `period` kwarg, this
test must use it as-is. Re-read that helper at line 145:

```python
def _filing(symbol: str, yoy: float | None, *, period: str = "Q1") -> FilingDigest:
```

`period` is already a keyword with default `"Q1"`. Good — Task 3
tests pass `period="2026Q1"` / `period="2026H1"` directly.

If `FundHolding`'s constructor signature differs from `(symbol,
name_cn, exchange, weight_pct)`, look it up in
`src/irc/fundamentals/types.py` and adjust the kwargs in the test
to match — do not invent fields.

- [ ] **Step 3.2: Run the new active-fund tests — they must FAIL red**

```bash
uv run pytest tests/opportunity/test_thesis_evidence.py::test_evidence_for_constituent_cn_uses_disclosure_existence_template tests/opportunity/test_thesis_evidence.py::test_evidence_for_constituent_hk_uses_disclosure_existence_template -v
```

Expected: both fail on the
`ev.summary == "{symbol} {period} 财报已披露（口径未核实）"`
assertion because the current producers emit
`f"{digest.symbol} {digest.fiscal_period} revenue_yoy={digest.revenue_yoy}"`.

---

## Task 4: Green — reframe `_evidence_for_constituent` summary templates (CN + HK)

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py:344` (CN branch).
- Modify: `src/irc/fundamentals/snapshot.py:395` (HK branch).

- [ ] **Step 4.1: Replace the CN-branch summary template**

In `src/irc/fundamentals/snapshot.py`, change line 344:

Before:
```python
                    summary=f"{digest.symbol} {digest.fiscal_period} revenue_yoy={digest.revenue_yoy}",
```

After:
```python
                    summary=f"{digest.symbol} {digest.fiscal_period} 财报已披露（口径未核实）",
```

- [ ] **Step 4.2: Replace the HK-branch summary template**

In `src/irc/fundamentals/snapshot.py`, change line 395 (inside the
`elif holding.exchange == "HK":` branch):

Before:
```python
                    summary=f"{digest.symbol} {digest.fiscal_period} revenue_yoy={digest.revenue_yoy}",
```

After:
```python
                    summary=f"{digest.symbol} {digest.fiscal_period} 财报已披露（口径未核实）",
```

- [ ] **Step 4.3: Run the active-fund tests — they must PASS green**

```bash
uv run pytest tests/opportunity/test_thesis_evidence.py::test_evidence_for_constituent_cn_uses_disclosure_existence_template tests/opportunity/test_thesis_evidence.py::test_evidence_for_constituent_hk_uses_disclosure_existence_template -v
```

Expected: both pass.

- [ ] **Step 4.4: Re-run the legacy-producer tests to confirm no regression**

```bash
uv run pytest tests/opportunity/test_thesis_evidence.py::test_filing_evidence_summary_uses_disclosure_existence_template_legacy tests/opportunity/test_thesis_evidence.py::test_filing_evidence_preserves_structural_role_legacy -v
```

Expected: both pass.

---

## Task 5: Red test — appendix caveat trigger substring switch (AC #6)

**Files:**
- Modify (test only): `tests/memo/test_pipeline_sanitization.py`
  (append at end of file).

- [ ] **Step 5.1: Append failing test for the new trigger substring**

Append at the bottom of
`tests/memo/test_pipeline_sanitization.py`:

```python
# ── F6: appendix caveat trigger substring switch ─────────────────────────────

def test_appendix_caveat_fires_on_new_disclosure_existence_phrase() -> None:
    """F6 AC #6 — `_format_appendix_line` triggers the
    `⚠️ 合规警示：…` prefix when the rendered ref carries the locked
    F6 phrase `财报已披露（口径未核实）`, matching the new producer
    templates in `snapshot.py` and `thesis_evidence.py`.
    """
    from irc.memo.pipeline import _format_appendix_line

    ref = (
        "[ref:abcdef0123456789] filing · 600519.SH · 2026-03-31: "
        "600519 2026Q1 财报已披露（口径未核实）"
    )
    out = _format_appendix_line(ref)
    assert out.startswith("- ⚠️ 合规警示：")
    assert "原始证据：" in out
    assert ref in out


def test_appendix_caveat_no_longer_keys_on_revenue_yoy_substring() -> None:
    """F6 AC #6 — defensive: the old `revenue_yoy=` substring is no
    longer the trigger (because producers no longer emit it).

    This is a single-locus guard — if a regression re-introduces the
    `revenue_yoy=` substring keying, this test fires.
    """
    from irc.memo.pipeline import _format_appendix_line

    ref_with_old_phrase = (
        "[ref:abcdef0123456789] filing · 600519.SH · 2026-03-31: "
        "600519 2026Q1 revenue_yoy=-0.0771"
    )
    out = _format_appendix_line(ref_with_old_phrase)
    # The producer no longer emits this phrase, so the trigger MUST
    # NOT fire on it. (Belt-and-braces: stops a future engineer
    # from accidentally re-keying on the legacy substring.)
    assert not out.startswith("- ⚠️ 合规警示：")
```

- [ ] **Step 5.2: Update the existing appendix-caveat test to use the new phrase**

In `tests/memo/test_pipeline_sanitization.py`, locate
`test_evidence_appendix_adds_revenue_yoy_caveat_after_verbatim_ref`
around line 56-66. Update the ref fixture string so the assertion
runs against the new trigger phrase:

Before (lines 56-66):
```python
def test_evidence_appendix_adds_revenue_yoy_caveat_after_verbatim_ref():
    refs = [
        "akshare:filing:300308:2026-04-28 — "
        "300308.SZ 2026Q1 revenue_yoy=1.921169094232574"
    ]
    out = _render_evidence_appendix(refs)
    assert "合规警示" in out
    assert "该字段含义及换算口径未经核实" in out
    assert "数值不得作为业绩依据引用" in out
    assert "原始证据：" in out
    assert out.index("合规警示") < out.index("revenue_yoy=")
```

After:
```python
def test_evidence_appendix_adds_revenue_yoy_caveat_after_verbatim_ref():
    # F6: trigger substring is now the locked disclosure-existence
    # phrase `财报已披露（口径未核实）`, not `revenue_yoy=`. The
    # caveat text itself is unchanged (operator-facing wording is
    # preserved verbatim per ADR 0001 §5.2).
    refs = [
        "akshare:filing:300308:2026-04-28 — "
        "300308.SZ 2026Q1 财报已披露（口径未核实）"
    ]
    out = _render_evidence_appendix(refs)
    assert "合规警示" in out
    assert "该字段含义及换算口径未经核实" in out
    assert "数值不得作为业绩依据引用" in out
    assert "原始证据：" in out
    assert out.index("合规警示") < out.index("财报已披露")
```

Leave the sanitizer-input tests at lines 86-108 unchanged — those
exercise `sanitize_unverified_revenue_yoy`, which strips
LLM-hallucinated `revenue_yoy=` substrings. That belt-and-braces
defense is independent of the producer-side template and stays.

- [ ] **Step 5.3: Run the new + updated appendix tests — they must FAIL red**

```bash
uv run pytest tests/memo/test_pipeline_sanitization.py::test_appendix_caveat_fires_on_new_disclosure_existence_phrase tests/memo/test_pipeline_sanitization.py::test_appendix_caveat_no_longer_keys_on_revenue_yoy_substring tests/memo/test_pipeline_sanitization.py::test_evidence_appendix_adds_revenue_yoy_caveat_after_verbatim_ref -v
```

Expected:
- `test_appendix_caveat_fires_on_new_disclosure_existence_phrase`: FAIL — current trigger keys on `revenue_yoy=`, not the new phrase.
- `test_appendix_caveat_no_longer_keys_on_revenue_yoy_substring`: FAIL — current trigger fires on the old substring.
- `test_evidence_appendix_adds_revenue_yoy_caveat_after_verbatim_ref` (updated): FAIL — same root cause.

---

## Task 6: Green — switch `_format_appendix_line` trigger substring

**Files:**
- Modify: `src/irc/memo/pipeline.py:176`.

- [ ] **Step 6.1: Replace the trigger substring**

In `src/irc/memo/pipeline.py`, change line 176 inside
`_format_appendix_line`:

Before:
```python
def _format_appendix_line(ref: str) -> str:
    if "revenue_yoy=" in ref:
        return f"- {_REVENUE_YOY_APPENDIX_CAVEAT} 原始证据：{ref}"
    return f"- {ref}{_appendix_caveats(ref)}"
```

After:
```python
def _format_appendix_line(ref: str) -> str:
    # F6 / ADR 0001 §5.2: trigger substring is the locked
    # disclosure-existence phrase `财报已披露（口径未核实）` emitted
    # by every filing-evidence producer. The caveat text is
    # preserved verbatim — operator-facing compliance posture is
    # unchanged.
    if "财报已披露（口径未核实）" in ref:
        return f"- {_REVENUE_YOY_APPENDIX_CAVEAT} 原始证据：{ref}"
    return f"- {ref}{_appendix_caveats(ref)}"
```

NOTE: full-width parentheses `（）` in the substring — must match
the producer template byte-for-byte. Do NOT replace with ASCII `()`.

- [ ] **Step 6.2: Run the appendix tests — they must PASS green**

```bash
uv run pytest tests/memo/test_pipeline_sanitization.py::test_appendix_caveat_fires_on_new_disclosure_existence_phrase tests/memo/test_pipeline_sanitization.py::test_appendix_caveat_no_longer_keys_on_revenue_yoy_substring tests/memo/test_pipeline_sanitization.py::test_evidence_appendix_adds_revenue_yoy_caveat_after_verbatim_ref -v
```

Expected: all three pass.

---

## Task 7: Red test — Policy B rule 3 still considers filings as constituent-scope data evidence (AC #2)

**Files:**
- Modify (test only): `tests/opportunity/test_policy_b.py` (append
  at end of file).

- [ ] **Step 7.1: Inspect Policy B test scaffolding**

First, open `tests/opportunity/test_policy_b.py` and find any
existing helper that builds an `ActiveFundSnapshot` with one ranked
holding carrying filing-typed `citation_kind="data"` evidence. If
such a helper exists (e.g. `_active_snap_with_filing(...)`), reuse
it. If not, build the snapshot inline using the patterns already in
that file. Do not invent new helper modules.

If `tests/opportunity/test_policy_b.py` has no relevant scaffolding,
append the inline-construction variant below.

- [ ] **Step 7.2: Append the F6 regression test**

Append at the bottom of `tests/opportunity/test_policy_b.py`:

```python
# ── F6: Policy B rule 3 keeps firing on shape, not summary text ──────────────

def test_policy_b_rule3_accepts_new_filing_summary_phrase() -> None:
    """F6 AC #2 — Policy B rule 3 reads evidence shape
    (`type`, `citation_kind`, `scope`), NOT the summary text.

    An active fund whose top-N ranked holding carries a filing-typed
    `citation_kind="data" AND scope="constituent"` evidence row MUST
    remain publishable under Policy B even though the summary now
    reads `财报已披露（口径未核实）` instead of `revenue_yoy=...`.
    """
    from irc.fundamentals.types import ActiveFundSnapshot
    from irc.opportunity.policy_b import evaluate_policy_b
    from irc.opportunity.types import (
        ConstituentAnalysis,
        ThesisEvidence,
    )

    filing_ev = ThesisEvidence(
        type="filing",
        source="600519",
        url="https://example.com/filing/600519",
        date="2026-04-28",
        summary="600519 2026Q1 财报已披露（口径未核实）",  # F6 phrase
        scope="constituent",
        citation_kind="data",
        owner_instrument_id="005827",
        parent_fund_id="005827",
        constituent_key="600519",
        holding_weight_pct=8.0,
    )
    # Information leg — any non-data citation_kind row with the same
    # scope completes dual coverage so Policy B rule 3 has nothing
    # to fire on.
    broker_ev = ThesisEvidence(
        type="broker",
        source="中信证券",
        url="https://example.com/broker/600519",
        date="2026-04-25",
        summary="中信证券 增持: 600519 研报",
        scope="constituent",
        citation_kind="information",
        owner_instrument_id="005827",
        parent_fund_id="005827",
        constituent_key="600519",
        holding_weight_pct=8.0,
    )
    analysis = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=8.0,
        evidence=(filing_ev, broker_ev),
        failure_reasons=(),
        one_line_view="600519.SH 2026Q1 财报已",   # F6 side-effect on summary[:24]
    )
    snap = ActiveFundSnapshot(
        fund_id="005827", source_report_date="2026-03-31",
        source_report_quarter="2026Q1", cache_probed_at="2026-05-27",
        constituent_analyses=(analysis,),
        failure_reasons_by_symbol={},
    )

    verdict = evaluate_policy_b(snap)

    # Publishable: no `incomplete_constituent_data` rule-3 fire.
    assert "incomplete_constituent_data" not in verdict.failure_codes, (
        f"Policy B rule 3 fired against the F6 phrase; verdict={verdict}"
    )
```

NOTE: `evaluate_policy_b`'s exact return-shape and attribute names
(`failure_codes` vs `gap_codes` vs `verdict_codes`) may differ —
look up the actual function in `src/irc/opportunity/policy_b.py`
before editing the assertion. The semantic intent is: Policy B rule
3 (`incomplete_constituent_data`) does NOT fire when every ranked
holding carries `citation_kind="data" AND scope="constituent"`
evidence — adjust the attribute name to match whatever
`evaluate_policy_b` actually returns. Do NOT modify
`policy_b.py` itself.

- [ ] **Step 7.3: Run the new Policy B test — it should PASS green immediately**

```bash
uv run pytest tests/opportunity/test_policy_b.py::test_policy_b_rule3_accepts_new_filing_summary_phrase -v
```

Expected: PASS. This is a *regression-lock* test, not a red→green
test — Policy B already reads evidence shape, not summary text, so
the F6 reframe should not fire rule 3. If it FAILS, that means
either (a) the attribute name on the verdict object is wrong (fix
the test) or (b) there is a hidden coupling between Policy B and
summary text that the spec did not foresee (STOP — this is an
unstated constraint; report back to the orchestrator before
proceeding).

---

## Task 8: Lock-step update — synthesizer prompt clause (ADR 0001 §5.1)

**Files:**
- Modify: `src/irc/memo/synthesizer.py:55-56`.

- [ ] **Step 8.1: Re-read the relevant prompt lines**

In `src/irc/memo/synthesizer.py`, the rule-5 trailer (around lines
55-56) currently reads:

```python
"遇到 revenue_yoy 原始小数值时，不得主动换算为百分比/百分数；如必须提及，只能写"
"'revenue_yoy=原始字段值（具体含义及换算口径待核实，不得直接引用为业绩依据）'。\n"
```

- [ ] **Step 8.2: Replace the rule-5 trailer with the F6-aligned phrasing**

Update those two lines in `_GUARDRAILS` to reference the new
template and continue forbidding any free-text `revenue_yoy=`
output:

Before:
```python
"遇到 revenue_yoy 原始小数值时，不得主动换算为百分比/百分数；如必须提及，只能写"
"'revenue_yoy=原始字段值（具体含义及换算口径待核实，不得直接引用为业绩依据）'。\n"
```

After:
```python
"filing 证据条目格式为 `{symbol} {fiscal_period} 财报已披露（口径未核实）`；"
"不得自行换算或推断同比数值，禁止在任何段落输出 `revenue_yoy=...` 这类原始字段；"
"如需引用 filing，请仅引用披露事实与日期。\n"
```

NOTE: keep the f-string literal exactly as written above (the
`{symbol}` / `{fiscal_period}` placeholders inside backticks are
prompt-internal documentation for the LLM, NOT Python f-string
substitutions — there is no `f"..."` prefix). Match the existing
indentation and string-concatenation style in the surrounding
tuple.

- [ ] **Step 8.3: Run the memo prompt-related tests to ensure no fixture pins the old phrasing verbatim**

```bash
uv run pytest tests/memo/test_synthesizer_glossary.py tests/memo/test_pipeline_sanitization.py -v
```

Expected: green. If any test pins the literal old prompt text, it
will fail — update the fixture to reference the new phrasing in the
same commit. The `sanitize_unverified_revenue_yoy` tests at
`test_pipeline_sanitization.py:86-108` MUST continue to pass — they
exercise the belt-and-braces sanitizer regardless of prompt text.

---

## Task 9: Full-suite green + lint

**Files:** none modified in this task; verification only.

- [ ] **Step 9.1: Run the opportunity + memo test suites**

```bash
uv run pytest tests/opportunity tests/memo -v
```

Expected: all pass. Pay attention to:
- `test_thesis_evidence.py` — all original tests + F6 additions green.
- `test_pipeline_sanitization.py` — appendix-caveat + sanitizer tests green.
- `test_policy_b.py` — original rule 3 cases + F6 regression test green.
- `test_same_3_invariant.py` (AC #5) — pairwise citation-id equality across picks-table / evidence-pool / discipline still holds.
- `test_citation_map.py`, `test_auditor.py`, `test_report*.py` — no regressions on the dual-coverage gate (AC #4) or `find_uncited_opportunity_rows`.

If any pre-existing test that pins literal `revenue_yoy=` or
`营收同比 +X%` content fails, the fix is:
1. If the test is exercising producer output → update the fixture
   string to the new F6 phrase.
2. If the test is exercising the sanitizer or LLM-prompt input → keep
   the old `revenue_yoy=` string in the fixture (the sanitizer
   strips LLM hallucinations and must continue to handle the legacy
   substring).

- [ ] **Step 9.2: Run the full test suite (no markers) to catch broader regressions**

```bash
uv run pytest -q
```

Expected: green (ignoring any pre-existing `live_akshare` /
`live_llm` skips which require explicit env vars per CLAUDE.md).

- [ ] **Step 9.3: Lint**

```bash
uv run ruff check src tests
```

Expected: no new findings. (Line-length 100, target py312.) If
ruff reports a line-length violation on a Chinese-string line,
break the f-string across two adjacent string literals — Python's
implicit concatenation handles the rest.

---

## Task 10: Live sanity check against `outputs/2026-05-27/`

**Files:** none modified in this task; manual verification only.

- [ ] **Step 10.1: Regenerate memo against today's outputs**

```bash
uv run irc run --only memo
```

(`--only memo` runs the memo stage against the cached opportunity
outputs under `outputs/2026-05-27/`. If your run dir is older than
2026-05-27, sub in the correct ISO date via `IRC_RUN_DATE` per the
CLI conventions in `README.md`.)

Expected: the command exits 0. Watch for any
`fetch_budget_exhausted` or audit-gate fatals — these would
indicate an unrelated regression and STOP.

- [ ] **Step 10.2: Verify filing rows no longer show `revenue_yoy=` inline**

```bash
grep -nE "revenue_yoy=" outputs/2026-05-27/memo.md || echo "OK: no inline revenue_yoy= substrings"
```

Expected output: `OK: no inline revenue_yoy= substrings`.

(If any line still contains the substring, it should ONLY be the
sanitizer's CAVEAT text `财务数据字段含义及换算口径...` — NOT a
producer-side filing summary. Inspect the matching lines to confirm.)

- [ ] **Step 10.3: Verify the appendix `⚠️ 合规警示` still fires next to filing rows**

```bash
grep -nE "财报已披露（口径未核实）" outputs/2026-05-27/memo.md
grep -nE "⚠️ 合规警示" outputs/2026-05-27/memo.md
```

Expected: both grep calls return matches. The two counts should
roughly correlate — every appendix line containing the F6 phrase
should be prefixed by the `⚠️ 合规警示：...` caveat (one-to-one
modulo any non-filing caveats from `_appendix_caveats`).

- [ ] **Step 10.4: Spot-check §5 / §6 filing rows**

Read `outputs/2026-05-27/memo.md` and confirm:
- §5 picks-evidence filing rows render
  `... filing · {symbol}.{exch} · {date}: {symbol} {period} 财报已披露（口径未核实）`
  (no `revenue_yoy=<raw>` substring).
- §6 discipline-renderer nested filing bullets render
  `- [ref:{HEX16}] filing · {symbol}.{exch} · {date}` (identifier-only,
  unchanged shape).
- The appendix `## 附录·原始证据 (Raw Evidence)` block shows
  `- ⚠️ 合规警示：... 原始证据：... 财报已披露（口径未核实）`.

Note: outputs are NOT committed by this PR — Task 10 is a sanity
gate only. If the sanity check passes, proceed to commit. If it
fails, STOP and investigate.

---

## Task 11: Commit

**Files:** all source + test changes staged together.

- [ ] **Step 11.1: Review the diff one last time**

```bash
git diff --stat
git diff src/ tests/
```

Expected: changes only in
`src/irc/opportunity/thesis_evidence.py`,
`src/irc/fundamentals/snapshot.py`,
`src/irc/memo/pipeline.py`,
`src/irc/memo/synthesizer.py`,
`tests/opportunity/test_thesis_evidence.py`,
`tests/opportunity/test_policy_b.py`,
`tests/memo/test_pipeline_sanitization.py`.

NO changes to:
- `src/irc/opportunity/{policy_b.py, citation_selector.py, types.py}`.
- ADRs / CONTEXT.md (already amended in grill phase at commit 5a832ba).
- `outputs/<date>/`.
- Any IRC_*_BEGIN/END marker.

- [ ] **Step 11.2: Stage only the listed files (avoid `git add -A`)**

```bash
git add \
    src/irc/opportunity/thesis_evidence.py \
    src/irc/fundamentals/snapshot.py \
    src/irc/memo/pipeline.py \
    src/irc/memo/synthesizer.py \
    tests/opportunity/test_thesis_evidence.py \
    tests/opportunity/test_policy_b.py \
    tests/memo/test_pipeline_sanitization.py
```

Expected: no output. Confirm staged state with `git status`.

- [ ] **Step 11.3: Commit with a descriptive message**

The implementing agent picks the commit title; use a Conventional
Commits–style prefix and reference the item ID. Example:

```bash
git commit -m "$(cat <<'EOF'
feat(opportunity+memo): F6 — reframe filing-evidence summary to disclosure-existence anchor

Producers (`_filing_evidence` legacy path + `_evidence_for_constituent`
CN & HK branches) now emit
`{symbol} {fiscal_period} 财报已披露（口径未核实）` instead of leaking
the unverified `revenue_yoy=<raw>` scalar inline. The memo appendix
caveat trigger substring in `_format_appendix_line` and the
synthesizer prompt rule-5 trailer move to the new locked phrase in
lock-step — single locus per ADR 0001 §5.2.

Structural role (Policy B rule 3, dual-coverage gate, SAME-3
invariant, `_TYPE_RANK` ordering) is fully preserved: filings
remain `type="filing"` / `citation_kind="data"` /
`scope in {"instrument","constituent"}`. Citation-id minting is
unchanged; URL-bearing filings keep their citation_ids byte-for-byte,
and the rare URL-empty filing re-rolls once per ADR 0001 §5.3.

Refs: docs/2026-05-27-pickability-followups/items/F6-spec.md,
docs/adr/0001-citation-data-model.md §5.
EOF
)"
```

Expected: commit succeeds; pre-commit hooks (if any) pass. If a
hook fails, fix the underlying issue and create a NEW commit (do
NOT amend per the project's git safety protocol).

- [ ] **Step 11.4: Confirm commit landed on the sub-branch**

```bash
git log --oneline -3
git rev-parse --abbrev-ref HEAD
```

Expected: top commit is the F6 commit; branch is
`claude/pickability-followups-F6`.

- [ ] **Step 11.5: DO NOT push**

Per the orchestrator's contract: the impl agent does not push.
The orchestrator handles upstream integration (merge to
`autodev/pickability-followups-feature`, PR, ship).

---

## Verification checklist (mapping to spec ACs)

After Task 11 lands, each spec AC should be satisfied:

| AC  | Verified by                                                                                   |
|-----|-----------------------------------------------------------------------------------------------|
| #1  | Task 1.1 / 3.1 tests assert no `revenue_yoy=` in producer summaries; locked phrase present.   |
| #2  | Task 7.2 regression test: Policy B rule 3 does not fire on the new phrase.                    |
| #3  | Task 1.1 asserts `_TYPE_RANK["filing"] == 0`; Task 9.1 runs the existing flatten-order test. |
| #4  | Task 9.1 / 9.2 run `find_uncited_opportunity_rows` audits in `tests/opportunity/test_auditor.py`. |
| #5  | Task 9.1 runs `test_same_3_invariant.py` — pairwise citation-id equality preserved.           |
| #6  | Task 5.1 + 5.2 + 6.1: appendix caveat substring trigger moved to the new phrase.              |
| #7  | Plan does not touch citation-id minting — re-roll happens naturally per ADR 0001 §2.          |
| #8  | Task 8.2 updates the synthesizer prompt rule-5 trailer in lock-step.                          |
| #9  | Task 9.1 / 9.2 keep the full opportunity + memo test suites green; no new regressions.        |
| #10 | ADR 0001 §5 addendum + ADR 0003 §1 rule 3 pointer landed in the grill phase at 5a832ba.       |

---

## Self-review notes

- **Spec coverage:** All 10 ACs map to a task above. AC #10 is
  already landed (ADR amendments at commit 5a832ba per the grill
  output); the plan does not re-edit ADRs.
- **Placeholder scan:** No `TBD` / "implement later" / "TODO" markers.
  Each step contains the exact diff or exact assertion text the
  engineer needs.
- **Type consistency:** `ThesisEvidence`, `FilingDigest`,
  `FundHolding`, `ActiveFundSnapshot`, `ConstituentAnalysis` are
  referenced consistently across tasks; field names
  (`source`, `url`, `date`, `summary`, `scope`, `citation_kind`,
  `owner_instrument_id`, `parent_fund_id`, `constituent_key`,
  `holding_weight_pct`) match the dataclass contract in
  `src/irc/opportunity/types.py`.
- **Non-goals respected:** Plan does not modify Policy B logic,
  `_TYPE_RANK`, citation_id minting, ADRs, fetch adapters, or any
  IRC_*_BEGIN/END marker. Producer-side reframe + single appendix
  trigger substring switch + lock-step prompt-clause update.
