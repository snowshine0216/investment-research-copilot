# 008 — Plan

## Steps

1. `src/irc/commands/score_cmd.py`: add `tracked_index` to the
   enrichment columns drop_duplicates and metadata setdefault so the
   scoring.json carries it forward to allocation.
2. `src/irc/allocation/correlation_filter.py`: add a pure function
   `drop_duplicate_index_trackers(rows: list[dict]) -> tuple[list[dict],
   list[dict]]` that groups by (asset_class, tracked_index) and keeps
   the highest target_weight per group. Returns kept + dropped lists,
   where each dropped row carries a `reason: duplicate_tracked_index`.
3. `src/irc/allocation/pipeline.py`: invoke
   `drop_duplicate_index_trackers` BEFORE the correlation-matrix
   filter so the index-tracker dupes are removed first. Renormalize the
   kept rows' target_weight within their class to preserve the class
   total (reuse `_keep_and_preserve_class_totals`).
4. Add `tests/allocation/test_dedupe_tracked_index.py`:
   - two cn_equity_fund rows with `tracked_index=hs300` → keep one
   - rows with empty tracked_index pass through
   - rows in different asset_class with same tracked_index → keep both
5. Verify full allocation tests stay green.
