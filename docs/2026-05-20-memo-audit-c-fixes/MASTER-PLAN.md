# Master Plan — Memo Audit C-Fixes (C4–C8)

**Mode:** spec → single feature, multiple commits.
**Branch:** `feat/memo-audit-c-fixes` off `main`.
**Run dir:** `docs/2026-05-20-memo-audit-c-fixes/`.

## Order (per tracker doc recommendation)

1. **C4 — soften macro_summary** (mechanical 1-string edit)
   - `src/irc/commands/memo_cmd.py:308-311`
   - New phrasing: real-yield/USD as "重要参考变量之一", call out geopolitics + CB purchases as alternative drivers, defer A-share valuation specifics to evidence pool.
   - Test: add to `tests/memo/test_memo_inputs.py` (new) — assert `MemoInputs.macro_summary` contains "重要参考变量" and does NOT contain "主导变量".

2. **C6 — execution-line trigger detail** (deterministic)
   - `src/irc/commands/memo_cmd.py:_compose_execution_lines`
   - New format per trigger: `name (data_field comparator threshold)`; emit `AND`/`OR` header from trigger group semantics (default OR, but allow trade plan to declare). Inspect `trade_plan.yaml` shape: each trigger dict has `name`, `data_field`, `comparator`, `threshold`.
   - Tests: extend `tests/memo/test_execution_section.py` with new assertions for comparator/threshold rendering + AND/OR header.

3. **C7 — picks-table methodology footnote** (deterministic)
   - `src/irc/memo/picks_table.py:render_picks_table`
   - Append after the table: a single-line footnote: "综合分由内部多因子模型生成（估值/热度/质量/宏观契合度），仅作为辅助参考，不构成投资建议。"
   - Tests: extend `tests/memo/test_picks_table.py` — assert the footnote line is present in output, and check the disclaimer phrase appears verbatim.

4. **C5 — synthesizer guardrails** (prompt edit)
   - `src/irc/memo/synthesizer.py:_GLOSSARY` (extend) — add rule block: forbid directional price predictions, require explicit "数据缺失" callout when fields absent.
   - Tests: extend `tests/memo/test_synthesizer_glossary.py` — assert new keywords ("方向性预测" forbidden, "数据缺失" required) appear in the user prompt.

5. **C8 — QDII premium guardrail** (prompt edit, paired with C5)
   - Same file (`synthesizer.py`) — add specific rule: forbid "敞口可接受/不可接受" when QDII premium/discount data not provided.
   - Tests: extend `tests/memo/test_synthesizer_glossary.py` — assert "QDII" + "溢价" + "禁止" appear together in user prompt.

## Validation

After each commit:
- Run focused tests (`pytest tests/memo/ tests/commands/test_memo_cmd.py -x`)
- Run `ruff check` on touched files

Final:
- Full suite (`pytest`) — expect 2 pre-existing failures only (per PR #51 baseline)
- Push, open PR, dispatch QA + review subagents in parallel
- Triage findings, fix, re-verify, merge

## Stop conditions

- New unrelated test failures → investigate before next commit
- Synthesizer prompt edits that break `test_synthesize_memo_user_prompt_includes_cost_grade_glossary` → resolve glossary structure first
- Review finds latent bug → fix before merge (no merge-with-known-bug)
