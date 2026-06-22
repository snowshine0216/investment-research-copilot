# tests/monitor/test_cached_fetch.py
from __future__ import annotations

import json as _json

from irc.monitor.cached_fetch import (
    DEAD,
    OK,
    TRANSIENT,
    RetryPolicy,
    cache_first_fetch,
)


# A generic codec mirroring the real flow/industry contract: None -> miss.
def _serialize(by_symbol: dict[str, str | None]) -> dict[str, dict]:
    return {
        s: ({"status": "ok", "v": by_symbol[s]} if by_symbol[s] is not None
            else {"status": "miss", "v": None})
        for s in sorted(by_symbol)
    }


def _deserialize(payload: dict[str, dict]) -> dict[str, str | None]:
    return {s: (e["v"] if e.get("status") == "ok" else None) for s, e in payload.items()}


def _run(symbols, tmp_path, fetch_one, **kw):
    return cache_first_fetch(
        symbols, cache_dir=tmp_path, today="2026-06-21", fetch_one=fetch_one,
        serialize=_serialize, deserialize=_deserialize, sleep=lambda _s: None, **kw,
    )


# ---------------------------------------------------------------------------
# Tracer bullet: ok payload round-trips through the per-day cache.
# ---------------------------------------------------------------------------

def test_ok_payload_returned_deduped_and_served_from_cache(tmp_path):
    seen: list[str] = []

    def fetch_one(symbol):
        seen.append(symbol)
        return OK, f"val-{symbol}"

    out = _run(("AAA", "AAA", "BBB"), tmp_path, fetch_one)  # dup AAA
    assert out == {"AAA": "val-AAA", "BBB": "val-BBB"}
    assert seen == ["AAA", "BBB"]  # deduped, ordered

    seen.clear()
    out2 = _run(("AAA", "BBB"), tmp_path, fetch_one)
    assert out2 == {"AAA": "val-AAA", "BBB": "val-BBB"}
    assert seen == []  # second run fully served from cache


# ---------------------------------------------------------------------------
# The fix: a transient (raised) fetch is NOT persisted and is retried next run.
# ---------------------------------------------------------------------------

def test_transient_is_not_persisted_and_retried_next_run(tmp_path):
    # First run: endpoint is throttled → transient for the one symbol.
    out = _run(("AAA",), tmp_path, lambda _s: (TRANSIENT, None))
    assert out == {"AAA": None}  # caller sees no data
    assert not (tmp_path / "2026-06-21.json").is_file()  # nothing poisoned

    # Second run (same day): throttle lifted → symbol is retried and succeeds.
    seen: list[str] = []

    def recovered(symbol):
        seen.append(symbol)
        return OK, "val-AAA"

    out2 = _run(("AAA",), tmp_path, recovered)
    assert out2 == {"AAA": "val-AAA"}
    assert seen == ["AAA"]  # NOT skipped as a confirmed miss


def test_dead_is_persisted_as_miss_and_not_retried(tmp_path):
    seen: list[str] = []

    def fetch_one(symbol):
        seen.append(symbol)
        return DEAD, None

    out = _run(("AAA",), tmp_path, fetch_one)
    assert out == {"AAA": None}
    cache = _json.loads((tmp_path / "2026-06-21.json").read_text())
    assert cache["AAA"] == {"status": "miss", "v": None}

    seen.clear()
    _run(("AAA",), tmp_path, fetch_one)
    assert seen == []  # confirmed-dead symbol served from cache, never re-hit


# ---------------------------------------------------------------------------
# Backoff retry: a transient symbol recovers within one run.
# ---------------------------------------------------------------------------

def test_transient_then_ok_recovers_within_run_with_backoff(tmp_path):
    attempts = {"n": 0}

    def flaky(symbol):
        attempts["n"] += 1
        return (OK, "val-AAA") if attempts["n"] >= 3 else (TRANSIENT, None)

    slept: list[float] = []
    out = cache_first_fetch(
        ("AAA",), cache_dir=tmp_path, today="2026-06-21", fetch_one=flaky,
        serialize=_serialize, deserialize=_deserialize, sleep=slept.append,
    )
    assert out == {"AAA": "val-AAA"}  # recovered on the 3rd attempt
    assert attempts["n"] == 3
    # two backoff waits (0.5, 1.5) before the polite pacing gap (0.3)
    assert slept == [0.5, 1.5, 0.3]


def test_retries_are_bounded_then_gives_up_transient(tmp_path):
    attempts = {"n": 0}

    def always_throttled(symbol):
        attempts["n"] += 1
        return TRANSIENT, None

    out = _run(("AAA",), tmp_path, always_throttled,
               policy=RetryPolicy(retries=2, breaker_threshold=99))
    assert out == {"AAA": None}
    assert attempts["n"] == 3  # 1 + 2 retries, no infinite loop
    assert not (tmp_path / "2026-06-21.json").is_file()


# ---------------------------------------------------------------------------
# Circuit-breaker: stop hammering after N consecutive transients.
# ---------------------------------------------------------------------------

def test_breaker_stops_fetching_after_consecutive_transients(tmp_path):
    seen: list[str] = []

    def throttled(symbol):
        seen.append(symbol)
        return TRANSIENT, None

    syms = tuple(f"S{i}" for i in range(10))
    out = _run(syms, tmp_path, throttled,
               policy=RetryPolicy(retries=0, breaker_threshold=3))
    # first 3 tripped the breaker; the remaining 7 are never fetched
    assert seen == ["S0", "S1", "S2"]
    assert all(out[s] is None for s in syms)  # all uncovered
    assert not (tmp_path / "2026-06-21.json").is_file()  # nothing persisted → all retry


def test_breaker_resets_on_a_settled_outcome(tmp_path):
    # ok between transients keeps the breaker from tripping.
    def pattern(symbol):
        return (OK, symbol) if symbol.endswith("ok") else (TRANSIENT, None)

    syms = ("t1", "t2", "good-ok", "t3", "t4")
    out = _run(syms, tmp_path, pattern, policy=RetryPolicy(retries=0, breaker_threshold=3))
    assert out["good-ok"] == "good-ok"  # the ok reset the run-of-transients counter
    assert out["t4"] is None  # still fetched (breaker never tripped), just transient
