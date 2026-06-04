Verdict: PASS

Subagent: sonnet
Plan checklist items: 8 tasks (Tasks 1–8), ~50 steps across all tasks
Verified present in diff: 8/8 tasks (all production files, all test files, CONTEXT.md)

---

## Load-bearing invariants (verified against diff lines)

- **states.py symmetric guard** — CONFIRMED. The guard condition (diff lines `+    if (\n+        inp.asset_class in _EQUITY_ASSET_CLASSES\n+        and inp.theme in COMMODITY_CYCLICAL_THEMES\n+        and inp.valuation_percentile_fundamental is None\n+    ):`) is symmetric: it returns `evidence_insufficient` for ALL directions when the three conditions hold. It is NOT narrowed to only the expensive end. Tests confirm both low-NAV (would be `cheap`) and high-NAV (would be `very_expensive`) are withheld.

- **akshare_index_valuation.py** — CONFIRMED. `_CSINDEX_PE_TTM_COL = "市盈率1"` is a dedicated constant. `_csindex_pe_ttm_map` checks `if _CSINDEX_PE_TTM_COL not in df.columns` and does NOT call `_series_map(..., _PE_COLS)`. `pb=None` is hardcoded in every `IndexValuationPoint` returned by `fetch_cn_sector_index_valuation_history`. The literal `基金概况` does NOT appear in the file.

- **inputs_loader.py** — CONFIRMED. Latest-null guard is preserved: `if pe is not None and _pe_series_is_mature(pe_series)` (line 188) — the `pe is not None` check comes first so a null latest PE short-circuits before the maturity gate.

- **risk.py** — CONFIRMED. `out.append(("valuation_state", "valuation withheld — no fundamental anchor", 1))` is appended when `view.valuation_state == "evidence_insufficient"`. No `evidence_gap` is added anywhere in the diff. H3 publishability is intact.

- **ingest_cmd.py second leg** — CONFIRMED. A SECOND `ingest_index_valuation_history` call appears at line 587–590 with `tuple(sorted(_SECTOR_INDEX_KEYS))` and `fetch=fetch_cn_sector_index_valuation_history`, wrapped in `try/except Exception` (best-effort/non-fatal), mirrors the broad-index leg above it.

---

## Drift findings

- **Task 3 Step 1 / Task 3 Step 7 — fixture row count 130 → 200 (plan internally inconsistent)**
  Evidence: `test_inputs_loader.py` diff line `+    pairs = [(10.0 + i * 0.05, None) for i in range(200)]` and `+    # 200 daily non-null PE points (>120, span >180d)`; `test_populate_inputs_reads_cached_index_valuation_percentile` bumped to `range(200)` with `pe_ttm == pytest.approx(29.9)` / `pb == pytest.approx(2.99)` / `earnings_yield == pytest.approx(1.0 / 29.9)`.
  Root cause: The plan specified 130 rows, but 130 consecutive daily points span only 129 days, which is < `MIN_PE_DAYS=180` and would FAIL the very min-history gate being tested. 200 rows → 199-day span satisfies both `MIN_PE_POINTS=120` and `MIN_PE_DAYS=180`.
  Production logic: NOT weakened. The gate constants (`MIN_PE_POINTS=120`, `MIN_PE_DAYS=180`) are unchanged. Only the test fixture count was corrected upward.
  Action: plan amended inline — `001-plan.md` Task 3 Step 1 comment updated 130→200 (with rationale), Task 3 Step 7 bump updated 130→200 and dependent latest-value asserts updated to 29.9/2.99/1/29.9. Commit follows.

---

## Summary

All 8 tasks are fully implemented and match plan intent. The single divergence (fixture row count 130→200) is a correction of an internally inconsistent plan literal, not a weakening of any production invariant. Plan amended inline; no triage items.
