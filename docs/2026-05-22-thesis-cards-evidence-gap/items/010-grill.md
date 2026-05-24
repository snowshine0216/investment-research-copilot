# Item 010 — Grill summary

Auto-accepted under autonomy override 2026-05-24 (autodev backlog-mode grill subagent for the `2026-05-22-thesis-cards-evidence-gap` feature). No human in the loop; every recommended answer locked verbatim against existing project precedent (ADRs 0001–0004, CONTEXT.md, items 003 + 006 + 007 + 008 + 009 grill+ship cadence, `src/irc/data/duckdb_helper.py`, `src/irc/commands/ingest_cmd.py` `_upsert_nav`/`_upsert_prices`/`_upsert_instruments` shape).

## Verdict

**PASS-WITH-NOTES.** Spec is plan-ready. All 10 open questions auto-resolved against existing code, project conventions, or recent items' verdict files. 4 ACs sharpened, 3 ACs added (now 21 total: AC19 named-column INSERT shape lock, AC20 wall-clock `today_iso` staleness contract, AC21 fund_holdings independence from item 008's AC22/AC23 byte-equality tests). No new ADRs needed; CONTEXT.md gains 1 term (`fund_holdings ingest policy`). The "notes" tag flags two items the planner should expect to revisit: (a) Q1 asset-class expansion is explicitly deferred to v2 — re-evaluate if `cn_bond_fund` ever gains a holdings-concentration scoring factor; (b) the staleness-check `today_iso` derivation must use `_china_today()` (wall-clock), not a pipeline `seed_date`, because `run_ingest` has no `seed_date` concept and threading one in would couple item 010 to a non-existent contract.

## Ten open questions resolved

| # | Question | Locked answer | Source of authority |
|---|---|---|---|
| Q1 | Asset-class expansion to `cn_bond_fund`/`gold` | **Defer to v2.** Source diagnosis (`docs/diagnosis-thesis-cards-evidence-gap.md:172`) explicitly scopes B1 to `cn_equity_fund` + `cn_etf`. Scoring's `_concentration_score` is only registered in `scoring/factors/quality.py` for those two asset classes (verified: bonds and gold have no concentration-of-holdings metric in any factor module). Adding bonds/gold today would write rows that no factor reads — pure dead weight in the DB. Re-evaluate only if `scoring/factors/` grows a bond-duration-concentration or gold-vault-concentration factor. | `src/irc/scoring/factors/quality.py` direct read; source diagnosis line 172. |
| Q2 | Vanishing-holdings retention (delete on empty snapshot) | **NO — never delete.** Three reasons: (1) `_latest_holdings_concentration` queries `MAX(report_date)` (`metrics_loader.py:135`), so stale rows naturally lose to fresh ones without explicit deletion; (2) historical rows under older `report_date` are useful for future drift detection (Q3); (3) deletion-on-empty creates a non-pure side effect that complicates idempotency contract (Q8) — a same-day rerun with a now-empty cache would delete rows the previous run wrote. AC10 + AC11 lock the no-delete contract for `snapshot_empty` and `missing_report_date` paths. | `metrics_loader.py:127–144`; FP guidance ("Effects at edges; isolate state changes") from global CLAUDE.md. |
| Q3 | Multi-quarter retention / pruning | **No pruning in V1.** Disk footprint is trivial: 10 rows × ~350 funds × 4 quarters × ~80 bytes ≈ 1 MB per year. Pruning is reversible (the data is re-derivable from item 003's JSON cache); retention is the conservative default. Add `ALTER TABLE fund_holdings DELETE WHERE report_date < ?` as a future maintenance job if disk pressure ever materialises. | Order-of-magnitude estimate; CLAUDE.md "no premature optimisation". |
| Q4 | `report_date` granularity | **ISO `YYYY-MM-DD`, copied verbatim from `ActiveFundSnapshot.source_report_date` (active-fund path) or `HoldingsResult.source_report_date` (ETF fallback path).** Both are last-day-of-fiscal-quarter (e.g. `2024-03-31`) per CONTEXT.md "Active-fund fetch engine". DuckDB stores as `DATE` (`fund_holdings.report_date DATE NOT NULL`). The legacy test in `tests/scoring/test_metrics_loader.py:44` passes `date(2026, 3, 31)` — DuckDB auto-coerces both ISO strings and `datetime.date` to `DATE`. **NEVER use AkShare-published date** (publication lag varies 30–60 days and would corrupt the quarterly disclosure cadence the scoring layer depends on). | CONTEXT.md "Disclosure quarter"; `tests/scoring/test_metrics_loader.py:44`; `duckdb_helper.py:69`. |
| Q5 | Schema migration approach (positional vs named INSERT) | **Named-column `INSERT OR REPLACE` with `executemany`.** Mirrors the precedent set by `_upsert_instruments` (`ingest_cmd.py:313–322`), `_upsert_prices` (`ingest_cmd.py:334–342`), `_upsert_macro` (`ingest_cmd.py:354–361`), and `_upsert_nav` (`ingest_cmd.py:380–388`). Future column additions to `fund_holdings` (e.g. `weight_change_pct`) won't break the ingestor — only the positional test in `tests/scoring/test_metrics_loader.py:43` would need updating (and that's an existing test, not item 010's concern). `ensure_schema` stays additive-only (`CREATE TABLE IF NOT EXISTS` + future `ALTER TABLE ADD COLUMN IF NOT EXISTS` if ever needed). Locked as AC19. | `ingest_cmd.py:313–388` direct read; the 4 existing upsert helpers all use named columns. |
| Q6 | Coupling to item 003's cache layout `data/fundamentals/<quarter>/active_fund/` | **Import `active_fund_cache_path` from `snapshot_cache` for per-quarter path construction, but use a plain `base.glob(f"*/active_fund/fund_{iid}.json")` for the multi-quarter scan.** Two reasons: (1) `active_fund_cache_path(iid, quarter, root)` takes a known quarter — useless for a "find any quarter" scan; (2) item 003 hard-codes the `active_fund/` segment in `snapshot_cache.py:133`, so reusing the segment via glob is no more brittle than reusing it via the path constructor — both break together if item 003 moves the layout. Add a regression test (`test_collect_holding_rows_glob_pattern_matches_cache_path`) that constructs a path via `active_fund_cache_path("X", "2024Q1", root)` and asserts the ingestor's glob would find it. This is the cheapest possible coupling-monitor. | `snapshot_cache.py:132–133`; defensive-test pattern from item 008 grill F1. |
| Q7 | `cn_etf` ActiveFundSnapshot coverage | **Spec is correct: most cn_etf instruments hit the AkShare fallback path.** Item 003 dispatches by `LookthroughTarget.kind`; `cn_etf` resolves to `tracked_index` or `theme`, NOT `active_fund` (CONTEXT.md "Fund-level dispatch"). So the active-fund cache rarely contains `cn_etf` iids. The fallback `fetch_cn_etf_holdings(iid, top_n=10)` is one network call per cn_etf cache-miss, capped at ~30 cn_etf instruments in the typical run universe (confirmed: `config/universe/cn_funds.yaml` has ~22 cn_etf iids). Total worst-case AkShare cost: ~30 calls. **AC9 + a verify-time spy** lock the source attribution: `_source="active_fund_snapshot"` for cn_equity_fund, `_source="akshare_cn_etf"` for cn_etf cache-miss. | CONTEXT.md "Fund-level dispatch"; `config/universe/cn_funds.yaml`; spec §5 D2. |
| Q8 | Idempotency contract | **Same-day rerun against fresh data is a no-op:** `is_stale` returns False → `ingest_one` returns `skipped_fresh` with `rows_written=0` and zero `INSERT` statements. AC4 (existing) locks this. **Same-day rerun against stale data:** writes the same rows; PK `(instrument_id, report_date, holding_ticker)` dedups via `INSERT OR REPLACE`; `_ingested_at` advances but row count stays constant (AC5 + AC12). **Cross-day rerun:** if `today_iso` advances past the staleness threshold, re-ingests; otherwise no-op. Idempotency at the manifest level (`ak_counts["fund_holdings"]`) is NOT byte-equal across two reruns because the no-op rerun reports `rows_written=0` while the first run reports e.g. `350` — this is correct behaviour, not a bug, but locked as a clarifying note in §5 D4. | Spec §AC4–AC5; `duckdb_helper.py:74` PK definition. |
| Q9 | Test fixture strategy | **Real on-disk DuckDB via `tmp_path`, NOT in-memory or mock.** Universal project convention: `tests/data/test_duckdb_helper.py:13/20/32`, `tests/data/test_raw_ref.py:18`, `tests/scoring/test_metrics_loader.py:28/81/92/106/122` ALL use `connect(tmp_path / "local.duckdb")`. The DuckDB Python adapter is in-process / zero-cost; a "mock connection" would require duplicating the SQL-execution surface and would not catch type-coercion bugs (e.g. `DATE` vs ISO string). For `ActiveFundSnapshot` cache: write a real JSON file to `tmp_path / "data" / "fundamentals" / "2024Q1" / "active_fund" / "fund_005827.json"` via `write_active_fund_cache(snap, tmp_path / "data")` (item 003's own writer) — guarantees the format the ingestor reads is identical to production. Fixture files in `tests/fixtures/active_fund_snapshots/` are JSON shadows of typical `ActiveFundSnapshot` bodies, not stub data — the helper builds a real `ActiveFundSnapshot` then serializes via item 003's writer. | `tests/data/test_duckdb_helper.py:13` etc.; CLAUDE.md "Test must be fast, isolated, and deterministic". |
| Q10 | Logging cadence (per-iid vs batch summary) | **Both, behind a verbosity flag.** Per-iid `_log.info("fund_holdings %s: status=%s rows=%d %s", ...)` only when `_verbose` is True (matches existing `ingest_cmd.py:592–598` per-instrument NAV logging pattern). One unconditional summary line: `print(f"  fund_holdings: wrote={...} fresh={...} no_data={...} failed={...}")` after the manifest writes (matches `print(f"ingest OK: ...")` at line 645). The summary line is part of the observability contract; the per-iid line is debug-only. Per-iid logging at typical run cardinality (~350 funds) is ~14 KB stdout — non-trivial but acceptable when `--verbose`. Locked as AC14 + a clarifying note in §B2 wire-in. | `ingest_cmd.py:592–598,645` direct read. |

## Additional findings during grilling

### F1 — `today_iso` derivation: wall-clock `_china_today()`, not pipeline `seed_date`

Spec §B1 says `today_iso` is threaded into `ingest_one` / `ingest_many`. The audit prompt asked whether this uses wall-clock or pipeline `seed_date`. **Direct read of `src/irc/commands/ingest_cmd.py:430` confirms:** `run_ingest` has NO `seed_date` parameter — it derives `today_iso = _china_today()` (UTC+8 wall-clock) at the top of `run_ingest` and threads it through. There is no upstream `seed_date` to inherit. **Item 010 inherits the same wall-clock contract:** `ingest_cmd.py`'s new holdings block passes `today_iso=today_iso` (the already-derived local). For standalone test calls into `ingest_one`, tests pass `today_iso` explicitly (the fixture controls the clock). Locked as AC20. **Rationale for not introducing a `seed_date` indirection:** (a) `run_ingest` is a wall-clock-driven ingestion stage by design (it fetches today's NAV, today's prices) — it has no concept of "pipeline date for historical replay"; (b) introducing a `seed_date` here would invent a contract the rest of `run_ingest` doesn't honour; (c) the 30-day staleness threshold's purpose is "is the upstream provider's latest disclosure stale relative to RIGHT NOW?" — wall-clock is the semantically correct anchor.

### F2 — Risk to item 008's AC22/AC23 two-run byte equality: **NONE**

The audit prompt flagged this risk. Direct inspection of `tests/integration/test_publishable_set_lockdown.py:1002–1080` (`test_two_run_byte_equality_opportunity_artifacts` + `test_two_run_byte_equality_memo_after_run_memo`) reveals:

- AC22/AC23 invoke `run_opportunity(repo_root=...)` and `run_memo(repo_root=...)` directly. **Neither test invokes `run_ingest`.**
- Item 010's wire-in is exclusively in `run_ingest` (no changes to `run_opportunity` / `run_memo`).
- The opportunity + memo stages do NOT read the `fund_holdings` table (verified by `grep -rn "fund_holdings" src/irc/opportunity/ src/irc/memo/` returning zero matches).
- The publishable-set helper (`_publishable_set_helper.py`) does NOT seed `fund_holdings` either (verified by grep).

**Conclusion:** item 010 cannot affect AC22/AC23 by construction. No mitigation required. Locked as a clarifying AC21 ("item 010's holdings-ingest is structurally independent of AC22/AC23 byte-equality").

### F3 — Risk to item 009's citation gate: **NONE**

`src/irc/opportunity/citation_map.py`, `src/irc/opportunity/rejection_log.py`, `src/irc/memo/numeric_audit.py` all read `ThesisEvidence` / `ConstituentAnalysis` from in-memory `OpportunityRow` objects produced by `_build_rows`. None query the `fund_holdings` DuckDB table. Item 010's changes are wholly disjoint from item 009's audit gate surface. The scoring layer (`scoring/factors/quality.py`'s `_concentration_score`) reads `fund_holdings` indirectly via `holdings_concentration_top10`, but the scoring DataFrame is computed in `run_score` (a separate pipeline stage) and the resulting `holdings_concentration_top10` value is a single scalar on `OpportunityRow` — it does not interact with the citation gate. **No coupling. No risk.**

### F4 — `ingest_one` is NOT pure (cache-read + DuckDB-read + DuckDB-write)

Spec §B1 docstring says `collect_holding_rows` is "pure-with-cache-read". This is correct per the project's "Effects at edges" rule — the filesystem read is the boundary, the rest is pure transformation. But `ingest_one` performs three effects: (1) DuckDB `SELECT MAX(report_date)` read, (2) filesystem JSON read (and possibly AkShare network call), (3) DuckDB `INSERT OR REPLACE` write. **This is the I/O orchestration layer** — exactly where effects should live per the project's FP discipline. The grill's audit confirms: `ingest_one` IS the boundary, `upsert_holdings` + `is_stale` + `collect_holding_rows` are the building blocks (each does one effect; their composition is the I/O wrapper). The spec's structure is correct. Locked as a clarifying note in §B1.

### F5 — Universal AkShare-call defensive try/except is overkill but cheap

Spec AC13 says wrap `fetch_cn_etf_holdings` in `try/except Exception`. The adapter's own contract is "never raises" (`akshare_fundamentals.py:262`). So the defensive try/except is technically dead code on the happy path. However: (a) AkShare upstream behaviour drifts across versions (a future AkShare upgrade could re-introduce raise paths); (b) cost is zero (one try/except per cn_etf iid per ingest run); (c) the alternative — propagating an unexpected exception out of `ingest_many` — would crash the entire ingest stage on a single ETF fault, violating the "best-effort enrichment" promise (§B2). **Verdict: keep the defensive try/except.** Spec AC13 is correct as written; no change.

### F6 — Out-of-scope clarification: `ensure_schema` must already be idempotent

Spec §Edge cases says "ingest_cmd calls `ensure_schema(con)` before invoking the ingestor". Verified at `ingest_cmd.py:454` (line `_ensure_local_duckdb(con)` which calls `ensure_schema`). `ensure_schema` uses `CREATE TABLE IF NOT EXISTS` for all 7 tables — already additive-only by construction (`duckdb_helper.py:103–112`). **No item 010 change required to `ensure_schema`.** Locked as a clarifying note in §B1 pre-condition list.

## ADR review

3-of-3 ADR test applied to potential new ADRs for item 010:

| Candidate ADR | Hard to reverse? | Surprising without context? | Real trade-off? | Verdict |
|---|---|---|---|---|
| "fund_holdings retention is no-prune, no-delete in V1" | Marginal (additive future pruner is reversible) | No (matches existing data/*.duckdb retention philosophy) | Marginal (Q2 + Q3) | **SKIP** — locked in spec §Open Q2-Q3 resolutions + CONTEXT.md term. |
| "Active-fund cache is single source of truth for holdings" | Yes (couples item 010 to item 003's cache layout indefinitely) | Yes (counterintuitive — why not call AkShare?) | Yes (spec §Source-of-truth read path) | **Mitigation: extend ADR 0002 §5 in a planner-phase commit** rather than create ADR 0005. The "no duplicate AkShare calls" promise IS the ADR 0002 §5 dispatch contract reading "active_fund" goes to the snapshot cache exclusively. Item 010 enforces this contract on the consumer side; ADR 0002 already establishes it on the producer side. Adding a sentence to ADR 0002 §5 explicitly naming `fund_holdings` ingestion as a downstream consumer is sufficient. NO new standalone ADR. |
| "Named-column INSERT for upsert idempotency" | No (positional → named is a one-PR refactor) | No (matches existing upsert helpers) | No (Q5 is a follow-the-precedent decision) | **SKIP** — locked in spec §AC19. |

**No new ADRs created.** ADR 0001–0004 stand unmodified. The planner SHOULD append a one-sentence cross-reference to `docs/adr/0002-active-fund-fetch-engine.md` §5 naming item 010 / `fund_holdings` ingestion as a downstream consumer of the active-fund cache. This is documentation-only, not a contract change.

## CONTEXT.md additions

One new term appended to a new section "Holdings ingest policy":

1. **`fund_holdings` ingest policy** — wall-clock 30-day staleness gate; named-column `INSERT OR REPLACE`; no-delete-on-empty; no-prune retention; single source of truth is item 003's `ActiveFundSnapshot` cache for `cn_equity_fund` and (when present) `cn_etf`, with `fetch_cn_etf_holdings` as the AkShare fallback ONLY for `cn_etf` cache-misses. Best-effort enrichment for scoring layer — partial failure NEVER blocks `run_ingest`. Idempotent same-day reruns (fresh table → zero `INSERT` statements). Per-row determinism: rows written in `(weight_pct DESC, holding_ticker ASC)` order so DuckDB rowid is reproducible.

## AC audit results

### Testability without live network: PASS (all 21)

Every AC seeds via `tmp_path` (real DuckDB, real `ActiveFundSnapshot` JSON cache files written via `write_active_fund_cache`) or patches `fetch_cn_etf_holdings` for the fallback path. No network reachable. The `fetch_cn_etf_holdings` patch is a `monkeypatch.setattr` on the import-site name — matches existing patch convention from `tests/integration/_publishable_set_helper.py:_install_ak_call_dispatch`.

### Overlap with existing unit tests: AUDITED

- AC1 (DDL byte-equal) overlaps with `tests/data/test_duckdb_helper.py::test_expected_tables_exist` — but that test asserts existence, not byte-equality of the DDL string. Item 010's AC1 is additive (regression on DDL string identity), not duplicative.
- AC12 (`load_scoring_metrics` round-trip) overlaps with `tests/scoring/test_metrics_loader.py::test_load_scoring_metrics_returns_concentration` — that test inserts via positional SQL; item 010's AC12 inserts via the new `ingest_one`. Both should pass; AC12 is the integration test that locks the ingestor's output format against the scoring loader's input expectation. NOT duplicative.
- ACs 22–23 of item 008 are NOT affected by item 010 (per F2). No cross-item duplication to audit.

### Sharpness — single binary pass/fail per AC: PASS (all 21)

Every AC has a `sha256` comparison, `count == N`, `set ⊆ set` membership, `regex match`, `raises ExceptionClass`, or `== literal` predicate. No "the test asserts reasonable behavior" hand-waving. The new AC19 (named-column INSERT) uses a string-contains predicate against the captured SQL via `con.execute` spy — exact match against `INSERT OR REPLACE INTO fund_holdings (instrument_id, report_date, holding_ticker, holding_name, weight_pct, _ingested_at, _source, _raw_ref) VALUES`. AC20 (wall-clock contract) asserts `today_iso` equals `_china_today()` captured at the call site. AC21 (independence from byte-equality) is a meta-AC — implementation note rather than a runnable test.

### What's-already-covered table accuracy: VERIFIED

Re-grepped the test suite at the spec's reference commits — every cited test file exists. `tests/data/` and `tests/fixtures/active_fund_snapshots/` are NEW directories (the `__init__.py` exists in `tests/data/`; `tests/fixtures/` exists with `akshare/` subdirectory; no `active_fund_snapshots/` yet — to be created by item 010).

## File-touch map (revised)

### New files
- `src/irc/data/fund_holdings_ingestor.py` (~160 LOC — pure-core + 3 thin I/O wrappers)
- `tests/data/test_fund_holdings_ingestor.py` (~500 LOC — 22 unit + integration tests per the test plan)
- `tests/fixtures/active_fund_snapshots/fund_005827.json` (10-constituent snapshot)
- `tests/fixtures/active_fund_snapshots/fund_005827_empty.json` (zero constituents, snapshot_empty path)
- `tests/fixtures/active_fund_snapshots/fund_005827_q4.json` (later quarter, latest-wins test)

### Modified files (production)
- `src/irc/commands/ingest_cmd.py` — append the holdings-ingest block after the NAV loop (line ~595), before `finally:`. Add `from irc.data.fund_holdings_ingestor import ingest_many as ingest_fund_holdings` at top. Aggregate `holdings_counts` into `ak_counts["fund_holdings"]`. Add summary `print(...)` line.

### Modified files (tests)
- `tests/commands/test_ingest_cmd.py` — append three wire-in tests (`test_run_ingest_wires_holdings_step`, `test_run_ingest_holdings_failure_not_fatal`, `test_run_ingest_holdings_count_in_manifest`).

### Files explicitly NOT touched
- `src/irc/data/duckdb_helper.py` — schema unchanged; AC1 locks DDL string byte-equality.
- `src/irc/fundamentals/snapshot_cache.py` — item 003 owner; item 010 is a read-only consumer.
- `src/irc/fundamentals/akshare_fundamentals.py` — `fetch_cn_etf_holdings` contract unchanged.
- `src/irc/scoring/metrics_loader.py` — read-only consumer; once `fund_holdings` is populated, existing code returns real values instead of NaN.
- `src/irc/opportunity/`, `src/irc/memo/` — disjoint from holdings ingest (F2/F3).
- `docs/adr/0001-0004` — unchanged (ADR 0002 cross-reference is a planner-phase doc commit, not item 010 prod code).

## Spec file diff

`docs/2026-05-22-thesis-cards-evidence-gap/items/010-spec.md` rewritten with:
- §B1 docstring for `ingest_one` clarified: "I/O orchestration boundary" (per F4); pre-conditions list extended with "caller must invoke `ensure_schema(con)` first" (per F6).
- §B2 wire-in: `today_iso=today_iso` (the already-derived local from `_china_today()`, per F1).
- §"Behaviour rules" (§B1): new bullet on named-column INSERT (Q5) with the exact SQL string locked.
- §"Detailed schema specifications": `HoldingRow.__post_init__` invariants list extended with `source in {"active_fund_snapshot", "akshare_cn_etf"}` (defensive).
- §"Staleness contract": rewritten to lock wall-clock `today_iso` from `_china_today()` (F1).
- §AC1–AC18 retained, sharpened in places.
- §AC19 NEW — "Named-column INSERT shape is locked" (Q5).
- §AC20 NEW — "`today_iso` is wall-clock `_china_today()`, never a pipeline `seed_date`" (F1).
- §AC21 NEW — "Item 010 is structurally independent of item 008's AC22/AC23 byte-equality tests" (F2).
- §"Open questions for the planner / grill" REPLACED with §"Resolved questions" (Q1–Q10 all locked).
- New §"Cross-item impact audit" — explicit "no risk to items 008/009" (F2 + F3).
- Spec line count: 417 → ~480 lines.

## Unresolved questions

None at grill level. The planner inherits a fully-locked spec with one documented deferral (Q1 v2 asset-class expansion) flagged with a re-evaluation trigger ("if `scoring/factors/` grows a bond/gold concentration factor").

## Most consequential clarification

**F1 + Q8 — `today_iso` MUST be `_china_today()`, not a pipeline `seed_date`.** Without F1, the planner could have invented a `seed_date` parameter and threaded it through `ingest_one`, mistakenly modelling holdings ingestion as a "historical replay"-aware stage. **Direct read of `ingest_cmd.py:430` proves `run_ingest` has no `seed_date` concept** — every staleness/freshness check in the ingest stage is wall-clock-anchored. Threading a `seed_date` here would (a) invent a contract upstream `run_ingest` does not honour, (b) make 30-day staleness depend on a parameter the rest of `run_ingest` ignores, leading to silent drift between "is the price data fresh?" and "is the holdings data fresh?" — they would answer different time questions. Locked in AC20 + new CONTEXT.md term. The 30-day threshold and the staleness anchor MUST agree across all ingest stages; using wall-clock for both is the only self-consistent option.

**F2 + AC21 — Item 010 cannot break item 008's AC22/AC23 by construction.** The audit prompt flagged this risk because byte-equality tests are fragile to any non-determinism in the I/O stack. **Direct inspection proves the test surfaces are disjoint:** AC22/AC23 invoke `run_opportunity` + `run_memo`, neither of which reads `fund_holdings`. Item 010's wire-in is in `run_ingest`, which AC22/AC23 do not invoke. The scoring layer (which DOES read `fund_holdings`) runs in `run_score`, also outside AC22/AC23's call path. This is locked as a structural property in AC21 — not a test, but an explicit non-coupling claim that future refactors must preserve.
