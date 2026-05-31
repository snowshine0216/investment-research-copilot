# 005 — /ship steps 8+9 review findings (pre-push)

Captured before the PR opens (ship.md "review can demand fixes before push"). Routed through a fix subagent; superseded by `items/005-review.md` once the PR opens clean.

## Reviewers
- pr-review-toolkit:code-reviewer (sonnet) — no P0; 2× P1
- pr-review-toolkit:silent-failure-hunter (sonnet) — 1× P0 (silent LLM swallow) + 1× P1 + note
- adversarial general-purpose (sonnet) — verdict CLEAN; 3× P2

## Findings to fix pre-push

### FIX A — silent LLM swallow hides auth/network failure under --adversarial (observability)
`src/irc/opportunity/debate.py` `run_defend`/`run_falsify`: bare `except Exception → empty result` with NO log. An invalid DEEPSEEK token (401), rate-limit (429), or network error produces the same `arguments=()`/`conditions=()` as a legitimate empty model response. Since `--adversarial` is an explicit opt-in, a bad token silently yields a `thesis_debate.md` full of "未能生成辩论" placeholders — the user cannot distinguish "model had nothing to say" from "every call failed." Same class as item-003's silent swallow. **Fix:** (1) log a WARNING (exception class + row id/symbol) on the swallow in `run_defend`/`run_falsify`, returning the empty result unchanged (graceful degrade preserved); (2) at `run_debates` (or the call site), if EVERY row produced an empty debate under --adversarial, emit one WARNING that the debate generation failed for all rows (so total failure is observable). Add a test (caplog: a raising call_chat → warning emitted + empty result).

### FIX B — loose type annotation on debate_route (clarity/contract)
`src/irc/commands/opportunity_cmd.py:~1224` types `debate_route: object | None`; it's actually `tuple[ResolvedRoute, ResolvedRoute] | None`. **Fix:** correct the annotation. (No runtime change.)

### FIX C — non-list LLM `arguments`/`conditions` produces char-bullets (robustness)
`src/irc/opportunity/debate.py` parse: `{"arguments": "a string"}` → iterating a str yields one bullet per character. **Fix:** guard that the parsed value is a `list` before iterating (else treat as empty); add a test (string value → empty, not char-bullets).

## Accepted / noted → TODOS (NOT fixed now)
- Eager top-level import of debate.py in opportunity_cmd.py (architectural smell; declarative, no LLM call, no behavior change on flag-off). → TODOS.
- `test_renderer_is_deterministic` only asserts same-call stability; the cross-artifact byte-equality is covered by `test_canonical_artifacts_byte_identical_with_vs_without_flag`. Strengthen if cheap, else → TODOS.
- 16-hex citation test uses `[ref:abc]` (3 hex) not a real 16-hex; thesis_debate.md is NOT in the SAME-3/canonical set so no contamination is possible. Test-coverage nit. → TODOS.

## Confirmed CLEAN (adversarial + code-reviewer)
- Flag-OFF byte-identical (guard `if debate_route is not None`; route None unless adversarial=True; module import triggers no LLM call). Advisory-only: no thesis_state/Policy B/state/memo-pillar/citation change. thesis_debate.md written AFTER the 5 canonical artifacts, on post-citation-gate publishable_rows, NOT in canonical/SAME-3/H3. Determinism holds. Secrets: env var NAME (not value) in errors; token never logged/in prompts/output. Per-row failure isolation works. Backward-compatible (adversarial defaults False). debate.py 156 lines.
