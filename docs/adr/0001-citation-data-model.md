# ADR 0001 — Citation data model

**Status:** Accepted (2026-05-22)
**Owners:** opportunity / memo / discipline pipeline
**Supersedes:** none
**Spec:** `docs/2026-05-22-thesis-cards-evidence-gap/items/002-spec.md`

## Context

Before this slice, `ThesisEvidence` carried only `(type, source, url, date, summary)`. Memo, discipline and audit consumers had no deterministic way to:

- Address the same primary source across stages (no stable id).
- Distinguish fund-level from constituent-level evidence (no scope).
- Reject evidence whose owner doesn't match the row consuming it (no provenance).
- Run a dual-coverage gate that demands one data-leg AND one information-leg citation per opportunity row (no `citation_kind`).

This left audit gates unable to detect uncited conclusions, hallucinated citations, or scope-mismatched picks (e.g., a gold macro citation supporting an A-share equity row).

## Decision

Adopt a unified citation provenance schema with the following load-bearing invariants:

### 1. Provenance contract

Every `ThesisEvidence` instance carries:

| Field                  | Purpose                                                                             |
|------------------------|-------------------------------------------------------------------------------------|
| `scope`                | `instrument` \| `constituent` \| `asset_class_macro` \| `policy`                    |
| `citation_kind`        | `data` \| `information` (NEVER `both` — explicitly rejected by `__post_init__`)     |
| `owner_instrument_id`  | The `OpportunityRow.instrument_id` whose row this evidence will be filed under     |
| `parent_fund_id`       | Fund id when the evidence is about a constituent of that fund; else `None`         |
| `constituent_key`      | Stock symbol when scope is `constituent`; else `None`                              |
| `citation_id`          | First 16 hex chars of `sha256(preimage)` — computed in `__post_init__`             |

`build_cited_map` raises `RuntimeError` if any evidence's `owner_instrument_id != row.instrument_id` — provenance integrity is a hard invariant, not a soft check.

### 2. Citation-id hash scheme

```
preimage = f"{owner_instrument_id}:{scope}:{constituent_key or ''}:{type}:{canonical_id}:{date}"
canonical_id = url or f"{source}:{date}:{summary[:64]}"
citation_id  = sha256(preimage).hexdigest()[:16]   # 64 bits
```

The preimage explicitly uses `owner_instrument_id` (not "instrument_id" loosely). Two evidence entries that share `type/source/date/url` but differ in owner instrument, scope, or constituent get distinct ids by design — the citation is bound to the fund context that consumed it.

**Collision invariant:** 16 hex chars = 64 bits ⇒ birthday-paradox collision probability ≤2.7e-10 for ≤100k citations per run. The `build_cited_map` duplicate-id detector raises immediately if a collision fires — collisions are loud, not silent.

### 3. Deterministic selector invariant

`select_citations(entries, cap=3)` in `src/irc/opportunity/citation_selector.py` is the single source of truth for picks-table (D0e), evidence-pool (D1a), and the discipline-renderer nested thesis-evidence bullets (D3a, item 007). Two input tuples differing only in element order produce the same output tuple. The data-leg slot and information-leg slot are filled independently; both legs are guaranteed to appear in the output when both are present in the input.

The canonical module moved from `irc.memo.citation_selector` to `irc.opportunity.citation_selector` in item 007 to break an `opportunity → memo` cycle created when `opportunity.report._render_section` started calling the selector. The old import path remains as a re-export shim (`from irc.opportunity.citation_selector import select_citations`) so memo internals and existing tests keep working without churn; new code should prefer the canonical path.

### 4. Audit-gate consumer list

`build_cited_map` and `CitationMeta` are the schema foundation for these consumers (all land in later slices):

- `find_uncited_opportunity_rows` (item 009 D2a) — every `OpportunityRow.opportunity_state != "exclude"` row must have ≥1 data-leg + ≥1 information-leg citation in `cited_map[row.instrument_id]` whose `scope in {"instrument","constituent"}`.
- `find_missing_pick_citations` (item 009 D2b) — every pick-table row's `instrument_id` must appear as a key in `cited_map`.
- `find_hallucinated_citations` (item 009 D2c) — every `[ref:{citation_id}]` marker in `memo.md` must resolve to a `citation_id` present in `cited_map`.
- `find_uncited_conclusions` (item 009 D2d) — discipline `note_cn` lines making a state claim must carry a `[ref:...]` marker.
- `find_uncited_discipline_rows` (item 009 D2e) — every `DisciplineRow` with a non-trivial `note_cn` must have at least one `ThesisEvidence` propagated through.

These gates run immediately before `atomic_write_text` of `opportunity_report.json` and `memo.md`; a failed gate aborts the run.

## Alternatives considered

1. **UUID-per-citation generated at construction.** Rejected: not content-addressed, so the same source fetched twice would produce two different ids — breaks deduplication and makes audit cross-references useless.
2. **Single `citation_kind` value `both` for evidence that satisfies both legs.** Rejected: source diagnosis §3 row D0c explicitly removes `both` because it broke the dual-coverage gate's "at least one data AND at least one information" predicate — `both`-tagged evidence silently satisfied both legs from a single source, defeating the gate.
3. **Stash provenance in a side-table keyed by `(instrument_id, citation_id)` instead of on `ThesisEvidence`.** Rejected: the side-table introduces a synchronization burden between the evidence list and the side-table, and audit gates would need to load both. Embedding provenance on the dataclass is simpler and `dataclasses.asdict` round-trips it through JSON for free.
4. **Use full sha256 (64 hex chars) for `citation_id`.** Rejected: 64 bits is comfortable for the ≤100k-citations-per-run scale; the duplicate-id detector closes the residual collision risk. Shorter ids make `[ref:...]` markers in markdown readable.

## Consequences

- **Positive:** Audit gates can run cross-stage citation integrity checks with no extra plumbing. Memo `[ref:...]` markers are stable across runs (content-addressed). Provenance mismatch surfaces immediately at `build_cited_map`.
- **Positive:** `select_citations` is a pure function consumed by both picks-table and evidence-pool; one bug fix, one regression locus.
- **Negative (acknowledged):** Adding required fields to `ThesisEvidence` is a breaking change for every existing call site (3 production producers + 5 test fixtures). Item 002 absorbs the cost in a single slice.
- **Negative (acknowledged):** Pre-item-003, `_filing_evidence` and `_broker_evidence` carry `scope="instrument"` and `constituent_key=None` even though they iterate per-constituent filings. Item 003 rewires them to `scope="constituent"` and `constituent_key=f.symbol`. Until then, the dual-coverage gate's "constituent" requirement is partially under-served — accepted, because item 002 must land first to unblock item 003.

## Open follow-ups

- **`ThesisEvidence.from_dict` classmethod.** Item 002 puts the JSON→dataclass rebuilder in `memo_cmd.py` as `_evidence_from_dict`. If item 009 audit gates also need it, promote to a `@classmethod` on `ThesisEvidence`.
- **`provider_id` field.** Reserved for a future slice if empty-URL citation disambiguation outgrows the `summary[:64]` fallback in the hash preimage.

## Related ADRs

- [ADR 0002 — Active-fund fetch engine](0002-active-fund-fetch-engine.md): the runtime engine that emits `ThesisEvidence` with `scope="constituent"` for active-fund holdings. Adds the optional `holding_weight_pct` field (NOT part of the citation_id hash preimage; the contract in §2 of this ADR is unchanged).
- [ADR 0004 — Renderer determinism + alias policy](0004-renderer-determinism-and-alias-policy.md): downstream consumer-side companion. Locks the SAME-3 invariant across the three rendering surfaces (picks-table, evidence-pool, discipline nested bullets) — all three call `select_citations` directly with no pre-filter so the deterministic selector contract in §3 of this ADR is preserved end-to-end.

## Addendum — 2026-05-25: Published memo footnote-numbering veneer

`memo.md` published to disk now post-processes inline `[ref:HEXID]` markers into `[N]` numerals (global single sequence, ASCII brackets) for readability. The appendix is rewritten so each entry is prefixed with `**[N]**` and the original `[ref:HEXID]` is preserved at the line tail in backticks. The post-pass is implemented by `src/irc/memo/footnote_renderer.py::render_footnotes` and runs AFTER all audit gates have inspected the canonical hex-form draft.

This veneer does NOT change the citation-id contract defined in this ADR. Every internal surface — the LLM raw-ref pool, the synthesizer prompt, the auditor input, `citation_audit.json`, `memo_traceability.json`, `numeric_audit._MARKER_RE`, `find_uncited_conclusions`, `find_hallucinated_citations`, the alias-builder, `check_traceability` — continues to consume the canonical `\[ref:[0-9a-f]{16}\]` form. The hex is still grep-discoverable in the published memo via the appendix tail.

The post-pass also drops the `_MAX_REFS = 40` cap on the appendix renderer; the cap still constrains the synthesizer prompt input (a prompt-size budget) but the appendix renders every ref in the raw pool so no inline citation can be missing from the appendix.

## Addendum — 2026-05-28: Filing evidence semantics

**Status:** Accepted (2026-05-28, pickability-followups item F6).
**Spec:** `docs/2026-05-27-pickability-followups/items/F6-spec.md`.

A `ThesisEvidence` row with `type="filing"` is a **disclosure-existence anchor** — the canonical evidence that the issuer published a fiscal-period report on a specific date. It is NOT a quantitative performance claim. The displayed `summary` field MUST NOT expose the raw `revenue_yoy` scalar inline; every filing-evidence producer emits the locked template phrase:

```
{symbol} {fiscal_period} 财报已披露（口径未核实）
```

Producers (locked):

- `_evidence_for_constituent` (CN active-fund branch, `src/irc/fundamentals/snapshot.py:341-346`).
- `_evidence_for_constituent` (HK active-fund branch, `src/irc/fundamentals/snapshot.py:392-397`).
- `_filing_evidence` (legacy `ConstituentSnapshot` path for passive ETFs / tracked indices, `src/irc/opportunity/thesis_evidence.py:75-105`).

### 5.1 What did NOT change

- `citation_kind="data"` and `scope="constituent"` (active-fund branch) / `scope="instrument"` (legacy branch) are preserved. Filing rows continue to satisfy the dual-coverage gate's data leg (§4 of this ADR), Policy B rule 3's per-holding data-leg requirement ([ADR 0003 §1 rule 3](0003-failure-mode-policy-b.md)), and `select_citations`'s data slot ([ADR 0004 §3 SAME-3 invariant](0004-renderer-determinism-and-alias-policy.md)).
- `FilingDigest.revenue_yoy` is still produced by the fetch adapters (`akshare_filing.py`, `hkex_client.py`, `edgar_client.py`) and still drives the legacy `_yoy_split` classifier in `thesis_evidence.py` that feeds the deterministic `thesis_state` literal (`intact` / `under_pressure` / `falsified`). The classifier reads sign-of-fraction only — magnitude is never asserted.
- The synthesizer-prompt clause forbidding LLM percentage conversion (`src/irc/memo/synthesizer.py:55-56`) is updated to reference the new template phrase but still forbids any free-text `revenue_yoy=` output. `sanitize_unverified_revenue_yoy` (`src/irc/memo/pipeline.py:97-100`) stays as a belt-and-braces defense.

### 5.2 Appendix caveat trigger — substring switch

`memo/pipeline.py::_format_appendix_line` previously triggered the `⚠️ 合规警示：该字段含义及换算口径未经核实，数值不得作为业绩依据引用，仅作原始数据存档。` line when the rendered ref contained the substring `revenue_yoy=`. The PRIMARY trigger substring becomes `财报已披露（口径未核实）` — the load-bearing literal phrase named in §5 above. **During the cache-transition window** (post-impl hardening, F6 commit `9cb6765`), the trigger ALSO fires on the legacy `revenue_yoy=` substring so that pre-F6 cached snapshot files in `data/fundamentals/<quarter>/active_fund/*.json` — which serialize the old summary shape and rehydrate cleanly via source-url-keyed citation_ids — do NOT silently bypass the compliance caveat. The legacy branch is intended to become dead code once the next `irc fundamentals snapshot --target all` rewrites every cache to the new template; it can be removed in a follow-up cleanup. The caveat **text itself is preserved verbatim** — operator-facing compliance posture is unchanged. The trigger phrase MUST NOT be rephrased without simultaneously updating the trigger substring in `pipeline.py` AND the producer summaries in `snapshot.py` / `thesis_evidence.py`; locked by an acceptance test that asserts (a) no production summary contains `"revenue_yoy="` and (b) every filing-typed ref in the appendix carries the warning prefix.

### 5.3 Citation-id one-time re-roll — acknowledged

Per §2 of this ADR, the citation-id preimage uses `summary[:64]` as the URL-empty fallback. Filing-typed evidence rows do carry source URLs (from `FilingDigest.source_url`), so the URL component dominates the preimage and the summary change does NOT churn citation_ids for any filing row whose `source_url` is non-empty. For the (rare, defensive) filing rows that arrive with an empty URL — e.g. an adapter degraded path — the summary participates in the hash, and changing it from `… revenue_yoy=…` to `… 财报已披露…` re-rolls the citation_id once.

This mirrors the precedent set by:

- Item 002 (`docs/2026-05-22-thesis-cards-evidence-gap/items/002-spec.md`) absorbing `ThesisEvidence` field additions in a single slice.
- F5 ([ADR 0008 §3](0008-macro-research-excerpt-depth.md)) acknowledging citation_id churn on the macro-theme deploy run.

No persistent consumer keys on a specific filing citation_id across the change boundary (citation_ids are recomputed on every run from live evidence). The only call sites that pin specific hex citation_ids are test fixtures; those are updated in the same PR. ADR 0001's no-cross-run-stability contract (§2 collision invariant + §3 deterministic selector) is unchanged.

### 5.4 Why NOT drop filings; why NOT normalize the scalar

Two alternatives were considered and rejected:

- **Drop filings from constituent-scope evidence entirely.** Rejected — would cause Policy B rule 3 (`incomplete_constituent_data`) to fire for every CN active fund not routed through rule 2.5 (foreign-heavy). The only producer of `citation_kind="data" AND scope="constituent"` in V1 is `_evidence_for_constituent` emitting `type="filing"`; macro and fund-level paths emit different scopes. Re-routing all active funds through `_build_fund_level_snapshot` (QDII-style) would strip `constituent_analyses`, breaking the `## 持仓明细` appendix renderer — the same trade-off [ADR 0003 §7](0003-failure-mode-policy-b.md) rejected for foreign-heavy funds.
- **Normalize `revenue_yoy` to a comparable percentage at display time.** Rejected — per-provider unit conventions (fraction vs percent vs percent-of-percent) and accounting-period alignment are not validated; asserting `-0.0771 ⇒ -7.7%` everywhere is a confidence claim that cannot be backed today. A full unit-normalisation pass is the start of a fundamentals-data rewrite and is out of scope for this ADR.

### 5.5 Cross-reference

[ADR 0003 §1 rule 3](0003-failure-mode-policy-b.md) carries a one-line pointer back to this addendum so a reader landing in the Policy B precedence list sees the filing-evidence-semantics rationale.
