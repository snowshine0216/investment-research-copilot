# Item 007 spec — memo + discipline renderers + alias-builder (Slices D1a + D1c + D3a + D3b)

## Goal

Item 007 is the **renderer slice** that consumes the data items 002 (citation schema + `select_citations`), 003 (`ConstituentAnalysis`), 005 (fund-level NAV/announcement evidence), and 006 (Policy B verdicts, `evidence_gaps`, H3 partitioning) have already produced, and emits the user-facing artifacts: `memo.md` (evidence pool with `[ref:{citation_id}]` markers + `[stock:{symbol}]` constituent tags + `## 持仓明细` appendix) and `discipline_report.md` (per-row sections with nested `thesis_evidence` bullets + inline top-5 holdings + full top-N `## 持仓明细` appendix). It ALSO ships the alias-builder (`build_alias_maps`) that closes a load-bearing silent-no-op failure mode in `find_uncited_conclusions` (item 009): an empty `instrument_aliases` map causes the audit to silently pass every paragraph, so `find_uncited_conclusions` adds a first-line `RuntimeError` on empty input, and `build_alias_maps` becomes the named, testable, fail-fast producer.

Item 007 ships ZERO new audit logic. `find_uncited_conclusions`, `find_hallucinated_citations`, `find_uncited_discipline_rows`, and the per-mention strict gate land in item 009. Item 007 ONLY: (a) wires `select_citations` into `evidence_pool.py` with canonical `[ref:{citation_id}]` markers, (b) ships `src/irc/memo/aliases.py`, (c) adds the empty-map RuntimeError to `find_uncited_conclusions` (the function-body change; item 009 ships the function itself if it doesn't exist yet — see "Dependencies"), (d) extends `discipline_report.md`'s `_render_section` with nested thesis_evidence bullets, (e) extends `discipline_report.md` with inline top-5 holdings for active-fund rows, (f) appends a `## 持仓明细` appendix listing all top-N constituents per fund.

## In scope

### D1a — evidence_pool.py citation markers

1. **`build_evidence_pool(opportunity_rows, scoring_rows, plan_trades, gold_regime)`** — extend the existing function so that AFTER the state-codes line for each instrument (the `_format_instrument_evidence` output already shipped), append the top-3 citation lines produced by `select_citations(row.thesis_evidence, cap=3)`. Each appended line has the format:
   ```
   [stock:{symbol}] [ref:{citation_id}] {type} · {source} · {date}: {summary} ({url})
   ```
   `[stock:{symbol}]` is emitted ONLY when the entry's `scope == "constituent"` (otherwise omitted entirely — no empty `[stock:]` placeholder). `[ref:{citation_id}]` is ALWAYS emitted. `{url}` parenthetical is omitted when `url == ""` (the citation_id hash preimage already disambiguates URL-less entries via `summary[:64]`). Spacing locked: single space between `[stock:...]` and `[ref:...]`, single space between `[ref:...]` and the display text.

2. **Selector consumer.** `build_evidence_pool` consumes `row.thesis_evidence` as a frozen tuple of `ThesisEvidence` dataclass instances — NOT the JSON-dict form. The caller (`pipeline.py::run_memo`) must reconstruct `ThesisEvidence` from the `opportunity_report.json` dict form before passing rows in. Reuse `_evidence_from_dict` from `memo_cmd.py` (item 002 added it; promote it to `src/irc/opportunity/types.py` as a `ThesisEvidence.from_dict` classmethod if both `_build_pick_rows` and `build_evidence_pool` need it — see Open question OQ1).

3. **No pre-filtering.** Neither `build_evidence_pool` nor `_build_pick_rows` may pre-filter `row.thesis_evidence` before calling `select_citations`. If a future contributor wants to drop URL-less entries or restrict to `scope in {"instrument","constituent"}`, that logic MUST live inside `select_citations` itself (so both consumers see the same filter). Locked by a regression test: feed both consumers the same `row.thesis_evidence` tuple → assert the cited `citation_id` set is identical.

4. **Watchlist behavior unchanged.** The existing `op.get("opportunity_state") == "small_watch"` skip for watchlist instruments stays — small_watch rows do not contribute evidence-pool lines. Their citations still surface in the `## 持仓明细` appendix when the parent fund is published, but not in the evidence pool.

### D1c — aliases.py (new module)

5. **New file `src/irc/memo/aliases.py`** with the following surface:
   ```python
   InstrumentAliases = dict[str, str]
   # alias-string → instrument_id

   ConstituentAliases = dict[str, frozenset[tuple[str, str]]]
   # stock identifier (symbol OR name) → frozenset of (instrument_id, constituent_key)

   class InstrumentAliasCollisionError(RuntimeError): ...

   def build_alias_maps(
       publishable_rows: tuple[OpportunityRow, ...],
   ) -> tuple[InstrumentAliases, ConstituentAliases]:
       """Pure function. Builds alias maps from publishable rows.

       Raises InstrumentAliasCollisionError if any instrument alias key
       maps to two different instrument_id values.
       """
   ```

6. **Instrument-level aliases.** For each row, emit the following alias-string → `instrument_id` entries:
   - The bare `instrument_id` (e.g. `"005827"`).
   - The canonical Chinese name `row.name_cn` (e.g. `"易方达蓝筹精选"`) IF non-empty.
   - Venue-suffixed forms IF they appear elsewhere in the run (read from `lookthrough_target.key` and any `provider_symbol` carried on the row — best-effort; `_strip_venue_suffix(key)` already handles `.SH/.SZ/.OF/.HK`).

   **Collision invariant.** If any alias key resolves to two different `instrument_id` values, raise `InstrumentAliasCollisionError(alias, [iid1, iid2])` with both `instrument_id` values in the error message. Builder-time raise, NOT lazy at lookup — see Q4 below. Two rows legitimately sharing an `instrument_id` (e.g. duplicate publishable row — already a bug at item 006's H3 partition) collapse to the same map entry without raising (the alias points to the same `instrument_id`).

7. **Constituent-level aliases.** For each row's `constituent_analyses`, each `ConstituentAnalysis` contributes TWO alias keys, both pointing to the SAME `frozenset({(row.instrument_id, c.symbol)})`:
   - The symbol `c.symbol` (e.g. `"600519"`).
   - The Chinese name `c.name_cn` (e.g. `"贵州茅台"`) IF non-empty.

   **Multi-owner stocks.** If the same stock appears as a constituent of multiple funds in the publishable set (e.g. `贵州茅台` held by both `005827` and `163417`), the alias entry stores a frozenset with TWO tuples:
   ```python
   constituent_aliases["600519"] == frozenset({("005827","600519"), ("163417","600519")})
   constituent_aliases["贵州茅台"] == frozenset({("005827","600519"), ("163417","600519")})
   ```
   Both keys (symbol and name) resolve to the SAME frozenset. No collision raise — multi-owner is the normal case for blue-chip names.

   **Empty-string guard.** A constituent with empty `symbol` is a programming error (item 003's `ConstituentAnalysis.__post_init__` raises on it). A constituent with empty `name_cn` skips the name alias entry — no empty-string key in either map.

8. **`find_uncited_conclusions` empty-map precondition.** As the FIRST executable line of `find_uncited_conclusions`:
   ```python
   if not instrument_aliases:
       raise RuntimeError(
           "empty instrument_aliases — D1c build_alias_maps did not run "
           "or returned an empty map; refusing to silent-no-op the audit"
       )
   ```
   This closes the most likely failure mode: an upstream bug returns `{}`, every memo paragraph looks like "no instrument referenced", and the audit silent-no-ops the whole gate. The function exists in `src/irc/memo/numeric_audit.py` (or wherever item 009 lands it — see Dependencies); item 007 only commits the empty-map raise + the alias-builder. If `find_uncited_conclusions` does not yet exist when item 007 lands (item 009 is later in the chain), item 007 ships a stub:
   ```python
   def find_uncited_conclusions(
       prose: str,
       cited_map: CitedMap,
       instrument_aliases: InstrumentAliases,
       constituent_aliases: ConstituentAliases,
       constituent_cited_map: ConstituentCitedMap,
   ) -> list[NumericFinding]:
       if not instrument_aliases:
           raise RuntimeError(...)
       return []   # item 009 fills the body
   ```
   The empty-map raise is the irreducible contribution of item 007; the body is item 009's territory.

### D3a — discipline `_render_section` nested thesis_evidence bullets

9. **`_render_section(title, rows)` in `src/irc/opportunity/report.py`** — after the existing per-row line (`- **{instrument_id} {name_cn}** ｜ {opportunity_state} ｜ dca={dca_action} ｜ risk={risk_action} ｜ {note_cn}`), emit nested bullets carrying the top-3 thesis_evidence entries:
   ```
   - **{instrument_id} {name_cn}** ｜ ... ｜ {note_cn}
     - [ref:{citation_id}] {type} · {source} · {date}
     - [ref:{citation_id}] {type} · {source} · {date}
     - [ref:{citation_id}] {type} · {source} · {date}
   ```
   Top-3 selected via `select_citations(row.thesis_evidence, cap=3)` — same selector as the picks table and evidence pool (the SAME-3 invariant from Q2). Indentation: two spaces (markdown nested list).

10. **Active-fund row source.** For rows with `asset_class == "cn_equity_fund"` (active-fund kind), `row.thesis_evidence` is item 003's flattened tuple across all `constituent_analyses[*].evidence`. The selector therefore picks from the per-constituent evidence union, exactly as it does for the picks table and evidence pool — no separate code path. For instrument-scope rows (gold, cn_bond_fund, cn_etf, tracked indices), `row.thesis_evidence` carries fund-level NAV + announcement entries (item 005), and the selector picks from those.

11. **Empty thesis_evidence.** If `row.thesis_evidence == ()`, emit NO nested bullets (no `（无）` placeholder line). This is the publishable-but-no-evidence case which should NOT exist in canonical output (item 009's gate blocks it), but the renderer is defensive: render the parent line, omit the bullets, never crash.

### D3b — discipline 持仓明细 (inline cap-5 + appendix all top-N)

12. **Inline top-5 holdings.** For rows where `row.constituent_analyses != ()` (active-fund rows), AFTER the D3a nested thesis_evidence bullets and BEFORE the next row's parent line, emit:
    ```
      - 持仓 (Top 5):
        - {symbol} {name_cn} (权重 {weight_pct}%): {one_line_view}
        - {symbol} {name_cn} (权重 {weight_pct}%): {one_line_view}
        - ... (up to 5)
    ```
    Ordering: by `weight_pct` descending (rank 1 first). Cap at 5. For constituents in the inline-5 with `audit_errors != ()`, append ` ⚠️ {audit_errors_joined}` after `one_line_view`. For constituents with `evidence == () AND failure_reasons != ()`, render `❌ {failure_reasons_joined}` in place of `one_line_view`.

13. **`## 持仓明细` appendix.** Append a new top-level section at the END of `discipline_report.md` (AFTER `_DRAWDOWN_NOTE_CN`), structured as:
    ```markdown
    ## 持仓明细

    ### {instrument_id} {name_cn} ({asset_class})

    - {symbol} {name_cn} (权重 {weight_pct}%): {one_line_view} [ref:{citation_id}] [ref:{citation_id}]
    - {symbol} {name_cn} (权重 {weight_pct}%): {one_line_view} [ref:{citation_id}]
    - {symbol} {name_cn} (权重 {weight_pct}%): ❌ {failure_reasons_joined}
    - {symbol} {name_cn} (权重 {weight_pct}%): ⚠️ audit_error: {audit_errors_joined}
    - ... (all top-N, default top_N=10)

    ### {next_fund_id} {next_fund_name} ({asset_class})
    ...
    ```
    Per-constituent format precedence (FIRST matching rule wins):
    - `audit_errors != ()` → `- {symbol} {name_cn} (权重 {weight_pct}%): ⚠️ audit_error: {audit_errors_joined}` (no `[ref:]` markers).
    - `evidence == () AND failure_reasons != ()` → `- {symbol} {name_cn} (权重 {weight_pct}%): ❌ {failure_reasons_joined}` (no `[ref:]` markers).
    - `evidence != ()` → `- {symbol} {name_cn} (权重 {weight_pct}%): {one_line_view} {ref_markers}` where `ref_markers` is the space-joined `[ref:{citation_id}]` for each entry in `select_citations(c.evidence, cap=3)`.
    - `evidence == () AND failure_reasons == ()` → this is the `audit_error="missing_constituent_record"` case item 006 stamps via `evaluate_policy_b`. Since item 006 raises in Policy B before publishable status, this case SHOULD NOT REACH the renderer — but defensively render: `- {symbol} {name_cn} (权重 {weight_pct}%): ⚠️ audit_error: missing_constituent_record`.

14. **Appendix ordering.** Per fund subsection ordering: by section order in the memo's pick table (the order pick_rows emits — i.e. the order `_build_pick_rows` produces, which is the trade_plan.yaml target order). Funds present in `opportunity_report.json` AND publishable (per item 006's H3) but NOT in `pick_rows` (small_watch state or any other non-pick publishable state) are appended AFTER the pick-table funds, sorted by `instrument_id` ascending. Within each fund, constituents ordered by `weight_pct` descending (rank 1 first), `symbol` ascending as tiebreaker.

15. **Appendix scope = publishable rows only.** The appendix iterates `publishable_rows` from item 006's H3 partition — gapped rows (`evidence_gaps != ()`) do NOT appear in the appendix (they're already in the failure section). The audit gate (item 009's `find_uncited_discipline_rows`) iterates the same publishable set, so the appendix and the gate see the same constituents.

### Audit-gate coverage scope (item 009 contract)

16. The `find_uncited_discipline_rows` gate from item 009 reads `DisciplineRow.thesis_evidence` (top-level fund evidence) AND `DisciplineRow.constituent_analyses[*].evidence` (per-constituent). Item 007's appendix renders ALL top-N (default 10), not just the inline-5 — the gate consequently checks all top-N. The renderer's job is to make this enforceable: every constituent in the appendix either shows ≥1 `[ref:...]` marker, OR shows the `❌`/`⚠️` failure/audit-error sentinel. Item 009's gate fires when a constituent appears in the appendix with NEITHER markers NOR sentinels — which item 007's render precedence rules above make structurally impossible (every code path produces one of the four formats).

### Audit-gate parseable appendix contract (NEW — grill outcome)

17. **Locked regex contract for appendix bullets.** Every line in a `## 持仓明细` subsection matches exactly one of the following regex shapes. Item 009's `find_uncited_discipline_rows` keys off these shapes for its appendix-parse pass; item 007 commits to the structural format here so item 009 cannot drift.

    Where `SYM = [0-9A-Z]{4,6}`, `NM = .+?` (Chinese name, non-greedy), `WPCT = \d+(?:\.\d+)?`, `OLV = .+` (one_line_view), `REFS = ( \[ref:[0-9a-f]{16}\])+`, `FAIL = .+`:

    - **Shape 1 — evidence + failures (partial success):** `^- {SYM} {NM} \(权重 {WPCT}%\): {OLV}{REFS} \({FAIL}\)$`
    - **Shape 2 — failure only:** `^- {SYM} {NM} \(权重 {WPCT}%\): ❌ {FAIL}$`
    - **Shape 3 — audit-error only:** `^- {SYM} {NM} \(权重 {WPCT}%\): ⚠️ audit_error: {FAIL}$`
    - **Shape 4 — evidence only (canonical):** `^- {SYM} {NM} \(权重 {WPCT}%\): {OLV}{REFS}$`
    - **Shape 5 — defensive fallback:** identical to Shape 3 (`missing_constituent_record` literal). Renderer emits this when `evidence == () AND failure_reasons == () AND audit_errors == ()` — see AC22 last bullet.

    The inline top-5 block under a discipline-row line uses a SIMILAR but distinct format (single bullet with `audit_errors` appended after `one_line_view` via ` ⚠️ {errors}`, no separate audit-error-only line because the inline-5 ALWAYS shows weight + name first). Item 009 parses the appendix only — the inline-5 is for human readers, not for the audit gate.

    **Verification.** Item 007's `tests/opportunity/test_report.py` exercises all five shapes against the 4 fixture cases in AC22 + AC29. The regex contract is captured as a module-level `_APPENDIX_LINE_RE` constant in `report.py` for cross-test reuse and for the eventual item 009 audit-gate parser.

## Out of scope

- **`find_uncited_conclusions` body** (paragraph-level instrument/constituent reference detection, multi-owner disambiguation via section header, `kind="ambiguous_constituent_reference"` emission) — item 009. Item 007 only commits the empty-map RuntimeError + the alias-builder.
- **`find_hallucinated_citations`, `find_missing_pick_citations`, `find_uncited_opportunity_rows`, `find_uncited_discipline_rows`** — item 009.
- **`IRC_CITATION_ENFORCE_MODE` env var + `citation_audit.json` shadow log** — item 009.
- **Per-driver citation gate (`OpportunityRow.contributing_dimensions` consumed by `find_uncited_opportunity_rows`)** — item 009.
- **Per-mention strict citation enforcement** (every mentioned stock owes a dual-leg citation) — item 009.
- **Integration test sweep (E1–E17)** — item 008.
- **Changes to `ThesisEvidence` schema, `select_citations` algorithm, `ConstituentAnalysis` shape** — locked by items 002, 003, 006 + ADRs 0001/0002/0003. Item 007 is strictly downstream.
- **Memo-stage failure renderer** (`### 未能纳入精选：机会数据缺失` / `### 未能纳入精选：证据不足` h3 sub-sections in §5) — already shipped in item 002 (`_build_pick_rows` returns `(pick_rows, absent, gapped)`; `render_failure_sections` is in `picks_table.py`). Item 007 does NOT touch the memo failure renderer.
- **Discipline failure section renderer** (`## 证据不足 / Failed fetch` + V1 systematic exclusions summary line) — item 006 (`src/irc/opportunity/failure_renderer.py::render_failure_section` + `render_v1_systematic_exclusion_summary`).
- **Aliases for the failure-section renderer.** The failure section reads ONLY `instrument_id`, `name_cn`, `evidence_gaps`, `fetch_types_attempted` (item 006 invariant); aliases are not needed there.

## Constraints

- **FP / purity.** Every new function in `aliases.py` and the renderer changes are pure (no I/O, no mutation, no logging). The frozen-dataclass + spread-style invariants from `~/.claude/CLAUDE.md` apply: alias maps returned as new dicts (not mutated in-place), `frozenset` for the multi-owner case, no method calls on `OpportunityRow` mutating state.
- **Public API stability.** Additive only:
  - `build_evidence_pool` signature unchanged (already takes the four kwargs); behavior change is adding the citation lines after the state-codes line.
  - `_render_section` signature unchanged; behavior change is appending nested bullets + inline top-5 holdings.
  - `compose_discipline_markdown` signature unchanged; behavior change is appending the `## 持仓明细` section after `_DRAWDOWN_NOTE_CN`.
  - `aliases.py` is a NEW module — no breakage.
  - `find_uncited_conclusions` is either a new stub (item 007) or a body-edit (if item 009 ships first by mistake) — the empty-map raise is the only line item 007 owns.
- **Performance.** Renderers are pure functions over already-built data. Cost: O(rows × top_N × 3) for the appendix (default ~30 rows × 10 holdings × 3 ref markers = ~900 entries). `select_citations` is O(n log n) per call; called once per row + once per constituent + once per discipline-row = O(rows × (top_N + 2)) calls ≈ O(30 × 12) ≈ O(360) calls. Each call processes ≤ ~20 evidence entries. Total renderer cost is well under a second.
- **Alias builder performance.** O(rows × aliases_per_row) where aliases_per_row ≈ 3 (instrument) + 2 × top_N (constituents) ≈ 23. For ~30 publishable rows ≈ O(700) inserts per memo render. Negligible.
- **Dependencies.** No new third-party. Uses stdlib only (dataclasses, frozenset, dict).
- **I/O surface.** No new I/O. Renderers consume already-loaded data and return strings; `pipeline.py::run_memo` / `_write_opportunity_outputs` still own the `atomic_write_text` calls.
- **Determinism (locked by MASTER-SPEC AC9).** `select_citations` produces the same 3-entry output across shuffled input orders (item 002 invariant). Evidence_pool and picks_table cite the same 3 `citation_id`s per instrument (the SAME-3 invariant — see Q2). Appendix subsection ordering is deterministic (pick-row order, then `instrument_id` ascending). Constituent ordering within a fund is deterministic (`weight_pct` desc, `symbol` asc tiebreaker). Two runs over the same input data produce byte-identical `memo.md` + `discipline_report.md`.

## Acceptance criteria

Each criterion is independently verifiable by a test.

### D1a — evidence_pool citation markers

1. **`[ref:{citation_id}]` markers appear.** Given an `OpportunityRow` with 5 `thesis_evidence` entries (mix of data + information), `build_evidence_pool([row], [], [], None)` produces a pool containing at least one line with the regex `\[ref:[0-9a-f]{16}\]`. The selected `citation_id`s match `{e.citation_id for e in select_citations(row.thesis_evidence, cap=3)}` exactly (set equality).

2. **`[stock:{symbol}]` tag appears only for constituent-scope entries.** Given a row with mixed-scope evidence (1 fund-NAV `scope="instrument"` + 2 constituent-filings `scope="constituent"` with `constituent_key="600519"`), the evidence-pool lines for the two constituent entries start with `[stock:600519] [ref:...]`; the fund-NAV line starts with `[ref:...]` (no `[stock:]` prefix). Locked spacing: exactly one space between `[stock:...]` and `[ref:...]`.

3. **Old format rejected by the audit.** The format `[ref:filing:600519]` (item 002 explicitly rejected) does NOT appear in any evidence_pool output. Locked by a regression test: grep the output for `\[ref:[a-z_]+:` (non-hex characters after `[ref:`) → must match nothing.

4. **No URL parenthetical when url is empty.** Given a `ThesisEvidence` with `url=""` (e.g. a fund announcement from `fund_announcement_em` per ADR 0002 §1), the rendered line is `[ref:{citation_id}] {type} · {source} · {date}: {summary}` — no trailing `()` empty parenthetical.

5. **SAME-3 invariant.** Build a row with 8 `thesis_evidence` entries. Call `_build_pick_rows([{"target":iid,...}], opportunity_dict, scoring_dict)` → take the resulting `pick_row.citations`. Call `build_evidence_pool([op_row_dict], [], [{"target":iid,...}], None)` → parse the `[ref:...]` markers from the evidence_pool line for `iid`. Assert the two sets of `citation_id`s are IDENTICAL (set equality, length 3 each).

6. **Watchlist exclusion.** Given a row with `opportunity_state == "small_watch"` and `plan_trades` does NOT reference it, the evidence_pool output contains NO line for the instrument's `iid` — the existing behavior is preserved. The instrument's constituents still appear in the appendix (D3b) because the appendix iterates `publishable_rows`, not `pick_rows` alone.

### D1c — aliases.py

7. **`build_alias_maps` returns correct shape.** Given 3 publishable rows (`005827 易方达蓝筹精选` with 2 constituents `600519 贵州茅台`, `300750 宁德时代`; `163417 兴全合润` with 2 constituents `600519 贵州茅台`, `601318 中国平安`; `518880 黄金ETF` with 0 constituents): `build_alias_maps(rows)` returns `(instrument_aliases, constituent_aliases)`. Assertions:
   - `instrument_aliases["005827"] == "005827"`, `instrument_aliases["易方达蓝筹精选"] == "005827"`, `instrument_aliases["163417"] == "163417"`, `instrument_aliases["518880"] == "518880"`.
   - `"" not in instrument_aliases` (no empty-string key).
   - `constituent_aliases["600519"] == frozenset({("005827","600519"), ("163417","600519")})` (multi-owner).
   - `constituent_aliases["贵州茅台"] == frozenset({("005827","600519"), ("163417","600519")})` (Chinese-name parity with symbol).
   - `constituent_aliases["300750"] == frozenset({("005827","300750")})` (single owner — still wrapped in frozenset).
   - `"" not in constituent_aliases` (no empty-string key).

8. **`InstrumentAliasCollisionError` raised at builder time.** Construct two rows whose `name_cn` collides (e.g. two unrelated funds both named `"易方达蓝筹精选"` due to a malformed `opportunity_report.json`). `build_alias_maps(rows)` raises `InstrumentAliasCollisionError` whose message contains BOTH `instrument_id` values. The raise happens AT BUILD time, NOT at lookup time — the test catches the raise on the `build_alias_maps()` call itself.

9. **`InstrumentAliasCollisionError` raised on duplicate instrument_id collision.** Construct two rows with the SAME `instrument_id="005827"` (a bug in upstream H3 partition). `build_alias_maps(rows)` does NOT raise (the alias key `"005827"` resolves to the same `instrument_id` from both rows — no collision). This is the documented soft-collision case (item 007 trusts item 006's H3 partition to dedupe upstream).

10. **`find_uncited_conclusions` empty-map RuntimeError.** `find_uncited_conclusions(prose="...", cited_map={...}, instrument_aliases={}, constituent_aliases={}, constituent_cited_map={...})` raises `RuntimeError` whose message contains `"empty instrument_aliases"` and `"D1c"`.

11. **`find_uncited_conclusions` non-empty map does not raise.** `find_uncited_conclusions(prose="...", cited_map={...}, instrument_aliases={"005827":"005827"}, constituent_aliases={}, constituent_cited_map={...})` does NOT raise — the empty-map check guards against the builder-not-running bug, NOT against a sparse universe. Empty `constituent_aliases` is permitted (a publishable run may legitimately have zero active funds).

### D3a — discipline nested thesis_evidence bullets

12. **`_render_section` emits nested bullets.** Given a `DisciplineRow` with 5 `thesis_evidence` entries, the rendered section contains EXACTLY 3 nested bullets (the top-3 via `select_citations`), each in the format `  - [ref:{citation_id}] {type} · {source} · {date}`. The `citation_id` set matches `{e.citation_id for e in select_citations(row.thesis_evidence, cap=3)}`.

13. **Active-fund row uses flattened thesis_evidence.** A row with `asset_class="cn_equity_fund"` and 3 `constituent_analyses` (each with 2 evidence entries = 6 total in `row.thesis_evidence`): the 3 nested bullets are drawn from `select_citations(row.thesis_evidence, cap=3)` — the selector picks across the union, not per-constituent.

14. **Empty thesis_evidence renders no bullets.** A `DisciplineRow` with `thesis_evidence == ()` renders the parent line only, no nested bullets, no `（无）` placeholder. No crash.

15. **SAME-3 invariant with picks-table.** For the same row, the `citation_id` set in the discipline `_render_section` nested bullets matches the `citation_id` set in the corresponding `PickRow.citations` (when the row is also a pick). This locks the three-surface consistency (evidence_pool + picks_table + discipline_report) on `citation_id`.

### D3b — inline top-5 + 持仓明细 appendix

16. **Inline top-5 holdings.** Given a row with `constituent_analyses` of 8 entries (weights 8.2, 7.1, 6.5, 5.0, 4.2, 3.8, 3.0, 2.5), the discipline section emits exactly 5 inline `- {symbol} {name_cn} (权重 {weight_pct}%): {one_line_view}` lines under a `- 持仓 (Top 5):` header, ordered by weight descending. The 3 tail holdings (3.8, 3.0, 2.5) do NOT appear inline.

17. **Inline top-5 failure rendering.** For a constituent in the inline-5 with `evidence == () AND failure_reasons == ("filing_fetch_failed:600519",)`, the line reads `- 600519 贵州茅台 (权重 6.5%): ❌ filing_fetch_failed:600519` (no `one_line_view`).

18. **Inline top-5 audit-error rendering.** For a constituent in the inline-5 with `audit_errors == ("missing_constituent_record:600519",)`, the line reads `- 600519 贵州茅台 (权重 6.5%): {one_line_view} ⚠️ missing_constituent_record:600519`.

19. **`## 持仓明细` appendix appears.** `compose_discipline_markdown(rows, today)` output contains a `## 持仓明细` section AFTER `_DRAWDOWN_NOTE_CN` (the last line of the existing rendering). Empty case: if `publishable_rows` has zero active-fund rows AND zero rows with `constituent_analyses != ()`, the appendix header still appears with body `（无）`.

20. **Appendix lists all top-N (default 10).** For a row with 10 constituents, the appendix subsection for that row contains exactly 10 bullet lines (one per constituent), NOT 5. The full record is in the appendix; the inline-5 is the readability cap.

21. **Appendix ordering — pick-row order first.** Given 3 publishable funds A, B, C where the pick table renders them in order `[B, A, C]`, the appendix subsections appear in the same order: `### B → ### A → ### C`. Non-pick publishable funds (e.g. small_watch with constituent_analyses) appear AFTER, in `instrument_id` ascending order.

22. **Appendix per-constituent format precedence.** A row whose constituents include:
    - `c1` with `evidence=(e1,e2), failure_reasons=(), audit_errors=()` → line: `- {c1.symbol} {c1.name_cn} (权重 {c1.weight_pct}%): {c1.one_line_view} [ref:{e1.citation_id}] [ref:{e2.citation_id}]`.
    - `c2` with `evidence=(), failure_reasons=("filing_fetch_failed",), audit_errors=()` → line: `- {c2.symbol} {c2.name_cn} (权重 {c2.weight_pct}%): ❌ filing_fetch_failed`.
    - `c3` with `evidence=(e3,), failure_reasons=(), audit_errors=("missing_constituent_record",)` → line: `- {c3.symbol} {c3.name_cn} (权重 {c3.weight_pct}%): ⚠️ audit_error: missing_constituent_record`.
    - `c4` with `evidence=(), failure_reasons=(), audit_errors=()` → line: `- {c4.symbol} {c4.name_cn} (权重 {c4.weight_pct}%): ⚠️ audit_error: missing_constituent_record` (defensive — this case SHOULD be blocked by item 006's Policy B before reaching the renderer, but the renderer never crashes on it).

23. **Appendix scope = publishable only.** Given a gapped row (`evidence_gaps=("qdii_information_unavailable",)`), the appendix contains NO subsection for that row. The row appears in the failure section (`## 证据不足 / Failed fetch`) per item 006's H3 invariant.

24. **`[ref:{citation_id}]` uses full 16 hex chars.** All `[ref:...]` markers in the appendix, evidence_pool, and discipline nested bullets use 16-char hex `citation_id`s (matched by regex `\[ref:[0-9a-f]{16}\]`). No 8-char truncation. Locked by Q7.

### MASTER-SPEC AC9 — determinism

25. **`select_citations` shuffle-invariant.** Build two `thesis_evidence` tuples that differ only in element order. Pass each through `build_evidence_pool` for the same row → the `[ref:...]` marker sequences are byte-identical. Pass each through `_render_section` → byte-identical nested bullets. Pass each through `_render_appendix_subsection` → byte-identical appendix lines. (Test reuses item 002's selector determinism contract.)

26. **`memo.md` two-run byte equality.** Run the full memo pipeline twice on the same `opportunity_report.json` + `trade_plan.yaml` + `scoring_report.json`. `sha256(memo.md_run_1) == sha256(memo.md_run_2)`.

27. **`discipline_report.md` two-run byte equality.** Same as #26 for the discipline report.

### MASTER-SPEC AC5 — per-stock analysis appendix

28. **Every active-fund row has a `## 持仓明细` subsection with all top-N.** For every publishable row with `asset_class="cn_equity_fund"`, the appendix contains a `### {instrument_id} {name_cn} (cn_equity_fund)` subsection with one bullet per constituent in `constituent_analyses`.

29. **Constituents with neither evidence nor failure_reasons render the audit-error sentinel.** Test fixture: a constituent with `evidence=() AND failure_reasons=() AND audit_errors=()`. The renderer emits the `⚠️ audit_error: missing_constituent_record` sentinel (defensive — item 006 should have blocked it via Policy B rule 2, but the renderer handles the case, NEVER silently skips).

## Edge cases (locked by spec; tested in plan phase)

- **`row.thesis_evidence == ()` AND `row.constituent_analyses == ()`.** Renderer emits parent line only, no nested bullets, no inline-5 block, no appendix subsection. Defensive — shouldn't happen on publishable rows post-item-009-gate.

- **Top-N < 5.** A fund with `constituent_analyses` length 3: inline-5 renders all 3; appendix lists all 3. The `(Top 5)` header label adapts to `(Top 3)` if you want — but keep it as `(Top 5)` for stable rendering (the cap is 5; smaller universes just show fewer). Locked as `(Top 5)` literal.

- **Top-N == 0 on an active-fund row.** This is the H2.v2 `incomplete_constituent_record` audit-error case — item 006's Policy B stamps `evidence_gaps=("incomplete_constituent_record",)`, the row is gapped, and the renderer never sees it. If it somehow leaks through (programming error in upstream), render parent line only, log nothing (purity).

- **`name_cn` empty on a constituent.** Skip the name-alias entry in `constituent_aliases`; the symbol-alias entry still exists. Rendered appendix line uses empty name: `- 600519  (权重 6.5%): ...` — visually weird but not broken.

- **`name_cn` empty on a row.** Skip the name-alias entry in `instrument_aliases`; the `instrument_id`-alias entry still exists. Appendix subsection header is `### 005827  (cn_equity_fund)` — visually weird but not broken.

- **Multi-owner constituent in the appendix.** A stock held by two funds appears TWICE in the appendix (once per fund subsection), with potentially different `one_line_view` (since the analysis is fund-specific). The `[ref:...]` markers come from the per-fund `select_citations(c.evidence, cap=3)` — different fund context, different citation_ids (item 002's preimage includes `owner_instrument_id`).

- **`fund_announcement_em` URL-less citation.** Per ADR 0002 §1, AkShare's announcement endpoints have no `url` column; `ThesisEvidence.url=""` and the preimage uses `summary[:64]` fallback. Rendered line: `[ref:{citation_id}] announcement · 公告 · 2026-03-31: [report_id] title` — no trailing `()`. Locked by AC4 above.

- **Constituent with `evidence != () AND failure_reasons != ()` (partial-success case).** Per item 006's Policy B rule 5 + criterion 14, this is the realistic adapter-failure path (e.g. filing succeeded, broker failed). The row may still be publishable under Policy B if the data leg succeeded for all top-N AND the info-leg quorum is met for the material top-half. The appendix bullet renders BOTH the evidence ref markers AND the failure_reasons:
  ```
  - 600519 贵州茅台 (权重 6.5%): {one_line_view} [ref:abc123...] [ref:def456...] (filing succeeded; broker_fetch_failed)
  ```
  Trailing parenthetical with `failure_reasons` is appended after the ref markers when both are present. NEW format precedence rule (overrides #22 above): if `evidence != () AND failure_reasons != ()`, render evidence-with-failures format.

## Open questions resolved during brainstorming

### Q1 — `[stock:{symbol}]` tag placement (locked)

**Locked format:** `[stock:{symbol}] [ref:{citation_id}] {type} · {source} · {date}: {summary} ({url})` — single space between `[stock:...]` and `[ref:...]`, single space between `[ref:...]` and display text. The `[stock:...]` tag is OPTIONAL (only emitted when `scope == "constituent"`) and lives FIRST (before `[ref:...]`) so a single regex (`^(?:\[stock:[^\]]+\] )?\[ref:[0-9a-f]{16}\]`) can extract the citation and the optional stock context in one pass — easier for the audit (item 009) than embedding `[stock:...]` after `[ref:...]`.

**Rationale.** The stock symbol is metadata about the citation context (which holding does this filing cover?), the `[ref:...]` is the citation primary key. Placing the contextual tag BEFORE the primary key matches the natural reading order ("for stock X, here's the citation"). Locked by AC2.

### Q2 — `select_citations` SAME-3 invariant (locked)

**Locked invariant.** Both `_build_pick_rows` (item 002, shipped) and `build_evidence_pool` (item 007, this slice) MUST consume the IDENTICAL input: `OpportunityRow.thesis_evidence` reconstructed from `opportunity_report.json` via `_evidence_from_dict`. NO pre-filtering, NO pre-sorting, NO pre-deduplication at the consumer level. If a future contributor wants to drop URL-less entries or restrict scope, the filter MUST live inside `select_citations` itself (single locus of truth).

**Rationale.** The selector is pure; identical input → identical output. The SAME-3 invariant breaks SILENTLY if either consumer pre-processes the tuple (e.g. drops `scope="asset_class_macro"` entries before passing in). The regression test (AC5) feeds both consumers the same tuple via the production `_build_pick_rows` / `build_evidence_pool` code paths and asserts set equality on the resulting `citation_id`s. Most surprising tension uncovered (see Report).

### Q3 — `## 持仓明细` appendix ordering (locked)

**Locked.** Appendix subsection order = pick-row order (the order `_build_pick_rows` emits from `trade_plan.yaml`), then `instrument_id` ascending for publishable rows not in `pick_rows` (e.g. small_watch with `constituent_analyses != ()`). Within each subsection, constituents ordered by `weight_pct` descending, `symbol` ascending tiebreaker.

**Rationale.** Pick-row order reflects the user's mental model ("the picks I'm acting on today"); listing the appendix in that same order avoids forcing the reader to context-switch between memo §5 and appendix. The fallback to `instrument_id` ascending for non-pick publishable rows is deterministic + greppable for monitoring.

### Q4 — `InstrumentAliasCollisionError` at builder time (locked)

**Locked.** The collision check happens at the END of `build_alias_maps`, BEFORE return. The function builds a working `dict[str, str | set[str]]` where collisions accumulate; if any final value is a set with cardinality > 1, raise `InstrumentAliasCollisionError(alias, sorted_iids)`.

**Rationale.** Building the alias map ONCE per memo render is cheap (O(700) inserts; see Constraints). The collision invariant is loud and fail-fast: an upstream bug that produces duplicate `name_cn` across two unrelated funds surfaces immediately at builder time, not later when a memo paragraph's lookup happens to hit the colliding alias. Lazy-at-lookup would mean some runs pass and some fail depending on which paragraph contains which alias — flaky and silent.

### Q5 — `ambiguous_constituent_reference` is item 009's emission (locked)

**Locked.** Item 007 builds the multi-owner `frozenset` (AC7 above) and documents the contract: "when a memo paragraph mentions a stock whose `constituent_aliases` value has cardinality > 1, AND the section-header context cannot disambiguate, item 009's `find_uncited_conclusions` returns `NumericFinding(kind="ambiguous_constituent_reference", instrument_id="?", prose_excerpt=..., evidence_excerpt=alias_keys_joined)`."

Item 007's tests do NOT verify the emission of this finding (that's item 009's E16). Item 007's tests only verify that the multi-owner frozenset is correctly constructed — the precondition for item 009 to emit the finding.

**Rationale.** Slice boundary: item 007 is renderers + alias-builder. Item 009 is audit gates. The `kind="ambiguous_constituent_reference"` is an audit verdict, which is item 009's territory by the source diagnosis's slice boundary.

### Q6 — `audit_errors` rendering in `## 持仓明细` (locked, BUT see OQ2)

**Locked format.** `- {symbol} {name_cn} (权重 {weight_pct}%): ⚠️ audit_error: {audit_errors_joined}` — see AC22.

**Open issue (OQ2, deferred to planner).** Item 006's spec says `ConstituentAnalysis.audit_errors` is populated by `evaluate_policy_b` via `dataclasses.replace` and stamped on a NEW `ConstituentCoverageEntry` (NOT on the source `ConstituentAnalysis` — the cached snapshot stays byte-identical). But item 007's renderer reads `OpportunityRow.constituent_analyses[*].audit_errors`. There's a wiring question: does item 006's Policy B ALSO stamp `audit_errors` on the `OpportunityRow.constituent_analyses` it passes to `_write_opportunity_outputs`? Or does item 007 need to consume `RejectionRecord.constituent_coverage[*].audit_errors` from item 006's `rejections.json`?

**Decision (locked here):** Item 007's renderer reads `c.audit_errors` from `ConstituentAnalysis`. The planner MUST verify (or, if missing, add the wiring) that item 006's `_build_rows` patches `row.constituent_analyses` via `dataclasses.replace(c, audit_errors=...)` for the publishable subset BEFORE the row reaches `_write_opportunity_outputs`. If item 006 only stamps the rejection-record, item 007 needs a small wiring patch in `_write_opportunity_outputs` that re-runs Policy B on publishable rows to populate `audit_errors` for the renderer. Flagged in OQ2 for the planner.

### Q7 — `citation_id` uses full 16 hex chars (locked)

**Locked.** Full 16 hex chars per ADR 0001 §2. No truncation to 8.

**Rationale.** The audit (item 009's `find_hallucinated_citations` + `find_uncited_conclusions`) matches `[ref:{citation_id}]` markers against `CitedMap` keyed by full 16-char ids. Truncating to 8 chars in the rendered output would force the audit to do prefix matching, which (a) is slower, (b) creates ambiguity if two ids share a prefix (2^32 collision space is small enough that this matters in practice). The 16-char visual cost in markdown is acceptable; markdown readers don't read the hex by hand.

### Q8 — `ConstituentAliases` shape: `frozenset` with mandatory sort at traversal (locked — grill outcome)

**Locked shape.** `dict[str, frozenset[tuple[str, str]]]`. The frozenset stores `(instrument_id, constituent_key)` tuples for every fund in the publishable set that holds the same stock. Storage is unordered; **any traversal that affects rendered output OR audit-finding emission MUST `sorted(fs)` first.** Canonical sort: `(instrument_id, constituent_key)` ascending. See [ADR 0004 §1](../../adr/0004-renderer-determinism-and-alias-policy.md).

**Rationale.** Frozenset iteration order is hash-dependent, not insertion-dependent. The map is in-memory only — no serialisation round-trip would force a canonical storage order. Sort-at-traversal is the cheaper contract. Alternatives considered (sorted-tuple, list, dict-of-set) rejected — see ADR 0004 §1.

**Item 007's responsibility.** Build the frozenset correctly. Item 007's renderer does NOT iterate `ConstituentAliases` (the renderer reads `OpportunityRow.constituent_analyses` directly). Item 009 owns the lookup site; its tests must include a multi-owner fixture and assert byte-stable finding emission across runs.

### Q9 — Lookup signature for section-header disambiguation (locked — grill outcome)

**Locked: item 007 ships the BUILDER ONLY. Item 009 ships the LOOKUP.** The proposed lookup signature for item 009 to consume:

```python
def lookup_constituent(
    name_or_symbol: str,
    constituent_aliases: ConstituentAliases,
    *,
    current_instrument_id: str | None = None,
) -> str | frozenset[tuple[str, str]] | None:
    """If the alias resolves to a single (instrument_id, constituent_key)
    tuple, return that constituent_key directly. If multi-owner and
    current_instrument_id matches one tuple, return that tuple's
    constituent_key (disambiguated by section context). Otherwise return
    the full frozenset (caller must emit `ambiguous_constituent_reference`).
    Returns None when the name is not an alias.
    """
```

Item 007 does NOT implement `lookup_constituent`. The signature is documented here so item 009's planner inherits the contract verbatim — the spec captures the disambiguation rule item 009 must implement.

### Q10 — `compose_discipline_markdown` signature change for appendix wiring (locked — grill outcome)

**Issue uncovered during code-grill.** The current signature is `compose_discipline_markdown(rows, date) -> str`. The new `## 持仓明细` appendix needs the pick-row order from `_build_pick_rows` (item 002) to satisfy Q3 / AC21 ("appendix subsection order = pick-row order first"). But `_build_pick_rows` lives in `memo_cmd.py` (memo pipeline), while `compose_discipline_markdown` is called from `opportunity_cmd.py::_write_opportunity_outputs` — a DIFFERENT pipeline entry point.

**Locked solution.** Two-step:

1. **Signature extension (item 007 commits):**
   ```python
   def compose_discipline_markdown(
       rows: tuple[DisciplineRow, ...],
       date: str,
       *,
       publishable_rows: tuple[OpportunityRow, ...] = (),
       pick_order_iids: tuple[str, ...] = (),
   ) -> str:
   ```
   New keyword-only params with empty defaults preserve backward compatibility. When BOTH are empty (legacy call), the appendix renders with `instrument_id` ascending order (no pick-row priority) — the renderer still produces a valid appendix, just with a less-ergonomic ordering.

2. **Call-site wiring (item 007 commits in `opportunity_cmd.py::_write_opportunity_outputs`):** Compute `pick_order_iids` from the same `trade_plan.yaml` loader that `memo_cmd.py::run_memo` uses — `_load_trade_plan(repo_root)` returns the list of `(target, ...)` dicts; `pick_order_iids = tuple(t["target"] for t in trade_plan if t.get("target"))`. The trade plan is the single source of truth for pick order; both `memo_cmd` and `opportunity_cmd` read it.

   `publishable_rows` is already in scope at the `compose_discipline_markdown` call site (line 1087 of `opportunity_cmd.py` — partitioned earlier in `_write_opportunity_outputs`).

**Rationale.** The "pick-row order" is data, not coupling — pulling `_build_pick_rows` from `memo_cmd` into `opportunity_cmd` would create a memo→opportunity dependency that the architecture rejects (opportunity is upstream of memo). Reading the trade plan in both pipelines is the right factoring; it is already the case for `memo_cmd`. The renderer signature stays composable.

**Alternative considered.** Defer the wiring to item 008 (E sweep) and ship the appendix in `instrument_id` ascending order only. Rejected — AC21 is testable as part of item 007; deferring would leave a load-bearing UX choice (pick-row order matches the operator's mental model) under-specified and require a follow-up PR.

## Open questions for the planner

### OQ1 — `_evidence_from_dict` promotion (sharpened post-grill)

**Code-grill finding.** `_evidence_from_dict` already exists in TWO production locations:
- `src/irc/fundamentals/snapshot_cache.py:148` (item 003's cache loader)
- `src/irc/commands/memo_cmd.py:262` (item 002's `_build_pick_rows` consumer)

Item 007 adds a THIRD consumer: `build_evidence_pool` (and its caller in the memo pipeline that must hand `select_citations` the dataclass form, not the dict form). Three copies of the same JSON→dataclass rebuilder is one too many — promotion is no longer "nice-to-have", it is a load-bearing dedup.

**Locked direction.** Promote to `@classmethod ThesisEvidence.from_dict(d: dict) -> ThesisEvidence` in `src/irc/fundamentals/types.py` (where `ThesisEvidence` itself lives — not `src/irc/opportunity/types.py` which only re-exports it). Update both existing call sites (snapshot_cache.py:148, memo_cmd.py:262) AND the new item 007 call site to consume the classmethod. The planner picks the implementation order: ideally the classmethod lands FIRST (a single-commit dedup), then item 007's renderer changes consume it.

**Why `irc.fundamentals.types`, not `irc.opportunity.types`.** `ThesisEvidence` is defined in `irc.fundamentals.types`; `irc.opportunity.types` re-exports it. The classmethod is the dataclass's own constructor — it belongs on the source-of-truth module. The re-export keeps consumers working unchanged.

### OQ2 — `ConstituentAnalysis.audit_errors` wiring

See Q6 above. The planner verifies item 006's `_build_rows` patches `row.constituent_analyses` via `dataclasses.replace` for the publishable subset, OR adds the patch as part of item 007. If the patch is added in item 007, it lives in `_write_opportunity_outputs` (a copy-once-replace pattern, no in-place mutation), and the AC test fixture forces a Policy B audit-error to surface on a publishable constituent.

### OQ3 — Watchlist (small_watch) handling in the appendix

The appendix iterates `publishable_rows` from item 006's H3 partition. Watchlist rows (small_watch state) are publishable but excluded from the evidence-pool (existing behavior). Question: do they get an appendix subsection? Locked answer: YES, if `constituent_analyses != ()` — the user explicitly wants per-stock analysis for all disclosed holdings of all active funds, regardless of action state. AC21 covers this (non-pick publishable funds appear after pick-row funds in `instrument_id` ascending order). The planner verifies the test fixture covers a small_watch row.

### OQ4 — `(Top 5)` literal vs adaptive label

Spec locks `(Top 5)` as a fixed literal even when `len(constituent_analyses) < 5`. Planner may revisit if user feedback during /verify shows confusion. Low-risk; deferrable.

## Dependencies on other items

- **Depends on item 002 (merged).** `select_citations`, `ThesisEvidence` provenance fields (`citation_id`, `scope`, `citation_kind`, `owner_instrument_id`, `parent_fund_id`, `constituent_key`), `_evidence_from_dict`, `_build_pick_rows` returning `(pick_rows, absent, gapped)`.
- **Depends on item 003 (merged).** `ConstituentAnalysis` shape, `OpportunityRow.constituent_analyses`, `ThesisCard.constituent_analyses`, flattened `OpportunityRow.thesis_evidence` for active-fund rows.
- **Depends on item 005 (merged).** Fund-level NAV + announcement `ThesisEvidence` entries for gold/cn_bond_fund/cn_etf/tracked indices (so `row.thesis_evidence` for instrument-scope rows is non-empty).
- **Depends on item 006 (merged).** `OpportunityRow.evidence_gaps` populated by Policy B, H3 partition (`publishable_rows` vs `gapped_rows`), `ConstituentAnalysis.audit_errors` stamping (OQ2).
- **Blocks item 009 (D2).** `find_uncited_conclusions` empty-map RuntimeError is the precondition for item 009's gate to function without the silent-no-op failure mode. `build_alias_maps` is the named producer item 009's gate consumes.
- **Independent of item 008 (E sweep), item 010 (DuckDB holdings ingest).** Item 008 may add tests that exercise item 007's renderers end-to-end (covered there, not here).

## Files touched (preview for planner)

| File | Change |
|---|---|
| `src/irc/memo/evidence_pool.py` | Extend `_format_instrument_evidence` to optionally take `row.thesis_evidence` (or extend `build_evidence_pool` to append citation lines after each instrument's state-codes line). Use `select_citations(thesis_evidence, cap=3)`; format each entry as `[stock:{symbol}] [ref:{citation_id}] {type} · {source} · {date}: {summary} ({url})`. Skip `[stock:...]` when `scope != "constituent"`; skip ` ({url})` when `url == ""`. |
| `src/irc/memo/aliases.py` (new) | `InstrumentAliasCollisionError` class. `build_alias_maps(rows) -> (InstrumentAliases, ConstituentAliases)` pure function. Type aliases `InstrumentAliases = dict[str, str]`, `ConstituentAliases = dict[str, frozenset[tuple[str, str]]]`. |
| `src/irc/memo/numeric_audit.py` (or wherever `find_uncited_conclusions` lives) | Add empty-map RuntimeError at the top of `find_uncited_conclusions`. If the function doesn't exist yet, ship a stub (signature only + the raise + `return []`). Item 009 will fill the body. |
| `src/irc/opportunity/report.py` | Extend `_render_section` to append nested `thesis_evidence` bullets (top-3 via `select_citations`) and inline top-5 holdings (for rows with `constituent_analyses != ()`). Extend `compose_discipline_markdown` to append the `## 持仓明细` appendix section after `_DRAWDOWN_NOTE_CN`. New helper `_render_appendix_subsection(row)` + `_render_appendix_section(publishable_rows, pick_rows)` (pure). |
| `src/irc/opportunity/types.py` | (OQ1) Promote `_evidence_from_dict` to `@classmethod ThesisEvidence.from_dict(d)`. Update `_build_pick_rows` and `build_evidence_pool` call sites to use the classmethod. |
| `src/irc/memo/pipeline.py` (or wherever `run_memo` lives) | Pass already-loaded `opportunity_report.json` rows-as-dataclass into `build_evidence_pool` (i.e. reconstruct `ThesisEvidence` via `ThesisEvidence.from_dict` per row). Wire `build_alias_maps(publishable_rows)` into the `find_uncited_conclusions` call site (item 009 consumer; item 007 wires the producer side). |
| `src/irc/commands/opportunity_cmd.py` | (OQ2 — IF item 006 didn't stamp `audit_errors` on publishable `OpportunityRow.constituent_analyses` already) Add a `dataclasses.replace` patch in `_write_opportunity_outputs` to stamp `audit_errors` on publishable-row constituents from Policy B verdicts. Pure copy-replace, no in-place mutation. |
| `tests/memo/test_evidence_pool.py` | Add test for `[ref:...]` markers, `[stock:...]` tag emission/omission, SAME-3 invariant against `_build_pick_rows`, watchlist exclusion, URL-less entry rendering. |
| `tests/memo/test_aliases.py` (new) | `build_alias_maps` correctness (E14), empty-map precondition (E15), multi-owner resolution (E16), collision invariant (E17). |
| `tests/opportunity/test_report.py` | Add tests for `_render_section` nested bullets, inline top-5, `## 持仓明细` appendix structure, appendix ordering, per-constituent format precedence (evidence / failure / audit-error / mixed). |
| `tests/memo/test_determinism.py` (new or extend existing) | Two-run byte equality for `memo.md` + `discipline_report.md` (AC26, AC27). |

## Test universe (fixtures)

Reuse the canonical fixtures already established for items 002+003+005+006 where possible. Suggested new fixtures:

- **`active_fund_005827_with_8_constituents`** — 8 holdings, weights `[8.2, 7.1, 6.5, 5.0, 4.2, 3.8, 3.0, 2.5]`, all with full data+info evidence. Exercises inline top-5 + full appendix.
- **`active_fund_with_failure_constituent`** — 1 holding with `evidence=() AND failure_reasons=("filing_fetch_failed:600519",)`. Exercises `❌` rendering.
- **`active_fund_with_audit_error_constituent`** — 1 holding with `audit_errors=("missing_constituent_record:600519",)`. Exercises `⚠️` rendering.
- **`active_fund_with_partial_success_constituent`** — 1 holding with `evidence=(e1,) AND failure_reasons=("broker_fetch_failed:600519",)`. Exercises mixed-success rendering.
- **`multi_owner_constituent_universe`** — 2 funds A and B both holding `贵州茅台 (600519)`. Exercises `ConstituentAliases` multi-owner frozenset.
- **`alias_collision_universe`** — 2 funds with the same `name_cn`. Exercises `InstrumentAliasCollisionError`.
- **`hk_constituent_universe`** — 1 active fund with at least one HK 5-digit constituent (e.g. `00700 腾讯控股`). Exercises `[stock:00700]` tag emission (HK code passes through as `symbol` verbatim; no transformation).
- **`empty_alias_map_universe`** — direct call `find_uncited_conclusions(prose=..., cited_map=..., instrument_aliases={}, constituent_aliases={}, constituent_cited_map=...)` — asserts the `RuntimeError` message. No upstream fixture needed.

## Grill verdict

**Verdict: PASS** (2026-05-23, grill-with-docs auto-accept mode against [ADR 0001](../../adr/0001-citation-data-model.md), [ADR 0002](../../adr/0002-active-fund-fetch-engine.md), [ADR 0003](../../adr/0003-failure-mode-policy-b.md), [ADR 0004](../../adr/0004-renderer-determinism-and-alias-policy.md), and `CONTEXT.md`).

**Pre-grill state.** 7 internal Qs resolved; 4 OQs deferred to planner. Spec covered the renderer surfaces (D1a + D1c + D3a + D3b) and the alias-builder, but left 4 contracts under-specified that the grill surfaced:

1. **G-Q3 (audit-gate parseable appendix contract).** Spec said "every constituent shows a `[ref:...]` or a `❌`/`⚠️` sentinel" — true, but not parseable. Item 009's `find_uncited_discipline_rows` needs a REGEX contract to lock against, not a prose contract. Added §17 + 5-shape regex + `_APPENDIX_LINE_RE` module-level constant for cross-test reuse.

2. **G-Q2 + ADR 0004 §1 (frozenset determinism rule).** Spec used `frozenset` for multi-owner storage but didn't surface the trap: frozenset iteration is hash-order, not insertion. Added the "mandatory sort at traversal" rule to CONTEXT.md and ADR 0004 §1; locked the canonical sort key as `(instrument_id, constituent_key)` ascending. Item 009 inherits the contract.

3. **G-Q10 + Q10 (compose_discipline_markdown wiring).** Code-grill discovered `compose_discipline_markdown(rows, date)` does NOT receive pick_rows — and the appendix ordering (AC21) requires pick-row order. Resolved by extending the signature with two keyword-only params (`publishable_rows`, `pick_order_iids`) and committing the trade-plan load in `opportunity_cmd.py::_write_opportunity_outputs`. Backward compatible (empty defaults render in `instrument_id` order).

4. **OQ1 sharpening + ADR 0004 (`_evidence_from_dict` triplication).** Code-grill discovered the rebuilder exists in TWO production locations already (`snapshot_cache.py:148`, `memo_cmd.py:262`), and item 007 introduces a THIRD consumer. Promotion to `ThesisEvidence.from_dict` is now a load-bearing dedup, not a nice-to-have. Direction locked: classmethod lives in `irc.fundamentals.types` (where the dataclass is defined).

**Most consequential clarification.** **G-Q2 / ADR 0004 §1 — frozenset iteration is hash-order, not insertion-order.** Without the "mandatory sort at traversal" rule, item 009's `ambiguous_constituent_reference` finding's `evidence_excerpt` field would render with non-deterministic ordering — two consecutive runs would emit byte-different findings, breaking the AC9 determinism contract. The grill caught this before item 009's plan phase locked it in incorrectly. Locked in ADR 0004 §1 + CONTEXT.md "Determinism rule" + Q8 of this spec.

**Unresolved questions (none — all transferred to OQ list).** OQ1 (classmethod promotion), OQ2 (`ConstituentAnalysis.audit_errors` wiring), OQ3 (small_watch appendix coverage), OQ4 (`(Top 5)` literal vs adaptive) are the planner's territory. No further grill-level ambiguity.

**Documentation updates committed in this grill pass.**
- `CONTEXT.md` — new "Renderers + alias-builder" section (10 terms: `[ref:{citation_id}]` marker, `[stock:{symbol}]` marker, `持仓明细 appendix`, "Appendix line format precedence", SAME-3 invariant, `InstrumentAliases`, `ConstituentAliases`, `build_alias_maps`, `InstrumentAliasCollisionError`, `ambiguous_constituent_reference`, "Renderer tier-1 import contract").
- `docs/adr/0004-renderer-determinism-and-alias-policy.md` — NEW. Locks (1) frozenset shape + sort-at-traversal, (2) builder-time collision raise, (3) SAME-3 invariant.
- `docs/adr/0001-citation-data-model.md` — added cross-link to ADR 0004 in "Related ADRs".
- `docs/2026-05-22-thesis-cards-evidence-gap/items/007-spec.md` — added §17 (audit-gate parseable appendix contract), Q8 (frozenset shape lock), Q9 (lookup signature for item 009), Q10 (compose_discipline_markdown wiring), sharpened OQ1, added 2 new test fixtures (`hk_constituent_universe`, `empty_alias_map_universe`), this Grill verdict section.
