Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pre-landing parallel review + adversarial), orchestrator-inline
PR: https://github.com/snowshine0216/investment-research-copilot/pull/88
Supersedes: items/005-ship-blocked.md (pre-push findings; the substantive one fixed before push)

## Reviewers
- pr-review-toolkit:code-reviewer (sonnet) — no P0; 2× P1
- pr-review-toolkit:silent-failure-hunter (sonnet) — 1× P0 (silent LLM swallow) + 1× P1
- adversarial general-purpose (sonnet) → verdict CLEAN; 3× P2

## Findings

### FIXED pre-push (commit cb9f28b)
1. **Silent LLM swallow under --adversarial** — `run_defend`/`run_falsify` swallowed all exceptions (auth/rate-limit/network) with no log, so a bad DEEPSEEK token silently produced a `thesis_debate.md` full of "未能生成辩论" placeholders, indistinguishable from a legitimately-empty model response. Fixed: WARNING logging on each swallow (exception class + row id) + a `run_debates`-level warning when every row came up empty. Returns unchanged (graceful degrade preserved). Tests added.
2. **Non-list parse → char-bullets** — `{"arguments": "a string"}` iterated to one bullet per character. Fixed: guard `isinstance(value, list)` before iterating. Test added.
3. **Loose `debate_route` annotation** — `object | None` → `tuple[ResolvedRoute, ResolvedRoute] | None`. No runtime change.

### Nits → TODOS (not blocking)
- Eager top-level import of debate.py in opportunity_cmd.py (declarative; no behavior change).
- `test_renderer_is_deterministic` only asserts same-call stability (cross-artifact determinism covered by the flag-on-vs-off byte-equality test).
- 16-hex citation test uses a 3-hex stub (thesis_debate.md not in SAME-3/canonical set → no contamination possible).

### Adversarial — CONFIRMED CLEAN
- Flag-OFF byte-identical (route resolved only when adversarial=True; guard `if debate_route is not None`; module import triggers no LLM call).
- Advisory-only: no thesis_state (derive_thesis_from_evidence) / Policy B / valuation_state / core_dca / deterministic memo pillar / citation-set change.
- `thesis_debate.md` written AFTER the 5 canonical artifacts, on post-citation-gate publishable_rows; NOT in the canonical-artifact set, NOT in H3/SAME-3, exempt from the determinism contract.
- Determinism of the renderer holds; secrets never logged/in prompts/output (env var NAME only in errors); per-row failure isolation works; backward-compatible (adversarial defaults False).

## Test notes
- tests/opportunity + tests/commands: 745 passed / 3 skipped (post-fix).
- Full suite: 2634 passed / 36 skipped / 8 failed — the 8 are the documented pre-existing failures (identical to base per items/001-ship.md); 0 new.
- ruff: clean on all item-005 files. Live LLM test double-gated, skips offline.
