Verdict: PASS

Subagent: sonnet
Source: src/irc/narrative/report.py, src/irc/narrative/report_appendix.py
Entry points exercised:
  1. `uv run irc narrative --help` — command wired, no import error.
  2. `render_report_md` / `render_report_json` driven offline via inline Python script with a MIXED report (insufficient INS + sufficient EL, both carrying real sub-state verdicts like very_expensive/overheated/intact).
  3. `uv run pytest tests/narrative/test_report.py -q` — 49 passed.

Observed behavior (AC → evidence):

AC1 PASS — all forbidden tokens absent from insufficient block (no 子状态, no 机会/dca/风险, no small_watch/slow_dca/trim_review/very_expensive/overheated/intact/acceptable/weak, no triggers/cadence markers). Locked-grep test `test_insufficient_block_forbidden_tokens_locked` green.

AC2 PASS — 证伪触发, 减仓触发, 复核节奏 absent from insufficient block.

AC3 PASS — block contains `⚠️ 证据不足 / insufficient — 行动建议已抑制 (未形成结论)；缺口: missing_product_metadata, missing_valuation_data；刷新: \`uv run irc narrative 算力金属 --analyze\``.

AC4 PASS — position_risk_level: **insufficient**, 主因/drivers, 说明(risk_rationale), and standalone `- 产品驱动: 费率=0.015 规模=250000000.0 任职=3.5 跟踪误差=—` all present. No 子状态 line.

AC5 PASS — partial evidence renders; inline ref `[ref:20a263fb585956f8]` resolves exactly once in footnote table.

AC6 PASS — sufficient (elevated) block unchanged: 机会/dca/风险, 子状态, 复核节奏, 证伪触发 all present.

Weak-floor legend PASS — legend present when sufficient fund has product_quality_state=weak; absent when the only weak fund is insufficient (orphan guard confirmed).

AC7 PASS — .json for insufficient row carries opportunity_state=small_watch, dca_action=slow_dca, risk_action=trim_review, valuation_state=very_expensive, thesis_state=intact, review_cadence, falsification_triggers, evidence_gaps — unchanged.

AC8 PASS — two render_report_md calls on identical input are byte-identical.

Failures: 0
