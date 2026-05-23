# Item 004 spec — live-verify `fund_announcement_em` (Slice E13, Q4 hard-stop gate)

## Goal

Falsify — against the **real** AkShare package installed in this repo — the load-bearing assumption that `ak.fund_announcement_em(symbol=<fund_id>)` exists, is callable, and returns a non-empty DataFrame carrying time-bound announcement metadata for the three fund classes that item 005 (Slice F) must publish: **gold** (`518880`), **cn_bond_fund** (`000001`), and an active CN equity fund (`005827`, sanity check). This is the **Q4 hard-stop gate** identified in `docs/diagnosis-thesis-cards-evidence-gap.md` §5 Open Q4 and §4 step 3 — item 005 wires this adapter as the *only* `citation_kind="information"` source for gold and cn_bond_fund (the `单位净值走势` indicator is the `citation_kind="data"` leg). If `fund_announcement_em` is missing or empty in the pinned AkShare, item 005's information leg is **impossible**, every gold + cn_bond_fund row will fail the dual-coverage citation gate in item 009, and Q4 must be re-decided **before** any item 005 work begins. The autodev orchestrator reads this test's exit code as the gate: PASS → proceed to item 005; FAIL → STOP the entire run and fall back to Q4 option (b) (reuse theme reports with promoted scope) or option (c) (exclude gold + cn_bond_fund from V1). Item 004 ships ONLY the live test, the captured fixture, and the `pyproject.toml` marker registration — it does NOT ship any production adapter (that is item 005's `fetch_fund_nav_report` + announcement-fetch wrapper).

## In scope

1. **Pytest marker registration.** Add a `[tool.pytest.ini_options]` `markers` entry (and `--strict-markers` in `addopts`) to `pyproject.toml`. `[tool.pytest.ini_options]` already exists with `testpaths` + `pythonpath` — extend, do not replace:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   pythonpath = ["src", "."]
   addopts = ["--strict-markers"]
   markers = [
       "live_akshare: hits the real AkShare network. Run via `pytest -m live_akshare` with IRC_RUN_LIVE_AKSHARE=1. Excluded from default `pytest` runs.",
       "integration: integration test exercising multiple modules end-to-end (no external network). Currently used by tests/integration/test_thesis_coverage.py.",
   ]
   ```
   Without `markers = [...]` the marker emits `PytestUnknownMarkWarning`, AND without `--strict-markers` a typo (`live_akshre`) would silently skip the test entirely. **`integration` MUST also be registered:** grep across `tests/` confirms `@pytest.mark.integration` is the only other custom marker in the suite (two usages in `tests/integration/test_thesis_coverage.py`). Omitting it would make every default `pytest` run abort with `'integration' not found in markers` once `--strict-markers` is active — a regression of item 003's coverage gate.
2. **Default exclusion.** Default `pytest` invocations (no `-m` flag) MUST skip every `live_akshare` test. Achieved via the pattern already used by `tests/integration/test_live_endpoints.py`: a module-level `pytestmark` combining `pytest.mark.live_akshare` with a `pytest.mark.skipif` on an env flag (`IRC_RUN_LIVE_AKSHARE=1`) **OR** by adding a default `-m "not live_akshare"` to `addopts`. **Decision: dual gate** — both the marker (`pytest -m live_akshare`) AND the env flag (`IRC_RUN_LIVE_AKSHARE=1`) must be active. This matches the existing live-test idiom (`RUN_LIVE_INGEST_TESTS=1`, `RUN_LIVE_LLM_TESTS=1`) and prevents accidental network calls in CI where someone might `pytest -m live_akshare tests/` and expect a dry-run.
3. **New test file.** Create `tests/fundamentals/test_fund_announcement_em_live.py` carrying the live-call tests. Located in `tests/fundamentals/` (not `tests/integration/`) because (a) item 003 has already established `tests/fundamentals/` as the home for AkShare-adapter tests; (b) item 005's eventual `fetch_fund_announcement_em` adapter wrapper will live in `src/irc/fundamentals/akshare_fundamentals.py` and its mocked unit test will sit next to this live test — keeping live + mocked side-by-side makes the fixture-driven contract obvious.
4. **Module-level gating preamble.**
   ```python
   import os
   import pytest

   _RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
   pytestmark = [
       pytest.mark.live_akshare,
       pytest.mark.skipif(not _RUN, reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests"),
   ]
   ```
5. **Invocation indirection.** Tests call `ak.fund_announcement_em(...)` through the existing `_ak_call` wrapper in `src/irc/fundamentals/akshare_fundamentals.py` (`_ak_call("fund_announcement_em", symbol=<fund_id>)`). Rationale: any future fixture-driven mocking patches `_ak_call`; using the same path here means the live shape and the mocked shape are guaranteed congruent. Do NOT `import akshare as ak` directly in the test file — keep all AkShare access through the project's wrapper.
6. **Adapter-existence preflight (`test_fund_announcement_em_adapter_exists`).** First test in the file. Imports `akshare` (lazily) and asserts `hasattr(ak, "fund_announcement_em")`. On failure raises `AssertionError` with the Q4-prerequisite-failure message (see §"Failure-trace contract"). This test executes before the per-symbol tests so an empty AkShare attribute fails fast with the right diagnostic rather than buried inside an `AttributeError` traceback.
7. **Three per-symbol smoke tests.** Three independent test functions (NOT `pytest.mark.parametrize`):
   - `test_fund_announcement_em_gold_518880`
   - `test_fund_announcement_em_bond_000001`
   - `test_fund_announcement_em_active_005827`

   Each one: (a) calls `_ak_call("fund_announcement_em", symbol=<fund_id>)`; (b) asserts the return value is a `pandas.DataFrame`; (c) asserts the DataFrame is non-empty (`len(df) >= N_MIN[symbol]`); (d) resolves the four logical columns `{title, type, date, url}` via the column-equivalence map (§"Column-name discovery") and asserts each maps to a present column with non-null entries on the first row; (e) emits a one-line `print` summary `"  ✓ fund_announcement_em/{symbol} → {n} rows, latest={date_value}, url={url_value[:60]}"` matching the diagnostic-print style of `tests/integration/test_live_endpoints.py`.

   **Per-symbol minimum row thresholds** (`N_MIN`):
   - `518880` (gold, active product since 2013) → `>= 5` rows.
   - `000001` (bond — `华夏成长` legacy code; bond funds disclose periodically) → `>= 5` rows.
   - `005827` (易方达蓝筹精选 — active equity, the regression sanity-check) → `>= 3` rows.

   These thresholds exist because the threshold ratchet detects "AkShare returned 1 row only" regressions that strict non-empty checks would miss.
8. **Aggregate gate test (`test_fund_announcement_em_q4_gate`).** Last test in the file. Calls all three symbols in sequence (re-using the per-symbol logic). Collects per-symbol PASS/FAIL into a structured dict. **Asserts all three PASSED.** On failure, raises with the structured Q4-failure message listing exactly which symbol(s) failed and which check failed (missing function | empty result | missing column | row count below threshold). This is the test the autodev orchestrator reads for the gate decision — the three per-symbol tests give granular debugging signal; this one gives the binary go / no-go.
9. **Fixture capture (`tests/fixtures/akshare/fund_announcement_em_518880.json`).** The gold-symbol test captures its live response to `tests/fixtures/akshare/fund_announcement_em_518880.json`. Format: a JSON object with two keys:
   ```json
   {
     "columns": ["公告标题", "公告类型", "公告日期", "公告链接", ...],
     "rows": [
       {"公告标题": "...", "公告类型": "...", "公告日期": "2024-12-31", "公告链接": "https://...", ...},
       ...
     ],
     "captured_at": "2026-05-22T10:30:00Z",
     "akshare_version": "1.13.x"
   }
   ```
   AkShare-canonical column names (Chinese, where present) are preserved so item 005's mocked unit test sees the real shape. `captured_at` and `akshare_version` are metadata stamps so a stale fixture can be detected later.
10. **Fixture-capture site & overwrite policy.** Fixture capture is integrated into `test_fund_announcement_em_gold_518880` (NOT a separate test) — after the assertions pass for `518880`, the test writes the fixture file via a small helper `_capture_fixture(df, path)`. **Overwrite policy: always overwrite on a successful live run** (NOT first-run-only). Argued both sides:
    - *First-run-only (rejected):* a frozen fixture diverges from upstream AkShare over time. The whole point of E13 is to re-falsify on each AkShare upgrade — a frozen fixture defeats that purpose.
    - *Always-overwrite (chosen):* fixture is treated as a captured shadow of the latest live response. Re-running the test refreshes it. Determinism note: the JSON content varies day-to-day (new announcements), so the fixture file itself is checked in but the test does NOT assert content equality against the fixture — only column shape + non-empty. The diff-noise on commit is expected and benign (signals that announcements were added upstream, which is the desired behaviour).
11. **AkShare-already-installed precondition.** The test does NOT install AkShare. The repo's `pyproject.toml` already pins `akshare>=1.13`. If a developer runs the live test against a stale env, the `_ak_call` lazy-import will raise `ModuleNotFoundError` — that's an environment defect, not a test failure to fix. Add a one-line pytest fixture or module-load assert that surfaces `ModuleNotFoundError` with the message `"akshare not installed in this venv. Install with: uv sync --extra dev (or check pyproject.toml dependencies)"` so the failure mode is clear.
12. **Mocked failure-mode companion test file.** Create `tests/fundamentals/test_fund_announcement_em_failure_modes.py` — NOT live, runs in default `pytest` invocations, ~30 LoC. Uses `pytest-mock` (already in dev extras) to patch `irc.fundamentals.akshare_fundamentals._ak_call` and assert the *helper functions* produce the right structured `Q4 PREREQUISITE FAILURE` messages for: (a) missing function (`hasattr` returns False), (b) empty DataFrame return, (c) DataFrame missing `公告链接` column, (d) `None` return, (e) exception during call. The helpers under test are `_resolve_column` and the message-template builders extracted from the live test file (lifted into a small `_failure_messages` module in the test file or imported from the live test file). Rationale: the live tests can only assert "real AkShare passes today"; they cannot assert "the failure trace tone is correct" because that path is never exercised when AkShare is healthy. The mocked companion file locks the failure-trace contract so future regressions in the message templates surface immediately. **Permanent** addition to the default suite (NOT hand-verified-only like criteria 11–14 of acceptance below). Cost: ~30 LoC; benefit: protects the autodev orchestrator's stdout-reading gate logic from silent template drift.

## Out of scope

- **Any production adapter.** No `fetch_fund_announcement_em(fund_id) -> tuple[...]` wrapper. That ships in item 005 (Slice F2), informed by the fixture this slice captures.
- **Any other AkShare endpoint.** No live tests for `fund_open_fund_info_em(indicator="单位净值走势")`, `fund_individual_basic_info_xq`, `stock_news_em`, or `stock_hk_news_em`. The diagnosis already verifies `fund_open_fund_info_em` works in `tests/integration/test_live_endpoints.py:50-56` (Layer 1, EastMoney NAV). Live verification for `stock_news_em` / `stock_hk_news_em` is item 003's concern (already shipped).
- **Wiring the fixture into a mock-based unit test.** Item 005 owns the mock-test side (`test_fetch_fund_announcement_em_uses_fixture` or similar). Item 004 only writes the fixture file; it does not consume it.
- **Q4 fall-back path implementation.** Options (b) "reuse theme reports with promoted scope" and (c) "exclude gold + cn_bond_fund from V1" are documented in the diagnosis. Their *implementation* is the orchestrator's decision after this test fails — out of scope for the test itself.
- **`fund_open_fund_info_em(symbol, indicator="基金概况")` exclusion test.** The diagnosis (§F2) says `基金概况` static profile text must NOT satisfy the `citation_kind="information"` gate. That gate assertion belongs in item 005's unit tests, not here.
- **Pyproject AkShare version pin tightening.** Current pin `akshare>=1.13` is a floor, not a lock. Tightening to `akshare>=1.13,<1.x.y+1` is a separate maintenance decision out of scope here.
- **Renaming `RUN_LIVE_INGEST_TESTS` / `RUN_LIVE_LLM_TESTS` to the `IRC_*` prefix.** Out of scope — item 004 introduces ONE new `IRC_RUN_LIVE_AKSHARE` env var consistent with the modern `IRC_*` convention; unifying the older names is a separate follow-up cleanup. Both naming families coexist after item 004 (documented in CONTEXT.md "Live test gate").

## Column-name discovery

AkShare's `fund_announcement_em` returns Chinese column names in its DataFrame. From the AkShare project conventions and inspection of similar fund-facing endpoints (`fund_individual_basic_info_xq`, `fund_open_fund_info_em`), the canonical columns are expected to be:

| Logical name | Expected AkShare column (Chinese) | Acceptable alternates |
|---|---|---|
| `title` | `公告标题` | `标题`, `title` |
| `type` | `公告类型` | `类型`, `type` |
| `date` | `公告日期` | `日期`, `发布日期`, `date` |
| `url` | `公告链接` | `链接`, `url` |

The test defines a `COLUMN_EQUIVALENCE` map:

```python
COLUMN_EQUIVALENCE: dict[str, tuple[str, ...]] = {
    "title": ("公告标题", "标题", "title"),
    "type":  ("公告类型", "类型", "type"),
    "date":  ("公告日期", "公告时间", "日期", "发布日期", "date"),
    "url":   ("公告链接", "链接", "url"),
}

def _resolve_column(df, logical: str) -> str:
    for candidate in COLUMN_EQUIVALENCE[logical]:
        if candidate in df.columns:
            return candidate
    raise AssertionError(
        f"Q4 PREREQUISITE FAILURE: fund_announcement_em returned a DataFrame "
        f"missing the '{logical}' column. "
        f"Expected one of {COLUMN_EQUIVALENCE[logical]!r}. "
        f"Got columns: {sorted(df.columns)!r}. "
        f"AkShare schema may have changed — STOP and re-decide Q4 "
        f"(option b: theme-report scope promotion, option c: exclude gold+cn_bond_fund)."
    )
```

The `date` field intentionally accepts `公告时间` (some AkShare versions use timestamp rather than date). If schema drift adds a new required column (e.g. `公告全文`) the test silently ignores it — only the 4 logical columns are gate-relevant. If schema drift REMOVES one of the 4, the resolver raises and the gate fails loudly. This is the intended behaviour (covers the "AkShare adds a new required col" judgement call below).

## Failure-trace contract

All assertion failures use **structured Q4-prerequisite-failure messages**, not terse `assert df.size > 0`. Argued both sides:

- *Terse `AssertionError` (rejected):* leaves a future reader (autodev orchestrator, human triage) hunting through diagnosis docs to discover that this test is the Q4 gate. The retrieval cost compounds across re-runs.
- *Structured (chosen):* the failure message itself carries: (1) the symbol that failed, (2) the specific check that failed (missing function | empty result | missing column | row count below threshold), (3) the next action ("STOP and re-decide Q4"), (4) the two known fall-back options. Cost: ~5 extra lines of test code; benefit: zero context-switching cost when the test fails 6 months from now.

Failure-message templates:

```
Q4 PREREQUISITE FAILURE: ak.fund_announcement_em is missing from the installed
AkShare ({akshare.__version__}). Item 005 cannot ship its information leg.
STOP and re-decide Q4 (option b: theme-report scope-promotion, option c:
exclude gold + cn_bond_fund from V1). See docs/diagnosis-thesis-cards-evidence-gap.md §5.

Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol}) returned
{actual_n} rows; threshold is {N_MIN[symbol]}. Information leg unreliable.
STOP and re-decide Q4. See docs/diagnosis-thesis-cards-evidence-gap.md §5.

Q4 PREREQUISITE FAILURE: ak.fund_announcement_em returned a DataFrame
missing the '{logical}' column. Expected one of {candidates!r}.
Got columns: {actual_columns!r}. AkShare schema may have changed.
STOP and re-decide Q4. See docs/diagnosis-thesis-cards-evidence-gap.md §5.

Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol}) raised
{exc_type}: {exc}. Information leg unreachable.
STOP and re-decide Q4. See docs/diagnosis-thesis-cards-evidence-gap.md §5.
```

The aggregate gate test (`test_fund_announcement_em_q4_gate`) collects per-symbol failure messages and emits a multi-line summary of every failing symbol — so one failure surfaces all related failures in one read.

## Acceptance criteria

1. **Marker registration lands in `pyproject.toml`.** `[tool.pytest.ini_options]` carries a `markers = [...]` list including `"live_akshare: ..."` AND `addopts = ["--strict-markers"]`. `pytest --markers | grep live_akshare` lists the marker with its description. A typo'd marker like `pytest -m live_akshre` exits non-zero with a `'live_akshre' not found in markers` error (proves `--strict-markers` is active).
2. **Default `pytest` invocations skip the live test.** Running `pytest tests/fundamentals/test_fund_announcement_em_live.py` with no env vars and no `-m` flag reports `all tests skipped` (via `pytest.mark.skipif`). Zero AkShare calls occur.
3. **`pytest -m live_akshare tests/fundamentals/test_fund_announcement_em_live.py` (without env var) still skips.** Both the marker AND `IRC_RUN_LIVE_AKSHARE=1` are required — this proves the dual gate. The skip reason is `"set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests"`.
4. **`IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare tests/fundamentals/test_fund_announcement_em_live.py -v -s` runs all 5 tests** (1 preflight + 3 per-symbol + 1 aggregate gate) and they all PASS against the AkShare version currently pinned in `pyproject.toml`.
5. **Adapter-existence preflight.** `test_fund_announcement_em_adapter_exists` PASSES — `hasattr(ak, "fund_announcement_em")` is True in the pinned AkShare.
6. **Per-symbol live calls return non-empty DataFrames with required columns.**
   - `518880` → `len(df) >= 5` AND the four logical columns `{title, type, date, url}` resolve via `COLUMN_EQUIVALENCE` to real columns with non-null values on at least the first row.
   - `000001` → `len(df) >= 5` AND same column-resolution.
   - `005827` → `len(df) >= 3` AND same column-resolution.
7. **Aggregate gate test PASSES.** `test_fund_announcement_em_q4_gate` reports all three symbols PASSED.
8. **Fixture file is written to `tests/fixtures/akshare/fund_announcement_em_518880.json`** after the gold-symbol test passes. File contents: `{"columns": [...], "rows": [...], "captured_at": "<ISO-8601 UTC>", "akshare_version": "<version string>"}`. The Chinese column names from AkShare are preserved verbatim (not romanized).
9. **Fixture-write directory creation.** If `tests/fixtures/akshare/` does not exist, the test creates it via `path.parent.mkdir(parents=True, exist_ok=True)` before writing. The write is atomic (`.tmp → os.replace`).
10. **Idempotent re-run.** Running the full test file twice in succession produces the same final state: tests pass, fixture file exists and is overwritten on each successful run (timestamp differs; row count may differ if upstream added announcements; column shape is identical). No leftover `.tmp` files in `tests/fixtures/akshare/`.
11. **Function-missing failure mode.** Patch `_ak_call` (or monkeypatch `hasattr`) to simulate `fund_announcement_em` missing → `test_fund_announcement_em_adapter_exists` FAILS with the structured `"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em is missing..."` message. The aggregate gate test ALSO fails (does not need to re-run if preflight fails; pytest stops via `-x` if desired, but the suite still completes by default). **This test is hand-verified during impl; it is NOT a permanent test in the suite** (no point in mocking AkShare to assert AkShare is missing).
12. **Empty-DataFrame failure mode.** Patch `_ak_call` to return `pd.DataFrame()` (or `pd.DataFrame(columns=["公告标题", "公告类型", "公告日期", "公告链接"])` — empty rows) for ALL three symbols → all three per-symbol tests FAIL with structured row-count failure messages; aggregate gate FAILS listing all three. Same caveat as (11) — hand-verified during impl, not a permanent suite test.
13. **One-symbol-empty failure mode.** Patch `_ak_call` so `518880` returns empty but `000001` and `005827` return real data → `test_fund_announcement_em_gold_518880` FAILS; the other two PASS; aggregate gate FAILS naming only `518880`. Same caveat as (11).
14. **Missing-column failure mode.** Patch `_ak_call` to return a DataFrame missing `公告链接` → per-symbol test FAILS with the structured missing-column message listing the expected alternates and the actual columns observed. Same caveat as (11).
15. **`pytest -x` invocations without the marker are unaffected.** `pytest -x` (the default suite gate) does NOT run the live test; total test runtime is unchanged. Zero AkShare imports occur in default suite runs (proven via `python -X importtime` or via grepping the pytest collection output for `akshare` — neither should appear).
16. **No production code in `src/` changes.** Only `pyproject.toml`, `tests/fundamentals/test_fund_announcement_em_live.py`, and the fixture file are added/modified. (`src/irc/fundamentals/akshare_fundamentals.py`'s `_ak_call` is read, not modified.)

## Constraints

- **Network access required.** The live test cannot run in offline CI. CI documentation (out of scope here but worth noting in the PR description) must clarify that `pytest -m live_akshare` is a manual-trigger / nightly job, not on every PR.
- **AkShare rate limits.** EastMoney (the upstream that `fund_announcement_em` scrapes) imposes per-IP throttling. Three calls per run is well under any threshold. No sleep / retry needed for V1. If item 005 expands this to per-fund-row in canonical runs (50+ funds), revisit; item 004 itself uses only 3 calls.
- **Fixture format = JSON.** Not CSV (Chinese column names + escaped commas in titles cause parsing pain) and not parquet (binary diff is unreviewable in PR review). UTF-8 JSON with `ensure_ascii=False` so Chinese columns and Chinese announcement titles read naturally in PR diffs.
- **AkShare-canonical Chinese column names preserved.** The fixture stores the columns AS RETURNED by AkShare. Item 005's mocked unit test will operate on these. Romanizing or translating column names would silently break the contract.
- **No new dependencies.** `pandas` is already in `pyproject.toml`. `pytest` and `pytest-mock` are in `dev` extras. No new runtime or dev deps.
- **`IRC_RUN_LIVE_AKSHARE` env-var name** is new — chosen for consistency with the existing `RUN_LIVE_INGEST_TESTS` / `RUN_LIVE_LLM_TESTS` family. **Naming choice:** prefix with `IRC_` to match the project-wide env-var convention (`IRC_FETCH_BUDGET`, `IRC_OPPORTUNITY_AUTOBUILD`, `IRC_CITATION_ENFORCE_MODE`) rather than the older `RUN_LIVE_*` names. **Migration note for the planner:** the older `RUN_LIVE_INGEST_TESTS` env var is left untouched in this slice; a follow-up cleanup item could unify them but is out of scope for E13.

## Open questions resolved during brainstorming

**Q-A. Fixture capture — first-run-only vs. always-overwrite?** Resolved: **always-overwrite** on every successful live run. Rationale documented in §"In scope" #10. Trade-off: PR diff churn on the fixture file becomes routine (new announcements arrive upstream). Mitigation: the test does NOT assert content equality against the fixture (only shape + non-empty), so fixture-content drift never breaks the test.

**Q-B. Parametrize vs. 3 separate test functions?** Resolved: **3 separate functions + 1 aggregate gate test**. Rationale: separate functions give granular failure isolation in pytest's report (one symbol's failure does not stop the others from running). The aggregate test gives the orchestrator-readable binary gate. A single `@pytest.mark.parametrize("symbol", ["518880", "000001", "005827"])` would conflate "function exists, symbol N empty" with "function missing" because pytest's parametrized failure UI lumps them. The separation also lets per-symbol `N_MIN` thresholds differ (5/5/3) without `pytest.param`-marker contortions.

**Q-C. Failure-trace tone — terse vs. structured?** Resolved: **structured Q4-prerequisite-failure messages**. Rationale documented in §"Failure-trace contract". The test's primary reader is an autodev orchestrator (which reads stdout); the secondary reader is a human triaging a failed run six months from now. A terse `AssertionError: df is empty` forces both readers to re-read the diagnosis doc to remember why this test matters. The structured message carries the next action (STOP, re-decide Q4) in the failure itself.

**Q-D. Will the test catch a NEW required AkShare column?** Resolved: **No, by design.** If AkShare adds a new column (e.g. `公告全文`) the existing test passes — only the 4 gate-relevant logical columns are checked. This is intentional: item 005's information leg cares about `{title, type, date, url}`; new columns are bonus context, not gate failures. If a future slice depends on a new column, that slice's test extends `COLUMN_EQUIVALENCE` — it does not require modifying item 004's test.

**Q-E. Will the test catch a REMOVED required AkShare column?** Resolved: **Yes, loudly.** The `_resolve_column` helper raises a structured `AssertionError` listing the missing logical column, its accepted alternates, and the actual columns observed. This is the primary "AkShare regression" failure mode the test is designed to catch — distinct from "empty rows" (count threshold) and "function missing" (preflight).

**Q-F. Fund ID format — leading zeros?** Resolved: **always pass as 6-character string** matching AkShare's existing convention (`"518880"`, `"000001"`, `"005827"`). No stripping, no conversion to `int`. AkShare's docs and other adapters (`fund_open_fund_info_em(symbol="510300")`, `fund_individual_basic_info_xq(symbol="006075")`) consistently use string-with-leading-zeros. Tests assert this format explicitly so a future "let's pass int" refactor fails fast.

**Q-G. What if AkShare returns `None` instead of an empty DataFrame?** Resolved: explicit `isinstance(result, pd.DataFrame)` check before `len(result)`. If the return is `None` or any non-DataFrame, the per-symbol test fails with `"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol}) returned a non-DataFrame ({type(result).__name__}) — possibly an AkShare error path. STOP and re-decide Q4."` Three-state handling: `DataFrame` (normal — count gate applies), `None` (failure), exception (failure with traceback captured in message).

**Q-H. What if AkShare returns a DataFrame but `pd.api.types.is_object_dtype` columns are all-null?** Resolved: assert `df.iloc[0][resolved_col]` is non-null and non-empty-string for each of the 4 logical columns. A DataFrame with structurally-present but content-empty columns counts as failure. The first-row check is sufficient — assumes AkShare's response is row-uniform, which matches every other AkShare adapter the repo uses.

**Q-I. Does the live test need to assert on `005827` specifically being an active fund?** Resolved: **No.** The active-fund sanity check is a *coverage* concern (proving the adapter works for active funds, not just on-exchange ETFs and bond funds). The test does not need to assert `005827` IS active — it just needs a non-empty response. If `005827` is delisted or renamed, swap to another active fund (e.g. `001071` `华安媒体互联网` or whatever item 003 uses) — but defer that to whoever encounters the failure, since it's a fixture-input choice, not a structural change.

**Q-J. Should the aggregate gate test re-call AkShare or aggregate the prior 3 test results?** Resolved: **Re-call.** Pytest does not natively pass results between tests; using `request.session` to thread results in is fragile. Three extra AkShare calls (6 total per run) is negligible. The aggregate test is the autodev gate signal — making it self-contained (does not depend on test execution order) is worth the duplicate-call cost.

**Q-K. Should `fund_announcement_em` accept an optional `date` argument that needs verification?** Resolved: **Out of scope.** The MASTER-SPEC only requires `symbol`-based calls; item 005's eventual wrapper may add date-windowing if useful, but item 004 verifies only the minimum-viable signature.

## Files touched (preview for planner)

| File | Action |
|---|---|
| `pyproject.toml` | Add `markers` entry under `[tool.pytest.ini_options]` (BOTH `live_akshare` AND `integration`); add `addopts = ["--strict-markers"]`. |
| `tests/fundamentals/test_fund_announcement_em_live.py` (new) | The 5 tests (preflight + 3 per-symbol + aggregate gate) + `COLUMN_EQUIVALENCE` map + `_resolve_column` + `_capture_fixture` helpers + `pytestmark` gating preamble. |
| `tests/fundamentals/test_fund_announcement_em_failure_modes.py` (new) | Mocked companion: ~30 LoC, runs by default, locks the failure-trace tone. Patches `_ak_call` to cover function-missing / empty / `None` / missing-column / exception paths. |
| `tests/fixtures/akshare/fund_announcement_em_518880.json` (new) | Captured live response. Written on first successful run; overwritten on every subsequent successful run. |
| `tests/fixtures/akshare/` (new directory) | Created if missing. |

No `src/` changes. No new dependencies. No new ADR (this slice's decisions are entirely test-infrastructure — they don't survive past the gate event; CONTEXT.md captures the four new vocabulary entries instead).

## Dependencies on other items

**Hard requires (must merge before item 004 — already done):**
- Item 001, 002, 003 — none of them block item 004 structurally. Item 003 incidentally established `tests/fundamentals/` as the AkShare-adapter test home and `_ak_call` as the canonical wrapper; item 004 reuses both.

**Required-by (items that read item 004's outputs):**
- Item 005 (Slice F) — gated entirely on item 004 passing. If item 004 FAILS, item 005's information-leg adapter cannot ship as designed; the autodev run halts at the master-plan stop condition.
- Item 005 also consumes the captured fixture indirectly: item 005's mocked unit test for its eventual `fetch_fund_announcement_em` wrapper will load `tests/fixtures/akshare/fund_announcement_em_518880.json` to assert column-name handling matches the real shape.

## Stop / proceed contract

After item 004 ships and verifies:

- **PASS** (all 5 tests green against pinned AkShare) → autodev proceeds to item 005 (Slice F). The fixture is now available for item 005's mock tests.
- **FAIL** (any of the 5 tests red) → autodev STOPS. Operational definition of **STOP** for the autodev orchestrator:
  1. Do NOT start item 005 implementation. Do NOT start items 006–010 (every downstream item depends on item 005's evidence emission).
  2. Mark item 004 with a `FAIL` verdict in the run-level `PROGRESS.md`. Mark items 005–010 with `BLOCKED-BY-004` (not `PENDING`).
  3. Return control to the user with a structured message: the failing test name(s), the captured stdout containing the `Q4 PREREQUISITE FAILURE: ...` lines, the symbol(s) that failed, and the verbatim three Q4 fall-back options from `docs/diagnosis-thesis-cards-evidence-gap.md` §5: (a) re-pin AkShare to a version with the function; (b) reuse theme reports with promoted scope (treat asset-class macro citations as information-leg for gold + cn_bond_fund); (c) exclude gold + cn_bond_fund from V1.
  4. Do NOT auto-select a fall-back option. The choice between (a)/(b)/(c) is a product-scope decision that the autodev orchestrator MUST escalate to the user rather than guess.
  5. Resume only after the user re-decides Q4 and records the decision in a new item (e.g. item 004b) or amends item 005's spec to reflect the chosen fall-back.

  Item 005 does NOT enter the implementation order until that re-decision is documented in the run-level `PROGRESS.md`.

## Pivot — Q4 option (a)

**User chose option (a) on 2026-05-23.**

The single `fund_announcement_em` endpoint does not exist in AkShare 1.18.63. Per the Q4 FAIL verdict (`004-verify.md`), three topic-specific endpoints are present and workable. The pivot substitutes these three endpoints for the missing one.

### Endpoints adopted

| Endpoint | Topic | 518880 rows | 000001 rows | 005827 rows |
|---|---|---|---|---|
| `fund_announcement_dividend_em` | 分红配送 / dividend & distribution | 4 | 15 | 1 |
| `fund_announcement_report_em` | 定期报告 / periodic reports | 94 | 100 | 50 |
| `fund_announcement_personnel_em` | 人员变动 / personnel changes | 2 | 14 | 2 |

### Actual column shapes (AkShare 1.18.63, explored 2026-05-23)

All three endpoints return the **same** schema:

```
['基金代码', '公告标题', '基金名称', '公告日期', '报告ID']
```

- `基金代码` — fund symbol (e.g. `"518880"`)
- `公告标题` — announcement title → logical `title`
- `基金名称` — fund name (e.g. `"华安黄金易ETF"`)
- `公告日期` — announcement date (Python `datetime.date`) → logical `date`
- `报告ID` — report identifier (e.g. `"AN201307240003689710"`) → logical `id` / surrogate for `url`

**Notable difference from original spec:** No `公告类型` (type) column and no `公告链接` (url) column. The `报告ID` serves as the canonical reference identifier. Item 005's information-leg normalizer must derive a URL from `报告ID` or treat it as an opaque ID.

### Updated `COLUMN_EQUIVALENCE` (per-endpoint)

All three endpoints have identical schemas, so a single map applies:

```python
COLUMN_EQUIVALENCE = {
    "fund_announcement_dividend_em": {
        "title": ("公告标题", "标题", "title"),
        "date":  ("公告日期", "公告时间", "日期", "发布日期", "date"),
        "id":    ("报告ID", "id"),
        "fund":  ("基金代码", "code"),
    },
    "fund_announcement_report_em": {
        "title": ("公告标题", "标题", "title"),
        "date":  ("公告日期", "公告时间", "日期", "发布日期", "date"),
        "id":    ("报告ID", "id"),
        "fund":  ("基金代码", "code"),
    },
    "fund_announcement_personnel_em": {
        "title": ("公告标题", "标题", "title"),
        "date":  ("公告日期", "公告时间", "日期", "发布日期", "date"),
        "id":    ("报告ID", "id"),
        "fund":  ("基金代码", "code"),
    },
}
```

### Updated acceptance criteria (replaces original §"Acceptance criteria")

~~Original acceptance criteria (4–8): `fund_announcement_em` exists, returns non-empty DataFrame with `{title, type, date, url}` columns for all 3 symbols, fixture written to `fund_announcement_em_518880.json`.~~ — pivoted to option (a) 2026-05-23: AkShare 1.18.63 has no `fund_announcement_em`; substituted 3 topic-specific endpoints.

**New criteria (option a):**

1. **11-test suite.** `test_fund_announcement_em_live.py` carries: 1 preflight + 9 per-endpoint × per-symbol + 1 aggregate gate = 11 live tests.
2. **Preflight.** `test_fund_announcement_endpoints_exist` asserts `hasattr(ak, fn)` for all 3 endpoints.
3. **Per-endpoint × per-symbol tests (9 cells).** Each test calls the endpoint and asserts no exception raised; returns a DataFrame (possibly empty for some cells — see aggregate gate for coverage requirement). Non-empty cells also assert `title` and `date` columns resolve and first row is non-null.
4. **Per-symbol coverage (aggregate gate).** For each of the 3 symbols, AT LEAST ONE of the 3 endpoints must return a non-empty DataFrame. This gate PASSes even if some endpoint × symbol combinations are legitimately empty (e.g. `dividend_em` for `005827` returned only 1 row — fine if `report_em` covers it).
5. **9 fixture files.** `tests/fixtures/akshare/{endpoint}_{symbol}.json` written for all 9 combinations. Empty DataFrames produce empty `rows: []` arrays (still valid fixture, captures the schema).
6. **Failure-mode companion untouched.** `test_fund_announcement_em_failure_modes.py` still 5/5 PASS.

### Downstream impact for item 005

Item 005 (Slice F) must:

1. Call all 3 topic-specific endpoints for each fund symbol (not one endpoint).
2. Union the 3 DataFrames per symbol, normalizing columns to `{title, date, id}` (no `url` — use `报告ID` as opaque reference identifier).
3. The `citation_kind="information"` leg now emits 3 rows per fund (one per announcement topic) rather than N rows from a single unified stream.
4. The column normalizer must handle `datetime.date` objects in `公告日期` (not strings) — AkShare returns Python date objects, not date strings.

## Resolved decisions

Grilling pass on 2026-05-23. Six questions raised against the spec; auto-accepted recommendations applied inline above. Original spec content preserved; corrected lines are called out below for provenance.

**Strike-through provenance (corrected lines):**
- §"In scope" #1 originally said only `"live_akshare"` needs registration. ~~`markers = ["live_akshare: ..."]`~~ — corrected by grill: `@pytest.mark.integration` is already used in `tests/integration/test_thesis_coverage.py` (lines 14, 33) and would fail under `--strict-markers` unless ALSO registered. The corrected `markers = [...]` list now contains both entries.
- §"Files touched" — `pyproject.toml` row originally said "Add `markers` entry". Corrected to clarify that BOTH `live_akshare` AND `integration` markers must be added together, not separately.

### Resolved Q&A

**Q-1. Does `[tool.pytest.ini_options]` already exist in `pyproject.toml`, and does enabling `--strict-markers` break other tests?**
A: YES it exists (lines 46–48 of `pyproject.toml`) with `testpaths` and `pythonpath` keys, but NO `markers` or `addopts`. Adding `--strict-markers` will break `tests/integration/test_thesis_coverage.py` (uses unregistered `@pytest.mark.integration` at lines 14 and 33). The spec MUST register `integration` alongside `live_akshare`. Rationale: a coverage gate (item 003) regressing because of a marker-strictness setting introduced by item 004 would be a cross-item defect. Doc impact: CONTEXT.md "Live test gate" term + spec §"In scope" #1 corrected.

**Q-2. Is `005827` (易方达蓝筹精选) still active and disclosing announcements?**
A: Defer to impl-time verification. The fund was active at the diagnosis date (2026-05-21) per the source diagnosis doc. The spec already has the right fallback (Q-I): "If `005827` is delisted or renamed, swap to another active fund (e.g. `001071` `华安媒体互联网`) — but defer that to whoever encounters the failure, since it's a fixture-input choice, not a structural change." No further grill action — the spec's hand-off to impl is acceptable. If the live test fails specifically on `005827` while the other two pass, the impl-stage author swaps the symbol and re-records; this is NOT a Q4 hard-stop. Doc impact: none (already captured in spec Q-I).

**Q-3. AkShare canonical column names for `fund_announcement_em` — are `公告标题 / 公告类型 / 公告日期 / 公告链接` still current, or has the schema drifted?**
A: The spec is robust to drift by design — the `COLUMN_EQUIVALENCE` map accepts alternates (`标题`, `公告时间`, `链接`, etc.) and the `_resolve_column` helper raises a structured `Q4 PREREQUISITE FAILURE` listing what was expected vs. what was observed. No further grill action — drift detection is the feature, not a bug. The fixture itself (always-overwritten) captures whatever AkShare currently emits, so the fixture is self-correcting across AkShare upgrades. Doc impact: CONTEXT.md "Column equivalence map" term added.

**Q-4. New `IRC_RUN_LIVE_AKSHARE` env var vs. reusing `RUN_LIVE_INGEST_TESTS`?**
A: Confirmed: introduce `IRC_RUN_LIVE_AKSHARE`. Rationale: (a) the modern project convention is `IRC_*` prefix (`IRC_FETCH_BUDGET`, `IRC_OPPORTUNITY_AUTOBUILD`, `IRC_CITATION_ENFORCE_MODE`, `IRC_CACHE_FRESHNESS_DAYS`, etc. — verified via `grep -roE "IRC_[A-Z_]+" src/`); (b) reusing `RUN_LIVE_INGEST_TESTS` would conflate two different scopes (general ingest live tests vs. the specific Q4 gate); (c) renaming the older `RUN_LIVE_*` vars is a separate cleanup, explicitly out of scope. Both naming families coexist after item 004; the precedent of introducing new vars under the modern convention is the right one. Doc impact: CONTEXT.md "Live test gate" term explicitly notes the two coexisting families.

**Q-5. Mocked failure-mode companion test — add it, or hand-verify only?**
A: ADD it. Recommendation: create `tests/fundamentals/test_fund_announcement_em_failure_modes.py` (~30 LoC, runs by default, uses `pytest-mock` already in dev extras) covering the five failure paths the live test cannot exercise: missing function, empty DataFrame, missing column, `None` return, exception. Rationale: live tests can only assert "AkShare passes today"; they cannot lock the failure-trace tone (the path is unreachable when AkShare is healthy). The autodev orchestrator reads structured `Q4 PREREQUISITE FAILURE: ...` lines from stdout to decide STOP; silent template drift in those messages would break the gate. ~30 LoC is cheap insurance. Acceptance criteria 11–14 in the original spec all said "hand-verified only" — the grill keeps those as hand-verified for the *live* file but adds permanent mocked equivalents in the new companion file. Doc impact: spec §"In scope" gains item #12; §"Files touched" gains a new row.

**Q-6. What does "STOP and re-decide Q4" mean operationally for the autodev orchestrator?**
A: Spelled out in five operational steps in §"Stop / proceed contract": (1) do NOT start items 005–010; (2) mark item 004 FAIL and items 005–010 `BLOCKED-BY-004` in PROGRESS.md; (3) escalate to user with structured failure message + three verbatim fall-back options; (4) do NOT auto-select a fall-back (product-scope decision); (5) resume only after the user records a re-decision. Rationale: the spec previously said "STOP" without defining what the orchestrator does — leaving "STOP" as a vibe is dangerous when the orchestrator runs unattended. Auto-selecting a fall-back would silently commit the project to a smaller V1 scope, which is precisely the decision the user must own. Doc impact: spec §"Stop / proceed contract" expanded. No CONTEXT.md change (orchestrator semantics, not domain vocabulary).

### Three-of-three ADR check

The grill considered whether a new ADR is warranted for the live-test gate convention. Verdict: **NO ADR**.

- **Hard-to-reverse?** Partial. Renaming `IRC_RUN_LIVE_AKSHARE` later is a single-test refactor (~5 minutes). Adding a marker is similarly cheap. NOT hard to reverse.
- **Surprising without context?** No. The pattern mirrors the existing `RUN_LIVE_INGEST_TESTS` / `RUN_LIVE_LLM_TESTS` idiom already familiar to anyone working in `tests/`.
- **Real trade-off with alternatives?** Mild. Single-gate (marker OR env var) vs. dual-gate (marker AND env var) was the real choice. Resolved in §"In scope" #2; dual gate prevents accidental network calls. Trade-off is real but narrow.

Two of three are weak → skip ADR. The four new CONTEXT.md glossary entries (Live test gate, Q4 prerequisite, AkShare fixture, Column equivalence map) capture the vocabulary; no architectural lock-in deserves an ADR.
