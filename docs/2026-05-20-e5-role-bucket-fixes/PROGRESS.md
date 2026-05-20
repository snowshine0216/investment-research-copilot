# Progress — E5 role-bucket fixes

Feature branch: `feat/e5-role-bucket-fixes` → merged to `main` as `032c71c` (PR #52).

| # | Item | Tests | Impl | Lint | Commit | Note |
|---|---|---|---|---|---|---|
| 001 | Raise DD buffer 1.6 → 1.8 | ✅ | ✅ | ✅ | ✅ | `4706640` — config-only |
| 002 | US-bond QDII feeders | ✅ | ✅ | ✅ | ✅ | `bcd32df` — template + 1 new test |
| 003 | SOE + real-estate proxies | ✅ | ✅ | ✅ | ✅ | `22f4ba3` — template + 1 new test |
| 004 | Broaden `_is_core_us` | ✅ | ✅ | ✅ | ✅ | `87b8158` — 5 new tests (3 +, 2 −) |
| 005 | Broaden `_is_hedge_low_corr` | ✅ | ✅ | ✅ | ✅ | `8bf745f` — 3 new tests |
| 006 | Verify + PR + tracker | ✅ | ✅ | ✅ | ✅ | + `69077d3` regression-guards |

## Final stage

| Step | Status |
|---|---|
| All commits on branch | ✅ 7 commits (1 design + 5 phase + 1 review-fix) |
| Focused suite green | ✅ 38 role_bucket + 3 universe-completeness |
| Full suite | ✅ 1457 passed / 17 skipped / 2 pre-existing failures (baseline) |
| Branch pushed | ✅ |
| PR opened | ✅ #52 |
| Review subagent | ✅ PASS-WITH-NITS (N1 + N2 addressed in 69077d3) |
| Triage / fixes | ✅ both nits fixed before push to PR |
| Merged | ✅ #52 squashed to main as `032c71c` |
| Tracker updated | ✅ AUDIT_FIXES_TRACKER.md E5 row → Done |

Legend: ⏳ pending • 🔄 in progress • ✅ done • ⚠️ blocked

## Cross-branch validation

Compared `main` (pre-merge) vs `feat/e5-role-bucket-fixes`:

- `main` (pre-PR): 2 pre-existing failures (`test_no_all_evidence_insufficient_valuation`, `test_eval_single_stage_data` — documented in AUDIT_FIXES_TRACKER as the same baseline that prior E1-E4 PRs reported).
- Feature branch: same 2 failures + 12 new passing tests (5 broad-US bucket + 3 HK-dividend bucket + 2 regression-guards + 2 universe-completeness).
- **No regressions introduced.**

## Review findings + dispositions

| Finding | Severity | Action |
|---|---|---|
| N1 — No routing test for bond QDII feeders (us_etf + cn_off_exchange + bond) → defensive_us_bond | Nit (latent regression risk) | **Added** `test_bucket_us_bond_qdii_feeder_routes_to_defensive_us_bond` in 69077d3 |
| N2 — No negative test pinning 561380 (cn_etf + theme=soe + 红利) away from hedge_low_correlation | Nit (latent regression risk) | **Added** `test_bucket_cn_soe_dividend_etf_does_not_leak_into_hedge_low_correlation` in 69077d3 |

## After-merge follow-ups (user-side, not in PR)

1. `irc init --force` (or copy three+three new instrument rows manually) to bring the template additions into local `config/universe/qdii_us.yaml` and `cn_funds.yaml`.
2. Run `irc run --resume` (or fresh) to regenerate `discovery_diagnostics.csv` and confirm bucket counts.
3. If any previously-filtered junk-quality cn_equity_fund pick shows up in `memo.md`, file a follow-up to split the DD buffer into broad-vs-themed (was Option B in the report; we took Option A).
