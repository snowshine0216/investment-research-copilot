# Item 002 — QDII Premium-to-NAV Fetcher

**Status:** spec
**Run:** decision-confidence-followup (backlog mode)
**Date:** 2026-05-26
**Master row:** `docs/2026-05-26-decision-confidence-followup/MASTER-SPEC.md` §002

## Goal

Wire an AkShare premium-to-NAV fetcher into the scoring pass so QDII feeder ETFs that today block on `qdii_premium_unknown` are scored against a real number. Block only when premium exceeds a configurable threshold (`qdii_max_premium_pct`) OR when fetch returned no data. The 3 on-exchange QDII ETFs in today's blocked bucket (159691, 513690, 513650) become actionable when their premium is healthy; the 5 off-exchange feeders (517641, 019172, 161716, 016452, 019547) are unblocked structurally because off-exchange units transact at NAV by construction — they get `qdii_premium_pct=0.0` injected in the scoring pass so the existing gate accepts them.

## Acceptance criteria

Each criterion is independently testable.

1. **AC1 — Pure adapter call signature.** `fetch_qdii_premium_pct(symbol: str) -> float | None` exists in `src/irc/data/akshare_client.py`. Returns a `float` in **ratio units** (e.g. `0.0292` for 2.92% premium) when AkShare returns a row for the symbol, `None` otherwise. The float represents **premium** (positive = above NAV); it is computed as `-(基金折价率 / 100.0)` so that the sign convention matches everywhere downstream.
2. **AC2 — Bulk-fetch indirection.** The adapter dispatches through a single bulk-table call (`ak.fund_etf_spot_em()`) that is memoised at module scope via `lru_cache` keyed on `()`. The decorated helper `_fetch_full_etf_spot_table()` is the only function that calls `_ak_call("fund_etf_spot_em")`. Per-symbol lookups read from the cached table — at most ONE AkShare call per pipeline run regardless of how many QDII symbols ask.
3. **AC3 — Column resilience.** The adapter requires `代码` and `基金折价率` columns. Missing either column → return `None` for the symbol (degrade-to-None per `fetch_fund_nav_report`'s contract). Tested with a fixture that simulates AkShare schema drift.
4. **AC4 — Symbol normalisation.** Input symbol is matched against the `代码` column after stripping whitespace and zero-padding to 6 digits — mirrors `_normalize_fund_code` in the existing client. Symbols not present in the table → `None`.
5. **AC5 — Off-exchange synthetic value.** A pure helper `qdii_premium_for_row(asset_class: str, market: str, fetcher: Callable[[str], float | None], symbol: str) -> float | None` lives in `src/irc/scoring/qdii_premium.py`. Behaviour: (a) `asset_class ∉ {"us_etf","hk_etf","qdii_global"}` → returns `None` (non-QDII rows must not stamp this field); (b) `asset_class ∈ QDII` AND `market == "cn_off_exchange"` → returns `0.0` (off-exchange feeders transact at NAV; the secondary-market premium concept does not apply); (c) otherwise → returns `fetcher(symbol)`.
6. **AC6 — Scoring wire-in.** `src/irc/scoring/pipeline.py::run_scoring` accepts an optional `qdii_premium_resolver: Callable[[str], float | None] | None = None` parameter. When provided AND the watchlist row's `asset_class` is in `_QDII_ASSET_CLASSES`, the resolver is invoked once per QDII row and the result is set as `qdii_premium_pct` on the emitted score dict (key absent when value is `None`, matching the existing serialiser convention for empty scalar fields). The pipeline remains pure: it does not call AkShare directly.
7. **AC7 — Command-layer composition.** `src/irc/commands/score_cmd.py::run_score` builds the resolver by composing `qdii_premium_for_row` with `fetch_qdii_premium_pct` (curried over the watchlist row's `market` and `asset_class`) and passes it into `run_scoring`. AkShare calls live exclusively in the command layer (effects at edges).
8. **AC8 — New gap code `qdii_premium_too_high`.** `src/irc/decision/gates.py::compute_blocking_reasons` gains a new boolean parameter `qdii_premium_too_high: bool = False` (default False to preserve existing call sites). When `True`, `"qdii_premium_too_high"` is appended to `reasons`. The two QDII gap codes are mutually exclusive in any single call: the caller computes `qdii_premium_too_high = (asset_class ∈ QDII AND premium is not None AND premium > threshold AND action ∈ BUY_ACTIONS)` and `qdii_premium_unknown = (asset_class ∈ QDII AND premium is None AND action ∈ BUY_ACTIONS)`.
9. **AC9 — Threshold sourcing.** `config/discovery.yaml::hard_filters.qdii_max_premium_pct` exists with a default of `0.03` (3%). `src/irc/schemas/discovery.py::HardFilters` gains the field with `Field(default=0.03, ge=0, le=1)`. Threshold is in **ratio units** matching AC1's value units.
10. **AC10 — Gate consumes the new threshold.** `decide_row` (and its memo-stage twin in `commands/memo_cmd.py`) receives a `qdii_max_premium_pct: float` parameter and feeds the `qdii_premium_too_high` boolean into `compute_blocking_reasons`. Memo-stage twin (`_compute_decision_status_for_memo`) reads the threshold from the loaded `DiscoveryConfig` bundle, not a hardcoded constant.
11. **AC11 — Decision report labels.** `src/irc/decision/report.py::_BLOCKING_REASON_LABEL` and `_BLOCKING_REMEDIATION` gain entries for `qdii_premium_too_high`:
    - label: `"QDII premium-to-NAV above threshold"`
    - remediation: `"Premium is {premium_pct:.1%} (max {threshold:.1%}). Wait for the premium to normalise or use an alternative venue."` (the `{...}` are illustrative; the actual remediation string is static — the dynamic-format pattern is OUT of scope for V1).
12. **AC12 — Live AkShare test (double-gated).** `tests/data/test_akshare_client.py::test_fetch_qdii_premium_pct_live` exists with `pytest.mark.live_akshare` AND a module-level `pytest.mark.skipif(os.environ.get("IRC_RUN_LIVE_AKSHARE") != "1", reason=...)` guard. Asserts the adapter returns a float for at least one of `{159691, 513690, 513650}` and that the value is finite and within `(-1.0, 1.0)` (±100% sanity bound).
13. **AC13 — Unit-test fixture.** `tests/fixtures/akshare/fund_etf_spot_em.json` (column-shadow capture per CONTEXT.md "AkShare fixture") is loaded by `tests/data/test_akshare_client.py::test_fetch_qdii_premium_pct_uses_bulk_table` to assert: (a) one AkShare call regardless of how many symbols query; (b) sign-flip arithmetic (`-2.92` in `基金折价率` → `0.0292` in the adapter output); (c) missing-symbol returns `None`.
14. **AC14 — Scoring-level TDD.** `tests/scoring/test_qdii_premium.py` covers:
    - `qdii_premium_for_row` returns `None` for non-QDII rows.
    - `qdii_premium_for_row` returns `0.0` for `(us_etf, cn_off_exchange)` and `(hk_etf, cn_off_exchange)` and `(qdii_global, cn_off_exchange)` WITHOUT invoking the fetcher (stub raises if called).
    - `qdii_premium_for_row` invokes the fetcher for `(us_etf, cn_on_exchange)`, `(hk_etf, cn_on_exchange)`.
    - `run_scoring` stamps `qdii_premium_pct` on QDII rows and omits the key on non-QDII rows.
15. **AC15 — Gate-level TDD.** `tests/decision/test_gates.py` gains tests:
    - QDII row with `premium=0.10`, `threshold=0.03`, `buy_candidate` → `blocking_reasons` contains `"qdii_premium_too_high"` and NOT `"qdii_premium_unknown"`.
    - QDII row with `premium=0.01`, `threshold=0.03`, `buy_candidate` → `blocking_reasons` contains NEITHER code.
    - QDII row with `premium=None`, `buy_candidate` → existing `qdii_premium_unknown` path stays green (regression check).
    - Non-QDII row with arbitrary `premium` → neither code fires.
16. **AC16 — Fetch-budget bookkeeping.** The bulk-table call counts as exactly ONE AkShare call against `IRC_FETCH_BUDGET` per run, asserted via the existing `_AKSHARE_CALL_COUNTER`-style instrumentation if it exists; otherwise documented in the spec text and confirmed via the `lru_cache` decoration.
17. **AC17 — Three-section markdown rendering.** `tests/decision/test_three_section_markdown.py` gains a test analogous to the existing `test_qdii_premium_unknown_renders_in_blocked_section` that asserts a `qdii_premium_too_high` row surfaces in the blocked section with its label + remediation.
18. **AC18 — `config validate` passes.** `uv run irc config validate` succeeds after the change. Documented as a smoke step in the verification path.
19. **AC19 — CONTEXT.md addendum.** A new bullet under "Failure-mode + audit policy" (or "Active-fund fetch engine", as appropriate) defines `qdii_premium_too_high` as a peer of `qdii_premium_unknown`, pins the units (ratio, not percent), pins the off-exchange synthetic-zero policy, and pins the bulk-fetch + lru_cache contract.

## Non-goals

- **No premium time-series.** V1 fetches the single latest snapshot. Historical premium percentiles, rolling smoothing, or premium-volatility scoring is OUT of V1.
- **No FX-status leg.** The existing `qdii_premium_unknown` remediation mentions "premium / FX status" — V1 covers only the premium half. FX-conversion timing risk stays as a future addition.
- **No new `FundPremiumReport` dataclass.** The adapter returns a bare `float | None`; the existing `FundNavReport`-style snapshot dataclass shape would be over-engineering for a single scalar. Dataclass promotion is a V2 concern if time-series enters scope.
- **No new ADR.** This item lives as an addendum bullet to CONTEXT.md plus a sentence in ADR 0002 §5 cross-reference; the underlying fetch / gate semantics are already covered by ADR 0002 (fund-level fetch engine) and the existing `qdii_premium_unknown` precedent.
- **No new on-disk cache for premium values.** The `lru_cache` decoration is per-process and survives one CLI invocation, which is sufficient (premium is a scoring-pass input, scoring runs once per `irc run`). Cross-run premium snapshots are not needed.
- **No retry / proxy plumbing.** AkShare's `fund_etf_spot_em` is served from a CN-mainland host that does not need `IRC_HTTPS_PROXY` (mirrors the existing direct-call pattern for non-DXY AkShare endpoints). Transient failures bubble up as `None` per AC3 — retries are not exercised in V1.
- **No discovery-stage filter on premium.** The premium is consumed at the gate layer only; discovery (hard_filter / quality_filter) still admits QDII rows regardless of premium so the watchlist is stable across runs.

## Constraints

- **TDD enforced.** Each AC ships with its failing test first, then implementation. Module-level test files mirror source files: `src/irc/scoring/qdii_premium.py` → `tests/scoring/test_qdii_premium.py`; new code in `src/irc/data/akshare_client.py` → additions in `tests/data/test_akshare_client.py`.
- **Functional, immutable.** `qdii_premium_for_row` is pure — no module-level state, no I/O. The fetcher is the only effectful boundary. Scoring rows are dicts that the pipeline composes via spread / new-dict construction, never mutated in place.
- **Effects at edges.** AkShare calls live exclusively in `src/irc/data/akshare_client.py` (the adapter layer) and `src/irc/commands/score_cmd.py` (the command-layer composer). `src/irc/scoring/*` and `src/irc/decision/*` remain pure and unit-testable without mocks.
- **No mutation of frozen dataclasses.** Score rows are dicts (not dataclasses), so the constraint is structural — produce new dicts rather than mutating in place.
- **Live-test gate honoured.** New live test gets BOTH the `live_akshare` marker AND the `IRC_RUN_LIVE_AKSHARE` env-var skipif. Default `pytest` invocations skip silently.
- **Size budget.** New `qdii_premium.py` module < 60 LOC (single pure function + type alias). New adapter section in `akshare_client.py` < 40 LOC. No function exceeds 20 LOC.
- **Backward compatibility.** Existing call sites of `compute_blocking_reasons` and `decide_row` keep working without modification (new parameters have `False` / sentinel defaults). The new `qdii_premium_pct` key on the score dict is additive — older serialised `scoring.json` files still parse.
- **`基金概况` forbidden invariant preserved.** The new adapter calls `fund_etf_spot_em` only — does NOT touch `fund_open_fund_info_em(indicator="基金概况")`. The acceptance test that greps for `"基金概况"` in production code stays green.

## Open questions resolved during brainstorming

### Q1 — AkShare adapter shape (single float vs time-series vs dataclass)

**Resolved: (a) single latest `float` (ratio units).**

The gate logic in `decision/gates.py` reads `score.get("qdii_premium_pct")` as a scalar. There is no consumer in V1 that would benefit from a time-series or a percentile. A dataclass mirroring `FundNavReport` would add JSON-serialisation surface (`_premium_report_to_dict` / `_from_dict`) for zero gain — premium is a single scalar, not a series. Time-series promotion stays a V2 concern if rolling-percentile scoring enters scope.

**Rationale:** YAGNI; the simplest type that satisfies the consumer is correct.

### Q2 — Which AkShare column

**Resolved: `基金折价率` from `fund_etf_spot_em()`, NOT `溢价率` from `fund_etf_fund_info_em`.**

Empirical inspection (live AkShare 1.18.63):
- `fund_etf_fund_info_em(fund="513650")` returns NAV history columns `[净值日期, 单位净值, 累计净值, 日增长率, 申购状态, 赎回状态]` — NO premium/discount columns.
- `fund_etf_spot_em()` returns the bulk daily snapshot with columns including `代码`, `名称`, `最新价`, `IOPV实时估值`, `基金折价率`, ... — exactly the field needed.

The MASTER-SPEC's reference to `溢价率` / `折价率` on `fund_etf_fund_info_em` is factually incorrect. The spec corrects this.

**Sign convention:** `基金折价率` is the discount-from-NAV in percent units. Premium = `-(基金折价率) / 100.0`. Example: for `513650`, AkShare returns `-2.92` → 2.92% premium → ratio `0.0292`.

**Rationale:** Use what the API actually provides; match the existing client's pattern of normalising at the adapter boundary so downstream consumers see clean ratio units.

### Q3 — Where to populate `qdii_premium_pct` on the score row

**Resolved: (b) producer helper module — `src/irc/scoring/qdii_premium.py`.**

Three options were considered:
- (a) `score_cmd.py` direct — keeps everything in the command layer but tangles QDII-specific logic with generic score-row assembly.
- (b) producer helper — separates "which rows need premium" from "how to fetch premium" from "how to wire it into a score row". This is what the design picks.
- (c) snapshot cache (fundamentals-style) — over-engineered for a single scalar; the `lru_cache` on the bulk-table call already handles amortisation.

The chosen split:
- `src/irc/data/akshare_client.py::fetch_qdii_premium_pct` — bare effectful fetcher.
- `src/irc/scoring/qdii_premium.py::qdii_premium_for_row` — pure routing logic (QDII vs not, on-exchange vs off-exchange).
- `src/irc/commands/score_cmd.py` — composer (wires the two together and passes the resolver into `run_scoring`).
- `src/irc/scoring/pipeline.py::run_scoring` — pure consumer of the resolver.

**Rationale:** Single-responsibility per module; AkShare effects live only at the edge; the pure routing logic is unit-testable without mocks.

### Q4 — QDII identification

**Resolved: existing `_QDII_ASSET_CLASSES = {"us_etf", "hk_etf", "qdii_global"}` set (already defined in `decision/gates.py` line 15 and re-used by `commands/memo_cmd.py`).**

The set will be moved to a shared location — `src/irc/scoring/qdii_premium.py` becomes the new home and `decision/gates.py` / `commands/memo_cmd.py` import from it. No new asset-class introspection is needed (no `is_qdii` flag on rows).

The `market` field on the watchlist row (`cn_on_exchange` vs `cn_off_exchange`) determines whether the fetcher runs vs the synthetic-zero path applies. Both fields are already on the discovered_watchlist.csv schema (header inspected: `instrument_id,ticker,market,name_cn,asset_class,...`).

**Rationale:** Reuse the existing canonical set; don't auto-fetch for non-QDII rows.

### Q5 — Threshold semantics

**Resolved: ratio units, `>` comparison (strict-greater-than blocks).**

`qdii_max_premium_pct: float = 0.03` in `config/discovery.yaml` and `HardFilters`. Comparison: `premium > qdii_max_premium_pct` blocks. A fund sitting exactly at 3.0% premium is accepted (`>=` would reject the boundary case; `>` admits it, matching the existing `FOREIGN_HEAVY_THRESHOLD` convention of accepting the boundary).

**Default value `0.03` rationale:** the MASTER-SPEC proposed `0.05`. Lowered to `0.03` based on the 3 on-exchange data points observed (`513650: -2.92%` discount = effectively no premium; `159691: 0.79%` premium; `513690: 0.22%` premium). All three are well under 3%, so the threshold is realistic for current market conditions while still leaving headroom for the 5–15% premium range CONTEXT.md flags as risky. The operator can tune via YAML.

**Rationale:** Match the units of the adapter output (ratio, not percent); strict-greater matches `FOREIGN_HEAVY_THRESHOLD` precedent.

### Q6 — Failure modes

**Resolved: degrade-to-None at every layer.**

- AkShare exception → `_ak_call` raises → adapter catches and returns `None`.
- Empty DataFrame → `None`.
- Required column missing (schema drift) → `None`.
- Symbol not in table → `None`.
- Adapter returns `None` → score row's `qdii_premium_pct` is `None` (key omitted).
- Gate sees `None` → `qdii_premium_unknown` path fires (existing behaviour, unchanged).

The new code `qdii_premium_too_high` ONLY fires when the adapter returned a real number AND that number exceeds the threshold. The two codes are mutually exclusive in any single call.

**Rationale:** Mirrors `fetch_fund_nav_report`'s degrade-to-None contract (ADR 0002 §5). The existing `qdii_premium_unknown` plumbing handles the "no premium known" branch — no new behaviour needed there.

### Q7 — New rejection reason `qdii_premium_too_high`

**Resolved: YES, separate code from `qdii_premium_unknown`.**

The two carry distinct operator semantics:
- `qdii_premium_unknown` → "we don't have the data; fetch it" (remediation: refresh the snapshot).
- `qdii_premium_too_high` → "we have the data; the market itself is unfavourable" (remediation: wait or use an alternative venue).

A reader of `decision_report.md` needs to distinguish these to take the right action. Conflating them would lose audit signal.

**Rationale:** Operator action diverges → distinct code (mirrors the item 001 precedent for distinguishing `foreign_heavy_evidence_missing` from generic `incomplete_constituent_data`).

### Q8 — AkShare call budget

**Resolved: +1 call per `irc run` (not +N).**

The bulk-table indirection (`lru_cache(maxsize=1)` on `_fetch_full_etf_spot_table()`) means ALL QDII symbols share a single AkShare call. Today's universe has ~30 QDII candidates; tomorrow's could have 100; the budget delta is unchanged: +1.

`IRC_FETCH_BUDGET=2000` has ample headroom. No preflight contract change needed (item 001 precedent: ADR 0003 §7 "Fetch budget impact" sub-bullet documented +2 calls × ~50 active funds = ~100 with no preflight change).

**Rationale:** Empirical headroom + bulk-fetch design.

### Q9 — Live test gate

**Resolved: paired `pytest.mark.live_akshare` AND `IRC_RUN_LIVE_AKSHARE=1` env-var.**

Module-level marker and module-level `skipif(os.environ.get("IRC_RUN_LIVE_AKSHARE") != "1", reason=...)` block — exact same pattern as `tests/fundamentals/test_fund_announcement_em_live.py:36–48` (CONTEXT.md "Live test gate" canonical pattern).

**Rationale:** Project convention; double-gated so default `pytest` invocations skip silently and CI must opt in explicitly.

### Q10 — ADR impact

**Resolved: no new ADR; CONTEXT.md addendum + a one-sentence ADR 0002 §5 cross-reference.**

The new code `qdii_premium_too_high` is a peer of the existing `qdii_premium_unknown` code, governed by the same gate (`compute_blocking_reasons`). The fetch semantics (bulk-table + lru_cache + degrade-to-None) are already covered by ADR 0002's fund-level fetch principles. Promoting this to a new ADR would inflate the decision log without new architectural ground.

CONTEXT.md gains a new bullet under "Failure-mode + audit policy" (mirroring the existing `qdii_premium_unknown` entry's neighbourhood) defining the new code and pinning units / off-exchange-synthetic-zero policy.

ADR 0002 §5 gains a one-sentence cross-reference noting that the QDII premium fetcher follows the same fund-level fetch pattern (bulk + lru_cache + degrade-to-None) used by `_build_fund_level_snapshot`.

**Rationale:** Match the documentation surface to the architectural delta. New code = new bullet, not new ADR.

## Files touched (summary)

| Path | Change |
|---|---|
| `src/irc/data/akshare_client.py` | Add `fetch_qdii_premium_pct` + `_fetch_full_etf_spot_table` + lru_cache + `_QDII_PREMIUM_HANDLER` registration (parallel to `_AKSHARE_MACRO_HANDLERS`). |
| `src/irc/scoring/qdii_premium.py` | NEW. Pure `qdii_premium_for_row` + shared `_QDII_ASSET_CLASSES` constant. |
| `src/irc/scoring/pipeline.py` | Accept `qdii_premium_resolver` parameter; stamp `qdii_premium_pct` on QDII rows. |
| `src/irc/commands/score_cmd.py` | Build resolver from fetcher + routing helper; pass into `run_scoring`. |
| `src/irc/decision/gates.py` | Add `qdii_premium_too_high` parameter and `decide_row` threshold parameter; import `_QDII_ASSET_CLASSES` from the new module. |
| `src/irc/commands/memo_cmd.py` | Mirror the gate update; read threshold from `DiscoveryConfig` bundle. |
| `src/irc/decision/report.py` | Add label + remediation for `qdii_premium_too_high`. |
| `src/irc/schemas/discovery.py` | Add `qdii_max_premium_pct: float = Field(default=0.03, ge=0, le=1)` to `HardFilters`. |
| `config/discovery.yaml` | Add `qdii_max_premium_pct: 0.03` under `hard_filters`. |
| `tests/data/test_akshare_client.py` | New tests: bulk-table contract, sign-flip arithmetic, missing-symbol, live double-gated. |
| `tests/scoring/test_qdii_premium.py` | NEW. Pure-function tests for routing helper. |
| `tests/decision/test_gates.py` | Add tests for `qdii_premium_too_high` path. |
| `tests/decision/test_three_section_markdown.py` | Add test asserting `qdii_premium_too_high` renders in the blocked section. |
| `tests/fixtures/akshare/fund_etf_spot_em.json` | NEW column-shadow fixture for the bulk table. |
| `CONTEXT.md` | Add bullet under "Failure-mode + audit policy" for `qdii_premium_too_high`. |
| `docs/adr/0002-active-fund-fetch-engine.md` | Add one-sentence cross-reference in §5. |

## Verification plan

1. `uv run pytest tests/data/test_akshare_client.py tests/scoring/test_qdii_premium.py tests/decision/test_gates.py tests/decision/test_three_section_markdown.py -x` — all green.
2. `uv run pytest` — full suite green (no regression).
3. `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare tests/data/test_akshare_client.py::test_fetch_qdii_premium_pct_live` — live test green.
4. `uv run irc config validate` — passes.
5. `uv run irc run --only score` (after `irc run --only discover`) on today's universe — `outputs/<date>/scoring.json` contains `qdii_premium_pct` for the 3 on-exchange QDII rows and `0.0` for the 5 off-exchange feeders.
6. `uv run irc decision` — `decision_report.md` shows the 8 previously-blocked QDII rows in the actionable section (assuming premium ≤ 3%), with the blocked section reduced.
7. `uv run ruff check src tests` — passes.
