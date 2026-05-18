# Item 004 — Rename `valuation_cost` in evidence pool + add glossary

## What

The memo audit caught a contradiction on `000105`: "状态=cheap … valuation_cost=85". The data is fine; the labels collide.

- `valuation_state` ("cheap" / "expensive" …) comes from a **price percentile** (`src/irc/opportunity/states.py:59-79`).
- `valuation_cost` (0–100) is the **expense-ratio + premium-discount cost score** (`src/irc/scoring/factors/valuation_cost.py:13-23`). Higher = cheaper to hold = better.

`build_evidence_pool` (`src/irc/memo/evidence_pool.py:28-31`) emits both side-by-side under names containing "valuation", so the LLM (and any reader) treats them as the same axis. The synthesized memo then narrates "valuation_cost=85 ⇒ 估值极高 ⇒ 赔率不佳" — exactly inverted from what the score means.

## Files to touch

- `src/irc/memo/evidence_pool.py` — emit `cost_grade` instead of `valuation_cost`; keep the other 4 factor names (`risk`, `quality`, `macro_fit`, `thesis_news`) unchanged.
- `src/irc/memo/synthesizer.py` — prepend a 1-block glossary to the user prompt so the LLM cannot collapse the two axes.
- `tests/memo/test_evidence_pool.py` — update the field-name assertion.
- `tests/memo/test_synthesizer.py` (if it exists) — add a prompt-shape assertion.

## Acceptance criteria

- Evidence-pool lines emitted by `_format_instrument_evidence` use `cost_grade=NN` where today they use `valuation_cost=NN`. The other 4 factors (`risk`, `quality`, `macro_fit`, `thesis_news`) keep their names.
- JSON outputs are unchanged. `scoring.json` keeps `factor_breakdown.valuation_cost.score` exactly as today. The rename is *display-only*, scoped to the memo evidence emission.
- `synthesize_memo` user prompt now contains an explicit glossary block, e.g.:
  > 字段说明：`状态=A/B/C/D` 是基于估值百分位（A）、热度（B）、长期逻辑（C）、产品质量（D）的分桶；`cost_grade` 是 0-100 的持有成本评分（费率+折溢价，越高越友好），与`状态`中的估值分桶是两个独立维度，不可互换解读。
- A new test asserts that `_format_instrument_evidence(...)` for `000105` contains `cost_grade=` and does not contain `valuation_cost=`.
- A new test asserts `synthesize_memo` includes the glossary phrase `cost_grade` in the user message it constructs (use `monkeypatch` to capture the message; do not hit the network).
- The full suite is green.

## Out of scope

- Renaming the JSON schema field.
- Changing the scoring formula in `factors/valuation_cost.py`.
- Touching the auditor — let the next item (006) introduce the numeric-prose validator.
