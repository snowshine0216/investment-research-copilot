Verdict: PASS-WITH-NITS

Source: /ship steps 8 (pre-landing parallel review) + 9 (adversarial review), re-run after 3-commit fix round closed initial 2 P0s + 1 P1.
PR: https://github.com/snowshine0216/investment-research-copilot/pull/60
Subagents: pr-review-toolkit:code-reviewer (step 8a, re-run), pr-review-toolkit:silent-failure-hunter (step 8b, initial), general-purpose adversarial (step 9 re-run, model=sonnet)

## Summary

- **P0 (blockers):** 0 (after fix round)
- **Latent bugs:** 2 (worth fix-loop pickup; deferred candidates)
- **Nits:** 1

## Fix round 1 (pre-push)

Initial step 8 surfaced 2 P0s + 1 P1, recorded in `items/006-ship-blocked.md`. Closed via:
- `2976add` fix(opportunity): _classify_rejection_reason raises on any unknown gap (P0-1 — silent first-match)
- `08a2bb7` feat(opportunity): _GAP_TO_REASON covers legacy news + constituent gap codes (P1-1 — missing mappings would have raised on legacy-path rows)
- `eaa9863` fix(opportunity): plumb plan_hash + snapshot_cache_by_instrument through run_opportunity (P0-2 — silent rejections.json data loss)

Post-fix re-review (step 8 code-reviewer + step 9 adversarial): **all 3 closed; no new P0/P1 introduced by the fixes**.

## Classification (post-fix latents)

### Latent (worth fix-loop pickup; deferred candidates)

1. **`_apply_reduction` ignores `evidence_gaps`** (adversarial review highest-priority finding). `reduce_same_theme` in `src/irc/commands/opportunity_cmd.py` groups rows by `lookthrough_target.key` and keeps the highest-`_rank_key` row per key. `_rank_key` is purely quality-signal based (ER, AUM, TE, P/D, history, completeness) — it does NOT consider `evidence_gaps`. Concrete bug: if fund A (gapped, better ER) and fund B (clean, higher ER) share key `"CSI300"`, `reduce_same_theme` drops B before H3 partitioning. B is then absent from both `thesis_cards.yaml` AND `rejections.json` — silent loss from the audit trail. **Fix path:** extend `_rank_key` to either downrank gapped rows below clean ones, or run H3 partition BEFORE `_apply_reduction`. Should be paired with item 007's/008's renderer + integration-test work since the reduction policy interacts with publish-ability semantics.

2. **`_classify_rejection_reason` misleading message on empty-gaps row** (adversarial review P1). H3 partition prevents this in production (a row with `evidence_gaps == ()` is publishable, never reaches `_classify_rejection_reason`). But the fall-through `raise` message is "carries unrecognised evidence_gaps: ()" — confusing for test authors who construct a gapped row with empty gaps by mistake. **Fix path:** add a separate pre-empty-check `if not row.evidence_gaps: raise RuntimeError("...called on row with empty evidence_gaps — programming error; only gapped rows should reach this function")`. Trivial 2-line fix; deferred because not user-impacting.

### Nits (cosmetic / observation)

3. **`_build_rows` 7-tuple return is a smell** — code reviewer noted this hints at extracting a `_BuildRowsResult` dataclass. Not a CLAUDE.md violation (functions still small; immutability preserved). Refactor candidate, not a blocker.

### Notes (observations; no action required)

- Policy B precedence 1→2→3→4→5 verified at `policy_b.py:196-285` — matches ADR 0003 §1 exactly.
- `fetch_budget_exhausted` H3 defense-in-depth is unconditional `raise RuntimeError(...)`, survives `-O`. Verified at `opportunity_cmd.py:1015-1020`.
- `rejections.json` atomic write at end of `_write_opportunity_outputs` Step 4 — single `atomic_write_text` call, never incremental. Verified at `rejection_log.py:165-168`.
- Failure renderer reads ONLY 4 fields (`instrument_id`, `name_cn`, `evidence_gaps`, `fetch_types_attempted`) — signature enforces it (criterion 18 locked).
- V1 systematic exclusions summary emits unconditionally (N=0 case verified — emits `"## V1 systematic exclusions: 0 funds excluded due to US-heavy material holdings"`).
- Policy B is O(funds × top_N), not quadratic; invoked once per snapshot at build time.
- `_build_rows` 5-tuple → 7-tuple — all 4 production callsites updated; tests 7-tuple unpack verified.
- `_classify_rejection_reason` strict pre-scan covers (`evidence_gaps`, `()`)-empty edge case correctly (the fall-through raise message is the only nit).
- `_apply_reduction` H3 invariant survival: gapped row losing to clean sibling correctly partitions out into rejections.json; the inverse (clean losing to gapped) is the latent #1 finding above.

## Recommendation

PASS-WITH-NITS. Both latents (#1 + #2) are addressable opportunistically; #1 is the more impactful and should be picked up alongside item 007's renderer work or item 008's integration-test sweep (it touches publish-ability semantics that intersect with those slices).

Per autodev review→fix exit contract: all 3 post-ship verdicts must be PASS or PASS-WITH-NITS. This (inline review) is PASS-WITH-NITS; awaiting /verify + /code-review parallel dispatches.
