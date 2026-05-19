# 011 — Plan

Config-only change. No subagent dispatch needed.

## Steps

1. Edit `config/scoring.yaml`:
   - `valuation_cost: 0.10` → `0.30`
   - `macro_fit: 0.25` → `0.15`
   - `thesis_news: 0.20` → `0.10`
   - `risk: 0.25` → `0.25` (unchanged)
   - `quality: 0.20` → `0.20` (unchanged)
   - `weights_version: "2026-05-07-v1"` → `"2026-05-19-v2"`
   - Verify sum = 1.00 exactly: 0.30 + 0.25 + 0.20 + 0.15 + 0.10 = 1.00 ✓

2. Add a regression test `tests/scoring/test_weights_sum.py` that loads
   the production config and asserts weights sum to 1.0.

3. Run focused tests:
   ```
   uv run pytest tests/scoring/ -x -q
   ```

4. Update PROGRESS.md.
