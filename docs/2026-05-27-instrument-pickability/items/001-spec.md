# Item 001 — `broker_empty` propagation → standing demotion

**Run**: `2026-05-27-instrument-pickability`
**Branch**: `autodev/instrument-pickability-feature`
**Mode**: backlog item (smallest surface; validates the autodev loop)

## Goal

When triggers eventually fire and the user is choosing which of the 候选可执行 funds to act on, an active fund with multiple Top-5 holdings missing broker coverage (`broker_empty:<symbol>` in `failure_reasons`) must be **visibly demoted** — not co-mingled with evidence-strong picks. Today the `⚠️ broker_empty:xxx` markers are cosmetic-only: they render after the per-constituent line in §5 持仓 (Top 5) and discipline_report.md but do not change `opportunity_state`, `thesis_state`, pick ordering, or §6 风险提示. This item makes the gap **load-bearing** in §6 and in pick ordering, without mutating `thesis_state` (which would break the load-bearing invariant from CONTEXT.md: *`thesis_state` is set ONLY by `derive_thesis_from_evidence`, never by Policy B*).

## Acceptance criteria

Each criterion is independently verifiable by a single test (or a single grep over today's regenerated outputs).

1. **AC1 — New gap code defined.** A new `OpportunityRow.evidence_gaps` code `top_holdings_broker_thin` is added to the project's gap-code vocabulary. It is documented next to the existing `missing_broker_coverage` entry in CONTEXT.md "Failure-mode + audit policy" (one-line glossary entry only — no ADR).

2. **AC2 — Gap emitter is `derive_thesis_from_evidence`, not a new setter.** The active-fund branch of `derive_thesis_from_evidence` in `src/irc/opportunity/thesis_evidence.py` returns the new gap in its `gaps` tuple when the threshold (AC3) is met. No new function mutates `OpportunityRow.thesis_state` or `OpportunityRow.evidence_gaps` outside `derive_thesis_from_evidence` / `build_opportunity_row` / Policy B (whose existing scope is untouched). The invariant *`thesis_state` is set ONLY by `derive_thesis_from_evidence`* is **preserved verbatim** — `thesis_state` is NOT downgraded by this item.

3. **AC3 — Threshold (deterministic, disjunctive OR).** Given an `ActiveFundSnapshot`, count the Top-5 constituents (by `weight_pct` descending, with the existing boundary-tie extension) whose `failure_reasons` contains any entry matching `broker_empty:*`. Let:
   - `count_broker_empty_top5` = number of Top-5 holdings with `broker_empty:*` in `failure_reasons`
   - `weight_broker_empty_top5` = sum of `weight_pct` over those holdings (percent units, 0–100)
   Gap fires when `count_broker_empty_top5 >= 2 OR weight_broker_empty_top5 >= 20.0`. Either disjunct alone is sufficient. Threshold constants live as module-level `Final` (e.g. `TOP_HOLDINGS_BROKER_THIN_COUNT_THRESHOLD = 2`, `TOP_HOLDINGS_BROKER_THIN_WEIGHT_PCT_THRESHOLD = 20.0`) in `thesis_evidence.py` so the magic numbers have names. Comparison is `>=` (boundary inclusive, mirroring `FOREIGN_HEAVY_THRESHOLD` precedent).

4. **AC4 — Active-fund only (no passive / ETF regression).** Rows whose snapshot is a `FundLevelSnapshot` (gold / bond / cn_etf / QDII sentinel) MUST NOT receive `top_holdings_broker_thin`. They have no per-constituent broker fetch path and the broker-empty concept does not apply by design (per CONTEXT.md "Passive ETF / tracked index"). Locked by a unit test that feeds a `FundLevelSnapshot` through `derive_thesis_from_evidence` and asserts the gap is absent.

5. **AC5 — Foreign-heavy short-circuit interaction.** Policy B rule 2.5 (foreign-heavy fund-level evidence substitute) operates on the same `ActiveFundSnapshot`. The new gap is emitted by `derive_thesis_from_evidence` BEFORE Policy B evaluates rule 2.5. For foreign-heavy rows, the gap is emitted normally (the per-holding CN broker pipeline did not cover HK/US tickers; that's exactly the case the gap warns about). The H3 partition still keeps the row publishable because Policy B 2.5 substitutes fund-level evidence for the dual-coverage gate — but the row carries the new gap visibly in `evidence_gaps`. (Note: this means foreign-heavy active funds may legitimately accumulate BOTH `top_holdings_broker_thin` AND the rule-2.5 acceptance — both are correct simultaneously; documented in the spec, not a contradiction.)

6. **AC6 — H3 invariant preserved.** Adding `top_holdings_broker_thin` to `evidence_gaps` MUST NOT route the row to `gapped_rows` in `_write_opportunity_outputs`'s H3 partition. The H3 partition predicate is `evidence_gaps == ()` (any non-empty gaps routes to failure section). To preserve publishability while still surfacing the gap, the new code is added to a **publishable-safe gap allowlist** (parallel to `EXPECTED_OMISSION_CODES` in `states.py::_partition_gaps`). The allowlist member is split out of `evidence_gaps` into a new `OpportunityRow.advisory_gaps: tuple[str, ...] = ()` field (or, equivalently, the existing `expected_omissions` field if its semantic can be widened — see Open Q below). The renderer reads from `advisory_gaps` for the §6 row. **Locked by AC test:** every row that carries `top_holdings_broker_thin` also satisfies `row in publishable_rows` of the H3 partition.

7. **AC7 — Memo §6 风险提示 emits a "证据缺口" bullet.** When ≥1 pick in the memo picks-table carries `top_holdings_broker_thin`, `_compose_risk_notes` (in `src/irc/commands/memo_cmd.py`) prepends a deterministic bullet of the form:
   ```
   证据缺口（Top-5 经纪覆盖不足）：以下候选标的的核心持仓中至少 2 只（或合计权重 ≥ 20%）缺少券商研报覆盖，证据强度弱于其余候选，触发条件成立时建议优先选择证据更完整的标的：<instrument_id1> <name_cn1>、<instrument_id2> <name_cn2>...
   ```
   Bullet is built deterministically (sorted by `instrument_id` ascending), is enclosed in `<!-- IRC_EVIDENCE_GAP_BEGIN -->` / `<!-- IRC_EVIDENCE_GAP_END -->` markers (matches existing IRC_*_BEGIN/END deterministic-marker pattern), and renders in §6 with the existing `_section(6, "风险提示", ...)` template. Synthesizer prompt is updated to leave the new marker block verbatim. Empty case (no qualifying picks) omits the bullet entirely (no marker block emitted).

8. **AC8 — Pick-ordering demotion in §5 picks table.** `_build_pick_rows` in `commands/memo_cmd.py` (or wherever pick ordering is established for §5) appends a tiebreaker: when two rows have equal upstream priority, the one carrying `top_holdings_broker_thin` sorts AFTER the one without. The primary sort key is unchanged; this is a **stable secondary key**. Locked by a unit test feeding two synthetic rows with identical upstream scores: the gap-bearing row appears later in the rendered picks-table.

9. **AC9 — Discipline report parity.** The existing cosmetic `(⚠️ broker_empty:<sym>)` suffix on per-constituent lines is **preserved verbatim** (do not regress that surface). Additionally, when a row carries `top_holdings_broker_thin`, the discipline_report.md per-fund header line (e.g. `**001877 宝盈国家安全沪港深股票A** ｜ small_watch ｜ ...`) is extended with a `｜ 证据缺口：核心持仓券商覆盖不足` suffix BEFORE the existing `｜ ...` opportunity reason. Append-only — does not perturb existing column positions.

10. **AC10 — SAME-3 invariant unaffected.** The new gap does NOT add to `thesis_evidence`; it does NOT change the citation set. The SAME-3 invariant (picks-table 证据 cell == evidence-pool refs == discipline `_render_section` refs) is locked unchanged. Test: feed shuffled input through all three paths for a row with `top_holdings_broker_thin` — the three citation sets remain byte-identical.

11. **AC11 — Citation gate v1 row-level dual-coverage unchanged.** The new gap is **advisory**, not structural — it does NOT change `OpportunityRow.thesis_evidence` shape, citation_id format (still `\[ref:[0-9a-f]{16}\]`), or the dual-leg `(data + information)` structural binding the citation audit gate enforces. `IRC_CITATION_ENFORCE_MODE=block` still passes for all publishable rows that previously passed (and still rejects any that previously failed). Locked by the existing `tests/integration/test_publishable_set_lockdown.py` continuing to pass.

12. **AC12 — Determinism / two-run byte equality.** Two consecutive `irc memo` runs over the same `opportunity_report.json` produce byte-identical `memo.md` files (including the new §6 bullet and the new picks-table ordering). Locked by extending the existing publishable-set lockdown baseline (item 008's two-run byte-equality assertion) — no new lockdown file; the existing one absorbs the change.

13. **AC13 — TDD coverage.** Each of AC1–AC12 has at least one corresponding test, named after the AC, written **before** the implementation. Test file `tests/opportunity/test_top_holdings_broker_thin.py` mirrors `src/irc/opportunity/thesis_evidence.py`. Pure-logic tests (gap-emission threshold, ordering tiebreaker, allowlist partition) require no mocks. The renderer test for AC7 uses a small in-memory `MemoInputs` fixture.

## Non-goals (explicitly out of scope)

- **NG1.** Mutating `thesis_state` based on broker coverage. (Future ADR if user wants it; flagged below.)
- **NG2.** Cascading the gap to `dca_state` (`slow_dca` / `pause_dca`). dca_state continues to derive solely from `opportunity_state` per existing logic. Deferred.
- **NG3.** Hard-blocking execution (gate to `do_not_buy`) on the new gap. The signal is advisory; the user retains discretion.
- **NG4.** Changing the `(⚠️ broker_empty:<sym>)` per-constituent suffix format (the existing cosmetic surface). Keep it as-is; we only ADD on top.
- **NG5.** Reworking Policy B rule precedence or adding a new Policy B rule. The new gap is emitted by `derive_thesis_from_evidence`, never by Policy B.
- **NG6.** Backfilling historical outputs (e.g. `outputs/2026-05-20/`). Behavior change applies to the next run only.
- **NG7.** Items 002 (holdings overlap panel) and 003 (QDII premium hard block). Sibling items; independent.

## Constraints

These are inherited from project CLAUDE.md, CONTEXT.md, ADRs, and global FP guidance. Any deviation is a stop-and-ask trigger for the orchestrator.

- **TDD (hard rule).** Red → green → refactor. Each AC test is written before the production code that makes it pass. Test file mirrors source (`thesis_evidence.py` → `tests/opportunity/test_top_holdings_broker_thin.py`).
- **Functional / immutable.** New helpers are pure. No mutation of `OpportunityRow` or `ActiveFundSnapshot` — frozen-dataclass `dataclasses.replace` or tuple concatenation only.
- **File size budget.** New code lives in helpers ≤ 20 lines; `thesis_evidence.py` already at < 460 lines — additions must keep it under the 200-line ideal per-function-cluster (extract helpers if needed). No file may exceed 200 lines after the change. (Today's `thesis_evidence.py` is over the 200-line ideal but that's pre-existing; do NOT enlarge the violation — extract.)
- **thesis_state setter invariant.** `thesis_state` is set ONLY inside `derive_thesis_from_evidence`. New gap emission is added to the same function's existing `gaps` return slot — no new function writes `thesis_state`. Policy B continues to never set `thesis_state`. Locked by the existing CONTEXT.md glossary entry; no ADR change.
- **Citation ID format.** Unchanged: `\[ref:[0-9a-f]{16}\]`. New gap does not add citations.
- **H3 universal gap-row invariant.** Preserved by routing `top_holdings_broker_thin` through the `advisory_gaps` field (or widened `expected_omissions`), NOT through `evidence_gaps`. See AC6.
- **SAME-3 invariant.** Preserved: the new gap does not change the citation set for any row. See AC10.
- **IRC_*_BEGIN/END deterministic markers.** New `IRC_EVIDENCE_GAP_BEGIN/END` block follows the existing pattern (`IRC_PICKS_TABLE_*`, `IRC_EXECUTION_LINES_*`, `IRC_MACRO_LINES_*`, `IRC_GOLD_EVIDENCE_*`). Synthesizer prompt updated to leave the block verbatim.
- **Secrets in `.env` only.** N/A for this item (no new I/O).
- **No new I/O.** Item 001 reads existing `failure_reasons` from cached snapshots; no new AkShare call, no new fetcher.

## Open questions resolved during brainstorming

Each Q is the question asked during brainstorming; A is the auto-accepted answer with rationale.

- **Q1: Demote `thesis_state`, add §6 risk row, or both?**
  **A:** Both surfaces (§6 row + pick-ordering demote), but NEITHER mutates `thesis_state`. The intervention is a new advisory `evidence_gaps` code (`top_holdings_broker_thin`) emitted by `derive_thesis_from_evidence`. The renderer reads it to (a) emit a §6 bullet (AC7) and (b) push the row to the tail of equal-priority pick groups (AC8). **Rationale:** preserves the load-bearing CONTEXT.md invariant *`thesis_state` set ONLY by `derive_thesis_from_evidence`*. Mutating `thesis_state` from "intact" → "evidence_insufficient" based on broker coverage would conflate two semantically distinct signals (thematic thesis vs. evidence completeness); the user's stated goal is "demote or flag" — the gap-code path achieves both without semantic confusion.

- **Q2: Threshold — N-of-5 count, weight-weighted, or both?**
  **A:** Disjunctive OR — `count_broker_empty_top5 >= 2` OR `weight_broker_empty_top5 >= 20.0`. **Rationale:** Master spec AC1 wording is "≥2 broker_empty in Top-5"; the weighted disjunct catches the edge case where a single 25%-weight Top-1 holding has no broker coverage (a 1-of-5 count miss that's clearly evidence-thin). Both branches are deterministic and easy to test independently. Constants are named `Final` so they're tunable in a follow-up without a code-shape change.

- **Q3: ETF / index-fund differential?**
  **A:** Gap fires for `ActiveFundSnapshot` only. `FundLevelSnapshot` rows (passive ETF, gold, bond, QDII sentinel) have no per-constituent broker fetch by design — they cannot trip the gate. **Rationale:** CONTEXT.md "Passive ETF / tracked index" explicitly says per-constituent qualitative evidence is *not required* for passive vehicles. Forcing the gap on them would generate false positives for every ETF.

- **Q4: Extend `derive_thesis_from_evidence` vs new setter?**
  **A:** Extend `derive_thesis_from_evidence` (active-fund branch). **Rationale:** The function already returns `(state, reason, evidence, gaps, analyses)` — `gaps` is the existing slot for row-level advisory codes. A new setter would (i) require a new ADR by the project's own rules, (ii) increase the surface area, (iii) violate the "Effects at edges, pure cores" principle. Extending the existing branch is a 1-helper-function addition; no ADR; no invariant change.

- **Q5: Cascade to `dca_state`?**
  **A:** No cascade in this item. `dca_state` continues to derive solely from `opportunity_state`. **Rationale:** Cascading would require touching the dca derivation table — explicitly out of "smallest surface" scope for Item 001. The §6 risk-row + pick-ordering demote already meet the user's stated goal ("demote or flag"). If a later observation shows the §6 row + ordering are insufficient and execution-blocking is needed, that becomes a follow-up item (and likely an ADR for dca_state semantics).

- **Q6 (orchestrator-flagged): Are any of these decisions ADR-level?**
  **A:** No. The chosen design is a strict superset of an existing pattern (gap-code emission inside `derive_thesis_from_evidence`, parallel to `missing_broker_coverage`). The only ADR-trigger would have been mutating `thesis_state` from a non-`derive_thesis_from_evidence` site — which the chosen design explicitly avoids. If a future iteration chooses to demote `thesis_state` directly (e.g. `intact` → `under_pressure` when broker-thin), THAT becomes a CONTEXT.md edit + a new ADR (proposed name: `0005-evidence-completeness-thesis-coupling.md`). Out of scope for Item 001.

- **Q7 (resolved inline during AC drafting): Where to store the advisory gap so H3 doesn't route the row to gapped_rows?**
  **A:** Add a new `OpportunityRow.advisory_gaps: tuple[str, ...] = ()` field, OR widen `expected_omissions` semantics. **Recommendation:** new dedicated field `advisory_gaps`. **Rationale:** `expected_omissions` is currently scoped to "structural non-features by design" (e.g. `constituent_not_applicable` for asset classes that have no constituents). `top_holdings_broker_thin` is not a structural omission — it's a real evidence gap that doesn't fail-close the row. A dedicated `advisory_gaps` field preserves the semantic distinction and keeps `_partition_gaps` simple. The H3 partition predicate stays `evidence_gaps == ()` unchanged. The renderer reads `advisory_gaps` for the §6 bullet. **Implementation note for the plan:** if the new field would push frozen-dataclass field count past a comfortable threshold or break too many test fixtures, the fallback is to use a dedicated `EXPECTED_OMISSION_CODES`-style allowlist and route through `expected_omissions` with a docstring update — both are acceptable; final pick during planning.
