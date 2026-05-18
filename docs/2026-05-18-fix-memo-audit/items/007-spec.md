# Item 007 — Tag `watch_only` rows with the actual reason

## What

In `outputs/2026-05-18/decision_report.md`, 86 of 103 rows say `watch_only` with `Keep on watchlist and rerun after new data.` and `venue=unknown`. By design — but the reader can't tell why each row landed there.

Three distinct sub-cases collapse into one bucket today:

| Sub-case | What it means |
|---|---|
| `not_selected_by_allocation` | scoring action is `buy_candidate` (≥ 60), but the allocation didn't pick this instrument — usually because the correlation filter dropped it or a peer beat it on intra-class share |
| `score_watch` | scoring action is literally `watch` (score in 40-59 range) |
| `venue_unknown` | scoring is fine, but `venue_status == "unknown"` — no trade row exists yet, so the venue isn't known |

These are independent and the reader needs to know which.

## Files to touch

- `src/irc/decision/models.py` — add `watch_reason: WatchReason | None` to `DecisionRow`.
- `src/irc/decision/gates.py` — populate `watch_reason` inside `_build_decision_row` (or upstream); only set when `decision_status == "watch_only"`.
- `src/irc/decision/report.py` — render the watch_reason as a new "Why watch" column in the markdown.
- `tests/decision/test_gates.py` — add a parametrized test for the three sub-cases.
- `tests/decision/test_report.py` (if it exists) — add the snapshot for the new column.

## Acceptance criteria

- `WatchReason = Literal["not_selected_by_allocation", "score_watch", "venue_unknown", None]`.
- Decision rows with `decision_status="watch_only"` carry a `watch_reason` that follows this rule:
  - If `score_action == "watch"` → `score_watch`.
  - Else if `score_action in {"buy_candidate", "strong_buy_candidate"}` AND `not allocation_selected` → `not_selected_by_allocation`.
  - Else if `venue_status == "unknown"` → `venue_unknown`.
  - Else `None` (defensive).
- The JSON shape gains the field; existing consumers that don't read it are unaffected.
- Markdown table gains a column `Why watch`. For non-`watch_only` rows the column is empty.
- A unit test covers each of the three branches.
- The full suite is green.

## Coordination

- Item 008 changes `venue_status_for_trade` so `unknown` becomes rare. The `venue_unknown` branch here may end up unused after 008 ships — that's fine, leave it defined.
- Item 011 restructures the markdown layout; the new column needs to land first so 011 can use it.

## Out of scope

- Sub-classifying `not_selected_by_allocation` further (correlation drop vs. intra-class loser). Defer.
- Changing the gate logic itself. Only attach explanatory metadata.
