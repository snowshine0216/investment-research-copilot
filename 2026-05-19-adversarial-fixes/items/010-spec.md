# 010 — Role-bucket failure banner in memo

## Why

`discovery_diagnostics.csv` shows 10 of ~16 role buckets failed with
"below fail_below" (zero candidates passed): `core_us_equity`,
`defensive_us_bond`, `hedge_low_correlation`,
`satellite_cn_{consumer,defense,new_energy,real_estate,semiconductor,
soe,tech}`.

The memo presents the final picks as if the universe were exhaustive.
The adversarial review (§E) demands: surface "N of M role buckets
returned 0 candidates" as a headline-tier diagnostic.

## What changes

1. In `src/irc/memo/synthesizer.py`, read
   `discovery_diagnostics.csv` (or the in-memory equivalent) and compute:

```python
failed_roles = [...]  # rows where stage="role_bucket" and status="failed"
total_roles  = ...
```

2. If `len(failed_roles) > 0`, prepend a banner to Section 1 (TL;DR):

       「**发现层覆盖警告**：{N}/{M} 角色桶本期未召回任何候选 —
       {role1, role2, ...}。组合层面缺角，请把当周配置视为"在残缺集合
       中的最优选"，而非"全集合最优"。」

3. Also surface in Section 4 (allocation): one line per failed role with
   the role name and the dominant rejection reason from
   `discovery_rejections.csv` (e.g., "AUM-below-floor 145").

## Acceptance criteria

- Re-running on 2026-05-19 inputs produces a memo whose Section 1
  contains the "发现层覆盖警告" banner naming the 10 failed roles.
- For inputs where no roles failed, the banner is omitted (no
  false-positive).
- Section 4 contains a per-failed-role line with rejection counts.

## Tests to add

- `tests/memo/test_role_bucket_banner.py`:
  - 3 of 16 roles failed → banner mentions "3/16" and lists them
  - 0 failed → no banner
