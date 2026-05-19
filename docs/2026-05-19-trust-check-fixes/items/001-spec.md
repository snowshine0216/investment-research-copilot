# 001 — Add beginner glossary to decision_report.md

## Why

The trust-check doc (priority #7, B3) found that:

> A layperson cannot tell `scored watch` from `not_selected_by_allocation`
> or `venue_unknown` in any meaningful way. None of these terms are
> explained in-document.

Same goes for `venue_status` (`direct` reads as "ready to execute"
when it actually means "your account can route it, *given* QDII
activation"), `data_completeness` ("1.00" reads as "100% confident"),
`buy_candidate`, `core_dca`, `pause_wait`.

The fix is the lowest-effort, highest-clarity intervention: a short
glossary appended to `decision_report.md` so any reader can decode
the columns above without external knowledge.

## What changes

`src/irc/decision/report.py: render_decision_markdown` — append a new
section `## 术语速查 (Glossary)` after the existing three sections.

Content (verbatim):

```markdown
## 术语速查 (Glossary)

- **buy_candidate / 候选买入**: 评分模型给出的买入候选，*尚未*等同于
  "立即执行"。执行前需人工核对 venue、溢价、合规审核。
- **actionable_buy**: 候选买入 ∩ 资产配置选中 ∩ 通过所有阻断闸口。
  仍需人工核对。
- **core_dca / 正常定投**: 当前评估状态适合按月常规定投。
- **pause_wait / 暂停加仓**: 当前估值/事件层面建议本周不加仓，等待下次重评。
- **venue_status=direct**: 你的主账户支持直接下单（不代表已开通 QDII
  权限；首次交易前请在券商 App 内确认）。
- **venue_status=blocked_no_proxy**: 当前账户无法直接交易，且未配置代理
  (proxy)。
- **venue_status=unknown**: 系统未确认 venue 状态，请勿据此判断可执行性。
- **data_completeness**: 必需字段的*填充率*（0–1），**不等于**信心或胜率。
  1.00 仅表示字段齐全，*不代表*该笔交易高确定性。
- **watch_reason=scored watch**: 评分本身给出 watch 行动。
- **watch_reason=not_selected_by_allocation**: 评分尚可，但资产配置未选中。
- **watch_reason=venue_unknown**: venue 数据缺失。
```

## Acceptance criteria

- `render_decision_markdown(report)` includes a `## 术语速查 (Glossary)`
  section after the Watch section.
- The glossary contains entries for: `buy_candidate`, `actionable_buy`,
  `core_dca`, `pause_wait`, `venue_status` (direct / blocked_no_proxy /
  unknown), `data_completeness`, `watch_reason`.
- JSON shape unchanged (additive markdown only).
- Existing tests still pass.

## Tests to add

`tests/decision/test_three_section_markdown.py`:

- `test_markdown_has_glossary_section` — asserts `## 术语速查` is in
  the rendered output.
- `test_glossary_contains_required_terms` — asserts each of the 7 terms
  listed above appears in the glossary section.
- `test_glossary_data_completeness_warning` — asserts the
  `data_completeness` entry explicitly contains the
  `不等于信心或胜率` warning (the trust-check doc's specific concern A3).
