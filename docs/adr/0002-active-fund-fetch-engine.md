# ADR 0002 — Active-fund fetch engine: cache, freshness, budget, and exchange routing

**Status:** Accepted (2026-05-22, item 003)
**Supersedes:** none. Builds on [ADR 0001 — citation data model](0001-citation-data-model.md).

## Context

Item 003 introduces the runtime fetch engine that produces per-constituent evidence for every CN active equity fund (`asset_class="cn_equity_fund"`). The engine sits between the cached-snapshot layer (item 002) and the citation gate (item 009). Failures here cascade — a wrong cache key silently serves stale evidence; a missing freshness probe quietly violates the dual-coverage gate; an unbudgeted fetch path bricks every downstream artifact in the run.

Four contracts are non-obvious, expensive to reverse, and the product of a real trade-off:

1. **Cache layout keyed by provider-declared disclosure quarter**, not calendar quarter.
2. **Fail-closed freshness contract** — any probe failure forces a full re-fetch.
3. **Preflight budget ledger** — abort BEFORE the per-instrument loop, not mid-loop.
4. **Exchange-routing rules with forbidden adapter pairs** — wrong adapter for a market produces silently-wrong data, not an error.

This ADR locks all four. Reviewers reading any of `snapshot_cache.py`, `_build_active_fund_snapshot`, or `_build_rows` six months from now should land here first.

## Decision

### 1. Cache key = disclosure quarter, not calendar quarter

Active-fund cache path is:

```
data/fundamentals/{source_report_quarter}/active_fund/fund_{instrument_id}.json
```

where `source_report_quarter` is parsed FROM THE PROVIDER RESPONSE (`季度` column text like `"2024年1季度股票投资明细"` → `"2024Q1"`), NOT from `date.today()`. The provider's disclosure quarter and the calendar quarter diverge by 1–4 months (a fund disclosing 2024Q4 holdings in March 2025 must cache under `2024Q4`, not `2025Q1`).

The legacy `ConstituentSnapshot` cache layout (`data/fundamentals/{calendar_quarter}/{display_cn}.json`) is **left untouched** to avoid migrating other consumers in this slice — item 010 owns any unification.

**Trade-off considered:**
- *Alternative*: key by `output_date` (e.g. `data/fundamentals/2026-05-22/...`). Rejected — would explode disk usage and force a refetch every day even when the provider hasn't disclosed a new quarter.
- *Alternative*: key by calendar quarter. Rejected — the provider's disclosure cadence is the only thing that matters for "is this data fresh."

### 2. Fail-closed freshness probe

A cached active-fund snapshot is "fresh" iff `(today - cache_probed_at).days <= IRC_CACHE_FRESHNESS_DAYS` (default 7). On stale + canonical output paths, fire a freshness probe:

```python
probe = fetch_cn_etf_holdings(provider_symbol, top_n=1)
```

- Probe succeeds with same quarter → update `cache_probed_at`, reuse cached body. No full refetch. (1 AkShare call.)
- Probe succeeds with newer quarter → full refetch. New cache written under new quarter dir; old cache file at old dir is NOT deleted (disk hygiene is item 010's concern).
- Probe raises OR returns empty → **fail-closed: schedule full refetch.** The probe is counted against the budget; a partial failure does not silently serve stale data.

`--rebuild-fundamentals` bypasses the probe and forces full refetch.

**Trade-off considered:**
- *Alternative*: fail-open (if probe errors, reuse cache). Rejected — would mask AkShare regressions and serve stale evidence to the citation gate without surfacing. The point of fail-closed is to make staleness loud.
- *Alternative*: time-only TTL (no probe). Rejected — funds re-disclose quarterly, not on a fixed wall-clock cadence. The probe is cheap (1 call per stale fund per N days) and detects mid-quarter re-disclosures.

### 3. Preflight budget gate, not mid-loop check

`FetchPlan` is computed at the start of `_build_rows` BEFORE any adapter call other than cache reads:

```python
total_calls = (cold + stale) * (1 + top_n * 3) + passive_overhead
if total_calls > IRC_FETCH_BUDGET:      # default 2000
    raise FetchBudgetExceeded(plan, total_calls, IRC_FETCH_BUDGET)
```

Abort exits with code 3 and prints a per-category breakdown to stderr. No `.tmp` files in `outputs/<date>/` are created — the gate runs before any output write.

Mid-loop budget checks are explicitly NOT added: they would slow down the hot path with per-call accounting AND would leave the system in an indeterminate state (some funds rebuilt, others stale). Preflight + atomic completion is simpler and safer.

`plan_hash = sha256(f"{output_date}:{','.join(sorted(instrument_ids))}:{top_n}").hexdigest()[:12]` is computed BEFORE the fetch loop and pins the resumable state file. If `top_n` or the universe shape changes mid-run (impossible within a single process, possible across re-runs), the stale state file is silently discarded and the new run starts fresh.

**Trade-off considered:**
- *Alternative*: mid-loop budget tracking with graceful degradation (cap per-fund to fit). Rejected — produces non-deterministic outputs where the "cheap" funds get full evidence and the "expensive" ones don't.
- *Alternative*: no budget at all. Rejected — a buggy universe expansion could cost thousands of AkShare calls and trigger upstream rate-limits.

### 4. Exchange routing — forbidden adapter pairs

For every `FundHolding`, the engine routes per `FundHolding.exchange`:

| Exchange | Filing (data) | Broker (info) | News (info) | Forbidden |
|---|---|---|---|---|
| `SH`/`SZ`/`BJ` | `fetch_cn_filing_digest` | `fetch_cn_broker_reports` | `fetch_cn_stock_news` | — |
| `HK` | `fetch_hk_filing_digest` | none (no HK broker adapter in V1) | `fetch_hk_stock_news` | `fetch_cn_filing_digest`, `fetch_cn_broker_reports`, `fetch_cn_stock_news` |
| `US` | none (V1 stub) | none | none | all CN/HK adapters |
| `UNKNOWN` | none | none | none | all |

The "forbidden" column is enforced by the dispatcher's branch structure and by test assertions (criterion 7). Misrouting a HK ticker to `fetch_cn_*` returns nonsense data with no provider error — the parser stamps `exchange_unknown` rather than guessing.

**Trade-off considered:**
- *Alternative*: try all adapters on every holding; let the providers reject. Rejected — silently returns partial-junk for HK tickers (provider tolerates them, parses nothing usable). Test fixtures would not catch this.

## Canonical failure-reason list

The engine emits structured failure reasons for downstream gap-stamping (item 006). Codes are stable strings; item 006 keys off the prefix before the `:`. See `003-spec.md` §"Failure reason codes" for the full table.

Stability invariants:
- Codes are sorted alphabetically in serialised state files for deterministic diffs.
- New codes require an ADR amendment (this file) and a corresponding update to item 006's gap-stamping table.
- Existing codes are never repurposed — renaming requires a new code + temporary parallel emission.

## Consequences

**Positive:**
- Disk usage bounded by `(num_funds × num_disclosed_quarters)` — typically <100 MB total.
- Re-running the same `irc opportunity` command on the same `outputs/<date>/` path costs zero AkShare calls (covered by acceptance criterion 12).
- Concurrent canonical runs are impossible (advisory `fcntl.flock` rejects the second).
- Wrong-adapter-for-market bugs are caught by tests, not by silently-wrong outputs.

**Negative:**
- Migrating any of these four contracts later requires touching every cache file on disk (manual delete) and every downstream consumer (item 006, 007, 009).
- `fcntl.flock` is Unix-only; Windows fallback is a no-op + stderr warning. Acceptable per CLAUDE.md (the deployment surface is macOS/Linux).
- The legacy `ConstituentSnapshot` cache layout coexists with the new active-fund layout. Two cache code paths until item 010 unifies them.

## Related

- [ADR 0001 — citation data model](0001-citation-data-model.md): `citation_id` provenance contract that every emitted `ThesisEvidence` must satisfy. Item 003 inherits the contract unchanged — the new `ThesisEvidence.holding_weight_pct` field is appended AFTER `citation_id` and is NOT part of the hash preimage.
- `docs/2026-05-22-thesis-cards-evidence-gap/items/003-spec.md`: the implementation spec this ADR governs.
- `docs/diagnosis-thesis-cards-evidence-gap.md` §Slice A, §Slice G: the source diagnosis that motivated the engine.
