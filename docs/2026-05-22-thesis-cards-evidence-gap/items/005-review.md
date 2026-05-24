Verdict: PASS-WITH-NITS

Source: /ship steps 8 (pre-landing parallel review) + 9 (adversarial review)
PR: https://github.com/snowshine0216/investment-research-copilot/pull/59
Subagents: pr-review-toolkit:code-reviewer (step 8a), pr-review-toolkit:silent-failure-hunter (step 8b), general-purpose adversarial (step 9, model=sonnet)

## Summary

- **P0 (blockers):** 0
- **Latent bugs:** 2 confirmed (worth fix-loop pickup; see classification below)
- **Nits:** 4

## Classification

### Latent (real but unlikely-to-fire-soon; flag for fix loop)

1. **`_FUND_LEVEL_KINDS` (`snapshot.py`) vs `_FUND_LEVEL_KINDS_CMD` (`opportunity_cmd.py`) drift unguarded** — adversarial review finding. Two frozensets with identical declared contents `{"gold","bond","broad_index","sector_theme"}` in two modules. No shared constant; no test enforces equality. If they ever diverge (e.g. someone adds `"cn_etf"` to one without the other), `_classify_fund_level_scores` undercounts or overcounts budget vs actual `build_snapshot` dispatch. Budget gate could silently bypass or trip. **Fix:** dedupe via a single import from `snapshot.py` into `opportunity_cmd.py`, OR add a one-line equality assertion test. Cost: ~3 lines + 1 test.
2. **`_resolve_fund_level_snapshot` uses `assert isinstance(snap, FundLevelSnapshot)` for type narrowing** — silent-failure hunter finding (`opportunity_cmd.py` ~line 328). Under `python -O` (which production deployments often enable), the assert becomes a no-op. A future dispatch bug (e.g. the frozenset drift above) where `build_snapshot` returns the wrong type for a fund-level kind would silently flow downstream as the wrong shape. **Fix:** replace `assert` with `if not isinstance(...): raise RuntimeError(...)`, or stamp a `dispatch_mismatch` failure reason and continue.

### Nits (cosmetic / defense-in-depth; address opportunistically)

3. **`_ann_from_dict` does not validate `topic` against the `Literal["dividend","report","personnel"]` set** — code reviewer finding (`snapshot_cache.py` ~line 286-293). A corrupted JSON cache could re-hydrate `FundAnnouncement` with arbitrary `topic` string that then flows into `source=f"fund_announcement_{topic}_em"`. **Fix:** add topic-set check to `FundAnnouncement.__post_init__`.
4. **`_ISO_DATE_RE` accepts impossible calendar dates** (`types.py` ~line 9) — code reviewer finding. Regex matches `2024-13-99`. Both `FundNavReport.__post_init__` and `FundAnnouncement.__post_init__` rely on it. **Fix:** use `date.fromisoformat` in `__post_init__` for stricter validation (matches `snapshot_cache.infer_quarter` style).
5. **`fetch_fund_nav_report` broad `except Exception`** swallows `ValueError` from `FundNavReport(__post_init__)` violations — silent-failure-hunter finding (`akshare_fundamentals.py` ~line 531). The caller stamps `fund_nav_unavailable`, so the gap is recorded, but the discrimination "adapter failed" vs "data shape violated invariant" is lost. **Fix:** narrow the second `try/except` to `except ValueError:`.
6. **`snapshot_cache` dict mixes namespaces** — code reviewer finding (`opportunity_cmd.py` ~line 830). active-fund key = `fund_<id>`, fund-level key = bare `<id>`, legacy key = CN display name. No collision under current universe but adding a prefix would future-proof. **Fix:** prefix fund-level keys with `fl:` or similar.

### Notes (observations; no action required)

- **F5 invariant verified:** `"基金概况"` absent from `src/`. Locked by `tests/fundamentals/test_static_profile_invariant.py`.
- **F4 invariant verified:** QDII dispatch at `snapshot.py:265-266` is unconditional (precedes fund-level branch; ignores `provider_symbol`).
- **ADR 0001 §2 verified:** announcement `url=""` + `summary=f"[{report_id}] {title}"` gives report-id-unique fallback preimage. Adversarial reviewer constructed concrete two-announcement collision scenario and confirmed no collision.
- **Adapter "never raise" verified:** `fetch_fund_announcements` per-endpoint `try/except: continue` confirmed by `test_fetch_fund_announcements_endpoint_exception_degrades_to_empty`.
- **`_build_fund_level_snapshot` independence verified:** NAV and announcements fetched independently; when NAV is None, announcement branch still executes and stamps the appropriate gap.
- **`write_nav_cache` failure handling verified:** caught in `_resolve_fund_level_snapshot`, stderr-logged, failure reason appended to `fund_level_failure_reasons` via `replace()`; in-memory snapshot still propagates.
- **Adversarial `inf` NAV path:** `nav <= 0` filter passes `float('inf')`. `FundNavReport.__post_init__`'s `latest_nav > 0` passes `inf`. Cache write fails on `json.dumps` (which rejects `inf` without `allow_nan=True`); failure reason stamped. In-memory propagation works. Production impact: every run re-fetches that fund (budget waste). Severity P1; AkShare returning `inf` is unlikely in practice but defenseless if it ever does. Worth filtering for `math.isfinite(nav)` in the adapter — folded into latent finding #5's broader narrow-except recommendation.

## Recommendation

PASS-WITH-NITS. Latent items #1 and #2 should be addressed in the fix loop (they are real production risks, low-cost to fix). Items #3-#6 can be opportunistic.

Per autodev review→fix exit contract: this verdict satisfies "PASS-WITH-NITS" for the review leg. The fix loop will run if verify or pr-review surface anything blocker-grade; otherwise items #1 and #2 are still worth a targeted fix commit.
