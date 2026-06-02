# Item 002 — Passive-ETF fund-level + `theme_report` wiring into `analyze_fund`

**Run:** `narrative-coverage-markdown` · **Handoff step:** #2
**Primary files:** `src/irc/narrative/analyze.py`, `src/irc/commands/narrative_autobuild.py`,
`src/irc/commands/narrative_cmd.py` · (read-only consumers: `src/irc/fundamentals/snapshot.py`,
`src/irc/fundamentals/snapshot_cache.py`, `src/irc/opportunity/states.py`)
**Pattern to mirror:** item 001 (`autobuild_active_funds`) on the build side;
`opportunity_cmd.py:909-924` (`_resolve_fund_level_snapshot` / `_load_latest_nav_cached`) on the
fund-level dispatch side.

## Goal

`irc narrative <name> --analyze` cannot deepen passive vehicles. For a shortlist row whose
`asset_class` resolves to a **fund-level** lookthrough target (`cn_etf`, `us_etf` → `qdii_us`,
`hk_etf` → `qdii_hk`, and any tracked-index row that maps to `broad_index`/`sector_theme`/`qdii_*`
**with a `provider_symbol`**), the run is **doubly blocked**:

1. `analyze_fund` (`analyze.py:107`) loads **only** `load_active_fund_cache(...)` — the
   active-fund cache — so a passive fund's fund-level NAV snapshot (cached under `nav/`, never
   `active_fund/`) is never read; and
2. `theme_report=None` is hardcoded (`analyze.py:108`).

With `snapshot is None AND theme_report is None`, `build_opportunity_row` (`states.py:544-559`)
takes the table-fallback path and unconditionally stamps
`missing_constituent_snapshot + news_stage_skipped (+ constituent_missing)` → every passive row
resolves to `position_risk_level = insufficient` purely because evidence is uncached. This is the
`robots_report` gap (8/8 `cn_etf`, all insufficient).

Per CONTEXT.md "Passive ETF / tracked index", passive-ETF investability is **fund-level** — a NAV
data leg + an ETF/`fund_announcement_em` information leg, with **no per-constituent drill-through**.
The machinery exists (`FundLevelSnapshot`, `_build_fund_level_snapshot`, `write_nav_cache` /
`load_nav_cache`) but is **not wired into the narrative path**.

This item:

- adds a **passive fund-level autobuild edge** in `narrative_autobuild.py` (mirroring
  item 001's `autobuild_active_funds`) that builds a `FundLevelSnapshot` via
  `build_snapshot(target, provider=provider)` and caches it via `write_nav_cache(...)` for
  fund-level-eligible shortlist rows missing a cached `nav/` snapshot; and
- teaches `analyze_fund` to **dispatch on the resolved lookthrough kind**: active rows load the
  active cache (item 001's behaviour, unchanged); fund-level rows load a `FundLevelSnapshot` from
  the `nav/` cache and feed it into `build_opportunity_row` as the `snapshot` argument.

The result: a passive fund with both legs cached reaches a real `thesis_state` (`intact`) via the
`FundLevelSnapshot` branch of `derive_thesis_from_evidence`, recovering `robots_report`.

`theme_report` remains `None` for the narrative path in V1 — see Open Question Q4 (the fund-level
dual-leg gate does **not** consume `theme_report`; real theme-report sourcing is a flagged
follow-up, not a blocker for this item's recovery goal).

## Acceptance criteria

1. **Fund-level eligibility by resolved lookthrough kind.** The passive autobuild attempts a
   `FundLevelSnapshot` build only for shortlist rows whose resolved `LookthroughTarget` is
   fund-level **and carries a `provider_symbol`** — i.e. `target.kind ∈ (_FUND_LEVEL_KINDS ∪
   {"qdii_us", "qdii_hk", "qdii_global"}) AND target.provider_symbol`. Rows that resolve to
   `active_fund` (item 001's domain) or to a QDII target **without** a `provider_symbol` (the
   zero-fetch sentinel — nothing to cache) are never built by this path. Verified by a unit test
   asserting the build function is invoked for a `cn_etf` / `us_etf` row and **not** invoked for a
   `cn_equity_fund` row nor for a `provider_symbol`-less QDII row.
2. **Eligibility decided before any I/O.** The fund-level eligibility predicate is computed from
   an effect-free ~~`map_lookthrough(...)`-equivalent on the shortlist row's `(asset_class, theme,
   tracked_index)`~~ — corrected by grill (RD-3): `ShortlistRow` carries **no** `theme`/`tracked_index`
   (schema is `instrument_id, name_cn, asset_class, overlap, holdings`); `map_lookthrough` reads
   `(asset_class, theme, tracked_index)` from the resolved **`Instrument`** via `_build_input`
   (`inputs_build.py:27-28`). The passive autobuild therefore **takes the instrument index**
   (`instr_index` from `_open_analyze_context`) and resolves the target via
   `map_lookthrough(_build_input(score_row, instr, ...))`, deriving `(asset_class, theme,
   tracked_index)` from the in-memory `instr` (no DB round-trip needed for the eligibility decision),
   with no network, filesystem, or LLM call. This is the deliberate signature difference from the
   active autobuild, whose `cn_equity_fund → active_fund` mapping is instrument-independent. Verified
   by a unit test that exercises the predicate with a stubbed provider and asserts zero fetch calls.
3. **Cache-presence gate (no refetch).** The passive autobuild skips any eligible fund that
   already has a cached `nav/` `FundLevelSnapshot`. Because fund-level snapshots are keyed by the
   **NAV-derived `source_report_quarter`** (calendar quarter from `latest_nav_date`, unknowable
   before fetch — distinct from item 001's analyze-context-quarter probe), the presence probe is a
   **latest-`nav/`-quarter scan** (`root/fundamentals/*/nav/fund_{id}.json`, mirroring
   `opportunity_cmd._load_latest_nav_cached`), NOT a fixed-quarter `load_nav_cache(id, quarter,
   ...)` lookup. Verified by a unit test: a fund with a pre-seeded `nav/` cache file triggers zero
   `build_snapshot` calls.
4. **Effects at edges.** All fetch/build/cache-write I/O lives in the `commands/` layer
   (`narrative_autobuild.py`, invoked from `narrative_cmd._run_analyze` before the per-fund loop —
   alongside the existing `autobuild_active_funds` call). `analyze_fund` performs **reads only**
   (`load_nav_cache` / latest-`nav/` scan + `load_active_fund_cache`); it fetches nothing live.
   Verified by inspection + a unit test confirming `analyze_fund` issues no `build_snapshot` /
   AkShare calls.
5. **`analyze_fund` dispatches on lookthrough kind.** `analyze_fund` selects the snapshot loader
   by the resolved `target.kind`: `active_fund` → `load_active_fund_cache(iid, quarter, data_dir)`
   (unchanged); a fund-level kind → load a `FundLevelSnapshot` via the latest-`nav/` scan
   (AC3's probe). The selected snapshot (whichever type) is passed to `build_opportunity_row(...,
   snapshot=<snap>, theme_report=None)`. The dispatch is extracted into a small named reader helper
   (`< 20` lines) so `analyze_fund` stays focused. Verified by a unit test: a `cn_etf` row with a
   pre-seeded `nav/` cache produces an `OpportunityRow` whose `thesis_state` is derived from the
   `FundLevelSnapshot` branch (not the table fallback).
6. **Dual-leg gate → real `thesis_state` (Policy-B-free).** A `cn_etf` row whose cached
   `FundLevelSnapshot` carries **both** a NAV data-leg (`citation_kind="data"`) and ≥1 announcement
   information-leg (`citation_kind="information"`) resolves to `thesis_state == "intact"` (not
   `evidence_insufficient`) via `derive_thesis_from_evidence`'s `FundLevelSnapshot` branch
   (`thesis_evidence.py:361-368`). `thesis_state` is set **only** by `derive_thesis_from_evidence`;
   the narrative path does **not** invoke `evaluate_policy_b` / `_stamp_*_from_verdict` (Policy B
   applies only to `ActiveFundSnapshot`, and the narrative path is Policy-B-free per item 001's
   grill / CONTEXT.md). Verified by a unit test through `_run_analyze` (stubbed builder returning a
   two-leg `FundLevelSnapshot`) asserting `thesis_state == "intact"` and `position_risk_level !=
   "insufficient"`.
7. **Partial-evidence honesty.** A `FundLevelSnapshot` with only one leg (NAV-only or
   announcements-only) resolves to `thesis_state == "evidence_insufficient"` →
   `position_risk_level == "insufficient"` — the honest partial, not a fabricated verdict. Verified
   by a unit test with a one-leg snapshot.
8. **Default-on with the shared env kill-switch.** The passive autobuild is default-on for
   `--analyze` and disabled when `IRC_NARRATIVE_AUTOBUILD=0` (the **same** switch as the active
   autobuild — one narrative kill-switch, both paths). Verified by a unit test toggling the env var
   and asserting the build function is / is not called.
9. **Build + cache-write shape mirrors the opportunity fund-level path.** A built
   `FundLevelSnapshot` is written via `write_nav_cache(replace(snap, cache_probed_at=<today_iso>),
   root/"data")` **only when** `source_report_quarter` is non-empty AND
   `"qdii_information_unavailable" not in snap.evidence_gaps` (mirrors
   `_resolve_fund_level_snapshot` at `opportunity_cmd.py:374-376`; `write_nav_cache` already
   no-ops on the QDII sentinel, so the path-collapse is doubly guarded). Build uses
   `build_snapshot(target, provider=provider)` (no `top_n` — fund-level fetch ignores it). Verified
   by a unit test on the helper with a stubbed builder.
10. **Per-fund failure degrades, never crashes.** A build that raises, returns a non-`FundLevelSnapshot`,
    or yields an empty `source_report_quarter` is caught and logged (`_log.warning`); that fund
    proceeds to `analyze_fund` with no `nav/` cache and resolves to `insufficient` exactly as today.
    The narrative run still returns `rc == 0` and writes a report for every shortlist fund. Verified
    by a unit test where the builder raises for one passive fund and the run still produces a full
    report with that fund `insufficient`.
11. **Fetch budget enforced pre-build (no row sentinel).** The passive autobuild estimates call
    volume using the existing typed `FetchPlan.fund_level_misses` (costed at 4 calls each per
    ADR 0002 §5: 1 NAV + 3 announcement endpoints) and raises `FetchBudgetExceeded` **before** any
    fetch when the combined estimate exceeds `_fetch_budget()` (`IRC_FETCH_BUDGET`, default 2000).
    No narrative-specific budget knob is added. `fetch_budget_exhausted` is never written into any
    row's `evidence_gaps`. Verified by a unit test setting `IRC_FETCH_BUDGET` low enough to trip the
    raise. (The active and passive autobuilds may share one preflight `FetchPlan` or run two
    sequential budget-checked passes; either is acceptable as long as the raise is pre-fetch.)
12. **Determinism / idempotence.** Running `--analyze` twice over a passive shortlist produces a
    byte-identical `<name>_report.json`: the first run populates the `nav/` cache, the second reuses
    it with zero `build_snapshot` calls. Verified by a unit test asserting (a) byte-identical report
    JSON across two runs and (b) zero builds on the second run.
13. **No live network in unit tests.** Every new unit test stubs the builder / fetch edge
    (monkeypatch); no test hits AkShare. Any live test is double-gated (a `pytest.mark.live_akshare`
    marker AND `IRC_RUN_LIVE_AKSHARE=1`).
14. **Active path unchanged; existing suites green.** Item 001's active autobuild, the
    `analyze_fund` active-cache read, and the existing `tests/narrative/test_analyze.py` /
    `test_narrative_autobuild.py` / `test_narrative_cmd.py` continue to pass. A `cn_equity_fund` row
    still loads via `load_active_fund_cache` and is never built by the passive path. Verified by the
    existing suites passing unmodified plus a regression test asserting the active loader is used for
    a `cn_equity_fund` row.

## Non-goals

- **Active `cn_equity_fund` autobuild + cache load** — **item 001 (done/merged)**. This item adds
  the passive fund-level path *alongside* 001's active path; it does not touch 001's behaviour.
- **Markdown report enrichment** — evidence prose, resolvable citation footnotes, product-quality
  metric drivers — **item 003**. This item changes no rendering in `src/irc/narrative/report.py`.
- **Suppressing the action triad / triggers on `insufficient` rows** — **item 004**.
- **Real `theme_report` sourcing for the narrative path** (building/loading a theme report keyed by
  the narrative basket, `inp.theme`, or the persisted `data/research/` corpus and threading it into
  `build_opportunity_row`). Deliberately deferred — see Open Question Q4. The fund-level dual-leg
  gate does not consume `theme_report`, so `robots_report` recovery does not depend on it. Flagged
  as a documented follow-up for the planner/reviewer.
- **Policy B / rule-2.5 stamping in the narrative path** — Policy B applies only to
  `ActiveFundSnapshot`; the narrative path stays Policy-B-free (item 001's grill / CONTEXT.md
  "Narrative path is Policy-B-free").
- **Changing `derive_position_risk_level`** (`risk.py:60`) or the `FundLevelSnapshot` dual-leg gate
  (`thesis_evidence.py:348-373`) — both consumed as-is.
- A staleness/freshness probe on the narrative `nav/` cache (cache-presence only for V1; staleness
  can be added later without touching this contract — mirrors item 001's decision).

## Constraints

- **Effects at edges (CLAUDE.md / CONTEXT.md).** Network/fetch/cache-write I/O is confined to the
  `commands/` layer (`narrative_autobuild.py`) and thin wrappers; `analyze_fund` and the narrative
  stage core stay read-only and unit-testable without network mocks.
- **TDD (red → green → refactor).** Every behaviour above lands test-first; test files mirror source
  (`narrative_autobuild.py` → `tests/narrative/test_narrative_autobuild.py`; `analyze.py` →
  `tests/narrative/test_analyze.py`).
- **Policy-B-free narrative path (ADR 0003).** `thesis_state` is set **only** by
  `derive_thesis_from_evidence`; this item adds no `evaluate_policy_b` call and no new
  state-setting logic. It only supplies the `FundLevelSnapshot` the existing gate consumes.
- **ADR 0002 §5 (fund-level engine) / 2026-05-25 QDII fetch reform.** Reuse `_build_fund_level_snapshot`
  / `build_snapshot` / `write_nav_cache` / `load_nav_cache` unchanged; `us_etf`/`hk_etf` route to
  `qdii_us`/`qdii_hk` and fetch fund-level NAV + announcements when a `provider_symbol` is present
  (QDII reform). Do not add new fetch calls.
- **No `基金概况` indicator** anywhere in fetch code (acceptance test greps for the literal).
  Information-leg citations come only from `fetch_fund_announcements`. This item adds no fetch — it
  reuses the existing fund-level fetch — so the constraint is preserved by construction.
- **Frozen dataclasses + `dataclasses.replace`.** Snapshot mutation (stamping `cache_probed_at`)
  uses `replace(...)`, never in-place mutation.
- **Citation ID format** locked at 16 hex chars (`\[ref:[0-9a-f]{16}\]`, ADR 0001) — unchanged;
  fund-level evidence already emits compliant citation IDs (`_build_fund_level_snapshot`).
- **Size budget.** Files < 200 lines, functions < 20 lines (ideal). Extract small named helpers
  (`autobuild_fund_level_funds`, `_fund_level_eligible_missing`, `_build_and_cache_fund_level_one`,
  and a reader helper in `analyze.py`). `narrative_autobuild.py` is ~120 lines today; keep it
  under 200 (split into a `narrative_autobuild_passive.py` module if it would overflow).
- **No live network in unit tests; live tests double-gated** (marker + `IRC_*=1` env), per the
  live-test gate in CONTEXT.md.

## Open questions resolved during brainstorming

(No live user — every question auto-resolved on its recommended answer + rationale. Grounded in
CONTEXT.md, the handoff PART 1 "Fixability → Passive ETFs" bullet, ADR 0002 §5 / 0003, and the real
code paths `map_lookthrough`, `build_snapshot`, `thesis_evidence.py:330-373`,
`opportunity_cmd.py:909-924`, `narrative_autobuild.py`, `analyze.py`.)

**Q1 — Which asset_classes are "passive fund-level" for the narrative path?**
A: Gate on the **resolved `LookthroughTarget.kind`**, not a hardcoded asset-class list:
`target.kind ∈ (_FUND_LEVEL_KINDS ∪ {qdii_us, qdii_hk, qdii_global}) AND target.provider_symbol`.
~~In practice this covers `cn_etf` (→ falls through `map_lookthrough` to `broad_index`/`sector_theme`
with `provider_symbol`), `us_etf` (→ `qdii_us`), `hk_etf` (→ `qdii_hk`), and `qdii_global` — all
with a `provider_symbol` per the 2026-05-25 QDII fetch reform.~~ — corrected by grill (RD-2): there
is **no `cn_etf` branch** in `map_lookthrough`. `us_etf`→`qdii_us`, `hk_etf`→`qdii_hk`,
`qdii_global`→`qdii_global` (all with `provider_symbol`, QDII reform). A `cn_etf` row resolves only
via its `tracked_index` (→ `broad_index`/`qdii_*` with `provider_symbol`) or a recognized `theme`
(→ `sector_theme` with `provider_symbol`); a **bare** `cn_etf` with neither falls to the terminal
`LookthroughTarget("broad_index","unknown","未知底层")` which carries **no** `provider_symbol` and is
correctly excluded (nothing to fetch). The predicate's `AND target.provider_symbol` clause is what
makes this correct — verified at `lookthrough.py:80-164`.
Rationale: `target.kind` is the single source of truth that both `build_snapshot` (`snapshot.py:263-280`)
and `opportunity_cmd.py:909-912` dispatch on; reusing it avoids a divergent asset-class list that
could silently drift from the engine. `cn_equity_fund` is excluded (it routes to `active_fund` —
item 001). QDII targets lacking a `provider_symbol` resolve to the zero-fetch sentinel (nothing to
cache) and are excluded.

**Q2 — Where does the passive branch live — `analyze_fund` signature change or a new helper?**
A: `analyze_fund` keeps its signature and gains an internal dispatch on the resolved `target.kind`
(extracted to a `< 20`-line reader helper): active → `load_active_fund_cache`; fund-level →
latest-`nav/` `FundLevelSnapshot` load. The fetch/build/write stays entirely in the `commands/`
layer (`narrative_autobuild.py`).
Rationale: mirrors item 001's discipline (analyze_fund read-only, effects at edges). Both snapshot
types are already accepted by `build_opportunity_row(snapshot=...)`, so the only change inside the
stage core is *which cache to read* — a pure decision driven by the already-computed `target`.

**Q3 — Add a passive fund-level autobuild edge, or rely on existing `nav/` caches?**
A: **Add a passive autobuild edge** (`autobuild_fund_level_funds`), mirroring item 001's
`autobuild_active_funds`.
Rationale: the handoff's core finding is that narrative-*discovered* passive funds are absent from
**every** cache — there is no `nav/` cache for them either, because `fundamentals snapshot` only
builds the fixed 29-entry registry of index *names*, not discovered fund IDs. "Load existing cache
only" would recover nothing (it is the gap). Effects-at-edges is preserved by keeping
build/fetch/write in `commands/narrative_autobuild.py`. The handoff's "machinery exists, just not
wired" refers to `_build_fund_level_snapshot` / `FundLevelSnapshot` / `write_nav_cache`; the
autobuild *wiring* is the new glue — identical in spirit to item 001.

**Q4 — `theme_report` sourcing for a passive narrative fund. (FLAGGED — judgment call.)**
A: Pass **`theme_report=None`** for the passive narrative path in V1; do **not** source a real
theme report.
Rationale & flag: the MASTER-SPEC item title reads "+ theme_report wiring," but the **load-bearing
recovery mechanism is the fund-level snapshot, not the theme report**. Verified at
`thesis_evidence.py:348-373`: the `FundLevelSnapshot` branch of `derive_thesis_from_evidence`
**never reads `theme_report`** — the dual-leg gate is satisfied purely by NAV (data) + announcements
(information) on `FundLevelSnapshot.evidence`. So a passive fund with both legs reaches
`thesis_state="intact"` *without* a theme report, and `robots_report` recovery does not depend on it.
Sourcing a genuine theme report for a narrative-discovered passive fund is a **larger sub-problem**:
the opportunity path gets it from the persisted `data/research/` corpus via `load_theme_reports(root)`
+ `_resolve_research_theme(inp, theme_reports)` (`opportunity_cmd.py:579-597`), keyed by
`inp.theme` / asset_class — a corpus and mapping policy not currently part of the narrative
shortlist's inputs, and one that would add a new I/O dependency to `_run_analyze`. **Explicitly
scoped OUT of item 002 and flagged for the planner/reviewer**: if theme-report enrichment is wanted
later, the recommended shape is to `load_theme_reports(root)` once in `_run_analyze` and thread a
`_resolve_research_theme`-equivalent through `analyze_fund → build_opportunity_row(theme_report=...)`.
This is a citation-richness enhancement (supplemental `asset_class_macro`-scope evidence), **not** a
gate-passing requirement — so deferring it does not block this item's `robots_report` recovery.
(Documented follow-up, not silent scope reduction.)

**Q5 — Does a passive fund with NAV + announcement legs pass the dual-leg gate to a real
`thesis_state`?**
A: Yes — confirmed against `thesis_evidence.py:361-368`: `has_data AND has_info → "intact"`.
NAV-only or announcements-only → `"evidence_insufficient"` (honest partial). `thesis_state` is set
only by `derive_thesis_from_evidence`; the narrative path runs no `evaluate_policy_b` (Policy B is
`ActiveFundSnapshot`-only and the narrative path is Policy-B-free).
Rationale: matches CONTEXT.md "Passive ETF / tracked index" (fund-level NAV data leg + announcement
info leg) and the dual-coverage gate definition.

**Q6 — Cache-presence probe: fixed analyze-quarter (like item 001) or latest-`nav/` scan?**
A: **Latest-`nav/` scan** (`root/fundamentals/*/nav/fund_{id}.json`, most-recent quarter), used
identically by the autobuild gate AND `analyze_fund`'s load.
Rationale: unlike active snapshots (keyed by the provider-declared holdings quarter, which item 001
probes via the resolved analyze-context quarter), fund-level snapshots are keyed by the
**NAV-derived `source_report_quarter`** (calendar quarter from `latest_nav_date`) — unknowable
before the fetch. Probing a fixed analyze-context quarter would build/write quarter X yet read
quarter Y → non-idempotent (breaks AC12). The latest-`nav/` scan (mirroring
`opportunity_cmd._load_latest_nav_cached`) keeps the probe and the consumer agreed on the same
quarter. This is the deliberate, documented difference from item 001's probe.

**Q7 — Failure / budget behaviour.**
A: Mirror item 001 exactly. Per-fund build failure → logged, no write → `analyze_fund` loads no
`nav/` cache → `evidence_insufficient` → `insufficient`; never crash. Budget: reuse the typed
`FetchPlan.fund_level_misses` (4 calls each) + `_fetch_budget()` + `FetchBudgetExceeded`; raise
pre-fetch. The QDII sentinel (no `provider_symbol`) is skipped (nothing to cache;
`write_nav_cache` also no-ops on the `qdii_information_unavailable` gap).
Rationale: identical degrade contract to item 001; budget reuses the existing typed accounting
(`FetchPlan` already has `fund_level_misses`) rather than inventing a knob.

**Q8 — Env switch: new `IRC_NARRATIVE_PASSIVE_AUTOBUILD` or reuse `IRC_NARRATIVE_AUTOBUILD`?**
A: **Reuse `IRC_NARRATIVE_AUTOBUILD`** (one narrative kill-switch governs both the active and
passive autobuild edges).
Rationale: both are "narrative `--analyze` autobuild"; an operator who disables narrative autobuild
expects *all* of it off. A second switch is unnecessary surface and risks a half-on state. The
active/narrative vs opportunity split (`IRC_NARRATIVE_AUTOBUILD` vs `IRC_OPPORTUNITY_AUTOBUILD`)
already gives the needed independence.

### Could not be fully resolved from MASTER-SPEC / handoff / code alone

- **Real `theme_report` sourcing for the narrative path (Q4).** The MASTER-SPEC item title says
  "+ theme_report wiring," but the code proves the fund-level dual-leg gate does **not** consume
  `theme_report` (`thesis_evidence.py:348-373`), so `robots_report` recovery is achievable with
  `theme_report=None`. Whether the item *intends* genuine theme-report sourcing (and by which key —
  narrative basket? `inp.theme`? the `data/research/` corpus?) is **not determinable** from the
  MASTER-SPEC row, the handoff, or the code alone — the handoff itself flags this as "the part most
  likely to need a judgment call." Resolved conservatively to `None` (fund-level-snapshot-only V1)
  and **flagged for the planner/reviewer**: if theme-report enrichment is in-intent, it is a
  bounded follow-up reusing `load_theme_reports` + `_resolve_research_theme` (see Q4), and should be
  promoted to its own slice rather than silently widening item 002.

## Resolved decisions

Grill session (`grill-with-docs`, subagent: opus). No live user — every question auto-resolved on
its recommended answer + rationale, grounded in the real code paths and the project docs. Q/A pairs
below; doc-impact recorded against `CONTEXT.md` (the spec itself is refined inline via strikethrough
+ this section). **No new ADR** — the passive narrative path is a documented extension of ADR 0002 §5
(fund-level engine) + item 001's autobuild pattern, neither hard-to-reverse nor surprising (fails the
three-of-three ADR test; ADR 0002 §5 already rejected a separate fund-level ADR).

**RD-1 — Is `theme_report=None` correct, given the `FundLevelSnapshot` branch ignores `theme_report`?**
A: **Yes — confirmed, decision UNCHANGED.** `derive_thesis_from_evidence`'s `FundLevelSnapshot` branch
(`thesis_evidence.py:348-373`) reads **only** `snapshot.evidence` + `snapshot.evidence_gaps`; the
`theme_report` parameter is never referenced on that branch. `has_data AND has_info → "intact"`. So
`robots_report` recovery is gate-independent of `theme_report`. Genuine theme-report sourcing is a
citation-richness enhancement (`asset_class_macro`-scope supplement), not a gate requirement —
deferred as a documented follow-up (Q4 / non-goals). Doc-impact: new CONTEXT.md term **"Narrative
passive path is theme-independent"** recording WHY this is by-design, not a bug.

**RD-2 — Does the eligibility predicate match how `opportunity` treats passive funds? Any
asset_class wrong?** A: **Predicate correct, matches `opportunity_cmd.py:909-912` verbatim**
(`target.kind in qdii_* or (target.kind in _FUND_LEVEL_KINDS and target.provider_symbol)`). The
narrative predicate ANDs `provider_symbol` across QDII too — strictly safer (a QDII target without a
`provider_symbol` is the zero-fetch sentinel `write_nav_cache` no-ops on). `gold`/`bond` are in
`_FUND_LEVEL_KINDS` and would be handled identically if a basket surfaced them — harmless. Only the
**Q1 prose** overstated "cn_etf → falls through with provider_symbol": there is no `cn_etf` branch in
`map_lookthrough`; a bare cn_etf (no `tracked_index`/`theme`) hits the no-`provider_symbol` terminal
default and is correctly excluded. Doc-impact: spec Q1 strikethrough; no CONTEXT.md/ADR change.

**RD-3 — Can eligibility be computed effect-free from the `ShortlistRow`?** A: **No — corrected.**
`ShortlistRow` has no `theme`/`tracked_index`; `map_lookthrough` reads them from the resolved
`Instrument` via `_build_input`. The passive autobuild must take the **instrument index** and resolve
the target through `map_lookthrough(_build_input(...))` (deriving `(asset_class, theme,
tracked_index)` from the in-memory `instr` — no DB round-trip for the decision). This is the
signature difference from the active autobuild (whose `cn_equity_fund → active_fund` mapping is
instrument-independent). Doc-impact: spec AC2 strikethrough; CONTEXT.md autobuild term notes the
instr-resolved eligibility.

**RD-4 — Is the latest-`nav/`-quarter probe the right idempotence key (vs item 001's
analyze-context-quarter)?** A: **Yes — confirmed, UNCHANGED.** Fund-level `source_report_quarter` is
NAV-derived (`infer_quarter(latest_nav_date)`, ADR 0002 §5) and unknowable pre-fetch; the cache path
is `…/{quarter}/nav/fund_{id}.json`. A fixed analyze-context-quarter probe would write quarter X yet
read quarter Y → non-idempotent (breaks AC12). The latest-`nav/` scan (`_load_latest_nav_cached`)
keeps writer-gate and reader-load on the same quarter. Active snapshots differ — keyed by the
provider-declared holdings quarter. Doc-impact: new CONTEXT.md term **"NAV-derived quarter (latest-
`nav/` probe)"** distinguishing the two probe keys.

**RD-5 — Does the passive autobuild need a new ADR or its own kill-switch?** A: **No new ADR; reuse
`IRC_NARRATIVE_AUTOBUILD`.** ADR 0002 §5 explicitly rejected a separate fund-level ADR; item 001's
narrative autobuild added none either (CONTEXT.md term only). One narrative kill-switch governs both
edges (an operator disabling narrative autobuild expects all of it off). Doc-impact: new CONTEXT.md
term **"Narrative passive fund-level autobuild"**, sibling to the active one.

**RD-6 — Does the dual-leg gate reach a real, Policy-B-free `thesis_state`?** A: **Yes — confirmed,
UNCHANGED.** `thesis_evidence.py:361-368`: `has_data AND has_info → "intact"`; partial →
`evidence_insufficient`. `build_opportunity_row` routes through `derive_thesis_from_evidence` whenever
`snapshot is not None` (so the table-fallback at `states.py:552-559` is skipped). The narrative path
runs no `evaluate_policy_b` (Policy B is `ActiveFundSnapshot`-only). **One annotation nit (RD-6a):**
`build_opportunity_row`'s `snapshot` param is typed `ConstituentSnapshot | ActiveFundSnapshot | None`
(`states.py:526`) — it does NOT list `FundLevelSnapshot`, yet `opportunity_cmd.py:930-935` already
passes one in production and the gate handles it. The plan should **widen this annotation to include
`FundLevelSnapshot`** (zero-risk typing fix already implied by production usage) so the narrative
caller passes a `FundLevelSnapshot` cleanly. Doc-impact: spec note only; no CONTEXT.md/ADR change.

**RD-7 — Failure/budget parity with item 001?** A: **Confirmed, UNCHANGED.** Per-fund build
failure → logged, no write → `evidence_insufficient` → `insufficient`; never crashes; budget reuses
`FetchPlan.fund_level_misses` (4 calls each, `opportunity_cmd.py:96-104`) + `_fetch_budget()` +
`FetchBudgetExceeded` raised pre-fetch. **Recommendation (RD-7a):** prefer a **single shared
preflight `FetchPlan(active_fund_misses=Na, fund_level_misses=Np)`** checked once, so a combined run
cannot pass two independent sub-budget checks that jointly exceed budget (AC11 already permits this;
single shared plan is the safer of the two permitted shapes). Doc-impact: spec note only.

**RD-8 — Terminology drift vs CONTEXT.md?** A: Reconciled. The spec's informal "nav snapshot" /
"fund-level NAV snapshot" = a `FundLevelSnapshot` cached under `…/{quarter}/nav/`; "dual-leg gate" =
the fund-level branch of `derive_thesis_from_evidence` applying the canonical **Dual-coverage gate**'s
data+info-leg requirement; "passive fund" = CONTEXT.md's **Passive ETF / tracked index**. Doc-impact:
captured in the new CONTEXT.md narrative-passive terms.
