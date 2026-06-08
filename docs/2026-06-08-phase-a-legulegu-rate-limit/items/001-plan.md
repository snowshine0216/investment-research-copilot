# Phase A — legulegu broad-leg rate-limit hardening + PB-wipe guard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 8-call legulegu broad-index PE/PB ingest leg polite — pace before every call, retry network blips per-symbol, suspend the whole sweep (non-destructively) when the throttle signature recurs — and add a both-axes guard so a half-frame can never wipe good cached PE/PB.

**Architecture:** A new self-contained `legulegu_fetch.py` primitive owns paced dual-policy retry (effects injected: `ak_call` passed in, `_sleep` a module indirection). `akshare_index_valuation.py` routes its four legulegu calls through it, preserving a deliberate raise/catch asymmetry (`_history` raises `LeguleguCooldownExhausted`; the single-shot `fetch_cn_index_valuation` catches → `None`). The ingestor catches the suspension signal to `break` the per-key loop and adds the both-axes guard before its destructive DELETE+replace.

**Tech Stack:** Python 3.12, pandas, `requests` (2.33.1, simplejson-backed), AkShare 1.18.60, DuckDB, pytest, uv.

---

## CRITICAL scope clamps (read before any step)

- **OFFLINE ONLY.** Every test run in this plan is offline: fake `ak_call` + injected fake `_sleep`. **Do NOT run any live test.** The live-network gates #3/#4/#5 (`IRC_RUN_LIVE_AKSHARE=1`) are **deferred operator follow-up — NOT plan steps.** Task 6 edits `test_index_valuation_live.py` source only; it must NOT execute it.
- **Preserve the raise/catch asymmetry (ADR 0014 D3).** `fetch_cn_index_valuation_history` (ingest path) **raises** `LeguleguCooldownExhausted`. `fetch_cn_index_valuation` (provider/single-shot path) **catches it → returns `None`** (never-raises seam, ADR 0010). Do **not** unify them.
- **csindex sector call stays on `_fetch_frame`** — single static-Excel GET, no burst limiter. Do not pace it.
- **Constants are hardcoded judgment values, no env knob:** `_LEGULEGU_GAP_S=4.0`, `_LEGULEGU_NETWORK_ATTEMPTS=3`, `_LEGULEGU_BACKOFF_S=3.0`, `_LEGULEGU_COOLDOWN_S=30.0`, `_LEGULEGU_COOLDOWN_RETRIES=1`.
- **`VERSION` stays `0.9.3`** — changes go under CHANGELOG `[Unreleased]`.
- **CLAUDE.md conventions:** TDD red→green, pure functions, effects at edges, files <200 lines / functions <20 lines ideal, `_sleep` as module indirection, `ak_call` injected.

### Verified facts this plan depends on (do not re-derive — already checked against the live tree)

- `_is_transient_network_error` lives in **`src/irc/data/akshare_client.py:81`** (NOT `fundamentals/akshare_client.py` as the spec prose says — spec gap, resolved here). Import path: `from irc.data.akshare_client import _is_transient_network_error`.
- **`requests.exceptions.ConnectionError` / `Timeout` are NOT subclasses of builtin `ConnectionError` / `TimeoutError`** (MRO → `RequestException` → `OSError`). Verified. So `legulegu_fetch._is_network_transient` must add the `requests` classes explicitly.
- **`requests.exceptions.JSONDecodeError` is NOT a subclass of `json.JSONDecodeError`** in this env — requests 2.33.1 is built against `simplejson`, so `requests.exceptions.JSONDecodeError` extends `simplejson.errors.JSONDecodeError`. Verified: `isinstance(requests_jde_instance, json.JSONDecodeError)` returns **False**. **This is a spec gap.** The spec's `_is_throttle_signature` body `return isinstance(exc, json.JSONDecodeError)` would MISS the real throttle surface AkShare raises (`r.json()` → `requests.exceptions.JSONDecodeError`). **Resolution (judgment call, spec §Architecture.1 + §Testing):** the classifier checks `isinstance(exc, (json.JSONDecodeError, requests.exceptions.JSONDecodeError))`. This keeps the spec's intent (both `json` and `requests` JSON-decode surfaces are throttle) and matches the test list which asserts both are throttle.
- `src/irc/data/index_valuation_ingestor.py` currently has **no logger** — Task 4 adds `import logging` + `_log = logging.getLogger(__name__)`.
- The 2 RED wiring tests are confirmed failing on `_BROAD_INDEX_KEYS`. `_SECTOR_INDEX_KEYS` is imported in `ingest_cmd` from `irc.opportunity.lookthrough`, and the production broad-leg uses `_LEGULEGU_INDEX_SYMBOL` (`ingest_cmd.py:578`) + `replace_keys=True` (`:580`).
- `akshare` is 1.18.60; `requests` is 2.33.1 in the active venv.

---

## File map

- **Create:** `src/irc/fundamentals/legulegu_fetch.py` — paced dual-policy retry primitive + `LeguleguCooldownExhausted`.
- **Create:** `tests/fundamentals/test_legulegu_fetch.py` — offline classifier + sleep-sequence tests.
- **Modify:** `src/irc/fundamentals/akshare_index_valuation.py` — route 4 legulegu calls through `fetch_legulegu_frame`; scope the module docstring's "never-raises" wording; catch in single-shot, propagate in `_history`.
- **Modify:** `src/irc/data/index_valuation_ingestor.py` — add logger; both-axes guard + audit WARNING; catch `LeguleguCooldownExhausted` → `break` + WARNING.
- **Modify:** `tests/data/test_index_valuation_ingestor.py` — add sweep-suspension regression + inverted PE-only guard test + caplog warning-contract assertions.
- **Modify:** `tests/commands/test_ingest_index_valuation_wiring.py` — repair the 2 RED tests to assert the real surface.
- **Modify:** `tests/fundamentals/test_akshare_index_valuation.py` — no-sleep autouse fixture + paced/unpaced routing pin.
- **Modify:** `tests/fundamentals/test_provider.py` — no-sleep autouse fixture.
- **Modify:** `tests/fundamentals/test_index_valuation_live.py` — `IRC_RUN_LEGULEGU_SPECULATIVE=1` gate + route speculative sweep through `fetch_legulegu_frame` (source edit only, NOT executed).
- **Modify:** `CHANGELOG.md` — `[Unreleased]` sub-bullet (VERSION stays 0.9.3).

---

## Task 1: New `legulegu_fetch.py` primitive (TDD)

**Files:**
- Create: `tests/fundamentals/test_legulegu_fetch.py`
- Create: `src/irc/fundamentals/legulegu_fetch.py`

- [ ] **Step 1: Write the failing test file**

Create `tests/fundamentals/test_legulegu_fetch.py`:

```python
from __future__ import annotations

import json
import logging

import pandas as pd
import pytest
import requests

from irc.fundamentals.legulegu_fetch import (
    LeguleguCooldownExhausted,
    _LEGULEGU_BACKOFF_S,
    _LEGULEGU_COOLDOWN_RETRIES,
    _LEGULEGU_COOLDOWN_S,
    _LEGULEGU_GAP_S,
    _LEGULEGU_NETWORK_ATTEMPTS,
    _is_network_transient,
    _is_throttle_signature,
    fetch_legulegu_frame,
)


# ---- constants are the locked judgment values ----

def test_constants_are_locked_judgment_values() -> None:
    assert _LEGULEGU_GAP_S == 4.0
    assert _LEGULEGU_NETWORK_ATTEMPTS == 3
    assert _LEGULEGU_BACKOFF_S == 3.0
    assert _LEGULEGU_COOLDOWN_S == 30.0
    assert _LEGULEGU_COOLDOWN_RETRIES == 1


# ---- throttle classifier ----

def test_missing_csrf_attribute_error_is_throttle() -> None:
    exc = AttributeError("'NoneType' object has no attribute 'attrs'")
    assert _is_throttle_signature(exc) is True


def test_stdlib_json_decode_error_is_throttle() -> None:
    exc = json.JSONDecodeError("Expecting value", "<html>", 0)
    assert _is_throttle_signature(exc) is True


def test_requests_json_decode_error_is_throttle() -> None:
    # requests 2.33.1 builds against simplejson, so requests.JSONDecodeError is
    # NOT a json.JSONDecodeError subclass — the classifier must match it explicitly.
    exc = requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0)
    assert _is_throttle_signature(exc) is True


def test_attribute_error_without_nonetype_is_fatal() -> None:
    # A genuine parser/schema change can also trip an AttributeError on .attrs,
    # but only the missing-CSRF surface carries BOTH 'NoneType' and 'attrs'.
    exc = AttributeError("widget has no attribute 'attrs'")
    assert _is_throttle_signature(exc) is False


def test_plain_value_error_is_fatal() -> None:
    assert _is_throttle_signature(ValueError("boom")) is False


def test_key_error_data_envelope_is_fatal() -> None:
    # documented blind spot (ADR 0014 D2/Q2b): a JSON error envelope raises
    # KeyError('data') and is deliberately FATAL, not throttle.
    assert _is_throttle_signature(KeyError("data")) is False


# ---- network classifier ----

def test_requests_connection_error_is_network() -> None:
    assert _is_network_transient(requests.exceptions.ConnectionError("reset")) is True


def test_requests_timeout_is_network() -> None:
    assert _is_network_transient(requests.exceptions.Timeout("slow")) is True


def test_builtin_connection_error_is_network() -> None:
    assert _is_network_transient(ConnectionError("reset")) is True


def test_value_error_is_not_network() -> None:
    assert _is_network_transient(ValueError("nope")) is False


# ---- fetch_legulegu_frame sleep sequences (the heart of the spec) ----

class _Recorder:
    """Records the args fed to the injected fake _sleep."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _patch_sleep(monkeypatch, recorder: _Recorder) -> None:
    monkeypatch.setattr("irc.fundamentals.legulegu_fetch._sleep", recorder)


_FRAME = pd.DataFrame({"日期": ["2026-06-08"], "滚动市盈率": [12.1]})


def test_network_success_on_third_attempt(monkeypatch) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)
    calls = {"n": 0}

    def ak_call(fn_name, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.exceptions.ConnectionError("reset")
        return _FRAME

    out = fetch_legulegu_frame(ak_call, "stock_index_pe_lg", "沪深300")
    assert out is _FRAME
    # GAP before each attempt; backoff 3 then 6 between the 3 attempts.
    assert rec.sleeps == [4.0, 3.0, 4.0, 6.0, 4.0]


def test_network_exhausts_returns_none(monkeypatch, caplog) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)

    def ak_call(fn_name, **kwargs):
        raise requests.exceptions.ConnectionError("reset")

    with caplog.at_level(logging.WARNING):
        out = fetch_legulegu_frame(ak_call, "stock_index_pe_lg", "沪深300")
    assert out is None
    assert rec.sleeps == [4.0, 3.0, 4.0, 6.0, 4.0]  # 3 attempts, 2 backoffs
    assert sum(1 for r in caplog.records if r.levelno == logging.WARNING) == 1


def test_throttle_success_on_retry(monkeypatch) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)
    calls = {"n": 0}

    def ak_call(fn_name, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise AttributeError("'NoneType' object has no attribute 'attrs'")
        return _FRAME

    out = fetch_legulegu_frame(ak_call, "stock_index_pe_lg", "沪深300")
    assert out is _FRAME
    assert rec.sleeps == [4.0, 30.0, 4.0]  # GAP, cooldown, GAP-before-retry


def test_throttle_exhausts_raises(monkeypatch) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)
    calls = {"n": 0}

    def ak_call(fn_name, **kwargs):
        calls["n"] += 1
        raise AttributeError("'NoneType' object has no attribute 'attrs'")

    with pytest.raises(LeguleguCooldownExhausted):
        fetch_legulegu_frame(ak_call, "stock_index_pe_lg", "沪深300")
    assert calls["n"] == 2  # initial + one cooldown retry, then suspend
    assert rec.sleeps == [4.0, 30.0, 4.0]  # no second cooldown wait


def test_success_non_dataframe_returns_empty_frame(monkeypatch) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)

    out = fetch_legulegu_frame(lambda fn, **kw: "not a frame", "stock_index_pe_lg", "沪深300")
    assert isinstance(out, pd.DataFrame)
    assert out.empty
    assert rec.sleeps == [4.0]  # one GAP, one attempt


def test_fatal_error_returns_none_no_retry(monkeypatch, caplog) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)

    def ak_call(fn_name, **kwargs):
        raise KeyError("data")  # documented blind spot → fatal

    with caplog.at_level(logging.WARNING):
        out = fetch_legulegu_frame(ak_call, "stock_index_pe_lg", "沪深300")
    assert out is None
    assert rec.sleeps == [4.0]  # one GAP, one attempt, no retry
    assert sum(1 for r in caplog.records if r.levelno == logging.WARNING) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/fundamentals/test_legulegu_fetch.py -q`
Expected: collection/import error — `ModuleNotFoundError: No module named 'irc.fundamentals.legulegu_fetch'`.

- [ ] **Step 3: Create the implementation**

Create `src/irc/fundamentals/legulegu_fetch.py`:

```python
"""Paced dual-policy retry primitive for the legulegu PE/PB endpoints.

legulegu (Aliyun Tengine) admits a burst of ~3 requests then HTTP-504s for a
cooldown that escalates under sustained load. AkShare 1.18.60 hides the status
code, so a 504 surfaces as either a missing-CSRF AttributeError or a JSON-decode
of an HTML error body. This module paces (sleeps GAP before EVERY attempt so the
burst detector never trips), retries ordinary network blips per-symbol, and on a
repeated throttle signature RAISES `LeguleguCooldownExhausted` to suspend the
whole broad-leg sweep.

Effects at the edge: `ak_call` is INJECTED (callers pass their own indirection so
existing `_ak_call` patches keep intercepting); `_sleep` is a module indirection
so unit tests fast-forward through the waits.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

import pandas as pd

from irc.data.akshare_client import _is_transient_network_error

_log = logging.getLogger(__name__)

# Hardcoded judgment values (ADR 0014 D1) — no env knob. Conservative; gate #4
# calibrates GAP against the live limiter.
_LEGULEGU_GAP_S: float = 4.0          # inter-call pacing, slept BEFORE every attempt
_LEGULEGU_NETWORK_ATTEMPTS: int = 3   # total attempts for ordinary network transients
_LEGULEGU_BACKOFF_S: float = 3.0      # base of exp backoff (3s, 6s) between net attempts
_LEGULEGU_COOLDOWN_S: float = 30.0    # wait after a throttle signature
_LEGULEGU_COOLDOWN_RETRIES: int = 1   # at most one cooldown retry, then suspend


class LeguleguCooldownExhausted(Exception):
    """Broad-leg suspension signal: the throttle signature repeated after our
    judgment-value wait. Names OUR exhausted cooldown-retry budget — it does NOT
    assert a measured provider cooldown (ADR 0014 D2/D5). Caught by the ingestor
    (non-fatal) and by `fetch_cn_index_valuation` (never-raises seam)."""


def _sleep(seconds: float) -> None:
    """Indirection so unit tests fast-forward through pacing / backoff waits."""
    time.sleep(seconds)


def _is_throttle_signature(exc: BaseException) -> bool:
    """HEURISTIC: legulegu served a non-data throttle/error page instead of JSON.
    NOT a true HTTP-504 classifier — AkShare 1.18.60 hides the status code. Covers
    the two observed 504 surfaces (missing-CSRF AttributeError carrying BOTH
    'NoneType' AND 'attrs'; JSON-decode of an HTML error body). Blind spots
    (documented, treated as FATAL → no cooldown retry): a JSON error envelope
    raises KeyError('data'); a genuine parser/schema change also trips the
    AttributeError arm. Durable fix = an HTTP adapter preserving status (deferred).
    """
    if isinstance(exc, AttributeError):
        msg = str(exc)
        return "NoneType" in msg and "attrs" in msg
    # requests 2.33.1 builds against simplejson, so requests.JSONDecodeError is
    # NOT a json.JSONDecodeError subclass — match BOTH explicitly.
    import requests
    return isinstance(exc, (json.JSONDecodeError, requests.exceptions.JSONDecodeError))


def _is_network_transient(exc: BaseException) -> bool:
    """requests.exceptions.ConnectionError / Timeout are NOT subclasses of the
    builtin ConnectionError / TimeoutError (MRO -> RequestException -> OSError),
    so akshare_client._is_transient_network_error misses them. Reuse it for the
    builtin/urllib3 cases AND add the requests classes explicitly."""
    if _is_transient_network_error(exc):
        return True
    import requests
    return isinstance(exc, (requests.exceptions.ConnectionError,
                            requests.exceptions.Timeout))


def fetch_legulegu_frame(
    ak_call: Callable[..., Any], fn_name: str, cn_name: str
) -> pd.DataFrame | None:
    """Paced, dual-policy fetch of one legulegu endpoint for one symbol.

    network exhausted -> None (per-symbol miss; sweep continues).
    throttle repeated after the wait -> raises LeguleguCooldownExhausted (suspend).
    success non-DataFrame -> empty DataFrame. fatal/non-transient -> None.
    Every terminal failure logs a WARNING (preserves _fetch_frame's logging
    contract). Bounded: network <= 3 attempts, cooldown <= 1 retry.
    """
    cooldown_used = 0
    network_failures = 0
    while True:
        _sleep(_LEGULEGU_GAP_S)  # pace before EVERY attempt
        try:
            result = ak_call(fn_name, symbol=cn_name)
            return result if isinstance(result, pd.DataFrame) else pd.DataFrame()
        except Exception as exc:
            if _is_throttle_signature(exc):
                if cooldown_used >= _LEGULEGU_COOLDOWN_RETRIES:
                    _log.warning(
                        "legulegu throttle signature repeated for %s(%r) after "
                        "cooldown — suspending broad-leg sweep", fn_name, cn_name,
                    )
                    raise LeguleguCooldownExhausted(
                        f"{fn_name}({cn_name!r}) throttled after cooldown"
                    ) from exc
                cooldown_used += 1
                _sleep(_LEGULEGU_COOLDOWN_S)
                continue
            if _is_network_transient(exc):
                network_failures += 1
                if network_failures >= _LEGULEGU_NETWORK_ATTEMPTS:
                    _log.warning(
                        "legulegu network transient exhausted for %s(%r) after "
                        "%d attempts", fn_name, cn_name, network_failures,
                    )
                    return None
                _sleep(_LEGULEGU_BACKOFF_S * 2 ** (network_failures - 1))
                continue
            _log.warning(
                "legulegu fetch %s(%r) failed (fatal)", fn_name, cn_name,
                exc_info=True,
            )
            return None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/fundamentals/test_legulegu_fetch.py -q`
Expected: `17 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/legulegu_fetch.py tests/fundamentals/test_legulegu_fetch.py
git commit -m "feat(fundamentals): paced dual-policy legulegu_fetch primitive (Phase A)"
```

---

## Task 2: Route the four legulegu calls through `fetch_legulegu_frame`

**Files:**
- Modify: `tests/fundamentals/test_akshare_index_valuation.py` (add routing pins + no-sleep fixture)
- Modify: `src/irc/fundamentals/akshare_index_valuation.py`

- [ ] **Step 1: Add the no-sleep autouse fixture + routing-pin tests**

Add to the **top** of `tests/fundamentals/test_akshare_index_valuation.py`, immediately after the existing `import pytest` line area (after line 6), a no-sleep autouse fixture so the wrapped fetchers never wait:

```python
@pytest.fixture(autouse=True)
def _no_legulegu_sleep(monkeypatch):
    """Fast-forward legulegu pacing in every offline test in this module."""
    monkeypatch.setattr("irc.fundamentals.legulegu_fetch._sleep", lambda _s: None)
```

Then append these routing-pin tests at the **end** of the file (they pin the paced/unpaced boundary — broad fetchers route through the paced wrapper, csindex stays on `_fetch_frame`):

```python
def test_broad_history_routes_through_fetch_legulegu_frame() -> None:
    import inspect

    from irc.fundamentals import akshare_index_valuation as m

    src = inspect.getsource(m.fetch_cn_index_valuation_history)
    assert "fetch_legulegu_frame" in src
    assert '_fetch_frame("stock_index_pe_lg"' not in src
    assert '_fetch_frame("stock_index_pb_lg"' not in src


def test_broad_single_shot_routes_through_fetch_legulegu_frame() -> None:
    import inspect

    from irc.fundamentals import akshare_index_valuation as m

    src = inspect.getsource(m.fetch_cn_index_valuation)
    assert "fetch_legulegu_frame" in src


def test_csindex_sector_stays_on_fetch_frame_unpaced() -> None:
    import inspect

    from irc.fundamentals import akshare_index_valuation as m

    src = inspect.getsource(m.fetch_cn_sector_index_valuation_history)
    assert '_fetch_frame("stock_zh_index_value_csindex"' in src
    assert "fetch_legulegu_frame" not in src


def test_single_shot_catches_cooldown_exhausted_returns_none(monkeypatch) -> None:
    # Provider/single-shot seam (ADR 0010): must NEVER raise — catch -> None.
    from irc.fundamentals import akshare_index_valuation as m
    from irc.fundamentals.legulegu_fetch import LeguleguCooldownExhausted

    def _boom(ak_call, fn_name, cn_name):
        raise LeguleguCooldownExhausted("throttled")

    monkeypatch.setattr(m, "fetch_legulegu_frame", _boom)
    assert m.fetch_cn_index_valuation("csi300") is None


def test_history_propagates_cooldown_exhausted(monkeypatch) -> None:
    # Ingest path (ADR 0014 D3): must PROPAGATE for sweep suspension.
    from irc.fundamentals import akshare_index_valuation as m
    from irc.fundamentals.legulegu_fetch import LeguleguCooldownExhausted

    def _boom(ak_call, fn_name, cn_name):
        raise LeguleguCooldownExhausted("throttled")

    monkeypatch.setattr(m, "fetch_legulegu_frame", _boom)
    with pytest.raises(LeguleguCooldownExhausted):
        m.fetch_cn_index_valuation_history("csi300")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -q -k "routes_through or stays_on or catches_cooldown or propagates_cooldown"`
Expected: FAIL — the routing-pin tests fail (`_fetch_frame("stock_index_pe_lg"` still present) and the cooldown tests fail (no import / no catch yet).

- [ ] **Step 3: Edit the module docstring to scope "never-raises"**

In `src/irc/fundamentals/akshare_index_valuation.py`, replace the docstring block (lines 1-13) so the never-raises wording is scoped to the single-shot/sector paths and the `_history` carve-out is documented. Replace:

```python
"""Index-level PE/PB valuation fetcher (item 001) via legulegu AkShare endpoints.

`stock_index_pe_lg` (PE) and `stock_index_pb_lg` (PB) are addressed by a
live-confirmed Chinese broad-index symbol from `_LEGULEGU_INDEX_SYMBOL`. Network
I/O is confined to the `_ak_call` indirection; extraction is a pure helper.

Degrade-to-None contract: unknown index_key → None; any adapter failure or
empty frame → metrics None (never raises). Matches `fetch_cn_filing_digest`.

NOTE: legulegu PE/PB endpoints carry no dividend-yield column, so
`dividend_yield` is None in practice (spec §Judgment call 3). The forbidden
fund-profile indicator is never used here (see test_static_profile_invariant).
"""
```

with:

```python
"""Index-level PE/PB valuation fetcher (item 001) via legulegu AkShare endpoints.

`stock_index_pe_lg` (PE) and `stock_index_pb_lg` (PB) are addressed by a
live-confirmed Chinese broad-index symbol from `_LEGULEGU_INDEX_SYMBOL`. The four
legulegu calls are paced via `legulegu_fetch.fetch_legulegu_frame`; the csindex
sector call stays on the plain `_fetch_frame` (single static-Excel GET, no burst
limiter). Network I/O is confined to indirections; extraction is a pure helper.

Degrade-to-None contract: unknown index_key → None; any adapter failure or empty
frame → metrics None. **never-raises** holds for `fetch_cn_index_valuation` (the
ADR 0010 provider seam) and `fetch_cn_sector_index_valuation_history`. CARVE-OUT
(ADR 0014 D3): `fetch_cn_index_valuation_history` (ingest infra, single caller =
the ingestor) PROPAGATES `LeguleguCooldownExhausted` to suspend the broad-leg
sweep; the single-shot path catches the same signal → None to keep the seam.

NOTE: legulegu PE/PB endpoints carry no dividend-yield column, so
`dividend_yield` is None in practice (spec §Judgment call 3). The forbidden
fund-profile indicator is never used here (see test_static_profile_invariant).
"""
```

- [ ] **Step 4: Add the import**

In `src/irc/fundamentals/akshare_index_valuation.py`, after the existing `from irc.fundamentals.index_valuation_types import (...)` block (line 22-26), add:

```python
from irc.fundamentals.legulegu_fetch import (
    LeguleguCooldownExhausted,
    fetch_legulegu_frame,
)
```

- [ ] **Step 5: Swap the two `_history` legulegu calls + propagate**

In `fetch_cn_index_valuation_history`, replace the two `_fetch_frame` legulegu calls (lines 161-162):

```python
    pe_df = _fetch_frame("stock_index_pe_lg", cn_name)
    pb_df = _fetch_frame("stock_index_pb_lg", cn_name)
```

with (note: NO try/except here — the exception must propagate to the ingestor):

```python
    pe_df = fetch_legulegu_frame(_ak_call, "stock_index_pe_lg", cn_name)
    pb_df = fetch_legulegu_frame(_ak_call, "stock_index_pb_lg", cn_name)
```

- [ ] **Step 6: Swap the two single-shot legulegu calls + catch**

In `fetch_cn_index_valuation`, replace the two `_fetch_frame` legulegu calls (lines 242-243):

```python
    pe_df = _fetch_frame("stock_index_pe_lg", cn_name)
    pb_df = _fetch_frame("stock_index_pb_lg", cn_name)
```

with (this path is the provider seam — catch → None to preserve never-raises):

```python
    try:
        pe_df = fetch_legulegu_frame(_ak_call, "stock_index_pe_lg", cn_name)
        pb_df = fetch_legulegu_frame(_ak_call, "stock_index_pb_lg", cn_name)
    except LeguleguCooldownExhausted:
        return None
```

- [ ] **Step 7: Run the full module suite to verify green**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -q`
Expected: all pass (existing tests + the 5 new ones). The existing fetcher tests patch `_ak_call`, which `fetch_legulegu_frame` calls through, so they keep intercepting; the autouse fixture suppresses the GAP sleep.

- [ ] **Step 8: Commit**

```bash
git add src/irc/fundamentals/akshare_index_valuation.py tests/fundamentals/test_akshare_index_valuation.py
git commit -m "feat(fundamentals): route legulegu calls through paced wrapper; scope never-raises (Phase A)"
```

---

## Task 3: Provider-seam no-sleep fixture

**Files:**
- Modify: `tests/fundamentals/test_provider.py`

- [ ] **Step 1: Add the no-sleep autouse fixture**

`test_akshare_provider_index_equals_direct_call` calls `fetch_cn_index_valuation` twice (now paced). Add an autouse fixture so it never sleeps. Insert after the imports block (after line 13) in `tests/fundamentals/test_provider.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def _no_legulegu_sleep(monkeypatch):
    monkeypatch.setattr("irc.fundamentals.legulegu_fetch._sleep", lambda _s: None)
```

(If `import pytest` is already present at the top, do NOT duplicate it — only add the fixture.)

- [ ] **Step 2: Run the provider suite to verify green**

Run: `uv run pytest tests/fundamentals/test_provider.py -q`
Expected: all pass, fast (no real sleeps).

- [ ] **Step 3: Commit**

```bash
git add tests/fundamentals/test_provider.py
git commit -m "test(fundamentals): no-sleep fixture for paced provider-seam index test"
```

---

## Task 4: Ingestor both-axes guard + sweep suspension (TDD)

**Files:**
- Modify: `tests/data/test_index_valuation_ingestor.py`
- Modify: `src/irc/data/index_valuation_ingestor.py`

- [ ] **Step 1: Add the failing regression + guard + warning-contract tests**

Append to `tests/data/test_index_valuation_ingestor.py`:

```python
import logging

import pytest

from irc.fundamentals.legulegu_fetch import LeguleguCooldownExhausted


def test_cooldown_exhausted_suspends_sweep_and_writes_what_landed(tmp_path):
    """A fetch that raises LeguleguCooldownExhausted on the 2nd key suspends the
    sweep: later keys are never fetched, key-1 rows are still written."""
    con = _con(tmp_path)
    fetched: list[str] = []
    landed = IndexValuationHistory(
        index_key="csi1000",
        rows=(IndexValuationPoint("2026-06-01", 12.0, 1.3, None),),
    )

    def fetch(key):
        fetched.append(key)
        if key == "csi300":  # second key in lexical order
            raise LeguleguCooldownExhausted("throttled")
        return landed

    written = ingest_index_valuation_history(
        con, ("csi1000", "csi300", "csi500", "sse50"),
        fetch=fetch, now_iso="2026-06-08T00:00:00+08:00", replace_keys=True,
    )
    # Only the first key was written; the trip key + the two after it were skipped.
    assert fetched == ["csi1000", "csi300"]
    assert written == 1
    rows = con.execute(
        "SELECT DISTINCT index_key FROM index_valuation_history"
    ).fetchall()
    assert rows == [("csi1000",)]
    con.close()


def test_cooldown_suspension_logs_trip_key_and_skipped_keys(tmp_path, caplog):
    con = _con(tmp_path)

    def fetch(key):
        if key == "csi300":
            raise LeguleguCooldownExhausted("throttled")
        return IndexValuationHistory(
            index_key=key, rows=(IndexValuationPoint("2026-06-01", 12.0, 1.3, None),)
        )

    with caplog.at_level(logging.WARNING):
        ingest_index_valuation_history(
            con, ("csi1000", "csi300", "csi500", "sse50"),
            fetch=fetch, now_iso="2026-06-08T00:00:00+08:00", replace_keys=True,
        )
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "suspending broad-leg sweep" in text
    assert "csi300" in text                 # the trip key
    assert "csi500" in text and "sse50" in text  # the skipped keys, explicitly
    assert "cache preserved" in text
    con.close()


def test_replace_keys_skips_key_when_fetch_lacks_pb(tmp_path):
    """Inverted PB-only guard: a replace-mode fetch whose rows ALL have pb=None
    must NOT wipe good cached rows — skip the key (cache preserved)."""
    con = _con(tmp_path)
    good = IndexValuationHistory(
        index_key="csi300",
        rows=(IndexValuationPoint("2026-05-01", 13.8, 1.28, None),),
    )
    ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: good, now_iso="2026-05-31T00:00:00+08:00"
    )
    pe_only = IndexValuationHistory(
        index_key="csi300",
        rows=(IndexValuationPoint("2026-05-01", 14.0, None, None),),  # pb=None
    )
    written = ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: pe_only,
        now_iso="2026-06-01T00:00:00+08:00", replace_keys=True,
    )
    assert written == 0
    rows = con.execute(
        "SELECT CAST(date AS VARCHAR), pe_ttm, pb FROM index_valuation_history "
        "WHERE index_key='csi300'"
    ).fetchall()
    assert rows == [("2026-05-01", 13.8, 1.28)]  # cache untouched
    con.close()


def test_replace_skip_missing_axis_logs_warning(tmp_path, caplog):
    """The both-axes guard's skip is a tested WARNING contract."""
    con = _con(tmp_path)
    ingest_index_valuation_history(
        con, ("csi300",),
        fetch=lambda k: IndexValuationHistory(
            index_key="csi300", rows=(IndexValuationPoint("2026-05-01", 13.8, 1.28, None),)
        ),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    pb_only = IndexValuationHistory(
        index_key="csi300",
        rows=(IndexValuationPoint("2026-05-01", None, 1.3, None),),  # pe_ttm=None
    )
    with caplog.at_level(logging.WARNING):
        ingest_index_valuation_history(
            con, ("csi300",), fetch=lambda k: pb_only,
            now_iso="2026-06-01T00:00:00+08:00", replace_keys=True,
        )
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "replace skipped" in text
    assert "csi300" in text
    assert "pe" in text            # the missing axis
    assert "cache preserved" in text
    con.close()
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/data/test_index_valuation_ingestor.py -q -k "cooldown or lacks_pb or missing_axis"`
Expected: FAIL — `test_cooldown_*` (no catch → exception propagates out of the function), `test_replace_keys_skips_key_when_fetch_lacks_pb` (PE-only currently passes the guard → 0 rows expected but 1 written), `test_replace_skip_missing_axis_logs_warning` (no WARNING emitted yet).

- [ ] **Step 3: Add a logger to the ingestor**

In `src/irc/data/index_valuation_ingestor.py`, replace the import block (lines 9-21). Replace:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from typing import Callable

import duckdb

from irc.data.raw_ref import build_ref_id
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation_history
from irc.fundamentals.index_valuation_types import IndexValuationHistory
from irc.opportunity.lookthrough_valuation import MIN_PE_DAYS, MIN_PE_POINTS
from irc.opportunity.sector_indices import SECTOR_INDEX_KEYS
```

with:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as _date
from typing import Callable

import duckdb

from irc.data.raw_ref import build_ref_id
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation_history
from irc.fundamentals.index_valuation_types import IndexValuationHistory
from irc.fundamentals.legulegu_fetch import LeguleguCooldownExhausted
from irc.opportunity.lookthrough_valuation import MIN_PE_DAYS, MIN_PE_POINTS
from irc.opportunity.sector_indices import SECTOR_INDEX_KEYS

_log = logging.getLogger(__name__)
```

- [ ] **Step 4: Replace the per-key loop body with the guard + suspension catch**

In `ingest_index_valuation_history`, replace the loop (lines 44-62):

```python
    for key in index_keys:
        hist = fetch(key)
        if hist is None or not hist.rows:
            continue
        # D8: a non-empty fetch is required before delete, AND the fetch must carry
        # at least one usable PE-TTM row. A PB-only (pe_ttm=None for every row)
        # legulegu frame is a partial failure — skip the key entirely so that the
        # DELETE and the INSERT OR REPLACE (which resolves on PRIMARY KEY
        # (index_key, date)) cannot wipe or overwrite good cached PE rows.
        if replace_keys and not any(p.pe_ttm is not None for p in hist.rows):
            continue
        if replace_keys:
            keys_to_replace.append(key)
        for pt in hist.rows:
            params.append([
                key, pt.date_iso, pt.pe_ttm, pt.pb, pt.dividend_yield,
                now_iso, "akshare",
                build_ref_id("akshare", "index_valuation_history", key, pt.date_iso),
            ])
```

with:

```python
    for i, key in enumerate(index_keys):
        try:
            hist = fetch(key)
        except LeguleguCooldownExhausted:
            # ADR 0014 D4: legulegu's limiter is provider-wide and escalating —
            # poking later symbols only deepens it. Suspend the sweep, write what
            # landed. Non-destructive: skipped keys keep their cached rows (never
            # appended to keys_to_replace), so a mature skipped key still grounds.
            skipped = index_keys[i + 1:]
            _log.warning(
                "legulegu cooldown exhausted at %s; suspending broad-leg sweep — "
                "skipping %d remaining key(s): %s — cache preserved (skipped keys "
                "still ground if mature).",
                key, len(skipped), ", ".join(skipped) or "none",
            )
            break
        if hist is None or not hist.rows:
            continue
        # D2/D7: the destructive replace requires BOTH axes present. A frame
        # missing an axis entirely (all pe_ttm=None OR all pb=None) is a partial
        # failure — skip the key (cache preserved) and log the missing axis so
        # chronic half-frames are operationally visible.
        if replace_keys:
            has_pe = any(p.pe_ttm is not None for p in hist.rows)
            has_pb = any(p.pb is not None for p in hist.rows)
            if not (has_pe and has_pb):
                _log.warning(
                    "index_valuation replace skipped for %s: missing %s axis "
                    "(cache preserved)", key, "pe" if not has_pe else "pb",
                )
                continue
            keys_to_replace.append(key)
        for pt in hist.rows:
            params.append([
                key, pt.date_iso, pt.pe_ttm, pt.pb, pt.dividend_yield,
                now_iso, "akshare",
                build_ref_id("akshare", "index_valuation_history", key, pt.date_iso),
            ])
```

- [ ] **Step 5: Run the ingestor suite to verify green**

Run: `uv run pytest tests/data/test_index_valuation_ingestor.py -q`
Expected: all pass — the pre-existing `test_replace_keys_skips_key_when_fetch_lacks_pe_ttm` still passes (PE-less → missing pe axis → skip), the new PB-only and warning-contract tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/irc/data/index_valuation_ingestor.py tests/data/test_index_valuation_ingestor.py
git commit -m "feat(ingest): both-axes guard + non-destructive legulegu sweep suspension (Phase A D2/D4/D7)"
```

---

## Task 5: Repair the gate-1 wiring tests (D8)

**Files:**
- Modify: `tests/commands/test_ingest_index_valuation_wiring.py`

- [ ] **Step 1: Repair the two RED tests to assert the real surface**

In `tests/commands/test_ingest_index_valuation_wiring.py`, replace `test_run_ingest_calls_index_valuation_ingestor` (lines 8-13):

```python
def test_run_ingest_calls_index_valuation_ingestor() -> None:
    """run_ingest must invoke the index-valuation ingestor over the broad-index
    keys so the cached table is refreshed on `irc run --from ingest`."""
    src = inspect.getsource(ingest_cmd.run_ingest)
    assert "ingest_index_valuation_history" in src
    assert "_BROAD_INDEX_KEYS" in src
```

with:

```python
def test_run_ingest_calls_index_valuation_ingestor() -> None:
    """run_ingest must invoke the index-valuation ingestor over the production
    legulegu allowlist with replace_keys=True so the cached table self-migrates
    on `irc run --from ingest`."""
    src = inspect.getsource(ingest_cmd.run_ingest)
    assert "ingest_index_valuation_history" in src
    assert "_LEGULEGU_INDEX_SYMBOL" in src
    assert "replace_keys=True" in src
```

Then replace `test_ingest_cmd_imports_broad_index_keys_and_ingestor` (lines 16-19):

```python
def test_ingest_cmd_imports_broad_index_keys_and_ingestor() -> None:
    body = inspect.getsource(ingest_cmd)
    assert "from irc.data.index_valuation_ingestor import" in body
    assert "_BROAD_INDEX_KEYS" in body
```

with:

```python
def test_ingest_cmd_imports_broad_index_keys_and_ingestor() -> None:
    body = inspect.getsource(ingest_cmd)
    assert "from irc.data.index_valuation_ingestor import" in body
    assert "_LEGULEGU_INDEX_SYMBOL" in body
```

- [ ] **Step 2: Run the wiring suite to verify green**

Run: `uv run pytest tests/commands/test_ingest_index_valuation_wiring.py -q`
Expected: `4 passed` (the 2 repaired + the 2 already-green sector tests).

- [ ] **Step 3: Commit**

```bash
git add tests/commands/test_ingest_index_valuation_wiring.py
git commit -m "test(ingest): repair gate-1 wiring tests to real legulegu surface (Phase A D8)"
```

---

## Task 6: Live-test speculative-sweep gating (source edit ONLY — do NOT execute)

**Files:**
- Modify: `tests/fundamentals/test_index_valuation_live.py`

> **Do NOT run this file.** It is gated behind `IRC_RUN_LIVE_AKSHARE=1`; default `pytest` skips it. This edit only adds the extra opt-in gate and routes the speculative sweep through the paced wrapper. Live execution is deferred operator follow-up.

- [ ] **Step 1: Add the speculative opt-in gate and route the sweep through `fetch_legulegu_frame`**

In `tests/fundamentals/test_index_valuation_live.py`, update the import block (lines 19-27) to also import `_ak_call` and `fetch_legulegu_frame`. Replace:

```python
from irc.fundamentals.akshare_index_valuation import (  # noqa: E402
    _LEGULEGU_INDEX_SYMBOL,
    _LEGULEGU_PB_COL,
    _LEGULEGU_PE_TTM_COL,
    _SPECULATIVE_LEGULEGU_SYMBOL,
    _extract_latest_value,
    _fetch_frame,
    fetch_cn_index_valuation,
)
```

with:

```python
from irc.fundamentals.akshare_index_valuation import (  # noqa: E402
    _LEGULEGU_INDEX_SYMBOL,
    _LEGULEGU_PB_COL,
    _LEGULEGU_PE_TTM_COL,
    _SPECULATIVE_LEGULEGU_SYMBOL,
    _ak_call,
    _extract_latest_value,
    fetch_cn_index_valuation,
)
from irc.fundamentals.legulegu_fetch import fetch_legulegu_frame
```

Then replace the speculative test (lines 60-77):

```python
def test_speculative_symbol_landing_sweep_informational() -> None:
    """INFORMATIONAL only — never fails. Probes each speculative symbol DIRECTLY
    via legulegu (bypassing the production allowlist gate) and prints a landing
    table. When both pe and pb are numeric the symbol has landed and is ready to
    graduate into _LEGULEGU_INDEX_SYMBOL + the hard-assert set (D2 graduation).

    Uses _fetch_frame / _extract_latest_value directly so the allowlist gate in
    fetch_cn_index_valuation cannot mask a real landing.
    """
    print("\n  speculative legulegu sweep (informational):")
    for slug, symbol in sorted(_SPECULATIVE_LEGULEGU_SYMBOL.items()):
        pe_df = _fetch_frame("stock_index_pe_lg", symbol)
        pb_df = _fetch_frame("stock_index_pb_lg", symbol)
        pe = _extract_latest_value(pe_df, (_LEGULEGU_PE_TTM_COL,)) if pe_df is not None else None
        pb = _extract_latest_value(pb_df, (_LEGULEGU_PB_COL,)) if pb_df is not None else None
        landed = "[LANDED]" if (pe is not None and pb is not None) else "—"
        print(f"    {slug:14s} {symbol:10s} pe={pe} pb={pb}  {landed}")
```

with:

```python
@pytest.mark.skipif(
    os.environ.get("IRC_RUN_LEGULEGU_SPECULATIVE") != "1",
    reason="set IRC_RUN_LEGULEGU_SPECULATIVE=1 to run the 12-call speculative sweep "
    "(separate cold window — never right before gate #3)",
)
def test_speculative_symbol_landing_sweep_informational() -> None:
    """INFORMATIONAL only — never fails. Probes each speculative symbol DIRECTLY
    via legulegu (bypassing the production allowlist gate) and prints a landing
    table. When both pe and pb are numeric the symbol has landed and is ready to
    graduate into _LEGULEGU_INDEX_SYMBOL + the hard-assert set (D2 graduation).

    PACED via fetch_legulegu_frame so the 12-call sweep does not trip the burst
    limiter. Additionally opt-in gated (IRC_RUN_LEGULEGU_SPECULATIVE=1) on top of
    IRC_RUN_LIVE_AKSHARE so it is a deliberate separate cold-window job (D6).
    """
    print("\n  speculative legulegu sweep (informational):")
    for slug, symbol in sorted(_SPECULATIVE_LEGULEGU_SYMBOL.items()):
        pe_df = fetch_legulegu_frame(_ak_call, "stock_index_pe_lg", symbol)
        pb_df = fetch_legulegu_frame(_ak_call, "stock_index_pb_lg", symbol)
        pe = _extract_latest_value(pe_df, (_LEGULEGU_PE_TTM_COL,)) if pe_df is not None else None
        pb = _extract_latest_value(pb_df, (_LEGULEGU_PB_COL,)) if pb_df is not None else None
        landed = "[LANDED]" if (pe is not None and pb is not None) else "—"
        print(f"    {slug:14s} {symbol:10s} pe={pe} pb={pb}  {landed}")
```

- [ ] **Step 2: Verify the file still imports + collects (offline, skipped)**

Run: `uv run pytest tests/fundamentals/test_index_valuation_live.py -q`
Expected: `5 skipped` (4 parametrized hard-assert + 1 speculative, all skipped because `IRC_RUN_LIVE_AKSHARE` is unset). No import error. **Do NOT set the env vars.**

- [ ] **Step 3: Commit**

```bash
git add tests/fundamentals/test_index_valuation_live.py
git commit -m "test(live): gate speculative legulegu sweep + route through paced wrapper (Phase A D6)"
```

---

## Task 7: CHANGELOG `[Unreleased]` sub-bullet (VERSION stays 0.9.3)

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add the sub-bullet under `[Unreleased]`**

In `CHANGELOG.md`, immediately after the line `## [Unreleased]` (and its blank line), insert a new `### Added` section:

```markdown
### Added — Phase A legulegu broad-leg rate-limit hardening (2026-06-08)

- **The broad-index PE/PB ingest leg is now polite.** The 8 legulegu calls
  (csi300/csi500/csi1000/sse50 × `stock_index_pe_lg`/`stock_index_pb_lg`) route
  through a new `src/irc/fundamentals/legulegu_fetch.py` paced primitive: a 4s GAP
  is slept before every attempt so the burst detector never trips; ordinary
  network blips retry 3× with 3s·6s backoff (per-symbol → None on exhaustion);
  the throttle signature (missing-CSRF AttributeError / JSON-decode of an HTML
  error body) waits 30s and retries once, then **raises `LeguleguCooldownExhausted`**
  to suspend the remaining broad-leg sweep. Suspension is **non-destructive** — a
  skipped key keeps its cached `index_valuation_history` rows, so a mature key
  still grounds on PE-TTM this run (only the refresh is deferred). The single-shot
  provider seam (`fetch_cn_index_valuation`) catches the same signal → `None`
  (never-raises contract preserved). A **both-axes guard** now blocks the
  destructive DELETE+replace whenever either PE or PB is entirely absent from the
  fresh frame (cache preserved). Skips and suspensions emit tested WARNINGs
  (event · key · missing-axis/skipped-keys · "cache preserved"). Constants are
  hardcoded judgment values (no env knob); gate #4 calibrates the GAP against the
  live limiter. See [ADR 0014](docs/adr/0014-legulegu-rate-limit-handling.md).
  Deferred: full PB date-aligned carry-forward; a run-level ingest diagnostic
  artifact for chronicity; an HTTP adapter that preserves legulegu status codes.
```

- [ ] **Step 2: Confirm VERSION is untouched**

Run: `cat VERSION`
Expected: `0.9.3` (do NOT bump).

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): Phase A legulegu rate-limit hardening (Unreleased)"
```

---

## Task 8: Full offline verification gate

**Files:** none (verification only)

- [ ] **Step 1: Run all touched suites together (offline)**

Run:

```bash
uv run pytest \
  tests/fundamentals/test_legulegu_fetch.py \
  tests/fundamentals/test_akshare_index_valuation.py \
  tests/fundamentals/test_provider.py \
  tests/data/test_index_valuation_ingestor.py \
  tests/commands/test_ingest_index_valuation_wiring.py \
  tests/fundamentals/test_index_valuation_live.py \
  -q
```

Expected: all pass, `test_index_valuation_live.py` shows `5 skipped` (live gated off), no real network, no real sleeps. No failures.

- [ ] **Step 2: Lint the changed source**

Run: `uv run ruff check src/irc/fundamentals/legulegu_fetch.py src/irc/fundamentals/akshare_index_valuation.py src/irc/data/index_valuation_ingestor.py`
Expected: `All checks passed!` (line-length 100, py312).

- [ ] **Step 3: Confirm the file/line budgets**

Run: `wc -l src/irc/fundamentals/legulegu_fetch.py src/irc/data/index_valuation_ingestor.py src/irc/fundamentals/akshare_index_valuation.py`
Expected (verified by dry-run of this exact plan): `legulegu_fetch.py` = 124, ingestor = 153, `akshare_index_valuation.py` = 265. **Note:** `akshare_index_valuation.py` was already 259 lines pre-edit; it grows by ~6 (the try/except + import) and sits just over the 200-line ideal — this is expected and accepted, which is precisely why the heavy paced-retry logic lives in its own `legulegu_fetch.py` module rather than inflating it further (spec §Architecture.1 rationale). Do not refactor it in this PR.

---

## Deferred — operator-only, NOT plan steps (do NOT execute)

These run live network against legulegu and must each run in their OWN recovered cold window (ADR 0014 §Consequences). They are the human operator's follow-up after this offline PR merges:

- **Gate #4 (alone, `-x` load-bearing):** `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare tests/fundamentals/test_index_valuation_live.py -v -s -x` → 4 passed.
- **Gate #3 (alone):** `uv run irc run --from ingest` then `count_grounded.py outputs/<date>/opportunity_report.json` → grounded ≥ 9.
- **Gate #5 (alone):** steps 1–5 in `docs/2026-06-05-phase-a-broad-grounding/before-after.md`.
- **Speculative sweep (optional, separate cold window):** `IRC_RUN_LIVE_AKSHARE=1 IRC_RUN_LEGULEGU_SPECULATIVE=1 uv run pytest -m live_akshare tests/fundamentals/test_index_valuation_live.py::test_speculative_symbol_landing_sweep_informational -v -s`.

---

## Self-review notes (spec coverage)

- **§Architecture.1 (new primitive, constants, classifiers, sleep sequences):** Task 1. All four exact sleep sequences asserted: network success-on-3rd `[4,3,4,6,4]` (= `[GAP,3,GAP,6,GAP]`); network exhaust same → None; throttle success-on-retry `[4,30,4]` (= `[GAP,30,GAP]`); throttle exhaust `[4,30,4]` then raises.
- **§Architecture.2 (swap 4 calls, docstring scope, raise/catch asymmetry, csindex stays):** Task 2 (+ routing pins + asymmetry tests).
- **§Architecture.3 (both-axes guard + audit WARNING; sweep suspension + WARNING):** Task 4.
- **§Architecture.4 (gate-1 repair):** Task 5.
- **§Architecture.5 (live speculative gating — source only):** Task 6.
- **§Testing (no-sleep autouse fixtures):** Tasks 2 (akshare) + 3 (provider).
- **§Testing warning-contract table (two rows):** Task 4 asserts `replace skipped`·key·missing-axis·`cache preserved` and `suspending broad-leg sweep`·trip-key·skipped-list·`cache preserved`.
- **§Known limitations (VERSION 0.9.3, CHANGELOG Unreleased):** Task 7.

**Judgment calls made (cite spec section):**
1. **`_is_transient_network_error` import path** — spec §code-pointers says `fundamentals/akshare_client.py`; the real location is `src/irc/data/akshare_client.py:81`. Plan uses the verified path.
2. **`requests.JSONDecodeError` classifier** — spec §Architecture.1 + ADR 0014 D2 assert `requests.JSONDecodeError ⊂ json.JSONDecodeError`; **verified false** in this env (requests 2.33.1 / simplejson). `_is_throttle_signature` therefore checks `isinstance(exc, (json.JSONDecodeError, requests.exceptions.JSONDecodeError))` so the real AkShare throttle surface is matched. Preserves the spec's intent (both JSON-decode surfaces = throttle) and the test list (both asserted throttle).
3. **Ingestor logger** — the ingestor had no logger; added `import logging` + `_log = logging.getLogger(__name__)` (required by the spec's WARNING contract).
```
