# Item 001 — Active-fund autobuild in `narrative --analyze` + fix misleading error string

**Run:** `narrative-coverage-markdown` · **Handoff steps:** #1 + #6
**Primary files:** `src/irc/commands/narrative_cmd.py`, `src/irc/narrative/analyze.py` (read-only; unchanged if possible)
**Pattern to mirror:** `src/irc/commands/opportunity_cmd.py:840` (the only existing active-fund autobuild path)

## Goal

`irc narrative <name> --analyze` currently screens funds it cannot deepen: it is
cache-only (`analyze_fund` calls `load_active_fund_cache` and hardcodes
`theme_report=None`), and no supported command ever builds an `active_fund`
snapshot for a narrative-*discovered* fund (those funds are absent from
`scoring.json`, so `irc opportunity` autobuild never reaches them; `fundamentals
snapshot` writes only index `nav/` snapshots and rejects fund IDs). The result is
that active `cn_equity_fund` shortlist funds resolve to `position_risk_level =
insufficient` purely because their evidence is uncached — not as a market
judgement. This item adds an autobuild step in the **command layer** of
`--analyze` that, for shortlist funds whose `asset_class == "cn_equity_fund"` and
which are **missing** a cached `active_fund` snapshot, builds and caches one via
`build_snapshot(...)` + `write_active_fund_cache(...)` — mirroring
`opportunity_cmd.py:840` — so the existing cache-only `analyze_fund` then loads it
and produces a real thesis. It also corrects the misleading error string at
`narrative_cmd.py:159` that tells users to run `irc fundamentals snapshot` (which
cannot populate this cache). Passive `cn_etf` wiring and markdown rendering are
out of scope (items 002 / 003 / 004).

## Acceptance criteria

1. **Eligibility by active asset class.** Autobuild attempts a snapshot build only
   for shortlist rows with `asset_class == "cn_equity_fund"`. Rows of any other
   `asset_class` (e.g. `cn_etf`, `qdii_*`, `us_etf`, `cn_bond_fund`, `hk_etf`) are
   never built by this item. Verified by a unit test asserting the build function
   is invoked for a `cn_equity_fund` row and **not** invoked for a `cn_etf` row.
2. **Cache-presence gate (no refetch).** Autobuild skips any eligible fund that
   already has a cached `active_fund` snapshot ~~(probe via the latest-quarter
   cache lookup before building)~~ — corrected by grill: probe via the
   **resolved analyze-context quarter** (`load_active_fund_cache(iid, quarter,
   data_dir)` — the exact quarter `analyze_fund` will subsequently read), NOT a
   cross-module "latest-quarter" lookup, so the probe and the consumer agree on
   the quarter (idempotence, AC8) and no `commands/opportunity_cmd.py` private
   helper is imported. Verified by a unit test: a fund with a pre-seeded cache
   file (for the resolved quarter) triggers zero `build_snapshot` calls.
3. **Effects at edges.** All fetch/build/cache-write I/O lives in the
   `commands/` layer (a new thin helper in `narrative_cmd.py`), invoked before the
   per-fund `analyze_fund` loop or per-fund just ahead of it. `analyze_fund`'s
   signature and read-only body are unchanged; it continues to consume the cache
   via the existing `load_active_fund_cache(...)` call. Verified by inspection +
   existing `tests/narrative/test_analyze.py` continuing to pass unmodified.
4. **Default-on with env kill-switch.** Autobuild is default-on for `--analyze` and
   disabled when `IRC_NARRATIVE_AUTOBUILD=0` (mirrors `IRC_OPPORTUNITY_AUTOBUILD`;
   default `"1"`). Verified by a unit test toggling the env var and asserting the
   build function is / is not called.
5. **Build + cache-write shape mirrors opportunity.** A built `ActiveFundSnapshot`
   is written via `write_active_fund_cache(replace(snap, cache_probed_at=<today>),
   root/"data")` **only when** `source_report_quarter` is non-empty (skip the write
   on empty quarter to avoid the `data/fundamentals//active_fund/...` path-collapse).
   Target is obtained from `map_lookthrough(inp)` (kind `active_fund`); build uses
   `build_snapshot(target, top_n=TOP_N_DEFAULT, provider=provider)`. Verified by a
   unit test on the helper with a stubbed builder.
6. **Per-fund failure degrades, never crashes.** A build that raises, returns
   empty holdings, or yields an empty `source_report_quarter` is caught and logged
   (`_log.warning` / `sys.stderr`); that fund proceeds to `analyze_fund` with no
   cache and resolves to `insufficient` exactly as today. The narrative run still
   returns `rc == 0` and writes a report for every shortlist fund. Verified by a
   unit test where the builder raises for one fund and the run still produces a
   full report with that fund `insufficient`.
7. **Fetch budget enforced pre-build (no row sentinel).** The autobuild estimates
   call volume (`≈ TOP_N_DEFAULT`-bounded per eligible-missing fund) and raises
   `FetchBudgetExceeded` **before** any fetch when the estimate exceeds
   `_fetch_budget()` (env `IRC_FETCH_BUDGET`, default 2000). The fatal sentinel
   `fetch_budget_exhausted` is never written into any row's `evidence_gaps`.
   Verified by a unit test setting `IRC_FETCH_BUDGET` low enough to trip the raise.
8. **Determinism / idempotence.** Running `--analyze` twice produces a
   byte-identical `<name>_report.json`: the first run populates the cache, the
   second reuses it with zero `build_snapshot` calls. Verified by a unit test
   asserting (a) byte-identical report JSON across two runs and (b) zero builds on
   the second run.
9. **Corrected error string.** When `_open_analyze_context` returns `None` (no
   `data/local.duckdb` or no discoverable quarter), the stderr message no longer
   instructs the user to run `irc fundamentals snapshot`. It names the real
   prerequisites (`irc ingest` for the DuckDB; a snapshot quarter under
   `data/fundamentals/`) and states that active-fund snapshots are auto-built
   during `--analyze`. Verified by a unit test asserting the new substring is
   present and the literal `fundamentals snapshot` is absent from the message.
10. **No live network in unit tests.** Every new unit test stubs the builder /
    fetch edge (monkeypatch); no test hits AkShare. Any live test is double-gated
    (a `pytest.mark.live_akshare` marker AND `IRC_RUN_LIVE_AKSHARE=1`).
11. **Recovers active funds end-to-end (behavioural).** For a `cn_equity_fund`
    shortlist fund with a successful (stubbed) build, the produced
    `NarrativeFundReport` carries a non-empty `thesis_evidence` and a
    `thesis_state` other than `evidence_insufficient` — i.e. the fund is deepened,
    not merely screened. Verified by a unit test through `_run_analyze` with a
    stubbed builder returning an `ActiveFundSnapshot`.

## Non-goals

- **Passive `cn_etf` fund-level + `theme_report` wiring** into `analyze_fund`
  (detecting passive asset class, loading the `nav/` fund-level snapshot, feeding
  the fund-level NAV data leg + announcement info leg + a theme report) — that is
  **item 002**. This item builds and caches `active_fund` snapshots *only*.
- **Markdown report enrichment** — evidence prose, resolvable citation footnotes,
  product-quality metric drivers — **items 003 / 004**. This item changes no
  rendering in `src/irc/narrative/report.py`.
- **Suppressing the action triad / triggers on `insufficient` rows** — **item 004**.
- Changing the `derive_position_risk_level` rule (`risk.py:60`); the
  `evidence_gaps → insufficient` mapping stays as-is.
- A staleness/freshness probe on the narrative cache (recommend cache-presence
  only for V1; staleness can be added later without touching this contract).
- A narrative-specific fetch-budget knob (reuse `IRC_FETCH_BUDGET`).

## Constraints

- **Effects at edges (CLAUDE.md / CONTEXT.md).** Network/fetch/cache-write I/O is
  confined to the `commands/` layer and thin wrapper functions; `analyze_fund` and
  the narrative stage core stay pure/read-only and unit-testable without mocks.
- **TDD (red → green → refactor).** Every behaviour above lands test-first; test
  files mirror source (`narrative_cmd.py` → `tests/narrative/test_narrative_cmd.py`).
- **Policy B (ADR 0003).** `thesis_state` is set **only** by
  `derive_thesis_from_evidence`, never by Policy B and never by this autobuild path.
  Policy B verdict stamping (rule 2.5 fund-level evidence, gap codes) is whatever
  `build_opportunity_row` / the existing snapshot path already does; this item adds
  no new state-setting logic. (Note: the narrative `analyze_fund` path does not
  currently invoke `evaluate_policy_b`; this item does not add it — it only
  supplies the snapshot the existing path consumes.)
- **No `基金概况` indicator** anywhere in fetch code (acceptance test greps for the
  literal). Information-leg citations come only from `fetch_fund_announcements`.
  Reuse `build_snapshot` / `_build_active_fund_snapshot` unchanged — do not add new
  fetch calls.
- **Frozen dataclasses + `dataclasses.replace`.** Snapshot mutation (e.g. stamping
  `cache_probed_at`, failure reasons) uses `replace(...)`, never in-place mutation.
- **Citation ID format** locked at 16 hex chars (`\[ref:[0-9a-f]{16}\]`, ADR 0001) —
  unchanged; this item produces no new citation shapes.
- **Size budget.** Files < 200 lines, functions < 20 lines (ideal). The autobuild
  helper(s) must be extracted as small named functions, not inlined into
  `run_narrative` / `_run_analyze` past readability. `narrative_cmd.py` is ~168
  lines today; keep it under 200 (extract a helper module if it would overflow).
- **No live network in unit tests; live tests double-gated** (marker +
  `IRC_*=1` env), per the live-test gate in CONTEXT.md.

## Open questions resolved during brainstorming

1. **"Active" detection.** Use `shortlist_row.asset_class == "cn_equity_fund"`,
   decided in the command layer **before** any fetch. Rationale: the gate must
   precede I/O; `ShortlistRow.asset_class` is already available pre-analyze, and
   `map_lookthrough` routes `cn_equity_fund` to `kind="active_fund"`
   unconditionally (lookthrough.py:88), so this is equivalent to checking
   `target.kind` but cheaper and effect-free. Index LOFs in the universe carry
   `asset_class: cn_equity_fund`, so they are correctly treated as active.
2. **Hook location.** Command layer (a new thin helper in `narrative_cmd.py`,
   invoked from `_run_analyze` before / per-fund ahead of `analyze_fund`), **not**
   inside `analyze_fund`. Rationale: effects-at-edges keeps fetch/write out of the
   read-only stage core; leaving `analyze_fund` untouched means its
   `load_active_fund_cache` call transparently picks up the freshly-written cache,
   preserving determinism and the existing `test_analyze.py` suite.
3. **Opt-in vs default-on.** Default-on for `--analyze`, env kill-switch
   `IRC_NARRATIVE_AUTOBUILD` (default `"1"`; `"0"` disables). Rationale: the
   headline bug is that the default is broken; opportunity already defaults
   autobuild on. An env switch (not a CLI flag) keeps the CLI surface stable,
   matches `IRC_OPPORTUNITY_AUTOBUILD`, and lets tests disable network
   deterministically.
4. **Failure behaviour.** Degrade to today's behaviour — catch, log, proceed with
   no cache → `insufficient`; never crash the run. Mirrors the existing per-fund
   try/except in `_run_analyze` and opportunity's `sys.stderr.write` + `replace`
   degrade. Honest under the `evidence_gaps → insufficient` rule.
5. **Fetch budget / `FetchBudgetExceeded`.** Enforce a pre-build budget check
   reusing `_fetch_budget()` / `IRC_FETCH_BUDGET` (default 2000); raise
   `FetchBudgetExceeded` before any fetch if the estimate exceeds it. Never let
   `fetch_budget_exhausted` reach a row gap (it is a fatal sentinel). For a
   `top_n=15` narrative shortlist this realistically never trips, but the guard
   prevents runaway fetch. Reuse the existing budget concept rather than adding a
   narrative-specific knob.
6. **Corrected error string (`narrative_cmd.py:159`).** Replace the
   `run \`irc fundamentals snapshot\`` instruction with one that names the real
   prerequisites and states autobuild now happens during `--analyze`, e.g.:
   > `ERROR: --analyze needs data/local.duckdb (run \`irc ingest\`) and a cached snapshot quarter under data/fundamentals/. Active-fund snapshots are auto-built during --analyze when network access is available; if none exist yet, run \`irc opportunity\` once or re-run --analyze online. Shortlist written to {out}.`
   Rationale: the old text is the "bonus bug" from the handoff — `fundamentals
   snapshot` cannot populate the `active_fund/` cache narrative reads.
7. **Determinism / caching.** Cache-presence gate only (no staleness probe in V1):
   build only when the latest-quarter cache is absent; the second run reuses the
   cache with zero builds → byte-identical report. Keeps the change small and unit
   tests network-free.
8. **Build/cache-write shape.** `target = map_lookthrough(inp)`; build via
   `build_snapshot(target, top_n=TOP_N_DEFAULT, provider=provider)`; on an
   `ActiveFundSnapshot` with non-empty `source_report_quarter`, write via
   `write_active_fund_cache(replace(snap, cache_probed_at=<today_iso>),
   root/"data")`; skip the write on empty quarter. Directly mirrors
   opportunity_cmd.py:851-857 / 870-876.

### Could not be fully resolved from MASTER-SPEC / handoff / code alone

- ~~**Whether to also stamp Policy B verdicts in the narrative path.**~~ —
  resolved by grill (see `## Resolved decisions` Q-G2 below); the minimal
  posture (supply snapshot only, no `evaluate_policy_b`/rule-2.5 stamping) is
  **confirmed in scope** and the rule-2.5 citation-parity enrichment is a
  documented follow-up. Retained for provenance.
  The
  opportunity path runs `evaluate_policy_b` + rule-2.5 fund-level evidence stamping
  after building the row (opportunity_cmd.py:939-954); the narrative `analyze_fund`
  path does **not**. This spec deliberately keeps the narrative path's existing
  behaviour (supply the snapshot only; let `build_opportunity_row` consume it as it
  already does) to stay minimal and avoid changing publishability semantics for
  narrative reports. If a foreign-heavy active fund must be publishable in the
  narrative report via rule 2.5, that is a **follow-up** beyond item 001's stated
  scope (#1 + #6) and should be a separate item. Flagged for the planning step /
  reviewer to confirm this minimal posture is acceptable.

## Resolved decisions

Grilled against CONTEXT.md + ADR 0001/0002/0003 and the real code paths
(`narrative_cmd.py`, `narrative/analyze.py`, `opportunity_cmd.py:840`/`939-954`,
`opportunity/states.py::build_opportunity_row`, `opportunity/lookthrough.py:88`,
`opportunity/policy_b.py` `fired_rule`). Every Q below was auto-accepted on its
recommended answer (no-user-in-loop grill mode).

- **Q-G1: Is narrative autobuild the same concept as opportunity autobuild, or a
  variant deserving its own naming?**
  A: Same concept (build-and-cache an `ActiveFundSnapshot`, cache-presence gated,
  default-on, env kill-switch) on a **different command surface**; it gets its own
  env var `IRC_NARRATIVE_AUTOBUILD` (default `"1"`) so the two kill-switches are
  **independently** togglable, and a glossary nuance because it inverts the
  previously-locked "narrative `--analyze` is cache-only" invariant.
  Rationale: independent toggling is a real operator need; the cache-only inversion
  must be recorded as deliberate, not silent drift.
  Doc impact: CONTEXT.md (new "Narrative active-fund autobuild" term + amended
  "Analyze deepens, then reads cache" entry). No ADR — mirrors ADR 0002.

- **Q-G2: Should the narrative autobuild path also run `evaluate_policy_b` +
  rule-2.5 fund-level evidence stamping like opportunity_cmd.py:939-954?**
  A: **No — keep the minimal posture for item 001.** Supply the snapshot only; let
  `build_opportunity_row → derive_thesis_from_evidence` consume it as today. The
  narrative report has no dual-coverage gate, no H3 partition, no publishability
  decision, so Policy B's gap-codes would have no consumer and `thesis_state` is
  already set exclusively by `derive_thesis_from_evidence` (ADR 0003 — Policy B
  must never set it). The only consequence is that a **foreign-heavy** active fund's
  narrative report carries per-constituent citation legs but not the rule-2.5
  fund-level NAV+announcement legs — a citation-completeness gap, NOT a correctness
  or publishability defect, and it does not change the headline `position_risk_level`
  bug this item fixes.
  Rationale: keeps publishability semantics consistent with CONTEXT.md / ADR 0003;
  avoids semantic creep into the read-only stage core.
  Scope: **in scope** — confirmed minimal posture. Rule-2.5 citation parity in
  narrative reports is a **documented follow-up** (a separate future
  narrative-citation-parity item), out of scope for 001.
  Doc impact: CONTEXT.md (new "Narrative path is Policy-B-free" boundary term).
  No ADR (reaffirms ADR 0003's existing boundary; not a new hard-to-reverse
  decision).

- **Q-G3: Does the rule-2.5 deferral warrant an ADR?**
  A: No. Three-of-three fails: not hard to reverse (a follow-up adds the stamp with
  zero migration), not surprising (strict subset of ADR 0003 §7 — the narrative
  path simply doesn't invoke the publishability layer), no novel trade-off (already
  recorded in ADR 0003).
  Doc impact: none (CONTEXT.md boundary note + this section suffice).

- **Q-G4: Does flipping "narrative --analyze is cache-only" → "auto-builds" need an
  ADR?**
  A: No — CONTEXT.md amendment instead. Reversible (`IRC_NARRATIVE_AUTOBUILD=0`
  restores the exact cache-only behaviour), unsurprising (directly mirrors
  ADR 0002's opportunity autobuild), no novel trade-off.
  Doc impact: CONTEXT.md ("Analyze deepens, then reads cache" amendment). No ADR.

- **Q-G5: "active fund" / `cn_equity_fund` vs index LOF terminology (resolved-Q #1
  claims index LOFs labelled `cn_equity_fund` are treated as active).**
  A: No conflict to fix. `lookthrough.py:88` routes `cn_equity_fund → active_fund`
  unconditionally for the *entire* pipeline, so an index LOF mislabelled
  `cn_equity_fund` is already treated as active everywhere — the narrative gate
  inherits the same benign over-inclusion as the opportunity path. The spec's use
  of "active fund" / `cn_equity_fund` is consistent with CONTEXT.md.
  Doc impact: none.

- **Q-G6: "shortlist" / "look-through" terminology drift?**
  A: None. "Shortlist row" (`ShortlistRow`) and "look-through" (`map_lookthrough`)
  match CONTEXT.md "Narrative selector" / "Screen → analyze gate" and the code.
  Doc impact: none.

- **Q-G7: Cache-presence probe — reuse `_load_latest_active_fund_cached`
  (latest-quarter, private to opportunity_cmd.py) or probe the resolved quarter?**
  A: Probe the **resolved analyze-context quarter** via the public
  `load_active_fund_cache(iid, quarter, data_dir)` — the exact quarter
  `analyze_fund` will read. Rationale: probing "latest" while `analyze_fund` reads
  "resolved" could build/write quarter X yet read quarter Y → non-idempotent
  (breaks AC8); and it avoids a `narrative_cmd.py → opportunity_cmd.py` private
  cross-command import.
  Doc impact: spec strike-through on Acceptance #2. No CONTEXT/ADR change.

- **Q-G8: `FetchBudgetExceeded` / `_fetch_budget` — reuse or re-define?**
  A: **Reuse** the public `FetchBudgetExceeded` exception class and `_fetch_budget()`
  helper from `opportunity_cmd.py` (a legitimate shared seam — unlike the private
  cache probe). The narrative pre-build estimate is a documented constant fan-out:
  `n_eligible_missing × (constant × TOP_N_DEFAULT)`, compared against
  `_fetch_budget()` (`IRC_FETCH_BUDGET`, default 2000), raising before the first
  fetch. No narrative-specific budget knob (reuse the "Preflight fetch budget"
  concept). For a `top_n≈15` shortlist this never trips in practice.
  Doc impact: none (already glossaried under "Preflight fetch budget").

- **Q-G9: Does the corrected error string over-promise autobuild?**
  A: Tighten so it does not imply autobuild rescues the `None`-context case. The
  error fires precisely when `_open_analyze_context` returns `None` (no DuckDB or
  no discoverable quarter) — i.e. autobuild cannot even start. Name the real
  prerequisites (`irc ingest` for `data/local.duckdb`; a snapshot quarter under
  `data/fundamentals/`), state that active-fund snapshots are auto-built **during a
  successful `--analyze`** (once the context opens), and **drop** the
  `irc fundamentals snapshot` instruction (the bonus bug — it cannot populate the
  `active_fund/` cache narrative reads). Resolved-Q #6 wording is directionally
  correct and stands with this tightening; Acceptance #9's grep assertions
  (`fundamentals snapshot` absent, new substring present) are unchanged.
  Doc impact: none beyond this note.

- **Q-G10: `build_snapshot` return type vs `write_active_fund_cache` input
  (Acceptance #5).**
  A: No change. For `kind == "active_fund"` targets `build_snapshot` returns an
  `ActiveFundSnapshot`; the `isinstance(...)` guard before
  `write_active_fund_cache(snap: ActiveFundSnapshot, root)` is the correct
  defensive shape and mirrors `opportunity_cmd.py` exactly.
  Doc impact: none.
