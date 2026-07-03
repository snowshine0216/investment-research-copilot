# Item 004 — Fund-level evidence repair probe: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the cached-serve path, repair a foreign-heavy `ActiveFundSnapshot` whose `fund_level_evidence` is missing a data leg OR an information leg (rule 2.5's exact gap condition) with a 4-call fund-level refetch + **leg-wise monotone merge**, so the fund heals in one run instead of re-emitting `foreign_heavy_fund_level_evidence_missing` for the whole `IRC_CACHE_FRESHNESS_DAYS` window.

**Architecture:** One public pure predicate (`foreign_heavy_fund_level_gap`) co-located with rule 2.5 in `policy_b.py` (single source of truth — classifier, runtime, and rule 2.5 share it). One new module `src/irc/fundamentals/fund_level_repair.py` holding the pure leg-wise merge plus the single fail-safe I/O edge (`refetch_fund_level_evidence`). One ~14-line command-edge helper (`_maybe_fund_level_evidence_repair`) wired into `_build_rows`' cached-serve arm ONLY (post-probe snapshot). The preflight budget learns a fourth class (`FetchPlan.active_fund_fund_level_repair`, ×4) via a 3→4-tuple classifier signature change with exactly 4 grep-verified call/patch sites.

**Tech Stack:** Python 3.12, uv, pytest, ruff (line-length 100, target py312). No new dependencies, no new AkShare endpoints.

## Global Constraints

- **TDD mandatory** — failing test first for every AC; red-state expectations spelled out per step.
- **Purity / effects at edges** — `foreign_heavy_fund_level_gap` and `merge_fund_level_evidence` are pure (no I/O, no mutation, `dataclasses.replace` new instances); ALL fetch + cache-write effects live in `refetch_fund_level_evidence` and `_maybe_fund_level_evidence_repair`.
- **Size budget** — `fund_level_repair.py` < 200 lines; every new function < 20 lines body; `opportunity_cmd.py` (1573 lines) grows only by the helper + classifier/FetchPlan deltas mandated by AC5/AC6; `snapshot.py` gets a docstring fix only; `policy_b.py` grows ~15 lines.
- **No VERSION bump** — CHANGELOG `[Unreleased]` only (versioning convention).
- **Citation contract untouched** — `ThesisEvidence` shape, 16-hex `citation_id`, `citation_kind` literals unchanged (ADR 0001). Repaired evidence has the exact shape `_fetch_active_fund_level_evidence` already produces.
- **No Policy B rule change** — `evaluate_policy_b`, the six-rule precedence, rule 2.5's gap/decision strings are byte-identical. The predicate is additive and read-only.
- **No `_maybe_freshness_probe` signature or semantics change** — its 4 existing unit tests (`tests/commands/test_opportunity_cmd.py:565–652`) must pass unmodified.
- **No `ActiveFundSnapshot` schema change** — no backoff marker field (resolved Q5); the repair never touches `cache_probed_at`.
- **`tests/commands/` hangs as a whole dir** — run per-file only.
- **Known-failure diff-scoping** — full pytest is NOT green on main (24 pre-existing failures); replay any sweep failure on the base branch before assuming a regression.
- **CONTEXT.md is ALREADY updated** by the grill (commit `ff259456`): the "Fund-level evidence repair (repair probe)" term + the cross-ref in "Foreign-heavy fund (rule 2.5 short-circuit)". Do NOT re-edit unless the as-built behavior diverges (Task 6 verifies).
- **Branch:** the orchestrator creates the item working branch. No branch-creation or PR steps in this plan; commit per task.

## Verified current state (all line numbers re-checked 2026-07-03 against `autodev/todos-critical-fixes-feature`)

- `src/irc/commands/opportunity_cmd.py:90–116` — `FetchPlan` frozen dataclass; `total_calls()` at :107–116 with `per_active = 1 + top_n*3 + 4` and `per_fund_level = 4`. `FetchBudgetExceeded` message at :119–134.
- `opportunity_cmd.py:250–263` — `_constituent_has_data_leg` / `_active_snapshot_has_required_data_leg_gap`. `_maybe_freshness_probe` at :266–299 (three `(snap, False)` return paths: fresh early-return :278–279, cache-write-degrade :298, probe-success :299). `_load_latest_active_fund_cached` at :302–314.
- `opportunity_cmd.py:595–641` — `_classify_active_fund_scores` returning a 3-tuple. Sole production caller at :776–781; `FetchPlan` construction at :788–797.
- `opportunity_cmd.py:910–912` — the cached-serve arm, the ONLY insertion point (`else:` / `snap_obj = probed` / `_write_state_complete(...)`); `snap_obj = probed` appears exactly once in the file.
- `src/irc/opportunity/policy_b.py:283–315` — rule 2.5; gap fires on `not (has_data and has_info)`. `_rank_by_weight` :95, `_compute_foreign_listed_share` :105, `FOREIGN_HEAVY_THRESHOLD` :23. `ActiveFundSnapshot` already imported at :17.
- `src/irc/fundamentals/snapshot.py:477–524` — `_fetch_active_fund_level_evidence`; exactly 4 `_ak_call`s (1 × `fund_open_fund_info_em` + 3 × `_FUND_ANN_TOPIC_FNS`, verified in `akshare_fundamentals.py:577, :619–623, :682–686`). Producer invariant at :505–506 (`fund_nav_unavailable:{id}` appended iff NAV leg absent) and :522–523 (`fund_announcements_unavailable:{id}` iff announcements empty). STALE docstring claim "Per-fund call delta = 2 AkShare calls" at :486–487.
- `src/irc/fundamentals/snapshot_cache.py:224–233` — `write_active_fund_cache` (disclosure-quarter keying + `.tmp.{pid} → replace`; inherited by the repair, R4).
- **4-tuple call/patch sites (grill R1, re-verified by grep this session — exhaustive):** `src/irc/commands/opportunity_cmd.py:776` (production unpack); `tests/commands/test_opportunity_cmd.py:675` and `:719` (3-tuple unpacks); `:930` (`return_value=(0, 0, 0)` stub). `tests/opportunity/`, `tests/narrative/`, `evals/`, `scripts/`, `fund_eval_cmd.py`, `narrative_autobuild.py`: ZERO classifier references. Positional `FetchPlan(5, 0, 0, 0, 10)` at `tests/commands/test_opportunity_cmd.py:480` and `tests/commands/test_opportunity_cmd_acceptance.py:100` bind only the first 5 params — unaffected by the new defaulted field.
- `docs/adr/0003-failure-mode-policy-b.md:161–162` — §7 "Fetch budget impact" still carries the stale "**2 additional AkShare calls** … adds ~100 calls" claim (grill commit `ff259456` touched only CONTEXT.md + the spec) → this plan MUST fix it (AC11/R7). §7 ends at :167 (Alternative C line); §8 heading at :169.
- `TODOS.md:21` — the `- [ ] **Mixed-fund stale-cache with empty \`fund_level_evidence\` not force-retried**` line.
- Existing test factories reused: `tests/opportunity/test_policy_b.py` — `_ca` (:63), `_evidence_data_instrument` (:552), `_evidence_info_instrument` (:569), `_snapshot_with_fund_level_evidence` (:586); all module-scope, usable by appended tests. `tests/integration/_publishable_set_helper.py` — `_seed_publishable_set_repo`, `_install_ak_call_dispatch` (Counter keyed `(fn_name, str(symbol))`; symbol read from `args[0]` or `kwargs["symbol"]`), `_today_cn`. `tests/integration/test_publishable_set_lockdown.py:596–617` — `_prewrite_active_fund_cache` writes `constituent_analyses=()` (R6: predicate False via share 0.0 for AC15/AC16).
- `fetch_fund_nav_report` (`akshare_fundamentals.py:566–616`) parses columns `净值日期` + `单位净值` and calls `_ak_call("fund_open_fund_info_em", symbol=..., indicator=...)` — the dispatch helper resolves `symbol` from kwargs, so integration tests key on `("fund_open_fund_info_em", "005827")`.

## Design decisions locked by this plan

1. **Binding shapes from the grill (R10):** AC2's leg-wise monotone merge and AC4's post-probe input (`probed`, never the pre-probe `cached`) are the authoritative semantics; the spec's struck-through full-replacement text is dead.
2. **`merge_fund_level_evidence` keeps the `failures: list[str]` parameter but does not read it** — signature parity with the producer (AC2 pins the signature) while leg-failure strings are RECOMPUTED from leg absence in the MERGED evidence (grill R3; producer invariant). The docstring says so explicitly.
3. **Failure-reason ordering rule:** strip both leg-failure strings, keep unrelated reasons in original relative order, then re-append `fund_nav_unavailable:{id}` (iff merged data leg absent) then `fund_announcements_unavailable:{id}` (iff merged info leg absent) — NAV-first mirrors the producer order.
4. **Classifier restructured from `elif`-chain to `continue`-guards** so a fund can count toward BOTH `stale_probe_only` AND `fund_level_repair` (AC5: date-stale + gapped ⇒ `(0, 0, 1, 1)`), while miss / data-leg-gap short-circuit (`stale_full` wins over repair — no double count).
5. **`total_calls()` reuses the existing `per_fund_level = 4` local** for the repair term (AC6: "the constant mirrors `per_fund_level = 4`").
6. **Red/green honesty:** RED pre-fix = Task 1's 6 predicate tests, Task 2's 9 merge/wrapper tests, Task 3's 6 classifier/FetchPlan tests, Task 4's 5 helper unit tests + the AC7 integration heal test (on the pre-fix tree it fails at "zero fund-level calls fired" and "gap code present in rejections.json"). GREEN-locks (pass before AND after, run unmodified) = AC15/AC16/AC17 lockdowns, the 4 `_maybe_freshness_probe` unit tests, all existing `FetchPlan` tests (:458–486), and the new AC8 CN-heavy negative integration test (green even pre-fix — it locks the foreign-heavy-only scope against future widening). MECHANICAL edits (green→green in new shape, same commit as the signature change): `tests/commands/test_opportunity_cmd.py:675`, `:719`, `:930`.

---

### Task 1: `foreign_heavy_fund_level_gap` predicate in `policy_b.py`

**Files:**
- Modify: `src/irc/opportunity/policy_b.py` (insert after `_compute_foreign_listed_share`, i.e. after line 125)
- Test: `tests/opportunity/test_policy_b.py` (append at end of file; currently 971 lines)

**Interfaces:**
- Consumes: `_rank_by_weight`, `_compute_foreign_listed_share`, `FOREIGN_HEAVY_THRESHOLD`, `ActiveFundSnapshot` (all already in the module).
- Produces: `foreign_heavy_fund_level_gap(snapshot: ActiveFundSnapshot) -> bool` — imported by Task 3 (classifier) and Task 4 (command helper).

- [ ] **Step 1.1: Append the failing tests**

Append at the very end of `tests/opportunity/test_policy_b.py`:

```python
# ── Item 004 (todos-critical-fixes 2026-07-03): foreign_heavy_fund_level_gap ──
# Spec: docs/2026-07-03-todos-critical-fixes/items/004-spec.md AC1.
# The predicate mirrors rule 2.5's gap condition exactly (foreign-heavy AND
# missing data leg OR missing information leg) — the shared trigger for the
# fund-level evidence repair probe (CONTEXT.md term).


def _hk_heavy_analyses():
    """10 HK-listed constituents → foreign share 1.0 (≥ threshold)."""
    return tuple(_ca(f"0070{i}.HK", 1.0) for i in range(10))


def _cn_heavy_analyses():
    """10 SH-listed constituents → foreign share 0.0 (< threshold)."""
    return tuple(_ca(f"60000{i}", 1.0) for i in range(10))


def test_foreign_heavy_fund_level_gap_true_on_empty_evidence() -> None:
    from irc.opportunity.policy_b import foreign_heavy_fund_level_gap
    snap = _snapshot_with_fund_level_evidence(
        analyses=_hk_heavy_analyses(), fund_level_evidence=(),
    )
    assert foreign_heavy_fund_level_gap(snap) is True


def test_foreign_heavy_fund_level_gap_true_on_info_only() -> None:
    from irc.opportunity.policy_b import foreign_heavy_fund_level_gap
    snap = _snapshot_with_fund_level_evidence(
        analyses=_hk_heavy_analyses(),
        fund_level_evidence=(_evidence_info_instrument(),),
    )
    assert foreign_heavy_fund_level_gap(snap) is True


def test_foreign_heavy_fund_level_gap_true_on_data_only() -> None:
    """The TODO-correction shape: a NAV-only outage leaves a non-empty
    info-only tuple, an announcements-only outage leaves data-only — the
    TODO's literal `== ()` trigger would repair neither single-leg shape."""
    from irc.opportunity.policy_b import foreign_heavy_fund_level_gap
    snap = _snapshot_with_fund_level_evidence(
        analyses=_hk_heavy_analyses(),
        fund_level_evidence=(_evidence_data_instrument(),),
    )
    assert foreign_heavy_fund_level_gap(snap) is True


def test_foreign_heavy_fund_level_gap_false_when_both_legs_present() -> None:
    from irc.opportunity.policy_b import foreign_heavy_fund_level_gap
    snap = _snapshot_with_fund_level_evidence(
        analyses=_hk_heavy_analyses(),
        fund_level_evidence=(
            _evidence_data_instrument(), _evidence_info_instrument(),
        ),
    )
    assert foreign_heavy_fund_level_gap(snap) is False


def test_foreign_heavy_fund_level_gap_false_for_cn_heavy_fund() -> None:
    from irc.opportunity.policy_b import foreign_heavy_fund_level_gap
    snap = _snapshot_with_fund_level_evidence(
        analyses=_cn_heavy_analyses(), fund_level_evidence=(),
    )
    assert foreign_heavy_fund_level_gap(snap) is False


def test_foreign_heavy_fund_level_gap_false_on_empty_constituents() -> None:
    """Share 0.0 on empty analyses — load-bearing for AC8's lockdown fixtures
    (`_prewrite_active_fund_cache` writes constituent_analyses=(), grill R6):
    AC15/AC16 must stay zero-extra-calls / probe-only."""
    from irc.opportunity.policy_b import foreign_heavy_fund_level_gap
    snap = _snapshot_with_fund_level_evidence(
        analyses=(), fund_level_evidence=(),
    )
    assert foreign_heavy_fund_level_gap(snap) is False
```

- [ ] **Step 1.2: Run the new tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_policy_b.py -k foreign_heavy_fund_level_gap -q`
Expected: 6 failed — `ImportError: cannot import name 'foreign_heavy_fund_level_gap' from 'irc.opportunity.policy_b'`

- [ ] **Step 1.3: Implement the predicate**

In `src/irc/opportunity/policy_b.py`, insert AFTER the closing `return foreign / total` of `_compute_foreign_listed_share` (line 125) and BEFORE `def _material_set_with_ties(`:

```python
def foreign_heavy_fund_level_gap(snapshot: ActiveFundSnapshot) -> bool:
    """True iff rule 2.5 would emit `foreign_heavy_fund_level_evidence_missing`.

    Trigger predicate for the *fund-level evidence repair* probe
    (todos-critical-fixes item 004; CONTEXT.md "Fund-level evidence repair"):
    foreign-listed weight share ≥ `FOREIGN_HEAVY_THRESHOLD` AND
    `snapshot.fund_level_evidence` missing a `citation_kind=="data"` entry OR
    a `citation_kind=="information"` entry — exactly rule 2.5's gap condition
    below. Co-located with rule 2.5 so the two conditions cannot drift
    (single source of truth). Pure, read-only. Empty `constituent_analyses`
    → share 0.0 → False (mirrors `_compute_foreign_listed_share`'s guard).
    """
    ranked = _rank_by_weight(snapshot.constituent_analyses)
    if _compute_foreign_listed_share(ranked) < FOREIGN_HEAVY_THRESHOLD:
        return False
    has_data = any(e.citation_kind == "data" for e in snapshot.fund_level_evidence)
    has_info = any(
        e.citation_kind == "information" for e in snapshot.fund_level_evidence
    )
    return not (has_data and has_info)
```

- [ ] **Step 1.4: Run the tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_policy_b.py -q`
Expected: all passed (existing suite + 6 new), 0 failed.

- [ ] **Step 1.5: Commit**

```bash
git add src/irc/opportunity/policy_b.py tests/opportunity/test_policy_b.py
git commit -m "feat(policy_b): foreign_heavy_fund_level_gap predicate — rule-2.5 gap mirror (004 AC1)"
```

---

### Task 2: `src/irc/fundamentals/fund_level_repair.py` — pure leg-wise merge + fail-safe refetch

**Files:**
- Create: `src/irc/fundamentals/fund_level_repair.py`
- Test (create): `tests/fundamentals/test_fund_level_repair.py`

**Interfaces:**
- Consumes: `_fetch_active_fund_level_evidence(fund_id) -> tuple[tuple[ThesisEvidence, ...], list[str]]` (private import from sibling `irc.fundamentals.snapshot`; precedent: `opportunity_cmd.py` imports `_FUND_LEVEL_KINDS`).
- Produces:
  - `merge_fund_level_evidence(snap: ActiveFundSnapshot, evidence: tuple[ThesisEvidence, ...], failures: list[str]) -> ActiveFundSnapshot` (pure)
  - `refetch_fund_level_evidence(snap: ActiveFundSnapshot) -> ActiveFundSnapshot` (I/O edge; never raises) — imported by Task 4.

- [ ] **Step 2.1: Create the failing mirror test file**

Create `tests/fundamentals/test_fund_level_repair.py` with exactly:

```python
"""Mirror tests for `src/irc/fundamentals/fund_level_repair.py` (item 004).

Locks the leg-wise monotone merge (grill R3) — the four named AC2 cases —
plus the producer invariant (leg-failure string present ⟺ leg absent in
MERGED evidence), field/immutability guarantees, and the fail-safe refetch
wrapper (AC3).
"""
from __future__ import annotations

import copy


def _fund_evidence(kind: str, *, fund_id: str = "006809", summary: str = ""):
    """Fund-level ThesisEvidence in the exact producer shapes
    (`_fetch_active_fund_level_evidence`, snapshot.py:489-524)."""
    from irc.fundamentals.types import ThesisEvidence
    if kind == "data":
        return ThesisEvidence(
            type="snapshot", source=fund_id, url="", date="2026-07-01",
            summary=summary or "NAV=1.5000 @ 2026-07-01",
            scope="instrument", citation_kind="data",
            owner_instrument_id=fund_id, parent_fund_id=None,
            constituent_key=None,
        )
    return ThesisEvidence(
        type="news", source="fund_announcement_report_em", url="",
        date="2026-07-01", summary=summary or "[REP-001] 季度报告",
        scope="instrument", citation_kind="information",
        owner_instrument_id=fund_id, parent_fund_id=None,
        constituent_key=None,
    )


def _snap(fund_level_evidence=(), fund_level_failure_reasons=()):
    from irc.fundamentals.types import ActiveFundSnapshot
    return ActiveFundSnapshot(
        fund_id="006809",
        source_report_date="2026-03-31",
        source_report_quarter="2026Q1",
        cache_probed_at="2026-07-01",
        constituent_analyses=(),
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=fund_level_failure_reasons,
        fund_level_evidence=fund_level_evidence,
    )


# ── merge_fund_level_evidence: the four named AC2 cases ──────────────────────

def test_merge_cached_info_only_plus_fresh_data_only_heals_both_legs() -> None:
    """AC2 case 1 — the heal-under-throttle case (the TODO's own motivating
    shape): NAV recovered, announcements still throttled the other way round.
    Full replacement would SWAP legs and oscillate; the leg-wise merge heals
    to BOTH legs in one run with zero leg-failure strings."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    cached_info = _fund_evidence("information", summary="[OLD-1] 旧公告")
    snap = _snap(
        fund_level_evidence=(cached_info,),
        fund_level_failure_reasons=("fund_nav_unavailable:006809",),
    )
    fresh_data = _fund_evidence("data")
    merged = merge_fund_level_evidence(
        snap, (fresh_data,), ["fund_announcements_unavailable:006809"],
    )
    assert merged.fund_level_evidence == (fresh_data, cached_info)
    assert merged.fund_level_failure_reasons == ()


def test_merge_cached_data_only_plus_fresh_info_only_heals_both_legs() -> None:
    """AC2 case 2 — mirror direction; merged tuple stays data-leg-first."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    cached_data = _fund_evidence("data", summary="NAV=1.4000 @ 2026-06-01")
    snap = _snap(
        fund_level_evidence=(cached_data,),
        fund_level_failure_reasons=("fund_announcements_unavailable:006809",),
    )
    fresh_info = _fund_evidence("information")
    merged = merge_fund_level_evidence(
        snap, (fresh_info,), ["fund_nav_unavailable:006809"],
    )
    assert merged.fund_level_evidence == (cached_data, fresh_info)
    assert merged.fund_level_failure_reasons == ()


def test_merge_cached_empty_plus_fresh_both_takes_fresh_verbatim() -> None:
    """AC2 case 3."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    snap = _snap(
        fund_level_evidence=(),
        fund_level_failure_reasons=(
            "fund_nav_unavailable:006809",
            "fund_announcements_unavailable:006809",
        ),
    )
    fresh = (_fund_evidence("data"), _fund_evidence("information"))
    merged = merge_fund_level_evidence(snap, fresh, [])
    assert merged.fund_level_evidence == fresh
    assert merged.fund_level_failure_reasons == ()


def test_merge_fresh_empty_keeps_cached_evidence_byte_identical() -> None:
    """AC2 case 4 — both fetch legs failed → merged evidence byte-identical
    to cached (so the AC4 call site writes nothing); leg-failure strings
    re-pinned to merged-leg absence (data still missing → nav failure only)."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    cached_info = _fund_evidence("information")
    snap = _snap(
        fund_level_evidence=(cached_info,),
        fund_level_failure_reasons=("fund_nav_unavailable:006809",),
    )
    merged = merge_fund_level_evidence(
        snap, (),
        ["fund_nav_unavailable:006809", "fund_announcements_unavailable:006809"],
    )
    assert merged.fund_level_evidence == snap.fund_level_evidence
    assert merged.fund_level_failure_reasons == ("fund_nav_unavailable:006809",)


# ── merge: monotonicity, failure-reason invariant, immutability ──────────────

def test_merge_fresh_leg_wins_over_cached_leg_when_produced() -> None:
    """Fresh entries replace the cached leg they cover; the other cached leg
    is retained untouched (leg presence monotone non-decreasing)."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    cached_data = _fund_evidence("data", summary="NAV=1.4000 @ 2026-06-01")
    cached_info = _fund_evidence("information", summary="[OLD-1] 旧公告")
    snap = _snap(fund_level_evidence=(cached_data, cached_info))
    fresh_data = _fund_evidence("data", summary="NAV=1.5000 @ 2026-07-01")
    merged = merge_fund_level_evidence(snap, (fresh_data,), [])
    assert merged.fund_level_evidence == (fresh_data, cached_info)
    assert merged.fund_level_failure_reasons == ()


def test_merge_preserves_unrelated_failure_reasons_in_order() -> None:
    """Both leg-failure strings stripped; unrelated reasons keep their
    original relative order; missing-leg failures re-appended NAV-first
    (the producer order, snapshot.py:505-506/:522-523)."""
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    snap = _snap(
        fund_level_evidence=(),
        fund_level_failure_reasons=(
            "holdings_quarter_parse_failed:006809",
            "fund_nav_unavailable:006809",
            "cache_write_failed:006809:OSError",
            "fund_announcements_unavailable:006809",
        ),
    )
    fresh = (_fund_evidence("data"),)
    merged = merge_fund_level_evidence(
        snap, fresh, ["fund_announcements_unavailable:006809"],
    )
    assert merged.fund_level_evidence == fresh
    assert merged.fund_level_failure_reasons == (
        "holdings_quarter_parse_failed:006809",
        "cache_write_failed:006809:OSError",
        "fund_announcements_unavailable:006809",
    )


def test_merge_returns_new_instance_all_other_fields_identical() -> None:
    """New frozen instance; input unmutated; every field other than the two
    merged ones — INCLUDING cache_probed_at — byte-identical (AC2)."""
    from dataclasses import replace
    from irc.fundamentals.fund_level_repair import merge_fund_level_evidence
    cached_info = _fund_evidence("information")
    snap = _snap(
        fund_level_evidence=(cached_info,),
        fund_level_failure_reasons=("fund_nav_unavailable:006809",),
    )
    before = copy.deepcopy(snap)
    merged = merge_fund_level_evidence(snap, (_fund_evidence("data"),), [])
    assert merged is not snap
    assert snap == before, "input snapshot must not be mutated"
    assert merged.cache_probed_at == snap.cache_probed_at
    assert replace(
        merged,
        fund_level_evidence=snap.fund_level_evidence,
        fund_level_failure_reasons=snap.fund_level_failure_reasons,
    ) == snap


# ── refetch_fund_level_evidence: fail-safe I/O edge (AC3) ────────────────────

def test_refetch_raising_fetch_returns_snapshot_unchanged(monkeypatch) -> None:
    """AC3 — ANY exception from the fetch → original snapshot returned;
    no exception escapes (a repair attempt must never crash a row build
    that previously served fine from cache)."""
    from irc.fundamentals.fund_level_repair import refetch_fund_level_evidence

    def _boom(fund_id):
        raise ConnectionError("akshare 502")

    monkeypatch.setattr(
        "irc.fundamentals.fund_level_repair._fetch_active_fund_level_evidence",
        _boom,
    )
    snap = _snap(
        fund_level_evidence=(),
        fund_level_failure_reasons=(
            "fund_nav_unavailable:006809",
            "fund_announcements_unavailable:006809",
        ),
    )
    out = refetch_fund_level_evidence(snap)
    assert out is snap


def test_refetch_success_merges_fresh_evidence(monkeypatch) -> None:
    from irc.fundamentals.fund_level_repair import refetch_fund_level_evidence
    fresh = (_fund_evidence("data"), _fund_evidence("information"))
    seen: list[str] = []
    monkeypatch.setattr(
        "irc.fundamentals.fund_level_repair._fetch_active_fund_level_evidence",
        lambda fund_id: (seen.append(fund_id) or fresh, []),
    )
    snap = _snap(
        fund_level_evidence=(),
        fund_level_failure_reasons=(
            "fund_nav_unavailable:006809",
            "fund_announcements_unavailable:006809",
        ),
    )
    out = refetch_fund_level_evidence(snap)
    assert seen == ["006809"]
    assert out.fund_level_evidence == fresh
    assert out.fund_level_failure_reasons == ()
```

- [ ] **Step 2.2: Run to verify red**

Run: `uv run pytest tests/fundamentals/test_fund_level_repair.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'irc.fundamentals.fund_level_repair'`

- [ ] **Step 2.3: Create the module**

Create `src/irc/fundamentals/fund_level_repair.py` with exactly:

```python
"""Fund-level evidence repair (repair probe) — todos-critical-fixes item 004.

The third cached-active-fund fetch class beside the full refetch (~35 calls)
and the fail-closed freshness probe (1 call): when a cached foreign-heavy
`ActiveFundSnapshot` serves with a rule-2.5 leg gap
(`foreign_heavy_fund_level_gap` in `irc.opportunity.policy_b`), ONLY the
fund-level legs are re-fetched (4 AkShare calls: 1 NAV + 3 announcement
endpoints) and leg-wise merged into the snapshot.

Pure merge (`merge_fund_level_evidence`) is separated from the single I/O
edge (`refetch_fund_level_evidence`) per repo conventions. See CONTEXT.md
"Fund-level evidence repair (repair probe)" and ADR 0003 §7.
"""
from __future__ import annotations

from dataclasses import replace

from irc.fundamentals.snapshot import _fetch_active_fund_level_evidence
from irc.fundamentals.types import ActiveFundSnapshot, ThesisEvidence


def _leg(
    evidence: tuple[ThesisEvidence, ...], kind: str,
) -> tuple[ThesisEvidence, ...]:
    """All entries of one `citation_kind`, original order preserved."""
    return tuple(e for e in evidence if e.citation_kind == kind)


def _merged_failure_reasons(
    snap: ActiveFundSnapshot, merged: tuple[ThesisEvidence, ...],
) -> tuple[str, ...]:
    """Re-pin the producer invariant: leg-failure string present ⟺ leg absent.

    Both leg-failure strings are stripped, then re-appended — NAV first, then
    announcements, the producer order of `_fetch_active_fund_level_evidence`
    (snapshot.py:505-506, :522-523) — iff the MERGED evidence lacks that leg.
    Unrelated reasons (e.g. `holdings_quarter_parse_failed:{fund_id}`) are
    preserved in their original relative order.
    """
    nav_failure = f"fund_nav_unavailable:{snap.fund_id}"
    ann_failure = f"fund_announcements_unavailable:{snap.fund_id}"
    kept = tuple(
        r for r in snap.fund_level_failure_reasons
        if r not in (nav_failure, ann_failure)
    )
    if not _leg(merged, "data"):
        kept = kept + (nav_failure,)
    if not _leg(merged, "information"):
        kept = kept + (ann_failure,)
    return kept


def merge_fund_level_evidence(
    snap: ActiveFundSnapshot,
    evidence: tuple[ThesisEvidence, ...],
    failures: list[str],
) -> ActiveFundSnapshot:
    """Leg-wise monotone merge of a fresh fund-level fetch into `snap` (pure).

    Per leg (by `citation_kind`): the fresh entries win when the refetch
    produced ≥1 entry for that leg; the cached entries are retained when it
    didn't (grill R3 — full replacement would drop a surviving cached leg
    under the 2026-06-21 throttle pattern and oscillate instead of healing).
    The merged tuple orders the data leg first, then the information leg
    (the producer order — NAV then announcements). Leg presence is monotone
    non-decreasing across a repair.

    `failures` — the fresh fetch's failure list — is accepted for signature
    parity with the producer but deliberately NOT merged: leg-failure strings
    are recomputed from leg ABSENCE in the merged evidence via
    `_merged_failure_reasons` (appending a fresh leg-failure while the merge
    retains that cached leg would break the producer invariant).
    Every other field — including `cache_probed_at` — is byte-identical:
    the repair is orthogonal to holdings-quarter freshness.
    """
    merged = (
        (_leg(evidence, "data") or _leg(snap.fund_level_evidence, "data"))
        + (_leg(evidence, "information")
           or _leg(snap.fund_level_evidence, "information"))
    )
    return replace(
        snap,
        fund_level_evidence=merged,
        fund_level_failure_reasons=_merged_failure_reasons(snap, merged),
    )


def refetch_fund_level_evidence(snap: ActiveFundSnapshot) -> ActiveFundSnapshot:
    """Fail-safe I/O edge: 4-call fund-level refetch merged via the pure merge.

    4 AkShare calls (1 NAV + 3 announcement endpoints) through the existing
    `_fetch_active_fund_level_evidence` (same-package private import;
    precedent: `opportunity_cmd.py` imports `_FUND_LEVEL_KINDS`). ANY
    exception → returns `snap` unchanged — a repair attempt must never crash
    a row build that previously served fine from cache (spec AC3;
    `fetch_fund_announcements` documents "Never raises" but this wrapper
    does not rely on that).
    """
    try:
        evidence, failures = _fetch_active_fund_level_evidence(snap.fund_id)
    except Exception:
        return snap
    return merge_fund_level_evidence(snap, evidence, failures)
```

- [ ] **Step 2.4: Run to verify green**

Run: `uv run pytest tests/fundamentals/test_fund_level_repair.py -q`
Expected: 9 passed, 0 failed.

- [ ] **Step 2.5: Commit**

```bash
git add src/irc/fundamentals/fund_level_repair.py tests/fundamentals/test_fund_level_repair.py
git commit -m "feat(fundamentals): fund_level_repair — leg-wise monotone merge + fail-safe refetch (004 AC2/AC3)"
```

---

### Task 3: `FetchPlan.active_fund_fund_level_repair` + 4-tuple classifier (all 4 call sites)

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py` (`FetchPlan` :90–116, `FetchBudgetExceeded` :119–134, policy_b import :19, `_classify_active_fund_scores` :595–641, caller :776–797)
- Modify: `tests/commands/test_opportunity_cmd.py` (append new tests; mechanical edits at :675, :719, :930)

**Interfaces:**
- Consumes: `foreign_heavy_fund_level_gap` (Task 1).
- Produces: `_classify_active_fund_scores(...) -> tuple[int, int, int, int]` = `(misses, stale_full, stale_probe_only, fund_level_repair)`; `FetchPlan.active_fund_fund_level_repair: int = 0` charged at ×4 in `total_calls()`. The shared test factory `_item004_snapshot` (defined in this task) is reused by Task 4's helper tests.

- [ ] **Step 3.1: Append the failing tests + shared factory**

Append at the very end of `tests/commands/test_opportunity_cmd.py`:

```python
# ── Item 004 (todos-critical-fixes 2026-07-03): fund-level evidence repair ────
# Spec: docs/2026-07-03-todos-critical-fixes/items/004-spec.md AC4-AC6, AC9.


def _item004_snapshot(
    *,
    symbol: str = "00700.HK",
    cache_probed_at: str = "2026-07-01",
    source_report_quarter: str = "2026Q1",
    constituent_has_data_leg: bool = True,
    fund_level_evidence: tuple = (),
    fund_level_failure_reasons: tuple = (
        "fund_nav_unavailable:006809",
        "fund_announcements_unavailable:006809",
    ),
):
    """Foreign-heavy (default 00700.HK → HK) or CN-heavy (symbol='600519')
    ActiveFundSnapshot for the item-004 repair tests. The single constituent
    carries a data leg by default so
    `_active_snapshot_has_required_data_leg_gap` stays False."""
    from irc.fundamentals.types import (
        ActiveFundSnapshot, ConstituentAnalysis, ThesisEvidence,
    )
    data_leg = ThesisEvidence(
        type="filing", source=symbol, url="", date="2026-04-15",
        summary=f"{symbol} 26Q1 财报", scope="constituent",
        citation_kind="data", owner_instrument_id="006809",
        parent_fund_id="006809", constituent_key=symbol,
    )
    evidence = (data_leg,) if constituent_has_data_leg else ()
    failure_reasons = (
        () if constituent_has_data_leg else (f"filing_empty:{symbol}",)
    )
    return ActiveFundSnapshot(
        fund_id="006809", source_report_date="2026-03-31",
        source_report_quarter=source_report_quarter,
        cache_probed_at=cache_probed_at,
        constituent_analyses=(
            ConstituentAnalysis(
                symbol=symbol, name_cn=symbol, weight_pct=8.0,
                evidence=evidence, failure_reasons=failure_reasons,
                one_line_view="核心持仓",
            ),
        ),
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=fund_level_failure_reasons,
        fund_level_evidence=fund_level_evidence,
    )


def test_classify_fresh_foreign_heavy_gapped_cache_counts_repair_only(tmp_path) -> None:
    """Item 004 AC5 — fresh-by-date, data-leg-complete, foreign-heavy, fund-level
    leg gap → the new fund_level_repair bucket ONLY: (0, 0, 0, 1)."""
    from datetime import date
    from irc.commands.opportunity_cmd import _classify_active_fund_scores
    from irc.fundamentals.snapshot_cache import write_active_fund_cache

    write_active_fund_cache(_item004_snapshot(cache_probed_at="2026-07-01"), tmp_path)
    counts = _classify_active_fund_scores(
        [{"instrument_id": "006809", "asset_class": "cn_equity_fund"}],
        tmp_path,
        today=date(2026, 7, 3),
        threshold_days=7,
        rebuild_fundamentals=False,
    )
    assert counts == (0, 0, 0, 1)


def test_classify_data_leg_gap_wins_over_fund_level_repair(tmp_path) -> None:
    """Item 004 AC5 — a data-leg gap forces the full re-fetch (which includes
    the fund-level legs); the fund is NOT double-counted as a repair:
    (0, 1, 0, 0)."""
    from datetime import date
    from irc.commands.opportunity_cmd import _classify_active_fund_scores
    from irc.fundamentals.snapshot_cache import write_active_fund_cache

    write_active_fund_cache(
        _item004_snapshot(cache_probed_at="2026-07-01", constituent_has_data_leg=False),
        tmp_path,
    )
    counts = _classify_active_fund_scores(
        [{"instrument_id": "006809", "asset_class": "cn_equity_fund"}],
        tmp_path,
        today=date(2026, 7, 3),
        threshold_days=7,
        rebuild_fundamentals=False,
    )
    assert counts == (0, 1, 0, 0)


def test_classify_date_stale_and_gapped_counts_probe_and_repair(tmp_path) -> None:
    """Item 004 AC5 — date-stale + gapped counts toward BOTH buckets (the
    runtime fires probe 1 call + repair 4 calls = 5): (0, 0, 1, 1)."""
    from datetime import date
    from irc.commands.opportunity_cmd import _classify_active_fund_scores
    from irc.fundamentals.snapshot_cache import write_active_fund_cache

    write_active_fund_cache(_item004_snapshot(cache_probed_at="2026-06-01"), tmp_path)
    counts = _classify_active_fund_scores(
        [{"instrument_id": "006809", "asset_class": "cn_equity_fund"}],
        tmp_path,
        today=date(2026, 7, 3),
        threshold_days=7,
        rebuild_fundamentals=False,
    )
    assert counts == (0, 0, 1, 1)


def test_fetch_plan_fund_level_repair_costs_four_not_thirty_five() -> None:
    """Item 004 AC6 — a repair-only fund costs exactly 4 (1 NAV + 3
    announcement endpoints), NEVER the 35-call per_active term (the ~35×
    over-estimate trap class)."""
    from irc.commands.opportunity_cmd import FetchPlan
    plan = FetchPlan(
        active_fund_misses=0, active_fund_stale=0,
        passive_misses=0, passive_stale=0, top_n=10,
        active_fund_fund_level_repair=1,
    )
    assert plan.total_calls() == 4


def test_fetch_plan_probe_plus_repair_costs_five() -> None:
    """Item 004 AC6 — date-stale + gapped fund: probe 1 + repair 4 = 5."""
    from irc.commands.opportunity_cmd import FetchPlan
    plan = FetchPlan(
        active_fund_misses=0, active_fund_stale=0,
        passive_misses=0, passive_stale=0, top_n=10,
        active_fund_stale_probe_only=1,
        active_fund_fund_level_repair=1,
    )
    assert plan.total_calls() == 5


def test_fetch_budget_exceeded_message_includes_fund_level_repair() -> None:
    """Item 004 AC6 — the budget-exceeded breakdown names the new class."""
    from irc.commands.opportunity_cmd import FetchBudgetExceeded, FetchPlan
    plan = FetchPlan(
        active_fund_misses=0, active_fund_stale=0,
        passive_misses=0, passive_stale=0, top_n=10,
        active_fund_fund_level_repair=2,
    )
    exc = FetchBudgetExceeded(plan=plan, total=8, budget=1)
    assert "active_fund_fund_level_repair=2" in str(exc)
```

- [ ] **Step 3.2: Run new tests to verify red**

Run: `uv run pytest tests/commands/test_opportunity_cmd.py -q -k "item004 or classify_fresh_foreign or classify_data_leg_gap_wins or classify_date_stale_and_gapped or fund_level_repair_costs or probe_plus_repair or message_includes_fund_level_repair"`
Expected: 6 failed — 3 × `TypeError: FetchPlan.__init__() got an unexpected keyword argument 'active_fund_fund_level_repair'` and 3 × `assert (0, 1, 0) == (0, 0, 0, 1)`-style tuple-length mismatches (the classifier still returns a 3-tuple).

- [ ] **Step 3.3: Implement — FetchPlan field, total_calls, exception message, import**

In `src/irc/commands/opportunity_cmd.py`, four edits:

(a) Policy-B import (line 19). Replace:

```python
from irc.opportunity.policy_b import PolicyBVerdict, evaluate_policy_b
```

with:

```python
from irc.opportunity.policy_b import (
    PolicyBVerdict,
    evaluate_policy_b,
    foreign_heavy_fund_level_gap,
)
```

(b) `FetchPlan` field. Replace:

```python
    active_fund_stale_probe_only: int = 0

    def total_calls(self) -> int:
```

with:

```python
    active_fund_stale_probe_only: int = 0
    # Item 004 (todos-critical-fixes): foreign-heavy cached funds whose
    # fund_level_evidence lacks a data or information leg (rule 2.5's gap,
    # `foreign_heavy_fund_level_gap`) get a 4-call fund-level evidence repair
    # (1 NAV + 3 announcement endpoints) on the cached-serve path — never the
    # ~35-call full re-fetch. MAY overlap with active_fund_stale_probe_only
    # (date-stale + gapped ⇒ probe 1 + repair 4 = 5 planned calls).
    active_fund_fund_level_repair: int = 0

    def total_calls(self) -> int:
```

(c) `total_calls()` term. Replace:

```python
        return (
            (self.active_fund_misses + self.active_fund_stale) * per_active
            + self.active_fund_stale_probe_only * 1  # cheap freshness probe only
            + (self.fund_level_misses + self.fund_level_stale) * per_fund_level
```

with:

```python
        return (
            (self.active_fund_misses + self.active_fund_stale) * per_active
            + self.active_fund_stale_probe_only * 1  # cheap freshness probe only
            + self.active_fund_fund_level_repair * per_fund_level  # 4-call repair (item 004)
            + (self.fund_level_misses + self.fund_level_stale) * per_fund_level
```

(d) `FetchBudgetExceeded` message. Replace:

```python
            f"active_fund_stale_probe_only={plan.active_fund_stale_probe_only} "
            f"fund_level_misses={plan.fund_level_misses} "
```

with:

```python
            f"active_fund_stale_probe_only={plan.active_fund_stale_probe_only} "
            f"active_fund_fund_level_repair={plan.active_fund_fund_level_repair} "
            f"fund_level_misses={plan.fund_level_misses} "
```

- [ ] **Step 3.4: Implement — classifier 4-tuple**

Replace the ENTIRE `_classify_active_fund_scores` function (currently :595–641, from `def _classify_active_fund_scores(` through `    return misses, stale_full, stale_probe`) with:

```python
def _classify_active_fund_scores(
    scores: list[dict],
    root: Path,
    *,
    today: date_cls,
    threshold_days: int,
    rebuild_fundamentals: bool,
    completed_ids: set[str] | None = None,
) -> tuple[int, int, int, int]:
    """Count (misses, stale_full, stale_probe_only, fund_level_repair) among
    cn_equity_fund rows.

    For the preflight budget estimate:
    - miss        = no cache file on disk → full top-N build.
    - stale_full  = cache exists but has a data-leg gap → forced full re-fetch
                    (includes the fund-level legs — never double-counted as
                    a repair).
    - stale_probe = cache exists, date-overdue, but data-leg-complete → resolves
                    with a single cheap freshness probe (1 call), not a full
                    re-fetch (unless that probe later finds the quarter rolled).
    - fund_level_repair = cache exists, no data-leg gap, AND
                    `foreign_heavy_fund_level_gap` (rule 2.5's gap mirror) →
                    4-call fund-level evidence repair on the cached-serve path
                    (item 004). A fund MAY count toward BOTH stale_probe AND
                    fund_level_repair (probe 1 + repair 4 = 5 — the plan
                    matches the expected runtime path).
    rebuild_fundamentals = True → every fund counts as a miss (full re-fetch forced).
    completed_ids: funds already finished in the current resume state are excluded
        from every count (resume credit, spec AC item 4 hardening).
    """
    _completed = completed_ids or set()
    misses = 0
    stale_full = 0
    stale_probe = 0
    repair = 0
    seen: set[str] = set()
    for score in scores:
        if score.get("asset_class") != "cn_equity_fund":
            continue
        iid = score.get("instrument_id", "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        # Credit already-completed funds — no fetch cost on a resumed run.
        if iid in _completed:
            continue
        if rebuild_fundamentals:
            misses += 1
            continue
        cached = _load_latest_active_fund_cached(iid, root)
        if cached is None:
            misses += 1
            continue
        if _active_snapshot_has_required_data_leg_gap(cached):
            stale_full += 1
            continue
        if _is_stale(cached, today=today, threshold_days=threshold_days):
            stale_probe += 1
        if foreign_heavy_fund_level_gap(cached):
            repair += 1
    return misses, stale_full, stale_probe, repair
```

- [ ] **Step 3.5: Implement — production call site (:776) + plan construction**

Replace:

```python
        misses, stale_full, stale_probe = _classify_active_fund_scores(
```

with:

```python
        misses, stale_full, stale_probe, fund_level_repair = _classify_active_fund_scores(
```

Then replace:

```python
            fund_level_misses=fl_misses,
            fund_level_stale=fl_stale,
            active_fund_stale_probe_only=stale_probe,
        )
```

with:

```python
            fund_level_misses=fl_misses,
            fund_level_stale=fl_stale,
            active_fund_stale_probe_only=stale_probe,
            active_fund_fund_level_repair=fund_level_repair,
        )
```

- [ ] **Step 3.6: Mechanical edits — the 3 test call sites (same commit; they break otherwise)**

In `tests/commands/test_opportunity_cmd.py`. NOTE: the bare unpack line
`    misses, stale_full, stale_probe = _classify_active_fund_scores(` appears at BOTH
:675 and :719 — a single-line Edit is NOT unique. Use the full multi-line blocks below
(disambiguated by the `today=` argument).

(a) At :675 (`test_classify_active_fund_scores_counts_missing_data_leg_cache_as_stale`), replace:

```python
    misses, stale_full, stale_probe = _classify_active_fund_scores(
        [{"instrument_id": "005827", "asset_class": "cn_equity_fund"}],
        tmp_path,
        today=date(2026, 5, 22),
        threshold_days=7,
        rebuild_fundamentals=False,
    )

    # Missing data leg → full re-fetch bucket (not the cheap-probe bucket).
    assert (misses, stale_full, stale_probe) == (0, 1, 0)
```

with:

```python
    misses, stale_full, stale_probe, fund_level_repair = _classify_active_fund_scores(
        [{"instrument_id": "005827", "asset_class": "cn_equity_fund"}],
        tmp_path,
        today=date(2026, 5, 22),
        threshold_days=7,
        rebuild_fundamentals=False,
    )

    # Missing data leg → full re-fetch bucket (not the cheap-probe bucket).
    assert (misses, stale_full, stale_probe, fund_level_repair) == (0, 1, 0, 0)
```

(b) At :719 (`test_date_stale_but_complete_cache_counts_as_probe_only`), replace:

```python
    misses, stale_full, stale_probe = _classify_active_fund_scores(
        [{"instrument_id": "005827", "asset_class": "cn_equity_fund"}],
        tmp_path,
        today=date(2026, 6, 4),
        threshold_days=7,
        rebuild_fundamentals=False,
    )
    assert (misses, stale_full, stale_probe) == (0, 0, 1)
```

with:

```python
    misses, stale_full, stale_probe, fund_level_repair = _classify_active_fund_scores(
        [{"instrument_id": "005827", "asset_class": "cn_equity_fund"}],
        tmp_path,
        today=date(2026, 6, 4),
        threshold_days=7,
        rebuild_fundamentals=False,
    )
    assert (misses, stale_full, stale_probe, fund_level_repair) == (0, 0, 1, 0)
```

(c) At :930 (`test_build_rows_stamps_policy_b_gaps_for_active_fund_rows`), replace:

```python
        "irc.commands.opportunity_cmd._classify_active_fund_scores",
        return_value=(0, 0, 0),
```

with:

```python
        "irc.commands.opportunity_cmd._classify_active_fund_scores",
        return_value=(0, 0, 0, 0),
```

- [ ] **Step 3.7: Run per-file to verify green**

Run: `uv run pytest tests/commands/test_opportunity_cmd.py -q`
Expected: all passed, 0 failed (existing suite + 6 new; the 3 mechanically-edited tests green in their 4-tuple shape).

Run: `uv run pytest tests/commands/test_opportunity_cmd_acceptance.py -q`
Expected: all passed (positional `FetchPlan(5, 0, 0, 0, 10)` at :100 binds only the first 5 params — untouched).

- [ ] **Step 3.8: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py tests/commands/test_opportunity_cmd.py
git commit -m "feat(opportunity): FetchPlan fund-level-repair budget class + 4-tuple classifier (004 AC5/AC6)"
```

---

### Task 4: `_maybe_fund_level_evidence_repair` — wiring on the cached-serve arm + AC7 integration heal

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py` (new import; new helper after `_load_latest_active_fund_cached`; wiring at the `else: snap_obj = probed` arm :910–912)
- Modify: `tests/commands/test_opportunity_cmd.py` (append 5 unit tests; uses `_item004_snapshot` from Task 3)
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append the item-004 prewrite helper + AC7 heal test)

**Interfaces:**
- Consumes: `foreign_heavy_fund_level_gap` (Task 1), `refetch_fund_level_evidence` (Task 2), existing `write_active_fund_cache` import.
- Produces: `_maybe_fund_level_evidence_repair(snap: ActiveFundSnapshot, *, root: Path) -> ActiveFundSnapshot`; the shared integration helper `_prewrite_gapped_fund_level_cache(tmp_path, *, fund_id, cache_probed_at, symbol)` reused by Task 5.

- [ ] **Step 4.1: Append the failing unit tests**

Append at the very end of `tests/commands/test_opportunity_cmd.py` (after Task 3's section):

```python
def _item004_fresh_legs():
    """Fund-level evidence pair in the producer shapes (both legs)."""
    from irc.fundamentals.types import ThesisEvidence
    return (
        ThesisEvidence(
            type="snapshot", source="006809", url="", date="2026-07-02",
            summary="NAV=1.5000 @ 2026-07-02", scope="instrument",
            citation_kind="data", owner_instrument_id="006809",
            parent_fund_id=None, constituent_key=None,
        ),
        ThesisEvidence(
            type="news", source="fund_announcement_report_em", url="",
            date="2026-07-01", summary="[REP-9] 季度报告", scope="instrument",
            citation_kind="information", owner_instrument_id="006809",
            parent_fund_id=None, constituent_key=None,
        ),
    )


def test_repair_skips_non_foreign_fund_and_fires_zero_calls(monkeypatch, tmp_path) -> None:
    """Item 004 AC4/AC8 — CN-heavy (below threshold) gapped cache: predicate
    False → same snapshot returned, ZERO fetch calls, ZERO cache writes.
    Widening to non-foreign funds is explicitly deferred (spec Non-goals)."""
    from irc.commands.opportunity_cmd import _maybe_fund_level_evidence_repair

    snap = _item004_snapshot(symbol="600519")
    calls: list[str] = []
    monkeypatch.setattr(
        "irc.fundamentals.fund_level_repair._fetch_active_fund_level_evidence",
        lambda fund_id: calls.append(fund_id) or ((), []),
    )
    writes: list = []
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.write_active_fund_cache",
        lambda s, r: writes.append(s),
    )
    out = _maybe_fund_level_evidence_repair(snap, root=tmp_path)
    assert out is snap
    assert calls == []
    assert writes == []


def test_repair_heals_gapped_foreign_fund_and_writes_cache(monkeypatch, tmp_path) -> None:
    """Item 004 AC4 — foreign-heavy gapped cache + successful 4-call refetch:
    merged snapshot written once (P0-5 pattern via write_active_fund_cache),
    cache_probed_at untouched, leg-failure strings cleared."""
    from irc.commands.opportunity_cmd import _maybe_fund_level_evidence_repair

    snap = _item004_snapshot()
    fresh = _item004_fresh_legs()
    monkeypatch.setattr(
        "irc.fundamentals.fund_level_repair._fetch_active_fund_level_evidence",
        lambda fund_id: (fresh, []),
    )
    writes: list = []
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.write_active_fund_cache",
        lambda s, r: writes.append((s, r)),
    )
    out = _maybe_fund_level_evidence_repair(snap, root=tmp_path)
    assert out.fund_level_evidence == fresh
    assert out.fund_level_failure_reasons == ()
    assert out.cache_probed_at == snap.cache_probed_at
    assert len(writes) == 1
    assert writes[0][0] == out
    assert writes[0][1] == tmp_path


def test_repair_skips_cache_write_when_quarter_empty(monkeypatch, tmp_path) -> None:
    """Item 004 AC4 — P0-5: empty source_report_quarter → merged snapshot is
    served in-memory but NEVER written (avoids the path-collapse
    data/fundamentals//active_fund/fund_X.json)."""
    from irc.commands.opportunity_cmd import _maybe_fund_level_evidence_repair

    snap = _item004_snapshot(source_report_quarter="")
    fresh = _item004_fresh_legs()
    monkeypatch.setattr(
        "irc.fundamentals.fund_level_repair._fetch_active_fund_level_evidence",
        lambda fund_id: (fresh, []),
    )
    writes: list = []
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.write_active_fund_cache",
        lambda s, r: writes.append(s),
    )
    out = _maybe_fund_level_evidence_repair(snap, root=tmp_path)
    assert out.fund_level_evidence == fresh
    assert writes == []


def test_repair_cache_write_failure_degrades_to_in_memory(monkeypatch, tmp_path, capsys) -> None:
    """Item 004 AC4 — cache-write failure: `cache_write_failed:{id}:{type}` on
    stderr, merged snapshot still served (the _maybe_freshness_probe degrade
    pattern, disk errors are environmental)."""
    from irc.commands.opportunity_cmd import _maybe_fund_level_evidence_repair

    snap = _item004_snapshot()
    fresh = _item004_fresh_legs()
    monkeypatch.setattr(
        "irc.fundamentals.fund_level_repair._fetch_active_fund_level_evidence",
        lambda fund_id: (fresh, []),
    )

    def _disk_full(s, r):
        raise OSError("disk full")

    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.write_active_fund_cache", _disk_full,
    )
    out = _maybe_fund_level_evidence_repair(snap, root=tmp_path)
    assert out.fund_level_evidence == fresh
    assert "cache_write_failed:006809:OSError" in capsys.readouterr().err


def test_repair_refires_each_run_with_zero_writes_on_persistent_failure(
    monkeypatch, tmp_path,
) -> None:
    """Item 004 AC9 — no backoff BY DESIGN: a failing refetch is re-attempted
    on every invocation (each run), never writes the cache (content unchanged),
    and keeps serving the cached snapshot. Within-run the attempt count is 1
    via the existing snapshot_cache memoisation in _build_rows."""
    from irc.commands.opportunity_cmd import _maybe_fund_level_evidence_repair

    snap = _item004_snapshot()
    attempts: list[str] = []

    def _boom(fund_id):
        attempts.append(fund_id)
        raise ConnectionError("akshare 502")

    monkeypatch.setattr(
        "irc.fundamentals.fund_level_repair._fetch_active_fund_level_evidence",
        _boom,
    )
    writes: list = []
    monkeypatch.setattr(
        "irc.commands.opportunity_cmd.write_active_fund_cache",
        lambda s, r: writes.append(s),
    )
    first = _maybe_fund_level_evidence_repair(snap, root=tmp_path)
    second = _maybe_fund_level_evidence_repair(snap, root=tmp_path)
    assert attempts == ["006809", "006809"]
    assert writes == []
    assert first == snap
    assert second == snap
```

- [ ] **Step 4.2: Append the failing AC7 integration heal test**

In `tests/integration/test_publishable_set_lockdown.py`, append at the very end of the file:

```python
# ─── Item 004 (todos-critical-fixes): fund-level evidence repair ─────────────


def _prewrite_gapped_fund_level_cache(
    tmp_path: Path, *, fund_id: str, cache_probed_at: str, symbol: str,
) -> None:
    """Item 004 — cache whose single constituent carries a data leg (so
    `_active_snapshot_has_required_data_leg_gap` stays False) and whose
    `fund_level_evidence` is EMPTY (rule 2.5 leg gap).
    symbol="00700.HK" → foreign-heavy (repair fires);
    symbol="600519"  → CN-heavy (repair must NOT fire, spec AC8)."""
    from irc.fundamentals.snapshot_cache import write_active_fund_cache
    from irc.fundamentals.types import (
        ActiveFundSnapshot, ConstituentAnalysis, ThesisEvidence,
    )

    data_leg = ThesisEvidence(
        type="filing", source=symbol, url="", date="2026-04-15",
        summary=f"{symbol} 26Q1 财报", scope="constituent",
        citation_kind="data", owner_instrument_id=fund_id,
        parent_fund_id=fund_id, constituent_key=symbol,
    )
    snap = ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date="2026-03-31",
        source_report_quarter="2026Q1",
        cache_probed_at=cache_probed_at,
        constituent_analyses=(
            ConstituentAnalysis(
                symbol=symbol, name_cn=symbol, weight_pct=8.0,
                evidence=(data_leg,), failure_reasons=(),
                one_line_view="核心持仓",
            ),
        ),
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=(
            f"fund_nav_unavailable:{fund_id}",
            f"fund_announcements_unavailable:{fund_id}",
        ),
        fund_level_evidence=(),
    )
    write_active_fund_cache(snap, tmp_path / "data")


def test_fund_level_evidence_repair_heals_foreign_heavy_gapped_cache(
    tmp_path, monkeypatch,
) -> None:
    """Item 004 AC7 — fresh-by-date foreign-heavy cache with empty
    fund_level_evidence: run_opportunity (a) fires ONLY the 4 fund-level
    calls (1 NAV + 3 announcements) — zero holdings probes, zero
    constituent-evidence calls; (b) rule 2.5 publishes (the
    foreign_heavy_fund_level_evidence_missing gap is NOT re-emitted);
    (c) the on-disk cache re-loads healed with cache_probed_at unchanged."""
    from irc.commands.opportunity_cmd import run_opportunity
    import pandas as pd

    today = _today_cn()
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",), seed_date=today,
    )
    _prewrite_gapped_fund_level_cache(
        tmp_path, fund_id="005827", cache_probed_at=today, symbol="00700.HK",
    )
    # NAV frame parseable by fetch_fund_nav_report (净值日期 + 单位净值).
    dispatch[("fund_open_fund_info_em", "005827")] = pd.DataFrame({
        "净值日期": ["2026-06-29", "2026-06-30"],
        "单位净值": [1.4900, 1.5000],
    })
    # The three announcement frames for 005827 are already in the seed.
    counter = _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(repo_root=str(tmp_path))

    # (a) exactly the 4 fund-level repair calls; nothing else for this fund.
    assert counter[("fund_open_fund_info_em", "005827")] == 1
    assert counter[("fund_announcement_dividend_em", "005827")] == 1
    assert counter[("fund_announcement_report_em", "005827")] == 1
    assert counter[("fund_announcement_personnel_em", "005827")] == 1
    assert counter[("fund_portfolio_hold_em", "005827")] == 0, \
        "fresh cache must not fire a quarter probe or a full rebuild"
    constituent_calls = sum(
        v for (fn, _sym), v in counter.items()
        if fn in (
            "stock_financial_abstract", "stock_research_report_em", "stock_news_em",
        )
    )
    assert constituent_calls == 0, "repair must not re-fetch constituent evidence"

    # (b) rule 2.5 heals within the SAME run (grill R5): the fund publishes;
    # the gap code is not re-emitted.
    out_dir = tmp_path / "outputs" / today
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    row_iids = {r["instrument_id"] for r in opp.get("rows", [])}
    assert "005827" in row_iids, \
        "healed foreign-heavy fund should publish via rule 2.5 in the same run"
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entry = next(
        (e for e in rej.get("entries", []) if e["instrument_id"] == "005827"),
        None,
    )
    assert entry is None or (
        "foreign_heavy_fund_level_evidence_missing"
        not in entry.get("evidence_gaps", [])
    ), f"repair failed to heal the rule 2.5 gap: {entry}"

    # (c) on-disk cache healed; cache_probed_at unchanged (repair is
    # orthogonal to holdings-quarter freshness).
    from irc.fundamentals.snapshot_cache import load_active_fund_cache
    healed = load_active_fund_cache("005827", "2026Q1", tmp_path / "data")
    assert healed is not None
    kinds = {e.citation_kind for e in healed.fund_level_evidence}
    assert kinds == {"data", "information"}, f"cache not healed: {kinds}"
    assert healed.cache_probed_at == today
    assert healed.fund_level_failure_reasons == ()
```

- [ ] **Step 4.3: Run to verify red**

Run: `uv run pytest tests/commands/test_opportunity_cmd.py -q -k "test_repair_"`
Expected: 5 failed — `ImportError: cannot import name '_maybe_fund_level_evidence_repair' from 'irc.commands.opportunity_cmd'`

Run: `uv run pytest tests/integration/test_publishable_set_lockdown.py::test_fund_level_evidence_repair_heals_foreign_heavy_gapped_cache -q`
Expected: 1 failed — `assert counter[("fund_open_fund_info_em", "005827")] == 1` fails with `0 == 1` (no repair exists yet; the fresh cache serves untouched and the gap re-emits).

- [ ] **Step 4.4: Implement — import, helper, wiring**

In `src/irc/commands/opportunity_cmd.py`, three edits:

(a) Import (after the `akshare_fundamentals` import at :27). Replace:

```python
from irc.fundamentals.akshare_fundamentals import fetch_cn_etf_holdings
from irc.fundamentals.provider import CnFundamentalsProvider, default_cn_provider
```

with:

```python
from irc.fundamentals.akshare_fundamentals import fetch_cn_etf_holdings
from irc.fundamentals.fund_level_repair import refetch_fund_level_evidence
from irc.fundamentals.provider import CnFundamentalsProvider, default_cn_provider
```

(b) Helper — insert immediately BEFORE the Item-005 comment block. Replace:

```python
# ── Item 005: fund-level + QDII dispatch helpers ──────────────────────────────
# _FUND_LEVEL_KINDS is imported from irc.fundamentals.snapshot (single source of truth).
```

with:

```python
def _maybe_fund_level_evidence_repair(
    snap: ActiveFundSnapshot, *, root: Path,
) -> ActiveFundSnapshot:
    """Fund-level evidence repair probe — cached-serve path ONLY (item 004).

    Receives the POST-probe served snapshot (grill R4 — merging into the
    pre-probe `cached` would roll back a probe-advanced `cache_probed_at`).
    When `foreign_heavy_fund_level_gap` is False → returns `snap` with zero
    fetch calls and zero writes. When True → 4-call fund-level refetch +
    leg-wise merge (`refetch_fund_level_evidence`, never raises); the cache
    is re-written ONLY when the evidence actually changed AND
    `source_report_quarter` is non-empty (P0-5 — avoids the
    `data/fundamentals//active_fund/` path collapse). Never touches
    `cache_probed_at`. Cache-write failure degrades to serving the merged
    snapshot in-memory (the `_maybe_freshness_probe` degrade pattern).
    No backoff: re-fires every run until healed (resolved Q5; CONTEXT.md
    "Fund-level evidence repair (repair probe)").
    """
    if not foreign_heavy_fund_level_gap(snap):
        return snap
    merged = refetch_fund_level_evidence(snap)
    if (
        merged.fund_level_evidence != snap.fund_level_evidence
        and merged.source_report_quarter
    ):
        try:
            write_active_fund_cache(merged, root)
        except Exception as cache_exc:
            sys.stderr.write(
                f"cache_write_failed:{snap.fund_id}:{type(cache_exc).__name__}\n"
            )
    return merged


# ── Item 005: fund-level + QDII dispatch helpers ──────────────────────────────
# _FUND_LEVEL_KINDS is imported from irc.fundamentals.snapshot (single source of truth).
```

(c) Wiring — the cached-serve arm (:910–912, the ONLY `snap_obj = probed` in the file). Replace:

```python
                            else:
                                snap_obj = probed
                                _write_state_complete(fetch_state, fund_id, snap_obj, fundamentals_dir, plan_hash)
```

with:

```python
                            else:
                                # Item 004: fund-level evidence repair on the
                                # cached-serve arm ONLY — post-probe snapshot,
                                # before _write_state_complete (spec AC4).
                                snap_obj = _maybe_fund_level_evidence_repair(
                                    probed, root=root / "data",
                                )
                                _write_state_complete(fetch_state, fund_id, snap_obj, fundamentals_dir, plan_hash)
```

Do NOT touch the `completed_ids` resume path (:851–852), the `rebuild_fundamentals` path, the cache-miss path, or the `refresh=True` arm — all of them rebuild the fund-level legs via `build_snapshot` (and the `refresh=True` skip is what keeps the pre-existing quarter-roll under-count from compounding, grill R2).

- [ ] **Step 4.5: Run to verify green**

Run: `uv run pytest tests/commands/test_opportunity_cmd.py -q`
Expected: all passed (5 new `test_repair_*` green; the 4 `_maybe_freshness_probe` tests and everything else untouched and green).

Run: `uv run pytest tests/integration/test_publishable_set_lockdown.py::test_fund_level_evidence_repair_heals_foreign_heavy_gapped_cache -q`
Expected: 1 passed.

- [ ] **Step 4.6: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py tests/commands/test_opportunity_cmd.py tests/integration/test_publishable_set_lockdown.py
git commit -m "feat(opportunity): wire fund-level evidence repair on the cached-serve path (004 AC4/AC7/AC9)"
```

---

### Task 5: AC8 negative lockdown — CN-heavy gapped cache fires ZERO calls + existing locks unmodified

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append one test; uses `_prewrite_gapped_fund_level_cache` from Task 4)

**Interfaces:**
- Consumes: `_prewrite_gapped_fund_level_cache` (Task 4), seed helpers.
- Produces: the scope lock named by the spec's Non-goals ("No widening beyond foreign-heavy funds").

- [ ] **Step 5.1: Append the negative test**

Append at the very end of `tests/integration/test_publishable_set_lockdown.py`:

```python
def test_snapshot_cache_fresh_cn_heavy_gapped_fund_level_no_repair(
    tmp_path, monkeypatch,
) -> None:
    """Item 004 AC8 (negative lock) — a fresh CN-heavy cache (foreign share
    0.0, below FOREIGN_HEAVY_THRESHOLD) with EMPTY fund_level_evidence fires
    ZERO AkShare calls for the fund: the repair is locked to foreign-heavy
    funds; widening is a separate, deferred decision (spec Non-goals).
    GREEN-lock: this test passes both before and after item 004."""
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",), seed_date=today,
    )
    _prewrite_gapped_fund_level_cache(
        tmp_path, fund_id="005827", cache_probed_at=today, symbol="600519",
    )
    counter = _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(repo_root=str(tmp_path))

    fund_calls = sum(v for (fn, sym), v in counter.items() if sym == "005827")
    assert fund_calls == 0, \
        f"CN-heavy gapped cache must fire zero repair calls, got {fund_calls}: " \
        f"{[k for k in counter if k[1] == '005827']}"
```

- [ ] **Step 5.2: Run the new test + the AC8 existing locks — all must pass UNMODIFIED**

Run:

```bash
uv run pytest tests/integration/test_publishable_set_lockdown.py -q
```

Expected: all passed — specifically `test_snapshot_cache_within_window_zero_akshare_calls` (AC15: empty `constituent_analyses` ⇒ share 0.0 ⇒ predicate False ⇒ still zero calls), `test_snapshot_cache_expired_probe_same_quarter_reuses` (AC16: same empty-analyses fixture ⇒ probe-only, exactly 1 `fund_portfolio_hold_em` call — grill R6), `test_snapshot_cache_probe_failure_fail_closed_refetch` (AC17), plus both new item-004 tests. Zero edits to any pre-existing test in this file.

Run: `uv run pytest tests/commands/test_opportunity_cmd.py -q -k "freshness_probe"`
Expected: 4 passed — the `_maybe_freshness_probe` unit tests pass unmodified (its signature and semantics are untouched).

- [ ] **Step 5.3: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): CN-heavy gapped cache fires zero repair calls — scope lock (004 AC8)"
```

---

### Task 6: Docs — docstring fix, ADR 0003 §7 addendum + stale-count fix, CHANGELOG, TODOS.md, CONTEXT verify

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py` (:486–487 docstring only)
- Modify: `docs/adr/0003-failure-mode-policy-b.md` (§7 "Fetch budget impact" + addendum paragraph)
- Modify: `CHANGELOG.md` (`[Unreleased]`)
- Modify: `TODOS.md` (line 21)
- Verify (no edit expected): `CONTEXT.md`

- [ ] **Step 6.1: Fix the stale docstring claim (AC6 doc-sync)**

In `src/irc/fundamentals/snapshot.py`, replace:

```python
    legs to short-circuit foreign-heavy funds. Per-fund call delta = 2 AkShare
    calls; see `_fetch_budget` in opportunity_cmd.py (default budget 2000).
```

with:

```python
    legs to short-circuit foreign-heavy funds. Per-fund call delta = 4 AkShare
    calls (1 NAV + 3 announcement endpoints, `_FUND_ANN_TOPIC_FNS`); see
    `_fetch_budget` in opportunity_cmd.py (default budget 2000).
```

- [ ] **Step 6.2: ADR 0003 §7 — fix the stale fetch-budget claim (grill R7)**

In `docs/adr/0003-failure-mode-policy-b.md`, replace:

```markdown
**Fetch budget impact.**
- Per active fund, `_build_active_fund_snapshot` now fires **2 additional AkShare calls** (NAV + announcements). On a full canonical run with ~50 active funds this adds ~100 calls; well under the default `IRC_FETCH_BUDGET=2000`. No preflight-budget contract change.
```

with:

```markdown
**Fetch budget impact.** *(Corrected 2026-07-03, todos-critical-fixes item 004 — the original "2 calls (~100)" figure predated the three-endpoint announcement union; the code's `per_active` "+4" term and `_FUND_ANN_TOPIC_FNS` were already right.)*
- Per active fund, `_build_active_fund_snapshot` now fires **4 additional AkShare calls** (1 NAV + 3 topic-specific announcement endpoints). On a full canonical run with ~50 active funds this adds ~200 calls; well under the default `IRC_FETCH_BUDGET=2000`. No preflight-budget contract change.
```

- [ ] **Step 6.3: ADR 0003 §7 — append the repair addendum paragraph (AC11/R7)**

In `docs/adr/0003-failure-mode-policy-b.md`, replace:

```markdown
- *Alternative C — make the threshold YAML-configurable from V1.* Rejected: a policy decision belongs in code+ADR. Runtime tuning would silently weaken the audit trail. Future promotion to env var is reversible without an API change.

### 8. Thesis-level dual-leg union for `ActiveFundSnapshot` — 2026-07-03 amendment
```

with:

```markdown
- *Alternative C — make the threshold YAML-configurable from V1.* Rejected: a policy decision belongs in code+ADR. Runtime tuning would silently weaken the audit trail. Future promotion to env var is reversible without an API change.

**Fund-level evidence repair on the cached-serve path — 2026-07-03 addendum (todos-critical-fixes item 004).**
- A cached foreign-heavy `ActiveFundSnapshot` whose `fund_level_evidence` is missing a data leg OR an information leg — exactly rule 2.5's gap condition, shared via the public predicate `foreign_heavy_fund_level_gap` co-located with rule 2.5 in `policy_b.py` — is **repaired in place** on the cached-serve path: `_maybe_fund_level_evidence_repair` (`opportunity_cmd.py`) re-runs ONLY the fund-level legs via `refetch_fund_level_evidence` (`fundamentals/fund_level_repair.py`) at a cost of **4 AkShare calls** (1 NAV + 3 announcement endpoints) and **leg-wise merges** the result: per `citation_kind`, fresh entries win when the refetch produced that leg, cached entries are retained when it didn't (monotone leg presence — a partial heal never drops a surviving cached leg), and leg-failure strings are present in `fund_level_failure_reasons` ⟺ the leg is absent in the MERGED evidence (the producer invariant). Holdings, per-constituent evidence, and `cache_probed_at` are untouched; the cache is re-written only when the evidence changed (and `source_report_quarter` is non-empty).
- **No backoff by design:** the repair re-fires every run until healed, bounded to one 4-call attempt per fund per run (snapshot-cache memoisation) — the same accepted retry pattern as the data-leg-gap full refetch, which costs ~35 calls/run until its gap heals; a persisted backoff marker would need a snapshot schema migration for negligible savings.
- **Budget accounting:** the preflight classifier (`_classify_active_fund_scores`, now a 4-tuple) counts these funds in a dedicated `FetchPlan.active_fund_fund_level_repair` class charged at ×4 — never the ~35-call `per_active` term — so the plan matches the runtime path; a date-stale + gapped fund is charged probe 1 + repair 4 = 5. The repair is skipped on the `refresh=True` arm, so the pre-existing quarter-roll under-count (probe charged 1, actual ~35) is never compounded.

### 8. Thesis-level dual-leg union for `ActiveFundSnapshot` — 2026-07-03 amendment
```

- [ ] **Step 6.4: CHANGELOG `[Unreleased]` entry**

In `CHANGELOG.md`, replace:

```markdown
## [Unreleased]

### Removed — production-dead per-fund narrative module `src/irc/monitor/narrative.py` (2026-07-03)
```

with:

```markdown
## [Unreleased]

### Fixed — fund-level evidence repair probe for foreign-heavy cached snapshots (2026-07-03)

- **A cached foreign-heavy `ActiveFundSnapshot` with a rule-2.5 fund-level evidence
  leg gap no longer re-emits `foreign_heavy_fund_level_evidence_missing` for up to
  `IRC_CACHE_FRESHNESS_DAYS` (default 7) on stale evidence.** New repair probe on the
  cached-serve path (`_maybe_fund_level_evidence_repair`, `opportunity_cmd.py`,
  post-probe snapshot): when the new public predicate `foreign_heavy_fund_level_gap`
  (co-located with rule 2.5 in `policy_b.py` — single source of truth) is True, ONLY
  the fund-level legs are re-fetched (4 AkShare calls: 1 NAV + 3 announcement
  endpoints) and **leg-wise monotonically merged** by the new pure module
  `src/irc/fundamentals/fund_level_repair.py` — per leg, fresh entries win when
  produced, cached entries are retained when not, and leg-failure strings are
  present ⟺ the leg is absent in the merged evidence (producer invariant).
  `cache_probed_at`, holdings, and constituent evidence untouched; the cache is
  re-written only when the evidence changed (P0-5 quarter guard inherited via
  `write_active_fund_cache`); fetch failures degrade to serving the cached snapshot;
  no backoff (re-fires each run until healed). Preflight budget:
  `_classify_active_fund_scores` returns a 4-tuple and `FetchPlan` gains
  `active_fund_fund_level_repair` charged at ×4 — never the ~35-call full-refetch
  term (the historical over-estimate trap class). Trigger deliberately corrected
  from the TODO's `fund_level_evidence == ()` to the rule-2.5 leg-gap mirror (a
  NAV-only outage leaves a non-empty info-only tuple that `== ()` would never
  repair). ADR 0003 §7 addendum added; §7's stale "2 additional AkShare calls
  (~100)" claim corrected to 4 (~200), matching the `snapshot.py` docstring fix.
  No VERSION bump.

### Removed — production-dead per-fund narrative module `src/irc/monitor/narrative.py` (2026-07-03)
```

- [ ] **Step 6.5: TODOS.md line 21 annotation**

In `TODOS.md`, replace (single line — the current line 21, verbatim):

```markdown
- [ ] **Mixed-fund stale-cache with empty `fund_level_evidence` not force-retried** — when `_fetch_active_fund_level_evidence` returns `()` (e.g. NAV fetch failed once), and the fund's CN constituents satisfy `_active_snapshot_has_required_data_leg_gap`, the snapshot is cached with empty evidence. Next run reuses the cached snapshot; rule 2.5 emits `foreign_heavy_fund_level_evidence_missing` for up to `IRC_CACHE_FRESHNESS_DAYS` (default 7) until a full refetch is triggered. Add a freshness probe: `if fund_level_evidence == () AND _compute_foreign_listed_share(...) >= FOREIGN_HEAVY_THRESHOLD: force refetch`. (item-001 ship adversarial review 2026-05-26)
```

with:

```markdown
- [x] **Mixed-fund stale-cache with empty `fund_level_evidence` not force-retried** — when `_fetch_active_fund_level_evidence` returns `()` (e.g. NAV fetch failed once), and the fund's CN constituents satisfy `_active_snapshot_has_required_data_leg_gap`, the snapshot is cached with empty evidence. Next run reuses the cached snapshot; rule 2.5 emits `foreign_heavy_fund_level_evidence_missing` for up to `IRC_CACHE_FRESHNESS_DAYS` (default 7) until a full refetch is triggered. Add a freshness probe: `if fund_level_evidence == () AND _compute_foreign_listed_share(...) >= FOREIGN_HEAVY_THRESHOLD: force refetch`. (item-001 ship adversarial review 2026-05-26) **Resolved 2026-07-03:** trigger corrected from the proposed `== ()` to the rule-2.5 leg-gap mirror (missing data leg OR information leg — a NAV-only outage leaves a non-empty info-only tuple that `== ()` would never repair), via new public predicate `foreign_heavy_fund_level_gap` co-located with rule 2.5 in `policy_b.py`. The cached-serve path now runs a *fund-level evidence repair probe* (`_maybe_fund_level_evidence_repair` → `refetch_fund_level_evidence` in new `src/irc/fundamentals/fund_level_repair.py`): 4-call fund-level refetch + leg-wise monotone merge (fresh leg wins when produced, cached leg retained when not; leg-failure ⟺ leg-absence invariant preserved; `cache_probed_at` untouched; no backoff), with a dedicated `FetchPlan.active_fund_fund_level_repair` budget class (×4, never the ~35-call full refetch). Tests: `test_foreign_heavy_fund_level_gap_*` (tests/opportunity/test_policy_b.py); `tests/fundamentals/test_fund_level_repair.py` (incl. `test_merge_cached_info_only_plus_fresh_data_only_heals_both_legs` — the heal-under-throttle case); `test_classify_*`/`test_fetch_plan_*repair*`/`test_repair_*` (tests/commands/test_opportunity_cmd.py); `test_fund_level_evidence_repair_heals_foreign_heavy_gapped_cache` + `test_snapshot_cache_fresh_cn_heavy_gapped_fund_level_no_repair` (tests/integration/test_publishable_set_lockdown.py).
```

- [ ] **Step 6.6: Verify CONTEXT.md as-built match (no edit expected)**

Read the CONTEXT.md entry "**Fund-level evidence repair (repair probe)**" (line ~88) and the cross-ref in "**Foreign-heavy fund (rule 2.5 short-circuit)**" (line ~114), both committed at grill time (`ff259456`). Confirm every claim matches the as-built behavior: leg-gap trigger via `foreign_heavy_fund_level_gap`; 4-call cost; leg-wise monotone merge; leg-failure ⟺ leg-absence invariant; `cache_probed_at` untouched; no backoff, one attempt per fund per run; own `FetchPlan.active_fund_fund_level_repair` class; foreign-heavy only; holdings/constituents untouched. All nine are implemented exactly as written in Tasks 1–4 — expect NO edit. If any detail shifted during implementation, amend the entry to the as-built truth in this step and note it in the commit message.

- [ ] **Step 6.7: Run affected quick checks**

Run: `uv run pytest tests/fundamentals/test_snapshot.py -q`
Expected: all passed (docstring-only change).

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6.8: Commit**

```bash
git add src/irc/fundamentals/snapshot.py docs/adr/0003-failure-mode-policy-b.md CHANGELOG.md TODOS.md
git commit -m "docs(004): ADR 0003 §7 repair addendum + 4-call budget-claim fix, CHANGELOG, TODOS line 21"
```

(Include `CONTEXT.md` in the `git add` ONLY if Step 6.6 required an amendment.)

---

### Task 7: Full caller sweep + lint (AC10)

**Files:** none modified (fix-forward only if a genuine regression surfaces).

The touched surfaces are: `policy_b.py` (new public fn), new `fund_level_repair.py`, `snapshot.py` (docstring), `opportunity_cmd.py` (`FetchPlan`, classifier signature, `_build_rows` cached-serve arm, new helper). Per the signature-change test-scope rule (repo memory: `tests/monitor/` alone once missed a broken lambda in `tests/commands/`), sweep EVERY dir/file exercising them — `tests/commands/` strictly per-file (the whole dir hangs).

- [ ] **Step 7.1: Run the sweep, one command at a time**

```bash
uv run pytest tests/opportunity/ -q
uv run pytest tests/fundamentals/ -q
uv run pytest tests/commands/test_opportunity_cmd.py -q
uv run pytest tests/commands/test_opportunity_cmd_acceptance.py -q
uv run pytest tests/commands/test_opportunity_cmd_adversarial.py -q
uv run pytest tests/commands/test_opportunity_cmd_citation_gate.py -q
uv run pytest tests/commands/test_opportunity_cmd_enforce_mode.py -q
uv run pytest tests/commands/test_opportunity_cmd_fund_level.py -q
uv run pytest tests/commands/test_opportunity_cmd_fund_level_integration.py -q
uv run pytest tests/commands/test_opportunity_cmd_h3_invariant.py -q
uv run pytest tests/commands/test_opportunity_cmd_lookthrough_dormancy.py -q
uv run pytest tests/commands/test_opportunity_recorder.py -q
uv run pytest tests/narrative/ -q
uv run pytest tests/integration/test_publishable_set_lockdown.py -q
```

Expected: every command ends `... passed` (live-gated tests auto-skip without their `IRC_*` env vars). Rationale for the list: `tests/opportunity/` mirrors `policy_b.py`; `tests/fundamentals/` mirrors the new module + `snapshot.py`; every `tests/commands/test_opportunity_cmd*.py` + `test_opportunity_recorder.py` exercises `opportunity_cmd` (incl. the positional `FetchPlan(5, 0, 0, 0, 10)` at `test_opportunity_cmd_acceptance.py:100` and the keyword `FetchPlan` ctors in `test_opportunity_cmd_fund_level.py:196/:210/:225`); `tests/narrative/` constructs `FetchPlan` at 4 sites (keyword form — must stay green with the defaulted field); the lockdown file carries AC7/AC8/AC15–17.

- [ ] **Step 7.2: Diff-scope ANY failure before touching code**

For each failing test id (if any):

```bash
git stash && uv run pytest <failing-id> -q ; git stash pop
```

If it also fails on the pre-change tree it is one of the 24 known pre-existing failures — record it in the task notes and move on. Only a pass-before/fail-after result is a regression to fix (fix forward, re-run the file, amend the relevant task's commit or add a `fix:` commit).

- [ ] **Step 7.3: Lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 7.4: Final verification of the AC list**

Confirm each spec AC maps to green evidence: AC1 → Task 1 tests; AC2/AC3 → Task 2 tests; AC4/AC9 → Task 4 unit tests; AC5/AC6 → Task 3 tests (incl. no-35×-regression cost asserts); AC7 → Task 4 integration heal; AC8 → Task 5 negative + AC15/16/17 + 4 probe tests unmodified (verify with `git diff main -- tests/integration/test_publishable_set_lockdown.py` showing only APPENDED content, no edits to existing tests); AC10 → this task; AC11 → Task 6. No commit in this task unless Step 7.2 produced a fix.

---

## Self-review (performed at plan-writing time)

- **Spec coverage:** AC1→T1, AC2→T2, AC3→T2, AC4→T4, AC5→T3, AC6→T3+T6(docstring), AC7→T4, AC8→T5(+T1 empty-constituents predicate test), AC9→T4, AC10→T7, AC11→T6. Non-goals respected: no Policy-B rule text touched, no new endpoints, no widening (locked by T5), no snapshot schema change, no `_maybe_freshness_probe` change, eval-funds untouched.
- **R1 sites re-verified this session by grep:** exactly `opportunity_cmd.py:776`, `test_opportunity_cmd.py:675/:719/:930`. No other classifier reference exists anywhere in `src/`, `tests/`, `evals/`, `scripts/`.
- **Type consistency:** `foreign_heavy_fund_level_gap(snapshot) -> bool` (T1) is what T3/T4 import; `refetch_fund_level_evidence(snap) -> ActiveFundSnapshot` (T2) is what T4 calls; `_item004_snapshot` (T3) is what T4's unit tests reuse; `_prewrite_gapped_fund_level_cache` (T4) is what T5 reuses.
- **Ordering trap:** T3's mechanical test edits land in the SAME commit as the classifier signature change (they would break either tree in isolation).
