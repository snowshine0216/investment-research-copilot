# Item 009 spec — citation audit gate (Slice D2)

**Source slice:** `docs/diagnosis-thesis-cards-evidence-gap.md` lines 206–212 (Slice D2 "Audit gate (structured, not theatrical)"), three sub-items D2a / D2b / D2c.
**Master-spec line:** `009 | citation-audit-gate` (one-liner: "wire find_uncited_* + find_missing_* + find_incomplete_* into opportunity-stage and memo-stage gates, gated by `IRC_CITATION_ENFORCE_MODE` with default `block` on canonical paths").
**Branch:** `autodev/thesis-evidence-009-citation-audit-gate` (cut from feature branch `autodev/thesis-cards-evidence-gap` after grill).
**Dependencies in:** items 001–008 merged on the feature branch — in particular item 002 (`CitationMeta`, `build_cited_map`), item 007 (`build_alias_maps`, `find_uncited_conclusions` stub), and item 008 (publishable-set lockdown baseline). **Dependents out:** none — this is the terminal D-slice item.

## 1. Goal

Replace the run-wide "any valid citation passes" anti-pattern with **four structural audit functions** and **two fail-closed gates** (opportunity-stage and memo-stage) that block any publishable artifact whose conclusions cannot be tied — per-instrument and per-dimension — to a `CitationMeta` entry in the `CitedMap` produced by item 002's `build_cited_map`. The gate must be load-bearing in production: `IRC_CITATION_ENFORCE_MODE` defaults to `block` and is honoured `warn` / `off` only on non-canonical scratch paths. `outputs/<date>/citation_audit.json` is written in all modes so the shadow log is observable even when the gate is hard-blocking.

## 2. What's already in place

Item-by-item dependency confirmation read off the feature branch as of item 008 merge:

| Surface | Source | Provided by |
|---|---|---|
| `CitationMeta` dataclass + `CitedMap` / `ConstituentCitedMap` type aliases | `src/irc/opportunity/types.py:117-139` | Item 002 |
| `build_cited_map(rows) -> CitedMap` (with cross-owner duplicate-id detection + provenance mismatch raise) | `src/irc/opportunity/citation_map.py` | Item 002 |
| `ThesisEvidence.citation_id` (sha256[:16] preimage) + `citation_kind` `Literal["data","information"]` (no `"both"`) | `src/irc/fundamentals/types.py:53-102` | Items 001 + 003 + 005 |
| `OpportunityRow.contributing_dimensions: frozenset[str]` populated by `derive_contributing_dimensions` in `states.py` (returns subset of `{"valuation","heat","thesis","product_quality"}`) | `src/irc/opportunity/states.py:345-386` | Item 002 |
| `PickRow.citations: tuple[ThesisEvidence, ...]` with deterministic `select_citations(cap=3)` | `src/irc/memo/picks_table.py:33-46` + `src/irc/memo/citation_selector.py` | Item 002 (D0d/D0e/D0f) |
| `build_alias_maps(rows) -> (InstrumentAliases, ConstituentAliases)` with `InstrumentAliasCollisionError` fail-fast | `src/irc/memo/aliases.py` | Item 007 |
| `find_uncited_conclusions(prose, cited_map, instrument_aliases, constituent_aliases, constituent_cited_map) -> list[NumericFinding]` **stub** (returns `[]`; empty-prose short-circuit only) | `src/irc/memo/numeric_audit.py:156-190` | Item 007 (stub) — **item 009 fills the body** |
| `_write_opportunity_outputs` H3 pre-gate `raise RuntimeError(...)` on `fetch_budget_exhausted` (Step 1) | `src/irc/commands/opportunity_cmd.py:1089-1096` | Item 006 |
| `_write_opportunity_outputs` H3 partition `publishable_rows = [r for r in kept_rows if not r.evidence_gaps]` (Step 2) | `src/irc/commands/opportunity_cmd.py:1098-1100` | Item 006 |
| Item 008 publishable-set lockdown baseline (`tests/integration/test_publishable_set_lockdown.py`) with `_install_ak_call_dispatch` + `_unexpected_calls` helpers and the `_patch_memo_routes` context manager | `tests/integration/test_publishable_set_lockdown.py` | Item 008 |

**Stubs item 009 must replace:**

1. `find_uncited_conclusions` body (currently `return []` unconditionally — item 007 noted "body in item 009" verbatim at line 164).
2. `_write_opportunity_outputs` has Steps 1–2 but no Step 2 (opportunity-row gate), Step 2b (per-constituent gate), or Step 3 (discipline-row gate).
3. `memo_cmd.run_memo` calls `build_alias_maps` (item 007) but **discards** the resulting maps without ever feeding them to `find_uncited_conclusions` (see `src/irc/commands/memo_cmd.py:474-486` — the two locals `_instrument_aliases`, `_constituent_aliases` are leading-underscored exactly because the consumer doesn't exist yet).

## 3. Acceptance criteria

The four audit functions, the two gate wirings, the env-var contract, and the shadow-log writer are validated by **25 acceptance criteria** (post-grill: AC24 + AC25 added; see §6) across new tests under `tests/opportunity/test_auditor.py`, `tests/memo/test_numeric_audit.py` (extended), and the integration file `tests/integration/test_citation_audit_gate.py`. Item 008's `tests/integration/test_publishable_set_lockdown.py` stays green throughout (a hard gating contract — item 009 may not weaken any baseline AC; verified by grill Q6 — item 008's existing seed already carries dual-leg dual-scope evidence on every publishable row).

### Audit functions (D2a + D2b)

1. **`find_uncited_opportunity_rows(publishable_rows, cited_map) -> list[NumericFinding]`** lives in **`src/irc/opportunity/auditor.py`** (new module — collocated with `policy_b.py`, `citation_map.py`, `rejection_log.py`). For each `OpportunityRow` in `publishable_rows`, for each dimension key in `row.contributing_dimensions`, require ≥1 `ThesisEvidence` entry in `row.thesis_evidence` whose `(type, citation_kind, scope, owner_instrument_id)` tuple matches **both legs**:
    - **data leg:** `citation_kind == "data"` AND `scope in {"instrument","constituent"}` AND `owner_instrument_id == row.instrument_id`.
    - **information leg:** `citation_kind == "information"` AND `scope in {"instrument","constituent"}` AND `owner_instrument_id == row.instrument_id`.

   **V1 dimension-citation binding (Q1 below):** the per-dimension binding is **structural-only** in v1 — the gate requires ≥1 data entry AND ≥1 information entry **anywhere in `row.thesis_evidence`** for each contributing dimension, with NO `(type → dimension)` mapping. This is a deliberate v1 scope cut (see D1 below): the `ThesisEvidence.type` literal set `("filing","broker","news","policy","snapshot")` does not currently carry dimension-tagged values like `valuation_metric` / `heat_metric` despite the diagnosis-doc D2a text. A `(type → dimension)` map is a v2 surface and would require a producer-side change to `derive_thesis_from_evidence`. Item 009 ships the structural binding and locks the v2 contract as an open question.

   **Restriction rule:** if a contributing dimension is uncited, the gate emits a `NumericFinding(kind="missing_data_citation"|"missing_information_citation", instrument_id=row.instrument_id, prose_excerpt="dimension:<dim>", evidence_excerpt=<row.opportunity_state>)` per failing dimension. The caller (gate wiring) decides whether to drop the dimension's conclusion text from rendered output or to block the row entirely — see AC6.

2. **`find_missing_pick_citations(pick_rows, cited_map) -> list[NumericFinding]`** lives in **`src/irc/memo/numeric_audit.py`** (extends the existing module). For each `PickRow` in `pick_rows`, require ≥1 entry in `pick_row.citations` with `citation_kind == "data"` AND ≥1 with `citation_kind == "information"` — both legs from the pre-filtered top-3 returned by `select_citations`. A `PickRow` with `citations == ()` returns a single `NumericFinding(kind="missing_pick_citations", ...)`. A `PickRow` whose `citations` field carries entries pointing at a different `owner_instrument_id` than `pick_row.instrument_id` returns `kind="wrong_instrument_citation"` (provenance leak from the selector).

3. **`find_uncited_conclusions(prose, cited_map, instrument_aliases, constituent_aliases, constituent_cited_map) -> list[NumericFinding]`** body in **`src/irc/memo/numeric_audit.py`** replaces the item 007 stub. Paragraph-level audit at sentence-aware granularity (split on `\n\n` for paragraphs; inside a paragraph, scan with `[ref:{id}]` markers as proximity anchors). For each paragraph that contains an actionable keyword (item 009 hardcodes the v1 keyword set `("加速定投","正常定投","减速定投","暂停加仓","禁止买入","回避","建仓","加仓","减仓","止损")`):
    - **(a)** identify all instrument references via `instrument_aliases.get(token)` for every alias-token that appears in the paragraph;
    - **(b)** identify all constituent references via `constituent_aliases.get(token)` (returns a `frozenset[(instrument_id, constituent_key)]`); when the matched frozenset has cardinality > 1 AND no section-header context resolves the owner, emit `kind="ambiguous_constituent_reference"` and skip further checks for this constituent in this paragraph;
    - **(c)** for each instrument reference, require ≥1 `[ref:{id}]` marker in the same paragraph (or its immediate predecessor paragraph) whose `id` exists in `cited_map[instrument_id]` AND whose `CitationMeta.scope in {"instrument","constituent"}` AND `CitationMeta.citation_kind == "data"`, AND a separate marker satisfying the same predicates with `citation_kind == "information"`. Failure emits `kind="uncited_conclusion"` (no marker found) or `kind="wrong_instrument_citation"` (marker exists but resolves to a different `owner_instrument_id`);
    - **(d)** for paragraphs that contain an actionable keyword but **zero alias hits**, determine asset-class context from the nearest preceding markdown header matching `^## ([A-Z_]+|CN权益基金|CN债券基金|黄金|CN ETF)\b` (mapping table baked into the function); require ≥1 marker per asset-class with `CitationMeta.asset_class` matching the section context; emit `kind="uncited_portfolio_conclusion"` (no marker) or `kind="wrong_instrument_citation"` (asset_class mismatch).

   **Empty-map guard (load-bearing, Q3-locked):** the function raises `RuntimeError("empty instrument_aliases — D1c builder did not run; check memo_cmd wiring")` IFF `instrument_aliases == {}` AND `strict_empty_alias_check == True`. The new keyword-only parameter `strict_empty_alias_check: bool` is passed by the gate-wiring caller (`memo_cmd.py` reads it from `bool(rebuilt_op_rows)`). Default `strict_empty_alias_check=False` keeps the all-gapped pipeline state legal (item 007's resolved semantic) and preserves backward compatibility with all existing call sites — only the gate-wiring caller in `memo_cmd.py` flips it to `True` when the upstream publishable set is non-empty. The renamed-from-`_publishable_rows_present_upstream` parameter (per Q3) reads as intent-disclosing at the call site rather than implementation-leaking.

4. **`find_uncited_discipline_rows(discipline_rows, cited_map) -> list[NumericFinding]`** in `src/irc/memo/numeric_audit.py` (structural; no marker parsing). For each `DisciplineRow` in `discipline_rows`:
    - **(i)** require ≥1 entry in `row.thesis_evidence` with `citation_kind == "data"` AND ≥1 with `citation_kind == "information"`;
    - **(ii)** for each entry, validate `entry.owner_instrument_id == row.instrument_id`; for constituent-scoped entries, additionally validate `entry.parent_fund_id == row.instrument_id`. Mismatches emit `kind="wrong_instrument_citation"`.

   No `[ref:...]` marker check is applied to `note_cn`; the structural check on `DisciplineRow.thesis_evidence` is authoritative.

5. **`find_incomplete_constituent_analyses(publishable_rows) -> list[NumericFinding]`** in `src/irc/opportunity/auditor.py`. **Q9-corrected predicate (per dispatch):** the spec violation is `evidence == () AND failure_reasons != ()` (pure-failure constituent that escaped H2's gap stamp). Partial-success (`evidence != () AND failure_reasons != ()`) is NOT a violation — Policy B's per-holding data leg + top-half info quorum is the correct disposition. A finding from this function is fatal at the opportunity-stage gate (caller raises `RuntimeError`, see AC7) — kept as a structured `NumericFinding` rather than an in-function raise so the auditor module stays pure and uniformly testable.

### Audit-function behaviours (regression set)

6. **Row-level restriction rule (v1 structural).** Under the structural binding from AC1 / D1, `find_uncited_opportunity_rows` emits findings at the **row level**, not the per-dimension level: a row whose `row.thesis_evidence` lacks a data leg emits one `missing_data_citation` finding (carrying `prose_excerpt="dimension:<first dim from contributing_dimensions sorted>"` so the message is still per-dimension-informative for log readers); a row that lacks an information leg emits one `missing_information_citation`. A `core_dca` row with both legs present anywhere in `row.thesis_evidence` returns `[]` regardless of which dimension the evidence covers — this is the v1 structural binding's deliberate looseness. **A row with `contributing_dimensions == frozenset()` (empty) but `opportunity_state == "exclude"` is still subject to the row-level dual-leg check** — scoring-excluded rows still require their excluding evidence to be cited. Multi-finding-per-row (one per uncited dimension) is the v2 contract per D1 + Q1; AC9 row-blocking semantic in v1 is "either leg missing → row blocked", which is strictly stricter than the diagnosis-doc's "all dimensions uncited → block" rule and is the safer choice while structural binding ships.

7. **Pure-failure constituent fatal.** `find_incomplete_constituent_analyses` returns a `NumericFinding(kind="constituent_pure_failure", instrument_id=row.instrument_id, prose_excerpt=f"symbol={c.symbol}", evidence_excerpt="evidence=() failure_reasons=(...)")` for every `ConstituentAnalysis` with `evidence == () AND failure_reasons != ()` on a publishable row (`evidence_gaps == ()`). Partial-success constituents (both fields non-empty) and intact constituents (`failure_reasons == ()`) do not appear in the result.

8. **Memo prose paragraph-level audit positive + negative cases.** `find_uncited_conclusions` finds (a) `uncited_conclusion` when a paragraph mentions instrument `005827` plus an actionable keyword but has no `[ref:{id}]` marker resolving to `cited_map["005827"]`; (b) `wrong_instrument_citation` when the marker resolves to a different `owner_instrument_id`; (c) `wrong_instrument_citation` (sub-class: asset-class mismatch) when the marker's `CitationMeta.asset_class` disagrees with the section header context (e.g. `## CN权益基金` paragraph with a `gold` citation); (d) `uncited_portfolio_conclusion` when the paragraph carries an actionable keyword, zero alias hits, and zero markers; (e) `ambiguous_constituent_reference` when a constituent symbol resolves to ≥2 owner pairs and no section header disambiguates.

### Opportunity-stage gate wiring (D2c)

The gate is inserted into `_write_opportunity_outputs` in `src/irc/commands/opportunity_cmd.py` after Step 2 (H3 partition) and before Step 3 (the existing `atomic_write_text(opportunity_report.json)` call at line ~1117).

9. **Three-pass gate sequence.** After the H3 partition produces `publishable_rows` (Step 2), the gate runs:
   - **Step 2a — opportunity-row gate:** `cited_map = build_cited_map(tuple(publishable_rows))`; `findings = find_uncited_opportunity_rows(publishable_rows, cited_map)`. Under v1 structural binding (AC1, AC6), **any row that produces a finding has at least one leg missing → the entire row is blocked**: removed from `publishable_rows` before any serializer call AND added to `gapped_rows` with a synthesised `evidence_gaps=("citation_gate_blocked",)` so the row surfaces in `rejections.json` and the discipline-report failure section. The "drop the dimension's conclusion text, keep the row" mode from the diagnosis-doc D2a is v2 work (Open Q5).
   - **Step 2b — per-constituent gate:** `constituent_findings = find_incomplete_constituent_analyses(publishable_rows_after_step_2a)`. ANY non-empty result raises `RuntimeError("constituent_failure_in_publishable_row: " + "; ".join(f.prose_excerpt for f in constituent_findings))` — fail-closed; no `.tmp` file has been created yet. **This raise is unconditional — it ignores `IRC_CITATION_ENFORCE_MODE`** because a pure-failure constituent escaping H2 indicates a programming bug, not a citation gap (parallel to the `fetch_budget_exhausted` raise in AC10).
   - **Step 2c — discipline-row gate:** `discipline_findings = find_uncited_discipline_rows(discipline_rows, cited_map)`. ANY non-empty result triggers the gate-mode dispatch (see AC12).

10. **`fetch_budget_exhausted` pre-gate invariant remains a `raise`, not an `assert`.** The existing item 006 Step 1 (lines 1089-1096) stays as-is. Item 009 does not weaken it to `assert`; CLAUDE.md and item 008 AC12 lock the `raise` requirement.

11. **`IRC_CITATION_ENFORCE_MODE` env var.** New env var with values `{"off","warn","block"}`. Resolution function `_resolve_enforce_mode(out_dir: Path, today: str) -> str` lives at module scope in `opportunity_cmd.py` and is imported by `memo_cmd.py` (D2: import-rather-than-duplicate; same precedent as `_today`). Resolution rules (Q2-locked):
    - **Canonical-path detection (precise rule, regex-expressible):** `out_dir` is canonical IFF `out_dir.resolve().parent.name == "outputs" AND re.fullmatch(r"\d{4}-\d{2}-\d{2}", out_dir.name)`. The date component is read from `out_dir.name`, **NOT** from a wall-clock `_today()` — this handles (a) the off-by-one risk when a run launched at 23:59:30 CST has `_today() != out_dir.name`, (b) `--output-dir outputs/2026-05-22` cross-day invocations (still canonical — it's a real `outputs/<date>/` path), (c) `tmp_path` scratch dirs (not canonical — parent is not `outputs`). When canonical, the env var is **ignored** and `block` is forced.
    - **Non-canonical paths:** `os.environ.get("IRC_CITATION_ENFORCE_MODE","block")` is honoured verbatim. Unknown values fall back to `block` with a `stderr` warning of the form `WARN citation-audit: unknown IRC_CITATION_ENFORCE_MODE={value!r}; falling back to 'block'`.

12. **Gate-mode dispatch (block / warn / off).** Given any non-empty findings collection from Step 2a (post-row-blocking) or Step 2c:
    - **`block`** — raise `RuntimeError("citation_gate_blocked: " + "; ".join(...))` BEFORE any `.tmp` file is created. No artifact reaches disk.
    - **`warn`** — log all findings to stderr with prefix `WARN citation-audit: `, write the shadow log (AC13), and proceed to emit artifacts. The exit code is `0`.
    - **`off`** — write the shadow log (AC13), proceed silently.

13. **Shadow log `outputs/<date>/citation_audit.json` is written in ALL modes**, including `block` (the write is the **last** action before the `RuntimeError` is raised, ensuring the log captures the blocking findings; the write goes to `out_dir / "citation_audit.json"` via `atomic_write_text` and is independent of the canonical four artifacts). Schema:
    ```json
    {
      "run_date": "YYYY-MM-DD",
      "enforce_mode": "block|warn|off",
      "canonical_path": true,
      "out_dir": "<absolute path>",
      "opportunity_findings": [{"instrument_id": "...", "kind": "...", "prose_excerpt": "...", "evidence_excerpt": "..."}],
      "constituent_findings": [...],
      "discipline_findings": [...],
      "memo_findings": [],
      "summary": {"total": <int>, "blocking": <bool>}
    }
    ```
    The `memo_findings` field is written empty by `_write_opportunity_outputs` and populated (in-place over the existing file) by `memo_cmd.py` after its own gate runs; the file is **shared** across the two stages and serves as the audit-trail correlation key. Both stages use `atomic_write_text` so a partial file is never observable.

### Memo-stage gate wiring (D2c)

14. **Insertion site:** in `run_memo` in `src/irc/commands/memo_cmd.py`, after the synth+audit pipeline returns `output` and BEFORE the `atomic_write_text(out_dir / "memo.md", output.draft)` call at line 568. The `audit_blocks_publish` gate (the existing memo-audit / P-tier gate at line 539-567) stays in place; item 009 adds a SECOND gate downstream of it. The two gates are independent — the existing audit-blocking gate fires first; the citation gate fires only if `audit_blocks_publish` returns `False`.

15. **Memo-stage gate sequence.** After `audit_blocks_publish` clears:
    - Build `cited_map = build_cited_map(tuple(_reconstruct_opportunity_rows(rebuilt_op_rows)))` (the existing local already wires the rebuild).
    - Build `constituent_cited_map` from `ConstituentAnalysis.evidence` entries on every publishable row (same shape — `instrument_id → constituent_key → {citation_id: CitationMeta}` — built by a new small helper `build_constituent_cited_map(publishable_rows) -> ConstituentCitedMap` in `src/irc/opportunity/citation_map.py`).
    - Run `pick_findings = find_missing_pick_citations(pick_rows, cited_map)`.
    - Run `prose_findings = find_uncited_conclusions(output.draft, cited_map, _instrument_aliases, _constituent_aliases, constituent_cited_map, strict_empty_alias_check=bool(rebuilt_op_rows))`.
    - Apply the `IRC_CITATION_ENFORCE_MODE` dispatch from AC12 (against `out_dir` per AC11). Update the shared `citation_audit.json` shadow log with `memo_findings = pick_findings + prose_findings` (overlaying the existing file written by the opportunity stage).
    - On `block` with non-empty findings: behave like the existing audit-blocking gate — write `memo_blocked.md` (existing helper), remove any stale `memo.md`, print the block reasons, return exit code `2`.

16. **No regression on the existing memo audit-blocking gate.** Tests assert that an `audit_blocks_publish` failure (e.g. `审核未通过` token) still produces `memo_blocked.md` independently of citation findings; citation findings on top of an audit-failed memo are merged into the shadow log but do not change the exit shape (which is already `2`).

### `find_uncited_conclusions` regression set (D2b.1)

17. **Empty-map raises when publishable set is non-empty.** Calling `find_uncited_conclusions(prose="non empty", cited_map={...}, instrument_aliases={}, constituent_aliases={}, constituent_cited_map={}, strict_empty_alias_check=True)` raises `RuntimeError("empty instrument_aliases — D1c builder did not run; check memo_cmd wiring")`. With `strict_empty_alias_check=False` (default), returns `[]` — preserves item 007's all-gapped pipeline-state semantic.

18. **Empty-prose short-circuit preserved.** `find_uncited_conclusions(prose="", ...)` and `find_uncited_conclusions(prose="   \n  ", ...)` return `[]` regardless of all other arguments — locks item 007's existing `if not prose or not prose.strip(): return []` line.

19. **Section-header disambiguation for multi-owner constituents.** When `贵州茅台 (600519)` is held by funds A and B, and the prose has a paragraph under markdown header `### 易方达蓝筹精选 (005827)` mentioning `贵州茅台 ... 加仓`, `find_uncited_conclusions` resolves to `(instrument_id="005827", constituent_key="600519")` and checks `constituent_cited_map["005827"]["600519"]` for the dual-leg coverage. A paragraph with no section header context that mentions `贵州茅台 ... 加仓` returns `kind="ambiguous_constituent_reference"`. (E16 from the diagnosis doc lands inside this AC.)

### Test-suite invariants (cross-cutting)

20. **Item 008 baseline stays green.** `pytest tests/integration/test_publishable_set_lockdown.py -x` passes unchanged after item 009 lands. ACs 22–23 (two-run byte equality) catch any non-deterministic ordering accidentally introduced by the gate wiring (e.g. set iteration over `cited_map.values()` without a sort key).

21. **`_unexpected_calls(counter) == []` is asserted in every new integration test.** Item 008 left the sentinel un-wired (documented-only). Item 009 must adopt the assertion in `tests/integration/test_citation_audit_gate.py` for all tests that exercise the AkShare dispatcher; this closes the test-isolation hole noted in item 008's PR review.

22. **Canonical-path × mode matrix locked.** `tests/integration/test_citation_audit_gate.py::test_enforce_mode_matrix` covers (a) `canonical + block + uncited` → raises; (b) `canonical + warn + uncited` → still raises (env var ignored on canonical path); (c) `canonical + off + uncited` → still raises (env var ignored); (d) `non-canonical (scratch) + block + uncited` → raises; (e) `non-canonical + warn + uncited` → logs to stderr, writes shadow log, exits 0; (f) `non-canonical + off + uncited` → silent, writes shadow log, exits 0; (g) `canonical + block + clean` → exits 0 normally. Seven scenarios.

23. **Shadow log written in all modes including block.** A separate integration test asserts: in `block` mode with non-empty findings, `outputs/<date>/citation_audit.json` exists on disk AFTER the `RuntimeError` is raised (caught in the test); the file's `summary.blocking == True`; the four canonical artifacts (`opportunity_report.json`, `thesis_cards.yaml`, `discipline_report.md`, `rejections.json`) do NOT exist on disk (no `.tmp` file leaked).

24. **Item 008 baseline passes with citation gate live (Q6).** `pytest tests/integration/test_publishable_set_lockdown.py -x` exits zero with `IRC_CITATION_ENFORCE_MODE` unset (i.e., the default `block` is in force). Verified by grill Q6: the existing `_seed_publishable_set_repo` helper (lines 229-444 of that file) seeds dual-leg dual-scope evidence on every publishable row by construction (holdings frame → data leg via `_build_active_fund_snapshot`; announcement frame → information leg; filing frame → CN-constituent data leg; broker-report frame → CN-constituent info leg). The gate is therefore a no-op on item 008's seeds. The planner SHOULD also run `pytest -x` once with the gate live and surface any unexpected failures in `009-drift.md` (matches item 006/008 inline-fix precedent).

25. **Memo-stage `out_dir` is the write-path local, not the read-path local (Q7+F1).** `_resolve_enforce_mode` in `memo_cmd.run_memo` is called with `out_dir` (line ~534: `root / "outputs" / today` where `today = _today()` is captured once at line 409), **NOT** with `out_today` (line ~419: `scoring_path.parent`, which can resolve to a stale-date dir when scoring fell back via `_latest_file`). The shadow log is written to `out_dir / "citation_audit.json"` — the same directory the memo writes land in. Locked by a unit test that monkey-patches `_locate_scoring` / `_latest_file` to return a yesterday-dated `scoring.json` and asserts (a) `out_today.name != out_dir.name`; (b) the citation_audit.json was written under `out_dir`, not `out_today`; (c) `_resolve_enforce_mode` was called with `out_dir` (asserted via patched-callee inspection).

## 4. File-touch map

### New files

- **`src/irc/opportunity/auditor.py`** (~120 LOC) — pure-function module. Exports `find_uncited_opportunity_rows`, `find_incomplete_constituent_analyses`. Imports `NumericFinding` from `irc.memo.numeric_audit` (the dataclass is canonical there per item 007).
- **`tests/opportunity/test_auditor.py`** (~250 LOC) — covers ACs 1, 5, 6, 7. One assertion per AC pattern; uses hand-built `OpportunityRow` instances with controlled `contributing_dimensions` + `thesis_evidence` / `constituent_analyses` shapes; no `run_opportunity` invocation here (unit-test layer).
- **`tests/integration/test_citation_audit_gate.py`** (~600 LOC; budget mirrors item 008's lockdown file) — covers ACs 9, 11, 12, 13, 14, 15, 20, 21, 22, 23. Uses the `_seed_publishable_set_repo` helper from `test_publishable_set_lockdown.py` (refactor: lift the helper to `tests/integration/_publishable_set_helper.py` so both files import it — D3 below).

### Modified files (production)

- **`src/irc/memo/numeric_audit.py`** — adds `find_missing_pick_citations`, `find_uncited_discipline_rows`; replaces the `find_uncited_conclusions` stub body with the paragraph-level implementation; adds the new `strict_empty_alias_check: bool = False` keyword parameter (Q3-locked rename from `_publishable_rows_present_upstream`).
- **`src/irc/opportunity/citation_map.py`** — adds `build_constituent_cited_map(rows) -> ConstituentCitedMap`. Same provenance-check shape as `build_cited_map`.
- **`src/irc/opportunity/rejection_log.py`** (Q4-locked) — adds `"citation_gate_blocked"` to the `RejectionReasonCode` `Literal[...]` union (extending lines 23-33) AND appends an identity mapping `"citation_gate_blocked": "citation_gate_blocked"` at the END of `_GAP_TO_REASON` (lines 62-92) so existing precedence is unchanged. Same shape as `qdii_information_unavailable` / `fund_announcements_unavailable` / `missing_us_news_adapter` (identity-mapped gap codes).
- **`src/irc/commands/opportunity_cmd.py`** — adds `_resolve_enforce_mode(out_dir, today)`, `_write_citation_audit_shadow_log(out_dir, payload)`; wires Steps 2a / 2b / 2c into `_write_opportunity_outputs` between the existing H3 partition and the existing serializer calls. No changes to `run_opportunity` (signature unchanged); the gate is fully internal to `_write_opportunity_outputs`. The Step 2a-blocked row stamps `evidence_gaps=("citation_gate_blocked",)` AND is appended to `gapped_rows` BEFORE Step 4's `_classify_rejection_reason` runs, so the new `_GAP_TO_REASON` entry (above) is the resolution path. Inline `# Q5 deferral: drop-dimension-text renderer is v2 work; v1 blocks the entire row.` comment at the Step 2a emission site so future readers don't accidentally re-implement the diagnosis-doc D2a verbatim.
- **`src/irc/commands/memo_cmd.py`** — wires the memo-stage gate between `audit_blocks_publish` (line ~539) and the `atomic_write_text(memo.md)` (line ~568). Imports `_resolve_enforce_mode` from `opportunity_cmd` (D2-locked: import-not-duplicate). **F1 / Q7 lock:** passes `out_dir` (line 534, the write-path local) to `_resolve_enforce_mode`, NOT `out_today` (line 419, the read-path local). `today = _today()` is captured once at line 409 and threaded through.

### Modified files (tests)

- **`tests/memo/test_numeric_audit.py`** — adds AC2/3 unit tests for `find_missing_pick_citations` (kinds: `missing_pick_citations`, `wrong_instrument_citation`); AC4 for `find_uncited_discipline_rows`; AC8 / 17 / 18 / 19 for `find_uncited_conclusions` body.
- **`tests/integration/test_publishable_set_lockdown.py`** — **no changes expected**, but the import for `_seed_publishable_set_repo` shifts to the lifted helper module if D3 is chosen.
- **`tests/integration/_publishable_set_helper.py`** (new IFF D3 chosen) — extracted from `test_publishable_set_lockdown.py` module-level helpers; pure-function exports `_seed_publishable_set_repo`, `_install_ak_call_dispatch`, `_unexpected_calls`, `_patch_memo_routes`, `_collect_publishable_citation_universe`.

### Files explicitly NOT touched

- **`src/irc/opportunity/types.py`** — no schema changes. `OpportunityRow.contributing_dimensions` already exists (item 002).
- **`src/irc/opportunity/thesis_evidence.py`** — no producer-side change. The v1 dimension binding does not require new `type` literal values (see D1).
- **`docs/adr/0001-0004`** — no ADR amendment. ADR 0004 §1 already covers renderer determinism; the gate's frozenset iteration uses `sorted()` per the existing rule.
- **`CONTEXT.md`** — TWO paragraphs appended under a new section "Audit gates and enforcement modes" (the section is created by item 009 if it doesn't already exist — first occupant). Paragraph 1: `IRC_CITATION_ENFORCE_MODE` (env var, default `block`, canonical-path override rule, shadow log location). Paragraph 2: "Citation gate v1 dimension binding" (Q1 breadcrumb: structural-only; v2 contract sketch; Q5 dimension-conclusion-dropping renderer deferred).

## 5. Decisions made (alternatives considered)

### D1: V1 dimension-citation binding — structural vs `(type → dimension)` map

- **Option A (rejected):** Ship the diagnosis-doc D2a text verbatim: tag each `ThesisEvidence` with a dimension-specific `type` (`valuation_metric`, `heat_metric`, etc.) and require per-dimension `type`-match. Requires producer-side changes to `derive_thesis_from_evidence` and to the four scoring classifiers, plus expansion of the `ThesisEvidenceKind` literal set.
  - Con: producer-side surface is large (5 adapters × 4 dimensions = up to 20 emission sites); breaks item 003's fixture corpus; v2 territory.
- **Option B (CHOSEN):** Structural dual-leg-per-dimension binding only. For each contributing dimension, require ≥1 data entry + ≥1 information entry **anywhere in `row.thesis_evidence`** (no per-dimension `type` match). The dimension-conclusion-dropping renderer behaviour from D2a is recorded as Open Q5 (deferred to v2).
  - Pro: zero producer-side changes; locks the gate against the realistic failure mode (entire row uncited) which is what the diagnosis-doc was actually catching in the 2026-05-20 audit.
  - Con: a row with valuation+heat citations only would pass the gate even when `thesis_state` was the dominant driver — but `find_uncited_opportunity_rows` would still see all four dimensions cited as a single bag. v2 work.
- **Option C (rejected):** Skip dimension awareness entirely; just require row-level dual-leg coverage. Equivalent to AC1 collapsing `contributing_dimensions` to a single `True/False` check.
  - Why rejected: loses the diagnosis-doc's "restriction rule" (drop uncited dimension conclusions; block only if ALL uncited) — which we keep in shape at AC6 even if v1 binding is structural.

### D2: Where `_resolve_enforce_mode` lives

- **Option A (rejected):** New `src/irc/audit_modes.py` module.
  - Con: 30-line module for two functions — over-fragmentation given the project's <200-LOC-per-file budget and the fact that no other consumer needs it.
- **Option B (CHOSEN):** Define in `opportunity_cmd.py` at module scope, import into `memo_cmd.py`. Same shape as `_today()` (defined in both `opportunity_cmd.py:404` and `memo_cmd.py:146` as identical functions today — the project precedent tolerates this duplication).
  - Pro: matches existing pattern; one source of truth for the canonical-path detection logic that already lives in `opportunity_cmd._reject_limit_on_canonical`.
- **Option C (deferred):** Extend `src/irc/io_utils.py` (which currently only owns `atomic_write_text`) to be the home for "I/O-policy helpers" including canonical-path detection.
  - Why deferred: requires renaming + a CONTEXT.md term; out of scope for this item but recorded as a v2 refactor opportunity.

### D3: Lift `_seed_publishable_set_repo` to a shared helper module — or duplicate?

- **Option A (CHOSEN):** Lift to `tests/integration/_publishable_set_helper.py`. Both `test_publishable_set_lockdown.py` (item 008) and `test_citation_audit_gate.py` (item 009) import from it.
  - Pro: avoids the 200-LOC seed-helper duplication that would otherwise grow with every integration file under `tests/integration/`; lifts AC22's deterministic-time discipline (`_FIXED_INGESTED_AT`, `_BROKER_REPORT_DATE`) into a single home.
  - Con: refactor touches an existing test file — must keep item 008 ACs 22–23 byte-equal-locked through the lift.
- **Option B (rejected):** Copy-paste the helper into `test_citation_audit_gate.py`.
  - Why rejected: duplication grows linearly; the `_FIXED_INGESTED_AT` clock-discipline trick would be inevitably forgotten in the copy.

### D4: Gate insertion site in `_write_opportunity_outputs` — pre-partition vs post-partition

- **Option A (CHOSEN):** Insert after Step 2 (H3 partition) and before Step 3 (serializer call). The gate operates on `publishable_rows` only.
  - Pro: matches the diagnosis-doc D2c text ("Step 2 — opportunity-row gate ... compute `publishable_rows = [r for r in rows if not r.evidence_gaps]`"); reuses item 006's H3 partition discipline; keeps gapped rows on the rejection path untouched.
- **Option B (rejected):** Insert before Step 2 (operate on `kept_rows`).
  - Why rejected: would force the gate to know about `evidence_gaps` filtering (duplication of H3 logic); breaks the layering between Policy B classification and citation audit.

### D5: Shadow log shared file vs per-stage files

- **Option A (CHOSEN):** Single `citation_audit.json` file. Opportunity stage writes the four lists (`opportunity_findings`, `constituent_findings`, `discipline_findings`, `memo_findings=[]`); memo stage reads-modify-writes the file in place, populating only `memo_findings` and updating `summary.total` + `summary.blocking`. Atomic via `atomic_write_text`.
  - Pro: single audit-trail correlation key; trivial to grep across runs.
- **Option B (rejected):** Two files (`opportunity_citation_audit.json`, `memo_citation_audit.json`).
  - Why rejected: doubles the file count; loses the natural "summary across both stages" affordance.

### D6: `out_dir` (write-path) vs `out_today` (read-path) in memo_cmd — grill F1

- **Context:** `memo_cmd.run_memo` carries two "today's output dir" locals: `out_today = scoring_path.parent` (line 419, READ path for upstream artifacts; can resolve to a stale-date dir when scoring fell back via `_latest_file`) and `out_dir = root / "outputs" / today` (line 534, WRITE path for memo.md and friends; always uses `_today()`). This is a pre-existing design decision (item 010 / `WARNING: using stale scoring from ...` at opportunity_cmd.py:1202 acknowledges the cross-date scenario).
- **Option A (CHOSEN):** Citation gate uses `out_dir` (write path). The shadow log `citation_audit.json` lives next to the writes; canonical-path detection runs against `out_dir.name`.
  - Pro: shadow log co-located with the artifacts it audits; no cross-day write surprise.
- **Option B (rejected):** Use `out_today` (read path).
  - Why rejected: shadow log would land in a stale-date dir when scoring fell back; AC22 two-run byte equality would split the audit trail across two day folders.

## 6. Resolved open questions (grill phase)

All seven questions resolved by the grill subagent on 2026-05-23 under autonomy override. Detailed resolutions and authority sources captured in `009-grill.md`.

### Q1 — Dimension-citation binding v2 contract — RESOLVED

**Locked:** Defer to v2 via a CONTEXT.md breadcrumb under "Audit gates and enforcement modes". V1 ships the structural binding (D1 CHOSEN). No new ADR — fails the 3-of-3 ADR test (not hard to reverse; the binding is additive in v2 via `type` literal expansion).

### Q2 — Canonical-path detection rule — RESOLVED

**Locked:** `out_dir` is canonical IFF `out_dir.resolve().parent.name == "outputs" AND re.fullmatch(r"\d{4}-\d{2}-\d{2}", out_dir.name)`. Date component read from `out_dir.name`, not from wall-clock `_today()`. Handles (a) end-of-day wall-clock skew, (b) cross-day `--output-dir` invocations, (c) `tmp_path` scratch dirs. See AC11.

### Q3 — Empty-alias guard parameter naming — RESOLVED

**Locked:** Rename to `strict_empty_alias_check: bool = False` (Q3 alternative (c)). Keyword-only. Loud at the call site; no leading-underscore-as-warning crutch. The bool stays (no enum; no function split). See AC17, AC15.

### Q4 — New `RejectionReasonCode = "citation_gate_blocked"` — RESOLVED

**Locked:** Add `"citation_gate_blocked"` to both the `RejectionReasonCode` literal set AND `_GAP_TO_REASON` in `src/irc/opportunity/rejection_log.py`. Identity mapping (same shape as `qdii_information_unavailable`). Appended at the end of `_GAP_TO_REASON` so existing precedence is unchanged. See §4 "Modified files (production)".

### Q5 — Dimension-conclusion-dropping renderer behaviour — DEFERRED to v2

**Locked:** V1 scope = fail-the-row (Step 2a removes the row, stamps `evidence_gaps=("citation_gate_blocked",)`, routes to `rejections.json` + discipline failure section). Renderer follow-up documented as a v2 TODO via inline comment at the Step 2a emission site AND in CONTEXT.md "Audit gates and enforcement modes" §2 (v1 dimension binding breadcrumb). No AC churn — AC6 already locks the v1 row-blocking interpretation.

### Q6 — Item-008 baseline interaction with default `block` — RESOLVED

**Locked:** Item 008's `_seed_publishable_set_repo` (lines 229-444 of `test_publishable_set_lockdown.py`) carries dual-leg dual-scope evidence on every publishable row by construction. The gate is a no-op on item 008's seeds. No `IRC_CITATION_ENFORCE_MODE=off` env-var override needed in the harness. New AC24 locks this. Planner SHOULD run `pytest -x` once with the gate live; surface any unexpected failures in `009-drift.md` (item 006/008 inline-fix precedent).

### Q7 — Memo-stage `out_dir`-vs-`today` canonical mismatch — RESOLVED (with factual correction)

**Spec's original Q7 claim was wrong.** The actual code at `memo_cmd.py:534` is `out_dir = root / "outputs" / today`, NOT `out_dir = scoring_path.parent`. The latter is `out_today` at line 419 (a different local, used only for READING upstream artifacts). **Locked:** `_resolve_enforce_mode(out_dir, today)` uses the write-path local `out_dir`; `today = _today()` is captured once at line 409. See AC25 and D6.

## 7. Non-goals

- **No producer-side `ThesisEvidence.type` changes.** The diagnosis-doc D2a per-dimension `type` map is v2 (Q1).
- **No renderer changes to drop uncited-dimension conclusion text.** Q5 deferral; AC6 stops at finding-emission.
- **No new env var beyond `IRC_CITATION_ENFORCE_MODE`.** All four env vars from item 008 (`IRC_OPPORTUNITY_AUTOBUILD`, `IRC_CACHE_FRESHNESS_DAYS`, `IRC_FETCH_BUDGET`, `IRC_ALLOW_STALE`) stay as-is.
- **No live AkShare calls.** Integration tests use `_install_ak_call_dispatch` from item 008.
- **No changes to `audit_blocks_publish` (the existing memo audit / P-tier gate).** Item 009's citation gate runs downstream and independently.
- **No new ADR.** ADR 0001–0004 stand unmodified; the gate is a wiring of already-defined primitives.
- **No `_GAP_TO_REASON` precedence reordering.** Q4 adds one new identity-mapped entry AT THE END of the dict — existing precedence (qdii first, etc.) is unchanged. Item 008 AC11's hard-coded precedence string stays valid.
- **No v2 dimension-conclusion-dropping renderer.** Q5 deferral; the gate emits a row-blocking finding instead. CONTEXT.md "Audit gates and enforcement modes" carries the v2 breadcrumb.
- **No `run_decision` integration.** Out of scope (consistent with item 008).

## 8. Done means

1. `src/irc/opportunity/auditor.py` exists with `find_uncited_opportunity_rows` + `find_incomplete_constituent_analyses`.
2. `src/irc/memo/numeric_audit.py` adds `find_missing_pick_citations` + `find_uncited_discipline_rows`, and replaces the `find_uncited_conclusions` stub body with the paragraph-level implementation.
3. `src/irc/opportunity/citation_map.py` adds `build_constituent_cited_map`.
4. `src/irc/commands/opportunity_cmd.py` wires the three-pass gate in `_write_opportunity_outputs` with `IRC_CITATION_ENFORCE_MODE` dispatch.
5. `src/irc/commands/memo_cmd.py` wires the memo-stage gate, reading the same env var via the same `_resolve_enforce_mode` helper.
6. `outputs/<date>/citation_audit.json` shadow log is written in all modes; schema matches AC13.
7. New tests under `tests/opportunity/test_auditor.py` + extended `tests/memo/test_numeric_audit.py` + new `tests/integration/test_citation_audit_gate.py` all pass; full suite (`pytest -x`) green on the sub-branch.
8. Item 008's `tests/integration/test_publishable_set_lockdown.py` ACs 1–23 stay green (no regression of the lockdown baseline).
9. `ruff check src tests` clean.
10. `CONTEXT.md` updated with the `IRC_CITATION_ENFORCE_MODE` paragraph under "Audit gates and enforcement modes".
11. PR opens into `autodev/thesis-cards-evidence-gap`, `/ship` workflow runs verify + inline review + code-review, merges via squash.
12. **Gating contract:** item 009 ships only when the gate is live on canonical paths with no test-suite regressions; the diagnosis-doc Slice D2 is closed at item 009 merge.

## 9. Cross-item references

- **Item 008 grill Q5 vs item 009 spec §6 Q5 are DIFFERENT questions** (grill F5 disambiguation). Item 008 Q5 = "publishable citation universe excludes `rejections.json`" (universe formula, locked in CONTEXT.md "Publishable citation universe"). Item 009 Q5 = "dimension-conclusion-dropping renderer behaviour" (a v2 deferral; locked above). Both correctly scoped; no conflict.
- **Item 007 grill G-Q6 / Q7 / Q9** define the `find_uncited_conclusions` signature contract that item 009 inherits verbatim (defensive empty-map raise; section-header disambiguation; `lookup_constituent` signature). Item 009 ships the body that uses these primitives.
- **Item 002 + 003 + 007** primitives (`CitationMeta`, `build_cited_map`, `ConstituentAnalysis`, `build_alias_maps`, `select_citations`, `ThesisEvidence.from_dict`) are all consumed unchanged. Item 009 adds no producer-side primitives — only consumers (the four audit functions + two gates).
