# MASTER-SPEC — `irc eval-funds` targeted fund evaluation command

**Mode:** spec (single feature; N=1)
**Source:** `docs/superpowers/specs/2026-06-01-eval-funds-command-design.md`
**Date:** 2026-06-01

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | `irc eval-funds` — targeted per-fund evaluation command (new pure core `fund_eval.py` + `_build_input` extraction + command edge + CLI wiring + docs) | **IN** | Single coherent feature, fully specified with goals / non-goals / acceptance criteria. Reuses existing classification logic; no SME / credentials / external blockers. |

No OUT-scope items (single-feature spec). See `SKIPPED.md` (empty).

## Out-of-spec (explicit non-goals — carried from the design's §2)

These are **not** failures to be fixed in this run; they are deliberate boundaries:

- Not fixing the `ingest` exit-1 failure (tracked separately).
- Not changing discovery, scoring, the active-fund cap, or any existing pipeline output.
- Not fetching live data (reads cached snapshots + existing DuckDB).
- Not applying Policy B as a gate (publishability MAY be an informational flag only).
- Not persisting to the standard `opportunity_report.json`.

## Acceptance (carried from design §8)

`uv run irc eval-funds --ids "<metals ids>"` writes `outputs/<today>/fund_eval.{md,json}`;
the md lists the `core_dca` funds + a full sub-state table; the new tests
(`tests/opportunity/test_fund_eval.py`, `tests/commands/test_fund_eval_cmd.py`) and the
existing `opportunity_cmd` suite pass; `ruff check src tests` is clean.
