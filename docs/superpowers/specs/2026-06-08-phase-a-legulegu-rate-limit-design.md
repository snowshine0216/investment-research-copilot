# Phase A — legulegu broad-leg rate-limit hardening + PB-wipe guard

*2026-06-08. Follow-up to `2026-06-05-phase-a-broad-index-grounding-design.md`.*

## Problem

The broad-index PE/PB ingest leg fires **8 back-to-back** legulegu calls (4 keys ×
`stock_index_pe_lg` + `stock_index_pb_lg`) in one `ingest_index_valuation_history(
..., replace_keys=True)` (`commands/ingest_cmd.py:576`). legulegu (Aliyun Tengine,
`acw_tc`) admits a **burst of ~3 requests, then HTTP-504s for a cooldown** that
**escalates under sustained load**. On a 504, AkShare's `get_cookie_csrf` does
`csrf_tag.attrs` on a `None` tag (the 504 page carries no CSRF `<meta>`) and raises
`AttributeError("'NoneType' object has no attribute 'attrs'")`. `_fetch_frame`
swallows it → `None`. Net: csi500 / sse50 / csi300-PB chronically fail to land
**every weekly run** — not a one-off outage. AkShare *can* reach legulegu (06-08
probes pulled live numbers for all four symbols); the limiter is the wall.

This is upstream rate-limiting, so the durable fix is **polite client behaviour**:
pace the calls so the burst detector never trips, and retry the transient
504/AttributeError with a cooldown long enough to let an escalated limiter recover.

## Decisions (locked)

- **D1 — Pacing constants are hardcoded**, no env knob (YAGNI). They are
  conservative starting values; **gate #4 calibrates** them against the live limiter.
- **D2 — PB-wipe gap:** add the narrow *"no destructive replacement when either axis
  is entirely absent"* guard **now**; full PB carry-forward (land fresh PE while
  preserving cached PB on disjoint dates) is a **separate follow-up PR**.
- **D3 — Two distinct retry policies.** Ordinary network blips and the provider's
  escalating cooldown are different failure modes and get different schedules.
- **D4 — The speculative live sweep is paced *and* separately opt-in gated**, so the
  gate-#4 hard assertions run alone in a cold window.

## Architecture

### 1. New module `src/irc/fundamentals/legulegu_fetch.py`

A focused, self-contained paced-retry primitive (keeps the already-259-line
`akshare_index_valuation.py` from growing further). Effects at the edge: the
`ak_call` callable is **injected** (so existing tests that patch
`akshare_index_valuation._ak_call` keep intercepting unchanged), and `_sleep` is a
module indirection (mirrors `akshare_client._sleep`) so unit tests fast-forward.

Constants:

| Name | Value | Meaning |
|------|-------|---------|
| `_LEGULEGU_GAP_S` | `4.0` | inter-call pacing, slept **before every attempt** |
| `_LEGULEGU_NETWORK_ATTEMPTS` | `3` | total attempts for ordinary network transients |
| `_LEGULEGU_BACKOFF_S` | `3.0` | base of exp backoff between network attempts (3s, 6s) |
| `_LEGULEGU_COOLDOWN_S` | `30.0` | wait after a provider-cooldown signature |
| `_LEGULEGU_COOLDOWN_RETRIES` | `1` | at most one cooldown retry |

Two classifiers (a failure is exactly one of: cooldown / network / fatal):

```python
def _is_cooldown_signature(exc):
    # legulegu 504 page has no CSRF <meta>; AkShare's get_cookie_csrf does
    # csrf_tag.attrs on None. Match TIGHTLY on both substrings, NOT any
    # AttributeError mentioning "attrs".
    return (isinstance(exc, AttributeError)
            and "NoneType" in str(exc) and "attrs" in str(exc))

def _is_network_transient(exc):
    # requests.exceptions.ConnectionError / Timeout are NOT subclasses of the
    # builtin ConnectionError / TimeoutError (verified: MRO -> RequestException
    # -> OSError), so akshare_client._is_transient_network_error returns False
    # for them. Reuse it for the builtin/urllib3 cases, AND add the requests
    # classes explicitly.
    if _is_transient_network_error(exc):
        return True
    import requests
    return isinstance(exc, (requests.exceptions.ConnectionError,
                            requests.exceptions.Timeout))
```

`fetch_legulegu_frame(ak_call, fn_name, cn_name) -> pd.DataFrame | None`:

```
cooldown_used = 0
network_failures = 0
loop:
    _sleep(GAP_S)                       # pace before EVERY attempt
    try:
        result = ak_call(fn_name, symbol=cn_name)
        return result if isinstance(result, pd.DataFrame) else pd.DataFrame()
    except Exception as exc:
        if _is_cooldown_signature(exc):
            if cooldown_used >= COOLDOWN_RETRIES: -> warn + return None
            cooldown_used += 1; _sleep(COOLDOWN_S); continue
        if _is_network_transient(exc):
            network_failures += 1
            if network_failures >= NETWORK_ATTEMPTS: -> warn + return None
            _sleep(BACKOFF_S * 2 ** (network_failures - 1)); continue
        -> warn + return None            # fatal: degrade-to-None, no retry
```

Preserves `_fetch_frame`'s two contracts: **successful non-DataFrame result
normalises to an empty DataFrame** (never `None` on success), and **final failure
logs a WARNING**. The loop is bounded (network capped at 3, cooldown at 1) — no
unbounded retry even under alternating failures.

Sleep sequences (exact, asserted in tests):

- network transient, succeeds on 3rd attempt → `[GAP, 3, GAP, 6, GAP]`
- network transient, exhausts → `[GAP, 3, GAP, 6, GAP]` then `None`
- cooldown signature, succeeds on retry → `[GAP, 30, GAP]`
- cooldown signature, exhausts → `[GAP, 30, GAP]` then `None`

### 2. `akshare_index_valuation.py` edits

Replace the **four** legulegu `_fetch_frame("stock_index_pe_lg" / "stock_index_pb_lg",
cn_name)` calls (2 in `fetch_cn_index_valuation_history`, 2 in
`fetch_cn_index_valuation`) with `fetch_legulegu_frame(_ak_call, fn_name, cn_name)`.
The **csindex** sector call (`stock_zh_index_value_csindex`) stays on the plain
`_fetch_frame` — different host, out of scope, and we do not want to add ~56s of
pacing to the 14-slug sector leg.

### 3. `index_valuation_ingestor.py` — "no destructive replacement when either axis is entirely absent"

Extend the `replace_keys` guard (line 53) to require **both** axes carry at least one
value before the destructive DELETE+replace:

```python
if replace_keys and not (
    any(p.pe_ttm is not None for p in hist.rows)
    and any(p.pb is not None for p in hist.rows)
):
    continue
```

A PE-only frame (PB exhausted its retries) now **skips the key** — the cache keeps
its prior rows rather than being wiped to PE-only. Gated on `replace_keys`, so the
sector append leg (PB-less by design) is untouched.

**Invariant wording (narrow, do not overstate):** the guard blocks a destructive
replacement only when an axis is **entirely absent** from the fresh frame. It does
**not** guarantee snapshot completeness: PE and PB dates are unioned at
`akshare_index_valuation.py:168` (`dates = sorted(set(pe_map) | set(pb_map))`), so a
single stale PB value or disjoint PE/PB date sets can still pass both `any(...)`
checks and replace a more complete cached snapshot. Closing that is the deferred
carry-forward PR.

### 4. Live test (`tests/fundamentals/test_index_valuation_live.py`)

- The 4-symbol parametrized hard-assert test calls `fetch_cn_index_valuation`, which
  now paces transparently — **no change** beyond it running slower. This is gate #4
  and its real pacing is the calibration check; it must **not** patch `_sleep`.
- The **speculative sweep** (line 60) is routed through `fetch_legulegu_frame(_ak_call,
  ...)` instead of raw `_fetch_frame`, and gains an **additional** skip gate:
  `IRC_RUN_LEGULEGU_SPECULATIVE=1` (on top of the existing `live_akshare` /
  `IRC_RUN_LIVE_AKSHARE` gating). Default gate-#4 runs the 8 hard-assert calls alone;
  the 12-call sweep is a deliberate separate cold-window job so it cannot deepen the
  limiter's cooldown immediately before gate #3.

## Testing (TDD, red → green)

**New `tests/fundamentals/test_legulegu_fetch.py`** (fake `ak_call` + injected fake
`_sleep` recorder; no network):

- cooldown signature matches `AttributeError("'NoneType' object has no attribute
  'attrs'")`; a plain `AttributeError("widget has no attribute 'attrs'")` (no
  `NoneType`) is **fatal**, not cooldown; a `ValueError` is fatal.
- `requests.exceptions.ConnectionError` and `requests.exceptions.Timeout` classify as
  **network**; builtin `ConnectionError` classifies as network.
- network path: success on 3rd attempt → returns frame, sleeps `[GAP, 3, GAP, 6, GAP]`.
- network path: all fail → `None` after exactly 3 attempts (1 WARNING).
- cooldown path: fail-then-succeed → returns frame, sleeps `[GAP, 30, GAP]`.
- cooldown path: fail-twice → `None` after exactly 2 attempts (no 2nd cooldown retry).
- success returning a non-DataFrame (e.g. `None` / dict) → returns **empty DataFrame**.
- fatal error (non-transient) → `None` on the first attempt, no retry, WARNING logged.

**`tests/data/test_index_valuation_ingestor.py`**: keep
`test_replace_keys_skips_key_when_fetch_lacks_pe_ttm` (PB-only) and **add** the
inverted PE-only case — a `replace_keys=True` fetch whose rows all have `pb=None`
must write 0 rows and leave the cached rows untouched.

**No-sleep autouse fixtures** patching `legulegu_fetch._sleep` → no-op, added to the
two offline suites that drive the real fetch wrapper:
`tests/fundamentals/test_akshare_index_valuation.py` and
`tests/fundamentals/test_provider.py` (its `test_akshare_provider_index_equals_direct_call`
calls `fetch_cn_index_valuation` twice). The wiring test is source-grep only — no
fixture needed.

## Then: operator gates (real network, cold window)

Run **after** the limiter recovers from the prior session's deep cooldown (do all
offline TDD first; probe live only once cold).

0. Cold-window probe: `fetch_cn_index_valuation('csi300')` returns numbers.
1. **Gate #4:** `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare
   tests/fundamentals/test_index_valuation_live.py -v -s` → 4 passed (the speculative
   sweep stays skipped without `IRC_RUN_LEGULEGU_SPECULATIVE=1`). If the limiter still
   trips, raise `_LEGULEGU_GAP_S` and re-run.
2. **Gate #3:** `uv run irc run --from ingest` then
   `count_grounded.py outputs/<date>/opportunity_report.json` → grounded (real PE-TTM)
   ≥ 9; csi500/sse50 land; 161721/003318 NOT grounded.
3. **Gate #5:** Steps 1–5 in `docs/2026-06-05-phase-a-broad-grounding/before-after.md`.

## Out of scope

- Full PB carry-forward (merge fresh PE with cached PB on disjoint dates) — separate PR.
- Pacing the csindex sector leg.
- Exposing `valuation_percentile_fundamental` on the opportunity row (deferred item #2).
- `VERSION` stays `0.9.3`; changes accumulate under CHANGELOG `[Unreleased]`.
