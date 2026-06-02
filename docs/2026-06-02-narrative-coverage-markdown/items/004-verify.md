Verdict: PASS

Subagent: sonnet
Source: src/irc/narrative/report.py, src/irc/narrative/report_appendix.py
Entry points exercised:
  1. `uv run irc narrative --help` — command wired, no import error.
  2. `render_report_md` / `render_report_json` driven offline via inline Python script with a MIXED report
     (1 insufficient fund: real sub-state verdicts expensive/overheated/intact/weak + non-empty evidence_gaps
     + product_metrics + thesis_evidence; 1 sufficient fund: elevated).
     Called as `render_report_md("算力金属", reports, name="compute_metals")` — display_label != narrative_id.
  3. `uv run pytest tests/narrative -q` — 151 passed, 1 skipped.

Observed behavior (AC → evidence):

F1-fix PASS — Refresh line:
  `- ⚠️ 证据不足 / insufficient — 行动建议已抑制 (未形成结论)；缺口: missing_valuation_data, missing_product_metadata；刷新: \`uv run irc narrative compute_metals --analyze\``
  Contains 'compute_metals': True. Contains '算力金属': False. The prior PASS erroneously showed '算力金属'
  in this line (commit eeaec42 introduced the `name` kwarg fix; this run confirms it is active).

AC1 PASS — All forbidden tokens absent from insufficient block (no 子状态, no 机会/dca/风险,
  no slow_dca, small_watch, expensive, overheated, intact, weak, very_expensive, crowded,
  under_pressure, falsified, poor, cheap, acceptable, no 证伪触发, 减仓触发, 复核节奏).

AC2 PASS — 证伪触发, 减仓触发, 复核节奏 absent from insufficient block (covered by AC1 check above).

AC3 PASS — ⚠️ 证据不足 line present; names evidence_gaps (missing_valuation_data,
  missing_product_metadata); points at `--analyze` not `fundamentals snapshot`.

AC4 PASS — position_risk_level: **insufficient**, 主因/drivers line, 说明 (risk_rationale) line,
  and standalone `- 产品驱动: 费率=0.5 规模=1000000000.0 任职=3.0 跟踪误差=—` all present.
  No 子状态 line.

AC6/sufficient PASS — sufficient (elevated) block unchanged: 机会/dca/风险, 子状态, 证伪触发,
  减仓触发, 复核节奏 all present.

AC7 PASS — render_report_json for insufficient fund carries opportunity_state=small_watch,
  dca_action=slow_dca, risk_action=none, falsification_triggers=['trigger_A'],
  trim_triggers=['trim_B'], review_cadence=monthly — full source of truth unchanged.

AC8 PASS — Two render_report_md calls on identical input are byte-identical.

Failures: 0
