Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct CLI + python3 inspection
Entry point exercised:
  - `uv run irc eval-funds --ids "000127,000390,000452,001008,001054,001069,001075,001076,001158,001184"`
  - `uv run irc eval-funds --ids "999999,000127"` (degraded-data / honesty check)

Observed behavior:

- **Output files written** — both `outputs/2026-06-01/fund_eval.md` (1 391 bytes) and
  `outputs/2026-06-01/fund_eval.json` (15 767 bytes) were created atomically.
  ```
  eval-funds OK: 0 core_dca / 10 evaluated -> outputs/2026-06-01/fund_eval.md
  ```
  ```
  -rw-------@ 1 snow  staff  15767 Jun  1 19:49 outputs/2026-06-01/fund_eval.json
  -rw-------@ 1 snow  staff   1391 Jun  1 19:49 outputs/2026-06-01/fund_eval.md
  ```

- **Markdown structure** — `fund_eval.md` opens with a `## core_dca 候選` headline section
  (listed `（無）` for 0 qualifiers), followed by `## 全部評估 / Full sub-state table` with a
  pipe-delimited table header:
  `| 代码 | 名称 | 估值 | 热度 | 逻辑 | 质量 | 机会 | 定投 | core_dca |`
  and exactly 10 data rows — one per requested fund — covering columns
  valuation / heat / thesis / product-quality / opportunity_state / dca_action / core_dca.

- **JSON structure** — `fund_eval.json` contains a top-level `"funds"` array. Each object
  has all required fields: `instrument_id`, `name_cn`, `valuation_state`, `heat_state`,
  `thesis_state`, `product_quality_state`, `opportunity_state`, `dca_action`,
  `core_dca` (boolean), `note_cn`, `top_holdings` (array of [symbol, name_cn, weight]),
  `evidence_gaps` (array), `role`.
  Sample (fund 000452):
  ```json
  {
    "instrument_id": "000452", "opportunity_state": "small_watch",
    "core_dca": false, "dca_action": "slow_dca",
    "top_holdings": [["600276", "恒瑞医药", 7.11], ...],
    "evidence_gaps": [], "role": "satellite_cn_metals"
  }
  ```

- **Honesty — degraded data** — running with `--ids "999999,000127"` (999999 has no DuckDB
  NAV and no cached snapshot):
  - 999999 resolved with `opportunity_state=small_watch`, `core_dca=False`,
    `evidence_gaps=['missing_valuation_data', 'missing_flow_or_return_data',
    'missing_product_metadata', 'missing_constituent_snapshot', ...]`.
  - `core_dca=False` is correctly reported even though evidence_gaps contains
    `missing_constituent_snapshot` and valuation data is absent.
  - No crash observed on degraded input.

- **No spurious `core_dca=True`** — all 10 funds evaluated in the primary run have
  `core_dca=False`; none of the funds with any insufficient sub-state claim `core_dca=True`.

- **Tests** — all 13 tests in `tests/opportunity/test_fund_eval.py` and
  `tests/commands/test_fund_eval_cmd.py` pass (0.57 s).
  Key test coverage:
  - `test_evaluate_fund_snapshot_none_surfaces_missing_constituent_gap` — snapshot=None path
  - `test_evaluate_fund_insufficient_inputs_yields_insufficient_substates` — insufficient_evidence honesty
  - `test_run_eval_funds_errors_clearly_when_db_missing` — rc 2 clean error path

- **Ruff** — `ruff check` clean on all modified source files.

Failures: none
