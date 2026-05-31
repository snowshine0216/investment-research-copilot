# Item 003 — Pluggable CN data layer + Tushare fallback

> Run: `funding-analysis` · Source: `docs/funding-analysis-review.md` → "## Recommended changes" #3
> Status: spec · Authored 2026-05-31 (autonomous run, no user — decisions made and recorded below)
> Depends on: 001 + 004 (sequenced AFTER both per `dependency-scan.md` so the provider seam wraps REAL CN call-sites, not speculative ones). This spec includes an explicit, behavior-preserving "migrate 001/004 fetchers behind the provider interface" step.

## Goal

IRC's CN fundamentals are single-sourced on AkShare→EastMoney with no fallback (US/HK have OpenBB; CN does not), and the `tushare_token` `SecretStr` is a declared-but-unused stub (`settings.py:42`). This item introduces a **provider-agnostic CN fundamentals fetch interface** — a `Protocol` whose three methods mirror exactly the CN fetchers items 001/004 already use (filing digest, broker reports, index valuation) — with an `AkShareProvider` default that reproduces today's behavior byte-for-byte and an optional `TushareProvider` **fallback** that fills gaps the EastMoney feed structurally cannot (most valuably `BrokerReport.target_price`, which ADR 0009 records is dropped upstream by `stock_research_report_em`, so the already-wired `consensus_upside_pct` metric stays `None` today; a Tushare target-price feed activates it). The Tushare network boundary is isolated behind a thin `_tushare_call` edge (mirroring `_ak_call`) so the pure routing/fallback logic is unit-tested without network; a single double-gated live test pins the real Tushare shape. No new data fields are invented and no existing output changes when no token is configured.

## Context grounding (verified, not assumed)

- **`tushare_token` is a declared-but-unused `SecretStr`** at `src/irc/settings.py:42` (read confirmed). No production code references it. It stays `.env`-only.
- **The CN fetchers the seam must wrap (introduced/used by 001 + 004):**
  - 001: `fetch_cn_index_valuation(index_key) -> IndexValuation | None` (`fundamentals/akshare_index_valuation.py`), called at `opportunity/inputs_loader.py:105`.
  - 004 (rides on the active-fund engine): `fetch_cn_filing_digest(symbol) -> FilingDigest | None` and `fetch_cn_broker_reports(symbol, *, days, max_reports) -> tuple[BrokerReport, ...]` (`fundamentals/akshare_filing.py`), called at `fundamentals/snapshot.py:337,355` (active-fund) and `:595,600` (legacy `_build_cn_snapshot`). `_common_metric` / `_profitability_metric` (ROE, item 004) are private helpers of `fetch_cn_filing_digest` — they are NOT separate seam methods; they ride inside the `FilingDigest` the provider returns.
- **Each fetcher already obeys a degrade-to-None / empty contract via its own `_ak_call` indirection** (`akshare_filing.py:28`, `akshare_index_valuation.py:35`). The provider seam wraps these whole functions; it does not re-implement the parsing.
- **ADR 0009** records the honest-`None` contract: AkShare EastMoney drops 目标价, so `target_price` is `None` and `consensus_upside_pct` degrades to `None`. The ADR explicitly anticipates "item 003 Tushare" as the source that lands target prices. This is the single most valuable thing the fallback unlocks.
- **Live-test convention** (`pyproject.toml [tool.pytest.ini_options].markers`, `tests/fundamentals/test_index_valuation_live.py`): double-gated = `pytest.mark.<name>` marker AND `IRC_*=1` env var; `--strict-markers` is on, so a new marker MUST be registered.
- **Proxy policy** (`src/irc/http_proxy.py`, README "HTTPS proxy"): `IRC_HTTPS_PROXY` is applied only to LLM / web-search / Jina / DXY-via-EastMoney. Other AkShare CN calls stay direct "because most serve mainland-CN domains where a non-CN proxy hurts."
- **`基金概况` is forbidden** in production fetch code (CONTEXT.md "Static-profile invariant", ADR 0002 §5; grep-locked by `tests/fundamentals/test_static_profile_invariant.py`). None of the three seam methods touch fund static-profile; the invariant is unaffected.

## Interface shape (decided)

A `Protocol` (structural, no inheritance required) in a new module `src/irc/fundamentals/provider.py`:

```python
class CnFundamentalsProvider(Protocol):
    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None: ...
    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]: ...
    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None: ...
```

- **Reuses existing typed returns** — `FilingDigest`, `BrokerReport` (`fundamentals/types.py`), `IndexValuation` (`fundamentals/index_valuation_types.py`). **No new DTOs.**
- `AkShareProvider` (concrete) delegates each method verbatim to the existing module-level functions `fetch_cn_filing_digest` / `fetch_cn_broker_reports` / `fetch_cn_index_valuation`. Stateless.
- `TushareProvider(token: str)` (concrete) implements the same three methods against Tushare endpoints through a thin `_tushare_call(token, fn_name, **kwargs)` edge; parsing maps Tushare frames into the SAME three typed returns, degrading to `None`/`()` on any failure / empty / schema miss / missing token.
- `FallbackProvider(primary, secondary)` composes two providers per-method: call `primary`; if it raised OR returned a **miss** (`None` for digest/index, empty tuple for brokers) try `secondary`; if `secondary` also misses (or raises) return the primary's miss value. **Never raises** (degrade-to-None family, ADR 0009).
- `default_cn_provider() -> CnFundamentalsProvider` — the wiring factory at the I/O edge: returns `AkShareProvider()` when `Settings().tushare_token` is empty, else `FallbackProvider(AkShareProvider(), TushareProvider(token))`. **With no token the result is AkShare-only — byte-identical to today.**

## Acceptance criteria

Each is independently verifiable.

1. **Protocol defined.** `src/irc/fundamentals/provider.py` defines `CnFundamentalsProvider` (`typing.Protocol`, `@runtime_checkable`) with the three methods + signatures above, reusing `FilingDigest` / `BrokerReport` / `IndexValuation` — **no new return types**. A test asserts `AkShareProvider`, `TushareProvider`, and `FallbackProvider` each satisfy `isinstance(x, CnFundamentalsProvider)`.

2. **`AkShareProvider` reproduces current behavior exactly.** Each method delegates to the existing module function with identical arguments. A regression test stubs `_ak_call` (via the existing `akshare_filing._ak_call` / `akshare_index_valuation._ak_call` monkeypatch points) and asserts `AkShareProvider().fetch_filing_digest(s)` / `.fetch_broker_reports(s)` / `.fetch_index_valuation(k)` return objects **equal** to the direct function calls on the same stub. No DataFrame parsing is re-implemented in the provider layer.

3. **Tushare fallback path (pure routing, no network).** `FallbackProvider` is unit-tested with two in-memory fake providers (no network, no mocks of `tushare`): (a) primary hit → secondary never called, primary value returned; (b) primary miss (`None`/`()`) → secondary value returned; (c) primary raises → secondary value returned; (d) both miss → primary's miss value returned (`None` / `()`), and no exception propagates. A `target_price` case proves a Tushare-supplied `BrokerReport.target_price` flows through when AkShare returns `target_price=None`.

4. **Network mocked in unit tests.** `TushareProvider` performs all I/O through a single `_tushare_call(token, fn_name, **kwargs)` edge that does the local `import tushare`. Unit tests monkeypatch `_tushare_call` (or pass fixture frames) so they never import/hit `tushare`; they assert the frame→`FilingDigest`/`BrokerReport`/`IndexValuation` mapping and the degrade-to-`None`/`()` behavior on exception / empty / missing-column / empty-token. The pure mapping helpers are separate and unit-tested against fixture frames.

5. **Double-gated live Tushare test.** A new marker `live_tushare` is registered in `pyproject.toml`. A live test in `tests/fundamentals/test_tushare_provider_live.py` carries `pytest.mark.live_tushare` and is skipped unless **`IRC_RUN_LIVE_TUSHARE=1`** AND a non-empty `TUSHARE_TOKEN` is present. It asserts a real `TushareProvider(token).fetch_filing_digest("600519")` (or another known A-share) returns a `FilingDigest` of the expected shape (at least one of `revenue_yoy`/`net_income_yoy` non-`None`); a broker-reports smoke optionally asserts ≥0 reports with the field shape. Default `pytest` skips it.

6. **`tushare_token` wired from `.env`.** `default_cn_provider()` reads `Settings().tushare_token.get_secret_value()` and constructs `TushareProvider` only when non-empty; otherwise returns `AkShareProvider()`. A test with `tushare_token=""` asserts the returned provider is AkShare-only (e.g. `isinstance(p, AkShareProvider)` or a `FallbackProvider` flag absent), and with a token set asserts a `FallbackProvider` is returned. No token value appears in any YAML or log.

7. **001/004 call-sites migrated behavior-preservingly.** The four direct call-sites are routed through an injected provider:
   - `opportunity/inputs_loader.py::populate_inputs` and `::_index_valuation_metrics` gain a `provider: CnFundamentalsProvider` parameter (default `default_cn_provider()` resolved at the command edge, not at import) and call `provider.fetch_index_valuation(key)`.
   - `fundamentals/snapshot.py` active-fund path (`:337,355`) and legacy `_build_cn_snapshot` (`:595,600`) obtain the provider via an injected parameter (default the module default) and call `provider.fetch_filing_digest` / `provider.fetch_broker_reports`.
   A regression test runs the existing `tests/fundamentals` + `tests/opportunity` suites green with **no token configured**, and a targeted test asserts the migrated path with `AkShareProvider` produces output **byte-identical** to the pre-migration direct-call path on the same stubbed `_ak_call`.

8. **README updated (Tushare setup).** README "Environment setup" gains a `TUSHARE_TOKEN` row in the variables table and a short "Tushare fallback (optional)" subsection: install (`uv add tushare`), get a token at tushare.pro, set `TUSHARE_TOKEN=...` in `.env`, what it unlocks (CN filing-digest fallback + broker `target_price` → activates `consensus_upside_pct`), and the gated live-test command `IRC_RUN_LIVE_TUSHARE=1 uv run pytest -m live_tushare`. `tests/fundamentals/README-live-tests.md` gains a one-line pointer to the new marker/env.

9. **No `基金概况`.** No production code added by this item references the literal `基金概况`; `tests/fundamentals/test_static_profile_invariant.py` stays green (the new `provider.py` / `tushare_provider` modules are within its grep scope or explicitly added to it).

10. **No-network correctness + budget.** `uv run pytest tests/fundamentals tests/opportunity` passes offline; `uv run ruff check src tests` is clean. New files < 200 lines, new functions < 20 lines ideal (helpers extracted). The Tushare fallback fires only on a primary miss — it does NOT add unconditional calls to the per-run AkShare fetch budget (ADR 0002 §3); a Tushare call is not counted against `IRC_FETCH_BUDGET` (separate provider) but the fallback is gated on a miss so it cannot multiply the hot-path call count for cache-hit funds.

## Non-goals (explicit)

- **No trading.** No signals, backtests, ML factors, transaction-cost modeling, or point-in-time factor pipelines. Tushare's PIT-financials advantage is noted in the review as a *bonus* but is NOT built here — only the existing three fetch surfaces are abstracted. (Scope boundary: `ashare-quant` owns trading.)
- **No behavior change to existing outputs.** With no `TUSHARE_TOKEN`, every output is byte-identical to pre-003. The migration is a refactor (dependency injection), not a behavior change.
- **No NEW data fields fetched.** The seam abstracts the *existing* filing-digest, broker-reports, and index-valuation fetches. It does not add balance-sheet / cash-flow / EV-EBITDA / segments / screener surfaces. (`debt_equity`/`fcf_yield` on `KeyRatios` stay `None` per item 004 / ADR 0009.)
- **No global selectable-primary config knob.** Tushare is a per-method *fallback* (try AkShare, fill misses with Tushare), not a config-driven primary swap. No new YAML key; provider selection is implicit on token presence.
- **No new seam method beyond the three.** Holdings (`fetch_cn_etf_holdings`), NAV (`fetch_fund_nav_report`), announcements, news, and the QDII-premium fetch are governed by ADR 0002's engine and are out of scope — Tushare's value (filings + target price) maps onto the three chosen methods only.
- **No proxy routing for Tushare** — see Constraints. CN-direct, like other AkShare CN calls.
- **No `valuation_state` / classifier / `core_dca` change** (item 002), **no bull/bear debate** (item 005).

## Constraints

- **TDD.** Red→green→refactor; test file mirrors source (`provider.py` → `tests/fundamentals/test_provider.py`, etc.). Pure routing/mapping written test-first.
- **Purity / effects at edges.** `FallbackProvider` routing and all Tushare frame→DTO mapping are pure and unit-tested without mocks/network. Network I/O lives only in `_tushare_call` (local `import tushare`) and the existing `_ak_call` wrappers. `default_cn_provider()` (reads `Settings()`) is the construction edge — resolved in `commands/`, not at module import.
- **Immutability.** Providers are stateless (or hold only the immutable token). All returns are the existing frozen dataclasses. No argument mutation; no module-level mutable provider singleton.
- **Secrets in `.env` only.** `tushare_token` stays a `SecretStr` read via `get_secret_value()` at the edge; never inlined in YAML, never logged. No new config key.
- **Live tests double-gated.** New `live_tushare` marker (registered, `--strict-markers`) AND `IRC_RUN_LIVE_TUSHARE=1` AND a real `TUSHARE_TOKEN` — all three required to run; default `pytest` skips.
- **Proxy.** Tushare is mainland-CN (api.tushare.pro); it is called **direct**, NOT through `IRC_HTTPS_PROXY`, matching the "other AkShare CN calls stay direct" policy (`http_proxy.py`, README "HTTPS proxy"). No change to `http_proxy.py`.
- **Citation / gate invariants untouched.** This item moves *where* the existing three fetches are dispatched from; it emits no new `ThesisEvidence` and changes no `citation_id` preimage. The 16-hex citation-id format (ADR 0001), Policy B / `thesis_state` ownership (ADR 0003), dual-coverage gate, and H3 / SAME-3 invariants (ADR 0004) are structurally unaffected. A Tushare-supplied `BrokerReport.target_price` flows only into the numeric `consensus_upside_pct` scalar (ADR 0009), not into a citation.
- **Forbidden indicator.** `基金概况` is not referenced by any new production code (AC9).
- **Degrade-to-None.** Every provider method returns `None`/`()` on failure and never raises, matching `fetch_cn_filing_digest` and the `FallbackProvider` contract.
- **Size budget.** New files < 200 lines; functions < 20 lines ideal. If `tushare` parsing pushes `provider.py` over budget, split `tushare_provider.py` (Tushare impl + mapping helpers) from `provider.py` (Protocol + AkShare + Fallback + factory).

## Open questions resolved during brainstorming

1. **Interface shape — Protocol with three methods, or narrower/wider?** — **Decided: a 3-method `Protocol` (`fetch_filing_digest`, `fetch_broker_reports`, `fetch_index_valuation`) reusing the existing `FilingDigest`/`BrokerReport`/`IndexValuation` returns.** Rationale: these are exactly the CN-fundamentals seams 001/004 touch. Holdings/NAV/announcements/news are ADR 0002 engine surfaces and not what the review's "single-sourced CN data → add Tushare" point targets (Tushare's value is filings + broker target_price). A `Protocol` (vs ABC) needs no inheritance change to `AkShareProvider` and stays structural. No new DTOs keeps the seam minimal and avoids touching downstream consumers.

2. **Default vs fallback semantics.** — **Decided: per-method fallback (AkShare primary, Tushare fills misses), NOT a global selectable-primary.** A "miss" = `None` (digest/index) or `()` (brokers) or a primary exception. Both-miss → degrade-to-None/`()` (ADR 0009 family). Rationale: AkShare-first reproduces today's behavior exactly; Tushare only fills the documented gaps (most importantly the EastMoney-dropped `target_price`). A config-driven global primary swap is more surface for no V1 value and risks changing existing outputs. Provider selection is implicit on token presence — no YAML knob.

3. **How is the network isolated so unit tests never hit it?** — **Decided: a thin `_tushare_call(token, fn_name, **kwargs)` edge** (mirrors the proven `_ak_call` pattern) doing the local `import tushare` + `ts.pro_api(token)` + `getattr(pro, fn_name)(**kwargs)`. Unit tests monkeypatch `_tushare_call`; `FallbackProvider` is tested with in-memory fakes. Rationale: identical seam to `_ak_call`; keeps I/O at the edge (CLAUDE.md); no `tushare` import at module load.

4. **Live-test marker + env var names?** — **Decided: marker `live_tushare`, env var `IRC_RUN_LIVE_TUSHARE=1`, plus a real `TUSHARE_TOKEN`.** Asserts a real filing-digest fetch returns the expected shape. Rationale: mirrors `live_akshare`/`IRC_RUN_LIVE_AKSHARE` and `RUN_LIVE_LLM_TESTS` exactly; a distinct gate keeps the paid-credential cost opt-in and separate from the free AkShare live tests. Registered in `pyproject.toml` (`--strict-markers` requires it).

5. **Secrets.** — **Decided: `tushare_token` stays `.env`-only**, read via `Settings().tushare_token.get_secret_value()` at the construction edge; no YAML key, never logged. Rationale: project rule (secrets in `.env`, YAML references env names) + the stub is already a `SecretStr`.

6. **001/004 migration — which call-sites, how kept behavior-preserving?** — **Decided: route the four direct call-sites (`inputs_loader.py:105`; `snapshot.py:337,355,595,600`) through an injected `CnFundamentalsProvider` defaulting to `default_cn_provider()`.** With no token the default is AkShare-only and each method delegates verbatim to the existing function, so outputs are byte-identical (locked by an explicit byte-equality regression test on stubbed `_ak_call`). Rationale: dependency injection at the edge is the smallest behavior-preserving refactor; the dependency-scan demanded this be a visible, scoped step — it is (this AC + plan step).

7. **README content + location.** — **Decided: a `TUSHARE_TOKEN` table row + a "Tushare fallback (optional)" subsection under "Environment setup"** (alongside the EDGAR/OpenBB optional keys), covering install, token, `.env`, what it unlocks, and the gated live-test command; plus a one-line pointer in `tests/fundamentals/README-live-tests.md`. Rationale: user explicitly asked for README docs; matches the existing optional-provider documentation pattern.

8. **Proxy — does Tushare need `IRC_HTTPS_PROXY`?** — **Decided: NO — Tushare is called direct.** Rationale: api.tushare.pro is a mainland-CN service, the same domain class as the AkShare CN calls that the README/`http_proxy.py` explicitly keep direct ("a non-CN proxy hurts"). Only LLM/web/Jina/DXY-via-EastMoney are proxied. No `http_proxy.py` change.

## Could-not-fully-resolve (grill targets)

1. **Exact Tushare endpoint names + token-permission tier.** The Tushare Pro endpoints for (a) CN filing financials (likely `fina_indicator` / `income` / `balancesheet`), (b) broker target prices (`report_rc` or similar), and (c) index valuation (`index_dailybasic`) — and their exact column labels — are not pinned without a live token + response. The free Tushare tier gates many endpoints behind a points threshold, so the broker-target-price feed that justifies the fallback may require a paid tier. **Mitigation, not a blocker:** the mapping helpers are written defensively against candidate column sets (same approach as `_PE_COLS`/`_PB_COLS` in `akshare_index_valuation.py`), and the single double-gated live test is the designed pin point. If the token tier cannot reach `target_price`, the fallback still adds the CN filing-digest redundancy the review asked for, and `consensus_upside_pct` simply stays `None` (ADR 0009 unchanged). Grill should confirm the minimum viable endpoint set and whether to scope the live test to filing-digest only.

2. **Does the active-fund FetchPlan / budget ledger (ADR 0002 §3) need to account for fallback Tushare calls?** The preflight budget counts AkShare calls; a Tushare fallback fires only on a per-constituent AkShare miss, so worst-case it doubles the *miss* count, not the total. Whether `IRC_FETCH_BUDGET` should gain a Tushare sub-ledger or stay AkShare-only is a judgment call. **Recommendation:** keep the budget AkShare-only in V1 (fallback is miss-gated and Tushare is a separate provider with its own rate limits); revisit if Tushare becomes primary. Grill should confirm this does not violate the preflight-abort invariant.

3. **Provider injection threading depth.** `populate_inputs` is called from `opportunity_cmd.py`; the active-fund `_build_*` chain in `snapshot.py` is several frames deep. Whether the provider is threaded as an explicit parameter all the way down, or resolved once at the command edge and passed as a single argument, affects how many signatures change. **Recommendation:** resolve `default_cn_provider()` once at each command edge (`opportunity_cmd`, `memo_cmd` if it builds inputs) and thread it as one parameter; default-arg `default_cn_provider()` only at the outermost public function to keep existing tests calling the inner functions valid. Grill/plan should pin the exact signature set to stay within the size budget and avoid a sprawling diff.
