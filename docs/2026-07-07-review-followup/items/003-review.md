Verdict: PASS-WITH-NITS
Source: /ship steps 8+9

Reviewers: pr-review-toolkit:code-reviewer (step 8a) + general-purpose adversarial (step 9); step-8b silent-failure-hunter not dispatched (prose-only diff, zero error-handling surface — documented adaptation, same rationale as item 002). Codex secondary running at capture — triages before merge.

## Findings

- [fixed `dc22d0f5`] P0-class (both reviewers, convergent) — the fixture bullet's own wording backfired: "integration fixtures" collided with the repo's reserved `-m integration` marker meaning (loophole exempting plain unit tests — the exact R-1 class), and the absolute "never hand-crafted" outlawed legitimate deliberately-adversarial fixtures (incl. tests added by THIS run: dropped-name/duplicate-board warnings, malformed shapes). Reworded: purpose-scoped (normal-shape stand-ins copied from real artifacts, any tier; adversarial fixtures exempt + visibly synthetic). Meaning preserved.
- [fixed `dc22d0f5`] P1 (both) — assembly-assertion bullet funneled future e2e tests toward tests/commands/ without the per-FILE caveat for the documented whole-dir hang. Cross-reference added.
- [fixed `dc22d0f5`] P1 (both) — FACTS preamble named the env-var set/unset category as requiring a cited verify command while two existing entries carried none; generic `grep -oE '^NAME=' .env` recipe added to the preamble.
- [nit, accepted] "contract sentences name their test" is forward-only by wording ("added") — the pre-existing uncited CONTEXT.md contracts (H3 etc.) are intentionally not swept; residual risk is the documented drift-subagent scope-creep habit, noted.

## Classification

Blockers: 0 remaining. Latent bugs: 0 remaining (all wording loopholes closed pre-push). Nits: 1 accepted.

## Post-capture rounds addendum (2026-07-07)

- pr-review round: FAIL → 3 findings ("weeks" claim git-refuted; bare "fixture" ×7 vs CONTEXT.md:42; phantom §4.3/§4.4 anchors) → fixed `81b1bde0` → pr-review re-review upgraded to PASS (`659f91a7`).
- Codex secondary: 1 finding — "copied from a real on-disk artifact" readable as live data/** runtime reads → tightened to committed-snapshot wording `ffec6703`. No other contradiction found.
- Verify (`07b8c73f`) predates the last two wording commits; its cold-read conclusions (marker disclaim, adversarial exemption, per-file caveat, forward-only, env recipe) all survive — the later commits only narrowed wording further in the same direction (orchestrator gate re-ran tests/docs 9/9 at merge).
Verdict unchanged: PASS-WITH-NITS.
