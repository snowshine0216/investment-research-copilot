Verdict: PASS

## Subagent

`grill-with-docs` (auto-accept mode), dispatched by `autodev` to harden `items/003-spec.md` against the project's domain model before the plan phase reads it.

## Questions resolved

11 questions resolved (G-Q1 through G-Q11). Mapped to the spec's `## Resolved decisions (grill pass, 2026-05-27)` appendix.

## Docs touched

- **CONTEXT.md** — appended four new entries under "QDII premium-to-NAV":
  - `QDII_PREMIUM_THRESHOLD_PCT` (re-export alias)
  - 溢价 column (picks-table §5 13th column)
  - `qdii_premium.json` projection (top-level audit-trail artefact)
  - `IRC_QDII_PREMIUM_BEGIN/END` marker (deterministic §6 marker block)
- **docs/adr/0006-qdii-premium-memo-surface.md** — created. Four decisions locked: (1) new `溢价` column + 13-column lock migration, (2) top-level `qdii_premium.json` projection artefact with always-written invariant, (3) explicit `0.00%（场外申赎）` off-exchange suffix, (4) §7 hard-block prefix at memo_cmd edge (not template). Rule-of-three test: all three legs pass (hard-to-reverse / surprising / real tradeoff). Cross-references ADR 0001, ADR 0002 §5 F6, ADR 0004.
- **docs/2026-05-27-instrument-pickability/items/003-spec.md** — refined in-place. Two strikethrough corrections (AC11 fixture location; AC12 call-site count) + `## Resolved decisions (grill pass, 2026-05-27)` appendix with 11 Q&A entries.

## Spec refined

In-place edits:

- **AC11 strikethrough**: removed the incorrect claim that `tests/integration/test_publishable_set_lockdown.py` locks the picks-table column count. Verified by grep — the integration lockdown locks two-run byte-equality of `memo.md`, which absorbs the new column automatically. The canonical column-order lock is `tests/memo/test_picks_table.py::test_picks_table_header_contains_tranche_cap_and_trigger_status_columns` (lines 285–301), which DOES need a 3-step → 4-step index-chain migration.
- **AC12 correction**: PickRow call-site count corrected from "21" to "34" (2 production + 32 test, verified via `grep -rn "PickRow(" src/irc/ tests/`).

## Resolved decisions Q&A summary

- **G-Q1**: Picks-table column count is locked in `tests/memo/test_picks_table.py:285–301`, NOT in `test_publishable_set_lockdown.py`.
- **G-Q2**: §6 marker block format locked — `<!-- IRC_QDII_PREMIUM_BEGIN -->` header line + per-row bullets sorted by `instrument_id` ASC + `<!-- IRC_QDII_PREMIUM_END -->`. Empty projection → legacy placeholder. Marker constants live in `qdii_premium_lines.py` (producing-module pattern).
- **G-Q3**: §7 prefix format locked — `⛔ qdii_premium_too_high（{render_cell} > {threshold_pct*100:.0f}%，已暂缓）｜` (full-width separator U+FF5C), prepended at `memo_cmd.py` level, not `template.py`.
- **G-Q4**: Off-exchange cell `0.00%（场外申赎）` confirmed (NOT `—`). The economically-correct value IS known; the suffix is the disambiguation channel.
- **G-Q5**: `qdii_premium.json` always-written (empty `rows: []` when no QDII candidates). Missing file = build error.
- **G-Q6**: Top-level placement confirmed — verified `outputs/2026-05-27/` inventory; `data/` reserved for DuckDB cache.
- **G-Q7**: ADR 0006 rule-of-three test PASSES on all three legs. ADR created.
- **G-Q8**: ADR 0002 §5 F6 cross-reference is accurate; no contradiction with this ADR.
- **G-Q9**: Four new CONTEXT.md entries added under "QDII premium-to-NAV", each cross-referencing ADR 0006.
- **G-Q10**: AC12 call-site count corrected via strikethrough (21 → 34, verified).
- **G-Q11**: `name_cn` is in scope at projection-build time via the existing `opportunity_rows` already consumed by `_build_pick_rows`. No new I/O path needed.
