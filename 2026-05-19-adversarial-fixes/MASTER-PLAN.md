# MASTER-PLAN — Adversarial Review Fixes

## Branch strategy

- **Feature branch:** `claude/adversarial-fixes-2026-05-19` (off `main`)
- **Per-item sub-branches:** `claude/adversarial-fixes-<NNN>` (one per item)
- **Worktree mode:** each sub-branch is implemented in the main checkout
  in-place. Squash-merges back into the feature branch keep history flat.
- **Final landing:** one PR `feature → main` after Phase 3 cross-cutting
  validation passes.

## Phase ordering

Items are ordered to keep the regression surface small and to let later
items consume the contracts produced by earlier ones.

| Order | ID | Why this slot |
|---|---|---|
| 1 | 011 | Config-only reweight — small, isolated, validates the loop |
| 2 | 015 | Single-allocator constraint — pure function in target_weights |
| 3 | 008 | Correlation filter intra-index dedupe — pure function |
| 4 | 005 | Bond valuation yield anchor — new path in states.py |
| 5 | 007 | Equity earnings-yield sanity anchor — new field on states |
| 6 | 004 | Source-quality tier classifier — new pure module |
| 7 | 001 | Theme research query relevance — depends on source tiering |
| 8 | 002 | Thesis intact requires relevance — depends on 001 |
| 9 | 003 | Provider degradation gate — depends on 001/002 |
| 10 | 006 | Gold drivers into tilt — pipeline rewrite |
| 11 | 012 | Trim-side triggers — config + discipline derivation |
| 12 | 013 | Execution-drift alert — decision diagnostics |
| 13 | 014 | FX/QDII premium diagnostics — memo synthesizer |
| 14 | 010 | Role-bucket failure banner — memo synthesizer |
| 15 | 009 | Audit blocking gate — must be LAST so we know it actually triggers when expected |

## Workflow per item

For each item (per autodev-loop skill):

1. **Write `items/<id>-plan.md`** — exact files, exact code, exact commands.
2. **Create sub-branch** off the feature branch.
3. **Dispatch implementation subagent (Sonnet)** with the spec/plan paths.
4. **Squash-merge** sub-branch into feature branch locally (no GitHub PR
   per item; the feature branch's final PR-to-main is the single review
   surface).
5. **Run focused tests** for the touched module.
6. **Update `PROGRESS.md`** immediately.

The skill's "open PR + QA agent + review agent" loop is collapsed here
because (a) the feature branch is a single PR at the end, (b) tests in
this repo are fast and deterministic, and (c) the prior autodev run on
this repo followed the same worktree-mode collapse. This is documented
deviation, not silent skipping.

## Cross-cutting validation (Phase 3)

After all items merged into the feature branch:

1. **Unit suite green:** `uv run pytest` exits 0 across `tests/`.
2. **Pipeline re-run:** `uv run irc run --date 2026-05-19` (or equivalent
   using the frozen 2026-05-19 inputs) regenerates the seven default
   stages without halting.
3. **Acceptance check:** for each of the 10 acceptance criteria in
   MASTER-SPEC, grep / read the regenerated artifact and confirm the
   criterion holds. Document in `cross-branch-diff.md`.
4. **Final PR:** `gh pr create` from the feature branch into `main`.

## Stop conditions

Stop and report to the user when:

- Same item fails 2 retries with different errors → architectural surprise.
- Full pytest suite goes red on a previously-green test for a reason
  unrelated to the item under test (cross-contamination).
- Re-running `irc run` requires API keys not present in `.env` for
  fetched data → degrade to mock fixtures and document, but do not stop.

## Cost note

15 items × ~1 implementation subagent each ≈ 15 Sonnet dispatches plus
the orchestrator's planning + verification. Phase-3 re-run is a single
pipeline pass.
