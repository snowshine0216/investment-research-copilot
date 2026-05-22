# Master plan — Thesis-cards / memo / discipline_report evidence-gap remediation

## Mode
- **Detected mode:** backlog (source doc has 10 distinct slices with explicit dependency-ordered execution in §4)
- Brainstorming: invoked per item (Opus subagent) — input is a diagnosis/spec, not a brainstorm
- grill-with-docs (auto-accept): invoked per item (Opus subagent) — backlog mode runs grill automatically
- writing-plans: invoked per item (Opus subagent)
- Spec/plan/grill model: `opus`
- Implementation / drift / verify / pr-review / fix model: `sonnet`

## PR shape
- **Mode A** — one PR per item, each opening into the feature branch
- **Feature branch:** `autodev/thesis-cards-evidence-gap` (synthetic, off `main`)
- **Final landing target:** `main` (protected) — the feature branch is left open at the end of the run; the user reviews and merges it.

## Project type
- **non-web** (Python CLI `irc`) — per-item post-ship verification uses `/verify`, NOT `/qa`. Each item's task graph gets an `<id>-verify` task, not `<id>-qa`.

## Workflow per item

Every item (001–010) walks through the canonical autodev phases:

1. **spec** (Opus subagent invoking `superpowers:brainstorming`) → `items/<id>-spec.md`
2. **grill** (Opus subagent invoking `grill-with-docs` in auto-accept mode) → updated `CONTEXT.md` / new ADRs under `docs/adr/` if needed + refined `items/<id>-spec.md`
3. **plan** (Opus subagent invoking `superpowers:writing-plans`) → `items/<id>-plan.md`
4. **branch** — cut sub-branch off `autodev/thesis-cards-evidence-gap`. Suggested names:
   - 001 → `autodev/thesis-evidence-001-contributing-dimensions`
   - 002 → `autodev/thesis-evidence-002-citation-data-model`
   - 003 → `autodev/thesis-evidence-003-active-fund-constituent-layer`
   - 004 → `autodev/thesis-evidence-004-live-verify-fund-announcement-em`
   - 005 → `autodev/thesis-evidence-005-per-asset-class-citation-coverage`
   - 006 → `autodev/thesis-evidence-006-failure-mode-and-policy-b`
   - 007 → `autodev/thesis-evidence-007-memo-and-discipline-renderers`
   - 008 → `autodev/thesis-evidence-008-integration-test-sweep`
   - 009 → `autodev/thesis-evidence-009-citation-gate-block-mode`
   - 010 → `autodev/thesis-evidence-010-duckdb-fund-holdings-ingest`
5. **impl** (Sonnet subagent invoking `superpowers:subagent-driven-development`) — TDD per task, frequent commits
6. **drift** (Sonnet subagent) — diff vs. plan checklist; FAIL routes through triage-fix
7. **ship** — `/ship` opens PR into `autodev/thesis-cards-evidence-gap`; review verdict captured inline by `/ship` steps 8+9
8. **verify ‖ pr-review** (parallel Sonnet subagents):
   - `/verify` → `<id>-verify.md` (entry-point smoke, e.g. `irc run --from opportunity --limit 3 --output-dir /tmp/...` with relevant evidence about the slice's acceptance)
   - `/code-review` on the open PR → `<id>-pr-review.md`
9. **fix** — triage findings from 3 post-ship verdicts (verify + inline review + pr-review); fix loop until all three PASS or PASS-WITH-NITS (no retry budget; environmental stops only)
10. **merge** — pre-merge gate (protected-base check + ship + drift + grill + 3 post-ship verdicts), then `gh pr merge <PR#> --squash --delete-branch` into `autodev/thesis-cards-evidence-gap`

## Execution order (from source §4 — strict serial up to test landing)

Items land in this order; the per-phase task graph for each item is created at the START of that item's loop iteration, NOT upfront for all 10.

| Step | Item | Source slice | Why this order |
|------|------|--------------|----------------|
| 0    | 001  | A0           | Foundational pure function; 002 and 009 read `contributing_dimensions`. |
| 1    | 002  | D0           | Schema additions must precede any code that constructs `ThesisEvidence` with provenance fields. |
| 2    | 003  | A + G        | Active-fund constituent layer + per-stock structured field; reads D0 schema. |
| 3    | 004  | E13          | Live AkShare verification of `fund_announcement_em` BEFORE 005 (Q4 prerequisite). If it fails, STOP and re-decide Q4. |
| 4    | 005  | F            | Per-asset-class fund-level NAV + announcement (gold/bond/CN ETF/tracked CN indices); QDII exclusion. |
| 5    | 006  | H            | Policy B weight-aware quorum + structured rejection log + H3 universal gapped-row invariant. |
| 6    | 007  | D1 + D3 + D1c | Memo evidence_pool renderer + discipline renderer + alias-builder. |
| 7    | 008  | E (sweep)    | Integration tests lock the publishable set; must be green before 009 flips canonical-path block mode. |
| 8    | 009  | D2           | Audit gate enabled in block mode for canonical paths. |
| 9    | 010  | B            | Independent — DuckDB persistence for scoring. Sequenced last to avoid coupling. |

## Cross-cutting validation (Phase 3 — final)

After all 10 items merge into the feature branch:

- **Workflow-completeness audit** — every IN item has all required verdict files on disk: `<id>-grill.md`, `<id>-drift.md`, `<id>-ship.md`, `<id>-verify.md`, `<id>-review.md` (inline from /ship), `<id>-pr-review.md`. SKIPPED items in `SKIPPED.md` checked against intent.
- **Cross-cutting build/tests** — `pytest -x` runs green on `autodev/thesis-cards-evidence-gap`; `pytest -m live_akshare` runs green where adapters changed; `ruff check` clean.
- **Run-level smoke** — `irc run --from opportunity --limit 3 --output-dir /tmp/autodev-smoke/` exits zero, writes `thesis_cards.yaml`, `opportunity_report.json`, `discipline_report.md`, `rejections.json`. Spot-check that a `cn_equity_fund` row carries non-empty `thesis_evidence` with concrete stock symbols; a QDII row appears only in the discipline failure section.
- **Doc-sync gate** — `CONTEXT.md` and `docs/adr/*` reflect the new types (`ActiveFundSnapshot`, `ConstituentAnalysis`, `CitationMeta`, `FundHolding`) and the citation gate semantics. README touched only if user-facing CLI flags changed (`--limit`, `--rebuild-fundamentals`, `--force-resume`).
- **Close-out commit** on `autodev/thesis-cards-evidence-gap` updating `PROGRESS.md` to all-green and noting that the feature branch is ready for user review/merge into `main`.

## Stop conditions (hard)

- Item 004 (live verify) FAIL → STOP. Re-decide Q4 (fall back to (b) reuse theme reports with promoted scope, or (c) exclude gold + cn_bond_fund from V1).
- `IRC_FETCH_BUDGET` preflight > 2000 on any item's verify step → STOP. Either bump the budget consciously or `--limit` the run.
- Any item's fix loop exits only via environmental stop (missing auth, broken infra, explicit user instruction) — never via "looks stuck, mark BLOCKED and move on".

## Model selection (subagent contract)

| Phase | Model | Why |
|-------|-------|-----|
| Orchestrator (this session) | session default — no override | User's choice; coordinate-only |
| Spec subagent (brainstorming) | `opus` | Authoring intent is judgment-heavy |
| Grill subagent (grill-with-docs auto-accept) | `opus` | CONTEXT.md / ADR updates affect every downstream phase |
| Plan subagent (writing-plans) | `opus` | Plans are the source of truth a Sonnet impl will follow verbatim |
| Implement / drift / verify / pr-review / fix | `sonnet` | Execution against a well-specified plan; fast and cost-effective |

Every `Agent(...)` call MUST include `model=` explicitly.

## Protected-branch invariant

`main` is protected. Sub-PRs target `autodev/thesis-cards-evidence-gap`, NEVER `main`. The pre-merge guardrail in each item's merge phase verifies `gh pr view <PR#> --json baseRefName` is the feature branch before calling `gh pr merge`. The final landing into `main` is left to the user — autodev does not auto-merge protected branches.

## PR shape (re-stated for visibility)

**PR shape: A**
