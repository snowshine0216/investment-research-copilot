# E5 — Role-bucket gap fixes

**Source:** `outputs/2026-05-20/E5_role_bucket_report.md`
**Goal:** Implement the phased fix to rescue the 10 failing role buckets, then merge a single feature PR.
**Feature branch:** `feat/e5-role-bucket-fixes` → main
**Run date:** 2026-05-20

## Scope rationale

The report defines 4 phases. The user asked to "fix and merge PR once it's safe to merge" — singular PR — so all in-scope items land on one branch with separate commits.

Decisions taken autonomously from the report's stated recommendations:

- **Phase 1 — blanket DD-buffer raise** (`cn_equity_fund: 1.6 → 1.8`). The report's primary single-knob recommendation. The "surgical split" alternative would require new schema fields and is heavier; blanket raise is the lighter first step. Cross-cutting risk note in the report says rerun and audit memo for junk-quality promotions — we will verify this in QA.
- **Phase 2 — universe additions.** Add the specific instruments named in the report. Inception-year filter (`inception_years_min: 3`) will silently drop any instrument launched after 2023-05-20; that's acceptable — the role buckets that need rescuing will simply not be rescued if the listed instruments are too new.
- **Phase 3 — predicate broadening** for `_is_core_us` (Russell 1000, CRSP US Total Market) and `_is_hedge_low_corr` (HK High Dividend, 恒生央企红利 etc). Small code change with TDD per the report.
- **Phase 4 — acknowledge-gap documentation** — folded into the post-merge tracker update.

## IN-scope items

| ID | Phase | Item | Files |
|---|---|---|---|
| 001 | 1 | Raise `cn_equity_fund` DD buffer 1.6 → 1.8 | `config/discovery.yaml` + any test that pins the value |
| 002 | 2 | Add US-bond QDII feeders | `config/universe/qdii_us.yaml` |
| 003 | 2 | Add SOE / real-estate / semiconductor proxies | `config/universe/cn_funds.yaml` |
| 004 | 3 | Broaden `_is_core_us` predicate | `src/irc/discovery/role_bucket.py` + `tests/discovery/test_role_bucket.py` |
| 005 | 3 | Broaden `_is_hedge_low_corr` predicate | `src/irc/discovery/role_bucket.py` + `tests/discovery/test_role_bucket.py` |
| 006 | 4 | Verify pipeline + cross-cutting validation | full test suite, build, memo re-render dry-check |

## OUT-of-scope

| ID | Item | Reason |
|---|---|---|
| — | "Surgical split" of `cn_equity_fund` into broad-vs-themed | The blanket raise is the report's first recommendation. Split is only justified if QA shows junk-quality picks promoted to the memo. If that happens, follow-up. |
| — | `lower fail_below: 5 → 3` (alt fix for SOE bucket) | Listed as Option B in the report; Option A (universe expansion) is preferred and gets us all the way. Lowering `fail_below` weakens the gate globally. |
| — | Adding `_is_satellite_cn_growth` adjustments / new `growth` bucket | Not in the E5 report. |
| — | Pipeline rerun + memo regen on user environment | Pipeline-level rerun is a manual user action — we run focused tests + cross-branch validation only. |

## Acceptance criteria

- All new and existing tests pass (`pytest`).
- `ruff check` clean on touched files.
- Config + yaml changes parse cleanly (DiscoveryConfig validation runs in tests).
- Branch merges to main as a single squash PR.
- `outputs/2026-05-20/AUDIT_FIXES_TRACKER.md` updated to reflect E5 status.
