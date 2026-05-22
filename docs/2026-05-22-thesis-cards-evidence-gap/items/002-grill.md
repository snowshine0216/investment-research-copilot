# Item 002 grill — citation-data-model (Slice D0)

## Verdict

**PASS-WITH-EDITS** — spec was structurally sound but had three load-bearing ambiguities that would have caused planner rework. All resolved inline. ADR 0001 authored to capture the schema invariants for future slices.

## Questions raised & resolved

1. **Hash-preimage `instrument_id` term.** The §3 spec table phrased the preimage with bare "instrument_id". Code clearly uses `self.owner_instrument_id`, but the prose was loose. **Resolution:** spec rationale paragraph and CONTEXT.md both now say `owner_instrument_id` explicitly. ADR pins the term.
2. **Empty-URL fallback collision risk.** Original fallback `f"{source}:{date}"` would collide two empty-URL Sina digests with same constituent symbol + same publish date but different fiscal-period content. **Resolution:** fallback now `f"{source}:{date}:{summary[:64]}"`. Spec `__post_init__` and the "Edge cases" entry updated; ADR documents the choice.
3. **`citation_kind="both"` rejection.** Confirmed `__post_init__` rejects anything not in `{"data","information"}` (acceptance #2). No test fixture in the spec table uses `"both"`. ADR notes `both` was explicitly removed per source diagnosis §3 D0c.
4. **Theme-report citation provenance.** Spec §"Threading provenance" already says `owner_instrument_id` = the instrument being built; no edit needed.
5. **Fund-level adapter scope tagging.** Spec already states `scope="instrument", constituent_key=None` for V1 `_filing_evidence`/`_broker_evidence`; item 003 rewires. ADR "Consequences" documents this pre-item-003 stance.
6. **`asset_class` derivation on `CitationMeta`.** Verified `OpportunityRow.asset_class` is required (no default), always populated by `build_opportunity_row`. Safe to source from `row.asset_class` at `build_cited_map` time.
7. **PickRow markdown rendering.** `<br>`-joined markers within one cell is valid GFM; confirmed `render_picks_table` adds the `证据` column. Spec already covers; no edit needed.
8. **Failure-section placement in `memo.md`.** **This was the biggest find.** `MemoInputs` is a fixed-shape dataclass (`src/irc/memo/template.py:5-21`); top-level `## 未能纳入精选…` headers would collide with the numbered `## 6. 风险提示`. **Resolution:** failure sections nest under §5 "精选标的" as `###` (h3) sub-blocks, appended to `picks_table_md`. A new pure helper `render_failure_sections` lives in `src/irc/memo/picks_table.py`. Spec "Caller change" rewritten; acceptance #26 amended `##` → `###`; open question #4 resolved.
9. **Duplicate-detector timing.** Spec said "immediately before artifact promotion" but didn't say item 002 doesn't call it. **Resolution:** schema additions point #12 now states explicitly that item 002 lands the function only; item 009 wires the call before `atomic_write_text`. ADR consumer list documents this.
10. **64-bit collision invariant.** Documented as a hard run-time invariant in spec preimage-rationale paragraph and in ADR — not a probabilistic best-effort.

## Spec edits applied

- `ThesisEvidence.__post_init__`: fallback canonical_id now `f"{source}:{date}:{summary[:64]}"`.
- Preimage rationale paragraph: clarifies `owner_instrument_id` term and documents 64-bit invariant explicitly.
- Edge cases entry for empty URL: updated to reflect summary-prefix disambiguation.
- §"Caller change" for `run_memo`: failure sections become `###` h3 sub-blocks appended to `picks_table_md`, with new `render_failure_sections` helper in `picks_table.py`.
- Acceptance criterion #26: `##` → `###`; adds positional assertion.
- Schema point #12: documents that item 002 lands the detector function only; item 009 wires the audit call site.
- Open question #4: marked resolved.

## CONTEXT.md changes

- "Citation ID" glossary entry: `(instrument_id, ...)` → `(owner_instrument_id, ...)`, fallback formula documented, collision invariant + ADR link added.

## ADR created

`docs/adr/0001-citation-data-model.md` — "Citation data model". Covers: provenance contract, citation_id hash scheme (with explicit `owner_instrument_id` and `summary[:64]` fallback), 64-bit collision invariant, deterministic-selector invariant, audit-gate consumer list (5 gates in item 009), alternatives considered (UUID / `both` kind / side-table / full sha256), and consequences. ADR meets the "hard to reverse + surprising without context + real trade-off" bar because the hash preimage and provenance contract reach into every later slice (003–009).

## Residual open questions

- **Open question #5** (`_strip_venue_suffix` exhaustive suffix list) — punted to planner per spec. Conservative regex `\.[A-Z]{2,3}$` is sufficient if the planner enumerates from universe configs.
- **Open question #3** (`_evidence_from_dict` location) — spec defers to second-consumer discovery; ADR follow-up notes this.
- Tests that currently snapshot the picks-table markdown (open question #2) need locating during the implement step — flagged in spec but not a grill blocker.
