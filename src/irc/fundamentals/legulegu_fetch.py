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
