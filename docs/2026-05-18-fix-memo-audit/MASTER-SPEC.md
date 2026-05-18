# Memo-Audit Cleanup Backlog — Master Spec

**Date:** 2026-05-18
**Base branch:** `main`
**Source:** review of `outputs/2026-05-18/` (decision_report, memo + memo_audit, discipline_report, trade_plan)
**PR strategy:** one sub-branch per item, base = `main`, sub-branch prefix = `claude/fix-memo-audit-`. Matches the recent pattern of single-purpose squash-merge PRs (#25-#28).

## Scope classification

| # | Item | Verdict |
|---|---|---|
| 001 | Fix `weekly_drawdown` trigger key mismatch (Tier A #3) | IN |
| 002 | Drop `manager_tenure_years` from cn_bond_fund required metrics (Tier A #5) | IN |
| 003 | Backfill `name_cn` for funds that render as ID-twice in reports (Tier A #7) | IN |
| 004 | Rename `valuation_cost` factor field in evidence pool + glossary (Tier A #1) | IN |
| 005 | Stamp evidence cutoff date into the memo (Tier A #4) | IN |
| 006 | Memo numeric-prose sanity validator (Tier B #11) | IN |
| 007 | Tag `watch_only` rows with the actual reason (Tier B #9) | IN |
| 008 | Derive `venue_status` when no trade exists, drop `unknown` default (Tier C #13) | IN |
| 009 | Deterministic Section 7 ("执行要点") built from the trade plan (Tier A #2) | IN |
| 010 | Allow same-class gold proxy without `tracked_index` match (Tier A #6) | IN |
| 011 | Collapse `decision_report.md` markdown view to 3 reader-first blocks (Tier B #8) | IN |
| B10 | Rewrite synthesizer for per-claim citations | OUT |
| C12 | Zero-weight portfolio holdings that the account cannot execute | OUT |
| C14 | Wire a real macro evidence block (real yield, DXY, CB buying) | OUT |

The three OUT items are documented in `SKIPPED.md` with rationale and unblock paths.

## Execution order (smallest-risk first)

1. **001** — one-line key mismatch fix in `src/irc/trades/triggers.py`. Validates the loop.
2. **002** — extend a single per-asset-class drop list in `src/irc/decision/completeness.py`.
3. **003** — config-only edits in `config/universe/cn_funds.generated.yaml`; need akshare lookup for the 5 names.
4. **004** — rename one field in `src/irc/memo/evidence_pool.py`; add glossary preface to the synthesizer prompt; update one snapshot test.
5. **005** — small plumbing in `src/irc/memo/pipeline.py` + `template.py` to surface the latest `raw_refs` date as `evidence_cutoff` and rewrite the boilerplate "T+1" risk note.
6. **006** — new module `src/irc/memo/numeric_audit.py` + a wire-up in `pipeline.py`; emits warnings into `audit_notes`.
7. **007** — annotate `decide_row` (`src/irc/decision/gates.py`) with a `watch_reason` column (`not_selected_by_allocation` / `score_watch` / `venue_unknown`).
8. **008** — extend `venue_status_for_trade` so a `None` trade falls back to a universe-plus-available-venues lookup; remove the `"unknown"` default for instruments that exist in the universe.
9. **009** — populate `MemoInputs.execution_notes` from the trade plan and render in `template.py`. Drop the HTML-comment placeholder.
10. **010** — relax the `tracked_index` requirement when `target.asset_class == "gold"` and `cross_class is False` in `src/irc/trades/venue_check.py`. Add a regression test for 518880 → `cmb_paper_gold`.
11. **011** — refactor `src/irc/decision/report.py` (markdown rendering only). 3 sections: Actionable buys, Blocked-fixable-today, Watch-collapsed. JSON unchanged.

## Judgment calls made upfront (no further clarification)

- **Item 003 names.** Use the akshare `fund_name_em` / `fund_em_open_fund_info` mapping if reachable; if offline, fall back to the names visible in the project's `outputs/2026-05-18/discovered_watchlist.csv` (`name_cn` column). If neither has a name, mark the row with a deterministic placeholder (`未公开命名`) rather than the raw ID.
- **Item 004 field name.** Use `cost_grade` (0-100, "越高越友好") rather than inverting the number. Inverting risks downstream consumers that read the JSON `factor_breakdown.valuation_cost.score` from `scoring.json`. The evidence-pool emission is the only consumer that needs renaming; the JSON schema stays.
- **Item 005 cutoff source.** Extract date from the first matching `raw_refs` string per evidence pool entry (e.g. `akshare:nav_history:000105:2026-05-15` → `2026-05-15`). Take the maximum date across the pool; surface as `MemoInputs.evidence_cutoff: date`.
- **Item 008 fallback.** When `available_venues` is empty (no account configured), keep `unknown`. Only derive `direct` / `proxy_available` / `blocked_no_proxy` when we actually have `available_venues`.
- **Item 009 contents.** For each trade row emit: `instrument_id`, `target_weight` cap, `buy_method`, `granularity`, trigger list (one per trigger), `venue_note`. No stop-loss / authorization fields — those need policy decisions outside the data layer.
- **Item 010 risk.** Limit the index-free proxy match to `gold` to avoid unintended substitutions in equity classes. Bond classes already proxy within-class only.
- **Item 011 schema.** Markdown output reorganizes; JSON (`decision_report.json`) is the contract for downstream and stays unchanged. Existing tests against the JSON keep passing; markdown tests (if any) get updated.

## Per-item acceptance criteria

Every item must satisfy:
- All existing tests still pass.
- New behavior has a failing test that becomes passing — for items 003/011 where the test is asserting on rendered markdown, snapshot-style assertions are acceptable.
- No re-ingest required to take effect.
- PR description includes a one-line before/after sample drawn from the actual `outputs/2026-05-18/` artifacts.

## Out of scope

- Anything not on the 11-item IN list (no opportunistic refactors).
- Re-running the full pipeline. We verify via unit tests + existing fixtures.
- Schema migrations or breaking JSON changes.
- Network calls during tests.

## Cost / token budget

11 items × ~5 subagent dispatches each ≈ 55 dispatches + ~200K orchestrator tokens. Below the 20-item warning threshold.
