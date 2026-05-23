# ADR 0003 — Failure-mode + Policy B weight-aware quorum + H3 universal gapped-row invariant

**Status:** Accepted (2026-05-23, item 006)
**Supersedes:** none. Builds on [ADR 0001 — citation data model](0001-citation-data-model.md) and [ADR 0002 — active-fund fetch engine](0002-active-fund-fetch-engine.md).
**Spec:** `docs/2026-05-22-thesis-cards-evidence-gap/items/006-spec.md`

## Context

Items 003 and 005 produce the raw per-fund data — `ActiveFundSnapshot.constituent_analyses` with per-constituent `ThesisEvidence` + `failure_reasons`, and `FundLevelSnapshot.evidence_gaps` for the QDII sentinel and fund-level NAV failures. Item 006 is the **audit-policy layer** that decides which funds publish, which funds get gap-stamped, and what evidence trail downstream consumers (items 007 + 009) can rely on.

Three contracts are non-obvious, expensive to reverse, and the product of real trade-offs:

1. **Policy B weight-aware quorum** — not the simpler "all top-N must dual-cite" or "any one citation is enough" gate. The weight-aware shape is the post-grill amendment to the original diagnosis.
2. **Audit-error vs evidence-gap vs failure-reason taxonomy.** Three named-by-purpose fields on different dataclasses. A future contributor who collapses them would break the rejection-log's diagnostic value AND item 009's defence-in-depth raise.
3. **H3 universal gapped-row invariant** — `_write_opportunity_outputs` partitions on `evidence_gaps != ()` and the failure renderer reads only 4 fields. Without H3 a gapped row could leak `opportunity_state`/`note_cn` into publishable outputs.

This ADR locks all three. Reviewers reading `rejection_log.py`, `failure_renderer.py`, `evaluate_policy_b`, or `_write_opportunity_outputs` six months from now should land here.

## Decision

### 1. Policy B v2 — five-rule precedence with weight-aware quorum

`evaluate_policy_b(snapshot: ActiveFundSnapshot, *, top_n: int) -> PolicyBVerdict` evaluates exactly five rules in this fixed order. Each rule short-circuits when it fires:

1. **`holdings_fetch_failed`** — `snapshot.constituent_analyses == () AND snapshot.fund_level_failure_reasons` non-empty.
2. **`incomplete_constituent_record` (audit error)** — any `ConstituentAnalysis` with `evidence == () AND failure_reasons == ()`. Item 003's adapter contract was violated; the constituent record is shape-corrupt. Audit error string: `f"missing_constituent_record:{symbol}"`.
3. **`incomplete_constituent_data` (per-holding data leg)** — any holding in the top-N lacks a `citation_kind="data"` evidence entry. Disclosure listed the holding, so missing data-leg is a real gap. Tail holdings are NOT exempt.
4. **`insufficient_info_coverage_top_half` (weight-aware info quorum)** — the material top-half (top `ceil(top_N/2)` holdings by weight, EXTENDED to include positions tied at the cutoff weight) must EACH have a `citation_kind="information"` evidence entry. Tail holdings may be data-only without blocking.
5. **`incomplete_constituent_coverage`** — at least one constituent has `evidence == () AND failure_reasons != ()` (mixed case: some constituents have evidence + diagnostics, others have only diagnostics). Rule 5 catches the case rule 3 doesn't reach when not ALL top-N lack data leg.

**Why this order:**
- Rule 1 first because nothing else is computable without holdings.
- Rule 2 second because a corrupt-shape record poisons downstream interpretation; audit error is the most informative failure to surface.
- Rule 3 third because data-leg is universally required (every holding); rule 4 (info-leg) is weight-restricted to the material set. Surfacing data-leg failure as its own code lets the operator distinguish "the filings pipeline broke" from "we don't have enough broker commentary."
- Rule 4 fourth — info-leg quorum is the V1 signature gate (drives the US-heavy systematic exclusion).
- Rule 5 last — the leftover diagnostic, not a primary cause.

**Material-set boundary tie rule:** ties at the cutoff weight EXTEND the material set rather than truncate it. Tiebreaker between equal-weight symbols at non-boundary positions = `symbol` ascending for deterministic ordering.

**Trade-off considered:**
- *Alternative A — flat quorum (any K of N).* Rejected: doesn't acknowledge weight. A 30%-weight rank-1 holding without info-leg is much more material than a 2%-weight rank-10 holding without info-leg. Weight-aware is the correct shape.
- *Alternative B — strict "every constituent must dual-cite".* Rejected: would systematically exclude EVERY active CN fund holding any HK or US name in V1, even when those names are minor positions. Tail-data-only-permitted is the load-bearing relaxation.
- *Alternative C — top-K-by-weight (K hard-coded as 3 or 5).* Rejected: `top_n` is configurable (`TOP_N_DEFAULT=10`) and the material set must scale with it. `ceil(top_n/2)` is the right linkage.

### 2. Three-field failure taxonomy

| Field | Lives on | Semantic | Populated by |
|---|---|---|---|
| `failure_reasons` | `ConstituentAnalysis`, `ActiveFundSnapshot.failure_reasons_by_symbol`, `FundLevelSnapshot.fund_level_failure_reasons` | Adapter ran but couldn't produce evidence (e.g. `filing_fetch_failed:600519:ConnectionError`) | Item 003 (per-constituent), item 005 (fund-level) |
| `evidence_gaps` | `OpportunityRow.evidence_gaps`, `FundLevelSnapshot.evidence_gaps` | Fund-row-level disposition: cannot publish | Items 003 (structural), 005 (sentinel + fund-level), 006 (Policy B) |
| `audit_errors` | `ConstituentAnalysis.audit_errors` (NEW in item 006) | Shape-corruption: constituent has neither evidence nor diagnostics, violating item 003's contract | Item 006 only (derived on evaluation; never persisted to disk caches) |

The three are NOT collapsed because:
- Item 006's Policy B reads `failure_reasons` and `evidence` SEPARATELY to distinguish rule-3 (no data leg) from rule-5 (mixed evidence + failure_reasons).
- Item 007's discipline failure section reads `evidence_gaps` only (4-field renderer contract).
- Item 009's defence-in-depth `find_incomplete_constituent_analyses` reads BOTH `failure_reasons` and `audit_errors` with different raise messages.

`OpportunityRow` does NOT gain an `audit_errors` field. Row-level effects of audit errors are captured by `evidence_gaps += ("incomplete_constituent_record",)` and surfaced in the rejection record via per-constituent `ConstituentCoverageEntry.audit_errors`. The locus of the audit error is the constituent symbol — denormalizing to the row level would invite drift.

**`audit_errors` is derived, never persisted.** When Policy B detects a missing-record case, it builds a fresh `ConstituentCoverageEntry` carrying the audit_errors string via `dataclasses.replace`. The original cached `ConstituentAnalysis` JSON on disk is byte-identical before and after `evaluate_policy_b` — locked by a sha256 cache-file regression test.

### 3. H3 universal gapped-row invariant

`_write_opportunity_outputs` partitions `kept_rows` into:
- `publishable_rows = [r for r in kept_rows if not r.evidence_gaps]`
- `gapped_rows = [r for r in kept_rows if r.evidence_gaps]`

at the top of the function, after a fatal pre-gate raise on `fetch_budget_exhausted`. Five locked invariants follow:

1. **`thesis_cards.yaml` contains ZERO gapped rows.** The card emit loop iterates `publishable_rows` only.
2. **`opportunity_report.json.rows` contains ZERO entries with non-empty `evidence_gaps`.**
3. **Publishable discipline-bucket sections** (`今日可定投`/`减速定投`/`暂停加仓`/`风险复核`/`调仓复核`/`退出复核`) contain ZERO gapped rows.
4. **Failure-section renderer reads only 4 fields:** `instrument_id`, `name_cn`, `evidence_gaps`, `fetch_types_attempted`. The renderer's signature accepts `Sequence[OpportunityRow]` but the implementation NEVER references `opportunity_state`/`dca`/`risk`/`note_cn`/`valuation_state`/`heat_state`/`thesis_state`/`product_quality_state`/`opportunity_reason`/`contributing_dimensions`/`thesis_evidence`/`constituent_analyses`. A regression test greps the rendered output for forbidden tokens.
5. **`fetch_budget_exhausted` is run-level fatal.** A row carrying this gap → `RuntimeError` raised IMMEDIATELY at Step 1 (before any partition, before any `.tmp` write). Distinct exception class from item 003's `FetchBudgetExceeded` (which raises in `_build_rows` before `_write_opportunity_outputs` is ever called). Unconditional `raise`, not `assert` — `-O` does not silence it.

**Trade-off considered:**
- *Alternative A — emit thesis_cards for gapped rows with a "placeholder" conclusion.* Rejected: defeats the purpose. The whole point of evidence_gaps is "we cannot draw a conclusion." Emitting one would mislead the operator.
- *Alternative B — combine publishable + gapped rows in a single discipline output with a per-row gap flag.* Rejected: discipline_report.md's bucket sections (`今日可定投` etc.) are the operator's action list. Mixing in gapped rows would force every reader to mentally filter. Separating into a `## 证据不足` section is the load-bearing UX choice.
- *Alternative C — failure-section renderer takes the full row but a code-comment instructs "don't read conclusion fields."* Rejected: a code comment is not an enforcement mechanism. The renderer's signature is — a future contributor cannot accidentally add `r.opportunity_state` because the regression test greps for the forbidden token.

### 4. Atomic write-once for `rejections.json`

`RejectionsDocument` is built in-memory in `_write_opportunity_outputs` Step 4 from the partitioned `gapped_rows` + `pending_verdicts`. Then written ONCE via `write_rejections_json` using the `.tmp.{pid} → os.replace` pattern. NOT appended per-row.

**Why atomic write-at-end:**
- Idempotent reruns: no partial files visible to consumers between iterations.
- Consistent with item 003's `.fetch_state_*.json` and item 005's NAV cache pattern (atomic write is the project's I/O convention).
- Append-per-row would require either O(n²) re-read + rewrite OR a custom streaming JSON-array writer (corrupts JSON if the process dies mid-write).

Empty rejections case still writes `entries: []` — the empty file is the signal of "no rejections this run", NOT a skip. Stable presence makes monitoring greppable.

### 5. V1 systematic exclusions — computed and rendered by item 006

The once-per-run `## V1 systematic exclusions: N funds excluded due to US-heavy material holdings` line in `discipline_report.md` is computed AND rendered by `render_v1_systematic_exclusion_summary(records)` in `src/irc/opportunity/failure_renderer.py`. N counts the `RejectionRecord`s where `rejection_reason == "insufficient_info_coverage_top_half"` AND a strict majority of `material_top_half` constituents have `exchange == "US"`.

**Why item 006 (not item 007):**
- The tally is purely a function of `rejections.json` entries — duplicating it as a separate field in the JSON would invite drift.
- Item 006 already composes the discipline_report.md failure-section frame; splitting the V1 summary line to item 007 would fragment the composition.
- The "once-per-run, unconditional" semantic is locked by a single renderer call site — the test is trivial.

Item 007's territory (per item 006's "Out of scope") remains memo evidence_pool + per-fund constituent inline bullets + `## 持仓明细` appendix.

### 6. Policy B applies ONLY to ActiveFundSnapshot

`evaluate_policy_b` is invoked ONLY when `lookthrough_target.kind == "active_fund"` AND `snap_obj` is `ActiveFundSnapshot`. Reasons:
- `FundLevelSnapshot` (gold/cn_bond_fund/cn_etf, tracked CN indices) has no `constituent_analyses` field — the entire fund IS the row. Its citations are fund-level NAV + announcements, evaluated by the dual-coverage gate in item 009.
- `ConstituentSnapshot` (legacy display-only) carries no `ThesisEvidence` — it's the `## 持仓明细` appendix path only.
- The QDII sentinel (item 005's `_build_qdii_sentinel_snapshot`) emits `evidence_gaps=("qdii_information_unavailable",)` directly; Policy B has no role.

`_classify_rejection_reason` (the post-partition helper) handles ALL gap codes (QDII + Policy B + fund-level) so the rejection log records every excluded fund regardless of which engine stamped the gap. But the Policy B evaluator itself only runs for active funds.

## Consequences

**Positive:**
- Operators get a single canonical `rejections.json` per run with every excluded fund and a stable `decision_rule` string. Diffs across runs are clean.
- The 4-field failure renderer makes "gapped row leaked into publishable output" impossible by signature, not by convention.
- The three-field taxonomy survives future audit-policy additions (V2's US-news adapter ships, the V1 systematic exclusions line should drop to N=0 — same code path, no schema change).
- `audit_errors` derived-on-evaluation means item 003's cache files don't need migration when item 006 lands.

**Negative (acknowledged):**
- Policy B precedence is load-bearing — changing the order of rules 1–5 would shift which gap code surfaces for ambiguous funds (e.g., a fund with both data-leg and info-leg failures). Reversing is a multi-test refactor.
- Adding a new `RejectionReasonCode` literal requires updating `_GAP_TO_REASON` AND adding a test (criterion 19's regression check raises on unrecognised codes). The strictness is deliberate — silent acceptance of new codes would let bugs slip through.
- The V1 systematic exclusions line is greppable and stable — but it also publicises the V1 limitation to anyone reading `discipline_report.md`. This is the *intended* behaviour per the diagnosis Q9.b user requirement.

## Related

- [ADR 0001 — citation data model](0001-citation-data-model.md): `citation_kind="data"` vs `"information"` is the load-bearing distinction Policy B's rules 3 and 4 key off.
- [ADR 0002 — active-fund fetch engine](0002-active-fund-fetch-engine.md): the engine whose outputs Policy B evaluates. The `fail-closed freshness probe` + `preflight budget gate` contracts are what guarantee Policy B never sees stale or partially-fetched snapshots. Item 006's H3 Step 1 raise on `fetch_budget_exhausted` is the defence-in-depth complement to ADR 0002 §3's preflight raise.
- `docs/2026-05-22-thesis-cards-evidence-gap/items/006-spec.md`: the implementation spec this ADR governs.
- `docs/diagnosis-thesis-cards-evidence-gap.md` §1.2: the V1 systematic exclusion footnote.
