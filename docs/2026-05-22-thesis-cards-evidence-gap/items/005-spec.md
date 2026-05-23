# Item 005 spec — per-asset-class citation coverage (Slice F, post-Q4-pivot)

## Goal

Item 005 closes the per-asset-class citation gap for the four **V1 actionable asset classes** — gold, cn_bond_fund, cn_etf, and tracked CN indices that ARE themselves tradeable funds — by emitting fund-level evidence: NAV/return metrics as the **data leg** (via `ak.fund_open_fund_info_em(symbol=fund_id, indicator="单位净值走势")`) and fund-specific announcements as the **information leg** (via the **three topic-specific endpoints** `fund_announcement_dividend_em` + `fund_announcement_report_em` + `fund_announcement_personnel_em` — adopted post-Q4 because the originally-planned `fund_announcement_em` is absent from AkShare 1.18.63, see `items/004-verify.md`). The slice also stamps the universal QDII V1 exclusion: every `qdii_us`/`qdii_hk`/`qdii_global` row emits a sentinel snapshot carrying `evidence_gaps=["qdii_information_unavailable"]` so item 006's H3 universal-gap invariant routes them ONLY to the discipline failure section. Active funds (item 003's `cn_equity_fund` flow) are untouched — they keep their per-constituent `ActiveFundSnapshot` path. Item 005 introduces a parallel cache layout `data/fundamentals/{source_report_quarter}/nav/fund_{iid}.json` alongside item 003's `active_fund/fund_{iid}.json`, both keyed by provider-declared disclosure quarter per ADR 0002. All new evidence satisfies ADR 0001's citation_id preimage contract verbatim: fund announcements set `url=""` and stash the opaque `报告ID` in `summary = f"[{report_id}] {title}"` (the preimage falls back to `f"{source}:{date}:{summary[:64]}"` when URL is empty, so the embedded report id participates in the hash — citation_ids remain deterministic and unique even without a URL column).

## In scope

### F1 — `FundNavReport` dataclass + cache layout

Add a frozen dataclass `FundNavReport` in `src/irc/fundamentals/types.py` (NOT `opportunity/types.py` — avoids the cycle item 003 fixed):

```python
@dataclass(frozen=True)
class FundNavReport:
    fund_id: str                               # e.g. "518880"
    fund_name: str                             # e.g. "华安黄金易ETF"
    latest_nav: float                          # 单位净值 — most recent point
    latest_nav_date: str                       # ISO date, e.g. "2026-05-22"
    nav_history: tuple[tuple[str, float], ...] # ((iso_date, nav), ...) ascending
    source_report_quarter: str                 # "2026Q1" — derived from latest_nav_date

    def __post_init__(self) -> None:
        # non-empty fund_id, latest_nav > 0, latest_nav_date ISO-shape,
        # nav_history non-empty with latest_nav_date == nav_history[-1][0],
        # latest_nav == nav_history[-1][1] (float equality after rounding to 6dp),
        # source_report_quarter matches /^\d{4}Q[1-4]$/.
        ...
```

Cache layout: `data/fundamentals/{source_report_quarter}/nav/fund_{fund_id}.json`. Writer + reader live next to item 003's active-fund cache code in `src/irc/fundamentals/snapshot_cache.py`. Disclosure-quarter derivation: `latest_nav_date` (an ISO date) → `infer_quarter(latest_nav_date)` reusing the existing helper. Atomic write via the existing `.tmp.{pid} → os.replace` pattern.

### F2 — `FundAnnouncement` dataclass + 3-endpoint unioned fetch (Q4-pivoted)

Add a frozen dataclass `FundAnnouncement` in `src/irc/fundamentals/types.py`:

```python
@dataclass(frozen=True)
class FundAnnouncement:
    fund_id: str       # e.g. "518880"
    title: str         # 公告标题
    topic: Literal["dividend", "report", "personnel"]  # endpoint origin
    date: str          # ISO date string, e.g. "2024-12-31"
                       # (AkShare returns datetime.date; adapter normalises)
    report_id: str     # 报告ID, e.g. "AN201307240003689710" — opaque citation reference

    def __post_init__(self) -> None:
        # non-empty fund_id/title/report_id; ISO-shape date.
        ...
```

Public adapter `fetch_fund_announcements(fund_id: str) -> tuple[FundAnnouncement, ...]` in `src/irc/fundamentals/akshare_fundamentals.py`:

1. Calls **three** endpoints **serially** via `_ak_call`:
   - `_ak_call("fund_announcement_dividend_em", symbol=fund_id)` → topic `"dividend"`
   - `_ak_call("fund_announcement_report_em",   symbol=fund_id)` → topic `"report"`
   - `_ak_call("fund_announcement_personnel_em",symbol=fund_id)` → topic `"personnel"`
   Each call wrapped in a try/except: per-endpoint failures **degrade to empty** (consistent with existing adapters' "never raise" contract) and are surfaced via the returned tuple being shorter than expected — caller stamps the gap.
2. Normalizes columns via the column-equivalence map identical to item 004's live test (`公告标题`→title, `公告日期`→date, `报告ID`→report_id, `基金代码`→fund). Handles AkShare's `datetime.date` return type for `公告日期` by calling `.isoformat()` (per item 004's `004-verify.md` §"Downstream impact for item 005" #3).
3. Unions across the 3 endpoints; **dedup key = `(fund_id, report_id)`** (one entry per provider-opaque announcement id; if the same `报告ID` appears in two endpoints, the first observed `topic` wins — deterministic by endpoint-call order: dividend → report → personnel).
4. Sorts the unioned list **descending by `date`, ascending by `report_id`** as tie-breaker (deterministic; `report_id` is sortable as a stable lexicographic string).
5. Returns `tuple[FundAnnouncement, ...]`. **Never raises** — exception per endpoint = log via a structured failure label, fall through to the remaining endpoints, return whatever was collected. Empty union → caller stamps `fund_announcements_unavailable`.

**Key spec deviation from MASTER-SPEC row 005:** the original spec mentions a single `fund_announcement_em` endpoint with a `公告链接` URL column. AkShare 1.18.63 has neither (item 004 confirmed). `报告ID` is the only opaque reference; `ThesisEvidence.url` stays `""` and `summary = f"[{report_id}] {title}"`. The ADR 0001 preimage contract still produces deterministic, unique citation_ids because the preimage falls back to `f"{source}:{date}:{summary[:64]}"` when URL is empty — the embedded `[{report_id}] ` prefix makes `summary[:64]` discriminate even between announcements with similar titles.

### F3 — `build_snapshot` dispatch + `_build_fund_level_snapshot`

Extend `build_snapshot(target: LookthroughTarget, ...)` in `src/irc/fundamentals/snapshot.py` with two new branches BEFORE the legacy `_build_legacy_snapshot` fall-through:

```python
def build_snapshot(target, *, top_n=10, as_of_iso=""):
    if target.kind == "active_fund":
        return _build_active_fund_snapshot(target, top_n=top_n)        # item 003
    if target.kind in {"qdii_us", "qdii_hk", "qdii_global"}:
        return _build_qdii_sentinel_snapshot(target)                   # NEW (F4)
    if target.kind in {"gold", "bond", "broad_index", "sector_theme"} \
       and target.provider_symbol:
        return _build_fund_level_snapshot(target)                      # NEW (F3)
    return _build_legacy_snapshot(target.display_cn, top_n=top_n,
                                  as_of_iso=as_of_iso)                 # display-only
```

`_build_fund_level_snapshot(target: LookthroughTarget) -> FundLevelSnapshot`:

1. Fetches `nav = fetch_fund_nav_report(target.provider_symbol)`.
2. Fetches `announcements = fetch_fund_announcements(target.provider_symbol)`.
3. Composes both into `ThesisEvidence` records:
   - **NAV (data leg)** — ONE evidence record with `type="snapshot"` (re-using the existing `ThesisEvidenceKind` literal — NAV is a single periodic data point, semantically aligned with "snapshot"), `scope="instrument"`, `citation_kind="data"`, `owner_instrument_id=target.provider_symbol`, `parent_fund_id=None`, `constituent_key=None`, `url=""`, `summary=f"NAV={nav.latest_nav:.4f} @ {nav.latest_nav_date}"`, `date=nav.latest_nav_date`, `source=target.provider_symbol`. **No `holding_weight_pct`** — instrument-scope evidence does not carry a holding weight (ADR 0001 §Consequences).
   - **Announcements (information leg)** — ONE evidence record per `FundAnnouncement` returned, capped at the first **3** entries (deterministic — already sorted by F2). Each: `type="news"` (the closest existing literal — fund announcements are time-bound communication, semantically aligned with "news"; using "news" preserves the existing `_one_line_view` rendering and the type-rank ordering in `_flatten_analyses`), `scope="instrument"`, `citation_kind="information"`, `owner_instrument_id=target.provider_symbol`, `parent_fund_id=None`, `constituent_key=None`, `url=""`, `summary=f"[{a.report_id}] {a.title}"`, `date=a.date`, `source=f"fund_announcement_{a.topic}_em"`.
4. Writes the new `FundLevelSnapshot` to the NAV cache (`data/fundamentals/{nav.source_report_quarter}/nav/fund_{fund_id}.json`).

New dataclass `FundLevelSnapshot` in `src/irc/fundamentals/types.py`:

```python
@dataclass(frozen=True)
class FundLevelSnapshot:
    fund_id: str
    nav_report: FundNavReport | None       # None iff NAV fetch failed/empty
    announcements: tuple[FundAnnouncement, ...]
    evidence: tuple[ThesisEvidence, ...]   # composed by _build_fund_level_snapshot
    source_report_quarter: str             # mirrors nav_report.source_report_quarter,
                                           # empty when nav_report is None
    cache_probed_at: str                   # ISO timestamp (ADR 0002 freshness probe)
    fund_level_failure_reasons: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
```

`build_snapshot`'s return-type union widens to `ActiveFundSnapshot | ConstituentSnapshot | FundLevelSnapshot`. Callers in `opportunity_cmd.py` route on `isinstance(snapshot, FundLevelSnapshot)` to consume the new shape (the `_row_to_dict` serialiser shipped by item 002 already handles arbitrary `ThesisEvidence` tuples — only the new dataclasses need shape-aware serialisation in `snapshot_cache.py`).

### F4 — QDII universal exclusion sentinel

`_build_qdii_sentinel_snapshot(target: LookthroughTarget) -> FundLevelSnapshot` returns:

```python
FundLevelSnapshot(
    fund_id=target.provider_symbol or target.key,
    nav_report=None,
    announcements=(),
    evidence=(),
    source_report_quarter="",
    cache_probed_at="",
    fund_level_failure_reasons=(),
    evidence_gaps=("qdii_information_unavailable",),
)
```

This is the **only** mechanism by which QDII rows acquire `evidence_gaps`. NO AkShare call is issued for QDII — the sentinel is computed in-process. Cache: NOT written (gap-only rows have nothing to cache; re-emitting the sentinel on every call is cheaper than I/O).

### F5 — Static-profile exclusion invariant

`ak.fund_open_fund_info_em(symbol, indicator="基金概况")` is **NOT called** by item 005. If a future slice wants to surface fund profile text as metadata, it must be tagged with a NON-information citation_kind that does not exist today (`"metadata"` would be a new `CitationKind` literal — out of scope here). Document the invariant in CONTEXT.md (grill phase) and in a code comment on `fetch_fund_nav_report` so a future reader does not silently add it to the information leg. The existing `CitationKind = Literal["data", "information"]` is unchanged by item 005 — adding `"metadata"` would be a follow-up ADR amendment.

### F6 — Freshness probe + budget accounting (ADR 0002 reuse)

NAV cache freshness reuses item 003's contract verbatim:

- `(today - cache_probed_at).days <= IRC_CACHE_FRESHNESS_DAYS` (default 7) → fresh, reuse cached body, update `cache_probed_at`.
- Stale → fire a freshness probe via `fetch_fund_nav_report(fund_id)` with a 1-point limit (the existing adapter doesn't expose `top_n`; the probe is effectively a full re-call — accept the cost, document the trade-off). Probe success with the same `source_report_quarter` → reuse cached body, update `cache_probed_at`. Newer quarter or exception → fail-closed: refetch NAV + announcements.
- `--rebuild-fundamentals` bypasses the probe (existing flag from item 003).

**Preflight budget:** the FetchPlan computed at `_build_rows` entry must account for the new per-fund cost. Per cold fund: 1 NAV + 3 announcement = 4 calls. Per stale fund: 1 probe + (if newer quarter or fail) 4 calls = up to 5 calls. V1 universe: ~5 gold/bond/etf rows + ~15 broad/sector index ETFs ≈ 20 funds × 4 calls = 80 calls. Comfortably under `IRC_FETCH_BUDGET=2000`. The FetchPlan dataclass (item 003) gets a new field `fund_level_cold + fund_level_stale` (or extends the existing `cold/stale` tally with a categorical breakdown — concrete shape deferred to plan phase).

## Acceptance criteria

1. **New dataclasses live in `src/irc/fundamentals/types.py`.** `FundNavReport`, `FundAnnouncement`, `FundLevelSnapshot` — all `@dataclass(frozen=True)` with `__post_init__` validation as specified in F1/F2/F3. Each is added to the module's `__all__` export list. Construction with invalid args (empty fund_id, malformed date, negative NAV, missing `source_report_quarter` shape) raises `ValueError`.

2. **`fetch_fund_nav_report("518880")` returns a populated `FundNavReport`.** With AkShare mocked to return a realistic `单位净值走势` DataFrame (columns `净值日期`, `单位净值`, `日增长率`) for `518880`, the adapter returns `FundNavReport(fund_id="518880", fund_name="...", latest_nav>0, latest_nav_date ISO, nav_history non-empty, source_report_quarter matches "YYYYQ[1-4]")`. Unknown symbol or empty DataFrame → returns `None` without raising (consistent with `fetch_cn_filing_digest`'s contract). Fixture-driven unit test in `tests/fundamentals/test_fetch_fund_nav_report.py`.

3. **`fetch_fund_announcements("518880")` returns a unioned, deduplicated, sorted tuple.** With the 3 item-004 fixtures mocked in (`tests/fixtures/akshare/fund_announcement_{dividend,report,personnel}_em_518880.json`), the adapter returns a `tuple[FundAnnouncement, ...]` of length = `union(report_ids)` (dedup by `(fund_id, report_id)`), sorted by `date desc, report_id asc`. Each entry has `fund_id="518880"`, non-empty `title`/`report_id`, ISO `date`, `topic in {"dividend","report","personnel"}`. Verified for all 3 symbols (`518880`, `000001`, `005827`). The `005827` test confirms active funds CAN call this adapter (it's used by item 003's flow too? — NO; item 003's active-fund flow uses per-constituent evidence, not fund-level announcements. The `005827` test here is a fixture-shape regression only).

4. **Dedup verified.** Construct a unit test where two of the 3 endpoints return the same `报告ID` for `518880` → the unioned tuple contains ONE entry for that id (the one from the first-observed endpoint per the dividend→report→personnel call order). Dedup key = `(fund_id, report_id)`, not `(title, date)`.

5. **`build_snapshot(LookthroughTarget(kind="gold", provider_symbol="518880", ...))` returns `FundLevelSnapshot` with both legs cited.** Snapshot has: `nav_report` populated, `announcements` non-empty (≥1), `evidence` containing exactly one `citation_kind="data"` record (the NAV) AND ≥1 `citation_kind="information"` record (capped at 3 announcements). Every `ThesisEvidence` carries `scope="instrument"`, `owner_instrument_id=target.provider_symbol`, `parent_fund_id=None`, `constituent_key=None`. NAV evidence has `holding_weight_pct=None`.

6. **`build_snapshot(LookthroughTarget(kind="qdii_global", ...))` returns the QDII sentinel.** `FundLevelSnapshot(nav_report=None, announcements=(), evidence=(), evidence_gaps=("qdii_information_unavailable",))`. Zero AkShare calls fired (verified via `mocker.patch("irc.fundamentals.akshare_fundamentals._ak_call")` call-count assertion). Same assertion for `kind="qdii_us"` and `kind="qdii_hk"`.

7. **NAV cache layout = `data/fundamentals/{source_report_quarter}/nav/fund_{iid}.json`.** Writer creates parent dirs, atomic `.tmp.{pid} → os.replace`. Reader returns `None` on missing file or malformed JSON. Disclosure-quarter parsing matches ADR 0002 (`latest_nav_date="2026-03-15"` → `"2026Q1"`).

8. **Freshness probe contract matches ADR 0002.** Stale cache (`cache_probed_at` > 7 days) on a canonical run fires a NAV probe. Probe success with same quarter → cache reused, `cache_probed_at` advanced. Probe exception OR newer quarter → fail-closed, full refetch. `--rebuild-fundamentals` bypasses the probe. Test mocks `_ak_call` and asserts the probe call count + cache-write call count for each branch.

9. **F5 invariant: `基金概况` indicator is NOT consulted by item 005.** Grep `src/irc/fundamentals/akshare_fundamentals.py` for the literal `"基金概况"` returns ZERO production-code matches. (Test fixtures and comments are exempt.)

10. **Preflight budget includes fund-level calls.** Universe of 20 V1 funds → preflight reports `cold + stale = 20`, `total_calls ≤ 4 × 20 = 80`, well under `IRC_FETCH_BUDGET=2000`. With `--limit 3`, total ≤ 12. Test asserts the FetchPlan tally on a fixture universe.

11. **Citation_id determinism for announcement entries.** Two consecutive runs against the same fixtures produce byte-identical `citation_id` values for every `FundAnnouncement`-derived `ThesisEvidence`. Two announcements with the same `title` and `date` but different `report_id` produce distinct `citation_id`s (because `summary` differs via the `[{report_id}]` prefix → preimage's `summary[:64]` fallback discriminates them). Test in `tests/fundamentals/test_fund_level_snapshot_citation_ids.py`.

12. **Integration: `irc opportunity --output-dir /tmp/...` produces dual-coverage rows.** With fixture-mocked adapters (NAV + 3 announcement endpoints), the run produces `opportunity_report.json` entries for `518880` (gold), `000001` (bond), and one `cn_etf` row (e.g. `510300`) where the `thesis_evidence` field contains ≥1 `citation_kind="data"` AND ≥1 `citation_kind="information"` record, both with `scope="instrument"` and `owner_instrument_id` matching the row.

13. **Regression: item 003's active-fund flow unchanged.** `tests/fundamentals/test_active_fund_snapshot.py` (item 003's tests) pass without modification. `_build_active_fund_snapshot` is not touched. `cn_equity_fund` rows still route to `kind="active_fund"` → `_build_active_fund_snapshot`, NOT to the new fund-level dispatch.

14. **QDII rows appear ONLY in discipline failure section.** With a `qdii_global` row in the fixture universe, the integration run emits the row's sentinel `evidence_gaps=("qdii_information_unavailable",)`. Item 006's H3 invariant will route the row away from `thesis_cards.yaml` and `pick_rows` — item 005's job is ONLY to stamp the gap. Test asserts the gap is present on the snapshot; the H3 routing test is item 006's territory.

15. **Existing passive-fund display tests still pass.** `tests/fundamentals/test_snapshot.py` (legacy `_TARGET_REGISTRY` keyed by `display_cn`) is untouched. The `## 持仓明细` appendix path is preserved. Display-only entries are NEVER tagged `citation_kind="data"` or `citation_kind="information"` — they don't participate in the citation gate per CONTEXT.md "Passive ETF / tracked index".

16. **No new ADR required.** Item 005 inherits ADR 0001 (citation_id preimage — unchanged; `url=""` + `summary` carrying `[{report_id}]` is a valid preimage by §2's fallback) and ADR 0002 (cache layout, freshness, budget — extended along the same patterns). The grill phase decides whether the new dataclass triad warrants a CONTEXT.md expansion (likely yes for `FundNavReport`, `FundAnnouncement`, `FundLevelSnapshot`).

## Out of scope

- **Item 006 territory:** Policy B weight-aware quorum, `rejections.json` emission, H3 universal gapped-row routing, V1 systematic-exclusion summary line in `discipline_report.md`. Item 005 only stamps `evidence_gaps`; the routing is item 006.
- **Item 007 territory:** memo `evidence_pool` rendering of fund-level `ThesisEvidence`, discipline `_render_section` nested-evidence bullets, the `## 持仓明细` appendix expansion. Item 005's NAV + announcement evidence becomes consumable BY item 007 — but item 005 does NOT touch the renderers.
- **Item 008 territory:** the E10 coverage smoke across V1 asset classes locks the contract; item 005 ships the per-adapter unit tests + the integration smoke (criterion 12) but the cross-asset-class invariant test is item 008.
- **Item 009 territory:** the canonical-path block-mode citation gate. Item 005's evidence MUST satisfy the gate once item 009 flips it on; that's verified at item 009's verify phase, not here.
- **Active-fund flow (item 003) — untouched.** No changes to `_build_active_fund_snapshot`, `fetch_cn_etf_holdings`, `ConstituentAnalysis`, `ActiveFundSnapshot`, or the per-constituent evidence builders.
- **New AkShare adapters beyond the 4** (`fund_open_fund_info_em` + the 3 topic-specific announcement endpoints). No manager-commentary adapter, no US/HK news adapter (item 003 shipped HK news for active-fund constituents; passive QDII is V2 per the diagnosis).
- **DuckDB persistence of fund-level evidence.** Item 010 owns DuckDB ingest for holdings; fund-level NAV/announcements are not part of that slice.
- **`basket` → `instrument_id` reverse alias for ETFs that don't disclose holdings.** Out of scope; item 010's territory if/when needed.

## Constraints

- **Tests:** all unit tests mock `_ak_call`. NO new `live_akshare`-marked tests in item 005 (item 004 already verified the 4 endpoints live). The 9 fixtures from item 004 (`tests/fixtures/akshare/fund_announcement_{dividend,report,personnel}_em_{518880,000001,005827}.json`) are reused as mock data. A new NAV fixture `tests/fixtures/akshare/fund_open_fund_info_em_518880_nav.json` is added — its shape is captured from `tests/integration/test_live_endpoints.py:50-56` (the diagnosis confirms the endpoint is verified live), not from a new live call.
- **Citation contract:** ADR 0001 §2 preimage is unchanged. Fund announcements set `url=""` and rely on the `summary[:64]` fallback (`summary = f"[{report_id}] {title}"` puts the discriminating `report_id` in the first ~24 chars, well within the 64-char window).
- **Cache contracts:** ADR 0002's 4 contracts hold. Disclosure-quarter cache (§1) — `nav/` mirrors `active_fund/`. Fail-closed probe (§2) — same semantics, NAV-specific probe. Preflight budget (§3) — extended with fund-level cost. Forbidden adapter pairs (§4) — fund-level doesn't have "exchange routing" the way per-constituent does; the F3 dispatch is by `target.kind`. No new forbidden pairs.
- **`IRC_FETCH_BUDGET=2000`** default holds. V1's ~80 fund-level calls + item 003's ~1620 active-fund calls + freshness probes stays comfortably under.
- **Dataclass location:** all new dataclasses (`FundNavReport`, `FundAnnouncement`, `FundLevelSnapshot`) live in `src/irc/fundamentals/types.py`. NOT in `src/irc/opportunity/types.py` — that would re-introduce the cycle item 003's spec §"Module dependency" eliminated.
- **Functional programming:** every new helper is a pure function. I/O (AkShare calls, cache reads/writes) is isolated to `fetch_fund_nav_report`, `fetch_fund_announcements`, and the cache module. The dispatcher `_build_fund_level_snapshot` orchestrates but does not mutate. All new dataclasses are frozen + use spread to compose (`replace(snap, cache_probed_at=now)` rather than `snap.cache_probed_at = now`).
- **Backward compat:** `build_snapshot`'s caller in `opportunity_cmd.py` MUST handle the union `ActiveFundSnapshot | ConstituentSnapshot | FundLevelSnapshot`. The grill phase confirms the caller's existing isinstance ladder accommodates the new type without breaking the legacy display-only `ConstituentSnapshot` consumers (the `## 持仓明细` appendix path).
- **Dispatch correctness:** `target.kind` is the SOLE dispatch field. `target.key` and `target.display_cn` are NEVER read by the new dispatcher (those are display-only — coupled to `_TARGET_REGISTRY` keys). The grill phase confirms `map_lookthrough` already populates `provider_symbol` for `cn_etf` rows (asset_class `cn_etf` → likely `kind="broad_index"` or `kind="sector_theme"` depending on `tracked_index`/`theme`). If `provider_symbol` is empty for a `kind="broad_index"` row, the dispatcher falls through to the legacy display-only path (correct behaviour: row is an "index" reference, not a fund).

## Open questions for the grill phase

1. **Does `map_lookthrough` already populate `target.provider_symbol` for `cn_etf` rows?** If `cn_etf` with `tracked_index="csi300"` produces `LookthroughTarget(kind="broad_index", key="csi300", display_cn="沪深300", provider_symbol="")`, the new dispatch falls through to the legacy display-only path — defeating F1's intent. The grill phase MUST inspect `OpportunityInput` for ETF rows and confirm whether the fund's tradeable symbol (e.g. `"510300"` for 华泰柏瑞沪深300) flows into `provider_symbol`. If not, item 005 must patch `map_lookthrough` to populate it from `OpportunityInput.instrument_id` for `cn_etf` rows (a 5-line change, but it MUST happen here, not deferred).

2. **Does `tracked_index` (e.g., `kind="broad_index"` with NO `provider_symbol`) route to `_build_fund_level_snapshot` or the legacy display-only path?** Resolved-by-default: the dispatcher checks `target.provider_symbol` — empty → legacy path, populated → new path. The grill phase confirms whether the diagnosis doc's phrase "tracked CN indices" means "the index itself" (display-only) or "ETFs tracking that index" (fund-level). Item 005 currently assumes the latter.

3. **Does the NAV freshness probe need to be cheaper than a full refetch?** ADR 0002's active-fund probe uses `fetch_cn_etf_holdings(provider_symbol, top_n=1)` — a 1-point read. `fetch_fund_nav_report` has no `top_n` parameter; the probe IS the full call. The grill phase decides whether to (a) add a `top_n=1` parameter to `fetch_fund_nav_report` (extra adapter surface), or (b) accept the 1-call cost as the "probe" (current spec position — pragmatic, slightly redundant).

4. **Is `type="snapshot"` the right `ThesisEvidenceKind` literal for the NAV evidence record?** Existing literals are `Literal["filing", "broker", "news", "policy", "snapshot"]`. NAV is neither filing (it's a periodic data point, not a financial statement) nor broker (not opinion-derived). "snapshot" is the closest existing fit — but item 009's per-driver gate may key off `type` (the diagnosis at §D2a tags `"nav_metric"` as a separate type for gold/bond). The grill phase decides whether to (a) reuse `"snapshot"` (current spec position), (b) extend the literal to `Literal["..., "nav"]` (cleaner semantics, but item 009's per-driver gate then needs to map `"nav"` → data-leg), or (c) introduce `"nav_metric"` per the diagnosis. **Recommendation pending grill phase:** option (b) — add `"nav"` to `ThesisEvidenceKind`. Per-driver gate mapping is a 1-line addition to item 009's gate function.

5. **Should `FundLevelSnapshot` be cached when `evidence_gaps != ()` (QDII sentinel case)?** Currently no — the sentinel is computed in-process. The grill phase confirms whether item 006's H3 invariant reads from disk or from the in-memory snapshot. If from disk, the sentinel needs serialisation. Likely answer: in-memory, since QDII produces no fetchable data.

6. **CONTEXT.md additions:** `FundNavReport`, `FundAnnouncement`, `FundLevelSnapshot`, `NAV cache layout`, `Fund-level snapshot dispatch`, `QDII V1 sentinel`. The grill phase auto-accepts and writes these terms.

7. **ADR amendment vs. new ADR?** ADR 0002 §1 currently documents the `active_fund/` cache layout. Item 005 adds `nav/`. The grill phase decides whether to (a) amend ADR 0002 in place (adding §5 on fund-level cache), or (b) write a new ADR 0003 (fund-level evidence engine). Lean toward (a) — the contracts (disclosure quarter, fail-closed probe, preflight budget) are identical; only the per-fund call-count math changes.

## Files touched (preview for planner)

| File | Action |
|---|---|
| `src/irc/fundamentals/types.py` | Add `FundNavReport`, `FundAnnouncement`, `FundLevelSnapshot` dataclasses (frozen, `__post_init__` validation); extend `__all__`. |
| `src/irc/fundamentals/akshare_fundamentals.py` | Add `fetch_fund_nav_report(fund_id)` + `fetch_fund_announcements(fund_id)`. Both never raise; degrade-empty contract. |
| `src/irc/fundamentals/snapshot.py` | Extend `build_snapshot` dispatch (3-branch `if/elif/else` BEFORE legacy fall-through). Add `_build_fund_level_snapshot`, `_build_qdii_sentinel_snapshot`. Widen return type union. |
| `src/irc/fundamentals/snapshot_cache.py` | Add `nav_cache_path`, `write_nav_cache`, `load_nav_cache`. Parallel to existing `active_fund_cache_path` family. Same `.tmp.{pid} → os.replace` pattern. |
| `src/irc/opportunity/lookthrough.py` | (CONDITIONAL on grill Q1) — patch `cn_etf` branch to populate `provider_symbol=inp.instrument_id`. ≤5 lines. |
| `src/irc/commands/opportunity_cmd.py` | Extend the `isinstance(snapshot, ...)` ladder to handle `FundLevelSnapshot`. Forward `FundLevelSnapshot.evidence` into `OpportunityRow.thesis_evidence`. |
| `tests/fundamentals/test_fetch_fund_nav_report.py` (new) | Unit tests for NAV adapter — happy path + empty + unknown symbol. |
| `tests/fundamentals/test_fetch_fund_announcements.py` (new) | Unit tests for the 3-endpoint union, dedup, sort, `datetime.date` normalisation. |
| `tests/fundamentals/test_fund_level_snapshot.py` (new) | Unit tests for `_build_fund_level_snapshot` + `_build_qdii_sentinel_snapshot` + citation_id determinism. |
| `tests/fixtures/akshare/fund_open_fund_info_em_518880_nav.json` (new) | NAV fixture (shape from existing live test). |
| `CONTEXT.md` | Append fund-level glossary entries (grill phase). |
| `docs/adr/0002-active-fund-fetch-engine.md` | Append §5 (fund-level cache layout) — grill phase decides amend-in-place vs. new ADR. |

## Dependencies on other items

**Hard requires (must merge before item 005 — already done):**
- Item 001 (contributing_dimensions): no direct touch — item 009 reads this field.
- Item 002 (citation data model): `ThesisEvidence` schema + `_evidence_to_dict` serialiser. Item 005 emits new `ThesisEvidence` instances; the schema is verbatim from item 002.
- Item 003 (active-fund constituent layer): `_ak_call`, cache layout pattern, freshness probe pattern, FetchPlan budget. Item 005 reuses all of these.
- Item 004 (live verify): the 9 fixture files + the column-shape contract for the 3 topic-specific endpoints. Item 005's mocked unit tests consume these fixtures.

**Required-by (items that read item 005's outputs):**
- Item 006 (failure-mode + Policy B): reads `FundLevelSnapshot.evidence_gaps` for H3 routing; reads the QDII sentinel for the discipline failure section.
- Item 007 (memo + discipline renderers): reads `FundLevelSnapshot.evidence` for memo `evidence_pool` + discipline `_render_section` nested bullets.
- Item 008 (integration sweep): E10 coverage smoke asserts every V1 published row has dual-coverage `ThesisEvidence` — item 005's emissions are the data under test.
- Item 009 (citation gate block mode): the per-driver gate consumes item 005's evidence. NAV evidence must satisfy the data leg for gold/bond/etf rows; announcement evidence must satisfy the information leg.
