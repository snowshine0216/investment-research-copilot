Verdict: PASS

Grill phase for item 005 (per-asset-class citation coverage, Slice F). All 7 open questions surfaced by the spec phase plus 3 additional grill questions have been resolved and applied. Spec hardened against the domain model before plan phase reads it.

## Inputs read (verification before completion)

- `docs/2026-05-22-thesis-cards-evidence-gap/items/005-spec.md` (commit 0d44589; 16 ACs + 7 open Qs)
- `docs/2026-05-22-thesis-cards-evidence-gap/items/004-verify.md` (Q4 pivot context — 3 topic-specific endpoints, shared schema, no URL column, `datetime.date` for `公告日期`)
- `docs/adr/0001-citation-data-model.md` (citation_id preimage; `summary[:64]` fallback when `url=""`)
- `docs/adr/0002-active-fund-fetch-engine.md` (4 contracts; will be amended in §5)
- `CONTEXT.md` (existing glossary)
- `src/irc/fundamentals/types.py` (`ThesisEvidenceKind` literals)
- `src/irc/opportunity/lookthrough.py` (`map_lookthrough` provider_symbol coverage)
- `src/irc/fundamentals/snapshot.py` (`build_snapshot` dispatch + `_TARGET_REGISTRY` registry)
- `src/irc/fundamentals/snapshot_cache.py` (cache layout patterns)
- `tests/fundamentals/test_fund_announcement_em_live.py` (column shapes from item 004)
- `src/irc/opportunity/types.py` (OpportunityInput.instrument_id)

## Questions resolved

### Q1 — `map_lookthrough` provider_symbol coverage

- **Recommendation:** patch `map_lookthrough` to populate `provider_symbol=inp.instrument_id` for `gold`, `cn_bond_fund`, and the `cn_etf` (tracked_index/theme) fall-through branches.
- **Adopted:** YES — confirmed required (not conditional). Without the patch, F3 dispatch ALWAYS falls through to legacy display-only path. Spec body F3 hardened with explicit pre-requisite section.

### Q2 — Tracked CN indices routing target

- **Recommendation:** `cn_etf` rows with a tracked_index route to `_build_fund_level_snapshot` (the ETF is itself a tradeable fund); raw-index `_TARGET_REGISTRY` path stays for display-only.
- **Adopted:** YES — `_TARGET_REGISTRY` keys are `display_cn` strings mapping to **index codes** (`000300` = CSI300), confirming the registry serves display-only constituent listings. The two paths coexist; fund-level path activates only when `provider_symbol` is non-empty.

### Q3 — NAV freshness probe cheapness

- **Recommendation:** skip the cheap-probe optimization. `ak.fund_open_fund_info_em(symbol, indicator="单位净值走势")` has no `top_n` parameter; probe = full refetch.
- **Adopted:** YES — stale cache → direct full refetch (4 calls). Spec F6 and ADR 0002 §5 both updated. Original spec line struck through with grill correction.

### Q4 — `type` literal for NAV evidence

- **Recommendation:** reuse existing `"snapshot"` literal (avoids ThesisEvidenceKind touch).
- **Adopted:** YES — `ThesisEvidenceKind = Literal["filing", "broker", "news", "policy", "snapshot"]` confirmed at `src/irc/fundamentals/types.py:40`. NAV is a single periodic data point; `"snapshot"` is the closest semantic fit. No Literal change, no item 009 gate-map change, no ADR 0001 amendment. Documented as a rejected alternative in ADR 0002 §5.

### Q5 — QDII sentinel disk storage

- **Recommendation:** NO. Gap-only rows have nothing to cache; in-memory sentinel re-emission is cheaper than I/O.
- **Adopted:** YES — spec F4 and ADR 0002 §5 both document the no-cache rule for sentinel snapshots.

### Q6 — CONTEXT.md additions

- **Recommendation:** add `FundNavReport`, `FundAnnouncement`, `FundLevelSnapshot`, `Fund-level dispatch`, `QDII V1 exclusion`, `Static-profile invariant`.
- **Adopted:** YES — new "Fund-level fetch engine" section inserted between "Active-fund fetch engine" and "Test infrastructure" in `CONTEXT.md`. Six terms defined.

### Q7 — ADR amendment vs new ADR 0003

- **Recommendation:** extend ADR 0002 with §5 "Fund-level engine (Slice F)". §4 (forbidden adapter pairs) does NOT apply — fund-level dispatches by `target.kind`, not by holding `exchange`.
- **Adopted:** YES — ADR 0002 gets §5 with cache layout (`nav/`), simplified probe (single full call per Q3), dispatch contract table by `target.kind`, F5 static-profile invariant, F4 QDII sentinel no-cache rule, and the empty-URL citation-id determinism note. Two rejected alternatives documented (new ADR 0003; new `"nav"` literal).

### Additional Q-A — F5 invariant enforcement location

- **Recommendation:** enforce upstream at the adapter, not downstream at the gate (gate cannot distinguish indicator origin from `ThesisEvidence`).
- **Adopted:** YES — `fetch_fund_nav_report` calls only `indicator="单位净值走势"`; information leg emits only via `fetch_fund_announcements`. Locked by AC 9 (grep-based assertion).

### Additional Q-A — date column types

- **Recommendation:** `str` (ISO 8601) at the dataclass boundary; `.isoformat()` conversion in adapter.
- **Adopted:** YES — `FundAnnouncement.date` and `FundNavReport.latest_nav_date` are both `str`. Locked by AC 2/3 ISO-shape assertions.

### Additional Q-A — symbol normalization

- **Recommendation:** existing `_normalize_ticker` from item 003 is sufficient (all V1 fund-level symbols are 6-digit codes).
- **Adopted:** YES — no extension needed.

## Documents touched

| File | Change |
|---|---|
| `CONTEXT.md` | Added "Fund-level fetch engine" section with 6 glossary entries. |
| `docs/adr/0002-active-fund-fetch-engine.md` | Appended §5 "Fund-level engine (Slice F)" with cache layout, probe, dispatch, F5 invariant, F4 sentinel, citation-id note, and 2 rejected alternatives. |
| `docs/2026-05-22-thesis-cards-evidence-gap/items/005-spec.md` | Inserted F3 pre-requisite section; struck through 2 incorrect lines with grill correction notes; appended `## Resolved decisions` (10 Q-A entries). |

## Verdict line

**PASS** — spec hardened against domain model. Ready for plan phase to read.
