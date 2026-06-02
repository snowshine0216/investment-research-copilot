# MASTER-SPEC — `irc narrative` Thematic Fund Mining

**Mode:** spec (single feature, N=1)
**Source spec:** `docs/superpowers/specs/2026-06-02-thematic-fund-mining-design.md` (copied verbatim → `items/001-spec.md`)
**Run dir:** `docs/2026-06-02-thematic-fund-mining/`
**Date:** 2026-06-02

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | `irc narrative <name>` — narrative-driven fund selector (holdings look-through) in front of the existing opportunity-grade per-fund analysis, plus a new pure `position_risk_level` | **IN** | The whole feature is one cohesive vertical slice: new `src/irc/narrative/` package (schemas/screen/risk/report/holdings_fetch/config) + `irc.commands.narrative_cmd` + `irc narrative` CLI command + `config/narratives/compute_metals.yaml`. Reuses existing cores verbatim. |

No OUT-scope items (single-feature spec). `ai` / `robots` narrative configs are explicitly follow-up work in the spec (§7) requiring **no code change** — out of band for this run, captured in SKIPPED.md as a forward note, not a blocked item.

## Acceptance criteria (from spec §1 Goals + §5 Testing)

1. `irc narrative <name>` resolves `config/narratives/<name>.yaml` → `NarrativeBasket`; missing/invalid config fails fast and lists available narratives.
2. **Screen (default / `--screen-only`):** enumerates the curated universe, fetches top-10 holdings per fund (cached), `score_overlap` + `rank_shortlist` produce a deterministic ranked shortlist; funds with no published holdings go to `<name>_screen_diagnostics.json` (never silently dropped).
3. **Analyze (`--analyze`):** ensures fundamentals snapshot on the shortlist only, runs `build_opportunity_row` (reused, untouched) per fund, derives the new `position_risk_level`, renders per-fund cards + roll-up.
4. New pure `derive_position_risk_level(eval_row, overlap, metrics) -> (RiskLevel, rationale)` ∈ `{low, moderate, elevated, high, insufficient}`; `evidence_gaps` non-empty ⇒ `insufficient`; rationale names dominant drivers, backed by existing `[ref:...]` citations.
5. Determinism: stable sort (basket-weight → overlap-count → `instrument_id`); locked 16-hex `[ref:...]` format; no wall-clock/random in cores; run-twice diff is empty.
6. Forbidden `基金概况` indicator stays absent in fetch code (acceptance grep).
7. New narratives reusable by adding a YAML config — no code change.
8. All new files < 200 lines, functions < 20 lines (ideal); pure cores unit-testable without mocks; `tests/narrative/` mirrors `src/irc/narrative/` 1:1.

## Key reuse contract (do NOT touch)

`enumerate_universe`, `build_opportunity_row`, `derive_thesis_from_evidence`, `derive_risk_action`, snapshot cache, the H3 / SAME-3 / citation invariants, and existing outputs (`eval-funds`, `discover`, `score`, `opportunity`). The narrative selector sits *in front of* and *reuses* these — it must not modify them (spec §2 Non-goals).
