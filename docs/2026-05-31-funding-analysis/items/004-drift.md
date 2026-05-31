Verdict: PASS

Subagent: sonnet
Plan checklist items: 9
Verified present in diff: 9
Drift findings: none

---

## Load-bearing commitment verification

### `compute_ratios` + `KeyRatios` in new module `src/irc/fundamentals/ratios.py`; pure (no I/O/LLM imports)
CONFIRMED. `ratios.py` is created at 72 lines (diff lines +1..+72). The module imports only `math`, `dataclasses`, and `irc.fundamentals.types`. No `akshare`, `duckdb`, `requests`, `open(`, or `irc.llm` present. `compute_ratios` is a pure function returning a frozen `KeyRatios` dataclass. `debt_equity`/`fcf_yield` are always `None` (diff `ratios.py:+49,+50`). `_finite` screens `None`/`NaN` → `None`.

### `roe` extracted via separate `_profitability_metric` (`盈利能力` section); `_common_metric` (`常用指标`) UNCHANGED
CONFIRMED. `_profitability_metric` is a NEW function added after `_common_metric` (diff `akshare_filing.py:+115..+128`). The diff shows zero minus-lines touching the `_common_metric` body — it is untouched. `_profitability_metric` filters `df.get("选项") == "盈利能力"`, whereas `_common_metric` filters `"常用指标"`. No new network fetch: the same `_ak_call` to `stock_financial_abstract` is reused; `roe = _profitability_metric(df, _KEY_ROE, latest)` is called after the existing `gross_margin = ...` line (diff `akshare_filing.py:+159`).

### `debt_equity`/`fcf_yield` always `None`; `None` ratios OMITTED from fragment (never string "None")
CONFIRMED. `compute_ratios` hard-codes `debt_equity=None, fcf_yield=None` (diff `ratios.py:+49,+50`). `ratios_reason_fragment` only appends a part when the field `is not None` (diff `ratios.py:+58,+60,+62,+64`). The comment at `ratios.py:+61` reads "debt_equity / fcf_yield are None today → never appended (omitted, not 'None')".

### `_evidence_for_constituent` returns 3-tuple; sole production caller and ALL 5 test call-sites updated; no 2-tuple left dangling
CONFIRMED.
- Return type annotation changed to `tuple[tuple[ThesisEvidence, ...], list[str], FilingDigest | None]` (diff `snapshot.py:+314`).
- `cn_digest` captured in CN branch (diff `snapshot.py:+346`); returned as third element (diff `snapshot.py:+429`).
- Production caller `_build_active_fund_snapshot` line 554: `evidence, failures, _cn_digest = _evidence_for_constituent(...)` (diff `snapshot.py:+554`).
- `_one_line_view` call updated to pass `_cn_digest` (diff `snapshot.py:+563`).
- Test call-sites: `test_snapshot.py:466` fake updated to 3-tuple with `None`; `test_thesis_evidence.py:657,688` both updated to `_digest` capture; `test_opportunity_cmd.py:760,800` both updated to `_digest` capture. Verified: no remaining 2-tuple unpack exists (grep confirmed all 6 unpack sites bind 3 names).

### `one_line_view` `[:60]` cap UNCHANGED; byte-stability of existing (empty-fragment) rows locked by test
CONFIRMED. The `return " · ".join(fragments)[:60]` line is NOT in the diff's minus-lines; it appears unchanged at `snapshot.py:464`. The plan's `[:60]` mention in the docstring comment at `+441` is a comment-only addition. `test_one_line_view_byte_identical_when_digest_none` (diff `test_snapshot.py:+548..+562`) locks byte-stability when `cn_digest=None`. `test_one_line_view_two_run_byte_stable_for_ratio_bearing_row` (diff `test_snapshot.py:+577..+586`) additionally locks byte-stability for ratio-bearing rows across two calls and asserts no `[ref:...]` marker.

### NO change to `valuation_state`/`thesis_state`/`policy_b`/`core_dca`/`opportunity` partition/citation set
CONFIRMED. The diff touches zero files under `src/irc/opportunity/`. No `[ref:HEXHEX]` pattern appears in any added line (`git diff | grep "^\+.*\[ref:[0-9a-f]{16}\]"` returns empty). CONTEXT.md was not modified in this branch (already carried the required entries from commit 4b9f050, confirmed by zero diff on CONTEXT.md).

### No ADR 0010 created
CONFIRMED. `docs/adr/` contains only 0001–0009; no 0010 file.

---

## Per-task verification

**Task 1 (roe field on FilingDigest):** `types.py` adds `roe: float | None = None` as the LAST field after `source_url` (diff `types.py:+172..+177`). Test `test_filing_digest_roe_defaults_none_and_is_settable` added to `test_types.py` (diff `test_types.py:+104..+123`). OK.

**Task 2 (`_profitability_metric` + `_KEY_ROE` + wire into digest):** `_KEY_ROE = "净资产收益率"` added (diff `akshare_filing.py:+25`). `_profitability_metric` function added (diff `akshare_filing.py:+115..+128`). `roe = _profitability_metric(df, _KEY_ROE, latest)` wired in, `roe=roe` passed to `FilingDigest(...)` (diff `akshare_filing.py:+159,+168`). Three ROE tests added to `test_akshare_fundamentals.py` (diff `test_akshare_fundamentals.py:+486..+525`). OK.

**Task 3 (`KeyRatios` + `compute_ratios` in `ratios.py`):** New file `src/irc/fundamentals/ratios.py` created (72 lines); `KeyRatios` frozen dataclass with 4 fields all defaulting `None`; `_finite` helper; `compute_ratios` pure function. New test file `tests/fundamentals/test_ratios.py` created (155 lines) with AC1/AC2/AC3/AC4/AC5 tests. OK.

**Task 4 (`ratios_reason_fragment` helper):** `ratios_reason_fragment` appended to `ratios.py` (diff `ratios.py:+53..+72`). Fragment tests (AC7/G4) appended to `test_ratios.py` (diff `test_ratios.py:+79..+110`). Fragment format `（ROE 18%·毛利69%，口径未核实）` locked by `test_fragment_shows_roe_and_gross_margin_compact`. OK.

**Task 5 (`_evidence_for_constituent` → 3-tuple refactor):** Return type, `cn_digest` init, capture in CN branch, and final `return` all updated (diff `snapshot.py:+314,+327,+346,+429`). Test fake updated (`test_snapshot.py:+466`). Two new tests `test_evidence_for_constituent_returns_cn_digest_third` and `test_evidence_for_constituent_digest_none_for_non_cn` added (diff `test_snapshot.py:+493..+521`). All 4 existing 2-tuple unpacks in opportunity/command tests updated. OK.

**Task 6 (append fragment to `_one_line_view` within `[:60]` cap):** `_one_line_view` gains optional `cn_digest: FilingDigest | None = None` param (diff `snapshot.py:+432`). Fragment appended via `ratios_reason_fragment(compute_ratios(cn_digest))` before the join+cap (diff `snapshot.py:+457..+460`). Call site wired `_cn_digest` (diff `snapshot.py:+563`). Three `one_line_view` tests added to `test_snapshot.py` (diff `test_snapshot.py:+523..+570`). OK.

**Task 7 (purity lock for `compute_ratios`):** `test_compute_ratios_no_module_level_side_effects` and `test_compute_ratios_does_not_mutate_input` added to `test_ratios.py` (diff `test_ratios.py:+112..+155`). OK.

**Task 8 (byte-stability + no-state/citation lock):** `test_one_line_view_two_run_byte_stable_for_ratio_bearing_row` added to `test_snapshot.py` (diff `test_snapshot.py:+572..+587`), asserting same digest → byte-identical output and no `[ref:...]`. `test_snapshot_acceptance.py` was NOT modified (the plan noted acceptance tests assert evidence counts, not `one_line_view` byte content — no update needed and confirmed by zero diff). OK.

**Task 9 (CONTEXT.md assertion + full-suite gate):** CONTEXT.md entries for `KeyRatios`, `compute_ratios`, `FilingDigest.roe` confirmed present at lines 132–134 (pre-existing from commit 4b9f050, no new diff needed). No ADR 0010 created. PROGRESS.md records "978 passed / 2 pre-existing fails / 13 skipped, 0 new. Ruff clean." OK.

---

## Incidental scope

- `docs/2026-05-31-funding-analysis/PROGRESS.md` updated to mark item 004 impl column and add impl log entry. Accepted as standard harness tracking (incidental).
