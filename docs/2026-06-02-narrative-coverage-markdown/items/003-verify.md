Verdict: PASS

Subagent: sonnet
Source: branch claude/narrative-coverage-markdown-003
Entry points exercised:
- `uv run irc narrative --help` — command wired, no import error
- `render_report_md` / `render_report_json` driven directly via inline Python snippet
- `uv run pytest tests/narrative/test_report.py -q` — 33 tests

## Observed behavior (AC → evidence)

**AC1 — Inline bullet has summary prose + cap at 3:**
Rendered section showed exactly 3 `[ref:hex]` bullets, each ending with ` · {summary}`:
```
  - [ref:81290d723546d2f2] filing · cninfo · 2026-03-31 · 宁德 2026Q1 财报
  - [ref:eb61bf7f7b7d2e2d] filing · xinhua · 2026-03-31 · 矿业利好政策
  - [ref:0eeb22f7c26b1fc4] news · src5 · 2026-03-05 · headline-5
```

**AC2 — 16-hex refs:** 9 total refs in md; all matched `[0-9a-f]{16}`.

**AC3 — Per-constituent one_line_view in appendix:**
`601899 紫金矿业 (权重 8.5%): 紫金矿业 营收 +20%` present in block.

**AC4 — Every inline [ref:hex] resolves in 证据明细:** 5 distinct refs in block; each had exactly 1 matching footnote line. Constituent-only ref `39f89df505947d44` (NOT in `thesis_evidence`) resolved:
```
[ref:39f89df505947d44] broker · GS · 2026-04-01 · GS: 紫金强烈推荐 · http://gs.com/r1
```

**AC5 — Determinism:** Two `render_report_md` calls on identical input → byte-identical. Same for `render_report_json`.

**AC6/AC7 — Product drivers with `—` for None:**
- `pm_real`: `费率=0.005 规模=5e+08 任职=7.0 跟踪误差=—` (tracking_error=None → `—`)
- `pm_none`: `费率=— 规模=— 任职=—` visible metadata-floor signal

**M2 (F-1 legend):** `结构性下限` and `产品驱动` both present in output when any fund is `weak`.

**AC8 — .json evidence includes summary + url:**
`doc["funds"][0]["thesis_evidence"][0]` had `summary='宁德 2026Q1 财报'`, `url='http://cninfo.com/1'`. Constituent evidence also carried `summary` + `url`. `product_metrics` and `constituent_analyses` round-tripped intact.

**AC10 — SAME-3/memo suite:** `tests/memo/` → 387 passed.

**AC11 — No scorer change:** `git diff main -- src/irc/opportunity/states.py` shows only a type-annotation widening (`FundLevelSnapshot` added to union), not a classifier change. `states.py`, `thesis_evidence.py`, `risk.py` classifiers untouched.

**Test suite:** `tests/narrative/test_report.py` → **33 passed**.

## Failures

None. All 11 ACs verified (AC9 corroborated by the 33-test pass; AC10 by 387-test memo pass; AC11 by diff inspection).
