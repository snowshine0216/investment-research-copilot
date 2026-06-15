# 001 — Ship verdict

PR: https://github.com/snowshine0216/investment-research-copilot/pull/131
Base: `main` (PROTECTED — opened, left OPEN, NOT merged; no user opt-in to merge to main)
Head: `autodev/001-monitor-verdict-render`

**Fallback used:** `gh pr create`, not `/ship`. Reason: project convention (memory
`project_versioning_convention`) forbids per-feature VERSION bumps — features accumulate
under CHANGELOG `[Unreleased]` at a static VERSION. The generic `/ship` bumps VERSION, which
would violate that. So VERSION is intentionally unchanged; CHANGELOG `[Unreleased]` updated
instead. Branch pushed, PR opened.

**Review surface:** because the `/ship` inline review (steps 8+9) was bypassed by the
fallback, the substantive code review is provided by a single `/code-review` pass on the
diff (recorded in `001-review.md` / `001-pr-review.md`). Pre-merge gate counts that pass +
the verify verdict.

N=1 branch collapse: the sub-branch PR targets `main` directly (rather than a sub→feature
→main two-PR chain) since there is only one item. All run docs (spec, plan, drift, ship) and
the implementation are in this one PR.
