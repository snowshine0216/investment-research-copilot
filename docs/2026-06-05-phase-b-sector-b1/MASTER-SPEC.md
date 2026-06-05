# MASTER-SPEC — Phase B sector expansion (B1)

**Mode:** spec (single feature, N=1)
**Run dir:** `docs/2026-06-05-phase-b-sector-b1/`
**Source spec:** [`docs/superpowers/specs/2026-06-05-phase-b-sector-expansion-design.md`](../superpowers/specs/2026-06-05-phase-b-sector-expansion-design.md)
**Detected:** spec mode (Goal/Decisions/Out-of-scope sections; author routes `→ writing-plans → autodev for B1 only`). Project type: **non-web** (Python CLI/data tool). PR shape **A** (per-item PR).

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | **B1 — data onboarding (activation OFF)** | **IN** | Code + tests + config + docs; explicitly autodev-able per source spec §8. SoT catalog module (`opportunity/sector_indices.py`), fetcher import swap, `activated_slugs` config + read-gate, threading, tests, per-slug ingest audit, docs. Output byte-identical (allowlist empty by design). |
| — | **B2 — activation (after gate #5)** | **OUT** | Source spec §8: "B2 is **not** planned now." Requires ~6 months of forward accumulation until series clear the 120/180 maturity gate, **then** a human sign-off (gate #5) on the real NAV-vs-PE recommendation diff. It is a post-maturation config edit + recorded diff + docs, gated on human review — cannot be done autonomously now. → SKIPPED.md. |
| — | **`中证机床ZZ` universe rename** | **OUT** | Source spec §3.5 / §10: separate, separately-reviewed `config/universe/*.yaml` change. Not byte-identical (alters `map_lookthrough` keys). B1 handles `中证机床ZZ` purely via an alias in `SECTOR_INDICES`. → SKIPPED.md. |
| — | **Sector PB source spike** | **OUT** | Source spec §10: csindex carries no PB; PE-only is an intentional documented gap. A PB source is a separate spike. |
| — | **Gate #4 live identity+PE confirmation** | **PARTIAL / hard-stop** | The live identity guard (`IRC_RUN_LIVE_AKSHARE=1`) is authored as a test in B1 but its *execution against live AkShare* is a human/live hard stop (network-gated). B1 writes the test; flags #7 (`sse_star_chip` 000685, absent from `index_csindex_all`) and #16 (`csi_resource` 000819, display≠official) are recorded for human confirmation **before B2 activation**, not blockers for B1 onboarding (allowlist empty → inert). |

## What "done" means for B1 (item 001)

Per source spec §8 (B1 exit gates):
- **Gate #1** — `uv run pytest` + `uv run ruff check src tests` green.
- **Gate #2** — invariants intact: output **byte-identical** with allowlist empty (H3 universal gapped-row + SAME-3 citation-set equality unaffected).
- **Gate #3 — NOT claimed at B1** — grounded count = 0 *by design*. The per-slug ingest audit shows all 17 slugs present & accumulating, 0 mature → 0 grounded.
- **Gate #4** — live identity+PE confirmation test authored (execution is the live hard stop); #7/#16 flagged.
- **Gate #5 — N/A at B1** — no activation → no recommendation change; the empty diff is *expected*, not a pass.
- **Gate #6** — docs synced: CONTEXT.md "Valuation inputs", CHANGELOG `[Unreleased]`, ROADMAP Phase B → B1 done.

## Key engineering nuances (carry into plan)

- **Config location:** the source spec says `config/valuation_buckets.yaml` + schema `ValuationBucketsConfig`. The committed file is a **template** at `src/irc/templates/config/valuation_buckets.yaml` (scaffolded into `config/` by `irc init`). The plan must edit the template (and any test fixtures), not assume a committed `config/valuation_buckets.yaml`.
- **Byte-identity is the load-bearing B1 invariant.** The non-activated sector short-circuit must return the **full all-`None` tuple** `(None, None, None, None, None)` — withholding raw `pe_ttm/pb/dividend_yield` AND the percentile — because the raw metrics also feed `OpportunityInput` (source spec §3.2).
- **Existing 3 metals slugs** (`csi_nonferrous`, `csi_resource`, `csi_nonferrous_mining`) are folded into `SECTOR_INDICES` and are now **also** governed by the allowlist — deliberate correctness fix (source spec §3.2). They must NOT auto-activate on maturity.
- **No global reads** (FP rule): the allowlist threads `run_opportunity → _build_rows → _build_input → populate_inputs → _index_valuation_metrics(..., activated_sector_slugs=...)` as a keyword-only param defaulting to `frozenset()`.
