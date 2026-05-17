# P1 + P2 Backlog — Master Plan

## Workflow rules

1. Each item gets its own per-item spec (`items/<id>-spec.md`) and plan (`items/<id>-plan.md`).
2. Each item gets its own sub-branch off `feat/evidence-wiring-and-memo-enrichment`:
   - `claude/p1p2-005-evidence-gaps-cleanup`
   - `claude/p1p2-006-news-cause-codes`
   - `claude/p1p2-007-traceability-honest-counts`
   - `claude/p1p2-008-venue-registry-backfill`
   - `claude/p1p2-009-fundamentals-backfill`
   - `claude/p1p2-010-geopolitical-stress-wired`
   - `claude/p1p2-004-freshness-gate`
3. Each item goes through the full loop: spec → plan → branch → impl (subagent) → PR → QA + review (parallel subagents) → triage → fix → merge.
4. Per-item commits are squashed at merge so the feature branch keeps one commit per item.
5. After merge of each item, `PROGRESS.md` is updated immediately.

## Subagent model

- Orchestrator (this session): Claude Opus.
- All dispatched subagents: Claude Sonnet (default).

## Branch & PR conventions

- Base branch for all PRs: `feat/evidence-wiring-and-memo-enrichment`
- PR title: `<type>(<scope>): <one-line summary> (p1p2-<id>)`
- PR body: summary bullets + link to `items/<id>-spec.md` + test plan

## QA + Review

- QA subagent runs the full pytest suite + verifies the per-item acceptance criteria from the spec.
- Review subagent reads the diff and reports `PASS` / `PASS-WITH-NITS` / `FAIL`.
- Triage rules per `autodev-loop` skill: latent bugs blocked, cosmetic nits ship.

## Final validation (Phase 3)

After all items merge:
- Run full `pytest -q` on the feature branch.
- Run `ruff check src/ tests/`.
- Re-render today's pipeline outputs against the new code (with `irc gold`, `irc score`, `irc allocate`, `irc plan`, `irc memo` — note ingest is still gated by network; we'll use existing 2026-05-17 DuckDB if present, otherwise skip the re-render and document).
- Update `HANDOFF.md` with the merged-items summary.
- Write `docs/AUTODEV-LOOP/cross-branch-diff.md` if any cross-item interactions surfaced.

## Stop conditions

Per the autodev-loop skill — if any item fails 2 retries with different errors, mark BLOCKED in `PROGRESS.md`, document the blocker, and continue with the next item. Honest reporting > silent retries.
