# Item 010 spec — DuckDB `fund_holdings` persistence + ingest wiring (Slice B)

> Grilled 2026-05-24 (auto-accept). All 10 open questions resolved; spec is plan-ready. See [`010-grill.md`](./010-grill.md) for verdict + audit findings.

## Goal

Persist fund holdings to the DuckDB `fund_holdings` table so the scoring layer's `holdings_concentration_top10` factor reads real data instead of NaN. Today the table is created but left empty — `scoring/metrics_loader._latest_holdings_concentration` therefore returns NaN, the quality factor in `scoring/factors/quality.py` falls back to a default in `scoring/pipeline.py` (`_get(m, "holdings_concentration_top10", 0.30)`), and the completeness gate in `decision/completeness.py` either drops the field for index ETFs or counts it as missing.

This slice introduces a thin pure-core ingestor module (`src/irc/data/fund_holdings_ingestor.py`) that takes a list of `(instrument_id, asset_class)` pairs, reuses item 003's `ActiveFundSnapshot` cache as the source of truth for CN active-fund holdings (no duplicate AkShare calls), falls back to a direct `fetch_cn_etf_holdings` call only for `cn_etf` instruments without a cached snapshot, and upserts rows into `fund_holdings` keyed on `(instrument_id, report_date, holding_ticker)`. Wiring in `ingest_cmd.py` invokes the ingestor for any `cn_equity_fund`/`cn_etf` instrument whose latest cached `report_date` is older than 30 days (or absent).

The slice is intentionally narrow:
- **No new fetch policy** — reuses item 003's active-fund cache and item 003's existing `fetch_cn_etf_holdings`.
- **No new budget** — operations are at most one DuckDB read per instrument (staleness check) plus one DuckDB upsert per stale instrument. AkShare calls happen ONLY for `cn_etf` cache misses (active funds reuse item 003's cache).
- **No effect on `OpportunityRow.evidence_gaps`** — this slice feeds the scoring layer, not the opportunity layer.
- **No schema migration** — the `fund_holdings` table already exists with the right shape; we only need to populate it.

## In scope

### B1 — `src/irc/data/fund_holdings_ingestor.py` (new module)

Pure-core module with thin I/O wrappers (`ingest_one` and `ingest_many` are the I/O-orchestration boundary; `is_stale`, `collect_holding_rows`, and `upsert_holdings` are the single-effect building blocks per the project's "Effects at edges" FP rule). Public surface:

```python
@dataclass(frozen=True)
class HoldingRow:
    instrument_id: str
    report_date: str          # ISO YYYY-MM-DD; from snapshot.source_report_date
    holding_ticker: str       # raw 6-digit / 4-5-digit / .HK code; from FundHolding.symbol
    holding_name: str
    weight_pct: float         # percent units 0.0–100.0 (matches FundHolding.weight_pct)
    source: str               # "active_fund_snapshot" | "akshare_cn_etf"

@dataclass(frozen=True)
class IngestOutcome:
    instrument_id: str
    status: Literal["wrote", "skipped_fresh", "skipped_no_data", "failed"]
    report_date: str          # "" when status != "wrote"
    rows_written: int
    detail: str               # human-readable reason on skip/fail; "" on success

def collect_holding_rows(
    instrument_id: str,
    asset_class: str,
    *,
    data_root: Path,
) -> tuple[tuple[HoldingRow, ...], str, str]:
    """Pure-with-cache-read: returns (rows, source, detail).

    For cn_equity_fund: read the most-recent ActiveFundSnapshot for fund_{iid}
    from `data_root/fundamentals/*/active_fund/fund_{iid}.json` via
    `snapshot_cache.load_active_fund_cache` (latest-quarter scan).
    For cn_etf: same scan first; if no cached active_fund_snapshot exists
    for this iid (cn_etf instruments don't typically populate item 003's
    active-fund cache), call `fetch_cn_etf_holdings(iid, top_n=10)` directly.
    Returns ((), source, detail) when no data is available.
    """

def upsert_holdings(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[HoldingRow],
    *,
    now_iso: str,
) -> int:
    """Atomic batch upsert using named-column INSERT OR REPLACE
    (positional INSERT is forbidden — see AC19 / Q5). Returns row count.
    Uses build_ref_id(source, "fund_holdings", instrument_id, report_date)
    for the _raw_ref column. Rows must be pre-sorted by the caller per
    the determinism rule below.
    """

def is_stale(
    con: duckdb.DuckDBPyConnection,
    instrument_id: str,
    *,
    today_iso: str,
    threshold_days: int = 30,
) -> bool:
    """Returns True iff the latest report_date in fund_holdings for this
    instrument_id is None OR older than today - threshold_days. Pure DuckDB
    read; no network I/O. `today_iso` is wall-clock from _china_today()
    (see AC20 / Q8 / F1)."""

def ingest_one(
    con: duckdb.DuckDBPyConnection,
    instrument_id: str,
    asset_class: str,
    *,
    data_root: Path,
    today_iso: str,
    now_iso: str,
    threshold_days: int = 30,
    force: bool = False,
) -> IngestOutcome:
    """I/O orchestration boundary: staleness check → collect → upsert.
    Idempotent on same-day reruns (skips with status='skipped_fresh' when
    not stale). Pre-condition: caller must invoke `ensure_schema(con)`
    first (F6) — `ingest_one` does NOT call it itself to keep the function
    surface narrow and predictable."""

def ingest_many(
    con: duckdb.DuckDBPyConnection,
    targets: Iterable[tuple[str, str]],  # (instrument_id, asset_class)
    *,
    data_root: Path,
    today_iso: str,
    now_iso: str,
    threshold_days: int = 30,
    force: bool = False,
) -> tuple[IngestOutcome, ...]:
    """Iterate ingest_one; never raise — failures captured in IngestOutcome.
    Returns one IngestOutcome per target in input order."""
```

**Behaviour rules:**

- **Source priority**: `cn_equity_fund` → ALWAYS read item 003's `ActiveFundSnapshot` cache (item 003 is the upstream owner of CN active-fund holdings; we never call AkShare here). `cn_etf` → try `ActiveFundSnapshot` cache first (some ETFs share the active-fund layout via `LookthroughTarget(kind="active_fund")`), fall back to `fetch_cn_etf_holdings(iid, top_n=10)` direct call. This single source of truth requirement is explicit in the source diagnosis (`docs/diagnosis-thesis-cards-evidence-gap.md` line 171: "Source for B1's stock list is the same `snapshot_cache` Slice A writes — single source of truth").
- **Asset-class filter**: only `cn_equity_fund` and `cn_etf` are eligible. Other asset classes (`gold`, `cn_bond_fund`, `us_etf`, `hk_etf`, `qdii_*`) return `IngestOutcome(status="skipped_no_data", detail="asset_class_not_eligible:{ac}")` from `ingest_one` without touching the cache or DuckDB. (Deferred per Q1; re-evaluate when `scoring/factors/` grows a bond/gold concentration factor.)
- **Staleness check**: `is_stale` reads `SELECT MAX(report_date) FROM fund_holdings WHERE instrument_id = ?`. None → stale (no data yet). Otherwise compute `(date.fromisoformat(today_iso) - max_report_date).days`; stale iff `> threshold_days`. When `force=True`, the check is bypassed. `today_iso` is wall-clock from `_china_today()` (UTC+8) — NEVER a pipeline `seed_date` (locked per F1 / AC20; `run_ingest` has no `seed_date` concept).
- **Upsert semantics**: named-column `INSERT OR REPLACE` (Q5; AC19): `INSERT OR REPLACE INTO fund_holdings (instrument_id, report_date, holding_ticker, holding_name, weight_pct, _ingested_at, _source, _raw_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`. Executed via `executemany` to match `_upsert_prices` / `_upsert_nav` / `_upsert_instruments` precedent. The existing primary key `(instrument_id, report_date, holding_ticker)` provides natural dedup. The `_source` column carries `"active_fund_snapshot"` or `"akshare_cn_etf"`; `_raw_ref` uses `build_ref_id(source, "fund_holdings", instrument_id, report_date)`.
- **Weight units**: written to DuckDB as `weight_pct` in percent units (0.0–100.0), matching the existing test in `tests/scoring/test_metrics_loader.py` (which inserts `20.0`, `15.0`, `10.0` and asserts concentration `0.45` — `metrics_loader` divides by 100). This matches `FundHolding.weight_pct` semantics from item 003.
- **Empty snapshot handling (Q2)**: when `ActiveFundSnapshot` exists but `constituent_analyses == ()` (cold/empty snapshot — item 006's gap-state covers this on the opportunity side), `collect_holding_rows` returns `((), "active_fund_snapshot", "snapshot_empty")` and `ingest_one` returns `IngestOutcome(status="skipped_no_data", detail="snapshot_empty")`. The previously-written DuckDB rows for that instrument are NEVER deleted (locked per Q2 — `MAX(report_date)` in `_latest_holdings_concentration` naturally promotes fresh over stale; explicit deletion would create a non-pure side effect and complicate the idempotency contract).
- **Partial AkShare failure isolation (Q6)**: when `fetch_cn_etf_holdings(iid)` returns `HoldingsResult((), "", "")` (the documented no-raise empty path), `IngestOutcome(status="skipped_no_data", detail="akshare_empty:{iid}")`. When the call raises (it shouldn't per the adapter contract, but defensive — see F5), wrap in `try/except Exception` and emit `IngestOutcome(status="failed", detail="akshare_raised:{type(exc).__name__}")`. **Never propagate exceptions out of `ingest_many`.** AC13 locks: one fund failing does NOT fail the batch (Q6).
- **report_date derivation (Q4)**: from `ActiveFundSnapshot.source_report_date` (ISO `"2024-03-31"`) for the active-fund path, or `HoldingsResult.source_report_date` for the AkShare fallback. **NEVER the AkShare-published date** (publication lag varies 30–60 days; using it would corrupt the quarterly disclosure cadence the scoring layer depends on). If the upstream `source_report_date` is empty (item 003's `holdings_quarter_parse_failed` path), `collect_holding_rows` returns `IngestOutcome(status="skipped_no_data", detail="missing_report_date")` — we do not invent a fallback date because the primary key requires it.
- **Multi-quarter retention (Q3)**: no pruning in V1. Historical rows accumulate under their `report_date`; `_latest_holdings_concentration` reads only `MAX(report_date)` so scoring is unaffected. Disk footprint is < 1 MB/year at production scale; reversible if pressure materialises.
- **Determinism**: rows written to DuckDB in `(weight_pct DESC, holding_ticker ASC)` order. The caller (i.e. `upsert_holdings`) sorts before issuing `executemany` so DuckDB's row insertion order is reproducible. Two-run rerun on the same cache produces byte-equal rowid ordering (AC15).

### B2 — `src/irc/commands/ingest_cmd.py` (wire-in)

Add a new stage to `run_ingest` after the existing NAV ingestion block (line ~595, before `finally:`). The stage is intentionally additive — it does NOT participate in the preflight canary, does NOT propagate failures to `HaltReason`, and does NOT block downstream ingestion stages on partial failure. Holdings data is best-effort enrichment for scoring, not a hard pipeline dependency.

```python
# Top of file:
from irc.data.fund_holdings_ingestor import ingest_many as ingest_fund_holdings

# New block, after the NAV loop and before the finally:
eligible_targets = tuple(
    (i.instrument_id, i.asset_class)
    for i in all_instruments
    if i.asset_class in ("cn_equity_fund", "cn_etf")
)
holdings_outcomes = ingest_fund_holdings(
    con,
    eligible_targets,
    data_root=root / "data",
    today_iso=today_iso,        # ← wall-clock from _china_today(); see AC20 / F1
    now_iso=_now_iso(),
    threshold_days=30,
)
# Aggregate counts for the manifest + log
holdings_counts: dict[str, int] = {
    "wrote": 0, "skipped_fresh": 0, "skipped_no_data": 0, "failed": 0,
}
for outcome in holdings_outcomes:
    holdings_counts[outcome.status] += 1
ak_counts["fund_holdings"] = sum(
    o.rows_written for o in holdings_outcomes
)
# Emit per-iid debug log when verbose (Q10)
if _verbose:
    for o in holdings_outcomes:
        _log.info(
            "fund_holdings %s: status=%s rows=%d %s",
            o.instrument_id, o.status, o.rows_written, o.detail,
        )
# Unconditional summary line (Q10) — printed after the manifest writes:
print(
    f"  fund_holdings: wrote={holdings_counts['wrote']} "
    f"fresh={holdings_counts['skipped_fresh']} "
    f"no_data={holdings_counts['skipped_no_data']} "
    f"failed={holdings_counts['failed']}"
)
```

**Behaviour rules:**

- **No HaltReason emission**: `holdings_counts["failed"] > 0` does NOT trigger a halt or non-zero exit. Holdings enrichment is best-effort — losing it degrades scoring quality (concentration falls back to 0.30 in `scoring/pipeline.py`) but does not invalidate the pipeline.
- **Manifest counts**: `ak_counts["fund_holdings"]` records total rows written (sum across all instruments). The existing `write_manifest(ManifestEntry(source="akshare", ...))` already emits `record_counts=ak_counts`, so adding the key picks it up automatically.
- **Observability (Q10)**: print summary line after manifest writes (always emitted, even at non-verbose). Per-iid `_log.info` line emitted only when `_verbose` is True (matches existing NAV per-instrument log pattern at `ingest_cmd.py:592–598`).
- **Ordering**: targets are iterated in the order they appear in `all_instruments` (which is universe-file order). `ingest_many` preserves input order in its return tuple, so the log lines and the eventual byte-equality test on the manifest stay deterministic.

## Out of scope

- Active-fund cache writes (`write_active_fund_cache`) — owned by item 003.
- `LookthroughTarget`, `ActiveFundSnapshot`, `FundHolding`, `HoldingsResult` schema — owned by item 003.
- Opportunity-side gap stamping based on holdings staleness — owned by item 006.
- Memo / discipline rendering of holdings — owned by item 007.
- Citation gate over holdings rows — owned by item 009.
- CLI commands surfacing `fund_holdings` ingestion (no new `irc holdings refresh` command — wired into `irc run --only ingest` only).
- Migration of historical empty `fund_holdings` table contents (the table is currently empty per the source diagnosis; this slice begins populating it).
- Deletion of stale rows when no replacement data is found (per Q2: NEVER delete).
- Multi-quarter retention policy / pruning of old `report_date` rows (per Q3: no pruning in V1).
- Asset-class expansion to `cn_bond_fund`, `gold`, QDII (per Q1: deferred until scoring grows a corresponding concentration factor).
- A standalone `irc fundamentals holdings ...` CLI subcommand (deferred until user-facing ops need it).
- Cross-instrument deduplication when the same `holding_ticker` appears under multiple `instrument_id`s (the PK includes `instrument_id`, so collisions are not possible).

## Detailed schema specifications

### `HoldingRow` (new — `src/irc/data/fund_holdings_ingestor.py`)

```python
@dataclass(frozen=True)
class HoldingRow:
    instrument_id: str
    report_date: str          # ISO YYYY-MM-DD
    holding_ticker: str       # bare ticker, no exchange suffix (matches FundHolding.symbol)
    holding_name: str
    weight_pct: float         # percent units 0.0–100.0
    source: str               # "active_fund_snapshot" | "akshare_cn_etf"
```

Field invariants (enforced via `__post_init__`):
- `instrument_id` non-empty.
- `report_date` matches `^\d{4}-\d{2}-\d{2}$`.
- `holding_ticker` non-empty.
- `0.0 <= weight_pct <= 100.0` (raise `ValueError` otherwise).
- `source in {"active_fund_snapshot", "akshare_cn_etf"}` (raise `ValueError` otherwise — defensive against typo regressions).

### `IngestOutcome` (new — same module)

```python
@dataclass(frozen=True)
class IngestOutcome:
    instrument_id: str
    status: Literal["wrote", "skipped_fresh", "skipped_no_data", "failed"]
    report_date: str          # "" when status != "wrote"
    rows_written: int          # 0 when status != "wrote"
    detail: str
```

### DuckDB schema (no change)

The existing `fund_holdings` DDL in `src/irc/data/duckdb_helper.py:67–75` is unchanged:

```sql
CREATE TABLE IF NOT EXISTS fund_holdings (
    instrument_id  VARCHAR NOT NULL,
    report_date    DATE    NOT NULL,
    holding_ticker VARCHAR NOT NULL,
    holding_name   VARCHAR,
    weight_pct     DOUBLE  NOT NULL,
    _ingested_at   TIMESTAMP NOT NULL,
    _source        VARCHAR   NOT NULL,
    _raw_ref       VARCHAR   NOT NULL,
    PRIMARY KEY (instrument_id, report_date, holding_ticker)
)
```

The PK already covers per-quarter, per-instrument deduplication. No `ALTER TABLE`, no new column, no new index. `ensure_schema` is already additive-only (`CREATE TABLE IF NOT EXISTS` — F6). Confirmed against `_DDL_STATEMENTS` line 67–75. AC1 locks the DDL string byte-equality.

## Source-of-truth read path

`collect_holding_rows` reads from item 003's cache as follows:

1. **Active-fund snapshot lookup** (both `cn_equity_fund` and `cn_etf`):
   ```python
   from irc.fundamentals.snapshot_cache import active_fund_cache_path, load_active_fund_cache

   base = data_root / "fundamentals"
   # Scan for the most-recent quarter directory containing this fund.
   # Glob pattern matches `active_fund_cache_path` (Q6: same hard-coded
   # "active_fund/" segment; lock via test_collect_holding_rows_glob_pattern_matches_cache_path).
   candidates = sorted(base.glob(f"*/active_fund/fund_{iid}.json"))
   for path in reversed(candidates):
       quarter = path.parent.parent.name  # e.g. "2024Q1"
       snap = load_active_fund_cache(iid, quarter, data_root)
       if snap is not None and snap.constituent_analyses:
           # Found a non-empty snapshot — use it.
           rows = tuple(
               HoldingRow(
                   instrument_id=iid,
                   report_date=snap.source_report_date,
                   holding_ticker=c.symbol,
                   holding_name=c.name_cn,
                   weight_pct=c.weight_pct,
                   source="active_fund_snapshot",
               )
               for c in snap.constituent_analyses
               if c.symbol  # defence-in-depth; item 003 validates this
           )
           return rows, "active_fund_snapshot", f"loaded:{quarter}"
       if snap is not None:
           # Snapshot exists but is empty — keep looking for an older non-empty one.
           continue
   ```

2. **Direct AkShare fallback** (only for `cn_etf` when no active-fund snapshot is available — Q7):
   ```python
   if asset_class == "cn_etf":
       try:
           result = fetch_cn_etf_holdings(iid, top_n=10)
       except Exception as exc:
           # Defensive — F5; adapter contract says it never raises.
           return (), "akshare_cn_etf", f"akshare_raised:{type(exc).__name__}"
       if not result.constituents or not result.source_report_date:
           return (), "akshare_cn_etf", "akshare_empty"
       rows = tuple(
           HoldingRow(
               instrument_id=iid,
               report_date=result.source_report_date,
               holding_ticker=h.symbol,
               holding_name=h.name_cn,
               weight_pct=h.weight_pct,
               source="akshare_cn_etf",
           )
           for h in result.constituents
           if h.symbol
       )
       return rows, "akshare_cn_etf", f"fetched:{result.source_report_quarter}"
   ```

3. **No data path** (active fund with no cache): return `((), "active_fund_snapshot", "snapshot_missing")`. This is the expected pre-item-003 state. After item 003 runs, the next `irc run` will find the cache and populate `fund_holdings`.

## Staleness contract

`is_stale(con, iid, today_iso="2026-05-24", threshold_days=30)` algorithm:

```python
result = con.execute(
    "SELECT MAX(report_date) FROM fund_holdings WHERE instrument_id = ?",
    [iid],
).fetchone()
if result is None or result[0] is None:
    return True
latest = result[0]  # date object from DuckDB
age = (date.fromisoformat(today_iso) - latest).days
return age > threshold_days
```

**`today_iso` derivation:** wall-clock CST via `_china_today()` (UTC+8). NEVER a pipeline `seed_date` — `run_ingest` has no `seed_date` concept (F1; AC20). Test callers pass `today_iso` explicitly so the fixture controls the clock.

Note: `threshold_days=30` matches the source diagnosis ("holdings older than 30 days" — line 172). Disclosure cadence for CN funds is quarterly, but the public report-availability lag means new holdings appear ~45 days after quarter-end. The 30-day threshold means we re-check at least once per quarter; we do NOT chase intra-quarter freshness because there is no upstream data.

## Acceptance criteria

1. **DuckDB schema unchanged**: `EXPECTED_TABLES` in `duckdb_helper.py` still contains `"fund_holdings"`; the DDL string is byte-equal to the pre-item-010 version. (Locked via a regression test that diffs the constant against a captured copy.)
2. **Module shape**: `src/irc/data/fund_holdings_ingestor.py` exports `HoldingRow`, `IngestOutcome`, `collect_holding_rows`, `upsert_holdings`, `is_stale`, `ingest_one`, `ingest_many`. All are importable from the module. The module imports nothing from `commands/`, `opportunity/`, `memo/`, or `scoring/` (one-way dependency on `data/` + `fundamentals/`).
3. **Empty-table upsert writes rows**: `ingest_one(con, "005827", "cn_equity_fund", data_root=..., today_iso=...)` against a clean DuckDB with a pre-populated `ActiveFundSnapshot` cache at `data/fundamentals/2024Q1/active_fund/fund_005827.json` returns `IngestOutcome(status="wrote", rows_written=10)`. A `SELECT COUNT(*) FROM fund_holdings WHERE instrument_id='005827'` returns 10.
4. **Idempotent same-day rerun**: calling `ingest_one` twice in succession without changing the DuckDB clock returns `wrote` then `skipped_fresh`. No duplicate rows are inserted; the second call performs zero `INSERT` statements (verified via a DuckDB query-counter spy that wraps `con.execute`).
5. **`force=True` bypasses staleness**: `ingest_one(..., force=True)` after a fresh write produces `wrote` again with `rows_written=10`, overwriting via `INSERT OR REPLACE`. Row count remains 10 (PK dedup), but `_ingested_at` advances.
6. **30-day staleness gate**: with the latest `report_date = today - 29` days → `skipped_fresh`. With `today - 31` days → re-ingests. With no rows at all → re-ingests.
7. **Asset-class filter**: `ingest_one(con, "gold_etf", "gold", ...)` returns `IngestOutcome(status="skipped_no_data", detail="asset_class_not_eligible:gold")` without reading the snapshot cache or executing any DuckDB query against `fund_holdings`. Same for `cn_bond_fund`, `us_etf`, `hk_etf`, `qdii_us`, `qdii_hk`, `qdii_global`.
8. **Active-fund cache is single source of truth**: when both an `ActiveFundSnapshot` and a fresh `fetch_cn_etf_holdings` response would yield data for `cn_equity_fund` iid, the snapshot wins. Verified by patching `fetch_cn_etf_holdings` to raise `AssertionError("must not be called")` and asserting the cn_equity_fund ingest succeeds.
9. **`cn_etf` fallback to AkShare**: when no `ActiveFundSnapshot` exists for a `cn_etf` iid, `fetch_cn_etf_holdings(iid, top_n=10)` is called exactly once; result is upserted. The `_source` column for those rows is `"akshare_cn_etf"`.
10. **No data → no rows; existing rows preserved**: when `ActiveFundSnapshot.constituent_analyses == ()` (empty cache), `ingest_one` returns `IngestOutcome(status="skipped_no_data", detail="snapshot_empty")`. Existing rows for the instrument are NOT deleted (Q2: locked via `SELECT COUNT(*)` before and after — equal).
11. **Missing `source_report_date`**: when `ActiveFundSnapshot.source_report_date == ""` (item 003's `holdings_quarter_parse_failed` path), `ingest_one` returns `IngestOutcome(status="skipped_no_data", detail="missing_report_date")`. Zero rows written.
12. **Weight semantics + scoring integration**: after `ingest_one` writes 10 holdings (weights summing to e.g. 45.0%), a follow-up call to `load_scoring_metrics(con, [iid])` returns `holdings_concentration_top10 == 0.45` (sum / 100). Locks the unit contract with `scoring/metrics_loader._latest_holdings_concentration`.
13. **Partial AkShare failure does not raise (Q6)**: patching `fetch_cn_etf_holdings` to raise `ConnectionError("boom")` for one of 5 targets → `ingest_many` returns 5 `IngestOutcome` entries in order; the failing one has `status="failed"`, `detail="akshare_raised:ConnectionError"`; the other 4 succeed. The whole call does not raise. **No batch-level failure.**
14. **Observability — per-instrument outcome + cadence (Q10)**: `ingest_many` returns one `IngestOutcome` per target in input order, even when targets are filtered or fail. Counts of `wrote`/`skipped_fresh`/`skipped_no_data`/`failed` are observable by summing the returned tuple. The summary `print(...)` line is unconditional; per-iid `_log.info` line emits only when `_verbose=True`.
15. **Determinism**: row insertion order is `(weight_pct DESC, holding_ticker ASC)`. Two-run rerun in the same calendar day on the same cache produces byte-equal DuckDB row order via `SELECT * FROM fund_holdings WHERE instrument_id = ? ORDER BY rowid`.
16. **Wire-in does not break ingest**: `run_ingest` exit code stays 0 when `holdings_counts["failed"] == len(eligible_targets)` (all failed). The existing `fatal_failures` gating (prices/nav) is unaffected. No `HaltReason` emitted for holdings failures.
17. **Manifest carries holdings count**: after `run_ingest` succeeds, `read_manifest(data_root, "akshare")` has `record_counts["fund_holdings"] >= 0`. When rows were written, the count is non-zero.
18. **`_raw_ref` shape per instrument-quarter**: rows for the same `(instrument_id, report_date)` share the same `_raw_ref` value (the ref id is keyed on those two, not on `holding_ticker`). Existing contract from `build_ref_id(source, "fund_holdings", instrument_id, report_date)` — verified in a regression test that the ref id pattern matches `^(active_fund_snapshot|akshare_cn_etf):fund_holdings:\d+:\d{4}-\d{2}-\d{2}$`.
19. **Named-column INSERT shape is locked (Q5)**: `upsert_holdings` uses `con.executemany("INSERT OR REPLACE INTO fund_holdings (instrument_id, report_date, holding_ticker, holding_name, weight_pct, _ingested_at, _source, _raw_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", params)`. Verified via a spy on `con.execute` / `con.executemany` that captures the SQL string and asserts it contains the named-column block (substring match). Positional `INSERT INTO fund_holdings VALUES (...)` is forbidden in production code — future schema column additions would silently corrupt data.
20. **`today_iso` is wall-clock `_china_today()`, never a pipeline `seed_date` (F1)**: the holdings-ingest block in `ingest_cmd.py` passes `today_iso=today_iso` (the local already derived from `_china_today()` at the top of `run_ingest`). A regression test patches `_china_today` to return a fixed date and asserts `ingest_many` is invoked with that same date as `today_iso` kwarg.
21. **Item 010 is structurally independent of item 008's AC22/AC23 byte-equality tests (F2)**: implementation note (not a runnable test). `run_opportunity` + `run_memo` (the only stages AC22/AC23 invoke) do NOT read the `fund_holdings` table — verified by `grep -rn "fund_holdings" src/irc/opportunity/ src/irc/memo/` returning zero matches. The holdings-ingest wire-in is exclusively in `run_ingest`, which AC22/AC23 do not invoke. Item 010 cannot non-determinise AC22/AC23 by construction. This claim must be re-verified by future refactors that introduce new readers of `fund_holdings`.

## Edge cases

- **Two snapshots for the same fund, different quarters**: the latest-quarter directory wins (lexicographic sort, e.g. `2024Q4` beats `2024Q1`). Lock with a test that pre-populates both directories and asserts the written `report_date` matches the Q4 snapshot.
- **Holding that vanishes between snapshots**: when 2024Q1 had holdings `{A, B, C}` and 2024Q2 has `{A, B, D}`, the new write inserts the 2024Q2 rows under `report_date='2024-06-30'`. The 2024Q1 rows under `report_date='2024-03-31'` remain in the table (different PK; Q3 no-pruning policy). `_latest_holdings_concentration` reads `MAX(report_date)` so scoring sees only Q2. The vanished holding `C` is no longer in the latest set — correct behaviour.
- **Active fund whose cache was written today but is empty** (item 003 produced an empty snapshot for fail-closed reasons): `skipped_no_data` with `detail="snapshot_empty"`. Existing rows preserved (Q2). Same-day rerun continues to skip.
- **`cn_etf` instrument that ALSO has an `ActiveFundSnapshot` cache** (e.g. someone ran `irc opportunity` on it as an active fund): the snapshot wins. The fallback AkShare call is not triggered. `_source` is `"active_fund_snapshot"`.
- **`HoldingRow.weight_pct == 0.0`** (a constituent with zero weight from item 003): inserted as a normal row with `weight_pct=0.0`. `_latest_holdings_concentration` sums weights and divides by 100, so a zero-weight holding contributes nothing — equivalent to absence but preserved in the DB for audit.
- **DuckDB connection in use by another writer**: the ingestor uses the same `con` passed in by `ingest_cmd`. No new connection is opened. Concurrency is the caller's responsibility (same as existing `_upsert_*` helpers). DuckDB's single-writer constraint is upstream.
- **Empty `eligible_targets` list** (no `cn_equity_fund` / `cn_etf` instruments in the universe): `ingest_many` returns `()`, all `holdings_counts` keys stay `0`, manifest entry shows `"fund_holdings": 0`.
- **`ingest_one` called when DuckDB schema doesn't yet exist**: pre-condition — `ingest_cmd` calls `ensure_schema(con)` before invoking the ingestor (already does — `ingest_cmd.py:454`). Stand-alone callers (tests, future CLI) must call `ensure_schema(con)` first or get a DuckDB error. We do NOT call `ensure_schema` inside `ingest_one` to keep it pure / fast (F6).

## Test plan

Tests live in `tests/data/test_fund_holdings_ingestor.py` (new — real on-disk DuckDB via `tmp_path` + real `ActiveFundSnapshot` JSON cache files written via `write_active_fund_cache`; matches the universal project convention per Q9). A small wire-in test set lives in `tests/commands/test_ingest_cmd.py` (existing file, append).

| Test | Scope | Asserts |
|---|---|---|
| `test_holding_row_validates_fields` | unit | rejects empty `instrument_id`, malformed `report_date`, out-of-range `weight_pct`, unknown `source`. |
| `test_is_stale_no_rows` | unit (DuckDB) | empty table → `True`. |
| `test_is_stale_within_threshold` | unit (DuckDB) | latest report 29 days ago → `False`; 31 days ago → `True`. |
| `test_is_stale_threshold_override` | unit (DuckDB) | `threshold_days=7` swaps boundary at 8 days. |
| `test_collect_holding_rows_from_active_fund_snapshot` | unit (fs + cache) | pre-populated `data/fundamentals/2024Q1/active_fund/fund_005827.json` (written via `write_active_fund_cache`) → 10 `HoldingRow` with `source="active_fund_snapshot"`. |
| `test_collect_holding_rows_latest_quarter_wins` | unit (fs) | both 2024Q1 + 2024Q4 snapshots exist → output uses Q4 dates / data. |
| `test_collect_holding_rows_skips_empty_snapshot_and_falls_through` | unit (fs) | latest-quarter snapshot has `constituent_analyses=()` but an older one has 10 entries → output uses the older non-empty one. |
| `test_collect_holding_rows_no_snapshot_no_fallback_for_cn_equity_fund` | unit | no cache + asset_class=`cn_equity_fund` → returns `()` with detail `"snapshot_missing"`. `fetch_cn_etf_holdings` NOT called (patched to raise). |
| `test_collect_holding_rows_cn_etf_fallback_to_akshare` | unit | no cache + asset_class=`cn_etf` → calls `fetch_cn_etf_holdings(iid, top_n=10)` once, builds `HoldingRow`s with `source="akshare_cn_etf"`. |
| `test_collect_holding_rows_cn_etf_akshare_empty` | unit | fallback returns `HoldingsResult((), "", "")` → returns `()` with detail `"akshare_empty"`. |
| `test_collect_holding_rows_missing_report_date` | unit | snapshot has `source_report_date=""` → returns `()` with detail `"missing_report_date"`. |
| `test_collect_holding_rows_glob_pattern_matches_cache_path` | unit (Q6 regression) | a path built via `active_fund_cache_path("005827", "2024Q1", root)` IS matched by the ingestor's glob `*/active_fund/fund_005827.json`. |
| `test_upsert_holdings_uses_named_columns` | unit (AC19 / Q5) | spy on `con.executemany`; first call's SQL string contains `"INSERT OR REPLACE INTO fund_holdings (instrument_id, report_date, holding_ticker, holding_name, weight_pct, _ingested_at, _source, _raw_ref) VALUES"`. |
| `test_upsert_holdings_idempotent` | unit (DuckDB) | upserting the same 10 rows twice → row count stays 10; `_ingested_at` advances on the second write. |
| `test_upsert_holdings_writes_raw_ref_pattern` | unit | inserted `_raw_ref` matches `^(active_fund_snapshot\|akshare_cn_etf):fund_holdings:\d+:\d{4}-\d{2}-\d{2}$`. |
| `test_upsert_holdings_deterministic_order` | unit (AC15) | rows written in `(weight_pct DESC, holding_ticker ASC)` order; two reruns produce byte-equal `SELECT * ORDER BY rowid` output. |
| `test_ingest_one_skips_fresh` | integration (DuckDB+cache) | pre-fresh table → `skipped_fresh`, zero `INSERT` calls. |
| `test_ingest_one_writes_when_stale` | integration | stale table + populated cache → `wrote`, rows_written=10. |
| `test_ingest_one_asset_class_filter` | integration | `gold` / `cn_bond_fund` / `us_etf` / `qdii_global` → `skipped_no_data` with `detail="asset_class_not_eligible:..."`. |
| `test_ingest_one_force_bypasses_staleness` | integration | fresh table + `force=True` → `wrote`. |
| `test_ingest_one_snapshot_empty_preserves_existing_rows` | integration (Q2) | pre-existing rows for iid + empty snapshot → no rows deleted (`SELECT COUNT(*)` equal before/after); outcome `skipped_no_data`. |
| `test_ingest_many_preserves_order_and_isolates_failures` | integration (Q6 / AC13) | 5 targets, middle one raises in `fetch_cn_etf_holdings` → 5 outcomes in input order; only middle has `status="failed"`; others succeed. |
| `test_ingest_many_filter_then_collect` | integration | mixed asset classes (`cn_equity_fund`, `gold`, `cn_etf`, `cn_bond_fund`) → outcomes preserve input order; only eligible classes are processed. |
| `test_scoring_metrics_reads_ingested_holdings` | integration (scoring+ingest) | after `ingest_one` writes rows with weights `[10.0, 15.0, 20.0]`, `load_scoring_metrics(con, [iid])` returns `holdings_concentration_top10 == 0.45`. |
| `test_run_ingest_wires_holdings_step` | integration (commands) | patch `ingest_fund_holdings` to a spy; `run_ingest` invokes it once with `eligible_targets` derived from the test universe. Spy records `(iid, asset_class)` tuples in expected order; also asserts `today_iso` kwarg equals `_china_today()` (AC20). |
| `test_run_ingest_holdings_failure_not_fatal` | integration (commands) | spy returns `IngestOutcome(status="failed", ...)` for all targets → `run_ingest` still exits 0; no `HaltReason` sidecar written. |
| `test_run_ingest_holdings_count_in_manifest` | integration (commands) | after `run_ingest`, `read_manifest(data_root, "akshare").record_counts["fund_holdings"]` equals the sum of `rows_written`. |

## Files touched

| File | Action |
|---|---|
| `src/irc/data/fund_holdings_ingestor.py` | NEW — module with `HoldingRow`, `IngestOutcome`, `collect_holding_rows`, `upsert_holdings`, `is_stale`, `ingest_one`, `ingest_many`. |
| `src/irc/commands/ingest_cmd.py` | Append the holdings-ingest block after the NAV loop. Add import for `ingest_fund_holdings`. Aggregate `holdings_counts` into `ak_counts`. Add summary `print(...)` line + conditional per-iid `_log.info`. |
| `tests/data/test_fund_holdings_ingestor.py` | NEW — unit + integration tests per the test plan (~500 LOC). |
| `tests/commands/test_ingest_cmd.py` | APPEND — three wire-in tests (`test_run_ingest_wires_holdings_step`, `test_run_ingest_holdings_failure_not_fatal`, `test_run_ingest_holdings_count_in_manifest`). |
| `tests/fixtures/active_fund_snapshots/` | NEW directory — JSON fixture files mimicking `data/fundamentals/<quarter>/active_fund/fund_<iid>.json` for the cache-read tests. Each file is the round-trip of a real `ActiveFundSnapshot` through item 003's `write_active_fund_cache` (Q9). At minimum: `fund_005827.json` (10-constituent CN active fund), `fund_005827_empty.json` (zero constituents), `fund_005827_q4.json` (later quarter with different holdings). |

## Cross-item impact audit (per grill F2 / F3)

- **Item 008 (publishable-set lockdown baseline / AC22 / AC23 two-run byte equality):** **NO RISK.** AC22/AC23 invoke `run_opportunity` + `run_memo`, neither of which reads `fund_holdings`. Item 010's wire-in is exclusively in `run_ingest`. The publishable-set helper (`_publishable_set_helper.py`) does not touch `fund_holdings`. Locked as AC21.
- **Item 009 (citation gate):** **NO RISK.** `src/irc/opportunity/citation_map.py`, `src/irc/opportunity/rejection_log.py`, `src/irc/memo/numeric_audit.py` all operate on in-memory `OpportunityRow.thesis_evidence` / `ConstituentAnalysis` — none query the `fund_holdings` DuckDB table. The scoring layer's read of `fund_holdings` produces a scalar (`holdings_concentration_top10`) that does not interact with the citation gate.
- **Items 003, 006, 007:** **CONSUMER, NOT MUTATOR.** Item 010 reads item 003's cache; it does not modify it. The cache contract (path layout + JSON shape) is item 003's commitment; item 010 has one regression test that locks the glob pattern against item 003's `active_fund_cache_path` (Q6) to catch layout drift early.

## Dependencies on other items

**Hard requires (must merge before item 010):**

- **Item 002** — `ThesisEvidence` provenance fields and `ConstituentAnalysis` placeholder type on `DisciplineRow`. The ingestor does NOT touch `ThesisEvidence` directly, but loading `ActiveFundSnapshot` via `snapshot_cache.load_active_fund_cache` requires the schema item 002 / 003 settled.
- **Item 003** — `ActiveFundSnapshot`, `FundHolding`, `HoldingsResult`, `fetch_cn_etf_holdings` new contract, `snapshot_cache.active_fund_cache_path`, `snapshot_cache.load_active_fund_cache`, `snapshot_cache.write_active_fund_cache`. The whole "single source of truth" promise depends on item 003 writing the cache.

**Required-by (items that read item 010's outputs):**

- The scoring layer (`scoring/metrics_loader._latest_holdings_concentration`) and the quality factor (`scoring/factors/quality._concentration_score`) read the populated table directly. No code change is needed in scoring — once `fund_holdings` is non-empty, the existing query returns real values instead of NaN.
- `decision/completeness.py` will see `holdings_concentration_top10` populated for `cn_equity_fund` rows that previously had NaN. The completeness gate's per-asset-class field whitelist already includes the field for `cn_equity_fund` (it drops only for index ETFs at line 38/41); no change needed.
- No memo / discipline / opportunity-side reader depends on the DuckDB table (those layers read `OpportunityRow.holdings_concentration_top10` populated from the scoring DataFrame, which now contains real numbers).

## Resolved questions

All 10 spec-time open questions are now locked (see [`010-grill.md`](./010-grill.md) for the full rationale):

| # | Question | Locked answer |
|---|---|---|
| Q1 | Asset-class expansion (`cn_bond_fund` / `gold`)? | Deferred to v2 — re-evaluate if scoring gains a bond/gold concentration factor. |
| Q2 | Vanishing-holdings retention (delete on empty snapshot)? | NO — never delete. `MAX(report_date)` naturally promotes fresh over stale. |
| Q3 | Multi-quarter retention / pruning? | No pruning in V1; disk footprint < 1 MB/year. |
| Q4 | `report_date` granularity? | ISO `YYYY-MM-DD` from `source_report_date` (quarter-end). Never AkShare-published date. |
| Q5 | Schema migration (positional vs named INSERT)? | Named-column `INSERT OR REPLACE` with `executemany`. Locked in AC19. |
| Q6 | Coupling to item 003's cache layout? | Glob `*/active_fund/fund_{iid}.json` + regression test against `active_fund_cache_path`. |
| Q7 | `cn_etf` ActiveFundSnapshot coverage? | Spec is correct — most cn_etf hit AkShare fallback. |
| Q8 | Idempotency contract? | Same-day fresh = no-op (zero INSERTs); same-day stale = re-upsert via PK dedup. |
| Q9 | Test fixture strategy (mock vs real)? | Real on-disk DuckDB via `tmp_path`; real `ActiveFundSnapshot` JSON via `write_active_fund_cache`. |
| Q10 | Logging cadence (per-iid vs batch summary)? | Both: per-iid `_log.info` when `_verbose=True`; unconditional summary `print(...)` after manifest. |

Plus the grill-phase audit findings:
- **F1**: `today_iso` is wall-clock `_china_today()`, never a pipeline `seed_date`. Locked in AC20.
- **F2**: No risk to item 008's AC22/AC23 byte-equality. Locked in AC21.
- **F3**: No risk to item 009's citation gate.
- **F4**: `ingest_one` is the I/O orchestration boundary (per FP discipline).
- **F5**: Defensive `try/except` around `fetch_cn_etf_holdings` is intentional dead code on the happy path.
- **F6**: `ensure_schema` is already idempotent; no item 010 change required.

## Non-goals

- No new env vars.
- No new ADRs (the planner will append a one-sentence cross-reference to `docs/adr/0002-active-fund-fetch-engine.md` §5 naming item 010 as a downstream consumer; this is documentation-only).
- No changes to `_GAP_TO_REASON`, `RejectionReasonCode`, or any opportunity / memo / scoring production module.
- No live-network tests added (all tests run via `tmp_path` + patched `fetch_cn_etf_holdings`).
