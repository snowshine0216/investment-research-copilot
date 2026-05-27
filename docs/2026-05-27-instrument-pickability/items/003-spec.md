# Item 003 — QDII premium/discount snapshot + hard execution block

**Run**: `2026-05-27-instrument-pickability`
**Branch**: `autodev/instrument-pickability-feature`
**Mode**: backlog item (memo-rendering layer over an already-fetched score-row field; one new derived artefact; one new picks-table column; one new §7 execution-line prefix; sibling-independent from items 001 + 002).

## Goal

When triggers eventually fire and the user picks from the §5 候选可执行 list, they should be able to see — without leaving the memo — the on-exchange QDII premium-to-NAV for every QDII pick, the threshold at which the system blocks execution, and an explicit per-row block when the premium exceeds that threshold. Today's `outputs/2026-05-27/memo_blocked.md` §6 reads "数据未采集——请在交易前查阅各 QDII 二级市场溢价" even though `outputs/2026-05-27/scoring.json` already carries `qdii_premium_pct` for every QDII row (513690 is at -0.34%; off-exchange 017641/019441 synthetic-zero; 3 watch symbols 159941/513300/159501 are already above the 5% threshold). The fetcher (`fetch_qdii_premium_pct`), the routing helper (`qdii_premium_for_row`), and the decision-stage gate (`qdii_premium_too_high` in `decision/gates.py`) were all built by item 002 of the 2026-05-26 decision-confidence-followup run and documented in ADR 0002 §5 F6. This item closes the **memo rendering loop**: a new `溢价` column in the §5 picks table, a §6 risk-notes line that names the threshold and the cutoff, a §7 per-row hard-block prefix when the gate is hot, and a derived `outputs/<date>/qdii_premium.json` artefact for the audit trail.

## Acceptance criteria

Each criterion is independently verifiable by a single test (or a single grep over today's regenerated outputs).

1. **AC1 — `qdii_premium_pct` value flows from `scoring.json` to `PickRow`.** `PickRow` (frozen dataclass at `src/irc/memo/picks_table.py`) gains an optional field `qdii_premium_pct: float | None = None`. `_build_pick_rows` in `commands/memo_cmd.py` reads `score_row.get("qdii_premium_pct")` and assigns it (coerced to `float | None` via the same try/except pattern used in `_decision_status_for_pick`, lines 565–569 of `memo_cmd.py`). The field is **optional** so the 30+ existing `PickRow(...)` test call sites stay green without migration. Test: a hand-rolled score row with `{"qdii_premium_pct": 0.0648}` and `asset_class: "us_etf"` produces a `PickRow` whose `qdii_premium_pct == 0.0648`.

2. **AC2 — Picks-table column `溢价` between `单次定投上限` and `触发状态`.** `render_picks_table` in `src/irc/memo/picks_table.py` emits a 13-column markdown table (was 12; previous run's item 003 lock is being extended here, not preserved — see Q11 + AC15). New column header is exactly `溢价`. Cell renderer is a pure helper `_format_qdii_premium_cell(pick: PickRow) -> str` returning:
   - `—` when `qdii_premium_pct is None` (non-QDII rows; the field is unset by `qdii_premium_for_row` per CONTEXT.md "QDII premium-to-NAV").
   - `0.00%（场外申赎）` when `qdii_premium_pct == 0.0` AND the row's asset_class is in `{us_etf, hk_etf, qdii_global}` (synthetic-zero from the off-exchange policy in `qdii_premium_for_row`; the suffix distinguishes "structurally NAV-tracking" from "on-exchange happened to be 0%").
   - `+{pct:.2f}%` or `-{pct:.2f}%` otherwise (signed; `pct = qdii_premium_pct * 100`; format with 2 decimals; always include the sign character — `+` for positive, `-` for negative — so the operator never mistakes premium for discount).
   - Boundary case: `qdii_premium_pct == 0.0` AND asset_class NOT in the QDII set is structurally impossible (AC1 path only stamps the field via `qdii_premium_for_row` which returns `None` for non-QDII) but is handled defensively as `—` to match the AC1 None branch.

3. **AC3 — Markdown column rendering preserves the existing escape policy.** The new cell never contains a pipe character (`|`) or HTML break (`<br>`) so the single-line-per-row markdown contract from item 002-of-previous-run is preserved. Test: every render path for AC2 (None / synthetic-zero / positive / negative) produces a cell with zero `|` and zero `<br>`. The column header is a literal `溢价` (two CJK characters, zero punctuation).

4. **AC4 — Scoring footnote `_SCORING_FOOTNOTE` extended.** The footnote paragraph at `src/irc/memo/picks_table.py::_SCORING_FOOTNOTE` gains a single new sentence appended after the existing 触发状态 explainer: `溢价反映该 QDII 在二级市场相对单位净值的偏离（正值=溢价/折价为负），数据来源 AkShare fund_etf_spot_em 收盘快照，场外申赎类显示 0.00%（场外申赎）。`. The sentence is **exempt from the citation gate** (mirrors the existing 单次定投上限 exemption that landed in commit `6d45ba0` and is documented in `outputs/2026-05-27/PIPELINE_HALTED.md` predecessors) — the per-row premium cell is the audit surface, not the explainer. Test: `picks_table.py::_SCORING_FOOTNOTE` contains the literal substring `溢价反映` and the existing 触发状态 sentence remains byte-unchanged.

5. **AC5 — `QDII_PREMIUM_THRESHOLD_PCT` constant.** Module-level `Final` at `src/irc/memo/qdii_premium_lines.py::QDII_PREMIUM_THRESHOLD_PCT: Final[float] = QDII_MAX_PREMIUM_DEFAULT` (5%, ratio units). Re-exported from `schemas/discovery.py` — NOT redefined — so the memo display value can never drift from the decision-gate value. The threshold appears in §6 (AC7) and §7 (AC9) verbatim as `{QDII_PREMIUM_THRESHOLD_PCT * 100:.0f}%` (current rendering: `5%`). Test: a unit test imports both `QDII_MAX_PREMIUM_DEFAULT` and `QDII_PREMIUM_THRESHOLD_PCT` and asserts identity.

6. **AC6 — `qdii_premium.json` artefact emitted at memo stage.** New writer `src/irc/memo/qdii_premium_lines.py::write_qdii_premium_snapshot(rows, *, out_dir)` writes `outputs/<date>/qdii_premium.json` via the existing `atomic_write_text` pattern (`.tmp.{pid} → os.replace`). Schema:
   ```json
   {
     "generated_at": "2026-05-27T15:30:00+08:00",
     "threshold_pct": 0.05,
     "evidence_cutoff": "2026-05-26",
     "rows": [
       {
         "instrument_id": "513690",
         "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf",
         "market": "cn_on_exchange",
         "qdii_premium_pct": -0.0034,
         "blocking": false,
         "render_cell": "-0.34%"
       }
     ]
   }
   ```
   `rows` is sorted by `instrument_id` ASC (deterministic). `blocking = (qdii_premium_pct is not None) AND (qdii_premium_pct > threshold_pct)`. The artefact is a **projection** — every value is derived from data already in `scoring.json` + the memo's pick set; nothing is re-fetched. The artefact is keyed by all rows whose `qdii_premium_pct is not None` in scoring (covers picks AND watched-not-picked, so a later item can promote into discipline without re-emitting). Test: a hand-rolled scoring fixture with one above-threshold row and one below produces the exact JSON above (after `evidence_cutoff` is stubbed) with `blocking: true` on the above-threshold row.

7. **AC7 — §6 风险提示 line replaces the hardcoded placeholder.** `compose_fx_qdii_lines` in `src/irc/memo/diagnostics.py` (line 136) currently emits a 3-tuple `(header, premium, hedge)` with `premium = "溢价/折价：数据未采集——请在交易前查阅各 QDII 二级市场溢价。"`. The function signature gains two optional kwargs `qdii_premium_rows: Sequence[dict] | None = None` (the same projection AC6 writes) and `evidence_cutoff: str | None = None`. The `premium` line is recomputed:
   - When `qdii_premium_rows is None` or empty → emit verbatim the existing placeholder (back-compat for the existing 71 callers; no migration).
   - When non-empty → emit a deterministic block: `溢价/折价：QDII 候选标的二级市场偏离快照（数据截止 {evidence_cutoff}，阈值 {threshold_pct*100:.0f}%）：` followed by one ` - {iid} {name_cn}：{render_cell}{ "（超阈值，已暂缓执行）" if blocking else "" }` line per QDII pick (sorted by `instrument_id` ASC; same ordering as AC6). The full block is wrapped in `<!-- IRC_QDII_PREMIUM_BEGIN -->` / `<!-- IRC_QDII_PREMIUM_END -->` markers so the synthesizer leaves it verbatim (matches existing `IRC_*_BEGIN/END` pattern).
   - The replacement is performed only when `qdii_premium_rows` is supplied — the diagnostics module stays a pure renderer; the caller in `commands/memo_cmd.py` is responsible for sourcing the projection from `_build_pick_rows`.

8. **AC8 — `compose_fx_qdii_lines` keeps the 3-tuple return shape.** The function signature still returns `tuple[str, ...]` of length 3 `(header, premium_block, hedge)`. The `premium_block` element may now span multiple newline-separated lines (header + per-row bullets + closing marker) but is rendered as a single tuple element so the existing call site (`_compose_fx_qdii_lines(...)`) in `memo_cmd.py` does NOT need restructuring. Test: an empty-rows input still produces a 3-tuple whose `premium_block` is the original single-string placeholder.

9. **AC9 — §7 触发要点 hard-block prefix.** The execution-lines renderer at `src/irc/memo/template.py::_render_execution_section` keeps its preamble verbatim (line 45–48; `QDII标的执行前须查阅二级市场溢价/折价；溢价过高时暂缓执行。`). For each QDII pick whose `qdii_premium_pct > QDII_PREMIUM_THRESHOLD_PCT`, the execution line for that row is prefixed with a marker token at the start of the bullet body: `⛔ qdii_premium_too_high（{render_cell} > {threshold_pct*100:.0f}%，已暂缓）｜` followed by the existing target-weight / 建仓方式 / 触发 string verbatim. The prefix uses the **existing** blocking-reason code `qdii_premium_too_high` (not a new `qdii_premium_high` synonym — Q6). The prefix only attaches; it never rewrites or removes the trigger line. Empty above-threshold set → no prefixes anywhere → §7 byte-identical to the prior renderer. Test: a 2-pick fixture (one premium 6.5%, one premium 1.0%) produces §7 where exactly one line starts with `- ⛔ qdii_premium_too_high…`.

10. **AC10 — Execution-line prefix is composed at memo_cmd, not template.** Following the FP "effects at edges" rule, `template.py::_render_execution_section` accepts the `execution_lines` tuple verbatim (no logic added). The prefix is **prepended in `memo_cmd.py::_build_execution_lines`** (or its existing equivalent) where the projection rows from AC6 are already in scope. `template.py` remains a pure shape renderer over strings — no premium awareness. Test: `_render_execution_section` is fed two strings, one pre-prefixed and one not, and emits them verbatim wrapped in markers.

11. **AC11 — Picks-table column lock migration.** The previous run's item 003 introduced a 12-column lock (`代码 | 名称 | 角色 | 权重上限 | 综合分* | 决策 | 机会状态 | 本期行动 | 主要理由 | 单次定投上限 | 触发状态 | 证据`). This spec **extends** the lock to 13 columns by inserting `溢价` before `触发状态`. The fixture file `tests/integration/test_publishable_set_lockdown.py` (and any sibling lockdown fixture under `tests/integration/`) is migrated **in the same commit** as the production code change — no two-step migration. Test: the existing publishable-set lockdown two-run byte-equality assertion passes against the new 13-column header. A separate test asserts the column order in `render_picks_table` is exactly `[代码, 名称, 角色, 权重上限, 综合分*, 决策, 机会状态, 本期行动, 主要理由, 单次定投上限, 溢价, 触发状态, 证据]`.

12. **AC12 — Backwards compatibility for the 21 PickRow call sites.** The new field defaults to `None` on `PickRow`. All existing `PickRow(...)` constructions (test fixtures, helpers in `memo/picks_table.py`, the production builder in `memo_cmd.py`) keep working without keyword migration. Test: `PickRow(instrument_id="x", name_cn="X", asset_class="cn_etf", role="r", target_weight=0.01, composite_score=50.0, opportunity_state="small_watch", dca_action="hold", risk_action="hold", one_line_reason="...")` succeeds with `qdii_premium_pct == None`.

13. **AC13 — `qdii_premium_too_high` code-name unification.** The new code does NOT introduce `qdii_premium_high` — the existing `qdii_premium_too_high` from `decision/gates.py::compute_blocking_reasons` is used in the §7 prefix, the §6 line marker, and the `qdii_premium.json::blocking` flag. The MASTER-SPEC row 003's text "hard `qdii_premium_high` gate" is interpreted as colloquial language, not a literal new identifier. Test: a grep over `src/irc/` for the literal token `qdii_premium_high` returns zero matches (the existing `qdii_premium_too_high` is the one and only canonical name).

14. **AC14 — Determinism + two-run byte equality.** The whole pipeline `irc run --only memo` over identical scoring/opportunity inputs produces byte-identical `memo.md` and byte-identical `qdii_premium.json` across two consecutive runs. Nondeterminism sources: (a) dict/set ordering when serialising row records — pinned by sorting `qdii_premium.json::rows` by `instrument_id` ASC at construction time (AC6), and by enumerating QDII picks in `_build_pick_rows` insertion order which is itself deterministic; (b) timestamp in `qdii_premium.json::generated_at` — fixed by reading from a callable injected by the caller (`now_fn: Callable[[], datetime]`) so tests can stub the clock and the production caller passes `lambda: datetime.now(...)`; the timestamp must be a UTC+8 ISO string. (c) `evidence_cutoff` — computed by `extract_evidence_cutoff` over the same refs that scoring already used, NOT a fresh wall-clock read. Test: stub the clock + scoring inputs, run `write_qdii_premium_snapshot` twice, assert byte-identical files.

15. **AC15 — No row-level state change.** `OpportunityRow.advisory_gaps`, `evidence_gaps`, `expected_omissions`, `thesis_state`, `opportunity_state`, `dca_action`, `risk_action` are all unchanged. The premium signal does NOT propagate back into `opportunity_report.json` or `thesis_cards.yaml` (it is already in `scoring.json`; that's enough for the discipline report to consume in a future item). `OpportunityRow.constituent_analyses` unchanged. Item 008 lockdown stays valid for those artefacts. Test: the existing lockdown gate continues to pass for `opportunity_report.json` and `thesis_cards.yaml` byte-equality.

16. **AC16 — H3 / SAME-3 / citation gate v1 invariants preserved.** The new column emits no `[ref:...]` markers (the 溢价 cell is data-only; the underlying citation is the scoring snapshot already linked in the 证据 cell). The §6 marker block also emits no `[ref:...]`. No new citation IDs anywhere; the citation_audit gate sees no new shapes. Test: a citation-set equality test compares the new 13-column picks table's 证据 cell against `opportunity_report.json::rows[*].thesis_evidence[*].citation_id` and finds the SAME-3 invariant intact.

17. **AC17 — TDD coverage.** Every AC1–AC16 has at least one test, written **before** production. Test files:
    - `tests/memo/test_qdii_premium_lines.py` — new file mirroring `src/irc/memo/qdii_premium_lines.py` (AC5 / AC6 / AC7 / AC14).
    - `tests/memo/test_picks_table.py` — existing file gains AC1 + AC2 + AC3 + AC4 + AC11 + AC12 tests.
    - `tests/memo/test_diagnostics.py` — existing file gains AC7 + AC8 tests.
    - `tests/memo/test_template.py` — existing file gains AC10 test.
    - `tests/commands/test_memo_cmd.py` — gains AC9 + AC13 integration tests.
    Pure-logic tests (formatters, threshold imports, column ordering) need no mocks. The clock injection (AC14) is the only stubbing point.

18. **AC18 — File / function size budgets.** New module `src/irc/memo/qdii_premium_lines.py` < 200 lines. Each helper ≤ 20 lines (extract over nest). `picks_table.py` is currently ~210 lines (already over the 200-line ideal); the new column adds a ~15-line `_format_qdii_premium_cell` helper plus one column header string plus one cell call — DOES NOT enlarge the file beyond a reasonable delta (<30 lines added). `commands/memo_cmd.py` is already an established violation of the size budget; additions follow item 001's pattern (a single 10-15-line `_compose_qdii_premium_projection` helper paralleling `_compose_evidence_gap_lines`); do NOT enlarge the existing violation by more than necessary.

## Non-goals (explicitly out of scope)

- **NG1.** **No new AkShare fetcher.** `fetch_qdii_premium_pct` already exists and is called from `score_cmd.py`. This item reads `qdii_premium_pct` off the existing `scoring.json` rows — no second fetch, no live AkShare call in memo stage. The live-test gate (`IRC_RUN_LIVE_AKSHARE=1` + `pytest.mark.live_akshare`) protects the fetcher itself; this item adds no further live-test surface.
- **NG2.** **No discipline report integration.** The 3 watch-not-picked symbols above threshold (159941 / 513300 / 159501 in today's `scoring.json`) are NOT surfaced in `discipline_report.md` by this item. The `qdii_premium.json` artefact carries them (AC6 includes ALL premium-bearing rows), so a follow-up item can promote them into the discipline failure section without re-engineering. Deferred per the run's P0-only scoping.
- **NG3.** **No new blocking-reason code.** Reuse `qdii_premium_too_high` from `decision/gates.py`. The MASTER-SPEC's "hard `qdii_premium_high` gate" text is colloquial; the canonical code already exists.
- **NG4.** **No change to `qdii_max_premium_pct` default or schema.** 5% stays the default; YAML overrides remain the operator surface. The memo only displays the threshold; it does not validate or normalise it.
- **NG5.** **No allocation / `trade_plan.yaml` change.** Whether to soften target weights for above-threshold QDII is a separate concern (allocation-time). This item is memo-time only.
- **NG6.** **No premium on the §5 触发状态 column.** That column is reserved for `trade_plan.yaml::trades[*].triggers` (price/drawdown conditions, not data-availability gates). The §7 prefix is the canonical surface for the hard block; AC9 anchors it there.
- **NG7.** **No back-fill of historical `outputs/`.** Behaviour applies to the next memo run only. Old `outputs/<date>/memo.md` files keep the legacy "数据未采集" prose.
- **NG8.** **No intraday data, no provider switch.** The AkShare `fund_etf_spot_em` close-of-day snapshot is the only data source. The §6 marker block explicitly discloses `数据截止 {evidence_cutoff}` so the operator knows the staleness.
- **NG9.** **No coupling to items 001 + 002.** Item 001's broker_empty advisory and item 002's concentration panel are sibling items; this item neither imports their helpers nor reuses their markers. The `IRC_QDII_PREMIUM_*` marker pair is independent.
- **NG10.** **No change to the `qdii_premium_unknown` semantics.** When a QDII row's `qdii_premium_pct is None` (AkShare fetch failed mid-pipeline), the cell renders `—`, the §6 row omits that instrument, and the §7 prefix is NOT applied. The existing `qdii_premium_unknown` blocking reason (separate from `qdii_premium_too_high`) still fires in the decision stage; this item does not change that gate. Operator-facing remediation text in `decision/report.py::_BLOCKING_REMEDIATION["qdii_premium_unknown"]` is unchanged.

## Constraints

These are inherited from project CLAUDE.md, CONTEXT.md, ADRs, and global FP guidance. Any deviation is a stop-and-ask trigger for the orchestrator.

- **TDD (hard rule).** Red → green → refactor. Each AC test is written before the production code that makes it pass. Test files mirror source.
- **Functional / immutable.** New module is pure. `PickRow` stays a frozen dataclass; the new field is just one more frozen attribute. `_format_qdii_premium_cell`, `_compose_qdii_premium_projection`, `write_qdii_premium_snapshot` are pure functions modulo the explicit `atomic_write_text` I/O boundary.
- **File size budget.** New module < 200 lines; new helpers ≤ 20 lines. `picks_table.py` and `commands/memo_cmd.py` get small surgical additions (AC18); do NOT refactor pre-existing size violations as part of this item.
- **Pure cores, effects at edges.** The premium value flow is purely a renderer concern — reads `scoring.json` already in memory, writes one new JSON artefact at the existing memo I/O edge. No AkShare call. No LLM call. No DuckDB read.
- **Module import contract.** `src/irc/memo/qdii_premium_lines.py` imports from `irc.schemas.discovery` (for `QDII_MAX_PREMIUM_DEFAULT`) and the stdlib only. NO imports from `irc.opportunity.*`, `irc.scoring.*`, or `irc.commands.*`. Mirrors the existing `aliases.py` tier-1 import contract. The caller in `commands/memo_cmd.py` is the dependency-injection edge.
- **thesis_state setter invariant.** `thesis_state` is set ONLY inside `derive_thesis_from_evidence`. This item does NOT touch `thesis_state` (memo-only).
- **Citation ID format.** Unchanged: `\[ref:[0-9a-f]{16}\]`. The new column and §6 block emit no `[ref:...]` markers.
- **H3 universal gap-row invariant.** Preserved — this item does NOT touch `evidence_gaps`, the H3 partition predicate, or `gapped_rows`.
- **SAME-3 invariant.** Preserved — the citation-set across picks-table 证据 / evidence-pool / discipline is byte-unchanged (the new 溢价 cell carries no citation_ids).
- **Deterministic markers.** New `IRC_QDII_PREMIUM_BEGIN/END` pair follows the existing pattern. Synthesizer prompt (`memo/synthesizer.py`) gains an instruction to preserve the block verbatim, paralleling the existing `IRC_EVIDENCE_GAP_*` clause.
- **Secrets in `.env` only.** N/A for this item — no new credentials.
- **Live-test gate.** N/A for new tests — this item adds no new fetcher. The existing `fetch_qdii_premium_pct` live test (already gated by `IRC_RUN_LIVE_AKSHARE=1` + `pytest.mark.live_akshare` per CONTEXT.md "Live test gate") continues unchanged.
- **Atomic write pattern.** `qdii_premium.json` is written via `atomic_write_text` (`.tmp.{pid} → os.replace`) — same as every other memo-stage artefact.
- **No shared mutable state.** `write_qdii_premium_snapshot` takes its clock and rows as parameters; no module-level mutables. The lru_cache on `_fetch_full_etf_spot_table` is owned by the fetcher (`akshare_client.py`), not this module.

## Open questions resolved during brainstorming

Each Q is the question asked during brainstorming; A is the auto-accepted answer with rationale.

- **Q1: New fetcher and cache, or pure memo-rendering over `scoring.json`?**
  **A:** Pure memo-rendering. Plus one new derived artefact `outputs/<date>/qdii_premium.json` as a projection (audit trail / future discipline consumption). **Rationale:** `fetch_qdii_premium_pct` and `qdii_premium_for_row` already exist; `scoring.json` already carries `qdii_premium_pct`; verified by reading today's `outputs/2026-05-27/scoring.json`. Adding a second fetch would duplicate I/O and risk drift between scoring and memo views. The derived artefact gives the discipline report a single canonical surface to read in a follow-up item without re-engineering.

- **Q2: New picks-table column or reuse the 触发状态 column?**
  **A:** New `溢价` column inserted before 触发状态. **Rationale:** premium is a point-in-time market-state datum; the 触发状态 column is reserved for `trade_plan.yaml::trades[*].triggers` (conditional execution rules). Overloading the column would conflate "data availability" with "rule evaluation". The column lock from the previous run's item 003 is a versioned contract — migrating it (AC11) is part of this item's surface area, not an excuse to skip the column.

- **Q3: Threshold — keep 5% (`QDII_MAX_PREMIUM_DEFAULT`)?**
  **A:** Yes — reuse `QDII_MAX_PREMIUM_DEFAULT = 0.05` verbatim. Re-export via `QDII_PREMIUM_THRESHOLD_PCT` (alias, not a redefinition; AC5). **Rationale:** decision-stage gate already validates at 5%; memo must display the same number or it'd confuse the operator. The number is operator-tunable via `config/discovery.yaml::hard_filters.qdii_max_premium_pct` (per CONTEXT.md "qdii_max_premium_pct"). Locking the memo to the same alias keeps the display value chasing the gate value.

- **Q4: Disclose the evidence cutoff in the §6 line?**
  **A:** Yes — `数据截止 {evidence_cutoff}` is in the §6 marker block header (AC7). **Rationale:** AkShare's `fund_etf_spot_em` is close-of-day at best; intraday premium can differ materially. The operator needs to know the staleness before clicking buy. Reuses `extract_evidence_cutoff` (already in `memo/pipeline.py`).

- **Q5: Cover watched-not-picked rows in this item?**
  **A:** No — out of scope (NG2). The 3 watch symbols above 5% (159941 / 513300 / 159501) are emitted into `qdii_premium.json` (AC6 records ALL premium-bearing rows so the artefact is reusable), but neither §5 nor §6 surfaces them. **Rationale:** §5 / §6 are scoped to picks per the master-spec; discipline_report.md is a separate code path that's been intentionally left out of this run's P0 list. The artefact's "covers everyone" property removes friction from the follow-up.

- **Q6: `qdii_premium_high` (new code) vs `qdii_premium_too_high` (existing)?**
  **A:** Unify on existing `qdii_premium_too_high`. AC13 locks the no-new-code rule. **Rationale:** the existing code is already in `decision/gates.py::compute_blocking_reasons`, in `_BLOCKING_REASON_LABEL`, in `_BLOCKING_REMEDIATION`, and in `_decision_status_for_pick`. Introducing `qdii_premium_high` as a synonym would force callers to handle both, double-document remediation text, and risk drift. The MASTER-SPEC's wording is colloquial; the canonical name is `qdii_premium_too_high`.

- **Q7: Off-exchange QDII rendering — `—` or `0.00%`?**
  **A:** `0.00%（场外申赎）` (literal suffix included). **Rationale:** `—` would imply "data missing" and trigger operator anxiety; the synthetic-zero IS the correct economic answer because off-exchange feeders transact at NAV by construction (per CONTEXT.md "Off-exchange synthetic-zero premium policy"). The suffix `（场外申赎）` is the disambiguation channel — distinguishes structural NAV-tracking from a "happened to be 0% today" on-exchange snapshot. The picks-table is wide enough to absorb 5 extra CJK characters in one cell.

- **Q8: LOF ambiguity for 161716 — fetched value or synthetic-zero?**
  **A:** Trust score-row's `market` field verbatim. If 161716 is tagged `cn_off_exchange` in scoring (today's value `qdii_premium_pct == 0.0` suggests it is, despite the on-exchange ticker), the cell renders `0.00%（场外申赎）`. **Rationale:** the routing decision lives in `qdii_premium_for_row` and is the single source of truth; re-classifying at memo time would split the routing logic across two modules and break the "one place to change behaviour" rule. If the universe metadata is wrong, fix it in the universe config — not in the memo renderer.

- **Q9: Premium trigger in the §5 触发状态 column?**
  **A:** No — §7 prefix only (AC9 + AC10 + NG6). **Rationale:** the 触发状态 column is glyph-encoded (`✓ ✗ ⚠`) and tied to trigger-rule evaluation in `trade_plan.yaml`. Adding a data-availability gate to that column would (a) require a new glyph, (b) conflate two different operator workflows ("when will this fire?" vs "should I even be looking?"), (c) muddy the existing item 002-prev-run column semantics. The §7 prefix `⛔ qdii_premium_too_high…｜` is the canonical surface — explicit, prefixable, and adjacent to the actual execution instruction.

- **Q10: Snapshot cache path — `outputs/<date>/data/qdii_premium.json` or `outputs/<date>/qdii_premium.json`?**
  **A:** `outputs/<date>/qdii_premium.json` (top-level). **Rationale:** the `data/` subdir is reserved for the discovery universe cache (e.g. `discovery_diagnostics.csv` lives at top level, and `data/` is the DuckDB cache for the run). Top-level placement matches the sibling artefact naming convention (`scoring.json`, `opportunity_report.json`, `proposed_allocation.yaml`, `trade_plan.yaml`, `gold_regime.json`, `thesis_cards.yaml`). Discoverability + audit-clarity beats grouping by data origin.

- **Q11: ADR needed?**
  **A:** Yes — add `docs/adr/0006-qdii-premium-memo-surface.md`. Three-of-three test (hard-to-reverse / surprising / real tradeoff):
  - **Hard to reverse**: the 13-column picks-table lock change forces a lockdown fixture migration; the new top-level `qdii_premium.json` artefact establishes an output contract for downstream tooling. Both are hard to walk back without a separate cleanup migration. **PASS.**
  - **Surprising without context**: the `0.00%（场外申赎）` vs `—` rendering convention; the dual existence of `qdii_premium_unknown` + `qdii_premium_too_high`; the choice to read the projection at memo time rather than re-fetch — all surprising without an ADR pointing back to ADR 0002 §5 F6 and CONTEXT.md "QDII premium-to-NAV". **PASS.**
  - **Real tradeoff**: column-add vs cell-overload (AC2 vs Q9 alternative); §7 prefix vs §5 column for the hard block (AC9 vs Q9). Both are real and both are documented here. **PASS.**
  All three trigger; ADR is required. Title: `0006 — QDII premium-to-NAV memo surface`. Body cross-references ADR 0002 §5 F6 (the fetcher), CONTEXT.md "QDII premium-to-NAV" + "Off-exchange synthetic-zero premium policy", and this spec.

- **Q12: ADR-level open questions to flag for the orchestrator?**
  **A:** None blocking. Two soft items for the run's CHANGELOG.md:
  - The 3-watched-above-threshold gap (NG2) — explicitly out of scope; the artefact carries them so the follow-up is a pure rendering change.
  - The 161716 asset_class tagging (Q8) — note that the universe metadata may be misleading (a LOF with both NAV subscription AND on-exchange ticker is tagged `us_etf` + `cn_off_exchange`); not this item's concern, but worth a glossary footnote so the next item that touches universe metadata doesn't re-trip the same ambiguity.
