# Fundamentals diagnostics + evidence_gaps refinement

**Date:** 2026-05-16
**Branch:** feat/evidence-wiring-and-memo-enrichment
**Scope:** Fix two noisy classes of `ConstituentSnapshot` errors (`cn_index 399006 returned no constituents`, bulk `missing filing digest: <SYMBOL>`) and clean up the meaning of `OpportunityRow.evidence_gaps` so the report distinguishes "not applicable", "fetch failed", and "structurally missing".

**Out of scope (deferred):**
- Expanding `_TARGET_REGISTRY` to HK QDII, US extras (道琼斯, 美国50), and CN sector themes.
- Pulling 588000 / 588080 (科创50 ETFs) through discovery → scoring so the orphaned `data/fundamentals/2026Q1/科创50.json` snapshot actually gets consumed.
- Memo / template surface changes to render the new gap labels distinctly.

---

## Problem

Three concrete symptoms in `outputs/2026-05-16/`:

1. `data/fundamentals/2026Q1/创业板.json` reports `cn_index 399006 returned no constituents`. Root cause: `fetch_cn_index_constituents` calls AkShare's `index_stock_cons_weight_csindex`, which only covers indices published by 中证指数公司 (codes 000xxx / 930xxx / 000688). `399006` is a Shenzhen Stock Exchange index — CSI does not publish its weights — so the call returns an empty DataFrame and the snapshot orchestrator records a single generic failure reason. The same will affect any future `399xxx` registration (`创业板50 = 399673`, `深证成指 = 399001`).
2. `data/fundamentals/2026Q1/纳斯达克100.json` has `filings: []` and 10 lines of `missing filing digest: <SYMBOL>`. The SEC EDGAR adapter requires `EDGAR_CONTACT_EMAIL`; `.env.example` ships with it empty. With no email, SEC's fair-use policy rate-limits or blocks the request and `_fetch_json` returns `None` for every symbol. The current single error string loses the actual cause (HTTP 403 vs. CIK miss vs. network error).
3. `opportunity_report.json` rows for `gold`, `cn_bond_fund`, `cn_equity_fund` (主动权益), and the broken QDII targets all carry `evidence_gaps: ["missing_constituent_snapshot"]`. For gold / bond / active funds this is structurally not applicable (the asset class has no equity-style top-N constituents); for QDII US it is a real fetch failure (cause is symptom 2); for unregistered targets it means the target is unknown to `_TARGET_REGISTRY`. The same label covers all three semantically different conditions, so reviewers cannot tell from the report which rows are unfixable, fixable by setting an env var, or fixable by adding a target spec.

Additionally, `compose_opportunity_state` emits a generic `"证据不完整或信号不一致，列入小仓位观察。"` reason for the catch-all `small_watch` branch, hiding which sub-state caused the row to land there.

## Goals

- Concrete fix for `399006` (and any other SZSE-prefixed index code) so `创业板.json` is populated.
- EDGAR adapter surfaces an actionable cause when fetches fail; a single human-readable warning fires when `EDGAR_CONTACT_EMAIL` is missing instead of ten silent timeouts.
- `evidence_gaps` distinguishes `constituent_not_applicable`, `constituent_fetch_failed`, and `constituent_missing` so the report's gap stream is interpretable, without breaking the legacy `missing_constituent_snapshot` consumers (`evals/opportunity/metrics.py`, existing tests, memo `evidence_pool`).
- Catch-all `small_watch` reason names the weakest sub-state.

## Non-goals

- Any registry expansion. Adding HK / sector / US-extra targets is a separate spec.
- Any change to upstream discovery / scoring filters that currently exclude 科创50 ETFs from `scoring.json`.
- Schema migration of `evidence_gaps` (it stays `tuple[str, ...]`).
- Hard-failing on missing `EDGAR_CONTACT_EMAIL`. Cached snapshots must continue to load on machines that have never set the variable.

## Design

### 1. SZSE-aware fallback in `fetch_cn_index_constituents`

File: `src/irc/fundamentals/akshare_fundamentals.py`.

```
fetch_cn_index_constituents(index_code, top_n=10):
    1. df = _ak_call("index_stock_cons_weight_csindex", symbol=index_code)
       parse to weighted Constituent tuple — current behavior.
    2. If result is empty:
       df = _ak_call("index_stock_cons_sina", symbol=_sina_symbol(index_code))
       returns columns "品种代码", "品种名称" with NO weight.
       Convert to Constituent with weight=0.0 (equal-weight contract).
       Truncate to top_n by listing order.
    3. If still empty, return ().
```

`_sina_symbol(code)`:
- Leading `"6"` or `"5"` → `f"sh{code}"`.
- Leading `"3"` or `"0"` → `f"sz{code}"`.
- Other → fall through; sina call may still succeed for a few special tickers, otherwise empty.

Equal-weight is acceptable downstream: `thesis_evidence._yoy_split` and `_broker_consensus` count positive / negative signs across constituents and do not multiply by weight, so a Sina-sourced unweighted top-10 produces the same `thesis_state` classification it would with CSI weights. Document this contract in the docstring.

Failure-reason text stays the same (`cn_index {code} returned no constituents`) for the final empty case so existing tests that string-match on it keep working.

### 2. EDGAR adapter — setup warning + typed per-symbol error code

File: `src/irc/fundamentals/edgar_client.py`.

- Module-level constants: `_ERROR_MISSING_EMAIL = "missing_email"`, `_ERROR_HTTP_4XX = "http_4xx"`, `_ERROR_HTTP_5XX = "http_5xx"`, `_ERROR_NETWORK = "network"`, `_ERROR_DECODE = "decode"`, `_ERROR_CIK_MISS = "cik_not_found"`.
- Module-level sentinel `_warned_missing_email: bool = False`. The first call to `fetch_us_filing_digest` with `_EDGAR_CONTACT == ""` flips the sentinel to `True` and prints a single stderr line (using `print(..., file=sys.stderr)` to match the rest of the codebase, which doesn't use the `logging` module). Subsequent calls stay silent.
- `_fetch_json(url, timeout_s)` returns `tuple[Any | None, str | None]`:
  - SSRF guard failure → `(None, _ERROR_NETWORK)`.
  - `httpx.HTTPError` → `(None, _ERROR_NETWORK)`.
  - `resp.status_code >= 500` → `(None, _ERROR_HTTP_5XX)`.
  - `resp.status_code >= 400` → `(None, _ERROR_HTTP_4XX)`.
  - JSON decode failure → `(None, _ERROR_DECODE)`.
  - Success → `(payload, None)`.
- `_lookup_cik` returns `tuple[str | None, str | None]` so the caller can distinguish a network failure from a genuine "ticker not in SEC table".
- `fetch_us_filing_digest(symbol)` keeps its current return type `FilingDigest | None` (callers in `snapshot.py` need no signature break), but on `None` paths it stores the error code on a `contextvars.ContextVar[str | None]` named `_LAST_ERROR_CODE`. Snapshot orchestrator reads this immediately after each per-symbol call. This is the lightest-weight way to thread the diagnostic without changing the public function's return tuple shape, which would ripple into HK and CN siblings.
  - Alternative considered: introduce `fetch_us_filing_digest_diag` returning `(FilingDigest | None, str | None)` and keep `fetch_us_filing_digest` as a thin wrapper. Either is acceptable; the implementation step will pick based on whichever produces simpler tests. The spec does not constrain it further.

File: `src/irc/fundamentals/snapshot.py:_build_us_snapshot`.

- After each `fetch_us_filing_digest(symbol)` returning `None`, read the error code and append `f"missing filing digest: {symbol} ({code})"` to `failures`. When the code is `None` (defensive — shouldn't happen), fall back to today's `f"missing filing digest: {symbol}"`.
- If every symbol failed and every code is identical, append one extra summary line: `f"all US fetches failed: {code}"`.

The `"missing filing digest: "` prefix is preserved so existing string-matching tests keep working.

### 3. Refined `evidence_gaps` labels + weak-link reason

File: `src/irc/opportunity/thesis_evidence.py`.

- New helper:
  ```
  _classify_constituent_gap(snapshot, asset_class) -> str | None:
      if asset_class in {"gold", "cn_bond_fund"}: return "constituent_not_applicable"
      if asset_class == "cn_equity_fund": return "constituent_not_applicable"
      if snapshot is None: return "constituent_missing"
      if not snapshot.filings: return "constituent_fetch_failed"
      return None
  ```
- `derive_thesis_from_evidence(snapshot, theme_report)` signature is extended to `derive_thesis_from_evidence(snapshot, theme_report, *, asset_class: str | None = None)`. When `asset_class` is supplied, the refined label is appended to `gaps` in addition to (not instead of) `missing_constituent_snapshot`. When omitted, behavior is identical to today (backward compatible for any other caller).
- Existing emission of `"missing_constituent_snapshot"` stays exactly as today. The `evals/opportunity/metrics.py:visible_gaps` count (which only checks truthiness of the list) is unaffected.

File: `src/irc/opportunity/states.py`.

- `build_opportunity_row` passes `inp.asset_class` through to `derive_thesis_from_evidence`.
- In the table-fallback branch (no snapshot, no theme_report), `thesis_gaps` becomes `("missing_constituent_snapshot", "missing_recent_news", _classify_constituent_gap(None, inp.asset_class))` filtered for `None`.
- `compose_opportunity_state` learns about the weakest sub-state. The catch-all branch becomes:
  ```
  reason = (
      f"证据不完整或信号不一致（{_weak_link_label(valuation, heat, thesis, product_quality)}），"
      "列入小仓位观察。"
  )
  ```
  where `_weak_link_label` returns one of: `"产品质量薄弱"`, `"主题逻辑证据不足"`, `"估值数据缺失"`, `"热度信号不足"`, `"信号方向冲突"` (last is the default when no single sub-state stands out). The label is appended inside parentheses so the trailing `"列入小仓位观察。"` is preserved and any downstream string match on that tail keeps working.

`OpportunityRow` schema is unchanged. Downstream consumers (`memo/evidence_pool.py`, `report.py`, `cards.py`) receive the longer gap list and the longer reason string transparently.

### Data flow

```
build_snapshot(target)
  └─> fetch_cn_index_constituents(code, top_n)         # §1: CSI then Sina fallback
      └─> Constituent tuple (with weight=0.0 from sina path)
  └─> for c in constituents: fetch_cn_filing_digest(c.symbol)
build_snapshot(qdii_us_target)
  └─> _build_us_snapshot(target, spec, ts)
      └─> for s in spec.symbols: fetch_us_filing_digest(s)   # §2: typed error code
      └─> failures: f"missing filing digest: {s} ({code})"

run_opportunity
  └─> for each scored instrument:
        snap = load_latest_cached_snapshot(target.display_cn, root/data)
        row = build_opportunity_row(inp, theme_thesis, snapshot=snap, theme_report=tr)
              └─> derive_thesis_from_evidence(snap, tr, asset_class=inp.asset_class)   # §3
              └─> compose_opportunity_state(...)                                       # §3 reason
        evidence_gaps now contains the legacy label PLUS the refined label.
```

### Error handling

- Every new failure code is a string constant; nothing raises. `failure_reasons` and `evidence_gaps` remain `tuple[str, ...]`.
- The "warn once on missing email" sentinel is module-level state — acceptable here because `print(..., file=sys.stderr)` is an I/O side effect concentrated at the EDGAR boundary, not inside the pure-function classifiers.
- Mutation of `_warned_missing_email` is the only piece of mutable module state introduced; consider this exception to the global "no mutable module state" rule and document it inline.

### Testing

New / extended tests:

- `tests/fundamentals/test_akshare_fundamentals.py` (extend):
  - Stub `_ak_call` so CSI returns empty for `399006`; assert the second call goes to `index_stock_cons_sina` with `symbol="sz399006"`; assert returned constituents have `weight == 0.0`.
  - Stub both calls to return empty; assert `()` result (existing behavior).
- `tests/fundamentals/test_edgar_client.py` (new):
  - Stub `httpx.get` to return 403; assert `_fetch_json` returns `(None, "http_4xx")`.
  - Set `EDGAR_CONTACT_EMAIL = ""` and capture stderr; first call prints exactly one warning, second call is silent.
  - Stub network failure; assert `(None, "network")`.
- `tests/fundamentals/test_snapshot.py` (extend or create):
  - Build a US snapshot with all symbols failing on `http_4xx`; assert `failure_reasons` contains per-symbol entries and one trailing `"all US fetches failed: http_4xx"`.
- `tests/opportunity/test_thesis_evidence.py` (extend):
  - `asset_class="gold"`, `snapshot=None` → gaps contain BOTH `"missing_constituent_snapshot"` and `"constituent_not_applicable"`.
  - `asset_class="cn_etf"`, snapshot present with `filings=()` → gaps contain `"missing_constituent_snapshot"` and `"constituent_fetch_failed"`.
  - `asset_class="cn_etf"`, snapshot=None → `"constituent_missing"`.
  - `asset_class="cn_etf"`, snapshot present with filings populated → neither refined label.
  - Default-arg case (no `asset_class`) behaves identically to today (regression guard).
- `tests/opportunity/test_states.py` (extend):
  - Inputs that drive the catch-all `small_watch` branch with `product_quality="weak"` → reason contains `"产品质量薄弱"` and the trailing `"列入小仓位观察。"`.

Existing tests that match on `"missing_constituent_snapshot"` or on the trailing `"列入小仓位观察。"` substring must keep passing without modification.

Manual smoke (one-time, not automated):
- `irc fundamentals --target 创业板` → `data/fundamentals/2026Q1/创业板.json` shows non-empty `constituents` and per-symbol filing fetch outcomes.
- `irc fundamentals --target 纳斯达克100` with `EDGAR_CONTACT_EMAIL` set → populated filings. With it unset → one stderr warning and `failure_reasons` tagged `(missing_email)` / `(http_4xx)`.

### Risks and trade-offs

- Sina's `index_stock_cons_sina` does not return weights. Equal-weighting top-10 is faithful to the thesis classifier (sign-counting), but a downstream change that starts to weight by `Constituent.weight` would silently get zeros from the Sina path. Mitigation: docstring + a comment at the call site flagging that `weight=0.0` is intentional for the Sina fallback.
- `contextvars.ContextVar` on EDGAR (if that variant is chosen) couples the per-symbol error code to call ordering. The snapshot orchestrator reads it immediately after each call on the same thread, which is safe today (`_build_us_snapshot` is sequential), but a future parallelisation across symbols would need to revisit. Alternative: introduce a typed return tuple now. Implementation can pick either; the spec does not lock it down. If implementation picks the tuple form, prefer the alternative tuple-returning fetcher to keep purity tighter.
- Adding two labels per row inflates `evidence_gaps` length, which `memo/evidence_pool` surfaces verbatim. The memo template currently lists gaps as-is; reviewers may see e.g. `missing_constituent_snapshot, constituent_not_applicable` side-by-side. Acceptable: the redundancy is the price of backward compatibility, and a future memo-template polish pass (out of scope) can collapse them.

### Acceptance criteria

- `data/fundamentals/2026Q1/创业板.json` rebuilt with non-empty `constituents`.
- `data/fundamentals/2026Q1/纳斯达克100.json` rebuilt with per-symbol failure tagged by error code (e.g. `(missing_email)` until the env var is set, then `(network)` / `(http_4xx)` / etc. as appropriate).
- `opportunity_report.json` rows for gold / cn_bond_fund / cn_equity_fund / unregistered targets carry both `missing_constituent_snapshot` and a refined label.
- Catch-all `small_watch` reason includes a parenthesised weak-link label.
- All existing tests pass without modification; new tests cover each refined label and the SZSE fallback path.
- `evals/architecture/metrics.py` (run via `pytest evals/`) reports no new failures.
