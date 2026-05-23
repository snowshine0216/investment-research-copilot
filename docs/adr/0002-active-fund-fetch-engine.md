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

### 5. Fund-level engine (Slice F, item 005)

Item 005 adds a parallel **fund-level fetch engine** for the four V1 non-active asset classes (`gold`, `cn_bond_fund`, `cn_etf`, tracked CN indices that ARE themselves tradeable funds). The engine reuses contracts §1–§3 with the following per-slice adaptations; contract §4 (forbidden adapter pairs) does **not** apply (fund-level dispatches by `target.kind`, not by holding exchange).

**Cache layout (extends §1):**

```
data/fundamentals/{source_report_quarter}/nav/fund_{fund_id}.json
```

Parallel to `active_fund/`. `source_report_quarter` for fund-level snapshots is derived from `FundNavReport.latest_nav_date` via the existing `infer_quarter` helper (calendar-quarter rule — NAV is a daily series, the provider does not declare a fiscal disclosure quarter for NAV the way it does for holdings). Atomic write uses the same `.tmp.{pid} → os.replace` pattern as `active_fund/`.

The legacy `ConstituentSnapshot` cache layout under `data/fundamentals/{calendar_quarter}/{display_cn}.json` is **left untouched** — it now serves only the raw-index display path (`_TARGET_REGISTRY` keyed by `display_cn`). Three cache code paths coexist until item 010 unifies them.

**Freshness probe (extends §2):**

`fund_open_fund_info_em(symbol, indicator="单位净值走势")` does NOT expose a top-N parameter — it always returns the full NAV history. The "probe" is therefore equal in cost to a full refetch. Trade-off considered:

- *Alternative*: add a `top_n=1` parameter to `fetch_fund_nav_report` (extra adapter surface). Rejected — would require post-fetch DataFrame truncation since the upstream doesn't support pagination, adding API surface for no real saving.
- *Decision*: a stale-cache hit on the canonical path proceeds directly to a full refetch (NAV + 3 announcement endpoints). `cache_probed_at` is updated either on a successful re-read with same `source_report_quarter` (re-emit cached body) or on a full rebuild. Fail-closed semantics still hold: any adapter exception forces re-fetch state, never silent stale reuse.

`--rebuild-fundamentals` bypasses the freshness check exactly as for active funds.

**Preflight budget (extends §3):**

Per cold fund-level row: 1 NAV call + 3 announcement endpoints = **4 AkShare calls**. Per stale fund: same 4 calls (probe = refetch). V1 universe ≈ 5 gold/bond/etf rows + ~15 broad/sector index ETFs ≈ 20 funds × 4 calls = **80 calls** comfortably under `IRC_FETCH_BUDGET=2000`. Combined with item 003's ~1620 active-fund calls, total V1 cost is well below the budget.

The `FetchPlan` ledger gains a `fund_level_cold + fund_level_stale` categorical breakdown (concrete dataclass shape deferred to item 005's plan phase). Preflight abort behaviour is unchanged.

**Dispatch contract (new):**

`build_snapshot(target: LookthroughTarget)` routes by `target.kind` **only** — `target.key` and `target.display_cn` are never read by the new dispatch branches:

| `target.kind` | Branch | Notes |
|---|---|---|
| `active_fund` | `_build_active_fund_snapshot` | Item 003 (unchanged) |
| `qdii_us` / `qdii_hk` / `qdii_global` | `_build_qdii_sentinel_snapshot` | Zero AkShare calls; sentinel `evidence_gaps=("qdii_information_unavailable",)` |
| `gold` / `bond` / `broad_index` / `sector_theme` **with non-empty `provider_symbol`** | `_build_fund_level_snapshot` | NAV + 3 announcement endpoints |
| (else / empty `provider_symbol`) | `_build_legacy_snapshot` | Display-only; `_TARGET_REGISTRY`-keyed `## 持仓明细` appendix |

`map_lookthrough` is patched in item 005 to populate `provider_symbol=inp.instrument_id` for the four kinds that dispatch to fund-level (gold, bond, broad_index, sector_theme — when the instrument IS itself a tradeable fund). When `provider_symbol` is empty (raw-index display target), the row falls through to the legacy display-only path — correct behaviour (no fund to fetch NAV for).

**F5 static-profile invariant (new):**

`ak.fund_open_fund_info_em(symbol, indicator="基金概况")` MUST NOT be called by the production engine. Fund profile text is static metadata, not a time-bound communication; tagging it `citation_kind="information"` would silently bypass the freshness intent of the information leg. The invariant is enforced **upstream at the adapter layer** — `fetch_fund_nav_report` only consults `indicator="单位净值走势"`, and the information leg emits only via `fetch_fund_announcements` (the 3 topic-specific endpoints). There is no downstream gate enforcement (and none possible — `ThesisEvidence` carries no `indicator` field). Locked by an acceptance test that greps for the literal `"基金概况"` in `src/irc/fundamentals/akshare_fundamentals.py` and asserts zero production-code matches.

**F4 QDII sentinel (new):**

QDII V1 exclusion is **the only mechanism by which a row acquires `evidence_gaps=("qdii_information_unavailable",)`**. The sentinel `FundLevelSnapshot` is computed in-process (zero AkShare calls) and is **NOT serialised to disk** (gap-only rows have nothing to cache; in-process re-emission is cheaper than I/O). Item 006's H3 universal-gap invariant reads this gap from the in-memory snapshot and routes the row to the discipline failure section.

**Citation-id determinism for empty-URL announcements (new):**

Fund announcements have no `公告链接` column in AkShare 1.18.63's topic-specific endpoints. Per ADR 0001 §2, when `url=""` the citation-id preimage falls back to `f"{source}:{date}:{summary[:64]}"`. Item 005's adapter sets `summary = f"[{report_id}] {title}"` so the discriminating `report_id` (e.g. `AN201307240003689710`) lands in the first ~24 chars of `summary[:64]` — well within the fallback window. Two announcements with identical title and date but different `report_id` produce distinct `citation_id` values. ADR 0001 §2 is unchanged; the determinism contract is satisfied.

**Trade-offs considered for §5 as a whole:**

- *Alternative*: write a new ADR 0003 for the fund-level engine. Rejected — the four contracts (cache layout, freshness probe, preflight budget, plus the new dispatch table) are direct extensions of the active-fund engine. Co-locating them in ADR 0002 keeps the "fetch engine" decision surface in one document.
- *Alternative*: extend `ThesisEvidenceKind` with a new literal `"nav"` (or `"nav_metric"` per the diagnosis). Rejected — the existing `"snapshot"` literal semantically aligns with "single periodic data point" and item 009's per-driver gate map already handles `"snapshot"` → data-leg via standard rules. Adding a new literal would require touching every existing consumer (the type-rank ordering in `_flatten_analyses`, the renderer's per-type dispatch, etc.) for no semantic gain. Reuse `"snapshot"` for NAV.

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
