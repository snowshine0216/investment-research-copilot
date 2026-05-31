Verdict: PASS

Subagent: sonnet
Source: Fallback used: uv run python -c "..." (direct function exercise)
Entry point exercised: uv run python -c "import and call valuation_fundamental_signal, _fundamental_reason_phrase, classify_valuation, compose_opportunity_state, build_opportunity_row with concrete inputs"

Observed behavior:
  - AC1 (valuation_fundamental_signal, four branches + None): all-None input → None; cheap (0.25) → "cheap"; rich (-0.30) → "rich"; neutral (+0.05) → "neutral"; neutral (-0.05) → "neutral". Thresholds: CHEAP=0.2, RICH=-0.1
  - AC1 (None/dormant production case): valuation_fundamental_signal(equity()) → None — confirmed
  - AC2 (equity reason annotation, 便宜/上行空间): classify_valuation(equity(pct=0.55, upside=0.25)) → state='fair', reason contains "券商一致目标价隐含上行空间 25%，基本面偏便宜。" — 上行空间 present in reason
  - AC2 bug-fix (neutral-negative says 下行空间 not 上行空间): _fundamental_reason_phrase("neutral", -0.05) → "券商一致目标价隐含下行空间 5%，基本面中性。" — 下行空间 True, 上行空间 False
  - AC3(a) corroboration notch (reasonable_low + cheap → cheap): classify_valuation(pct=0.30, upside=0.25) → state='cheap'
  - AC3(b) no jump from fair (fair + cheap → fair): classify_valuation(pct=0.55, upside=0.25) → state='fair'
  - AC3(c) no move toward expensive (expensive + rich → expensive, reason annotated): classify_valuation(pct=0.80, upside=-0.30) → state='expensive', reason contains 下行: True
  - AC3(d) None signal → byte-identical to today: reasonable_low pct=0.30 with no upside → state='reasonable_low'
  - AC4 core_dca blocked by rich fundamental: compose_opportunity_state('cheap','cold','intact','acceptable', valuation_fundamental=None) → 'core_dca'; same with valuation_fundamental='rich' → 'small_watch'
  - AC4 full round-trip via build_opportunity_row: upside=None → opportunity_state='core_dca'; upside=-0.30 → opportunity_state='small_watch'; both rows valuation_state='cheap' (AC3-preserving)
  - AC6 dormant/all-None: bare equity (pct=0.10, no fundamentals) → state='cheap', reason='估值百分位 10% 偏低。' byte-identical whether populated or not
  - AC8 no new ThesisEvidence/gaps: thesis_evidence, evidence_gaps, thesis_state all identical between none_row and rich_row; only opportunity_state and reason differ
  - AC9 tests (23/23 pass, ruff clean on item-002 files): uv run pytest tests/opportunity/test_valuation_fundamental_anchor.py → 23 passed; ruff check src/irc/opportunity/valuation_fundamental.py src/irc/opportunity/states.py tests/opportunity/test_valuation_fundamental_anchor.py → All checks passed
  - Full opportunity suite: 458 passed, 1 skipped (pre-existing skip unrelated to item 002)

Failures: none
