# ADR 0014 — legulegu broad-leg rate-limiting: paced dual-policy retry + non-destructive sweep suspension via a caught exception

**Status:** Accepted (2026-06-08, Phase A rate-limit hardening)
**Spec:** `docs/superpowers/specs/2026-06-08-phase-a-legulegu-rate-limit-design.md`
**Builds on:** [ADR 0002](0002-active-fund-fetch-engine.md) (§3 preflight budget — the `FetchBudgetExceeded` raise-to-stop precedent this mirrors), [ADR 0010](0010-cn-fundamentals-provider-seam.md) (the degrade-to-`None`/never-raises provider-seam contract this preserves for `fetch_cn_index_valuation`).
**Glossary:** CONTEXT.md "Valuation inputs" (`index_valuation_history`, `LeguleguCooldownExhausted`) + "Failure-mode + audit policy" (`advisory_gaps` boundary).

## Context

The broad-index PE/PB ingest leg grounds equity `valuation_state` on the legulegu PE-TTM percentile. It fires **8 calls** per run — `tuple(sorted(_LEGULEGU_INDEX_SYMBOL))` = `(csi1000, csi300, csi500, sse50)` × (`stock_index_pe_lg` + `stock_index_pb_lg`) — in one `ingest_index_valuation_history(..., replace_keys=True)`. Each AkShare 1.18.60 endpoint call is itself **two HTTP GETs** to legulegu (`get_cookie_csrf` scrapes the CSRF page, then the API GET + `r.json()`).

legulegu (Aliyun Tengine, `acw_tc`) admits a **burst of ~3 requests then HTTP-504s for a cooldown that escalates under sustained load**. A 504 surfaces two ways, neither exposing the status code: the CSRF GET → `AttributeError('NoneType' … 'attrs')` (no CSRF `<meta>`), or the API GET → `requests.exceptions.JSONDecodeError` (HTML body to `r.json()`). The naive sweep loses ~5 of 8 calls **every weekly run** — confirmed rate-limiting, not an outage (06-08 probes pulled live numbers for all four symbols).

The repo's contracts constrain the fix: the fetch layer's documented **degrade-to-`None` "never raises"** contract; **effects at edges / no shared mutable module state**; the ADR 0010 provider seam (which wraps `fetch_cn_index_valuation` only — `fetch_cn_index_valuation_history` is **ingest infra, not a provider method**).

## Decision

A focused `src/irc/fundamentals/legulegu_fetch.py` primitive paces and retries the legulegu calls, and a **caught control exception** suspends the sweep once throttling recurs. Six coupled decisions:

1. **Pace before every attempt; dual-policy retry.** A `GAP` (4s) is slept before each legulegu call so the burst detector never trips. Failures split into two policies: **ordinary network** transients (`requests.exceptions.ConnectionError`/`Timeout` — added *explicitly* because they are **not** subclasses of the builtin `ConnectionError`/`TimeoutError`, so `akshare_client._is_transient_network_error` misses them — plus the builtin/urllib3 cases) retry 3× with 3s·6s backoff, returning `None` on exhaustion (per-symbol miss, sweep continues); the **throttle** signature waits 30s and retries **once**.

2. **Throttle is an honest heuristic, not a measured 504.** AkShare hides the status code, so `_is_throttle_signature` matches the two observed 504 surfaces: `AttributeError` containing **both** `NoneType` and `attrs` (tightly), and `json.JSONDecodeError` (covers `requests.JSONDecodeError ⊂ json.JSONDecodeError`). A `KeyError('data')` — a JSON *envelope* / schema change — is deliberately left **fatal** (→ `None`, no cooldown) so a real legulegu schema break **fails loud at gate #4** rather than masquerading as throttling forever. Exhaustion means *"the throttle signature repeated after our judgment-value wait,"* **not** a confirmed provider cooldown.

3. **Suspend the whole sweep by raising `LeguleguCooldownExhausted` from `fetch_cn_index_valuation_history`.** On throttle-retry exhaustion the fetcher **raises**; the ingestor catches it, `break`s the per-key loop (logging the trip key + remaining skipped keys), and writes whatever landed first. This reuses the `FetchBudgetExceeded` raise-to-stop idiom but is **caught and non-fatal** (best-effort leg; the run continues). **The asymmetry is deliberate, not a bug:** `fetch_cn_index_valuation` (the ADR 0010 provider method) still **never raises** — it catches the same signal → `None`, preserving the seam. The never-raises contract is load-bearing only across the provider seam; `_history` has exactly one caller (the ingestor), which handles the signal.

4. **Suspension is whole-sweep but non-destructive.** legulegu's limiter is shared across symbols and escalates, so poking later symbols after a confirmed-repeat throttle only deepens it — stop. A skipped key is never appended to `keys_to_replace`, so its cached `index_valuation_history` rows are never DELETEd: a skipped key with mature history **still grounds on PE-TTM this run**. Suspension defers the *refresh*, it does not un-ground; only uncached/immature keys fall back to the NAV percentile (which they already did by design).

5. **The PB-wipe guard is a destructive-wipe preventer, not a completeness guarantee.** Under `replace_keys=True` the DELETE+replace now requires **both** axes present (`any(pe) AND any(pb)`); a frame missing an axis entirely skips (cache preserved). It does **not** guarantee a complete replacement — PE/PB dates are unioned, so a single stale PB observation still passes `any(pb)`. Full date-aligned carry-forward is deferred to a separate PR.

6. **Throttling is logged, never stamped on a row.** Skip + suspension emit tested WARNINGs (event type · key · missing-axis/skipped-keys · `cache preserved`). It is **not** an `OpportunityRow.advisory_gap`: `advisory_gaps` describe *current row-level evidence quality*, whereas throttling is a *run-level ingest operational event* — and an ungrounded row may be uncached, immature, unsupported, OR throttled, which the opportunity stage cannot honestly disambiguate. A durable chronicity signal (a run-level ingest diagnostic artifact, not a row field) is deferred.

## Considered options

- **Q1 — breaker object threaded `ingestor → _history → fetch_legulegu_frame` (return `None`, set a `tripped` flag) to keep the literal never-raises wording.** Rejected: a mutable dependency through three layers + a `_FetchFn` signature change, for arguably less clarity than reusing the existing `FetchBudgetExceeded` raise idiom. The chosen raise pays off the contract debt by scoping the docstring instead.
- **Q2a — per-symbol skip (skip only the throttled key, keep trying the rest).** Rejected: the limiter is provider-wide and escalating; continuing re-arms it and loses the next symbols too. Whole-sweep suspension lands what we got and lets the rest return cold next run.
- **Q2b — treat `KeyError('data')` as throttle too.** Rejected: a schema change surfaces as `KeyError`, and masking it as "throttling" hides a real code-fix-needed break; keeping it fatal makes gate #4 fail loud.
- **Q4 — stamp a per-row `index_pe_source_throttled` advisory_gap.** Rejected: semantically wrong (run-level event vs row-level quality), cross-stage plumbing, and it contaminates the H3/SAME-3-sensitive reporting surface.
- **Cooldown calibration.** The 30s/1-retry are judgment values biased toward early suspension (safe, because suspension is non-destructive); gate #4 calibrates the happy-path `GAP`, not the cooldown duration.

## Consequences

- **Gate #4 must run with `-x`/`--maxfail=1`.** The live test uses the single-shot (never-raises) path, so it gets no batch suspension; `-x` halts on the first `csi1000` failure before hammering the other three symbols when the limiter is hot.
- Pacing adds `~8 × GAP ≈ 32s` (+ latency) to every run that executes the ingest stage; `--resume` pays it only if the halt stage was ingest. No freshness-skip this PR.
- Deferred: full PB date-aligned carry-forward; the run-level ingest diagnostic artifact for chronicity; pacing the csindex sector leg (verified unnecessary — csindex is a single static-Excel GET from `oss-ch.csindex.com.cn`, no burst limiter).
- Citation / H3 / SAME-3 / Policy B / dual-coverage invariants are structurally untouched (no new `ThesisEvidence`, no row fields, no gap codes).
