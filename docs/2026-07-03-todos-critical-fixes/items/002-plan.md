# Item 002 — `ActiveFundSnapshot` dual-leg thesis gate: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the dual-leg (≥1 `citation_kind="data"` AND ≥1 `citation_kind="information"`) thesis heuristic to the `ActiveFundSnapshot` branch of `derive_thesis_from_evidence`, so data-only (e.g. filing-only) evidence yields `evidence_insufficient` instead of `intact` — killing the `irc eval-funds` / `irc narrative --analyze` `core_dca` false positive.

**Architecture:** One pure helper (`_active_dual_leg_state`) added to `src/irc/opportunity/thesis_evidence.py`, replacing the branch's `if flattened:` state/reason block. The empty-flattened guard runs FIRST inside the helper (load-bearing — ADR 0003 §8 property 3); only then is the presence-only union `flattened ∪ snapshot.fund_level_evidence` leg-checked. All five return slots except `(state, reason)` are byte-identical to today. No signature change, no new `ThesisState` literal, no new gap code.

**Tech Stack:** Python 3.12, uv, pytest, ruff (line-length 100).

## Global Constraints

- **TDD mandatory** — failing tests first; red-state expectations spelled out below.
- **Purity** — `derive_thesis_from_evidence` stays a pure function; no I/O, no snapshot mutation.
- **Size budget** — `thesis_evidence.py` is 460 lines (already over the <200 ideal): add ≈20 net lines only; branch stays <20 lines; no nesting >3 levels.
- **No VERSION bump** — CHANGELOG `[Unreleased]` only (versioning convention).
- **Reason literals are exact** (AC3/AC5/AC6) — copy byte-for-byte from this plan; the intact literal `f"主动基金 {len(analyses)} 个核心持仓的成分股证据已收集。"` and empty literal `"主动基金未能收集到任何成分股证据。"` are regression-locked.
- **`tests/commands/` hangs as a whole dir** — run per-file only.
- **Known-failure diff-scoping** — full pytest is NOT green on main (24 pre-existing failures); replay any sweep failure on the base branch before assuming a regression.
- **CONTEXT.md + ADR 0003 §8 are ALREADY committed** by the grill (commit `954d54a4` on `autodev/todos-critical-fixes-feature`). Do NOT re-edit them; this plan's doc work is CHANGELOG + TODOS.md only (AC13).
- **Branch:** the orchestrator creates `claude/todos-critical-fixes-002`. No branch-creation or PR steps here.

## Verified current state (all line numbers checked 2026-07-03)

- `src/irc/opportunity/thesis_evidence.py:375-393` — active branch; `:385-392` is the naive `if flattened: intact` block to replace. `ThesisState`/`ThesisEvidence` already imported at `:26`. `_classify_constituent_gap` ends at `:327`; `derive_thesis_from_evidence` starts at `:330`.
- `src/irc/fundamentals/types.py:244` — `ActiveFundSnapshot.fund_level_evidence: tuple[ThesisEvidence, ...] = ()` (frozen; pre-field caches deserialize to `()` → strict data-only path, intended).
- Fund-level producer shapes (`src/irc/fundamentals/snapshot.py:186-221`): NAV data leg = `type="snapshot"`, `citation_kind="data"`, `scope="instrument"`, `parent_fund_id=None`, `constituent_key=None`; announcement info leg = `type="news"`, `citation_kind="information"`, same scope/None fields. Test fixtures below mirror these exactly.
- `should_emit_top_holdings_broker_thin` fires ONLY on `broker_empty:*` failure reasons (`src/irc/opportunity/advisory_gaps.py:29-31`) — pure-failure fixtures below use `filing_fetch_failed:*` so the gaps slot stays `()` (AC7 assertions).
- Existing tests exercising `derive_thesis_from_evidence` (caller sweep universe): `tests/opportunity/test_thesis_evidence.py`, `test_top_holdings_broker_thin.py`, `test_thesis_relevance_gate.py`, `test_fund_eval.py` (indirect via `build_opportunity_row`), `test_states.py:755+` (indirect), `test_valuation_fundamental_anchor.py:222` (indirect), `tests/narrative/` (via `analyze`), `tests/commands/test_opportunity_cmd.py` + `test_opportunity_cmd_acceptance.py` (indirect), `tests/integration/test_publishable_set_lockdown.py`. None asserts `intact` on a data-only active fixture (spec AC12 survey; re-verified: `test_thesis_evidence.py:21` and `test_states.py:755` assert only evidence/analyses/fetch-type slots).

## Design decisions locked by this plan

1. **Helper shape:** `_active_dual_leg_state(flattened, fund_level_evidence, analyses_count) -> tuple[ThesisState, str]` — a single state+reason helper rather than the spec's `_has_dual_legs -> bool` example. Rationale: the spec's size budget ("keep the branch <20 lines"; task constraint "extract a helper if the branch logic would push a function past ~20 lines") — a bool helper leaves a ~20-line if/elif ladder in the branch; the state+reason helper shrinks the branch to 3 lines and keeps the load-bearing ordering (empty guard → union check) in ONE place with its docstring. Same ≈20 net lines either way.
2. **`# type: ignore[return-value]` on the return line is kept** — byte-minimal change to the return statement's tail; removing it is out of scope.
3. **New tests are appended** to the two mirror test files (no new test files) per the TDD constraint "tests mirror source".
4. **Red/green honesty:** only 3 of the 8 new tests are RED pre-fix (AC1, AC2, AC9 — the actual bug). AC3/AC4×2/AC5(a)/AC5(b) are GREEN pre-fix regression locks whose kill-targets are *wrong implementations*: AC4 kills a constituent-only check; AC5(b) kills a union-first check (grill R1). Task 1/2 run them pre-fix and verify exactly this red/green split.

---

### Task 1: Failing + locking tests — `tests/opportunity/test_thesis_evidence.py`

**Files:**
- Modify: `tests/opportunity/test_thesis_evidence.py` (append at end of file; currently 698 lines)

**Interfaces:**
- Consumes: `derive_thesis_from_evidence` (module-scope import already at `:101`), `_make_evidence` helper (`:9`, module scope — derives `citation_kind` as `"data"` for `type_="filing"`, else `"information"`).
- Produces: test names consumed verbatim by the TODOS.md annotation in Task 5.

- [ ] **Step 1.1: Append the item-002 test section**

Append the following at the very end of `tests/opportunity/test_thesis_evidence.py`:

```python
# ── Item 002 (todos-critical-fixes 2026-07-03): ActiveFundSnapshot dual-leg gate ──
# Spec: docs/2026-07-03-todos-critical-fixes/items/002-spec.md
# ADR 0003 §8; CONTEXT.md "Dual-leg thesis heuristic".


def _fund_level_leg(kind: str, *, owner: str = "005827"):
    """Fund-level evidence in the exact producer shapes (fundamentals/snapshot.py
    :186-221): NAV data leg (type="snapshot") / announcement information leg
    (type="news"). scope="instrument", owner=fund_id, parent/constituent None."""
    from irc.opportunity.types import ThesisEvidence
    if kind == "data":
        return ThesisEvidence(
            type="snapshot", source=owner, url="",
            date="2026-06-30", summary="NAV=1.2345 @ 2026-06-30",
            scope="instrument", citation_kind="data",
            owner_instrument_id=owner, parent_fund_id=None, constituent_key=None,
        )
    return ThesisEvidence(
        type="news", source="fund_announcement_report_em", url="",
        date="2026-06-30", summary="[RPT1] 2026年第二季度报告",
        scope="instrument", citation_kind="information",
        owner_instrument_id=owner, parent_fund_id=None, constituent_key=None,
    )


def _dual_leg_analysis(evidence, *, failure_reasons=()):
    from irc.opportunity.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=6.2,
        evidence=evidence, failure_reasons=failure_reasons, one_line_view="",
    )


def _dual_leg_snapshot(analyses, fund_level=()):
    from irc.fundamentals.types import ActiveFundSnapshot
    return ActiveFundSnapshot(
        fund_id="005827", source_report_date="2026-03-31",
        source_report_quarter="2026Q1", cache_probed_at="",
        constituent_analyses=analyses,
        failure_reasons_by_symbol={},
        fund_level_evidence=fund_level,
    )


def _derive_active(snap):
    return derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )


def test_active_fund_data_only_evidence_is_insufficient() -> None:
    """AC1 + AC6: non-empty flattened, all data-leg, fund_level=() → NOT intact;
    missing-information-leg reason literal."""
    con = _make_evidence("filing", 6.2, "d1")
    snap = _dual_leg_snapshot((_dual_leg_analysis((con,)),))
    state, reason, evidence, gaps, _ = _derive_active(snap)
    assert state == "evidence_insufficient"
    assert reason == "主动基金证据缺少信息腿（券商/新闻/公告），长期逻辑暂不背书。"
    assert evidence == (con,)   # AC8: evidence slot byte-identical
    assert gaps == ()           # AC7: gaps slot byte-identical


def test_active_fund_info_only_evidence_is_insufficient() -> None:
    """AC2 + AC6: non-empty flattened, all information-leg → missing data leg."""
    con = _make_evidence("broker", 6.2, "i1")
    snap = _dual_leg_snapshot((_dual_leg_analysis((con,)),))
    state, reason, evidence, gaps, _ = _derive_active(snap)
    assert state == "evidence_insufficient"
    assert reason == "主动基金证据缺少数据腿（成分股财报），长期逻辑暂不背书。"
    assert evidence == (con,)
    assert gaps == ()


def test_active_fund_constituent_dual_leg_stays_intact() -> None:
    """AC3 (regression lock, GREEN pre-fix): flattened carries data + information
    → intact with the reason literal byte-identical to today."""
    ev = (_make_evidence("filing", 6.2, "d1"), _make_evidence("broker", 6.2, "i1"))
    snap = _dual_leg_snapshot((_dual_leg_analysis(ev),))
    state, reason, evidence, gaps, _ = _derive_active(snap)
    assert state == "intact"
    assert reason == "主动基金 1 个核心持仓的成分股证据已收集。"
    assert gaps == ()


def test_active_fund_fund_level_info_leg_satisfies_gate() -> None:
    """AC4 (kills a constituent-only implementation): data-only constituent
    evidence + fund-level announcement (information) → intact; the returned
    evidence tuple stays flattened-constituent-only (fund_level NOT merged —
    that remains _stamp_fund_level_evidence_from_verdict's job)."""
    con = _make_evidence("filing", 6.2, "d1")
    snap = _dual_leg_snapshot(
        (_dual_leg_analysis((con,)),),
        fund_level=(_fund_level_leg("information"),),
    )
    state, _, evidence, gaps, _ = _derive_active(snap)
    assert state == "intact"
    assert evidence == (con,)
    assert gaps == ()


def test_active_fund_fund_level_data_leg_satisfies_gate() -> None:
    """AC4 mirror: info-only constituent evidence + fund-level NAV (data) → intact."""
    con = _make_evidence("broker", 6.2, "i1")
    snap = _dual_leg_snapshot(
        (_dual_leg_analysis((con,)),),
        fund_level=(_fund_level_leg("data"),),
    )
    state, _, evidence, gaps, _ = _derive_active(snap)
    assert state == "intact"
    assert evidence == (con,)
    assert gaps == ()


def test_active_fund_empty_evidence_stays_insufficient_plain() -> None:
    """AC5(a) (regression lock): empty flattened + fund_level=() → the existing
    empty-reason literal, unchanged."""
    snap = _dual_leg_snapshot(
        (_dual_leg_analysis((), failure_reasons=("filing_fetch_failed:600519",)),),
    )
    state, reason, evidence, gaps, _ = _derive_active(snap)
    assert state == "evidence_insufficient"
    assert reason == "主动基金未能收集到任何成分股证据。"
    assert evidence == ()
    assert gaps == ()


def test_active_fund_empty_flattened_with_dual_leg_fund_level_stays_insufficient() -> None:
    """AC5(b) — the naive-implementation killer (grill R1; ADR 0003 §8 property 3).

    Rule-2.5-publishable shape: ALL top-N constituents pure-failure (empty
    evidence, non-empty failure_reasons — reachable per ADR 0003 §7's
    2026-06-04 reconciliation) + fund_level_evidence carrying BOTH legs.
    The empty-flattened guard must short-circuit BEFORE the union leg check;
    a union-first implementation would flip this *published* row
    evidence_insufficient → intact (AC10 invariance would break).
    """
    snap = _dual_leg_snapshot(
        (_dual_leg_analysis((), failure_reasons=("filing_fetch_failed:600519",)),),
        fund_level=(_fund_level_leg("data"), _fund_level_leg("information")),
    )
    state, reason, evidence, gaps, _ = _derive_active(snap)
    assert state == "evidence_insufficient"
    assert reason == "主动基金未能收集到任何成分股证据。"
    assert evidence == ()
    assert gaps == ()
```

- [ ] **Step 1.2: Run the file — verify the exact red/green split**

Run:

```bash
uv run pytest tests/opportunity/test_thesis_evidence.py -v 2>&1 | tail -20
```

Expected: **exactly 2 failed** (both with `AssertionError: assert 'intact' == 'evidence_insufficient'` on the first assert):

- `test_active_fund_data_only_evidence_is_insufficient` — FAILED (RED, the bug: AC1)
- `test_active_fund_info_only_evidence_is_insufficient` — FAILED (RED, the bug: AC2)

and **all other tests PASSED**, including the 5 new locks — `test_active_fund_constituent_dual_leg_stays_intact`, `test_active_fund_fund_level_info_leg_satisfies_gate`, `test_active_fund_fund_level_data_leg_satisfies_gate`, `test_active_fund_empty_evidence_stays_insufficient_plain`, `test_active_fund_empty_flattened_with_dual_leg_fund_level_stays_insufficient` — and every pre-existing test (notably `test_active_fund_thesis_evidence_flatten_ordering`, AC8).

If anything OTHER than the two named tests fails, STOP: either a fixture is wrong (compare against the producer shapes at `src/irc/fundamentals/snapshot.py:186-221`) or a pre-existing failure needs diff-scoping against the base branch.

No commit yet (tests are red; they commit together with the fix in Task 3).

---

### Task 2: Failing test — eval-funds surface, `tests/opportunity/test_fund_eval.py`

**Files:**
- Modify: `tests/opportunity/test_fund_eval.py` (append at end of file; currently 135 lines)

**Interfaces:**
- Consumes: `evaluate_fund`, `FundEval` (imported at `:6-11`), `ActiveFundSnapshot`/`ConstituentAnalysis`/`ThesisEvidence` (imported at `:5`), `_cheap_cold_input` (`:42`), `_intact_snapshot` (`:15` — already dual-leg; its test must pass unmodified, AC9).
- Produces: test name `test_evaluate_fund_data_only_evidence_is_small_watch_not_core_dca` for the TODOS annotation (Task 5).

- [ ] **Step 2.1: Append the AC9 test**

Append at the end of `tests/opportunity/test_fund_eval.py`:

```python
# ── Item 002 (todos-critical-fixes 2026-07-03): dual-leg gate on the eval surface ──

def _data_only_snapshot(fund_id: str) -> ActiveFundSnapshot:
    """Filing-only (data-leg-only) constituent evidence, fund_level_evidence=()."""
    data_leg = ThesisEvidence(
        type="filing", source="filing", url="", date="2026-03-31",
        summary="600519 2025Q4 财报已披露（口径未核实）",
        scope="constituent", citation_kind="data",
        owner_instrument_id=fund_id, parent_fund_id=fund_id, constituent_key="600519",
    )
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=12.0,
        evidence=(data_leg,), failure_reasons=(),
        one_line_view="600519 贵州茅台",
    )
    return ActiveFundSnapshot(
        fund_id=fund_id, source_report_date="2026-03-31",
        source_report_quarter="2026Q1", cache_probed_at="2026-05-30",
        constituent_analyses=(c,), failure_reasons_by_symbol={},
    )


def test_evaluate_fund_data_only_evidence_is_small_watch_not_core_dca():
    """AC9: cheap + cold + acceptable + DATA-ONLY evidence must not compose to
    core_dca — the false-confidence bug this item fixes (TODOS.md line ~51)."""
    inp = _cheap_cold_input("980005")
    snap = _data_only_snapshot("980005")
    ev = evaluate_fund(inp, snap, role="satellite_cn_metals")
    assert ev.thesis_state == "evidence_insufficient"
    assert ev.opportunity_state == "small_watch"
    assert ev.core_dca is False
```

- [ ] **Step 2.2: Run the file — verify red**

Run:

```bash
uv run pytest tests/opportunity/test_fund_eval.py -v 2>&1 | tail -12
```

Expected: **1 failed, 6 passed**:

- `test_evaluate_fund_data_only_evidence_is_small_watch_not_core_dca` — FAILED with `AssertionError: assert 'intact' == 'evidence_insufficient'` (first assert; today the row composes to `core_dca`).
- `test_evaluate_fund_core_dca_when_cheap_cold_intact_acceptable` — PASSED unmodified (its `_intact_snapshot` already carries both legs — AC9's second clause).

---

### Task 3: The fix — `src/irc/opportunity/thesis_evidence.py`

**Files:**
- Modify: `src/irc/opportunity/thesis_evidence.py` (two edits: insert helper before `:330`; replace the state block at `:385-393`)

**Interfaces:**
- Consumes: `ThesisState`, `ThesisEvidence` (already imported from `irc.opportunity.types` at `:26`); `snapshot.fund_level_evidence` (`ActiveFundSnapshot`, default `()`).
- Produces: `_active_dual_leg_state(flattened: tuple[ThesisEvidence, ...], fund_level_evidence: tuple[ThesisEvidence, ...], analyses_count: int) -> tuple[ThesisState, str]` — module-private; no other module imports it.

- [ ] **Step 3.1: Insert the pure helper**

In `src/irc/opportunity/thesis_evidence.py`, find this anchor (end of `_classify_constituent_gap`, immediately before `derive_thesis_from_evidence`):

```python
    return None


def derive_thesis_from_evidence(
```

Replace it with:

```python
    return None


def _active_dual_leg_state(
    flattened: tuple[ThesisEvidence, ...],
    fund_level_evidence: tuple[ThesisEvidence, ...],
    analyses_count: int,
) -> tuple[ThesisState, str]:
    """(state, reason) for the ActiveFundSnapshot branch (ADR 0003 §8).

    Empty-flattened guard FIRST — load-bearing (§8 property 3): a
    rule-2.5-publishable fund whose top-N constituents are all pure-failure
    has empty flattened evidence but dual-leg fund_level_evidence, and must
    stay evidence_insufficient. The union (flattened ∪ fund_level_evidence)
    is presence-only: the caller returns the flattened tuple unchanged
    (rule-2.5 stamping stays _stamp_fund_level_evidence_from_verdict's job).
    Both-legs-missing with non-empty evidence is unreachable (citation_kind
    is validated to the two-literal set in ThesisEvidence.__post_init__).
    """
    if not flattened:
        return "evidence_insufficient", "主动基金未能收集到任何成分股证据。"
    union = flattened + fund_level_evidence
    has_data = any(e.citation_kind == "data" for e in union)
    has_info = any(e.citation_kind == "information" for e in union)
    if has_data and has_info:
        return "intact", f"主动基金 {analyses_count} 个核心持仓的成分股证据已收集。"
    if not has_data:
        return (
            "evidence_insufficient",
            "主动基金证据缺少数据腿（成分股财报），长期逻辑暂不背书。",
        )
    return (
        "evidence_insufficient",
        "主动基金证据缺少信息腿（券商/新闻/公告），长期逻辑暂不背书。",
    )


def derive_thesis_from_evidence(
```

- [ ] **Step 3.2: Rewire the active branch**

In the same file, find (lines 385–393, inside the `isinstance(snapshot, ActiveFundSnapshot)` branch):

```python
        if flattened:
            state: ThesisState = "intact"
            reason = (
                f"主动基金 {len(analyses)} 个核心持仓的成分股证据已收集。"
            )
        else:
            state = "evidence_insufficient"
            reason = "主动基金未能收集到任何成分股证据。"
        return state, reason, flattened, gaps, tuple(analyses)  # type: ignore[return-value]
```

Replace with:

```python
        # Item 002 (2026-07-03, ADR 0003 §8): dual-leg thesis heuristic over the
        # presence-only union flattened ∪ fund_level_evidence; the helper's
        # empty-flattened guard runs FIRST (load-bearing for published rows).
        state, reason = _active_dual_leg_state(
            flattened, snapshot.fund_level_evidence, len(analyses),
        )
        return state, reason, flattened, gaps, tuple(analyses)  # type: ignore[return-value]
```

Nothing else in the branch changes: `flattened = _flatten_analyses(analyses)`, the item-003/ADR-0005 comments, the `gaps` advisory block, and the return-tuple shape stay byte-identical.

- [ ] **Step 3.3: Green verification — both mirror files**

Run:

```bash
uv run pytest tests/opportunity/test_thesis_evidence.py tests/opportunity/test_fund_eval.py -v 2>&1 | tail -8
```

Expected: **all tests pass, 0 failed** (the 2 Task-1 reds and the 1 Task-2 red now green; every lock still green).

- [ ] **Step 3.4: Fast AC11 spot-check (other branches untouched)**

Run:

```bash
uv run pytest tests/opportunity/test_top_holdings_broker_thin.py \
  tests/opportunity/test_thesis_relevance_gate.py \
  tests/opportunity/test_states.py -q 2>&1 | tail -4
```

Expected: all pass, 0 failed. (`test_top_holdings_broker_thin.py::test_advisory_gap_does_not_add_to_thesis_evidence` uses a data-only fixture but asserts only `advisory_gaps` + `thesis_evidence` — passes unmodified; the FundLevel/legacy/theme-report branches were not edited.)

- [ ] **Step 3.5: Lint + line-count guard**

Run:

```bash
uv run ruff check src/irc/opportunity/thesis_evidence.py \
  tests/opportunity/test_thesis_evidence.py tests/opportunity/test_fund_eval.py \
  && wc -l src/irc/opportunity/thesis_evidence.py
```

Expected: `All checks passed!` and a line count ≈ 485 (460 + ~25 net; anything > 500 means the edit grew the file beyond plan — revisit).

- [ ] **Step 3.6: Commit (tests + fix together)**

```bash
git add src/irc/opportunity/thesis_evidence.py \
        tests/opportunity/test_thesis_evidence.py \
        tests/opportunity/test_fund_eval.py
git commit -m "fix(opportunity): dual-leg thesis gate for ActiveFundSnapshot (item 002)

intact now requires >=1 data AND >=1 information leg across the
presence-only union of flattened constituent evidence and
snapshot.fund_level_evidence; empty-flattened guard runs first
(load-bearing, ADR 0003 s8). Single-leg union -> evidence_insufficient
with direction-specific reasons. Evidence/gaps/analyses slots unchanged."
```

---

### Task 4: Caller sweep (AC11 + AC12)

Behavior-consumers of `derive_thesis_from_evidence` must all be swept (signature-change test-scope rule — signature unchanged, but the state flip propagates through `build_opportunity_row`). Run each command separately; **never run `tests/commands/` as a whole dir (it hangs)**.

**Files:** none modified (verification only).

- [ ] **Step 4.1: `tests/opportunity/` (whole dir — safe)**

```bash
uv run pytest tests/opportunity/ -q 2>&1 | tail -4
```

Expected: 0 failed (live-gated tests in `test_debate_live.py` auto-skip without `IRC_*` env).

- [ ] **Step 4.2: `tests/narrative/` (whole dir — safe; `narrative --analyze` is a Policy-B-free consumer)**

```bash
uv run pytest tests/narrative/ -q 2>&1 | tail -4
```

Expected: 0 failed. (Spec Q4(iii): no gaps are added by this change, so `position_risk_level`'s evidence_gaps-driven `insufficient` force does not fire.)

- [ ] **Step 4.3: Integration lockdown (AC10 — publishable-set invariance)**

```bash
uv run pytest tests/integration/test_publishable_set_lockdown.py -q 2>&1 | tail -4
```

Expected: 0 failed, unmodified.

- [ ] **Step 4.4: `tests/commands/` — per-file ONLY**

```bash
uv run pytest tests/commands/test_opportunity_cmd.py -q 2>&1 | tail -4
```

Expected: 0 failed.

```bash
uv run pytest tests/commands/test_opportunity_cmd_acceptance.py -q 2>&1 | tail -4
```

Expected: 0 failed.

- [ ] **Step 4.5: Full lint**

```bash
uv run ruff check src tests
```

Expected: `All checks passed!` — **amended 2026-07-03 (drift review, item 002-drift.md):** this repo-wide lint carries 118 pre-existing violations on `autodev/todos-critical-fixes-feature` (confirmed byte-identical count/set before and after this item's diff via a detached-worktree replay); the accurate expectation for this step is "0 new violations introduced by this item's 3 touched files" (verified via Task 3 Step 3.5's file-scoped `ruff check`), not a clean `All checks passed!` across the whole tree.

**If any sweep test fails:** replay the exact failing id on the base branch (`git stash && uv run pytest <id> && git stash pop`, or check out `autodev/todos-critical-fixes-feature`'s pre-Task-3 commit) before treating it as a regression — 24 known pre-existing failures exist on main. If a genuinely stale lock surfaces (a test asserting `intact` on a data-only active fixture that the survey missed), updating it is expected per AC12 — name it in the commit message and the PR body.

---

### Task 5: Bookkeeping — CHANGELOG + TODOS.md (AC13)

**Files:**
- Modify: `CHANGELOG.md` (insert new `### Fixed` section directly under `## [Unreleased]`)
- Modify: `TODOS.md` line 51 (the dual-leg entry: `- [ ]` → `- [x]` + resolution note)

- [ ] **Step 5.1: CHANGELOG entry**

In `CHANGELOG.md`, find:

```markdown
## [Unreleased]

### Fixed — macro narrative: non-str `attribution_strength` consumes the schema-retry budget instead of degrading the whole block (2026-07-03)
```

Replace with:

```markdown
## [Unreleased]

### Fixed — ActiveFundSnapshot thesis gate: dual-leg (data + information) check extended to the active-fund branch (2026-07-03)

- **`derive_thesis_from_evidence` (`src/irc/opportunity/thesis_evidence.py`) no longer
  returns `thesis_state="intact"` for an `ActiveFundSnapshot` on ANY non-empty
  flattened constituent evidence.** `intact` now requires ≥1 `citation_kind="data"`
  AND ≥1 `citation_kind="information"` entry across the presence-only union of the
  flattened constituent evidence ∪ `snapshot.fund_level_evidence` — the same dual-leg
  heuristic the `FundLevelSnapshot` branch already applied. A single-leg union yields
  `evidence_insufficient` with direction-specific reasons（缺少数据腿 / 缺少信息腿）.
  The empty-flattened guard runs FIRST (load-bearing, ADR 0003 §8 property 3):
  rule-2.5-publishable all-pure-failure funds stay `evidence_insufficient` even with
  dual-leg fund-level evidence, so no Policy-B-publishable row changes `thesis_state`
  and the evidence/gaps/analyses return slots are byte-identical (H3 / SAME-3
  unaffected; the union is never merged into the returned evidence tuple). Fixes the
  `irc eval-funds` / `irc narrative --analyze` false confidence where filing-only
  (data-only) evidence + cheap valuation + cold heat composed to `core_dca`.
  New CONTEXT.md term "Dual-leg thesis heuristic"; ADR 0003 §8 addendum. No new
  `ThesisState` literal, no new gap code, no VERSION bump.

### Fixed — macro narrative: non-str `attribution_strength` consumes the schema-retry budget instead of degrading the whole block (2026-07-03)
```

- [ ] **Step 5.2: TODOS.md resolution annotation**

In `TODOS.md` (line 51), find:

```markdown
- [ ] **`ActiveFundSnapshot` thesis path lacks the dual-leg coverage check** — `derive_thesis_from_evidence` (`opportunity/states.py`) sets `thesis_state="intact"` for an `ActiveFundSnapshot` whenever flattened constituent evidence is non-empty, *without* requiring both a `data` leg and an `information` leg (the dual-leg gate exists only on the `FundLevelSnapshot` branch). A snapshot with data-only (e.g. filing-only) evidence can therefore reach `intact` → and, with cheap valuation + cold heat + acceptable quality, `core_dca`. Pre-existing (not introduced by eval-funds), but `irc eval-funds` surfaces `core_dca` prominently, so a data-only-evidence false-confidence is now more visible. Consider extending the dual-leg check to the `ActiveFundSnapshot` branch. (eval-funds ship adversarial review 2026-06-01)
```

Replace with (same line, `[x]` + appended note — matches the existing resolved-entry style at lines 15/25/27):

```markdown
- [x] **`ActiveFundSnapshot` thesis path lacks the dual-leg coverage check** — `derive_thesis_from_evidence` (`opportunity/states.py`) sets `thesis_state="intact"` for an `ActiveFundSnapshot` whenever flattened constituent evidence is non-empty, *without* requiring both a `data` leg and an `information` leg (the dual-leg gate exists only on the `FundLevelSnapshot` branch). A snapshot with data-only (e.g. filing-only) evidence can therefore reach `intact` → and, with cheap valuation + cold heat + acceptable quality, `core_dca`. Pre-existing (not introduced by eval-funds), but `irc eval-funds` surfaces `core_dca` prominently, so a data-only-evidence false-confidence is now more visible. Consider extending the dual-leg check to the `ActiveFundSnapshot` branch. (eval-funds ship adversarial review 2026-06-01) **Resolved 2026-07-03:** dual-leg heuristic extended to the `ActiveFundSnapshot` branch (the function lives in `opportunity/thesis_evidence.py`, not `states.py`) — `intact` requires ≥1 data + ≥1 information leg across the presence-only union flattened ∪ `fund_level_evidence`; the empty-flattened guard runs first so rule-2.5 all-pure-failure rows stay `evidence_insufficient` and no Policy-B-publishable row flips (ADR 0003 §8; CONTEXT.md "Dual-leg thesis heuristic"). Single-leg → `evidence_insufficient` with direction-specific reasons（缺少数据腿/缺少信息腿）. Tests `test_active_fund_data_only_evidence_is_insufficient` / `_info_only_evidence_is_insufficient` / `_constituent_dual_leg_stays_intact` / `_fund_level_info_leg_satisfies_gate` / `_fund_level_data_leg_satisfies_gate` / `_empty_evidence_stays_insufficient_plain` / `_empty_flattened_with_dual_leg_fund_level_stays_insufficient` (tests/opportunity/test_thesis_evidence.py) + `test_evaluate_fund_data_only_evidence_is_small_watch_not_core_dca` (tests/opportunity/test_fund_eval.py).
```

- [ ] **Step 5.3: Verify no VERSION change + commit**

```bash
git diff --stat            # must show ONLY CHANGELOG.md and TODOS.md
git diff --name-only | grep -c VERSION && echo "FAIL: VERSION touched" || true
git add CHANGELOG.md TODOS.md
git commit -m "docs(002): CHANGELOG entry + TODOS resolution for the dual-leg thesis gate"
```

Expected: `git diff --stat` lists exactly `CHANGELOG.md` and `TODOS.md`; the grep pipeline prints nothing before `true` (VERSION untouched); commit succeeds.

---

## AC → task map (self-review)

| AC | Where satisfied |
|---|---|
| AC1 data-only → insufficient | Task 1 `test_active_fund_data_only_evidence_is_insufficient` (RED→GREEN) |
| AC2 info-only → insufficient | Task 1 `test_active_fund_info_only_evidence_is_insufficient` (RED→GREEN) |
| AC3 dual-leg → intact, literal locked | Task 1 `test_active_fund_constituent_dual_leg_stays_intact` |
| AC4 fund-level leg satisfies gate (both directions) + no merge | Task 1 `test_active_fund_fund_level_{info,data}_leg_satisfies_gate` |
| AC5 empty path, fixtures (a)+(b) | Task 1 `test_active_fund_empty_evidence_stays_insufficient_plain` + `..._empty_flattened_with_dual_leg_fund_level_stays_insufficient` |
| AC6 missing-leg literals | Exact strings in Task 3 helper; asserted in AC1/AC2 tests |
| AC7 gaps slot unchanged | `gaps == ()` asserts in all Task 1 tests + Task 3.4 broker-thin file |
| AC8 evidence/analyses slots unchanged | `evidence ==` asserts in Task 1 tests + unmodified flatten-ordering test (Task 1.2) |
| AC9 eval-funds surface | Task 2 test (RED→GREEN) + existing core_dca test unmodified |
| AC10 publishable invariance | AC3/AC4/AC5(b) fixtures + Task 4.3 lockdown suite unmodified |
| AC11 other branches untouched | Task 3.2 edits only the active branch's state block; Task 3.4 + Task 4.1 |
| AC12 caller sweep + ruff | Task 4 (per-file for tests/commands/) |
| AC13 bookkeeping | Task 5 |

Placeholder scan: no TBD/TODO/"similar to" — every step carries verbatim code/commands. Type consistency: `_active_dual_leg_state` name and 3-arg signature identical in Task 3.1 (definition) and 3.2 (call site); test helper names (`_fund_level_leg`, `_dual_leg_analysis`, `_dual_leg_snapshot`, `_derive_active`) used only within Task 1's appended block and do not collide with existing module names (`_make_evidence`, `_r`, `_theme_report`, `_analysis` in other files).
