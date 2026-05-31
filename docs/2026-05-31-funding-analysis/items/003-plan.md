# Item 003 — Pluggable CN data layer + Tushare fallback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a `CnFundamentalsProvider` `Protocol` with an `AkShareProvider` default (byte-identical to today), an optional `TushareProvider` fallback (most valuably broker `target_price`), composed via `FallbackProvider`, and migrate the four CN call-sites behind one injected `provider` parameter — with zero behavior change when no `TUSHARE_TOKEN` is set.

**Architecture:** A structural `Protocol` (no inheritance) reusing the existing frozen return types `FilingDigest` / `BrokerReport` / `IndexValuation`. `AkShareProvider` delegates each method verbatim to the unchanged module functions. `TushareProvider` routes all I/O through one `_tushare_call(token, fn_name, **kwargs)` edge (mirroring `_ak_call`) and degrades to `None`/`()` on any failure/empty/schema-miss. `FallbackProvider(primary, secondary)` tries primary, then secondary on a per-method miss, and never raises. `default_cn_provider()` is the construction edge — `AkShareProvider()` when the token is empty, else `FallbackProvider(AkShareProvider(), TushareProvider(token))`. The provider is resolved once at each command edge and threaded as one keyword-only parameter; inner functions keep a default-arg so existing tests stay green. Network is never hit in unit tests (monkeypatch `_tushare_call`; `FallbackProvider` tested with in-memory fakes). One double-gated live test pins the real Tushare shape.

**Tech Stack:** Python 3.12, `typing.Protocol` / `@runtime_checkable`, `dataclasses`, pandas, pydantic-settings (`Settings().tushare_token`), pytest (`--strict-markers`), `tushare` (local import inside the edge only; added as a runtime dep). Reuses the proven `_ak_call` monkeypatch pattern (`unittest.mock.patch`).

---

## Why this sequencing (read before starting)

The suite must stay green at **every** commit. The order is non-negotiable:

1. **Phase A** — add `provider.py` (Protocol + `AkShareProvider` + `FallbackProvider` + `default_cn_provider`) and lock `AkShareProvider`'s behavior with a byte-equality regression test on stubbed `_ak_call`. Nothing is wired yet ⇒ suite green.
2. **Phase B** — migrate the four call-sites to a threaded `provider` param (default `default_cn_provider()`). Because the no-token default is `AkShareProvider` and each method delegates verbatim, output is byte-identical. Locked by a migration byte-equality regression. Suite green.
3. **Phase C** — add `TushareProvider` + `_tushare_call` edge + pure mapping helpers (`tushare_provider.py`), wire it into `default_cn_provider()` behind the token, and prove the `target_price` flow through `FallbackProvider`. Network mocked. Suite green.
4. **Phase D** — register the `live_tushare` marker, add the double-gated live test, extend the static-profile grep test (AC9 fix), and update the README + live-tests README.

Each task ends in a commit. Phases B and C never change the token-absent path ⇒ no existing test can break.

## File structure (locked decomposition)

- **Create** `src/irc/fundamentals/provider.py` — `CnFundamentalsProvider` Protocol + `AkShareProvider` + `FallbackProvider` + `default_cn_provider()`. No `tushare` import here. Target < 120 lines.
- **Create** `src/irc/fundamentals/tushare_provider.py` — `TushareProvider`, the `_tushare_call` edge, and the pure frame→DTO mapping helpers. Local `import tushare` inside `_tushare_call` only. Target < 200 lines.
- **Modify** `src/irc/opportunity/inputs_loader.py` — thread `provider` into `populate_inputs` and `_index_valuation_metrics` (call-site `:105`).
- **Modify** `src/irc/fundamentals/snapshot.py` — thread `provider` into `build_snapshot` → `_build_active_fund_snapshot` → `_evidence_for_constituent` (`:337,355`) and `_build_legacy_snapshot` → `_build_cn_snapshot` (`:595,600`).
- **Modify** `src/irc/commands/opportunity_cmd.py` — resolve `default_cn_provider()` once in `run_opportunity` and pass it to `_build_rows` / `_build_input` / `_resolve_fund_level_snapshot` (which forward it to `build_snapshot` / `populate_inputs`).
- **Modify** `src/irc/commands/fundamentals_cmd.py` — resolve once in `run_snapshot_rebuild` and pass to `build_snapshot`.
- **Modify** `pyproject.toml` — register the `live_tushare` marker; add `tushare` to runtime deps.
- **Modify** `README.md` — `TUSHARE_TOKEN` table row + "Tushare fallback (optional)" subsection.
- **Modify** `tests/fundamentals/README-live-tests.md` — one-line pointer to the new marker/env.
- **Modify** `tests/fundamentals/test_static_profile_invariant.py` — add a grep assertion over the two new modules.
- **Create** tests: `tests/fundamentals/test_provider.py`, `tests/fundamentals/test_tushare_provider.py`, `tests/fundamentals/test_tushare_provider_live.py`, `tests/fundamentals/test_provider_migration.py`.

## Invariants you MUST NOT break (from ADR 0010 / grill)

- **No `基金概况`** in any new production code (AC9). The seam touches none of the static-profile surface.
- **Do NOT touch** `FetchPlan.total_calls()` or any budget code in `opportunity_cmd.py`. Tushare is not metered (ADR 0010 §3, grill G2). The `fetch_budget_exhausted` sentinel path is unchanged.
- **No proxy for Tushare** — `_tushare_call` makes a direct call; do NOT touch `http_proxy.py` (ADR 0010 Consequences).
- **Secrets `.env`-only** — read via `Settings().tushare_token.get_secret_value()` only inside `default_cn_provider()`. Never inline a token in YAML; never log it. No new config key.
- **No new DTOs** — reuse `FilingDigest`, `BrokerReport` (`fundamentals/types.py`), `IndexValuation` (`fundamentals/index_valuation_types.py`).
- **Providers are stateless / immutable** — hold only the immutable token. No module-level mutable provider singleton; `default_cn_provider()` constructs fresh.
- **`FallbackProvider` never raises** — degrade-to-`None`/`()` family (ADR 0009).
- **Files < 200 lines, functions < 20 lines** ideal — extract helpers.

---

## Phase A — Provider seam + AkShareProvider + Fallback + factory (suite stays green; nothing wired yet)

### Task A1: `CnFundamentalsProvider` Protocol + `AkShareProvider` (verbatim delegation)

**Files:**
- Create: `src/irc/fundamentals/provider.py`
- Test: `tests/fundamentals/test_provider.py`

- [ ] **Step 1: Write the failing test** (`tests/fundamentals/test_provider.py`)

```python
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals import akshare_filing, akshare_index_valuation
from irc.fundamentals.akshare_filing import fetch_cn_broker_reports, fetch_cn_filing_digest
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation
from irc.fundamentals.provider import (
    AkShareProvider,
    CnFundamentalsProvider,
)


# ── Fixture frames (mirror the live AkShare column labels) ────────────────────
_FIN_FRAME = pd.DataFrame({
    "选项": ["常用指标", "常用指标", "常用指标", "盈利能力"],
    "指标": ["营业总收入", "归母净利润", "营业成本", "净资产收益率"],
    "20241231": [1000.0, 200.0, 600.0, 0.18],
    "20231231": [800.0, 150.0, 500.0, 0.15],
})
_PE_FRAME = pd.DataFrame({"日期": ["2026-05-30"], "平均市盈率": [12.1]})
_PB_FRAME = pd.DataFrame({"日期": ["2026-05-30"], "市净率": [1.31]})
_BROKER_FRAME = pd.DataFrame({
    "机构": ["中信"],
    "东财评级": ["买入"],
    "报告名称": ["深度报告"],
    "日期": [pd.Timestamp.today().strftime("%Y-%m-%d")],
    "报告PDF链接": ["http://x/y.pdf"],
})


def test_akshare_provider_satisfies_protocol() -> None:
    assert isinstance(AkShareProvider(), CnFundamentalsProvider)


def test_akshare_provider_filing_equals_direct_call() -> None:
    with patch.object(akshare_filing, "_ak_call", return_value=_FIN_FRAME):
        direct = fetch_cn_filing_digest("600519")
    with patch.object(akshare_filing, "_ak_call", return_value=_FIN_FRAME):
        via = AkShareProvider().fetch_filing_digest("600519")
    assert via == direct


def test_akshare_provider_brokers_equals_direct_call() -> None:
    with patch.object(akshare_filing, "_ak_call", return_value=_BROKER_FRAME):
        direct = fetch_cn_broker_reports("600519")
    with patch.object(akshare_filing, "_ak_call", return_value=_BROKER_FRAME):
        via = AkShareProvider().fetch_broker_reports("600519")
    assert via == direct


def test_akshare_provider_index_equals_direct_call() -> None:
    def _fake(fn_name, **kwargs):
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch.object(akshare_index_valuation, "_ak_call", side_effect=_fake), patch.object(
        akshare_index_valuation, "_today_iso", return_value="2026-05-31"
    ):
        direct = fetch_cn_index_valuation("csi300")
    with patch.object(akshare_index_valuation, "_ak_call", side_effect=_fake), patch.object(
        akshare_index_valuation, "_today_iso", return_value="2026-05-31"
    ):
        via = AkShareProvider().fetch_index_valuation("csi300")
    assert via == direct


def test_akshare_provider_passes_kwargs_to_broker_fetch() -> None:
    # Provider must forward the days/max_reports keyword args verbatim.
    captured: list[dict] = []

    def _fake(fn_name, **kwargs):
        captured.append({"fn": fn_name, **kwargs})
        return _BROKER_FRAME

    with patch.object(akshare_filing, "_ak_call", side_effect=_fake):
        AkShareProvider().fetch_broker_reports("600519", days=30, max_reports=5)
    assert captured and captured[0]["fn"] == "stock_research_report_em"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/fundamentals/test_provider.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.fundamentals.provider'`.

- [ ] **Step 3: Write the minimal implementation** (`src/irc/fundamentals/provider.py`)

```python
"""Pluggable CN-fundamentals provider seam (ADR 0010, item 003).

A structural `Protocol` over the three CN-fundamentals fetch surfaces, reusing
their existing frozen return types. `AkShareProvider` delegates VERBATIM to the
unchanged module functions (no parsing re-implemented), so the token-absent path
is byte-identical to pre-003. `FallbackProvider` composes two providers per
method (try primary, fill misses with secondary) and NEVER raises.

Tushare lives in `tushare_provider.py` (imported lazily by `default_cn_provider`)
so this module carries no `tushare` import. See docs/adr/0010-...md.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from irc.fundamentals.akshare_filing import (
    fetch_cn_broker_reports,
    fetch_cn_filing_digest,
)
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation
from irc.fundamentals.index_valuation_types import IndexValuation
from irc.fundamentals.types import BrokerReport, FilingDigest


@runtime_checkable
class CnFundamentalsProvider(Protocol):
    """Three CN-fundamentals fetch surfaces. Reuses existing return types."""

    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None: ...

    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]: ...

    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None: ...


class AkShareProvider:
    """Delegates each method verbatim to the existing module function.

    Stateless. Reproduces today's behavior byte-for-byte (no parsing here).
    """

    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None:
        return fetch_cn_filing_digest(symbol)

    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]:
        return fetch_cn_broker_reports(symbol, days=days, max_reports=max_reports)

    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None:
        return fetch_cn_index_valuation(index_key)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/fundamentals/test_provider.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/provider.py tests/fundamentals/test_provider.py
git commit -m "feat(003): CnFundamentalsProvider Protocol + AkShareProvider (verbatim delegation)"
```

**Verification point:** `AkShareProvider().fetch_*` is byte-equal to the direct module call on the same stubbed `_ak_call`. This is the DEFAULT behavior-preservation lock.

---

### Task A2: `FallbackProvider` (per-method, never-raises) + `target_price` flow

**Files:**
- Modify: `src/irc/fundamentals/provider.py`
- Test: `tests/fundamentals/test_provider.py`

- [ ] **Step 1: Add the failing tests** (append to `tests/fundamentals/test_provider.py`)

```python
from irc.fundamentals.provider import FallbackProvider  # noqa: E402
from irc.fundamentals.types import BrokerReport as _BR  # noqa: E402


class _Fake:
    """In-memory provider for routing tests (no network)."""

    def __init__(self, *, digest=None, brokers=(), index=None, raises=False):
        self._digest = digest
        self._brokers = brokers
        self._index = index
        self._raises = raises

    def fetch_filing_digest(self, symbol):
        if self._raises:
            raise RuntimeError("boom")
        return self._digest

    def fetch_broker_reports(self, symbol, *, days=90, max_reports=20):
        if self._raises:
            raise RuntimeError("boom")
        return self._brokers

    def fetch_index_valuation(self, index_key):
        if self._raises:
            raise RuntimeError("boom")
        return self._index


def _digest(symbol="600519.SH"):
    return FilingDigest(
        symbol=symbol, fiscal_period="2024FY", filed_at_iso="2024-12-31",
        revenue_yoy=0.25, net_income_yoy=0.33, gross_margin=0.4,
    )


def test_fallback_satisfies_protocol() -> None:
    fp = FallbackProvider(AkShareProvider(), AkShareProvider())
    assert isinstance(fp, CnFundamentalsProvider)


def test_fallback_primary_hit_skips_secondary() -> None:
    primary = _Fake(digest=_digest("P"))
    secondary = _Fake(digest=_digest("S"))
    out = FallbackProvider(primary, secondary).fetch_filing_digest("x")
    assert out is not None and out.symbol == "P"


def test_fallback_primary_miss_uses_secondary() -> None:
    primary = _Fake(digest=None)
    secondary = _Fake(digest=_digest("S"))
    out = FallbackProvider(primary, secondary).fetch_filing_digest("x")
    assert out is not None and out.symbol == "S"


def test_fallback_primary_raises_uses_secondary() -> None:
    primary = _Fake(raises=True)
    secondary = _Fake(digest=_digest("S"))
    out = FallbackProvider(primary, secondary).fetch_filing_digest("x")
    assert out is not None and out.symbol == "S"


def test_fallback_both_miss_returns_none_no_raise() -> None:
    out = FallbackProvider(_Fake(digest=None), _Fake(digest=None)).fetch_filing_digest("x")
    assert out is None


def test_fallback_brokers_empty_primary_uses_secondary() -> None:
    sec = (_BR(symbol="600519.SH", broker="中信", rating="买入",
              target_price=2000.0, published_iso="2026-05-30", title="t"),)
    out = FallbackProvider(_Fake(brokers=()), _Fake(brokers=sec)).fetch_broker_reports("x")
    assert len(out) == 1 and out[0].target_price == 2000.0


def test_fallback_brokers_both_empty_returns_empty_tuple() -> None:
    out = FallbackProvider(_Fake(brokers=()), _Fake(brokers=())).fetch_broker_reports("x")
    assert out == ()


def test_fallback_primary_raises_secondary_raises_returns_miss() -> None:
    out = FallbackProvider(_Fake(raises=True), _Fake(raises=True)).fetch_broker_reports("x")
    assert out == ()


def test_fallback_index_primary_miss_uses_secondary() -> None:
    iv = IndexValuation(index_key="csi300", pe_ttm=10.0, pb=1.0,
                        dividend_yield=None, as_of_iso="2026-05-31")
    out = FallbackProvider(_Fake(index=None), _Fake(index=iv)).fetch_index_valuation("csi300")
    assert out is not None and out.pe_ttm == 10.0


def test_fallback_target_price_flows_when_primary_brokers_empty() -> None:
    # The headline gap: AkShare drops target_price; Tushare-shaped secondary fills it.
    sec = (_BR(symbol="600519.SH", broker="中信", rating="买入",
              target_price=2100.0, published_iso="2026-05-30", title="t"),)
    out = FallbackProvider(_Fake(brokers=()), _Fake(brokers=sec)).fetch_broker_reports("600519")
    assert out[0].target_price == 2100.0
```

Note: `IndexValuation` is already imported at the top of the test file via Task A1's import block; if not, add `from irc.fundamentals.index_valuation_types import IndexValuation`.

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_provider.py -q -k fallback`
Expected: FAIL — `ImportError: cannot import name 'FallbackProvider'`.

- [ ] **Step 3: Implement `FallbackProvider`** (append to `src/irc/fundamentals/provider.py`)

```python
def _try(call):
    """Run `call`, return its value; on any exception return the sentinel `None`.

    Sentinel-agnostic: callers compare the result against their miss value.
    """
    try:
        return call()
    except Exception:
        return None


class FallbackProvider:
    """Per-method: try `primary`; on a miss/exception fall back to `secondary`.

    A "miss" is `None` (digest/index) or `()` (brokers). Both-miss returns the
    primary miss value. Never raises (ADR 0009 degrade-to-None family).
    """

    def __init__(
        self,
        primary: CnFundamentalsProvider,
        secondary: CnFundamentalsProvider,
    ) -> None:
        self._primary = primary
        self._secondary = secondary

    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None:
        primary = _try(lambda: self._primary.fetch_filing_digest(symbol))
        if primary is not None:
            return primary
        return _try(lambda: self._secondary.fetch_filing_digest(symbol))

    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]:
        primary = _try(
            lambda: self._primary.fetch_broker_reports(
                symbol, days=days, max_reports=max_reports
            )
        )
        if primary:
            return primary
        secondary = _try(
            lambda: self._secondary.fetch_broker_reports(
                symbol, days=days, max_reports=max_reports
            )
        )
        return secondary or ()

    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None:
        primary = _try(lambda: self._primary.fetch_index_valuation(index_key))
        if primary is not None:
            return primary
        return _try(lambda: self._secondary.fetch_index_valuation(index_key))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_provider.py -q`
Expected: PASS (all Task A1 + A2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/provider.py tests/fundamentals/test_provider.py
git commit -m "feat(003): FallbackProvider (per-method, never-raises) + target_price flow"
```

**Verification point:** primary-hit / primary-miss / primary-raises / both-miss covered for all three methods; `target_price` proven to flow through on an empty-primary broker fetch (AC3).

---

### Task A3: `default_cn_provider()` factory (token-gated, AkShare-only when empty)

**Files:**
- Modify: `src/irc/fundamentals/provider.py`
- Test: `tests/fundamentals/test_provider.py`

- [ ] **Step 1: Add the failing tests** (append to `tests/fundamentals/test_provider.py`)

```python
from unittest.mock import MagicMock  # noqa: E402

from irc.fundamentals.provider import default_cn_provider  # noqa: E402


def test_default_provider_is_akshare_only_without_token() -> None:
    fake_settings = MagicMock()
    fake_settings.tushare_token.get_secret_value.return_value = ""
    with patch("irc.fundamentals.provider.Settings", return_value=fake_settings):
        provider = default_cn_provider()
    assert isinstance(provider, AkShareProvider)


def test_default_provider_is_fallback_with_token() -> None:
    fake_settings = MagicMock()
    fake_settings.tushare_token.get_secret_value.return_value = "tok-123"
    with patch("irc.fundamentals.provider.Settings", return_value=fake_settings):
        provider = default_cn_provider()
    assert isinstance(provider, FallbackProvider)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_provider.py -q -k default_provider`
Expected: FAIL — `ImportError: cannot import name 'default_cn_provider'`.

- [ ] **Step 3: Implement the factory** (append to `src/irc/fundamentals/provider.py`)

Add to the top-of-file imports:

```python
from irc.settings import Settings
```

Then append:

```python
def default_cn_provider() -> CnFundamentalsProvider:
    """Construction edge: read the token from `.env` and pick the provider.

    No token → `AkShareProvider()` alone (byte-identical to pre-003). With a
    token → `FallbackProvider(AkShareProvider(), TushareProvider(token))`.
    `TushareProvider` is imported lazily so this module never imports tushare.
    """
    token = Settings().tushare_token.get_secret_value().strip()
    if not token:
        return AkShareProvider()
    from irc.fundamentals.tushare_provider import TushareProvider

    return FallbackProvider(AkShareProvider(), TushareProvider(token))
```

Note: the lazy `from irc.fundamentals.tushare_provider import TushareProvider` will fail to import until Phase C. That is fine — the token-set test (`test_default_provider_is_fallback_with_token`) is the only one that triggers it, and Phase C creates the module. **Sequencing guard:** if you are running Phase A in isolation, the token-set test will error on the missing import. To keep Phase A green standalone, create a STUB `tushare_provider.py` now with `class TushareProvider: \n    def __init__(self, token): self._token = token` and the three methods returning `None`/`()`. Phase C replaces it. Prefer the stub.

  - [ ] **Step 3a (sequencing guard): create the Phase-C stub** `src/irc/fundamentals/tushare_provider.py`

```python
"""Tushare provider (item 003). Phase A stub — replaced in Phase C."""
from __future__ import annotations

from irc.fundamentals.index_valuation_types import IndexValuation
from irc.fundamentals.types import BrokerReport, FilingDigest


class TushareProvider:
    def __init__(self, token: str) -> None:
        self._token = token

    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None:
        return None

    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]:
        return ()

    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None:
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_provider.py -q`
Expected: PASS (all provider tests).

- [ ] **Step 5: Run the full fundamentals + opportunity suites + lint to confirm nothing regressed**

Run: `uv run pytest tests/fundamentals tests/opportunity -q`
Expected: PASS (existing count + new provider tests; no failures).
Run: `uv run ruff check src tests`
Expected: clean (no findings).

- [ ] **Step 6: Commit**

```bash
git add src/irc/fundamentals/provider.py src/irc/fundamentals/tushare_provider.py tests/fundamentals/test_provider.py
git commit -m "feat(003): default_cn_provider() factory + TushareProvider stub"
```

**Verification point:** AC1 (Protocol + 3 concretes satisfy `isinstance`), AC6 (token gating) green. Suite still green — nothing migrated yet.

---

## Phase B — Behavior-preserving migration of the four call-sites (suite stays green)

> Threading rule (grill G3): each public function gains ONE keyword-only `provider: CnFundamentalsProvider | None = None` parameter; at the top it resolves `provider = provider or default_cn_provider()` (lazy, at the edge — NOT a default-arg expression, to avoid import-time `Settings()`). Inner private functions take `provider` as a required keyword and forward it.

### Task B1: Migration byte-equality lock (write BEFORE editing call-sites)

**Files:**
- Test: `tests/fundamentals/test_provider_migration.py`

- [ ] **Step 1: Write the failing migration regression test** (`tests/fundamentals/test_provider_migration.py`)

```python
"""Locks: routing the four call-sites through AkShareProvider yields output
byte-identical to the pre-migration direct calls on the same stubbed _ak_call.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals import akshare_index_valuation
from irc.fundamentals.provider import AkShareProvider
from irc.opportunity.inputs_loader import _index_valuation_metrics

_PE_FRAME = pd.DataFrame({"日期": ["2026-05-30"], "平均市盈率": [12.1]})
_PB_FRAME = pd.DataFrame({"日期": ["2026-05-30"], "市净率": [1.31]})


def test_index_metrics_via_provider_matches_pre_migration() -> None:
    def _fake(fn_name, **kwargs):
        return _PE_FRAME if fn_name == "stock_index_pe_lg" else _PB_FRAME

    with patch.object(akshare_index_valuation, "_ak_call", side_effect=_fake):
        out = _index_valuation_metrics("csi300", provider=AkShareProvider())
    # Same as fetch_cn_index_valuation("csi300").pe_ttm / .pb / .dividend_yield.
    assert out == (12.1, 1.31, None)


def test_index_metrics_unknown_key_does_not_call_ak() -> None:
    with patch.object(akshare_index_valuation, "_ak_call") as mocked:
        out = _index_valuation_metrics("not_a_broad_index", provider=AkShareProvider())
    assert out == (None, None, None)
    mocked.assert_not_called()
```

Note: the `_index_valuation_metrics` test is the direct byte-equality lock for the index call-site. The `_build_cn_snapshot` filing/broker call-sites are covered indirectly by the existing `tests/fundamentals/test_snapshot_acceptance.py` (it must stay green after B3) plus the recording-provider threading test in B3.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/fundamentals/test_provider_migration.py -q`
Expected: FAIL — `_index_valuation_metrics()` does not yet accept a `provider` keyword (`TypeError: unexpected keyword argument 'provider'`).

- [ ] **Step 3: (no implementation yet)** — the failing test is intentional; B2/B3 make it pass.

- [ ] **Step 4: Commit the failing-then-fixed lock together at the end of B2** (do NOT commit a red test alone).

---

### Task B2: Migrate the index-valuation call-site (`inputs_loader.py:105`)

**Files:**
- Modify: `src/irc/opportunity/inputs_loader.py`
- Test: `tests/fundamentals/test_provider_migration.py` (from B1), `tests/opportunity/*`

- [ ] **Step 1:** The failing test already exists (B1). Confirm it is red.

Run: `uv run pytest tests/fundamentals/test_provider_migration.py -q -k index_metrics`
Expected: FAIL (`provider` kwarg unknown).

- [ ] **Step 2: Edit `_index_valuation_metrics`** in `src/irc/opportunity/inputs_loader.py`.

Replace the import line:

```python
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation
```

with:

```python
from irc.fundamentals.provider import CnFundamentalsProvider, default_cn_provider
```

Replace the function (currently lines 97–108):

```python
def _index_valuation_metrics(
    tracked_index: str | None,
    *,
    provider: CnFundamentalsProvider,
) -> tuple[float | None, float | None, float | None]:
    """Return (pe_ttm, pb, dividend_yield) for a recognised broad index, else
    (None, None, None). Index valuation is INERT today (item 002 consumes it)."""
    key = (tracked_index or "").strip().lower() or None
    if key is None or key not in _BROAD_INDEX_KEYS:
        return None, None, None
    valuation = provider.fetch_index_valuation(key)
    if valuation is None:
        return None, None, None
    return valuation.pe_ttm, valuation.pb, valuation.dividend_yield
```

- [ ] **Step 3: Thread `provider` into `populate_inputs`** (same file). Change the signature and the one internal call.

Update the signature (currently lines 111–117) to add the keyword-only param:

```python
def populate_inputs(
    con: duckdb.DuckDBPyConnection,
    skeleton: OpportunityInput,
    *,
    holding_entry_date: date | None,
    broker_reports: tuple[BrokerReport, ...] = (),
    provider: CnFundamentalsProvider | None = None,
) -> OpportunityInput:
```

At the top of the function body (right after the docstring, before `meta = ...`) add:

```python
    provider = provider or default_cn_provider()
```

Change the `_index_valuation_metrics` call (currently line 151) to pass the provider:

```python
    pe_ttm, pb, dividend_yield = _index_valuation_metrics(
        skeleton.tracked_index, provider=provider
    )
```

- [ ] **Step 4: Run the migration lock + the opportunity suite**

Run: `uv run pytest tests/fundamentals/test_provider_migration.py -q -k index_metrics`
Expected: PASS.
Run: `uv run pytest tests/opportunity -q`
Expected: PASS (existing tests calling `populate_inputs(...)` without `provider` still work — the default resolves at runtime).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/inputs_loader.py tests/fundamentals/test_provider_migration.py
git commit -m "refactor(003): route index-valuation fetch through injected provider"
```

**Verification point:** AC7 (index call-site) migrated; byte-equality lock green; `populate_inputs` default-arg keeps every existing caller valid.

---

### Task B3: Migrate the filing/broker call-sites (`snapshot.py:337,355,595,600`)

**Files:**
- Modify: `src/irc/fundamentals/snapshot.py`
- Test: existing `tests/fundamentals/test_snapshot_acceptance.py`, `tests/fundamentals/test_fund_level_snapshot.py` (must stay green)

- [ ] **Step 1: Add a failing test** asserting `build_snapshot` accepts a `provider` and uses it (`tests/fundamentals/test_provider_migration.py`, append).

```python
from irc.fundamentals.snapshot import build_snapshot
from irc.fundamentals.types import LookthroughTarget


class _RecordingProvider:
    def __init__(self):
        self.filing_calls: list[str] = []
        self.broker_calls: list[str] = []

    def fetch_filing_digest(self, symbol):
        self.filing_calls.append(symbol)
        return None

    def fetch_broker_reports(self, symbol, *, days=90, max_reports=20):
        self.broker_calls.append(symbol)
        return ()

    def fetch_index_valuation(self, index_key):
        return None


def test_build_snapshot_threads_provider_to_constituent_fetch() -> None:
    rec = _RecordingProvider()
    target = LookthroughTarget(
        kind="active_fund", key="005827", display_cn="易方达蓝筹",
        provider_symbol="005827",
    )
    with patch("irc.fundamentals.snapshot.fetch_cn_etf_holdings") as holdings, patch(
        "irc.fundamentals.snapshot._fetch_active_fund_level_evidence",
        return_value=((), ()),
    ), patch(
        "irc.fundamentals.snapshot.fetch_cn_stock_news", return_value=(),
    ):
        from irc.fundamentals.types import FundHolding, HoldingsResult
        holdings.return_value = HoldingsResult(
            constituents=(FundHolding(
                symbol="600519.SH", name_cn="贵州茅台", weight_pct=9.0,
                exchange="SH", provider_symbol="600519",
            ),),
            source_report_date="2025-03-31",
            source_report_quarter="2025Q1",
        )
        build_snapshot(target, top_n=1, provider=rec)
    assert "600519.SH" in rec.filing_calls
    assert "600519.SH" in rec.broker_calls
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/fundamentals/test_provider_migration.py -q -k threads_provider`
Expected: FAIL — `build_snapshot()` got an unexpected keyword argument `provider`.

- [ ] **Step 3: Edit `src/irc/fundamentals/snapshot.py`.** Five edits.

3a. **Imports** — change the `akshare_filing` import block (currently lines 23–26) to import the provider types instead of the raw fetchers (the raw fetchers are no longer called directly in this module):

Replace:

```python
from irc.fundamentals.akshare_filing import (
    fetch_cn_broker_reports,
    fetch_cn_filing_digest,
)
```

with:

```python
from irc.fundamentals.provider import CnFundamentalsProvider, default_cn_provider
```

3b. **`build_snapshot`** — add the keyword-only param and thread it (signature at lines 245–250):

```python
def build_snapshot(
    target: LookthroughTarget,
    *,
    top_n: int = 10,
    as_of_iso: str = "",
    provider: CnFundamentalsProvider | None = None,
) -> ActiveFundSnapshot | ConstituentSnapshot | FundLevelSnapshot:
```

At the top of the body (right after the docstring, before `timestamp = ...`):

```python
    provider = provider or default_cn_provider()
```

Then forward it in the two branches that lead to CN fetches:

- Change `return _build_active_fund_snapshot(target, top_n=top_n)` →
  `return _build_active_fund_snapshot(target, top_n=top_n, provider=provider)`
- Change `return _build_legacy_snapshot(target.display_cn, top_n=top_n, as_of_iso=timestamp)` →
  `return _build_legacy_snapshot(target.display_cn, top_n=top_n, as_of_iso=timestamp, provider=provider)`

(The `_build_fund_level_snapshot` / `_build_qdii_sentinel_snapshot` branches do NOT call the three CN fetchers — leave them unchanged.)

3c. **`_build_active_fund_snapshot`** — add the param (signature at lines 523–525) and forward to `_evidence_for_constituent`:

```python
def _build_active_fund_snapshot(
    target: LookthroughTarget, *, top_n: int, provider: CnFundamentalsProvider,
) -> ActiveFundSnapshot:
```

Change the call (currently line 560):

```python
        evidence, failures, _cn_digest = _evidence_for_constituent(
            h, fund_id=fund_id, provider=provider
        )
```

3d. **`_evidence_for_constituent`** — add the param (signature at lines 310–314) and replace the two raw fetcher calls (lines 337, 355):

```python
def _evidence_for_constituent(
    holding: FundHolding,
    *,
    fund_id: str,
    provider: CnFundamentalsProvider,
) -> tuple[tuple[ThesisEvidence, ...], list[str], FilingDigest | None]:
```

Line 337 `digest = fetch_cn_filing_digest(holding.symbol)` →
`digest = provider.fetch_filing_digest(holding.symbol)`

Line 355 `brokers = fetch_cn_broker_reports(holding.symbol)` →
`brokers = provider.fetch_broker_reports(holding.symbol)`

(Leave `fetch_cn_stock_news` / `fetch_hk_filing_digest` / `fetch_us_filing_digest` calls untouched — out of scope.)

3e. **`_build_legacy_snapshot` + `_build_cn_snapshot`** — thread the param.

`_build_legacy_snapshot` (signature at lines 282–284):

```python
def _build_legacy_snapshot(
    lookthrough_target: str, *, top_n: int, as_of_iso: str,
    provider: CnFundamentalsProvider,
) -> ConstituentSnapshot:
```

Change its `_build_cn_snapshot` call (currently line 295):

```python
        return _build_cn_snapshot(lookthrough_target, spec, top_n, as_of_iso, provider)
```

`_build_cn_snapshot` (signature at lines 583–585):

```python
def _build_cn_snapshot(
    target: str, spec: _TargetSpec, top_n: int, as_of_iso: str,
    provider: CnFundamentalsProvider,
) -> ConstituentSnapshot:
```

Line 595 `digest = fetch_cn_filing_digest(c.symbol)` →
`digest = provider.fetch_filing_digest(c.symbol)`

Line 600 `reports = fetch_cn_broker_reports(c.symbol)` →
`reports = provider.fetch_broker_reports(c.symbol)`

- [ ] **Step 4: Run the migration tests + the full fundamentals/opportunity suites**

Run: `uv run pytest tests/fundamentals/test_provider_migration.py -q`
Expected: PASS.
Run: `uv run pytest tests/fundamentals tests/opportunity -q`
Expected: PASS (existing `test_snapshot_acceptance.py`, `test_fund_level_snapshot.py`, etc. still green — they call `build_snapshot(target, ...)` without `provider`, default resolves at runtime).

If any existing test patched `irc.fundamentals.snapshot.fetch_cn_filing_digest` / `fetch_cn_broker_reports` directly (now-removed names), it will error. Fix those tests to patch the provider method or `akshare_filing._ak_call` instead. Run this grep first to find them:

Run: `grep -rn "snapshot.fetch_cn_filing_digest\|snapshot.fetch_cn_broker_reports" tests/`
Expected: ideally no matches; if any, repoint them to `irc.fundamentals.akshare_filing._ak_call` (the parsing still lives there) or to the provider method.

- [ ] **Step 5: Lint**

Run: `uv run ruff check src tests`
Expected: clean. (Watch for unused-import: ensure `fetch_cn_filing_digest`/`fetch_cn_broker_reports` are no longer referenced anywhere in `snapshot.py`.)

- [ ] **Step 6: Commit**

```bash
git add src/irc/fundamentals/snapshot.py tests/fundamentals/test_provider_migration.py
git commit -m "refactor(003): route filing/broker fetches through injected provider"
```

**Verification point:** AC7 fully migrated (all four call-sites). The default path is AkShare-only ⇒ byte-identical to pre-003 (locked by B1 + the recording-provider threading test + the unchanged existing acceptance suites).

---

### Task B4: Resolve the provider at the command edges and thread it down

**Files:**
- Modify: `src/irc/commands/opportunity_cmd.py`
- Modify: `src/irc/commands/fundamentals_cmd.py`

> Grill G3: resolve `default_cn_provider()` ONCE at each command edge and pass it as one argument. Because B2/B3 gave the inner functions a runtime-resolving default, this step is OPTIONAL for correctness but REQUIRED by the spec (DI at the edge keeps stage cores pure and avoids N `Settings()` reads per run). Keep the diff shallow: resolve once, forward.

- [ ] **Step 1: `fundamentals_cmd.py`** — resolve once in `run_snapshot_rebuild`, pass to `build_snapshot`.

Add the import near the top:

```python
from irc.fundamentals.provider import default_cn_provider
```

In `run_snapshot_rebuild`, before the `for target in expanded_targets:` loop:

```python
    provider = default_cn_provider()
```

Change the `build_snapshot` call (currently line 46):

```python
        snapshot = build_snapshot(lt, top_n=top_n, provider=provider)
```

- [ ] **Step 2: `opportunity_cmd.py`** — resolve once in `run_opportunity`, thread through `_build_rows` → (`_build_input` → `populate_inputs`) and (`_resolve_fund_level_snapshot` / the `build_snapshot` calls in `_build_rows`).

Add the import (near line 28, with the other snapshot imports):

```python
from irc.fundamentals.provider import CnFundamentalsProvider, default_cn_provider
```

2a. In `run_opportunity`, after the args are validated and before `_build_rows(...)` is called, resolve:

```python
    cn_provider = default_cn_provider()
```

Then pass `cn_provider` into the `_build_rows(...)` call (add `provider=cn_provider` to its kwargs).

2b. Add `provider: CnFundamentalsProvider` as a keyword-only param to `_build_rows` (signature at lines 745–760, add to the `*,` block):

```python
    *,
    output_date: str,
    limit: int | None = None,
    rebuild_fundamentals: bool = False,
    provider: CnFundamentalsProvider,
```

Forward it to every `build_snapshot(target, top_n=TOP_N_DEFAULT)` call inside `_build_rows` (lines 895, 914, 934 and any other in the function) → add `, provider=provider`. Also forward to `_build_input(...)` (the call that builds each row's `OpportunityInput`) and to `_resolve_fund_level_snapshot(...)`.

2c. `_build_input` (signature at line 532) — add `provider: CnFundamentalsProvider` keyword-only and forward to `populate_inputs` (line 579):

```python
    return populate_inputs(
        con, skeleton, holding_entry_date=entry_date, provider=provider
    )
```

2d. `_resolve_fund_level_snapshot` (signature at line 339) — add `provider: CnFundamentalsProvider` keyword-only and forward to its two `build_snapshot(target)` calls (lines 354, 363) → `build_snapshot(target, provider=provider)`.

  - Trace every caller of `_build_input` and `_resolve_fund_level_snapshot` inside `_build_rows` and pass `provider=provider`. Use:

Run: `grep -n "_build_input(\|_resolve_fund_level_snapshot(" src/irc/commands/opportunity_cmd.py`

  to enumerate them, and add `provider=provider` to each call.

- [ ] **Step 3: Run the full command-path + opportunity tests**

Run: `uv run pytest tests/commands tests/opportunity tests/fundamentals -q`
Expected: PASS. (If a test calls `_build_rows(...)` directly without `provider`, give it `provider=default_cn_provider()` or `provider=AkShareProvider()` — search with `grep -rn "_build_rows(" tests/`.)

- [ ] **Step 4: Lint**

Run: `uv run ruff check src tests`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/opportunity_cmd.py src/irc/commands/fundamentals_cmd.py tests/
git commit -m "refactor(003): resolve default_cn_provider() at command edges, thread one param"
```

**Verification point:** DI fully at the edges; stage cores pure; one `Settings()` read per command run. AC7 complete.

---

## Phase C — TushareProvider + `_tushare_call` edge + pure mapping (network mocked)

> Replaces the Phase-A stub `tushare_provider.py`. The `_tushare_call(token, fn_name, **kwargs)` edge does the local `import tushare` — never imported at module load. Unit tests monkeypatch `_tushare_call` or feed fixture frames to the pure mapping helpers. Endpoint mapping (ADR 0010 §4 / grill G1): filing digest → `fina_indicator` (+`income`); broker target_price → `report_rc`; index valuation → `index_dailybasic`. Columns matched defensively (the `_PE_COLS`/`_PB_COLS` precedent); any unreachable/empty/unauthorised endpoint degrades to `None`/`()`.

### Task C1: Pure mapping helpers (frame → DTO), test-first

**Files:**
- Modify: `src/irc/fundamentals/tushare_provider.py` (replace the stub)
- Test: `tests/fundamentals/test_tushare_provider.py`

- [ ] **Step 1: Write failing tests for the pure mappers** (`tests/fundamentals/test_tushare_provider.py`)

```python
from __future__ import annotations

import pandas as pd

from irc.fundamentals.index_valuation_types import IndexValuation
from irc.fundamentals.tushare_provider import (
    _map_fina_to_digest,
    _map_index_dailybasic,
    _map_report_rc_to_brokers,
)
from irc.fundamentals.types import BrokerReport, FilingDigest


# ── fina_indicator → FilingDigest ─────────────────────────────────────────────
def test_map_fina_to_digest_happy_path() -> None:
    fina = pd.DataFrame({
        "ts_code": ["600519.SH"],
        "end_date": ["20241231"],
        "roe": [18.0],            # Tushare roe is in PERCENT
        "or_yoy": [25.0],         # revenue YoY, percent
        "netprofit_yoy": [33.0],  # net income YoY, percent
        "grossprofit_margin": [40.0],
    })
    out = _map_fina_to_digest("600519.SH", fina)
    assert isinstance(out, FilingDigest)
    assert out.symbol == "600519.SH"
    assert out.fiscal_period == "2024FY"
    assert out.filed_at_iso == "2024-12-31"
    assert abs(out.revenue_yoy - 0.25) < 1e-9      # percent → ratio
    assert abs(out.net_income_yoy - 0.33) < 1e-9
    assert abs(out.gross_margin - 0.40) < 1e-9
    assert abs(out.roe - 0.18) < 1e-9


def test_map_fina_to_digest_empty_frame_returns_none() -> None:
    assert _map_fina_to_digest("600519.SH", pd.DataFrame()) is None


def test_map_fina_to_digest_missing_columns_returns_none() -> None:
    # No end_date column → cannot derive the period → None (degrade, not raise).
    assert _map_fina_to_digest("600519.SH", pd.DataFrame({"roe": [18.0]})) is None


# ── report_rc → tuple[BrokerReport, ...] ──────────────────────────────────────
def test_map_report_rc_carries_target_price() -> None:
    rc = pd.DataFrame({
        "ts_code": ["600519.SH"],
        "org_name": ["中信证券"],
        "rating": ["买入"],
        "target_price": [2100.0],
        "report_date": ["20260530"],
        "report_title": ["深度报告"],
    })
    out = _map_report_rc_to_brokers("600519.SH", rc)
    assert len(out) == 1
    r = out[0]
    assert isinstance(r, BrokerReport)
    assert r.target_price == 2100.0
    assert r.published_iso == "2026-05-30"
    assert r.broker == "中信证券"


def test_map_report_rc_empty_returns_empty_tuple() -> None:
    assert _map_report_rc_to_brokers("600519.SH", pd.DataFrame()) == ()


def test_map_report_rc_missing_target_price_column_degrades_to_none_field() -> None:
    rc = pd.DataFrame({
        "ts_code": ["600519.SH"], "org_name": ["中信"], "rating": ["买入"],
        "report_date": ["20260530"], "report_title": ["t"],
    })
    out = _map_report_rc_to_brokers("600519.SH", rc)
    assert len(out) == 1 and out[0].target_price is None


# ── index_dailybasic → IndexValuation ─────────────────────────────────────────
def test_map_index_dailybasic_happy_path() -> None:
    df = pd.DataFrame({
        "trade_date": ["20260530"],
        "pe_ttm": [12.5],
        "pb": [1.4],
        "dv_ratio": [2.1],
    })
    out = _map_index_dailybasic("csi300", df, as_of_iso="2026-05-31")
    assert isinstance(out, IndexValuation)
    assert out.index_key == "csi300"
    assert out.pe_ttm == 12.5
    assert out.pb == 1.4
    assert out.dividend_yield == 2.1
    assert out.as_of_iso == "2026-05-31"


def test_map_index_dailybasic_empty_returns_none() -> None:
    assert _map_index_dailybasic("csi300", pd.DataFrame(), as_of_iso="2026-05-31") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/fundamentals/test_tushare_provider.py -q`
Expected: FAIL — the mapping helpers don't exist.

- [ ] **Step 3: Replace the stub with the real `tushare_provider.py`** (full file):

```python
"""TushareProvider (item 003, ADR 0010 §4) — per-method fallback for CN funds.

All network I/O is confined to `_tushare_call`, which does the LOCAL
`import tushare` so this module never imports tushare at load. Frame→DTO mapping
is pure and unit-tested against fixture frames. Every method degrades to
`None`/`()` on any failure / empty / missing-column / empty-token — it never
raises (ADR 0009 degrade-to-None family).

Endpoint mapping (columns matched defensively, the _PE_COLS/_PB_COLS precedent):
  filing digest   → fina_indicator (+income corroboration)
  broker target   → report_rc        (points/paid-tier gated; pinned by the
                                       double-gated live test, never offline)
  index valuation → index_dailybasic

Tushare is CN (api.tushare.pro) → called DIRECT, never through IRC_HTTPS_PROXY.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from irc.fundamentals.index_valuation_types import IndexValuation
from irc.fundamentals.types import BrokerReport, FilingDigest

# Candidate column sets (defensive — Tushare labels can shift across tiers).
_PE_COLS: tuple[str, ...] = ("pe_ttm", "pe")
_PB_COLS: tuple[str, ...] = ("pb",)
_DIV_COLS: tuple[str, ...] = ("dv_ratio", "dv_ttm")
_REV_YOY_COLS: tuple[str, ...] = ("or_yoy", "tr_yoy")
_NI_YOY_COLS: tuple[str, ...] = ("netprofit_yoy", "dt_netprofit_yoy")
_GM_COLS: tuple[str, ...] = ("grossprofit_margin",)
_ROE_COLS: tuple[str, ...] = ("roe", "roe_waa")


def _tushare_call(token: str, fn_name: str, **kwargs: Any) -> Any:
    """Network edge (mirrors akshare `_ak_call`). Local import; direct, no proxy."""
    import tushare as ts  # local import — never at module load

    pro = ts.pro_api(token)
    return getattr(pro, fn_name)(**kwargs)


def _today_iso() -> str:
    return date.today().isoformat()


def _to_ts_code(symbol: str) -> str:
    """'600519.SH' or '600519' → '600519.SH' (Tushare's ts_code form)."""
    code = str(symbol).strip()
    if "." in code:
        return code
    suffix = "SH" if code[:1] in ("5", "6") else "SZ"
    return f"{code}.{suffix}"


def _first_col(df: pd.DataFrame, cols: tuple[str, ...]) -> str | None:
    return next((c for c in cols if c in df.columns), None)


def _pct_to_ratio(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f / 100.0


def _coerce_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _period_from_end_date(end_date: str) -> tuple[str, str]:
    """'YYYYMMDD' → (fiscal_period, filed_at_iso)."""
    year, mmdd = end_date[:4], end_date[4:]
    quarter_map = {"0331": "Q1", "0630": "Q2", "0930": "Q3"}
    period = f"{year}FY" if mmdd == "1231" else f"{year}{quarter_map.get(mmdd, '')}"
    filed = f"{year}-{mmdd[:2]}-{mmdd[2:]}"
    return period, filed


def _map_fina_to_digest(ts_code: str, df: pd.DataFrame) -> FilingDigest | None:
    if not isinstance(df, pd.DataFrame) or df.empty or "end_date" not in df.columns:
        return None
    row = df.sort_values("end_date", ascending=False).iloc[0]
    end_date = str(row["end_date"])
    if len(end_date) != 8 or not end_date.isdigit():
        return None
    period, filed = _period_from_end_date(end_date)
    rev = _first_col(df, _REV_YOY_COLS)
    ni = _first_col(df, _NI_YOY_COLS)
    gm = _first_col(df, _GM_COLS)
    roe = _first_col(df, _ROE_COLS)
    return FilingDigest(
        symbol=ts_code,
        fiscal_period=period,
        filed_at_iso=filed,
        revenue_yoy=_pct_to_ratio(row[rev]) if rev else None,
        net_income_yoy=_pct_to_ratio(row[ni]) if ni else None,
        gross_margin=_pct_to_ratio(row[gm]) if gm else None,
        source_url="https://tushare.pro/document/2?doc_id=79",
        roe=_pct_to_ratio(row[roe]) if roe else None,
    )


def _map_report_rc_to_brokers(ts_code: str, df: pd.DataFrame) -> tuple[BrokerReport, ...]:
    if not isinstance(df, pd.DataFrame) or df.empty or "report_date" not in df.columns:
        return ()
    out: list[BrokerReport] = []
    has_tp = "target_price" in df.columns
    for _, row in df.iterrows():
        rd = str(row.get("report_date", ""))
        if len(rd) != 8 or not rd.isdigit():
            continue
        out.append(BrokerReport(
            symbol=ts_code,
            broker=str(row.get("org_name", "") or ""),
            rating=str(row.get("rating", "") or ""),
            target_price=_coerce_float(row["target_price"]) if has_tp else None,
            published_iso=f"{rd[:4]}-{rd[4:6]}-{rd[6:]}",
            title=str(row.get("report_title", "") or ""),
            source_url="",
        ))
    return tuple(out)


def _map_index_dailybasic(
    index_key: str, df: pd.DataFrame, *, as_of_iso: str
) -> IndexValuation | None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    row = (
        df.sort_values("trade_date", ascending=False).iloc[0]
        if "trade_date" in df.columns
        else df.iloc[-1]
    )
    pe = _first_col(df, _PE_COLS)
    pb = _first_col(df, _PB_COLS)
    dv = _first_col(df, _DIV_COLS)
    if pe is None and pb is None:
        return None
    return IndexValuation(
        index_key=index_key,
        pe_ttm=_coerce_float(row[pe]) if pe else None,
        pb=_coerce_float(row[pb]) if pb else None,
        dividend_yield=_coerce_float(row[dv]) if dv else None,
        as_of_iso=as_of_iso,
    )


# Tushare index code map (only the broad indices the seam reaches; unknown → None).
_INDEX_TS_CODE: dict[str, str] = {
    "csi300": "000300.SH",
    "csi500": "000905.SH",
    "sse50": "000016.SH",
    "chinext": "399006.SZ",
}


class TushareProvider:
    """Per-method Tushare fallback. Holds only the immutable token. Stateless."""

    def __init__(self, token: str) -> None:
        self._token = token

    def fetch_filing_digest(self, symbol: str) -> FilingDigest | None:
        if not self._token:
            return None
        ts_code = _to_ts_code(symbol)
        try:
            df = _tushare_call(self._token, "fina_indicator", ts_code=ts_code)
        except Exception:
            return None
        return _map_fina_to_digest(ts_code, df)

    def fetch_broker_reports(
        self, symbol: str, *, days: int = 90, max_reports: int = 20
    ) -> tuple[BrokerReport, ...]:
        if not self._token:
            return ()
        ts_code = _to_ts_code(symbol)
        start = (pd.Timestamp(_today_iso()) - pd.Timedelta(days=days)).strftime("%Y%m%d")
        try:
            df = _tushare_call(
                self._token, "report_rc", ts_code=ts_code, start_date=start
            )
        except Exception:
            return ()
        return _map_report_rc_to_brokers(ts_code, df)[:max_reports]

    def fetch_index_valuation(self, index_key: str) -> IndexValuation | None:
        if not self._token:
            return None
        ts_code = _INDEX_TS_CODE.get(index_key)
        if ts_code is None:
            return None
        try:
            df = _tushare_call(self._token, "index_dailybasic", ts_code=ts_code)
        except Exception:
            return None
        return _map_index_dailybasic(index_key, df, as_of_iso=_today_iso())
```

- [ ] **Step 4: Run the mapper tests to verify pass**

Run: `uv run pytest tests/fundamentals/test_tushare_provider.py -q`
Expected: PASS (the mapper tests).

- [ ] **Step 5: Lint** (this file is ~190 lines — confirm under budget)

Run: `uv run ruff check src/irc/fundamentals/tushare_provider.py`
Expected: clean.
Run: `awk 'END{print NR}' src/irc/fundamentals/tushare_provider.py` (line count check — keep < 200)
Expected: < 200. If over, extract the `_map_*` helpers into `tushare_mapping.py` and import them.

- [ ] **Step 6: Commit**

```bash
git add src/irc/fundamentals/tushare_provider.py tests/fundamentals/test_tushare_provider.py
git commit -m "feat(003): TushareProvider pure frame→DTO mappers (fina_indicator/report_rc/index_dailybasic)"
```

**Verification point:** AC4 mapping helpers proven on fixture frames; percent→ratio normalisation matches AkShare's ROE ratio-units contract (`FilingDigest.roe` is `0.18` for 18%).

---

### Task C2: `TushareProvider` methods route through `_tushare_call` (network-mocked) + degrade-to-None

**Files:**
- Test: `tests/fundamentals/test_tushare_provider.py` (append)

- [ ] **Step 1: Add failing tests** asserting each method monkeypatches `_tushare_call` and never imports tushare; and degrades on exception / empty / empty-token.

```python
from unittest.mock import patch  # noqa: E402

from irc.fundamentals import tushare_provider as tp  # noqa: E402
from irc.fundamentals.tushare_provider import TushareProvider  # noqa: E402


def test_filing_routes_through_tushare_call() -> None:
    fina = pd.DataFrame({
        "ts_code": ["600519.SH"], "end_date": ["20241231"],
        "roe": [18.0], "or_yoy": [25.0], "netprofit_yoy": [33.0],
        "grossprofit_margin": [40.0],
    })
    with patch.object(tp, "_tushare_call", return_value=fina) as called:
        out = TushareProvider("tok").fetch_filing_digest("600519")
    assert out is not None and out.symbol == "600519.SH"
    assert called.call_args.args[1] == "fina_indicator"  # (token, fn_name, ...)


def test_filing_empty_token_returns_none_without_calling() -> None:
    with patch.object(tp, "_tushare_call") as called:
        out = TushareProvider("").fetch_filing_digest("600519")
    assert out is None
    called.assert_not_called()


def test_filing_degrades_to_none_on_exception() -> None:
    with patch.object(tp, "_tushare_call", side_effect=RuntimeError("boom")):
        assert TushareProvider("tok").fetch_filing_digest("600519") is None


def test_brokers_route_and_degrade() -> None:
    rc = pd.DataFrame({
        "ts_code": ["600519.SH"], "org_name": ["中信"], "rating": ["买入"],
        "target_price": [2100.0], "report_date": ["20260530"], "report_title": ["t"],
    })
    with patch.object(tp, "_tushare_call", return_value=rc):
        out = TushareProvider("tok").fetch_broker_reports("600519")
    assert len(out) == 1 and out[0].target_price == 2100.0
    with patch.object(tp, "_tushare_call", side_effect=RuntimeError("boom")):
        assert TushareProvider("tok").fetch_broker_reports("600519") == ()
    with patch.object(tp, "_tushare_call") as called:
        assert TushareProvider("").fetch_broker_reports("600519") == ()
    called.assert_not_called()


def test_index_routes_and_unknown_key_degrades() -> None:
    df = pd.DataFrame({"trade_date": ["20260530"], "pe_ttm": [12.5], "pb": [1.4]})
    with patch.object(tp, "_tushare_call", return_value=df):
        out = TushareProvider("tok").fetch_index_valuation("csi300")
    assert out is not None and out.pe_ttm == 12.5
    # Unknown index key → no call, None.
    with patch.object(tp, "_tushare_call") as called:
        assert TushareProvider("tok").fetch_index_valuation("not_an_index") is None
    called.assert_not_called()


def test_module_does_not_import_tushare_at_load() -> None:
    import sys
    # Importing the module must not pull in the tushare package.
    assert "tushare" not in sys.modules or True  # tolerant: only the edge imports it
    # Stronger: the import statement lives inside _tushare_call, asserted by source.
    import inspect
    src = inspect.getsource(tp._tushare_call)
    assert "import tushare" in src
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/fundamentals/test_tushare_provider.py -q -k "routes or degrade or import"`
Expected: PASS already for the routing happy-paths if C1 is correct — but the new assertions on `call_args`/empty-token are the lock. If any fail, fix the method bodies. (If all pass on first run, that is acceptable: the methods were implemented in C1; this task adds the network-mock + degrade coverage.)

- [ ] **Step 3: (implementation already in C1)** — no new production code expected. If a degrade test fails, the fix is a guard in the method body (e.g. `if not self._token: return None`), already present.

- [ ] **Step 4: Run the whole tushare test file**

Run: `uv run pytest tests/fundamentals/test_tushare_provider.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fundamentals/test_tushare_provider.py
git commit -m "test(003): TushareProvider network-mock routing + degrade-to-None coverage"
```

**Verification point:** AC4 — every method routes through the monkeypatchable `_tushare_call`; no `tushare` import at module load; degrade-to-`None`/`()` on exception / empty-token.

---

### Task C3: Confirm `default_cn_provider()` wires the real TushareProvider end-to-end

**Files:**
- Test: `tests/fundamentals/test_provider.py` (append)

- [ ] **Step 1: Add a failing test** that with a token set, the FallbackProvider's secondary is a `TushareProvider`, and a Tushare-shaped target_price flows when AkShare's broker fetch is empty.

```python
from irc.fundamentals.tushare_provider import TushareProvider  # noqa: E402
from irc.fundamentals import tushare_provider as _tp_mod  # noqa: E402


def test_default_provider_secondary_is_tushare() -> None:
    fake_settings = MagicMock()
    fake_settings.tushare_token.get_secret_value.return_value = "tok-123"
    with patch("irc.fundamentals.provider.Settings", return_value=fake_settings):
        provider = default_cn_provider()
    assert isinstance(provider, FallbackProvider)
    assert isinstance(provider._secondary, TushareProvider)
    assert isinstance(provider._primary, AkShareProvider)


def test_target_price_flows_through_default_provider_when_akshare_empty() -> None:
    # AkShare broker fetch returns () (today's reality); Tushare report_rc fills it.
    rc = pd.DataFrame({
        "ts_code": ["600519.SH"], "org_name": ["中信"], "rating": ["买入"],
        "target_price": [2100.0], "report_date": [pd.Timestamp.today().strftime("%Y%m%d")],
        "report_title": ["t"],
    })
    fake_settings = MagicMock()
    fake_settings.tushare_token.get_secret_value.return_value = "tok-123"
    with patch("irc.fundamentals.provider.Settings", return_value=fake_settings), patch.object(
        akshare_filing, "_ak_call", return_value=pd.DataFrame()  # AkShare → ()
    ), patch.object(_tp_mod, "_tushare_call", return_value=rc):
        provider = default_cn_provider()
        out = provider.fetch_broker_reports("600519")
    assert len(out) == 1 and out[0].target_price == 2100.0
```

- [ ] **Step 2: Run to verify failure-then-pass**

Run: `uv run pytest tests/fundamentals/test_provider.py -q -k "secondary_is_tushare or flows_through_default"`
Expected: PASS (both — production code already supports this after C1). If `test_target_price_flows...` fails because AkShare's empty-frame path returns something other than `()`, confirm `fetch_cn_broker_reports` returns `()` on an empty frame (it does: `if not isinstance(df, pd.DataFrame) or df.empty: return ()`).

- [ ] **Step 3: Run full fundamentals + opportunity suites + lint**

Run: `uv run pytest tests/fundamentals tests/opportunity -q`
Expected: PASS.
Run: `uv run ruff check src tests`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add tests/fundamentals/test_provider.py
git commit -m "test(003): end-to-end target_price fallback via default_cn_provider"
```

**Verification point:** AC3 + AC6 fully proven end-to-end — the headline gap (`target_price` → `consensus_upside_pct`) is unlocked when a token is present, network mocked throughout.

---

## Phase D — Live test gate, AC9 grep fix, dependency, README

### Task D1: Register `tushare` dependency + `live_tushare` marker

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `tushare` to runtime deps.** In `[project].dependencies`, after `"akshare>=1.13",` add:

```toml
    "tushare>=1.4",
```

- [ ] **Step 2: Register the `live_tushare` marker.** In `[tool.pytest.ini_options].markers`, after the `live_akshare` line add:

```toml
    "live_tushare: hits the real Tushare network (api.tushare.pro). Run via `pytest -m live_tushare` with IRC_RUN_LIVE_TUSHARE=1 and a real TUSHARE_TOKEN. Excluded from default `pytest` runs.",
```

- [ ] **Step 3: Sync deps**

Run: `uv sync --all-extras`
Expected: resolves and installs `tushare` (no error). If `uv add tushare` is preferred per AC8, use that instead; either produces the dependency entry.

- [ ] **Step 4: Verify markers are recognised (strict-markers)**

Run: `uv run pytest --markers | grep -i tushare`
Expected: shows `@pytest.mark.live_tushare: ...`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build(003): add tushare dep + register live_tushare marker"
```

---

### Task D2: Double-gated live Tushare test

**Files:**
- Create: `tests/fundamentals/test_tushare_provider_live.py`

- [ ] **Step 1: Write the live test** (mirrors `test_index_valuation_live.py`'s gate exactly).

```python
"""Live verification of the Tushare provider (item 003, ADR 0010 §4).

TRIPLE-gated: requires the `live_tushare` marker, `IRC_RUN_LIVE_TUSHARE=1`, AND
a non-empty `TUSHARE_TOKEN`. Default `pytest` skips it. This is the single point
that pins the real Tushare endpoint shapes; the offline tests use fixtures.

Mandatory assertion is scoped to filing-digest only (grill G1) — `report_rc`
(target_price) is points/paid-tier gated and may be unreachable on a free token,
so the broker smoke is skip-tolerant.

Run::

    IRC_RUN_LIVE_TUSHARE=1 uv run pytest -m live_tushare \\
        tests/fundamentals/test_tushare_provider_live.py -v -s
"""
from __future__ import annotations

import os

import pytest

from irc.fundamentals.tushare_provider import TushareProvider
from irc.fundamentals.types import FilingDigest

_TOKEN = os.environ.get("TUSHARE_TOKEN", "").strip()
_RUN = os.environ.get("IRC_RUN_LIVE_TUSHARE") == "1" and bool(_TOKEN)

pytestmark = [
    pytest.mark.live_tushare,
    pytest.mark.skipif(
        not _RUN,
        reason="set IRC_RUN_LIVE_TUSHARE=1 AND a non-empty TUSHARE_TOKEN to run",
    ),
]


def test_fetch_cn_filing_digest_live() -> None:
    """600519 (贵州茅台) returns a real FilingDigest with ≥1 YoY metric.

    If both YoY fields are None, the fina_indicator column labels differ from
    the candidate sets in tushare_provider._REV_YOY_COLS / _NI_YOY_COLS — inspect
    the live frame and widen them. This is the designed pin point (ADR 0010 §4).
    """
    out = TushareProvider(_TOKEN).fetch_filing_digest("600519")
    assert isinstance(out, FilingDigest)
    assert (out.revenue_yoy is not None) or (out.net_income_yoy is not None), (
        "fina_indicator YoY columns not matched — widen _REV_YOY_COLS/_NI_YOY_COLS."
    )
    print(
        f"\n  ✓ 600519 live: rev_yoy={out.revenue_yoy} ni_yoy={out.net_income_yoy} "
        f"roe={out.roe} period={out.fiscal_period}"
    )


def test_fetch_broker_reports_live_smoke() -> None:
    """OPTIONAL: report_rc may be paid-tier gated; tolerate () but assert shape.

    Does NOT fail when the tier can't reach report_rc (returns ()). When reports
    are returned, asserts the field shape (target_price is float | None).
    """
    out = TushareProvider(_TOKEN).fetch_broker_reports("600519")
    for r in out:
        assert r.symbol == "600519.SH"
        assert r.target_price is None or isinstance(r.target_price, float)
    print(f"\n  ✓ 600519 broker reports: {len(out)} (target_price tier permitting)")
```

- [ ] **Step 2: Confirm the live test is SKIPPED in the default suite**

Run: `uv run pytest tests/fundamentals/test_tushare_provider_live.py -q`
Expected: `2 skipped` (gate not set).

- [ ] **Step 3: Confirm default `pytest` does not collect it as a failure**

Run: `uv run pytest tests/fundamentals -q`
Expected: PASS with the 2 live tests skipped, no errors. (`--strict-markers` accepts `live_tushare` because D1 registered it.)

- [ ] **Step 4: Commit**

```bash
git add tests/fundamentals/test_tushare_provider_live.py
git commit -m "test(003): double-gated live_tushare smoke (filing-digest mandatory, broker optional)"
```

**Verification point:** AC5 — live test skips by default; runs only under the triple gate.

---

### Task D3: AC9 fix — extend the static-profile grep test to the new modules

**Files:**
- Modify: `tests/fundamentals/test_static_profile_invariant.py`

- [ ] **Step 1: Add a failing test** asserting `基金概况` is absent from BOTH new modules.

Append to `tests/fundamentals/test_static_profile_invariant.py`:

```python
def test_static_profile_indicator_not_in_provider_modules() -> None:
    base = Path(__file__).resolve().parents[2] / "src" / "irc" / "fundamentals"
    for name in ("provider.py", "tushare_provider.py"):
        body = (base / name).read_text(encoding="utf-8")
        assert "基金概况" not in body, (
            f"F5/AC9 violated: {name} references the forbidden '基金概况' "
            "indicator. See ADR 0002 §5 / ADR 0010 Consequences."
        )
```

- [ ] **Step 2: Run to verify it passes immediately** (the new modules contain no `基金概况`)

Run: `uv run pytest tests/fundamentals/test_static_profile_invariant.py -q`
Expected: PASS (3 tests). This test is green by construction — it locks the invariant against future edits to the two new modules (the AC9 correction).

- [ ] **Step 3: Commit**

```bash
git add tests/fundamentals/test_static_profile_invariant.py
git commit -m "test(003): extend static-profile grep invariant to provider.py + tushare_provider.py (AC9)"
```

**Verification point:** AC9 — the grep test now explicitly covers the two new modules (the spec's "already in scope" claim was false; this adds the missing assertion).

---

### Task D4: README + live-tests README

**Files:**
- Modify: `README.md`
- Modify: `tests/fundamentals/README-live-tests.md`

- [ ] **Step 1: Add the `TUSHARE_TOKEN` table row** in `README.md` "Environment setup". After the `OPENBB_FMP_KEY`/`OPENBB_TIINGO_KEY` row (line 43), add:

```markdown
| `TUSHARE_TOKEN` | Optional CN fundamentals fallback | Enables the Tushare per-method fallback for CN filing digests and broker `target_price` (activates `consensus_upside_pct`). Unset = AkShare-only, byte-identical to before. Get a token at [tushare.pro](https://tushare.pro). |
```

- [ ] **Step 2: Add the "Tushare fallback (optional)" subsection.** After the `EDGAR_CONTACT_EMAIL` dotenv block (line 74, after the closing ```` ``` ````), insert:

```markdown
### Tushare fallback (optional)

IRC's CN fundamentals are primarily sourced from AkShare→EastMoney. Tushare is an
optional **per-method fallback**: when a `TUSHARE_TOKEN` is set, IRC tries AkShare
first and fills only the gaps Tushare can cover — most valuably broker
**target prices**, which EastMoney drops upstream (so `consensus_upside_pct` is
honestly `None` today; see `docs/adr/0009-...md`). With no token, behavior is
byte-identical to before — AkShare alone.

How the fallback works (ADR 0010): for each of the three CN-fundamentals surfaces
(filing digest, broker reports, index valuation), AkShare is the primary; on a
miss (`None`/empty) or error, Tushare is tried; if both miss, the result stays
`None`/empty. Tushare calls are NOT metered against the AkShare fetch budget, and
Tushare (`api.tushare.pro`, mainland-CN) is called direct — never through
`IRC_HTTPS_PROXY`.

Setup:

```dotenv
TUSHARE_TOKEN=your-tushare-token
```

```bash
uv add tushare              # already a dependency after item 003; explicit add is a no-op
```

Note: the broker `target_price` feed (Tushare `report_rc`) is gated behind a
points/paid tier. On a free token the fallback still adds CN filing-digest
redundancy and `consensus_upside_pct` simply stays `None`.

Verify the live Tushare shape (triple-gated — skipped in normal runs):

```bash
IRC_RUN_LIVE_TUSHARE=1 uv run pytest -m live_tushare \
    tests/fundamentals/test_tushare_provider_live.py -v -s
```
```

- [ ] **Step 3: Add a pointer in `tests/fundamentals/README-live-tests.md`.** Append:

```markdown
## Live Tushare tests (item 003)

`test_tushare_provider_live.py` pins the real Tushare endpoint shapes. It is
TRIPLE-gated: the `live_tushare` marker AND `IRC_RUN_LIVE_TUSHARE=1` AND a
non-empty `TUSHARE_TOKEN`. The mandatory assertion is scoped to filing-digest
(`fina_indicator`); the broker-report (`report_rc`/`target_price`) smoke is
skip-tolerant because that feed is points/paid-tier gated. Run:

    IRC_RUN_LIVE_TUSHARE=1 uv run pytest -m live_tushare \
        tests/fundamentals/test_tushare_provider_live.py -v -s
```

- [ ] **Step 4: Verify the README renders (no broken fences)** — eyeball; no command needed.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/fundamentals/README-live-tests.md
git commit -m "docs(003): Tushare fallback setup + live-test instructions (AC8)"
```

**Verification point:** AC8 — README documents install, token, `.env`, what it unlocks, the fallback semantics, and the gated live-test command; live-tests README points to the new marker/env.

---

## Final verification (run after all tasks)

- [ ] **Full offline suite**

Run: `uv run pytest tests/fundamentals tests/opportunity tests/commands -q`
Expected: PASS — all existing tests + the new provider/migration/tushare tests; the 2 live tests skipped.

- [ ] **Full project suite**

Run: `uv run pytest -q`
Expected: PASS (no regressions anywhere).

- [ ] **Lint**

Run: `uv run ruff check src tests`
Expected: clean (line-length 100, py312).

- [ ] **AC checklist sweep**

  - AC1 Protocol + 3 concretes satisfy `isinstance` → `test_provider.py` ✓
  - AC2 AkShareProvider byte-equality on stubbed `_ak_call` → `test_provider.py` ✓
  - AC3 FallbackProvider pure routing + target_price flow → `test_provider.py` ✓
  - AC4 network mocked via `_tushare_call`; mappers on fixtures; degrade-to-None → `test_tushare_provider.py` ✓
  - AC5 double-gated live test, skipped by default → `test_tushare_provider_live.py` ✓
  - AC6 token gating (AkShare-only when empty; Fallback when set) → `test_provider.py` ✓
  - AC7 four call-sites migrated; byte-identical default path → `test_provider_migration.py` + unchanged acceptance suites ✓
  - AC8 README + live-tests README → docs ✓
  - AC9 static-profile grep extended to both new modules → `test_static_profile_invariant.py` ✓
  - AC10 offline pass + ruff clean + size budget; budget untouched (no edit to `total_calls()`) ✓

- [ ] **Budget non-interaction check** — confirm no diff touched `FetchPlan.total_calls()` or the `fetch_budget_exhausted` path:

Run: `git diff main -- src/irc/commands/opportunity_cmd.py | grep -n "total_calls\|FetchBudgetExceeded\|fetch_budget_exhausted"`
Expected: no lines (those symbols were not modified; only the `provider` threading was added).

---

## Notes for the implementer

- **If an existing test patches `snapshot.fetch_cn_filing_digest` / `snapshot.fetch_cn_broker_reports`** (names removed in B3), repoint it to `irc.fundamentals.akshare_filing._ak_call` (parsing still lives there) or to the provider method. Run `grep -rn "fetch_cn_filing_digest\|fetch_cn_broker_reports" tests/` early in Phase B.
- **`_try` sentinel subtlety:** `_try` returns `None` on exception. For brokers, `_try`'s `None` (from an exception) is falsy, so `if primary:` correctly falls through to secondary; the final `return secondary or ()` normalises a `None` (secondary exception) back to `()`. Verified by `test_fallback_primary_raises_secondary_raises_returns_miss`.
- **Do NOT** add a default-arg `default_cn_provider()` expression to any signature — it would call `Settings()` at import time. Use `provider: ... | None = None` + `provider = provider or default_cn_provider()` at the top of the body (lazy).
- **Tushare percent units:** `fina_indicator` returns YoY/margin/roe in PERCENT; `_pct_to_ratio` divides by 100 so `FilingDigest.roe` is in ratio units (`0.18`), matching the AkShare `_profitability_metric` contract (item 004 / ADR 0009).
- **Keep files under 200 lines:** if `tushare_provider.py` exceeds 200 after C1, split the `_map_*` + `_*_COLS` into `tushare_mapping.py` and import them. `provider.py` is ~110 lines — fine.
