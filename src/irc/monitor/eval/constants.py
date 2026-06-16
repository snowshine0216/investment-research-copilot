"""M3 predictive-validity constants. Tunable; calibration is M4.

FORWARD_H carries TWO units:
  - forward-return / momentum / maturity window  → 20 NAV observations
  - block-bootstrap block size                   → ~20 run dates (an "H run-date block")
The retro replay grid floor is NOT here: it is the fund's `minimum_observations`
(config/monitor.yaml, currently 251), sourced at the call edge so the floor never
drifts from the trend leg's real 250-obs drawdown lookback (factors.py:29 / trend.py).
"""
from __future__ import annotations

FORWARD_H = 20            # NAV-obs window AND (separately) run-date block size
N_MIN_BLOCKS = 8          # min shared-timeline run-date blocks for a reportable point estimate
MIN_CROSS = 4             # min matured funds for a defined cross-sectional Rank-IC day
MIN_DEFINED_DAYS = 8      # min defined IC days for a statistically reportable IC
MIN_PERM_DATES = 8        # min permutable run_date groups for the random null
BOOTSTRAP_B = 2000        # bootstrap / permutation resamples
REVIEW_TRIGGER_K = 4      # consecutive ISO-week underperformance reports → review flag
NAV_APPEND_DAYS = 60      # producer appends only nav_date >= run_date - NAV_APPEND_DAYS
STALE_EVAL_DAYS = 10      # report stale if artifact_date < today - STALE_EVAL_DAYS
