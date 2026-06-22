"""Generic per-symbol, cache-first, per-day fetch with transient resilience.

Shared EDGE for monitor's sequential CN per-symbol legs (flow_fetch,
industry_valuation). It distinguishes THREE fetch outcomes so a transient
EastMoney throttle never poisons the day's cache (ADR 0019):

- ``ok``        — parsed payload (incl. a legitimately empty one) → persisted,
                  never re-fetched within the day.
- ``dead``      — confirmed absence (non-A-share line, or the endpoint answered
                  with no usable field) → persisted as ``miss``, never retried.
- ``transient`` — the fetch RAISED (timeout / rate-limit / 5xx) → NEVER persisted
                  → retried next run. Retried within-run with bounded exponential
                  backoff; a consecutive-transient circuit-breaker stops hammering
                  an endpoint that has started hard-blocking.

The injected ``fetch_one`` classifies a single symbol; it must NOT sleep (this
helper owns all pacing/backoff so tests stay deterministic via injected sleep).
``serialize`` / ``deserialize`` are the module's existing None→miss codecs, so
the on-disk JSON stays byte-stable. CN endpoints stay DIRECT (ADR 0017).
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

OK = "ok"
DEAD = "dead"
TRANSIENT = "transient"

# (status, payload) — payload is meaningful only for OK; None otherwise.
Outcome = tuple[str, object]


@dataclass(frozen=True)
class RetryPolicy:
    """Backoff + circuit-breaker knobs. Defaults pace ~30 sequential CN calls."""

    retries: int = 2  # extra attempts after the first → 3 total on a transient
    base_delay: float = 0.5  # first backoff; grows by `factor` each retry
    factor: float = 3.0  # 0.5s → 1.5s
    pacing: float = 0.3  # polite gap after a settled (ok/dead) fetch
    breaker_threshold: int = 5  # consecutive transient symbols → stop fetching


def _cache_path(cache_dir: Path, today: str) -> Path:
    return cache_dir / f"{today}.json"


def _read(cache_dir: Path, today: str, deserialize) -> dict[str, object | None]:
    """Cache JSON → symbol→(payload|None) map (ok→payload, miss→None). Unreadable,
    missing, OR structurally corrupt (a partial/garbled entry that fails to
    deserialize) → empty (refetch the day), NEVER a crash — the brief must degrade.
    Transient entries are absent by construction. The deserialize runs INSIDE the
    guard because a truncated/edited cache yields valid JSON with malformed rows."""
    path = _cache_path(cache_dir, today)
    if not path.is_file():
        return {}
    try:
        return deserialize(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError,
            KeyError, TypeError, ValueError, AttributeError):
        _log.warning("cached_fetch: unreadable cache %s; refetching", path, exc_info=True)
        return {}


def _write(cache_dir: Path, today: str, payload: dict[str, dict]) -> None:
    """Atomic byte-stable write (sorted keys, .tmp.{pid} → os.replace)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = _cache_path(cache_dir, today).with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, _cache_path(cache_dir, today))


def _fetch_with_retry(symbol: str, fetch_one, policy: RetryPolicy, sleep) -> Outcome:
    """Retry a per-symbol fetch ONLY while it reports transient, with bounded
    exponential backoff. Returns the first settled (ok/dead) outcome, or transient
    after exhausting retries."""
    delay = policy.base_delay
    for attempt in range(policy.retries + 1):
        status, payload = fetch_one(symbol)
        if status != TRANSIENT:
            return status, payload
        if attempt < policy.retries:
            sleep(delay)
            delay *= policy.factor
    return TRANSIENT, None


def cache_first_fetch(
    symbols: tuple[str, ...], *, cache_dir: Path, today: str, fetch_one,
    serialize, deserialize, policy: RetryPolicy = RetryPolicy(), sleep=time.sleep,
) -> dict[str, object | None]:
    """EDGE: dedup → cache-first per-day fetch → byte-stable write of ok+dead only.
    Transient symbols return None to the caller but are NOT persisted, so a re-run
    retries them. Idempotent within a day for settled symbols."""
    cached = _read(cache_dir, today, deserialize)
    out: dict[str, object | None] = {}
    persistable: dict[str, object | None] = {}  # ok→payload, dead→None
    consecutive_transient = 0
    tripped = False
    for symbol in dict.fromkeys(symbols):  # dedup, preserve order
        if symbol in cached:
            out[symbol] = cached[symbol]
            continue
        if tripped:  # breaker open → leave uncached (retry next run)
            out[symbol] = None
            continue
        status, payload = _fetch_with_retry(symbol, fetch_one, policy, sleep)
        if status == TRANSIENT:
            out[symbol] = None
            consecutive_transient += 1
            tripped = consecutive_transient >= policy.breaker_threshold
            continue
        consecutive_transient = 0
        sleep(policy.pacing)  # polite gap only after a settled CN call
        out[symbol] = payload if status == OK else None
        persistable[symbol] = payload if status == OK else None
    if persistable:
        _write(cache_dir, today, serialize({**cached, **persistable}))
    return out
