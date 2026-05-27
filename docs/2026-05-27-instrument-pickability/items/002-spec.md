# Item 002 — Holdings overlap / concentration panel in §6

**Run**: `2026-05-27-instrument-pickability`
**Branch**: `autodev/instrument-pickability-feature`
**Mode**: backlog item (pure-analytics; no fetcher, no new I/O)

## Goal

When triggers eventually fire and the user picks 2–3 candidates from the §5 候选可执行 list, they should not unknowingly buy two or three funds that all express the same underlying bet (e.g. four "growth" funds whose Top-10 holdings are 60–80% the same CPO / 光模块 cluster — 300502 新易盛, 300308 中际旭创, 300394 天孚通信, 002384 东山精密 recurring across 008382 / 008555 / 018956 / 519770 in today's `outputs/2026-05-27/discipline_report.md`). This item adds a deterministic **holdings overlap / concentration panel** to memo §6 风险提示: every pair of active-fund picks whose weighted Top-10 holdings overlap ≥ 30% is surfaced once, sorted, with the overlap percentage and the shared symbols, so the operator can swap one of the pair out before executing. The signal is informational — it does NOT alter `opportunity_state`, `thesis_state`, `dca_action`, or pick ordering (per Open Q9 / Non-Goal).

## Acceptance criteria

Each criterion is independently verifiable by a single test (or a single grep over today's regenerated outputs).

1. **AC1 — Metric definition.** `weighted_overlap_pct(A, B) = Σ_{s ∈ topN(A) ∩ topN(B)} min(w_A[s], w_B[s])` where `w_*[s]` is `ConstituentAnalysis.weight_pct` (percent units, 0–100), `topN` is the Top-`CONCENTRATION_TOP_N` constituents of each `ActiveFundSnapshot` ranked by `weight_pct` descending with `symbol` ascending tiebreaker. Result is in percent units, range `[0.0, min(Σw_A_topN, Σw_B_topN)]`. The metric is symmetric: `weighted_overlap_pct(A, B) == weighted_overlap_pct(B, A)`. **Cardinality clarification (grill Q4)**: when `len(A.constituent_analyses) < CONCENTRATION_TOP_N`, `topN(A)` is `A.constituent_analyses` after the rank sort with no padding; symmetry is preserved because the intersection is computed over the same identity set regardless of either fund's cardinality. Test: hand-rolled fixtures with known intersections + weights produce the expected float (to 2-dp tolerance), including one fixture with `len(A.constituent_analyses) == 4`.

2. **AC2 — `CONCENTRATION_TOP_N` constant.** Module-level `Final` at `src/irc/memo/concentration.py::CONCENTRATION_TOP_N = 10`. Hardcoded by design (no YAML / env-var knob in V1; mirrors `FOREIGN_HEAVY_THRESHOLD` precedent — operators tuning thresholds at runtime would silently weaken the audit trail). N=10 over N=5 chosen because the CPO cluster in the 2026-05-27 data extends through weight rank 6–8 in several funds; cutting at 5 truncates funds like 008382 whose rank 4 is 06869 长飞光纤光缆 at 8.44% (part of the same thesis).

3. **AC3 — `CONCENTRATION_OVERLAP_PCT_THRESHOLD` constant.** Module-level `Final` at `src/irc/memo/concentration.py::CONCENTRATION_OVERLAP_PCT_THRESHOLD: Final[float] = 30.0  # percent units (0–100), matches weight_pct unit; NOT a fraction`. Comparison is `>=` (boundary inclusive, mirrors `FOREIGN_HEAVY_THRESHOLD = 0.50` `>=` precedent). A pair sitting exactly at 30.0% is surfaced. 30.0 chosen because the actual 2026-05-27 CPO cluster shows pairwise overlaps in the 50–70% range and 30% leaves room for "tilted-toward-same-theme-but-different-managers" cases. **Unit clarification (grill Q5)**: the metric is in percent units (matching `weight_pct`'s unit per ADR 0002 §4); the threshold IS NOT in fraction units like `qdii_max_premium_pct` (0.05).

4. **AC4 — Symmetric pair generation.** `compute_concentration_pairs(active_picks: Sequence[OpportunityRow]) -> tuple[ConcentrationPair, ...]` enumerates unordered pairs `(row_i, row_j)` with `i < j` (after rows sorted by `instrument_id` ASC — this is **internal canonicalization** to guarantee each pair surfaces exactly once; not an observable render order — see AC8 for render order); for each pair, computes `weighted_overlap_pct`; emits a `ConcentrationPair` ONLY when the value `>= CONCENTRATION_OVERLAP_PCT_THRESHOLD`. Each pair appears exactly once (never `(A,B)` AND `(B,A)`). Test: feed a list of 4 funds where 3 pairs cross the threshold; the result has exactly 3 entries.

5. **AC5 — `ConcentrationPair` shape.** Frozen dataclass at `src/irc/memo/concentration.py::ConcentrationPair`:
   ```python
   @dataclass(frozen=True)
   class ConcentrationPair:
       instrument_id_a: str        # alphabetically smaller of the two
       instrument_id_b: str        # alphabetically larger
       name_cn_a: str
       name_cn_b: str
       overlap_pct: float          # percent units, round(weighted_overlap_pct, 1) — set ONCE at construction
       shared_symbols: tuple[str, ...]  # sorted ascending, symbol strings only
   ```
   `instrument_id_a < instrument_id_b` (strict) is a class-level invariant — the factory function sorts the two IDs before assignment. `overlap_pct` is set ONCE at construction time as `round(weighted_overlap_pct(A,B), 1)` — never re-rounded downstream (grill Q6: pins determinism by construction, not by render-time discipline). Locked by a test that passes the two rows in BOTH orderings and asserts byte-identical pairs result.

6. **AC6 — Scope: active fund only.** Only rows whose `OpportunityRow.constituent_analyses != ()` AND whose snapshot was an `ActiveFundSnapshot` participate. The function reads `constituent_analyses` directly off `OpportunityRow` (already threaded by item 003); no isinstance check on a separate `ActiveFundSnapshot` is needed. Rows with empty `constituent_analyses` (gold / bond / cn_etf / QDII sentinel passing through `FundLevelSnapshot` path, or any malformed row) are skipped silently — they cannot participate in a holdings-level overlap. Test: feed a mixed list of 2 active + 2 passive rows; result contains 0 or 1 pair (only the active-active pair is even eligible).

7. **AC7 — Pick scope (not full publishable universe).** The §6 panel computes pairs ONLY among rows that appear in `pick_rows` (the memo §5 picks-table population — populated from `trade_plan.yaml` matched against `opportunity_report.json` in `_build_pick_rows`). The watchlist may have 30+ funds; flagging every overlap-pair across the watchlist would bury the actionable signal. Implementation: `_compose_concentration_lines(pick_rows: list[PickRow], op_rows_by_id: dict[str, OpportunityRow]) -> tuple[str, ...]` is the renderer hook in `commands/memo_cmd.py` — mirrors `_compose_evidence_gap_lines(pick_rows)` from item 001. The helper looks up each `PickRow.instrument_id` in a pre-built `dict[str, OpportunityRow]` so it can reach `constituent_analyses`. **Origin of the lookup map (grill Q11)**: `op_rows_by_id` is constructed at the hook call-site in `memo_cmd.py` as `{r.instrument_id: r for r in opportunity_rows}` from the `opportunity_rows` already in scope (NOT built inside `_compose_concentration_lines`, NOT cached on a module-level global, NOT threaded onto `PickRow` which would break the item 003 column lock per NG3). FP guidance: dependencies visible in the function signature; the helper receives the dict explicitly.

8. **AC8 — Deterministic pair ordering.** Pairs in the rendered output sorted by `(round(overlap_pct, 1) DESC, instrument_id_a ASC, instrument_id_b ASC)`. The rounding-then-sort sequence (NOT the inverse) ensures stability across float-equal pairs. Test: two consecutive `irc memo` runs over the same `opportunity_report.json` produce byte-identical `memo.md`, including the §6 concentration panel ordering (extension of item 008 lockdown).

9. **AC9 — Memo §6 风险提示 emits a "持仓集中度" bullet block.** When ≥1 qualifying pair exists, `_compose_concentration_lines(pick_rows, op_rows_by_id)` returns a deterministic line tuple wrapped in `<!-- IRC_CONCENTRATION_BEGIN -->` / `<!-- IRC_CONCENTRATION_END -->` markers (matches existing `IRC_*_BEGIN/END` deterministic-marker pattern from item 001). The marker constants `CONCENTRATION_MARKER_BEGIN` / `CONCENTRATION_MARKER_END` are defined at module-top in `src/irc/memo/concentration.py` (producing-module pattern — mirrors `macro_pillar.py`'s `MACRO_SECTION_MARKER_*`, NOT the `template.py` pattern which is reserved for skeleton-level markers). Body format:
   ```
   持仓集中度（Top-10 加权重合 ≥ 30%）：以下候选标的实质表达相近的底层敞口，触发条件成立后只应择一执行；同时持有将放大单一主题回撤风险。
   - 008382 融通产业趋势股票 ↔ 008555 华商龙头优势混合：加权重合 64.3%，共同持仓 300502/300308/300394/002384/06869（5 只）
   - 008382 融通产业趋势股票 ↔ 018956 中航机遇领航混合发起A：加权重合 58.1%，共同持仓 300502/300308/300394/002384（4 只）
   ```
   - First line is the header (carries the threshold + intent verbatim — locked across runs).
   - Each pair line: `- {id_a} {name_a} ↔ {id_b} {name_b}：加权重合 {overlap_pct:.1f}%，共同持仓 {sym_list}（{n} 只）`.
   - `sym_list` joins `shared_symbols` with `/`, capped at 5 symbols (sorted ASC by AC5) followed by `...` when more than 5 exist.
   - Empty result (zero qualifying pairs) → no marker block emitted, no concentration lines in §6 at all (mirrors item 001 empty case).

10. **AC10 — Synthesizer marker passthrough.** The LLM synthesizer prompt (`src/irc/memo/synthesizer.py`) is updated to leave `IRC_CONCENTRATION_BEGIN/END` block verbatim. ~~Same treatment as the other 8 existing marker pairs — `IRC_PICKS_TABLE_*`, `IRC_EVIDENCE_GAP_*`, `IRC_EXECUTION_LINES_*`, `IRC_MACRO_LINES_*`, `IRC_GOLD_EVIDENCE_*`, `IRC_FX_QDII_*`, `IRC_ROLE_BUCKET_*`, `IRC_EXECUTION_DRIFT_*`.~~ — corrected by grill Q1: **only 5 existing marker pairs exist** in src/ (`IRC_PICKS_TABLE_*`, `IRC_EVIDENCE_GAP_*`, `IRC_EXECUTION_LINES_*`, `IRC_MACRO_LINES_*`, `IRC_GOLD_EVIDENCE_*` — verified via `grep -rno "IRC_[A-Z_]*_BEGIN" src/`). The claimed `IRC_FX_QDII_*`, `IRC_ROLE_BUCKET_*`, `IRC_EXECUTION_DRIFT_*` are non-existent; spec was wrong. Concentration becomes the 6th marker pair. The synthesizer extension mirrors the existing `if "<!-- IRC_EVIDENCE_GAP_BEGIN -->" in skeleton:` block (lines 135-140 of synthesizer.py): an additional `if "<!-- IRC_CONCENTRATION_BEGIN -->" in skeleton:` clause appends a Chinese instruction to `locked_section_lines`. ~~Audit gate (`memo/auditor.py`) recognises the new marker pair so a missing/mismatched block fails the audit.~~ — corrected by grill Q2: `memo/auditor.py` is an LLM content reviewer that parses 审核通过/审核未通过 verdict tokens; it has NO structural marker awareness, NO `IRC_*` reference (verified via `grep -n "IRC_" src/irc/memo/auditor.py` returns zero matches). The actual lock mechanism is (a) the synthesizer prompt instruction telling the LLM to preserve the block verbatim, (b) the two-run byte-equality coverage in the existing publishable-set lockdown (AC13). Test: a synthesizer round-trip with the new block emits byte-identical content between deterministic input and output.

11. **AC11 — No row-level state change.** `OpportunityRow.advisory_gaps` is **NOT** extended with a new code. `OpportunityRow.constituent_analyses`, `evidence_gaps`, `expected_omissions`, `thesis_state`, `opportunity_state`, `dca_action`, `risk_action` are all unchanged. The concentration analytic is a memo-time pure transform; it never round-trips through `opportunity_report.json` or `thesis_cards.yaml`. Locked by: (a) the existing item 008 lockdown continuing to pass with byte equality across the JSON/YAML artifacts unchanged, (b) a unit test that asserts `compute_concentration_pairs` is a free function with no `OpportunityRow` mutation in scope.

12. **AC12 — No pick-ordering interaction.** `_build_pick_rows` ordering is unchanged. The item 001 stable partition (advisory-gap-bearing rows move to the tail) still applies; concentration does NOT layer a second partition. **Rationale:** auto-demoting one of an overlapping pair would presume which of the pair is "correct" — a judgement call the §6 panel deliberately preserves for the operator. Test: a pick list with 2 mutually-overlapping rows emits §5 in trade-plan iteration order (item 001 partition only).

13. **AC13 — Determinism / two-run byte equality.** Two consecutive `irc memo` runs over identical inputs produce byte-identical `memo.md`. The only nondeterminism sources are frozenset/set iteration (pinned by sorting in AC4 + AC5) and float comparison (pinned by `round(x, 1)` at construction per AC5, then sort-by-rounded-value at render per AC8). **Lockdown strategy (grill Q12)**: extend the existing publishable-set lockdown baseline at `tests/integration/test_publishable_set_lockdown.py`. The existing `memo.md` two-run byte-equality assertion (item 008's pipeline-level invariant covering all 5 canonical artifacts) absorbs the change automatically — no new lockdown file, no new fixture migration. The lockdown gate becomes the regression gate for AC13.

14. **AC14 — H3 / SAME-3 / citation gate v1 invariants preserved.** The concentration analytic does NOT touch `thesis_evidence`, citation_ids, the dual-leg structural binding, or the H3 partition predicate (`evidence_gaps == ()`). No new `[ref:...]` markers are emitted in the concentration block (the analytic is operator-facing prose over symbols, not citation-bearing prose). The picks-table 证据 cell / evidence-pool refs / discipline `_render_section` refs are byte-unchanged. Locked by `tests/integration/test_publishable_set_lockdown.py` continuing to pass.

15. **AC15 — TDD coverage.** Each of AC1–AC14 has at least one corresponding test, named after the AC, written **before** the implementation. Test file `tests/memo/test_concentration.py` mirrors `src/irc/memo/concentration.py`. Pure-logic tests (metric, pair generation, ordering, threshold boundary) require no mocks. The renderer test (AC9) uses a small in-memory fixture: 4 synthetic `OpportunityRow` + a `PickRow` list, expected `_compose_concentration_lines` output asserted as a tuple of strings byte-for-byte.

## Non-goals (explicitly out of scope)

- **NG1.** Mutating `opportunity_state`, `thesis_state`, `dca_action`, `risk_action`, or any other row-level state based on concentration. The signal is informational.
- **NG2.** Adding a new `advisory_gaps` code (e.g. `peer_holdings_overlap`). Concentration is a PAIR-level signal; `advisory_gaps` is ROW-level. Forcing it into a row-level field requires either (a) flat codes that lose the counterparty info, or (b) embedding instrument_ids into the code string (`peer_holdings_overlap:008382:518880` — anti-pattern; breaks `frozenset[str]` allowlist semantic). Memo-only surfacing keeps `OpportunityRow` shape unchanged and avoids touching the item 008 lockdown fixture.
- **NG3.** Per-row §5 picks-table note (e.g. `集中度:与008382重合67%`). Would require a new picks-table column (breaks the item 003 column lock — `tranche_cap_pct` / `trigger_status` mirror), duplicates info already in §6, and structurally awkward (one row may overlap with multiple peers).
- **NG4.** Transitive clustering (A-B + B-C → cluster {A,B,C}). Pairs preserve asymmetric structure that clustering loses (A-B 35%, B-C 35%, A-C 15% — A and C are NOT the same bet). The pair list is a strict superset of the data needed to compute clusters later.
- **NG5.** Passive ETF / index-tracker overlap. Two QDII proxies tracking the same Nasdaq-100 ARE the same bet, but the signal lives in `tracked_index` metadata at a different code path — it's an **index identity check** (two CSI 300 ETFs are 100% overlapping by construction), not a holdings-overlap signal. The operator already knows the tracked-index match from `name_cn`. Item 003 covers QDII via premium/discount. Defer to F2 future iteration (grill Q8 confirmed). The spec's `OpportunityRow.constituent_analyses != ()` predicate naturally excludes passive ETFs because `build_snapshot` dispatch routes non-`active_fund` cases to `FundLevelSnapshot` which has no `constituent_analyses` field (per CONTEXT.md "Fund-level dispatch").
- **NG6.** Cascading concentration to allocation / `trade_plan.yaml` (e.g. reduce target_weight when overlap is high). Memo-time renderer only; allocation engine is a separate concern with its own constraint system.
- **NG7.** Across-watchlist concentration. Restricted to picks (AC7).
- **NG8.** Backfilling historical outputs (e.g. `outputs/2026-05-20/`). Behavior change applies to the next run only.
- **NG9.** Items 001 (broker_empty advisory) and 003 (QDII premium hard block). Sibling items; independent.

## Constraints

These are inherited from project CLAUDE.md, CONTEXT.md, ADRs, and global FP guidance. Any deviation is a stop-and-ask trigger for the orchestrator.

- **TDD (hard rule).** Red → green → refactor. Each AC test is written before the production code that makes it pass. Test file mirrors source (`src/irc/memo/concentration.py` → `tests/memo/test_concentration.py`).
- **Functional / immutable.** New module is pure. No mutation of `OpportunityRow`, `PickRow`, `ConstituentAnalysis`, or `ActiveFundSnapshot` — frozen-dataclass + tuple construction only. No module-level mutable state.
- **File size budget.** New module `src/irc/memo/concentration.py` < 200 lines. Helpers ≤ 20 lines each (extract rather than nest > 3 levels). `commands/memo_cmd.py` is already over the 200-line ideal but pre-existing — additions follow item 001's pattern of a 10-15-line `_compose_concentration_lines` helper paralleling `_compose_evidence_gap_lines`; do NOT enlarge the existing violation.
- **Pure cores, effects at edges.** No I/O in `concentration.py` — it reads `OpportunityRow.constituent_analyses` which is already in-memory at memo render time (loaded by `_read_opportunity_for_memo` / `_reconstruct_opportunity_rows`). No AkShare call, no LLM call, no disk read.
- **Module import contract (grill Q10).** `src/irc/memo/concentration.py` imports from `irc.opportunity.types` only (one-way). No imports from `irc.memo.*` siblings; no imports from `irc.commands.*`. Mirrors `aliases.py` tier-1 import contract per CONTEXT.md "Renderer tier-1 import contract". No cycle introduced. The renderer hook `_compose_concentration_lines` lives in `commands/memo_cmd.py` (not `concentration.py`) — it's the dependency-injection edge that converts `(pick_rows, op_rows_by_id)` into the marker-wrapped string tuple by calling `compute_concentration_pairs`.
- **thesis_state setter invariant.** `thesis_state` is set ONLY inside `derive_thesis_from_evidence`. Concentration analytic does NOT touch `thesis_state` (and is not even on the opportunity stage code path — purely a memo renderer). Preserved automatically.
- **Citation ID format.** Unchanged: `\[ref:[0-9a-f]{16}\]`. The concentration block emits no `[ref:...]` markers — it's operator-facing prose over symbols, not evidence-citing prose. Item 009 citation audit gate sees no new shapes.
- **H3 universal gap-row invariant.** Preserved — concentration does NOT touch `evidence_gaps`, the H3 partition predicate, or `gapped_rows`.
- **SAME-3 invariant.** Preserved — concentration does NOT change `thesis_evidence` or the 3-way citation-set equality across picks-table / evidence-pool / discipline.
- **IRC_*_BEGIN/END deterministic markers.** New `IRC_CONCENTRATION_BEGIN/END` block follows the existing pattern. Synthesizer prompt updated to leave the block verbatim; audit gate (`memo/auditor.py`) extended to recognise the new pair (mirrors how item 001 added `IRC_EVIDENCE_GAP_*`).
- **Secrets in `.env` only.** N/A for this item (no new I/O).
- **No new I/O.** Reads cached `OpportunityRow.constituent_analyses`; no new AkShare call, no new fetcher, no new disk read.
- **Determinism.** AC8 + AC13. The only nondeterminism sources are frozenset/set iteration (pinned by AC4 `i < j` after `instrument_id` ASC sort + AC5 `shared_symbols` sorted ASC) and float comparison (pinned by `round(overlap_pct, 1)` before both sort and render).

## Open questions resolved during brainstorming

Each Q is the question asked during brainstorming; A is the auto-accepted answer with rationale.

- **Q1: Metric — Jaccard, asymmetric, or symmetric weighted overlap?**
  **A:** Symmetric weighted overlap: `Σ min(w_A[s], w_B[s])` over shared symbols. **Rationale:** captures both shared identity AND shared bet size. Jaccard (set-only) ignores weight — a fund with 5% in 300502 vs one with 0.5% are not the "same bet". Asymmetric (% of A covered by B) introduces ordering and is harder to read. `min(w_A, w_B)` is the canonical economic interpretation: "if you bought equal $ of both, how much of your dollar lands on the same name". Matches academic portfolio-overlap literature (Cremers & Petajisto active share).

- **Q2: Top-N — Top-5 (parity with item 001) or Top-10 (richer)?**
  **A:** Top-10. **Rationale:** the 2026-05-27 CPO cluster extends through weight rank 6–8 in several funds; Top-5 truncates funds like 008382 whose rank 4 is 06869 长飞光纤光缆 at 8.44% (part of the same thesis). Item 001 used Top-5 because broker coverage is row-blocking advisory and the count-of-2 threshold lives in Top-5 land; concentration is informational and benefits from more data. `CONCENTRATION_TOP_N = 10` exposed as `Final` constant.

- **Q3: Threshold — 30%, 40%, or operator-configurable?**
  **A:** 30.0% hardcoded `Final` (no YAML knob in V1). **Rationale:** literature rule-of-thumb is 30–40% overlap = "substantially the same bet"; the actual 2026-05-27 CPO cluster pair overlaps are in the 50–70% range, so 30% catches them clearly while leaving room for "tilted-toward-same-theme-but-different-managers" cases. Hardcoded per `FOREIGN_HEAVY_THRESHOLD` precedent — operators tuning thresholds at runtime would silently weaken the audit trail. Future YAML promotion follows the same pattern as `IRC_CACHE_FRESHNESS_DAYS` without an API change.

- **Q4: Pairs vs transitive clusters?**
  **A:** Pairs only. **Rationale:** transitive clustering hides asymmetric structure (A-B 35%, B-C 35%, A-C 15% — clustering wrongly says {A,B,C} are the same). The user's goal is "don't unknowingly buy 3 funds expressing the same thesis"; pair-by-pair is the actionable view. Each pair stands or falls on its own evidence. The pair list is a strict superset of the data needed to compute clusters if a future need arises.

- **Q5: Scope — active fund only, or also passive QDII / index trackers?**
  **A:** Active-fund only (`OpportunityRow.constituent_analyses != ()`). **Rationale:** `FundLevelSnapshot` (passive ETF / gold / bond / QDII sentinel) has NO `constituent_analyses` — the holdings-level concentration signal is structurally undefined. Index-tracker overlap (two QDII proxies on the same Nasdaq-100) lives in `tracked_index` metadata at a different code path; out of scope per master spec and orthogonal to item 003's QDII premium signal.

- **Q6: Pick scope vs full publishable universe?**
  **A:** Picks only (AC7). **Rationale:** the user's stated goal is "when they pick 2–3 candidates… they should not unknowingly buy 3 funds". The watchlist may have 30+ funds; flagging every overlap-pair across the watchlist would bury the actionable signal at the operator decision surface.

- **Q7: Output surface — §6 panel only, per-row §5 note, or both?**
  **A:** §6 panel only. **Rationale:** concentration is a pair-level signal — putting it on a single row's cell is structurally awkward (one row may overlap with multiple peers). A new §5 column would break the item 003 column lock. The §6 panel naturally enumerates pairs once with both fund names; the user can cross-reference without column churn. Documented as NG3.

- **Q8: Interaction with `advisory_gaps` from item 001 — new code or memo-only?**
  **A:** Memo-only surfacing. NO new advisory gap code. **Rationale:** `advisory_gaps` is ROW-level; concentration is PAIR-level. Forcing it into a row-level field requires either flat codes that lose counterparty info OR embedding instrument_ids into the code string (`peer_holdings_overlap:008382:518880` — anti-pattern, breaks `frozenset[str]` allowlist semantic, doesn't survive serialisation cleanly). Memo-only keeps `OpportunityRow` shape unchanged and avoids touching the item 008 lockdown fixture (`opportunity_report.json` / `thesis_cards.yaml` artifacts byte-unchanged).

- **Q9: Does this analytic interact with `_apply_advisory_partition` from item 001?**
  **A:** No interaction. The item 001 partition still demotes individual rows; concentration does NOT layer a second partition or change pick ordering. **Rationale:** auto-demoting one of an overlapping pair presumes which is "correct" — a judgement call the §6 panel deliberately preserves for the operator. Documented as AC12 + NG1.

- **Q10: Module location — `src/irc/opportunity/` (parallel to `advisory_gaps.py`) or `src/irc/memo/`?**
  **A:** `src/irc/memo/concentration.py`. **Rationale:** the analytic is a renderer concern with no `OpportunityRow` shape change (Q8 outcome). Parallels `src/irc/memo/aliases.py`. Item 001's `advisory_gaps.py` lives in `opportunity/` because it produces row-level state that gets serialised; this module produces no row-level state.

- **Q11: Determinism — what are the nondeterminism sources, and how are they pinned?**
  **A:** Two sources: (a) frozenset / set iteration over symbol intersections — pinned by sorting `shared_symbols` ASC in `ConcentrationPair` (AC5) and iterating in sorted order during render (AC9); (b) float comparison ordering — pinned by `round(overlap_pct, 1)` BEFORE sorting AND before rendering (AC8). Rounding-then-sort (not the inverse) ensures stability across float-equal pairs.

- **Q12: ADR needed?**
  **A:** No. Three-of-three test (hard-to-reverse / surprising / real-tradeoff):
  - Hard to reverse: medium-low — a memo-only pure helper is reversible; no frozen-dataclass change. (Pass.)
  - Surprising without context: low — parallels existing item 001 marker block pattern; concentration is a well-known analytic. (Pass.)
  - Real tradeoff: medium — pair-vs-cluster, threshold value. Both documented in spec Open Questions. (Pass.)
  Two of three rate as "light"; one ADR-trigger isn't enough by the project's three-of-three rule. CONTEXT.md gains a short glossary entry for `IRC_CONCENTRATION_*` marker + `CONCENTRATION_*_THRESHOLD` constants in the "Renderers + alias-builder" section, paralleling how `IRC_EVIDENCE_GAP_*` was documented in item 001 without an ADR for the marker itself.

- **Q13: ADR-level open questions flagged?**
  **A:** None for V1. Two future-iteration questions are noted but DEFERRED:
  - **(F1)** Should YAML-configurable threshold replace the hardcoded `Final` (operator tuning)? — same pattern as `IRC_CACHE_FRESHNESS_DAYS`; defer until operators ask.
  - **(F2)** Should the analytic extend to passive index-tracker overlap (two QDII on the same index)? — requires a `tracked_index` metadata path that doesn't exist in V1; orthogonal to item 003's QDII premium signal. Defer.
  Neither is blocking; both can become follow-up items without code-shape churn.

## Resolved decisions

Brainstorming pass run autonomously on 2026-05-27 by autodev per orchestrator's "auto-accept best answers" directive. All Open Questions Q1–Q13 received the recommended answer. Recommendations stress-tested against: `CONTEXT.md` (advisory_gaps entry, H3 invariant, SAME-3 invariant, renderer dependency direction, IRC_*_BEGIN/END marker family), `docs/adr/0005-advisory-gaps-field.md` (the row-level vs memo-only distinction), `src/irc/opportunity/types.py` (frozen `OpportunityRow.constituent_analyses` already threaded by item 003 — no shape change needed), `src/irc/opportunity/advisory_gaps.py` (item 001's pattern for `Final` thresholds + Top-N selection), `src/irc/commands/memo_cmd.py` lines 240–261 (the `_compose_evidence_gap_lines` precedent for marker-wrapped §6 lines), `src/irc/memo/picks_table.py` (the column lock that NG3 protects), and `outputs/2026-05-27/discipline_report.md` lines 99–138 (the actual CPO cluster the analytic must detect).

### Grill pass (2026-05-27)

Second autonomous pass via `grill-with-docs` skill (auto-accept recommended answers; no user in loop). 13 questions resolved against CONTEXT.md, ADR 0005, and src/ source-of-truth code.

- **Q1: Spec AC10 claims 8 existing marker pairs. Is that factual?**
  **A:** No. `grep -rno "IRC_[A-Z_]*_BEGIN" src/` returns exactly **5** existing marker pairs: `IRC_EXECUTION_LINES_*`, `IRC_PICKS_TABLE_*`, `IRC_EVIDENCE_GAP_*`, `IRC_MACRO_LINES_*`, `IRC_GOLD_EVIDENCE_*`. The spec's claimed `IRC_FX_QDII_*`, `IRC_ROLE_BUCKET_*`, `IRC_EXECUTION_DRIFT_*` do not exist anywhere in the repo. Spec corrected via strikethrough on AC10.
  **Rationale:** Plan-stage engineer would have hit the non-existent imports and stalled. Fact-checking earns now is cheap.
  **Doc impact:** spec strikethrough on AC10; no CONTEXT.md change needed (existing markers already covered in renderers section).

- **Q2: Spec AC10 claims `memo/auditor.py` recognises markers structurally. Is that true?**
  **A:** No. `auditor.py` is an LLM content reviewer that parses 审核通过 / 审核未通过 verdict tokens (lines 38–44); `grep -n "IRC_" src/irc/memo/auditor.py` returns zero matches. Item 001's `IRC_EVIDENCE_GAP_*` likewise didn't extend the auditor. The actual lockdown mechanism is (a) the synthesizer prompt extension, (b) the publishable-set lockdown two-run byte equality. AC10 strikethrough corrects this.
  **Rationale:** Plan-stage engineer would have searched for an "auditor marker registry" that doesn't exist.
  **Doc impact:** spec strikethrough on AC10; no auditor change needed in V1.

- **Q3: Is AC4 (`i < j` after `instrument_id` sort) in conflict with AC8 (render order `overlap_pct DESC`)?**
  **A:** No conflict. AC4's `i < j` sort is internal canonicalization — ensures each unordered pair surfaces exactly once. AC8's three-key sort is the observable render order. Both can coexist. Added one-line clarification to AC4.
  **Rationale:** Distinguishes "deduplication invariant" from "render order" — both load-bearing.
  **Doc impact:** spec AC4 clarification only.

- **Q4: How does the metric handle a fund with fewer than 10 valid holdings?**
  **A:** `topN(A) = A.constituent_analyses` after the rank sort with no padding when `len(A.constituent_analyses) < CONCENTRATION_TOP_N`. Symmetry holds because intersection is over the same identity set regardless of cardinality asymmetry. Added an explicit AC1 sub-clause + test requirement.
  **Rationale:** AkShare returns 10 by default but corrupted/partial fixtures can hit this branch.
  **Doc impact:** spec AC1 clarification; CONTEXT.md's `weighted_overlap_pct` entry mentions the cardinality rule.

- **Q5: Is `CONCENTRATION_OVERLAP_PCT_THRESHOLD = 30.0` in percent units or fraction units?**
  **A:** Percent units (0–100), matches `weight_pct`'s unit per ADR 0002 §4. NOT a fraction like `qdii_max_premium_pct = 0.05`. Added inline unit comment on AC3.
  **Rationale:** Two precedent constants (`FOREIGN_HEAVY_THRESHOLD = 0.50` is fraction; `qdii_max_premium_pct = 0.05` is fraction; `CONCENTRATION_OVERLAP_PCT_THRESHOLD = 30.0` is percent units) — easy unit confusion at plan stage without explicit doc.
  **Doc impact:** spec AC3 unit clarification; CONTEXT.md's metric entry pins the unit.

- **Q6: When is `overlap_pct` rounded — at construction or at render?**
  **A:** At construction (inside `ConcentrationPair` factory). Pins determinism by construction, not by render-time discipline. Updated AC5: "set ONCE at construction; never re-rounded downstream."
  **Rationale:** Render-time-only rounding is brittle to future renderer additions.
  **Doc impact:** spec AC5 clarification; CONTEXT.md's `ConcentrationPair` entry documents the once-at-construction rule.

- **Q7: Pair vs cluster — is 6 lines for a 4-pick cluster (`C(4,2)`) noisy?**
  **A:** Keep pairs (spec's original Q4 answer is correct). 6 lines for 4 picks is operator-readable; clustering hides asymmetric structure (A↔B 64%, B↔C 30% does NOT imply A↔C 30%). No change required.
  **Rationale:** Stress-tested against the actual 2026-05-27 CPO cluster of 4 picks; emits ≤6 lines, fits the §6 risk-notes section without sprawl.
  **Doc impact:** none; existing spec answer preserved.

- **Q8: Should the analytic cover passive ETFs that have known holdings via `lookthrough_target`?**
  **A:** No, V1 is active-fund-only per spec's Q5. Passive ETF overlap is an `tracked_index` identity check (two CSI 300 ETFs are 100% by construction; operator already knows from `name_cn`) — a different signal. Strengthened NG5 rationale with this distinction. Defer to F2 future iteration.
  **Rationale:** CONTEXT.md "Passive ETF / tracked index" explicitly excludes them from drill-through; the `OpportunityRow.constituent_analyses != ()` predicate naturally excludes them because `build_snapshot` routes non-`active_fund` cases to `FundLevelSnapshot` (no `constituent_analyses` field).
  **Doc impact:** spec NG5 strengthening; no scope change.

- **Q9: Where do `IRC_CONCENTRATION_*` marker constants live?**
  **A:** Module-top in `src/irc/memo/concentration.py` — producing-module pattern, mirrors `macro_pillar.py`'s `MACRO_SECTION_MARKER_*`. NOT in `template.py` (which is reserved for skeleton-level markers). Updated AC9.
  **Rationale:** Concentration is a §6 sub-block produced at memo-cmd time, not a skeleton-level section like §5 picks or §7 execution.
  **Doc impact:** spec AC9 location clarification; CONTEXT.md's marker entry documents the location.

- **Q10: Is `aliases.py` the right shape mirror for `concentration.py`?**
  **A:** Yes. Both are pure modules: tuple-in / frozen-dataclass-tuple-out, no I/O, single `irc.opportunity.types` import. Added an explicit Constraint about the import contract.
  **Rationale:** Tier-1 import contract is load-bearing for renderer module independence (no cycles).
  **Doc impact:** spec Constraints section adds the import-contract bullet; CONTEXT.md's tier-1 contract entry mentions `concentration.py` joining the list.

- **Q11: Where does `op_rows_by_id` come from in `_compose_concentration_lines(pick_rows, op_rows_by_id)`?**
  **A:** Built once at the hook call-site in `memo_cmd.py` as `{r.instrument_id: r for r in opportunity_rows}` from `opportunity_rows` already in scope. NOT inside the pure helper, NOT on a module-level global, NOT threaded onto `PickRow` (which would break the item 003 column lock per NG3). Added FP-explicit clarification to AC7.
  **Rationale:** "Dependencies visible in the function signature" per CLAUDE.md FP guidance.
  **Doc impact:** spec AC7 clarification.

- **Q12: Is "extend existing publishable-set lockdown" the right two-run-byte-equality strategy?**
  **A:** Yes. Item 008's pipeline-level invariant covers all 5 canonical artifacts including `memo.md`; the new `IRC_CONCENTRATION_*` block is byte-stable IFF the two-run identical-inputs invariant from item 008 covers it. No new fixture, no new test file. Clarified AC13.
  **Rationale:** Avoid lockdown-fixture sprawl; the existing baseline is the single source of regression truth.
  **Doc impact:** spec AC13 clarification.

- **Q13: Is an ADR warranted?**
  **A:** No. Three-of-three test: (1) hard-to-reverse — LOW (memo-time pure helper, no on-disk state, fully reversible); (2) surprising-without-context — LOW (parallels item 001's marker pattern; concentration is a well-known analytic); (3) real-tradeoff — MEDIUM (pair-vs-cluster + threshold + Top-N all documented in spec Q1–Q4 + Q6). Two of three are LOW; ADR threshold is "three of three." CONTEXT.md gets glossary entries; no ADR.
  **Rationale:** Item 001 (the very-similar `IRC_EVIDENCE_GAP_*` marker addition) also got CONTEXT.md-only treatment; only the row-level `advisory_gaps` shape change earned ADR 0005.
  **Doc impact:** CONTEXT.md entries added (`IRC_CONCENTRATION_BEGIN/END` marker, `weighted_overlap_pct` metric, `ConcentrationPair` type); no ADR.
