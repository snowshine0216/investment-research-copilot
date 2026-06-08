# PROGRESS — Phase A legulegu rate-limit (spec mode, N=1)

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

**Project type:** non-web → post-ship verifier is `/verify` (no `/qa` column).

## Cell notes

- **001-spec** ✅ — `items/001-spec.md` (verbatim copy of the grilled design spec).
- **001-grill** ⏭️ — user-grilled before handoff (rev3 + ADR 0014 + CONTEXT.md, commits `7841f48`→`9692a2f`). Orchestrator must not auto-invoke grill in spec mode.
- **001 remaining** ⏳ — plan (Opus writing-plans) is the entry phase.

## Live-network operator gates — DEFERRED (run later, each in its own recovered cold window)

These are **not** run in this autonomous session (limiter in deep cooldown; environmental stop). Operator follow-up after merge:

- **Gate #4 (alone):** `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare tests/fundamentals/test_index_valuation_live.py -v -s -x` → 4 passed. (`-x` load-bearing.)
- **Gate #3 (alone):** `uv run irc run --from ingest` → `count_grounded.py outputs/<date>/opportunity_report.json` ≥ 9 grounded.
- **Gate #5 (alone):** steps 1–5 in `docs/2026-06-05-phase-a-broad-grounding/before-after.md`.
- **(Optional) speculative sweep:** `IRC_RUN_LIVE_AKSHARE=1 IRC_RUN_LEGULEGU_SPECULATIVE=1 uv run pytest …`.

## Run log

- 2026-06-08 — intake: spec mode, non-web, PR shape A. Run dir + design artifacts created. Feature branch `phase-a/legulegu-rate-limit`; sub-branch `phase-a/legulegu-rate-limit-impl` (to be cut at branch phase).
