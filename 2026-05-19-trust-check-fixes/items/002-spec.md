# 002 — Reconcile English score_action with Chinese label

## Why

Trust-check B2 found that the same instrument reads bullish in
`decision_report.md` (`score_action=buy_candidate`) and bearish in
`discipline_report.md` (`pause_dca / 暂停加仓`). A non-finance reader
who only sees the decision report builds the wrong mental model.

Trust-check A2/A4 found that all decision-report rows render *only*
the numeric instrument id (017641, 019172, 005561 …) — the reader has
no way to know what fund those ids point to.

## What changes

Two complementary fixes:

1. **Instrument name column** (already mostly implemented as
   uncommitted WIP — formalized here): a `Name` column appears in
   every decision-report table, populated from `name_cn` of the
   universe yaml configs, with `discovered_watchlist.csv` as fallback.

2. **Bilingual score_action label**: the `Score Action` column
   renders English-machine-label + Chinese-gloss pairs (e.g.
   `buy_candidate / 候选买入`, `watch / 观察`, `avoid / 回避`). This
   pairs the underlying English label with a Chinese gloss in-place,
   so a reader sees both sides immediately and is forced to recognize
   that `buy_candidate` is *only a candidate* — not "go buy this."

## Acceptance criteria

- Every decision-report table has a `Name` column (already verified by
  the existing WIP test).
- `Score Action` cells in all three sections (Actionable buys, Blocked,
  Watch) render in `english_label / 中文标签` form.
- Unknown score_action values fall back to the raw label string (no
  KeyError, no blank cell).
- Existing tests still pass.

## Tests added

`tests/decision/test_three_section_markdown.py`:

- `test_score_action_cell_is_bilingual_in_actionable_section`
- `test_score_action_cell_is_bilingual_in_watch_section`
- `test_score_action_cell_is_bilingual_in_blocked_section`
- `test_unknown_score_action_falls_back_to_raw_label`

Plus the previously-uncommitted name-column tests that this branch
formalizes.
