# Fundamentals diagnostics + evidence_gaps refinement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two noisy `ConstituentSnapshot` failure modes (CSI-only fetcher missing SZSE indices; silent EDGAR fetches when `EDGAR_CONTACT_EMAIL` is empty) and refine `OpportunityRow.evidence_gaps` so `gold` / `cn_bond_fund` / `cn_equity_fund` / unregistered targets are distinguishable from genuine fetch failures.

**Architecture:** Surgical edits to three modules (`akshare_fundamentals`, `edgar_client`, `snapshot`) plus two opportunity-layer modules (`thesis_evidence`, `states`). The legacy `missing_constituent_snapshot` label is preserved for backward compatibility and emitted alongside new refined labels. EDGAR errors are threaded through a typed-tuple sibling fetcher to keep the public single-value signature stable.

**Tech Stack:** Python 3.11+, AkShare (CSI + Sina), httpx + respx (SEC EDGAR), pytest, unittest.mock, monkeypatch.

**Source spec:** `docs/superpowers/specs/2026-05-16-fundamentals-diagnostics-design.md`.

**Working directory:** `/Users/snow/.codex/worktrees/6a85/investment-research-copilot`. All paths below are relative to this directory unless otherwise noted.

---

## File map

| Action | File | Responsibility |
|---|---|---|
| Modify | `src/irc/fundamentals/akshare_fundamentals.py` | Add SZSE Sina fallback to `fetch_cn_index_constituents`. |
| Modify | `src/irc/fundamentals/edgar_client.py` | Define typed error codes; add `fetch_us_filing_digest_diag` returning `(digest, error_code)`; keep `fetch_us_filing_digest` thin; warn once on empty `EDGAR_CONTACT_EMAIL`. |
| Modify | `src/irc/fundamentals/snapshot.py` | `_build_us_snapshot` reads typed error code per symbol; append summary line when all symbols share one cause. |
| Modify | `src/irc/opportunity/thesis_evidence.py` | New `_classify_constituent_gap`; `derive_thesis_from_evidence` takes optional `asset_class` kwarg. |
| Modify | `src/irc/opportunity/states.py` | Plumb `asset_class` into `derive_thesis_from_evidence`; teach `compose_opportunity_state` to embed a weak-link label in the catch-all `small_watch` reason. |
| Modify | `tests/fundamentals/test_akshare_fundamentals.py` | SZSE fallback test cases. |
| Modify | `tests/fundamentals/test_edgar_client.py` | Typed-error-code test cases + warn-once test. |
| Modify | `tests/fundamentals/test_snapshot.py` | US snapshot per-symbol error-tagged failure_reason test. |
| Modify | `tests/opportunity/test_thesis_evidence.py` | Refined-label test cases. |
| Modify | `tests/opportunity/test_states.py` | Weak-link label in catch-all reason. |

Tasks are ordered so each task's tests can run independently (TDD red → green → commit), then a final integration task wires the opportunity layer to the new fundamentals plumbing.

---

## Task 1: SZSE Sina fallback for `fetch_cn_index_constituents`

**Files:**
- Modify: `src/irc/fundamentals/akshare_fundamentals.py:41-65`
- Modify: `tests/fundamentals/test_akshare_fundamentals.py` (add tests after existing `fetch_cn_index_constituents` block)

- [ ] **Step 1: Write the failing tests (Sina fallback path)**

Append to `tests/fundamentals/test_akshare_fundamentals.py` (after the existing happy-path test for `fetch_cn_index_constituents`):

```python
# ---------- SZSE Sina fallback ----------

_SINA_SZ_FRAME = pd.DataFrame({
    "品种代码": ["300750", "300059", "300760", "300015"],
    "品种名称": ["宁德时代", "东方财富", "迈瑞医疗", "爱尔眼科"],
})


def test_fetch_cn_index_constituents_falls_back_to_sina_for_szse_code() -> None:
    """399006 (创业板指) is not published by CSI; Sina returns the constituent list
    without weights — we still return Constituent rows with weight=0.0 so the
    downstream thesis classifier (sign-counting) keeps working."""
    csi_empty = pd.DataFrame()
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = [csi_empty, _SINA_SZ_FRAME]
        out = fetch_cn_index_constituents("399006", top_n=3)
    assert mocked.call_args_list[0].kwargs == {"symbol": "399006"}
    assert mocked.call_args_list[1].kwargs == {"symbol": "sz399006"}
    assert len(out) == 3
    assert out[0] == Constituent(symbol="300750.SZ", name="宁德时代", weight=0.0, market="cn")
    assert out[2].name == "迈瑞医疗"


def test_fetch_cn_index_constituents_falls_back_to_sina_for_sh_code_when_csi_empty() -> None:
    """If CSI returns empty for a 6xxxxx code, try Sina with sh prefix."""
    sh_frame = pd.DataFrame({
        "品种代码": ["600519"],
        "品种名称": ["贵州茅台"],
    })
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = [pd.DataFrame(), sh_frame]
        out = fetch_cn_index_constituents("600000", top_n=1)
    assert mocked.call_args_list[1].kwargs == {"symbol": "sh600000"}
    assert out == (Constituent(symbol="600519.SH", name="贵州茅台", weight=0.0, market="cn"),)


def test_fetch_cn_index_constituents_returns_empty_when_both_paths_fail() -> None:
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = [pd.DataFrame(), pd.DataFrame()]
        out = fetch_cn_index_constituents("399006", top_n=5)
    assert out == ()


def test_fetch_cn_index_constituents_sina_exception_is_swallowed() -> None:
    """Sina endpoint failure must degrade to empty, never raise."""
    with patch("irc.fundamentals.akshare_fundamentals._ak_call") as mocked:
        mocked.side_effect = [pd.DataFrame(), RuntimeError("akshare down")]
        out = fetch_cn_index_constituents("399006", top_n=5)
    assert out == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_akshare_fundamentals.py -v -k "sina or both_paths"`
Expected: 4 failures (function does not yet fall back to Sina).

- [ ] **Step 3: Implement Sina fallback**

Replace `fetch_cn_index_constituents` in `src/irc/fundamentals/akshare_fundamentals.py` with the version below. Leave `_ak_call`, `_current_year`, `_suffix_for_code`, `_to_qualified_symbol`, and the `fetch_cn_etf_holdings` function untouched.

```python
def _sina_index_symbol(index_code: str) -> str | None:
    """Map a numeric CN index code to its Sina-prefixed symbol.

    Leading 6/5 → Shanghai (`sh`); leading 3/0 → Shenzhen (`sz`).
    Codes whose first character is not in {0,3,5,6} return None so the caller
    can short-circuit without an AkShare round-trip.
    """
    if not index_code:
        return None
    head = index_code[:1]
    if head in ("6", "5"):
        return f"sh{index_code}"
    if head in ("3", "0"):
        return f"sz{index_code}"
    return None


def _parse_csindex_frame(df: pd.DataFrame, top_n: int) -> tuple[Constituent, ...]:
    needed = {"成分券代码", "成分券名称", "权重"}
    if not needed.issubset(df.columns):
        return ()
    ranked = df.sort_values("权重", ascending=False).head(top_n)
    return tuple(
        Constituent(
            symbol=_to_qualified_symbol(str(row["成分券代码"])),
            name=str(row["成分券名称"]),
            weight=float(row["权重"]) / 100,
            market="cn",
        )
        for _, row in ranked.iterrows()
    )


def _parse_sina_frame(df: pd.DataFrame, top_n: int) -> tuple[Constituent, ...]:
    """Sina returns columns "品种代码" / "品种名称" with NO weight.

    Equal-weight (weight=0.0) is acceptable downstream: the thesis classifier
    counts YoY signs across constituents, never multiplies by weight.
    """
    needed = {"品种代码", "品种名称"}
    if not needed.issubset(df.columns):
        return ()
    head = df.head(top_n)
    return tuple(
        Constituent(
            symbol=_to_qualified_symbol(str(row["品种代码"])),
            name=str(row["品种名称"]),
            weight=0.0,
            market="cn",
        )
        for _, row in head.iterrows()
    )


def fetch_cn_index_constituents(
    index_code: str,
    *,
    top_n: int = 10,
) -> tuple[Constituent, ...]:
    """Top-N constituents of a CN index by weight.

    Primary source is CSI (`index_stock_cons_weight_csindex`), which only
    publishes 中证指数公司 indices (000xxx, 930xxx, 000688). For SZSE codes
    (399xxx) and any other code CSI does not cover, fall back to Sina
    (`index_stock_cons_sina`) and return equal-weight (weight=0.0) entries.
    """
    try:
        df = _ak_call("index_stock_cons_weight_csindex", symbol=index_code)
    except Exception:
        df = pd.DataFrame()
    if isinstance(df, pd.DataFrame) and not df.empty:
        parsed = _parse_csindex_frame(df, top_n)
        if parsed:
            return parsed
    sina_symbol = _sina_index_symbol(index_code)
    if sina_symbol is None:
        return ()
    try:
        df2 = _ak_call("index_stock_cons_sina", symbol=sina_symbol)
    except Exception:
        return ()
    if not isinstance(df2, pd.DataFrame) or df2.empty:
        return ()
    return _parse_sina_frame(df2, top_n)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_akshare_fundamentals.py -v`
Expected: all tests in that file pass (existing tests + the four new ones).

- [ ] **Step 5: Run full fundamentals + opportunity tests for regressions**

Run: `uv run pytest tests/fundamentals tests/opportunity -v`
Expected: PASS for everything. If any other test references `_to_qualified_symbol` or the CSI parsing path, verify it still passes — the helpers were factored but their behavior is unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/irc/fundamentals/akshare_fundamentals.py tests/fundamentals/test_akshare_fundamentals.py
git commit -m "feat(fundamentals): Sina fallback for SZSE index constituents

CSI's index_stock_cons_weight_csindex only covers 中证指数公司 indices
(000xxx, 930xxx). 399006 (创业板指) and other 399xxx codes return empty;
fall back to index_stock_cons_sina with sh/sz prefix. Equal-weight
(weight=0.0) is faithful to the sign-counting thesis classifier."
```

---

## Task 2: EDGAR typed error codes + warn-once on missing email

**Files:**
- Modify: `src/irc/fundamentals/edgar_client.py` (entire file)
- Modify: `tests/fundamentals/test_edgar_client.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/fundamentals/test_edgar_client.py`:

```python
# ---------- typed error codes via diag fetcher ----------

import os
import sys
import importlib

from irc.fundamentals import edgar_client as edgar_mod
from irc.fundamentals.edgar_client import (
    EDGAR_ERROR_MISSING_EMAIL,
    EDGAR_ERROR_HTTP_4XX,
    EDGAR_ERROR_HTTP_5XX,
    EDGAR_ERROR_NETWORK,
    EDGAR_ERROR_DECODE,
    EDGAR_ERROR_CIK_MISS,
    fetch_us_filing_digest_diag,
)


@respx.mock
def test_diag_returns_http_4xx_when_sec_blocks_request() -> None:
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(403, text="forbidden"))
    digest, code = fetch_us_filing_digest_diag("AAPL")
    assert digest is None
    assert code == EDGAR_ERROR_HTTP_4XX


@respx.mock
def test_diag_returns_http_5xx_when_sec_errors() -> None:
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(503))
    digest, code = fetch_us_filing_digest_diag("AAPL")
    assert digest is None
    assert code == EDGAR_ERROR_HTTP_5XX


@respx.mock
def test_diag_returns_network_when_request_raises() -> None:
    respx.get(_TICKERS_URL).mock(side_effect=httpx.ConnectError("boom"))
    digest, code = fetch_us_filing_digest_diag("AAPL")
    assert digest is None
    assert code == EDGAR_ERROR_NETWORK


@respx.mock
def test_diag_returns_cik_not_found_when_ticker_absent() -> None:
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(200, json=_tickers_payload()))
    digest, code = fetch_us_filing_digest_diag("ZZZZ")
    assert digest is None
    assert code == EDGAR_ERROR_CIK_MISS


@respx.mock
def test_diag_returns_decode_error_when_json_invalid() -> None:
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(200, text="not json"))
    digest, code = fetch_us_filing_digest_diag("AAPL")
    assert digest is None
    assert code == EDGAR_ERROR_DECODE


@respx.mock
def test_diag_happy_path_returns_digest_and_none_code() -> None:
    respx.get(_TICKERS_URL).mock(return_value=httpx.Response(200, json=_tickers_payload()))
    respx.get(_facts_url("0000320193")).mock(
        return_value=httpx.Response(200, json=_facts_payload())
    )
    digest, code = fetch_us_filing_digest_diag("AAPL")
    assert isinstance(digest, FilingDigest)
    assert code is None


def test_diag_reports_missing_email_without_network_call(monkeypatch) -> None:
    """When EDGAR_CONTACT_EMAIL is empty, short-circuit with missing_email."""
    monkeypatch.setattr(edgar_mod, "_EDGAR_CONTACT", "")
    monkeypatch.setattr(edgar_mod, "_warned_missing_email", False, raising=False)
    # Any httpx call would explode (no respx mock set), so a short-circuit is the
    # only way this test can pass.
    digest, code = fetch_us_filing_digest_diag("AAPL")
    assert digest is None
    assert code == EDGAR_ERROR_MISSING_EMAIL


def test_warn_missing_email_prints_once(monkeypatch, capsys) -> None:
    monkeypatch.setattr(edgar_mod, "_EDGAR_CONTACT", "")
    monkeypatch.setattr(edgar_mod, "_warned_missing_email", False, raising=False)
    fetch_us_filing_digest_diag("AAPL")
    first = capsys.readouterr().err
    fetch_us_filing_digest_diag("MSFT")
    second = capsys.readouterr().err
    assert "EDGAR_CONTACT_EMAIL" in first
    assert second == ""


def test_legacy_fetch_us_filing_digest_returns_digest_only(monkeypatch) -> None:
    """The legacy single-return signature is preserved for the snapshot orchestrator."""
    monkeypatch.setattr(edgar_mod, "_EDGAR_CONTACT", "")
    monkeypatch.setattr(edgar_mod, "_warned_missing_email", True, raising=False)
    result = fetch_us_filing_digest("AAPL")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_edgar_client.py -v -k "diag or missing_email or warn or legacy_fetch"`
Expected: import failures (`EDGAR_ERROR_MISSING_EMAIL`, `fetch_us_filing_digest_diag` etc. don't exist yet) → ImportError at collection time.

- [ ] **Step 3: Rewrite `edgar_client.py`**

Replace `src/irc/fundamentals/edgar_client.py` with the version below. Keep all existing functions (`_units_usd`, `_latest_periodic`, `_match_prior_year`, `_match_year`, `_fiscal_period`) but route them through the new diag fetcher.

```python
"""SEC EDGAR adapter.

Calls two JSON endpoints under data.sec.gov / www.sec.gov:
  - /files/company_tickers.json     — ticker → CIK
  - /api/xbrl/companyfacts/CIK*.json — XBRL facts (revenue, net income, cost)

SEC's fair-use policy requires a descriptive User-Agent. SSRF safety: hosts are
resolved with `verify_host_resolves_publicly` before any fetch.

Two public entry points:
  - fetch_us_filing_digest(symbol)             → FilingDigest | None  (legacy)
  - fetch_us_filing_digest_diag(symbol)        → (FilingDigest | None, error_code | None)

The diag variant lets callers (notably `snapshot._build_us_snapshot`) tag each
per-symbol failure with its cause. The legacy variant is a thin wrapper.
"""
from __future__ import annotations

import os
import sys
from typing import Any
from urllib.parse import urlparse

import httpx

from irc.fundamentals.types import FilingDigest
from irc.llm.http_client import verify_host_resolves_publicly


_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

EDGAR_ERROR_MISSING_EMAIL = "missing_email"
EDGAR_ERROR_HTTP_4XX = "http_4xx"
EDGAR_ERROR_HTTP_5XX = "http_5xx"
EDGAR_ERROR_NETWORK = "network"
EDGAR_ERROR_DECODE = "decode"
EDGAR_ERROR_CIK_MISS = "cik_not_found"

# SEC fair-use policy requires a valid contact email in the User-Agent.
_EDGAR_CONTACT = os.environ.get("EDGAR_CONTACT_EMAIL", "")
_USER_AGENT = (
    f"irc-research ({_EDGAR_CONTACT})"
    if _EDGAR_CONTACT
    else "irc-research (set EDGAR_CONTACT_EMAIL in .env)"
)

# Module-level sentinel: flip to True after the first warning so we don't
# spam stderr with one line per failed symbol. Mutation here is the only
# permitted module-level state in this file; see design doc.
_warned_missing_email: bool = False

_REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
)
_NET_INCOME_TAGS = ("NetIncomeLoss",)
_COST_TAGS = (
    "CostOfRevenue",
    "CostOfGoodsAndServicesSold",
    "CostOfGoodsSold",
)


def _maybe_warn_missing_email() -> None:
    global _warned_missing_email
    if _warned_missing_email:
        return
    _warned_missing_email = True
    print(
        "WARNING: EDGAR_CONTACT_EMAIL is empty — SEC may rate-limit or reject "
        "US filing fetches. Set it in .env.",
        file=sys.stderr,
    )


def _fetch_json(url: str, *, timeout_s: float = 15.0) -> tuple[Any | None, str | None]:
    host = urlparse(url).hostname
    if not host:
        return None, EDGAR_ERROR_NETWORK
    try:
        verify_host_resolves_publicly(host)
    except Exception:
        return None, EDGAR_ERROR_NETWORK
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        resp = httpx.get(url, headers=headers, timeout=timeout_s)
    except httpx.HTTPError:
        return None, EDGAR_ERROR_NETWORK
    if resp.status_code >= 500:
        return None, EDGAR_ERROR_HTTP_5XX
    if resp.status_code >= 400:
        return None, EDGAR_ERROR_HTTP_4XX
    if resp.status_code != 200:
        return None, EDGAR_ERROR_NETWORK
    try:
        return resp.json(), None
    except ValueError:
        return None, EDGAR_ERROR_DECODE


def _lookup_cik(ticker: str) -> tuple[str | None, str | None]:
    body, err = _fetch_json(_TICKERS_URL)
    if err is not None:
        return None, err
    if not isinstance(body, dict):
        return None, EDGAR_ERROR_DECODE
    target = ticker.upper()
    for entry in body.values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("ticker", "")).upper() == target:
            cik = entry.get("cik_str")
            if cik is None:
                return None, EDGAR_ERROR_CIK_MISS
            return str(int(cik)).zfill(10), None
    return None, EDGAR_ERROR_CIK_MISS


def fetch_us_filing_digest_diag(symbol: str) -> tuple[FilingDigest | None, str | None]:
    """Latest 10-K / 10-Q digest with a typed failure code on the None paths.

    Short-circuits with `EDGAR_ERROR_MISSING_EMAIL` (and a one-time stderr
    warning) when `EDGAR_CONTACT_EMAIL` is empty, so SEC's rate limiter never
    sees an unidentified request.
    """
    if not _EDGAR_CONTACT:
        _maybe_warn_missing_email()
        return None, EDGAR_ERROR_MISSING_EMAIL

    cik, err = _lookup_cik(symbol)
    if cik is None:
        return None, err
    facts, err = _fetch_json(_FACTS_URL.format(cik=cik))
    if facts is None:
        return None, err
    if not isinstance(facts, dict):
        return None, EDGAR_ERROR_DECODE
    revenue_rows = _units_usd(facts, _REVENUE_TAGS)
    if not revenue_rows:
        return None, EDGAR_ERROR_DECODE
    latest = _latest_periodic(revenue_rows)
    if latest is None:
        return None, EDGAR_ERROR_DECODE
    fy = int(latest["fy"])
    fp = str(latest["fp"])
    prior_revenue = _match_prior_year(revenue_rows, fy, fp)
    revenue_yoy = (
        (latest["val"] - prior_revenue["val"]) / prior_revenue["val"]
        if prior_revenue and prior_revenue.get("val")
        else None
    )

    net_rows = _units_usd(facts, _NET_INCOME_TAGS)
    net_cur = _match_year(net_rows, fy, fp)
    net_prior = _match_year(net_rows, fy - 1, fp)
    net_income_yoy = (
        (net_cur["val"] - net_prior["val"]) / net_prior["val"]
        if net_cur and net_prior and net_prior.get("val")
        else None
    )

    cost_rows = _units_usd(facts, _COST_TAGS)
    cost_cur = _match_year(cost_rows, fy, fp)
    gross_margin = (
        1 - cost_cur["val"] / latest["val"]
        if cost_cur and latest.get("val")
        else None
    )

    return (
        FilingDigest(
            symbol=symbol.upper(),
            fiscal_period=_fiscal_period(fy, fp),
            filed_at_iso=str(latest.get("filed", "")),
            revenue_yoy=revenue_yoy,
            net_income_yoy=net_income_yoy,
            gross_margin=gross_margin,
            source_url=_FACTS_URL.format(cik=cik),
        ),
        None,
    )


def fetch_us_filing_digest(symbol: str) -> FilingDigest | None:
    """Legacy single-return signature. Use `fetch_us_filing_digest_diag` for
    callers that need the typed error code."""
    digest, _err = fetch_us_filing_digest_diag(symbol)
    return digest


def _units_usd(facts: dict, tag_candidates: tuple[str, ...]) -> list[dict]:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tag_candidates:
        series = gaap.get(tag)
        if not isinstance(series, dict):
            continue
        units = series.get("units", {})
        usd = units.get("USD")
        if isinstance(usd, list) and usd:
            return usd
    return []


def _latest_periodic(rows: list[dict]) -> dict | None:
    candidates = [r for r in rows if r.get("form") in ("10-K", "10-Q")]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.get("filed", ""))


def _match_prior_year(rows: list[dict], fy: int, fp: str) -> dict | None:
    for r in rows:
        if r.get("fy") == fy - 1 and r.get("fp") == fp:
            return r
    return None


def _match_year(rows: list[dict], fy: int, fp: str) -> dict | None:
    for r in rows:
        if r.get("fy") == fy and r.get("fp") == fp and r.get("form") in ("10-K", "10-Q"):
            return r
    return None


def _fiscal_period(fy: int, fp: str) -> str:
    return f"{fy}FY" if fp == "FY" else f"{fy}{fp}"
```

- [ ] **Step 4: Update existing happy-path test if it asserts on `_USER_AGENT`**

Run: `uv run pytest tests/fundamentals/test_edgar_client.py -v`
Expected: previously-passing tests still pass; new tests pass.

If a previously-passing test fails because it directly imported a helper that moved or its return signature shifted (e.g. `_fetch_json`), fix it in place — for any test that calls `_fetch_json` directly, unpack the new tuple: `payload, err = edgar_client._fetch_json(url)`.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/edgar_client.py tests/fundamentals/test_edgar_client.py
git commit -m "feat(fundamentals): typed EDGAR error codes + warn-once on missing email

fetch_us_filing_digest_diag returns (FilingDigest | None, error_code | None)
so the snapshot orchestrator can tag per-symbol failures with the cause
(missing_email, http_4xx, http_5xx, network, decode, cik_not_found).
Legacy fetch_us_filing_digest stays as a thin wrapper. A single stderr
warning fires the first time we short-circuit on empty EDGAR_CONTACT_EMAIL."
```

---

## Task 3: Tag per-symbol failures in `_build_us_snapshot`

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py:147-167` (function `_build_us_snapshot`)
- Modify: `tests/fundamentals/test_snapshot.py` (add tests after existing US snapshot tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/fundamentals/test_snapshot.py`:

```python
# ---------- US snapshot per-symbol error tagging ----------


def test_build_us_snapshot_tags_each_failure_with_error_code(monkeypatch) -> None:
    """When every US symbol fails, failure_reasons must (a) tag each per-symbol
    line with the typed error code and (b) emit one summary line when all
    codes agree."""
    monkeypatch.setattr(
        snapshot, "fetch_us_filing_digest_diag",
        lambda sym: (None, "missing_email"),
    )
    snap = build_snapshot("纳斯达克100", top_n=10, as_of_iso="2026-05-16")
    assert snap.lookthrough_target == "纳斯达克100"
    assert snap.filings == ()
    per_symbol = [r for r in snap.failure_reasons if r.startswith("missing filing digest:")]
    assert len(per_symbol) == 10
    assert all("(missing_email)" in r for r in per_symbol)
    assert any(r == "all US fetches failed: missing_email" for r in snap.failure_reasons)


def test_build_us_snapshot_mixed_failures_omit_summary(monkeypatch) -> None:
    """Per-symbol tagging happens regardless, but the summary line only fires
    when every symbol shares one cause."""
    def fake_fetch(sym: str):
        if sym == "AAPL":
            return None, "http_4xx"
        return None, "missing_email"
    monkeypatch.setattr(snapshot, "fetch_us_filing_digest_diag", fake_fetch)
    snap = build_snapshot("纳斯达克100", top_n=10, as_of_iso="2026-05-16")
    assert any("(http_4xx)" in r for r in snap.failure_reasons)
    assert any("(missing_email)" in r for r in snap.failure_reasons)
    assert not any(r.startswith("all US fetches failed:") for r in snap.failure_reasons)


def test_build_us_snapshot_partial_success(monkeypatch) -> None:
    """Successful symbols populate filings; failed ones still record the cause."""
    good = FilingDigest(
        symbol="AAPL", fiscal_period="2026Q2", filed_at_iso="2026-05-02",
        revenue_yoy=0.06, net_income_yoy=0.05, gross_margin=0.45,
    )

    def fake_fetch(sym: str):
        if sym == "AAPL":
            return good, None
        return None, "http_4xx"
    monkeypatch.setattr(snapshot, "fetch_us_filing_digest_diag", fake_fetch)
    snap = build_snapshot("纳斯达克100", top_n=10, as_of_iso="2026-05-16")
    assert snap.filings == (good,)
    assert any(r == "missing filing digest: MSFT (http_4xx)" for r in snap.failure_reasons)
    assert not any(r.startswith("all US fetches failed:") for r in snap.failure_reasons)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_snapshot.py -v -k "us_snapshot_tags or mixed_failures or partial_success"`
Expected: failures — `snapshot` module does not yet expose `fetch_us_filing_digest_diag` and the per-symbol failure strings lack the `(code)` suffix.

- [ ] **Step 3: Wire the diag fetcher into `_build_us_snapshot`**

In `src/irc/fundamentals/snapshot.py`, change the top-level import block (the `from irc.fundamentals.edgar_client import …` line) and replace `_build_us_snapshot`.

Update the import (replace the existing one-line import):

```python
from irc.fundamentals.edgar_client import (
    fetch_us_filing_digest,           # kept for any external import
    fetch_us_filing_digest_diag,
)
```

Replace `_build_us_snapshot` with:

```python
def _build_us_snapshot(
    target: str, spec: _TargetSpec, as_of_iso: str,
) -> ConstituentSnapshot:
    filings: list[FilingDigest] = []
    failures: list[str] = []
    per_symbol_codes: list[str] = []
    constituents = tuple(
        Constituent(symbol=s, name=s, weight=0.0, market="us") for s in spec.symbols
    )
    for symbol in spec.symbols:
        digest, code = fetch_us_filing_digest_diag(symbol)
        if digest is None:
            tag = f" ({code})" if code else ""
            failures.append(f"missing filing digest: {symbol}{tag}")
            if code:
                per_symbol_codes.append(code)
        else:
            filings.append(digest)
    if filings == [] and per_symbol_codes and len(set(per_symbol_codes)) == 1:
        failures.append(f"all US fetches failed: {per_symbol_codes[0]}")
    return ConstituentSnapshot(
        lookthrough_target=target,
        as_of_iso=as_of_iso,
        constituents=constituents,
        filings=tuple(filings),
        broker_reports=(),
        failure_reasons=tuple(failures),
    )
```

Note: `FilingDigest` must be in scope inside this file. It already is via the existing `from irc.fundamentals.types import (Constituent, ConstituentSnapshot)` block — extend the tuple to include `FilingDigest`:

```python
from irc.fundamentals.types import (
    Constituent,
    ConstituentSnapshot,
    FilingDigest,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_snapshot.py -v`
Expected: all snapshot tests pass.

- [ ] **Step 5: Run the full fundamentals test suite**

Run: `uv run pytest tests/fundamentals -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/irc/fundamentals/snapshot.py tests/fundamentals/test_snapshot.py
git commit -m "feat(fundamentals): tag US snapshot failures with EDGAR error code

_build_us_snapshot now reads the typed error code from
fetch_us_filing_digest_diag and appends 'missing filing digest: SYM (code)'
per failure plus a summary 'all US fetches failed: <code>' line when every
symbol shares one cause."
```

---

## Task 4: Refined `evidence_gaps` labels in `thesis_evidence`

**Files:**
- Modify: `src/irc/opportunity/thesis_evidence.py:169-215` (function `derive_thesis_from_evidence` + helpers)
- Modify: `tests/opportunity/test_thesis_evidence.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/opportunity/test_thesis_evidence.py`:

```python
# ---------------------------------------------------------------------------
# Refined constituent-gap labels (in addition to legacy missing_constituent_snapshot)
# ---------------------------------------------------------------------------


def test_refined_label_constituent_not_applicable_for_gold():
    """Gold has no equity-style constituents; emit constituent_not_applicable
    alongside the legacy label."""
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="gold",
    )
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_not_applicable" in gaps


def test_refined_label_constituent_not_applicable_for_bond():
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="cn_bond_fund",
    )
    assert "constituent_not_applicable" in gaps


def test_refined_label_constituent_not_applicable_for_active_fund():
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="cn_equity_fund",
    )
    assert "constituent_not_applicable" in gaps


def test_refined_label_constituent_fetch_failed_when_snapshot_empty():
    """Snapshot object exists but filings is empty AND failure_reasons records
    a fetch problem → constituent_fetch_failed."""
    snap = ConstituentSnapshot(
        lookthrough_target="纳斯达克100",
        as_of_iso="2026-05-16",
        constituents=(Constituent(symbol="AAPL", name="AAPL", weight=0.0, market="us"),),
        filings=(),
        broker_reports=(),
        failure_reasons=("missing filing digest: AAPL (missing_email)",),
    )
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        snap, _theme_report(), asset_class="us_etf",
    )
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_fetch_failed" in gaps


def test_refined_label_constituent_missing_when_snapshot_none_for_indexable_class():
    """ETF whose lookthrough target is not yet registered → constituent_missing."""
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        None, _theme_report(), asset_class="cn_etf",
    )
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_missing" in gaps


def test_no_refined_label_when_snapshot_usable():
    filings = tuple(_filing(f"S{i}", 0.10) for i in range(5))
    snap = _snapshot(filings=filings)
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(
        snap, _theme_report(), asset_class="cn_etf",
    )
    assert "missing_constituent_snapshot" not in gaps
    assert "constituent_not_applicable" not in gaps
    assert "constituent_fetch_failed" not in gaps
    assert "constituent_missing" not in gaps


def test_no_refined_label_when_asset_class_omitted():
    """Backward-compatible: without asset_class, only legacy label appears."""
    _state, _reason, _ev, gaps = derive_thesis_from_evidence(None, _theme_report())
    assert "missing_constituent_snapshot" in gaps
    assert "constituent_not_applicable" not in gaps
    assert "constituent_fetch_failed" not in gaps
    assert "constituent_missing" not in gaps
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_thesis_evidence.py -v -k "refined or no_refined"`
Expected: failures — `derive_thesis_from_evidence` does not yet accept `asset_class`.

- [ ] **Step 3: Add the helper and extend the signature**

In `src/irc/opportunity/thesis_evidence.py`, add the helper just above `derive_thesis_from_evidence`:

```python
_NON_INDEXABLE_ASSET_CLASSES: frozenset[str] = frozenset({
    "gold", "cn_bond_fund", "cn_equity_fund",
})


def _classify_constituent_gap(
    snapshot: ConstituentSnapshot | None,
    asset_class: str | None,
) -> str | None:
    """Refined gap label for the constituent layer.

    Returns one of:
      - 'constituent_not_applicable': asset class has no equity-style top-N
        (gold, bond, active fund).
      - 'constituent_fetch_failed': snapshot exists but every filing fetch
        failed (snapshot.failure_reasons is non-empty, filings is empty).
      - 'constituent_missing': asset class is constituent-bearing but no
        snapshot was loaded (lookthrough target not in _TARGET_REGISTRY).
      - None: snapshot present with usable filings.
    """
    if asset_class is None:
        return None
    if asset_class in _NON_INDEXABLE_ASSET_CLASSES:
        return "constituent_not_applicable"
    if snapshot is None:
        return "constituent_missing"
    if not snapshot.filings:
        return "constituent_fetch_failed"
    return None
```

Replace the existing `derive_thesis_from_evidence` with the version below:

```python
def derive_thesis_from_evidence(
    snapshot: ConstituentSnapshot | None,
    theme_report: ThemeReport | None,
    *,
    asset_class: str | None = None,
) -> tuple[ThesisState, str, tuple[ThesisEvidence, ...], tuple[str, ...]]:
    """Derive (state, reason, evidence, gap_labels) from concrete sources.

    Pure: no I/O, no time-of-day dependence. The caller decides what to do
    with `gap_labels` — typically merge into `OpportunityRow.evidence_gaps`.

    When `asset_class` is provided, a refined constituent-gap label is appended
    to the legacy `missing_constituent_snapshot` label so consumers can
    distinguish 'not applicable' from 'fetch failed' from 'missing target'.
    """
    gaps: list[str] = []

    snapshot_usable = snapshot is not None and bool(snapshot.filings)
    if not snapshot_usable:
        gaps.append("missing_constituent_snapshot")
    if not _theme_report_usable(theme_report):
        gaps.append("missing_recent_news")

    refined = _classify_constituent_gap(snapshot, asset_class)
    if refined is not None and refined not in gaps:
        gaps.append(refined)

    # Path A: snapshot present and usable → constituent-driven thesis (authoritative)
    if snapshot_usable:
        pos, neg, total = _yoy_split(snapshot.filings)
        if total == 0:
            gaps.append("missing_constituent_snapshot")
        else:
            if not snapshot.broker_reports:
                gaps.append("missing_broker_coverage")
            consensus = _broker_consensus(snapshot.broker_reports)
            evidence = (
                _filing_evidence(snapshot.filings)
                + _broker_evidence(snapshot.broker_reports)
                + _news_evidence(theme_report)
            )
            state, reason = _classify_state(pos / total, neg / total, consensus)
            return (state, reason, evidence, tuple(gaps))

    # Path B: no usable snapshot → try theme_report-only thesis
    if theme_report is not None and _theme_report_usable(theme_report):
        state, reason, evidence = _thesis_from_theme_report(theme_report)
        if state != "evidence_insufficient":
            return state, reason, evidence, tuple(gaps)

    return (
        "evidence_insufficient",
        "缺少底层成分股财报数据，且主题研究证据不足，无法判定长期逻辑。",
        (),
        tuple(gaps),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_thesis_evidence.py -v`
Expected: all tests in that file pass (existing + new).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/thesis_evidence.py tests/opportunity/test_thesis_evidence.py
git commit -m "feat(opportunity): refined evidence_gaps labels for constituent layer

derive_thesis_from_evidence accepts an optional asset_class kwarg and emits
one of constituent_not_applicable / constituent_fetch_failed /
constituent_missing alongside the legacy missing_constituent_snapshot
label. Backward-compatible: omitting asset_class keeps today's behavior."
```

---

## Task 5: Plumb `asset_class` through `build_opportunity_row` + weak-link reason

**Files:**
- Modify: `src/irc/opportunity/states.py:183-286`
- Modify: `tests/opportunity/test_states.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/opportunity/test_states.py`:

```python
# ---------------------------------------------------------------------------
# Weak-link label in the catch-all small_watch reason
# ---------------------------------------------------------------------------


from irc.opportunity.states import build_opportunity_row, compose_opportunity_state


def test_compose_small_watch_reason_names_weak_product_quality():
    state, reason = compose_opportunity_state(
        valuation="reasonable_low",
        heat="cold",
        thesis="intact",
        product_quality="weak",
        venue_compatible=True,
    )
    assert state == "small_watch"
    assert "产品质量薄弱" in reason
    assert reason.endswith("列入小仓位观察。")


def test_compose_small_watch_reason_names_weak_thesis():
    state, reason = compose_opportunity_state(
        valuation="fair",
        heat="normal",
        thesis="evidence_insufficient",
        product_quality="acceptable",
        venue_compatible=True,
    )
    assert state == "small_watch"
    assert "主题逻辑证据不足" in reason


def test_compose_small_watch_reason_names_missing_valuation():
    state, reason = compose_opportunity_state(
        valuation="evidence_insufficient",
        heat="normal",
        thesis="intact",
        product_quality="acceptable",
        venue_compatible=True,
    )
    assert state == "small_watch"
    assert "估值数据缺失" in reason


def test_compose_small_watch_reason_falls_back_on_conflict():
    """No single sub-state is weakest → generic 'signal conflict' label."""
    state, reason = compose_opportunity_state(
        valuation="fair",
        heat="normal",
        thesis="intact",
        product_quality="acceptable",
        venue_compatible=True,
    )
    assert state == "small_watch"
    assert "信号方向冲突" in reason


def test_build_opportunity_row_passes_asset_class_to_thesis_evidence():
    """A gold instrument with no snapshot picks up the refined label."""
    from irc.fundamentals.types import ConstituentSnapshot
    from irc.opportunity.types import OpportunityInput

    inp = OpportunityInput(
        instrument_id="518880",
        asset_class="gold",
        market="cn_on_exchange",
        valuation_percentile_self=0.95,
        ret_1m=0.04,
        ret_3m=0.05,
    )
    row = build_opportunity_row(
        inp,
        theme_thesis=None,
        snapshot=None,
        theme_report=None,
    )
    assert "constituent_not_applicable" in row.evidence_gaps
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_states.py -v -k "small_watch_reason or passes_asset_class"`
Expected: failures — weak-link label not yet embedded; `asset_class` not yet threaded.

- [ ] **Step 3: Add the weak-link helper + update `compose_opportunity_state`**

In `src/irc/opportunity/states.py`, insert the helper just above `compose_opportunity_state` (and update that function's catch-all branch only):

```python
def _weak_link_label(
    valuation: ValuationState,
    heat: HeatState,
    thesis: ThesisState,
    product_quality: ProductQualityState,
) -> str:
    """Pick a short Chinese label describing the weakest sub-state.

    Priority mirrors the ordering reviewers care about: product quality
    fundamentals first, then thesis evidence, then valuation data, then heat.
    When no single sub-state stands out the label is the generic
    'signal conflict' fallback.
    """
    if product_quality == "weak":
        return "产品质量薄弱"
    if thesis == "evidence_insufficient":
        return "主题逻辑证据不足"
    if valuation == "evidence_insufficient":
        return "估值数据缺失"
    if heat == "evidence_insufficient":
        return "热度信号不足"
    return "信号方向冲突"
```

Replace the final `return` line of `compose_opportunity_state` (currently `return "small_watch", "证据不完整或信号不一致，列入小仓位观察。"`) with:

```python
    label = _weak_link_label(valuation, heat, thesis, product_quality)
    return (
        "small_watch",
        f"证据不完整或信号不一致（{label}），列入小仓位观察。",
    )
```

- [ ] **Step 4: Thread `asset_class` into `derive_thesis_from_evidence`**

Still in `src/irc/opportunity/states.py`, update `build_opportunity_row`. The change is one keyword argument plus extending the table-fallback `thesis_gaps` tuple. Replace the block that currently reads:

```python
    structural_gaps = _structural_evidence_gaps(inp)
    if snapshot is not None or theme_report is not None:
        thesis, thesis_reason, evidence, thesis_gaps = derive_thesis_from_evidence(
            snapshot, theme_report,
        )
    else:
        thesis, thesis_reason = classify_thesis(inp, theme_thesis)
        evidence = ()
        thesis_gaps = ("missing_constituent_snapshot", "missing_recent_news")
```

with:

```python
    structural_gaps = _structural_evidence_gaps(inp)
    if snapshot is not None or theme_report is not None:
        thesis, thesis_reason, evidence, thesis_gaps = derive_thesis_from_evidence(
            snapshot, theme_report, asset_class=inp.asset_class,
        )
    else:
        thesis, thesis_reason = classify_thesis(inp, theme_thesis)
        evidence = ()
        refined = _refined_table_gap(inp.asset_class)
        legacy = ("missing_constituent_snapshot", "missing_recent_news")
        thesis_gaps = legacy + ((refined,) if refined is not None else ())
```

Add this small helper just above `build_opportunity_row` (it re-uses the asset-class set from `thesis_evidence`, but `states.py` already imports from that module — extend the import rather than duplicating the constant):

```python
# Add this import at the top of states.py, alongside the existing
# `from irc.opportunity.thesis_evidence import derive_thesis_from_evidence` line:
from irc.opportunity.thesis_evidence import (
    _NON_INDEXABLE_ASSET_CLASSES,
    derive_thesis_from_evidence,
)


def _refined_table_gap(asset_class: str | None) -> str | None:
    """Refined label for the table-fallback path (no snapshot, no theme_report)."""
    if asset_class is None:
        return None
    if asset_class in _NON_INDEXABLE_ASSET_CLASSES:
        return "constituent_not_applicable"
    return "constituent_missing"
```

(Using a name-mangled private import is acceptable here because `states.py` and `thesis_evidence.py` are sibling modules in the same package and the spec explicitly carries the gap-label vocabulary as the contract between them. The alternative — re-defining the frozenset — would be a DRY violation that risks drift.)

- [ ] **Step 5: Run all opportunity tests**

Run: `uv run pytest tests/opportunity -v`
Expected: every test passes, including `test_build_opportunity_row_records_evidence_gaps` (existing) which checks `missing_constituent_snapshot` lives on for cn_etf rows.

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS. If `evals/` is collected and any architecture/coverage gate trips on the new private import in `states.py`, replace the import with a local re-declaration of the set instead — the test result is what matters.

- [ ] **Step 7: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): weak-link label in small_watch reason + asset_class threading

compose_opportunity_state's catch-all branch now names the weakest sub-state
(产品质量薄弱 / 主题逻辑证据不足 / 估值数据缺失 / 热度信号不足 /
信号方向冲突) inside the existing 列入小仓位观察 reason. build_opportunity_row
threads inp.asset_class into derive_thesis_from_evidence so gold / bond /
active-fund rows pick up constituent_not_applicable, and unmapped cn_etf
rows get constituent_missing."
```

---

## Task 6: Integration smoke + regenerate the affected snapshots

This task is not test-driven — it confirms the rebuilt fundamentals data behaves end-to-end. Skip this task in CI; run locally before merging.

**Files:**
- Run: `uv run irc fundamentals --target 创业板`
- Run: `uv run irc fundamentals --target 纳斯达克100`
- Inspect: `data/fundamentals/2026Q1/创业板.json`, `data/fundamentals/2026Q1/纳斯达克100.json`

- [ ] **Step 1: Rebuild the 创业板 snapshot**

Run: `uv run irc fundamentals --target 创业板`
Expected: the command exits 0 with `fundamentals snapshot OK: 创业板 -> data/fundamentals/<quarter>/创业板.json`. The JSON should now contain a non-empty `constituents` array (≤10 entries with `weight: 0.0` because the Sina fallback does not return weights).

- [ ] **Step 2: Rebuild the 纳斯达克100 snapshot**

Run: `uv run irc fundamentals --target 纳斯达克100`
Expected behavior depends on whether `EDGAR_CONTACT_EMAIL` is set:
- Empty: one stderr line `WARNING: EDGAR_CONTACT_EMAIL is empty …` printed once, then `failure_reasons` contains `missing filing digest: AAPL (missing_email)` ×10 plus `all US fetches failed: missing_email`.
- Set to a valid email: SEC requests succeed; `filings` populated; `failure_reasons` empty or contains only genuine per-symbol issues (e.g. `BRK.B (cik_not_found)`).

- [ ] **Step 3: Re-run opportunity to confirm the new gap labels surface**

Run: `uv run irc opportunity`
Inspect: `outputs/<today>/opportunity_report.json` — pick a gold row (e.g. `518880`), a 主动权益 row (e.g. `005827`), and a 纳斯达克100 row (e.g. `161130`). Each should now show the refined label alongside `missing_constituent_snapshot`:
- gold → `["missing_constituent_snapshot", "constituent_not_applicable"]`
- 主动权益 → `["missing_constituent_snapshot", "constituent_not_applicable"]`
- 纳斯达克100 (with empty filings) → `["missing_constituent_snapshot", "constituent_fetch_failed"]`

Any `small_watch` row that landed in the catch-all branch should now display the weak-link parenthetical in its `opportunity_reason`.

- [ ] **Step 4: Commit refreshed snapshots**

```bash
git add data/fundamentals/2026Q1/创业板.json data/fundamentals/2026Q1/纳斯达克100.json
git commit -m "chore(data): refresh 创业板 + 纳斯达克100 snapshots after diagnostics fix"
```

(If `EDGAR_CONTACT_EMAIL` is still empty, the Nasdaq snapshot file content is essentially unchanged structurally but the per-symbol failure strings now carry the typed code — that's still worth committing for the audit trail.)

---

## Self-review notes

1. **Spec coverage check.**
   - §1 of spec (SZSE fallback) → Task 1. ✓
   - §2 of spec (EDGAR setup warning + typed errors) → Tasks 2 + 3. ✓
   - §3 of spec (refined gap labels + weak-link reason) → Tasks 4 + 5. ✓
   - §4 testing list of the spec → distributed across each task's TDD step + Task 6 integration smoke. ✓
   - Acceptance criteria from spec → Task 6 integration. ✓
2. **Placeholder scan.** No "TBD"/"TODO"/"similar to" placeholders. Every step shows the code or the command.
3. **Type consistency.** Constants `EDGAR_ERROR_*` are spelled identically in source, tests, and the snapshot caller. The kwarg name `asset_class` matches across `thesis_evidence`, `states`, and the new tests. The helper `_classify_constituent_gap` returns labels exactly matching the test assertions (`constituent_not_applicable` / `constituent_fetch_failed` / `constituent_missing`).
4. **One uncertainty kept on purpose.** The decision to keep emitting `missing_constituent_snapshot` alongside refined labels is preserved end-to-end so `evals/opportunity/metrics.py` and the memo evidence pool need no changes — the design called this out and the tests assert *both* labels appear.
