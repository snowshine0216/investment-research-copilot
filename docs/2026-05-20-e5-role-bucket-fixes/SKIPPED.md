# Skipped / out-of-scope items

These were considered but excluded from this run. Each entry notes the reason and the unblock path.

## "Surgical split" of `cn_equity_fund` into broad-vs-themed DD buffer

**Why skipped:** The blanket buffer raise (1.6 → 1.8) is the report's primary recommendation. The surgical split would require a new schema field (`drawdown_3y_buffer_by_asset_class_themed` or per-(asset_class, theme) overrides) and changes to `quality_filter._drawdown_max`. That's a real refactor; the lighter knob change should be tried first.

**Unblock path:** If QA on this run reveals junk-quality picks promoted to the memo (visible in `picks_table` after a real pipeline run), follow up with a surgical-split PR.

## Lower `fail_below: 5 → 3` (alt fix for `satellite_cn_soe`)

**Why skipped:** Option A in the report (add SOE proxies) is preferred over Option B (lower threshold) because lowering `fail_below` weakens the gate for every role globally.

**Unblock path:** If the universe additions don't lift SOE above 5 candidates, revisit.

## Manual pipeline rerun + memo regen on user environment

**Why skipped:** Running `irc run` end-to-end requires the user's local DuckDB state, FRED/akshare data, and model API keys. We verify via focused tests + the existing test suite.

**Unblock path:** User runs `irc run --resume` after merge; if regressions appear, follow up.

## Adjusting `cn_etf` DD buffer

**Why skipped:** The report does not call for changing `cn_etf: 1.4`. ETFs aren't the failure mode — active themed funds are.

## Adding instruments not named in the E5 report

**Why skipped:** Discipline. The report named specific candidates; expanding the list invites un-vetted instruments.
