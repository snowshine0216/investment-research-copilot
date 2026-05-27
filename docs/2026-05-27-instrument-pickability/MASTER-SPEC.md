# MASTER-SPEC — Instrument Pickability Fixes

**Mode**: `backlog` (3 IN items + 3 OUT items deferred to SKIPPED.md)
**Detected at**: 2026-05-27
**Origin**: Findings from review of `outputs/2026-05-27/memo.md` and `discipline_report.md`. The current memo cannot answer "which of the 10 候选可执行 should I pick when triggers clear" — three concrete gaps prevent that judgment. This run closes the three highest-impact gaps.

## Goal of the run

Make the weekly memo + discipline report **sufficient to choose an instrument** (not just sufficient to decide "no action this week"). Specifically, when triggers eventually fire, the user should be able to read §5/§6/§7 and confidently pick which 1–3 of the 候选 list to act on.

## IN-scope items (3)

| ID | Title | Why it matters | Rough surface area |
|---|---|---|---|
| **001** | `broker_empty` propagation → standing demotion | Top-5 持仓 `⚠️ broker_empty:xxx` markers currently appear as cosmetic warnings only — they do not affect `opportunity_status` or pick ordering. Two evidence-incomplete funds can both appear as `small_watch` despite having half their Top-5 missing broker coverage. | Small: extend opportunity scoring rule + §6 风险提示 row + tests |
| **002** | Holdings overlap / concentration panel in §6 | The current `small_watch` list contains 4–5 funds whose Top-5 holdings are 60–80% identical (新易盛/中际旭创/天孚通信 翻来覆去). A user reading §5 sees "diversified candidates" but is actually being offered the same CPO/光模块 bet 4×. No concentration warning exists today. | Medium: new pure-analytics module + §6 panel + per-row note in §5 + tests |
| **003** | QDII premium/discount snapshot + hard execution block | 4 of 10 候选 (017641, 019441, 513690, plus future QDII picks) carry cross-border settlement risk. §6 today reads "数据未采集——请在交易前查阅各 QDII 二级市场溢价" — i.e. the report knows it's missing critical execution data but does nothing. Users may buy QDII at peak premium without knowing. | Large: new AkShare fetcher + snapshot cache + §5 column + §6 risk row + §7 hard block + tests |

**Item ordering rationale**: 001 first (smallest surface, fewest dependencies, validates the autodev loop). Then 002 (pure analytics over existing data). Then 003 (largest — adds new I/O fetcher + execution gate). All three are independent (no item depends on another's code); dependency-scan should confirm this.

## OUT-scope items (3) — see SKIPPED.md

- **F4**: `thesis_news=50` constant → real news-scored differentiation
- **F5**: §2 macro research excerpts truncated to first line / heading
- **F6**: Filing data orphan — compliance warning vs. evidence role

These are deferred per the user's P0-only scoping decision this turn. Reasons in SKIPPED.md.

## Acceptance gate for the run

A simulated rerun of the pipeline against today's outputs (2026-05-27) produces a memo where:

1. §6 风险提示 contains a new "证据缺口" row enumerating picks with ≥2 broker_empty in Top-5 (Item 001)
2. §6 风险提示 contains a new "持仓集中度" row showing weighted-overlap pairs ≥ threshold (Item 002)
3. §5 picks table includes a `溢价` column populated for all QDII roles, and §7 触发条件 contains a hard `qdii_premium_high` gate for those roles (Item 003)
4. No regression in existing IRC_*_BEGIN/END deterministic markers or H3/SAME-3 invariants
5. All existing tests pass; new behavior covered by unit tests
