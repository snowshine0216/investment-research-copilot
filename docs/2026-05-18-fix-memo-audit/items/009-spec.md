# Item 009 — Deterministic Section 7 "执行要点" built from the trade plan

## What

`outputs/2026-05-18/memo.md:55-58` Section 7 is literally:

```
## 7. 执行要点

<!-- 由AI合成器填充 -->
```

`src/irc/memo/template.py:40` writes that HTML comment as a placeholder, and the synthesizer prompt never explicitly tells the LLM to replace it. The LLM kept the placeholder verbatim. The memo audit flagged "执行要点是合规审核的重要组成部分 … 不具备完整的可执行性 … 阻断发布".

We should not depend on the LLM for execution details. Build Section 7 deterministically from the trade plan.

## Files to touch

- `src/irc/memo/template.py` — `MemoInputs` gains `execution_lines: tuple[str, ...] = ()`. Section 7 renders from this; only falls back to the LLM placeholder when `execution_lines` is empty.
- `src/irc/commands/memo_cmd.py` (or wherever `MemoInputs` is built) — read the trade plan and produce one bullet per row with `instrument_id`, target weight, `buy_method`, `granularity`, trigger list, and `venue_note`.
- `src/irc/memo/pipeline.py` — pass the execution_lines all the way through `render_skeleton`.
- `tests/memo/test_template.py` — assert Section 7 contains a bullet for each trade row when `execution_lines` is non-empty.
- `tests/memo/test_execution_lines.py` (NEW) — build sample MemoInputs from a synthetic trade plan; assert the rendering shape.

## Acceptance criteria

- Section 7 renders as one bullet per trade row in this shape:
  ```
  - **{instrument_id} {name_cn}** | 目标权重 ≤ {target_weight*100:.1f}% | 建仓方式 {buy_method} ({granularity}) | 触发 {trigger_names | "无"} | 渠道 {venue_note}
  ```
- When `execution_lines` is empty (e.g. a dry-run with no allocation), Section 7 falls back to today's placeholder. Don't break that path.
- When the trade plan exists, the LLM is *not asked* to fill Section 7; the synthesizer prompt is updated to say "Section 7 is provided verbatim — do NOT modify".
- A new test builds a sample MemoInputs with 3 execution_lines and asserts each appears in `render_skeleton`'s output exactly once.
- A snapshot/round-trip test confirms the line shape matches the spec.
- The full suite is green.

## Coordination

- Item 001 fixes the trigger key mismatch. Once 001 lands, the trigger names in 009's output for CN rows will actually appear instead of "(无)".

## Out of scope

- Adding stop-loss / authorization fields. Those require policy decisions and don't live in the data layer.
- Reformatting the rest of the memo. Section 7 only.
