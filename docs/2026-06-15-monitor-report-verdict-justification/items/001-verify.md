# 001 — Verify verdict (exit gate)

Verdict: **PASS**

Project type: non-web (Python CLI → static HTML). Verification = the user-specified exit
gate: regenerate today's `outputs/2026-06-15/monitor/report.html` with the new renderer and
confirm the per-fund cards match the approved mockup.

## Method

Ran `uv run irc monitor` (live refresh — no cache-reuse exists for impacts/narrative, so this
is a real MiniMax + web-search run; NAV from DuckDB cache). Spend preflight passed; report
rewritten atomically at 20:00:13. (Data differs slightly from the 19:13 run because it is a
fresh fetch — the gate validates *rendering*, which is what changed.)

## Evidence

- **7 fund-cards** rendered (H3 universal rows — every Monitor-set fund present).
- Per report: 7 verdict blocks, 7 factor tables, 7 returns tables, 7 price-action sections,
  7 risk blocks, 19 N/A factor rows. **No** bare `class='missing'` list.
- **Citation closure:** 100 rendered `[ref:…]` anchors == 100 evidence-appendix ids, 0 orphans.
- **Verdict summaries (all 7, self-explaining):**
  - 270023 → `综合分 C = 0.6297（≥ 买入阈值）→ ADD_BIAS`
  - 008986 / 519069 / 260112 / 000083 → `… （落在中性带内）→ NEUTRAL`
  - 006533 / 009225 → `insufficient_evidence — families 2 / available_weight 0.50 未达门槛 → NO_CALL`
- **Sample card 006533 (NO_CALL)** renders: verdict clause + lead MiniMax rationale; returns
  `5d +5.79% … 250d +201.28%`; factor table `trend 0.7974·w'0.60·0.4785·conf1.0·fresh`,
  `macro_tilt -0.38…`, dimmed N/A rows `valuation(valuation_no_anchor)`, `heat(heat_no_data)`,
  `constituent(constituent_no_coverage)`, footer `综合 C=0.3265 · 置信 0.9400 · available wt
  0.5000 · families: news、price-momentum`; price-action section; risk block with divergence
  caveats (趋势与宏观背离, 因子分歧较大) + MiniMax risk commentary. Matches the mockup.
- Scoped suite: **176 passed, 7 skipped**; ruff clean.

Matches the approved mockup `monitor_card_redesign_mockup` (verdict block → chart → returns
→ factor table → price-action → risk).
