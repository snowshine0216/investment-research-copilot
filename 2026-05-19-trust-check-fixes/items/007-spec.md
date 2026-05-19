# 007 — "Today's only action" headline

## Why

Trust-check priority #1, A1, B1: the report opens with a 100-row
table spread across `decision_report.md`, `memo.md §5/§7`, and
`discipline_report.md`. A non-finance reader needs one sentence:

> "This week: contribute up to X% of monthly capital to 000139 only;
> do nothing on the other six."

After items 001–006, the decision_report's `actionable_buy` set
already represents the intersection of score gates + allocation +
audit + venue + QDII premium — i.e., the same intersection the
trust-check called for. We just need to display it as the *first*
thing the reader sees.

## What changes

`src/irc/decision/models.py` — add two fields to `DecisionRow`:

```python
target_weight: float = 0.0
role: str = ""
```

`src/irc/decision/gates.py:decide_row` — accept `target_weight` and
`role` kwargs; pass to `_build_decision_row`.

`src/irc/decision/report.py`:

- `_build_rows`: look up `target_weight` from `allocation.selected_instruments`
  (already passed in) and `role` from `trade_plan.trades`. Pass to
  `decide_row`.
- `render_decision_markdown`: emit a new section ABOVE Verdict:

```markdown
## 今日唯一行动 / Today's only action

✅ **000139 富国国有企业债债券A/B** — defensive_cn_bond, target 5.4%.

(或者 actionable_buy rows are absent:)

⏸️ 本周无可执行标的 — 详见下方 Verdict 阻断原因。
```

## Acceptance criteria

- When >=1 actionable_buy row exists, the section lists each with
  `id name — role, target X%`.
- When zero actionable_buy rows exist, the section shows
  `⏸️ 本周无可执行标的`.
- target_weight and role are plumbed into DecisionRow.
- Existing tests pass.

## Tests to add

`tests/decision/test_three_section_markdown.py`:

- `test_todays_only_action_lists_actionable_buys`
- `test_todays_only_action_empty_when_no_actionable`
- `test_todays_only_action_renders_role_and_weight`
- `test_decision_row_has_target_weight_and_role_fields`
