Verdict: PASS

Subagent: sonnet
Source: /verify
Entry point exercised: `IRC_ALLOW_STALE=1 uv run irc memo` → outputs/2026-05-28/memo.md (54 184 chars, 40/40 refs verbatim)

Cross-item flow observed:
  - F4 contribution: `build_news_summaries` confirmed active — 7 theme reports loaded, 3 non-empty summaries per instrument (gold/cn_etf/qdii_global); 2026-05-27 scoring.json shows non-neutral thesis_news scores (gold: 60.0, cn_etf: 70.0 vs neutral-50 baseline). `news coverage: X/Y instruments` log fires at score boundary.
  - F5 contribution: `_summary_from_theme_report` verified directly against all 4 previously-broken themes — cn_monetary (62 chars, no `[N]`), geopolitics (200 chars, no `[N]`), us_fiscal_politics (400 chars, no `[N]`), cn_equity_property_policy (210 chars, no `[N]`). F5 P0 strip (`_LLM_REF_MARKER_RE`) confirmed removing embedded `[2]`/`[7]`/`[8]` etc. Cached gold_regime.json (written at 00:35 before F5 landed) still shows `[N]` in 3 themes — expected; next gold stage run will produce clean output.
  - F6 contribution: `_format_appendix_line` cache-transition guard fires on both `财报已披露（口径未核实）` (new phrase) and `revenue_yoy=` (legacy). 12 filing rows in appendix each received `⚠️ 合规警示` caveat. New `snapshot.py` template (`财报已披露（口径未核实）`) confirmed in source diff. `sanitize_unverified_revenue_yoy` in pipeline.py sanitizes any body leakage; `sanitize_compliance_phrasing` normalises per-field caveat to unified form.

Failures: none new — 1 pre-existing failure (`test_build_rows_qdii_row_carries_sentinel_gap`, confirmed fails on main branch identically)
Test count: 1327 passed, 1 failed (pre-existing), 1 skipped
