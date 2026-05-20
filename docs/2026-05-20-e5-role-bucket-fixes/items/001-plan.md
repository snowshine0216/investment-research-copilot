# Item 001 — Raise cn_equity_fund DD buffer 1.6 → 1.8

## Files

- `config/discovery.yaml` — one-line change

## Change

```diff
   drawdown_3y_buffer_by_asset_class:
     gold: 1.35
-    cn_equity_fund: 1.6
+    cn_equity_fund: 1.8
     cn_etf: 1.4
```

## Why

Per E5 report § "Headline numbers": the single highest-leverage knob. Rescues ~5 buckets:
`satellite_cn_consumer`, `satellite_cn_defense`, `satellite_cn_new_energy`,
`satellite_cn_semiconductor`, `satellite_cn_tech`.

## Why blanket vs split

Split into broad-vs-themed needs a schema field + quality_filter refactor — heavier.
Blanket is the report's primary recommendation; if it promotes junk-quality picks
to the memo, follow-up PR can refine. Caught either in QA subagent (this run) or
on the user's first `irc run` after merge.

## Tests

`tests/discovery/test_quality_filter.py` uses its own fixture — no pinning. Verified
by `grep -rn "cn_equity_fund.*1\.6" tests/` — zero hits outside the local fixture
that doesn't reflect prod config. No test updates needed.

## Verification

- `pytest tests/discovery/ -q` — must stay green
- `pytest tests/schemas/test_discovery.py -q` — config parses with new value

## Commit message

```
chore(discovery): raise cn_equity_fund DD buffer 1.6 → 1.8 (E5 phase 1)

Rescues 5 of 10 failing role buckets (consumer/defense/new_energy/semi/tech) —
themed active CN equity funds tripped the 32% DD threshold under the old buffer.

Per outputs/2026-05-20/E5_role_bucket_report.md § Phase 1.
```
