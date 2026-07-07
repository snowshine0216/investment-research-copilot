Verdict: PASS-WITH-NITS
Source: /ship steps 8+9

Reviewers: pr-review-toolkit:code-reviewer (step 8a), pr-review-toolkit:silent-failure-hunter (step 8b), general-purpose adversarial (step 9), all Sonnet. Codex secondary launched but still running at capture time — findings (if any) triage into the fix loop.

## Findings

- [fixed] P1 `src/irc/rotation/_cmd_helpers.py:104-107` — new join degraded silently (no `_log.warning`, unlike every sibling degrade path in the file). Fixed in `b37bc4cb` (`_translation_warnings`: dropped-name warning with count + ≤5-name sample), caplog TDD RED→GREEN.
- [fixed] P1 (adversarial) — duplicate `board_name` across BoardState rows would last-write-win silently. Fixed in `b37bc4cb` (warning naming duplicates; join behavior unchanged).
- [nit, deferred → TODOS.md] P1 `src/irc/rotation/exposure.py:29-32` — `unmapped_syms` conflates "not in store" vs "name translation failed". Artifact shape change; beyond item-004's locked "existing diagnostics path" scope. TODOS entry added (ship step 12).
- [nit, noted] P2 (pre-existing) — `board_fetch.py:52` doesn't `.strip()` `f14`; a padded name degrades to the visible unmapped path (self-diagnosing).
- [clean] Code reviewer: no P0/P1; caller sweep of `build_exposure` confirms no production caller regresses; O(n) comprehensions, no perf issue; 75 tests + ruff clean.
- [clean] Adversarial: abstain day never reaches `resolve_candidates` (`rotation_cmd.py:160-184`); no mutation; no concurrency change (store write path untouched); merge-tree clean vs base. Verdict RISKS (no P0).

## Classification

Blockers: 0. Latent bugs: 0 (both fixable findings fixed in-branch pre-push). Nits: 2 (deferred/noted above).
