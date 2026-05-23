# Item 007 — Grill summary

Auto-accepted under autonomy override 2026-05-23. No human in the loop; every recommended answer locked verbatim against ADRs 0001/0002/0003 + CONTEXT.md (refreshed).

## Verdict

**PASS.** Spec hardened against the domain model. 4 new contracts locked, 1 new ADR created, CONTEXT.md gains 10 terms, no unresolved questions outside the planner-owned OQ list.

## Seven grill questions resolved

| # | Question | Locked answer |
|---|---|---|
| G-Q1 | aliases.py vs memo/audit.py split — circular import risk? | No risk. `numeric_audit.py` is stdlib-only today; `aliases.py` imports `irc.opportunity.types` + `irc.fundamentals.types` one-way; `numeric_audit.py` empty-map raise uses `if not instrument_aliases` truthiness — zero new imports. Locked as CONTEXT.md "Renderer tier-1 import contract". |
| G-Q2 | `ConstituentAliases` multi-owner shape — frozenset vs sorted-tuple vs list? | `frozenset[tuple[str, str]]`. Storage is unordered (map is in-memory only, never serialised). **Mandatory sort at traversal** rule added: any traversal affecting rendered output OR audit-finding emission must `sorted(fs)` first with canonical key `(instrument_id, constituent_key)` asc. Locked in ADR 0004 §1 + CONTEXT.md. |
| G-Q3 | Audit-gate parseable appendix contract — structural format item 009 can pattern-match? | 5 regex shapes locked in spec §17 + `_APPENDIX_LINE_RE` module-level constant in `report.py` for cross-test reuse. Every appendix bullet provably matches exactly one shape (Shape 1: evidence+failures, Shape 2: ❌ failure-only, Shape 3: ⚠️ audit-error-only, Shape 4: evidence-only canonical, Shape 5: defensive fallback identical to Shape 3). |
| G-Q4 | `[stock:{symbol}]` for HK 5-digit codes? | Yes — `symbol` is passed through verbatim, no transformation. HK codes (`00700`), CN codes (`600519`), US tickers all render under the same tag. New test fixture `hk_constituent_universe` covers this. |
| G-Q5 | `ambiguous_constituent_reference` slice boundary — does item 007 emit findings? | NO. Item 007 builds the multi-owner frozenset (the precondition); item 009 implements the lookup AND emits the finding. Spec §Q5 already locked this; grill verified item 007's tests assert STRUCTURE only, never emission. |
| G-Q6 | `find_uncited_conclusions` empty-map raise — defensive vs misconfigured caller? | Defensive. With ≥1 row passing through `build_alias_maps`, the alias map is NEVER empty in practice — every row contributes `instrument_id → instrument_id`. The raise guards against a misconfigured caller passing `{}` directly. Locked in spec §Q6 + AC11 (non-empty does NOT raise; empty `constituent_aliases` permitted). |
| G-Q7 | Section-header disambiguation lookup signature — does item 007 ship it? | NO. Item 007 ships the BUILDER ONLY. Item 009 ships `lookup_constituent(name_or_symbol, constituent_aliases, *, current_instrument_id)` with the contract documented in spec §Q9 so the item 009 planner inherits it verbatim. |

## Additional contract uncovered during code-grill

| # | Question | Locked answer |
|---|---|---|
| G-Q10 | `compose_discipline_markdown(rows, date)` does not receive pick_rows — how does the appendix render in pick-row order (AC21)? | Signature extension with two keyword-only params (`publishable_rows`, `pick_order_iids`) and empty defaults preserve backward compat. Trade plan is read in `opportunity_cmd.py::_write_opportunity_outputs` (same source `memo_cmd.py::run_memo` already reads) → `pick_order_iids = tuple(t["target"] for t in trade_plan if t.get("target"))`. No memo→opportunity coupling added. Locked in spec §Q10. |
| OQ1 | `_evidence_from_dict` already exists in 2 production locations (snapshot_cache.py:148 + memo_cmd.py:262); item 007 adds a 3rd consumer. | Sharpened from "nice-to-have promotion" to "load-bearing dedup". Locked target: `@classmethod ThesisEvidence.from_dict(d) -> ThesisEvidence` on `irc.fundamentals.types` (source-of-truth module). All 3 call sites updated. Spec OQ1 sharpened. |

## Most consequential clarification

**G-Q2 / ADR 0004 §1.** Frozenset iteration is hash-dependent, not insertion-dependent. Without the "mandatory sort at traversal" rule, item 009's `ambiguous_constituent_reference` finding's `evidence_excerpt` field would render with non-deterministic ordering — breaking the AC9 determinism contract silently. The grill caught this before item 009's plan phase locked it incorrectly.

## Artifacts updated

- **CONTEXT.md** — new "Renderers + alias-builder" section (10 terms).
- **docs/adr/0004-renderer-determinism-and-alias-policy.md** — NEW ADR (3 sections). 3-of-3 ADR test passed: hard-to-reverse + surprising + real-trade-off.
- **docs/adr/0001-citation-data-model.md** — added cross-link to ADR 0004.
- **items/007-spec.md** — §17 (audit-gate parseable appendix), Q8 (frozenset lock), Q9 (lookup signature), Q10 (compose_discipline_markdown wiring), sharpened OQ1, 2 new test fixtures, grill verdict section appended.

## Unresolved questions

None at grill level. OQ1–OQ4 remain in the planner's territory per the spec's "Open questions for the planner" section — they are not blockers for spec acceptance.
