Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct entry-point (uv run python -c)
Entry point exercised:
  - `uv run irc --help`
  - `uv run python -c "... classify_valuation / COMMODITY_CYCLICAL_THEMES ..."` (symmetric guard)
  - `uv run python -c "... _csindex_pe_ttm_map / fetch_cn_sector_index_valuation_history ..."` (csindex fetcher)
  - `uv run python -c "... derive_position_risk_level ..."` (narrative risk driver)
  - `grep -n 基金概況 src/irc/fundamentals/akshare_index_valuation.py` (forbidden string)

Observed behavior:

  - **CLI loads** — `uv run irc --help` printed the full command list including opportunity / narrative; exit 0.

  - **Symmetric guard (cn_equity_fund + metals, NAV only, low pct = 0.05)** — `classify_valuation` returned `evidence_insufficient` with reason "NAV 价格百分位是动量而非估值；该周期性主题无基本面锚（PE 历史），方向性估值判断暂缺。" (would have been `cheap` without guard). PASS.

  - **Symmetric guard (cn_equity_fund + metals, NAV only, high pct = 0.95)** — returned `evidence_insufficient` with same reason (would have been `very_expensive`). PASS — guard is symmetric per invariant.

  - **qdii_global + metals guard** — `asset_class='qdii_global'`, `theme='metals'`, `valuation_percentile_fundamental=None`, `valuation_percentile_self=0.92` → `evidence_insufficient`. Cross-asset-class lock confirmed. PASS.

  - **metals WITH PE anchor (fund_pct=0.05)** — guard skipped; returned `cheap` with reason "PE 百分位 5% 偏低." — PE rule fires correctly once fundamental anchor present. PASS.

  - **Non-metals equity no regression (theme=semiconductor, pct=0.95)** — returned `very_expensive` with reason "估值百分位 95% 极高." — guard does not touch non-cyclical themes. PASS.

  - **COMMODITY_CYCLICAL_THEMES value** — `frozenset({'metals'})` as specified in §1. PASS.

  - **`_CSINDEX_PE_TTM_COL`** — printed `市盈率1`. PASS.

  - **`_csindex_pe_ttm_map` reads 市盈率1** — frame with cols `日期/市盈率1/市盈率2/股息率1/股息率2` → PE values `[26.97, 27.5, 28.1]` from 市盈率1; frame with only 市盈率2 → empty map. PASS.

  - **Unknown slug returns None** — `fetch_cn_sector_index_valuation_history('unknown_index_key')` → `None`. PASS.

  - **`fetch_cn_sector_index_valuation_history` with monkeypatched frame** — `pe_ttm=26.97` (from 市盈率1), `pb=None`, `dividend_yield=None`; `index_key='csi_nonferrous'`. PASS.

  - **Narrative driver (evidence_insufficient, empty evidence_gaps)** — `derive_position_risk_level` with `valuation_state='evidence_insufficient'`, `evidence_gaps=()` → level `moderate`, rationale `"moderate — valuation withheld — no fundamental anchor"`, drivers `('valuation_state',)`. Not `insufficient`, not silently `low`. PASS.

  - **`基金概况` forbidden** — `grep` on `src/irc/fundamentals/akshare_index_valuation.py` returned no output (string absent). PASS.

Failures: none
