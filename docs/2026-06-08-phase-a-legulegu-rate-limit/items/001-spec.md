# Phase A — legulegu broad-leg rate-limit hardening + PB-wipe guard

*2026-06-08. Follow-up to `2026-06-05-phase-a-broad-index-grounding-design.md`.
Rev 2: batch-scope cooldown suspension + throttle-heuristic honesty + gate-1 repair.
Rev 3: grilled (see Q1–Q5) — decisions ratified in [ADR 0014](../../adr/0014-legulegu-rate-limit-handling.md).*

## Problem

The broad-index PE/PB ingest leg fires **8 calls** (4 keys × `stock_index_pe_lg` +
`stock_index_pb_lg`) in one `ingest_index_valuation_history(..., replace_keys=True)`
(`commands/ingest_cmd.py:576`). Each AkShare 1.18.60 endpoint call is itself **two
HTTP GETs** to legulegu: `get_cookie_csrf(...)` scrapes the HTML page for a CSRF
token, then `requests.get(api_url, ...)` + `r.json()` fetches the data. legulegu
(Aliyun Tengine, `acw_tc`) admits a **burst of ~3 requests, then HTTP-504s for a
cooldown that escalates under sustained load**.

A 504 surfaces in **two** ways, neither of which exposes the status code:

1. **CSRF GET 504** → page has no CSRF `<meta>` → `csrf_tag.attrs` on `None` →
   `AttributeError("'NoneType' object has no attribute 'attrs'")`.
2. **API GET 504** → `r.json()` on the HTML error body →
   `requests.exceptions.JSONDecodeError` (subclass of `json.JSONDecodeError`).

`_fetch_frame` swallows both → `None`. Net: csi500 / sse50 / csi300-PB chronically
fail to land **every weekly run** — upstream throttling, not an outage (06-08 probes
pulled live numbers for all four symbols). The durable fix is **polite client
behaviour**: pace so the burst detector never trips, retry the transient 504 once
after a wait, and **stop the whole sweep when the throttle signature repeats after
that wait** rather than poking all 8 calls. We deliberately do **not** claim to
*measure* the provider's cooldown — exhaustion means "the throttle signature recurred
after our judgment-value wait," which is enough to justify backing off.

## Decisions (locked)

- **D1 — Pacing constants hardcoded**, no env knob (YAGNI). Conservative starting
  values; **gate #4 calibrates** them against the live limiter.
- **D2 — PB-wipe gap:** add the narrow *"no destructive replacement when either axis
  is entirely absent"* guard **now**; full PB carry-forward is a separate PR.
- **D3 — Two retry policies.** Ordinary network blips (per-symbol) and the provider's
  escalating cooldown (provider-wide) are different and get different handling.
- **D4 — Cooldown exhaustion suspends the remaining broad-leg sweep** (run scope),
  not just the current call. Network exhaustion does not (it's per-symbol).
- **D5 — The throttle classifier is an honest *heuristic*, not a true 504 detector**
  (AkShare hides the status). Documented blind spots; HTTP-status adapter deferred.
- **D6 — Speculative live sweep is paced *and* separately opt-in gated.**
- **D7 — Skips are audited:** every skipped destructive replacement logs a WARNING
  with the key and missing axis, so chronic failure is operationally visible.
- **D8 — Gate #1 (wiring tests) is repaired** as part of this PR's TDD scope.

## Architecture

### 1. New module `src/irc/fundamentals/legulegu_fetch.py`

Self-contained paced-retry primitive (keeps the already-259-line
`akshare_index_valuation.py` from growing). Effects at the edge: `ak_call` is
**injected** (so existing tests patching `akshare_index_valuation._ak_call` keep
intercepting), `_sleep` is a module indirection so unit tests fast-forward.

Constants:

| Name | Value | Meaning |
|------|-------|---------|
| `_LEGULEGU_GAP_S` | `4.0` | inter-call pacing, slept **before every attempt** |
| `_LEGULEGU_NETWORK_ATTEMPTS` | `3` | total attempts for ordinary network transients |
| `_LEGULEGU_BACKOFF_S` | `3.0` | base of exp backoff between network attempts (3s, 6s) |
| `_LEGULEGU_COOLDOWN_S` | `30.0` | wait after a throttle signature |
| `_LEGULEGU_COOLDOWN_RETRIES` | `1` | at most one cooldown retry, then **suspend** |

Exception: `class LeguleguCooldownExhausted(Exception)` — the broad-leg suspension
signal. It names **our** exhausted cooldown-*retry* budget (the throttle signature
repeated after the judgment-value wait); it does **not** assert a measured provider
cooldown. The 30s wait and 1-retry are judgment values biased toward early suspension
(suspension is non-destructive — Q2), **not** calibrated to legulegu's real cooldown.

Classifiers (a failure is exactly one of: throttle / network / fatal; throttle is
checked **first** because `requests.JSONDecodeError` is also OSError-ish):

```python
def _is_throttle_signature(exc):
    """HEURISTIC: legulegu served a non-data throttle/error page instead of JSON.
    NOT a true HTTP-504 classifier — AkShare 1.18.60 hides the status code. Covers
    the two observed 504 surfaces (missing-CSRF AttributeError; JSON-decode of an
    HTML error body). Blind spots (documented, treated as FATAL → no cooldown
    retry): a JSON error *envelope* raises KeyError on data_json['data']; a genuine
    parser/schema change also trips the AttributeError arm. Durable fix = an HTTP
    adapter that preserves status codes (deferred)."""
    if isinstance(exc, AttributeError):
        m = str(exc)
        return "NoneType" in m and "attrs" in m   # both substrings, tightly
    return isinstance(exc, json.JSONDecodeError)    # incl requests.JSONDecodeError

def _is_network_transient(exc):
    # requests.exceptions.ConnectionError / Timeout are NOT subclasses of the
    # builtin ConnectionError / TimeoutError (verified MRO -> RequestException ->
    # OSError), so akshare_client._is_transient_network_error misses them. Reuse it
    # for builtin/urllib3 cases AND add the requests classes explicitly.
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
    _sleep(GAP_S)                         # pace before EVERY attempt
    try:
        result = ak_call(fn_name, symbol=cn_name)
        return result if isinstance(result, pd.DataFrame) else pd.DataFrame()
    except Exception as exc:
        if _is_throttle_signature(exc):
            if cooldown_used >= COOLDOWN_RETRIES:
                warn; raise LeguleguCooldownExhausted(...)   # SUSPEND the sweep
            cooldown_used += 1; _sleep(COOLDOWN_S); continue
        if _is_network_transient(exc):
            network_failures += 1
            if network_failures >= NETWORK_ATTEMPTS: warn; return None
            _sleep(BACKOFF_S * 2 ** (network_failures - 1)); continue
        warn; return None                  # fatal: degrade-to-None, no retry
```

Terminal behaviour by failure type:

- **network exhausted → returns `None`** (per-symbol miss; the sweep continues).
- **throttle signature repeated after the wait → raises `LeguleguCooldownExhausted`**
  (treated as provider-wide because legulegu's limiter is shared across symbols; the
  ingestor suspends the sweep — see §3).
- success non-DataFrame → empty DataFrame; fatal/non-transient → `None`. Final
  failure of every kind logs a WARNING (preserves `_fetch_frame`'s logging contract).

Exact sleep sequences (asserted in tests):

- network, succeeds on 3rd attempt → `[GAP, 3, GAP, 6, GAP]`, returns frame
- network, exhausts → `[GAP, 3, GAP, 6, GAP]`, returns `None`
- throttle, succeeds on retry → `[GAP, 30, GAP]`, returns frame (iter-2 call lands)
- throttle, exhausts → `[GAP, 30, GAP]` then **raises** (iter-2 call throttles again)

The loop is bounded (network ≤ 3, cooldown ≤ 1) — no unbounded retry.

### 2. `akshare_index_valuation.py` edits

Replace the **four** legulegu `_fetch_frame("stock_index_pe_lg" / "stock_index_pb_lg",
cn_name)` calls with `fetch_legulegu_frame(_ak_call, fn_name, cn_name)`. Then:

- **`fetch_cn_index_valuation_history` (ingest path): does NOT catch
  `LeguleguCooldownExhausted`** — it propagates to the ingestor for sweep suspension.
- **`fetch_cn_index_valuation` (single-shot / provider path): catches it → returns
  `None`** — preserves the module's documented *never-raises* contract (relied on by
  `AkShareProvider.fetch_index_valuation` / `FallbackProvider`). On the live gate #4,
  a throttled symbol therefore returns `None` and fails the hard assert loudly.
- The **csindex** sector call (`stock_zh_index_value_csindex`) stays on plain
  `_fetch_frame`. **Verified (not assumed):** it is a *single GET of a static Excel
  file* from `oss-ch.csindex.com.cn` (Alibaba OSS) via `pd.read_excel(url)` — no
  `get_cookie_csrf`, no two-GET CSRF dance, no dynamic API, so **no legulegu-style
  burst-limiter surface to pace**. The 14-slug sector leg is correctly left unpaced;
  this is not a hidden symmetric bug. legulegu is hit *only* by the broad-index leg,
  so gate #4 (8 broad calls) is a faithful proxy for production legulegu load.

### 3. `index_valuation_ingestor.py`

**(a) Both-axes guard + audit (D2, D7).** Require both axes present before the
destructive DELETE+replace, and **log a WARNING naming the missing axis** when
skipping:

```python
has_pe = any(p.pe_ttm is not None for p in hist.rows)
has_pb = any(p.pb is not None for p in hist.rows)
if replace_keys and not (has_pe and has_pb):
    _log.warning("index_valuation replace skipped for %s: missing %s axis "
                 "(cache preserved)", key, "pe" if not has_pe else "pb")
    continue
```

**Invariant (narrow — do not overstate):** the guard blocks a destructive
replacement only when an axis is **entirely absent** from the fresh frame. It does
**not** guarantee snapshot completeness — PE and PB dates are unioned at
`akshare_index_valuation.py:168`, so a single stale PB value or disjoint date sets
can still pass both `any(...)` checks. Closing that is the deferred carry-forward PR.

**(b) Sweep suspension (D4).** Catch `LeguleguCooldownExhausted` in the per-key loop,
log the **trip key AND the remaining skipped keys explicitly**, `break`, and write
whatever landed before the trip:

```python
for i, key in enumerate(index_keys):
    try:
        hist = fetch(key)
    except LeguleguCooldownExhausted:
        skipped = index_keys[i + 1:]
        _log.warning(
            "legulegu cooldown exhausted at %s; suspending broad-leg sweep — "
            "skipping %d remaining key(s): %s — cache preserved (skipped keys "
            "still ground if mature).",
            key, len(skipped), ", ".join(skipped) or "none",
        )
        break
    ...
```

The broad leg iterates `tuple(sorted(_LEGULEGU_INDEX_SYMBOL))` =
**`('csi1000', 'csi300', 'csi500', 'sse50')`** (lexical: `csi1000` first). A
fully-throttled sweep makes ~2 calls then stops — not 16. The sector leg
(`replace_keys=False`, csindex) never raises this, so its loop is unaffected. Catching
**inside** the ingestor (not in `ingest_cmd`) preserves the partial transaction —
keys that landed before the trip are still written.

**Suspension does NOT mean the skipped keys lose grounding.** A skipped key is never
appended to `keys_to_replace`, so its prior `index_valuation_history` rows are never
DELETEd (`index_valuation_ingestor.py:56,67`). The opportunity stage reads the
**cached** table, so a skipped key with mature cached history (≥ `MIN_PE_POINTS` /
`MIN_PE_DAYS`) **still grounds on PE-TTM this run** — only *uncached* or
*insufficient-history* keys fall back to the NAV percentile. The blast radius of a
mid-sweep trip is therefore "this run's *refresh* of the not-yet-fetched keys is
deferred to the next cold run," not "those keys go ungrounded."

### 4. `ingest_cmd` wiring + gate-1 repair (D8)

Production already uses `_LEGULEGU_INDEX_SYMBOL` + `replace_keys=True`
(`ingest_cmd.py:578`); no production change. But the source-grep wiring tests
(`tests/commands/test_ingest_index_valuation_wiring.py:13,19`) still assert the
removed `_BROAD_INDEX_KEYS` name and are **currently RED** (verified: 2 failed).
Repair them to assert the real surface: `_LEGULEGU_INDEX_SYMBOL`, `replace_keys=True`,
and (in `test_akshare_index_valuation.py`, structurally) that the **broad** fetchers
route through `fetch_legulegu_frame` while the **csindex sector** fetcher stays on
`_fetch_frame` (pins the paced/unpaced boundary).

### 5. Live test (`tests/fundamentals/test_index_valuation_live.py`)

- The 4-symbol parametrized hard-assert test calls `fetch_cn_index_valuation` (paces
  transparently; catches exhaustion → `None` → loud assert failure). It must **not**
  patch `_sleep`. This is gate #4 and its real pacing is the calibration check.
- The **speculative sweep** (line 60) routes through `fetch_legulegu_frame(_ak_call,
  ...)` and gains an **additional** skip gate `IRC_RUN_LEGULEGU_SPECULATIVE=1` on top
  of the existing `live_akshare` / `IRC_RUN_LIVE_AKSHARE` gating, so the 12-call sweep
  is a deliberate separate cold-window job, never running right before gate #3.

## Testing (TDD, red → green)

**New `tests/fundamentals/test_legulegu_fetch.py`** (fake `ak_call` + injected fake
`_sleep` recorder; no network):

- throttle match: `AttributeError("'NoneType' object has no attribute 'attrs'")` and
  `json.JSONDecodeError`/`requests.exceptions.JSONDecodeError` are throttle; a plain
  `AttributeError("widget has no attribute 'attrs'")` (no `NoneType`) is **fatal**; a
  bare `ValueError` is fatal; `KeyError('data')` is fatal (documented blind spot).
- network match: `requests.exceptions.ConnectionError`, `requests.exceptions.Timeout`,
  builtin `ConnectionError` are network.
- network success on 3rd attempt → returns frame; sleeps `[GAP, 3, GAP, 6, GAP]`.
- network exhaust → `None` after exactly 3 attempts (1 WARNING).
- throttle success on retry → returns frame; sleeps `[GAP, 30, GAP]`.
- **throttle exhaust → raises `LeguleguCooldownExhausted`** after exactly 2 attempts
  (sleeps `[GAP, 30, GAP]`, no 2nd cooldown retry).
- success returning a non-DataFrame → returns **empty DataFrame**.
- fatal error → `None` on first attempt, no retry, WARNING logged.

**Batch regression (`tests/data/test_index_valuation_ingestor.py`):**

- a `fetch` that raises `LeguleguCooldownExhausted` on the 2nd key → **later keys are
  never fetched** (record fetched keys), and rows from key 1 are still written.
- keep `test_replace_keys_skips_key_when_fetch_lacks_pe_ttm` (PB-only) and **add** the
  inverted PE-only case (all `pb=None`) → 0 rows written, cache untouched.

**Warnings are a tested contract** (via `caplog`), because they are this PR's *only*
operator-visible signal for a run-level ingest event. Each must carry four fields:

| Event | tokens asserted |
|---|---|
| **replacement skipped** (missing axis) | `replace skipped` · the key · the missing axis (`pe`/`pb`) · `cache preserved` |
| **sweep suspended** (cooldown) | `suspending broad-leg sweep` · the trip key · the skipped key list · `cache preserved` |

**`tests/commands/test_ingest_index_valuation_wiring.py`:** update the two red tests to
assert `_LEGULEGU_INDEX_SYMBOL` + `replace_keys=True`.

**No-sleep autouse fixtures** patching `legulegu_fetch._sleep` → no-op, in the two
offline suites that drive the real wrapper:
`tests/fundamentals/test_akshare_index_valuation.py` and
`tests/fundamentals/test_provider.py` (`test_akshare_provider_index_equals_direct_call`
calls `fetch_cn_index_valuation` twice).

## Then: operator gates (real network — each in its OWN recovered cold window)

Do all offline TDD first; probe live only once the limiter has recovered from the
prior session's deep cooldown. **Do not chain gates back-to-back** — each makes real
legulegu calls that re-arm the limiter. There is **no separate step-0 probe** (it
would contaminate gate #4); gate #4's hard asserts ARE the cold-window check.

1. **Recover → Gate #4 (alone):** `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare
   tests/fundamentals/test_index_valuation_live.py -v -s -x` → 4 passed (sweep stays
   skipped without `IRC_RUN_LEGULEGU_SPECULATIVE=1`). **`-x`/`--maxfail=1` is
   load-bearing**: the live test calls the *single-shot* path, which catches the
   cooldown signal → `None` per-call (no batch suspension), so on a hot limiter
   `csi1000` fails first and `-x` halts the run **before it hammers the other three
   symbols**. If a symbol returns `None` the limiter is hot → **stop, wait for full
   recovery**, and only then consider raising `_LEGULEGU_GAP_S` and re-running. Never
   re-run into an active cooldown.
2. **Recover → Gate #3 (alone):** `uv run irc run --from ingest` then
   `count_grounded.py outputs/<date>/opportunity_report.json` → grounded ≥ 9;
   csi500/sse50 land; 161721/003318 NOT grounded. (Production ingest now batch-suspends
   on cooldown, so a hot limiter yields a partial result without hammering.)
3. **Recover → Gate #5 (alone):** Steps 1–5 in
   `docs/2026-06-05-phase-a-broad-grounding/before-after.md`.
4. **(Optional, separate cold window) speculative sweep:**
   `IRC_RUN_LIVE_AKSHARE=1 IRC_RUN_LEGULEGU_SPECULATIVE=1 uv run pytest ...`.

## Known limitations / out of scope

- The throttle classifier is a **heuristic** (D5). A JSON error *envelope* (KeyError
  on `data_json['data']`) and a genuine schema change are treated as fatal → no
  cooldown retry. The durable fix — an HTTP adapter that preserves legulegu status
  codes — is **deferred**.
- **Chronicity is not measured this PR.** A WARNING gives *immediate* visibility but
  only measures chronicity if logs are retained and queried. The durable follow-up is
  a **run-level ingest diagnostic artifact / manifest status** recording fetched /
  skipped / suspended keys + cache freshness — explicitly **NOT** an
  `OpportunityRow.advisory_gap` (throttling is a run-level ingest operational event,
  not current row-level evidence quality; conflating them would contaminate the
  H3/SAME-3-sensitive reporting surface). Deferred.
- **Wall-clock cost (accepted, 5a):** pacing adds `~8 × GAP ≈ 32s` (+ network latency)
  to every run that **executes the ingest stage** (default `irc run`, `irc run --from
  ingest`). `irc run --resume` re-runs ingest **only** when the recorded halt stage was
  ingest; resuming from a later stage skips ingest and pays nothing. No freshness-skip
  this PR (`replace_keys=True` always re-fetches — its self-migration intent wants the
  refresh).
- Full PB carry-forward (merge fresh PE with cached PB on disjoint dates) — separate PR.
- Pacing the csindex sector leg — out of scope.
- Exposing `valuation_percentile_fundamental` on the opportunity row — deferred.
- `VERSION` stays `0.9.3`; changes accumulate under CHANGELOG `[Unreleased]`.
