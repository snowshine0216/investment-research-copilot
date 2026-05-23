# Item 003 grill — active-fund constituent layer (Slices A + G)

## Verdict
**PASS-WITH-EDITS** — spec is structurally sound and self-consistent. Five corrections were needed; three involve real wiring (one previously-uncaught) and two lock previously-open questions.

## Questions raised & resolved

1. **OpportunityRow.constituent_analyses doesn't exist yet.** Spec said "narrow from `tuple[object, ...]`" but verified `src/irc/opportunity/types.py:180-198` has no such field — only `DisciplineRow` carries the item-002 placeholder. `report.py:35-37` reads via `getattr(...)` defensively. Spec edit: change "narrow" → "add", with placement after `fetch_types_attempted`. (G1 + schema section.)
2. **`ThesisEvidence.holding_weight_pct` missing from spec.** Verified `src/irc/memo/citation_selector.py:28` already reads `getattr(e, "holding_weight_pct", 0.0)` defensively, anticipating item 003 attaches the field. Spec was silent. Added a new schema subsection: field is `float | None = None`, appended after `citation_id`, NOT part of the hash preimage, populated only for `scope="constituent"`.
3. **Q-H (HK news fallback) — committed to stub-empty only.** Added new failure-reason code `hk_news_unsupported_adapter:{stock}` to distinguish "AkShare doesn't ship the adapter" from "adapter ran and returned empty." No scraper in V1.
4. **Q-I (ThesisCard kwargs) — confirmed safe.** Verified `cards.py:41-63` constructs `ThesisCard` with all keyword args; appending `constituent_analyses` is trivial.
5. **Q-J (flatten ordering) — locked.** `(weight_pct desc, type_rank asc, citation_id asc)` where `type_rank: filing=0, broker=1, news=2`. Aligned with the existing `_slot_key` invariant in `citation_selector.py`; note that `select_citations` is already input-order-independent, so flatten order is for renderer determinism only.
6. **股票市场 normalization too narrow.** Source diagnosis mentioned values like `沪市A`, `深市主板`, `创业板`, `科创板`. Changed Strategy 1 from exact-match to substring-containment with HK/US priority, and added 科创板 → SH (Shanghai). Conservative fallthrough preserved for unknown values.

## Spec edits applied

- `In scope` row 16 (G1): re-described `OpportunityRow.constituent_analyses` as ADD, not narrow; cited current types.py line range.
- New schema subsection `ThesisEvidence.holding_weight_pct` (before `ConstituentAnalysis`): defines the optional field, its placement, and that it is NOT part of the citation_id hash preimage (ADR 0001 contract preserved).
- `OpportunityRow.constituent_analyses` subsection: rewritten as "NEW FIELD — not narrowing"; placement note added.
- Exchange parser §"Strategy 1" rewritten to substring-containment with HK/US priority + 科创板 → SH + conservative-fallthrough rule.
- New failure-reason row `hk_news_unsupported_adapter:{symbol}`.
- Q-H resolved (stub-empty, no scraper).
- Q-I resolved (kwargs confirmed in cards.py).
- Q-J resolved (flatten order locked, rationale tied to ADR 0001 §3).

## CONTEXT.md changes

Added new section **Active-fund fetch engine** with 7 new glossary entries: `FundHolding`, `HoldingsResult`, `ConstituentAnalysis`, `ActiveFundSnapshot`, **Disclosure quarter**, **Fail-closed freshness probe**, **Preflight fetch budget**, **Forbidden adapter pair**. All cross-linked to ADR 0002.

## ADR created

`docs/adr/0002-active-fund-fetch-engine.md` — locks four foundational contracts: (1) cache key = disclosure quarter, not calendar quarter; (2) fail-closed freshness probe; (3) preflight budget gate (no mid-loop checks); (4) exchange routing with forbidden adapter pairs. Cross-linked from ADR 0001's new "Related ADRs" section. Justified against all three ADR criteria (hard to reverse, surprising without context, real trade-off with alternatives considered).

## Residual open questions

- **`source_report_date` for split-mid-year disclosures.** A few funds disclose semi-annual reports as `"2024年半年度..."` instead of `"2024年2季度..."`. The current regex `r"(\d{4})年(\d)季度"` will fail and stamp `holdings_quarter_parse_failed`. Acceptable for V1 (fund is excluded from publishable picks via fund-level failure), but the planner may want to add a `半年` → `Q2` mapping as a follow-up.
- **`top_n` env override.** Spec hardcodes `TOP_N_DEFAULT = 10`. If a future planner wants `IRC_OPPORTUNITY_TOP_N=15`, the `plan_hash` must include it (already does). Pure judgment call — leave as constant for V1.
- **`fcntl.flock` on NFS-mounted `data/fundamentals/`.** Advisory locks behave subtly on NFS (silently no-op on some configs). If the user ever puts `data/` on NFS, the "concurrent run detected" guarantee weakens to "best-effort." Acceptable per CLAUDE.md (local macOS development) but worth a sentence in ADR 0002's Negative consequences if the user wants belt-and-suspenders.
