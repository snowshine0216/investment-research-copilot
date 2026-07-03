# Item 004 — fund-level evidence repair probe (foreign-heavy stale cache)

Run: todos-critical-fixes (2026-07-03). Origin: TODOS.md line 21
("Mixed-fund stale-cache with empty `fund_level_evidence` not force-retried",
item-001 ship adversarial review 2026-05-26). MASTER-SPEC item 004.

**Trigger-condition correction (verified in code):** the TODO proposes
`if fund_level_evidence == () AND _compute_foreign_listed_share(...) >=
FOREIGN_HEAVY_THRESHOLD: force refetch`. The literal `== ()` condition does
NOT cover the TODO's own motivating example ("NAV fetch failed once"):
`_fetch_active_fund_level_evidence` (`src/irc/fundamentals/snapshot.py:477–524`)
appends announcements independently of the NAV result, so a NAV-only failure
yields a **non-empty, information-leg-only** tuple — and Policy B rule 2.5
(`src/irc/opportunity/policy_b.py:283–315`) still emits
`foreign_heavy_fund_level_evidence_missing` because it requires
`has_data AND has_info`. The probe's trigger therefore mirrors rule 2.5's
gap condition exactly (missing data leg OR missing information leg), not
emptiness.

## Goal

When `_fetch_active_fund_level_evidence` degrades (NAV and/or all three
announcement endpoints fail) during an active-fund snapshot build, the
`ActiveFundSnapshot` is cached with a gapped `fund_level_evidence`. On
subsequent runs the cached-serve path
(`_build_rows` → `_maybe_freshness_probe`,
`src/irc/commands/opportunity_cmd.py:266–299`, cached-serve branch
`else: snap_obj = probed` at :910–912) reuses it for up to
`IRC_CACHE_FRESHNESS_DAYS` (default 7): `_active_snapshot_has_required_data_leg_gap`
(:254) inspects only per-constituent data legs, so a mixed CN+HK
foreign-heavy fund whose constituents all carry data legs sails through,
and rule 2.5 re-emits `foreign_heavy_fund_level_evidence_missing` every run
for a week — the row stays unpublishable on stale evidence even though a
4-call refetch would heal it. Since item 002 (dual-leg thesis heuristic,
CONTEXT.md), a gapped `fund_level_evidence` also degrades `thesis_state`
for such funds, raising the cost of the poisoned cache.

Fix: a **fund-level evidence repair probe** on the cached-serve path. When
the cached snapshot is foreign-heavy (rule 2.5 territory) AND its
`fund_level_evidence` lacks a data leg or an information leg, re-run ONLY
the fund-level legs (`_fetch_active_fund_level_evidence`, 4 AkShare calls:
1 NAV + `fund_announcement_{dividend,report,personnel}_em`), merge the
result into the cached snapshot with a pure function — **leg-wise, monotone
per leg** (grill R3): fresh entries win for a leg the refetch produced;
cached entries are retained for a leg it didn't — and re-write the cache
when the evidence improved. Holdings and per-constituent evidence are
untouched (they are healthy by construction on this path — a data-leg gap
or quarter roll already forces a full refetch upstream). The preflight
budget classifier learns a fourth class so the plan stays honest without
re-introducing the ~35× full-refetch over-estimate.

## Acceptance criteria

Each AC is independently verifiable. Test files mirror sources.

- **AC1 (pure gate predicate).** New public pure function
  `foreign_heavy_fund_level_gap(snapshot: ActiveFundSnapshot) -> bool` in
  `src/irc/opportunity/policy_b.py` returns `True` iff
  `_compute_foreign_listed_share(_rank_by_weight(snapshot.constituent_analyses))
  >= FOREIGN_HEAVY_THRESHOLD` AND `snapshot.fund_level_evidence` is missing
  a `citation_kind=="data"` entry OR a `citation_kind=="information"` entry
  — the exact condition under which rule 2.5 emits
  `foreign_heavy_fund_level_evidence_missing` (single source of truth: the
  predicate and rule 2.5 share the module so they cannot drift). Unit tests
  in `tests/opportunity/test_policy_b.py`: foreign-heavy + empty evidence →
  True; foreign-heavy + info-only → True; foreign-heavy + data-only → True
  (the TODO-correction shape); foreign-heavy + both legs → False; CN-heavy
  (<0.50) + empty evidence → False; empty `constituent_analyses` → False
  (share 0.0 — load-bearing for AC8's lockdown fixture).
- **AC2 (pure merge — leg-wise, monotone).** New module
  `src/irc/fundamentals/fund_level_repair.py` (<200 lines) with pure
  `merge_fund_level_evidence(snap: ActiveFundSnapshot,
  evidence: tuple[ThesisEvidence, ...], failures: list[str])
  -> ActiveFundSnapshot` that returns a NEW frozen instance
  (`dataclasses.replace`) where: ~~`fund_level_evidence` is replaced by
  `evidence`~~ **[grill R3 — full replacement can DROP a surviving cached
  leg under the 2026-06-21 throttle pattern (cached info-only + fresh
  data-only would swap legs and oscillate instead of healing); the merge is
  leg-wise]** `fund_level_evidence` is merged **per leg by
  `citation_kind`**: the merged data leg = the fresh `citation_kind=="data"`
  entries when the refetch produced ≥1, else the cached data-kind entries;
  same rule independently for `citation_kind=="information"`; merged tuple
  ordered data-leg entries first then information-leg entries (the producer
  order of `_fetch_active_fund_level_evidence` — NAV then announcements).
  Leg presence is therefore monotone non-decreasing across a repair.
  ~~`fund_level_failure_reasons` has the stale
  `fund_nav_unavailable:{fund_id}` / `fund_announcements_unavailable:{fund_id}`
  entries stripped and the fresh `failures` appended~~ **[grill R3 —
  appending a fresh leg-failure while the merged snapshot retains that
  cached leg would break the producer invariant]**
  `fund_level_failure_reasons` has BOTH
  `fund_nav_unavailable:{fund_id}` and
  `fund_announcements_unavailable:{fund_id}` stripped, then re-appends
  `fund_nav_unavailable:{fund_id}` iff the MERGED evidence has no data leg
  and `fund_announcements_unavailable:{fund_id}` iff it has no information
  leg — preserving `_build_active_fund_snapshot`'s own invariant
  (leg-failure string present ⟺ leg absent in evidence;
  `snapshot.py:505–506, :522–523`). Unrelated reasons — e.g.
  `holdings_quarter_parse_failed:{fund_id}` — preserved in order. ALL
  other fields byte-identical, **including `cache_probed_at`** (the repair
  is orthogonal to holdings-quarter freshness — it must not extend or
  shorten the `_is_stale` window). Mirror tests in
  `tests/fundamentals/test_fund_level_repair.py`; input snapshot asserted
  unmutated. Required cases: cached info-only + fresh data-only → merged
  carries BOTH legs and zero leg-failure strings (the heal-under-throttle
  case — the TODO's own motivating shape); cached data-only + fresh
  info-only → both legs; cached empty + fresh both → fresh verbatim; fresh
  empty with both fetch legs failed → merged `fund_level_evidence` byte-
  identical to cached (so AC4 writes nothing).
- **AC3 (fail-safe refetch wrapper).** Same module: thin I/O wrapper
  `refetch_fund_level_evidence(snap: ActiveFundSnapshot) ->
  ActiveFundSnapshot` calls `_fetch_active_fund_level_evidence(snap.fund_id)`
  and merges via AC2. Any `Exception` from the fetch → return `snap`
  unchanged (a repair attempt must NEVER crash a row build that previously
  served fine from cache; `fetch_fund_announcements` documents
  "Never raises" but the wrapper does not rely on that). Test: raising
  fetch stub → original snapshot returned, no exception escapes.
- **AC4 (call-site wiring, effects at the edge).** New helper
  `_maybe_fund_level_evidence_repair(snap: ActiveFundSnapshot, *,
  root: Path) -> ActiveFundSnapshot` in
  `src/irc/commands/opportunity_cmd.py`, invoked in `_build_rows` on the
  cached-serve branch ONLY (the `else: snap_obj = probed` arm after
  `_maybe_freshness_probe` returns `refresh=False`, currently :910–912),
  BEFORE `_write_state_complete`. The helper receives the **post-probe
  served snapshot** (`probed`), NOT the pre-probe `cached` (grill R4): when
  the probe advanced `cache_probed_at` and wrote the cache, merging into
  the pre-probe snapshot would roll the probe date back on the second
  write and re-trigger probes every run. Behavior: when
  `foreign_heavy_fund_level_gap(snap)` is False → returns `snap` with zero
  fetch calls and zero writes; when True → `refetch_fund_level_evidence`,
  then `write_active_fund_cache(merged, root)` ONLY IF
  `merged.fund_level_evidence != snap.fund_level_evidence` AND
  `merged.source_report_quarter` is non-empty (P0-5 pattern; the write
  reuses `write_active_fund_cache`, so disclosure-quarter keying and the
  `.tmp.{pid} → replace` atomic pattern are inherited — the merged snapshot
  keeps `source_report_quarter` byte-identical, so it lands on the SAME
  quarter path; a probe-then-repair run performs two atomic writes to that
  path, which is benign); cache-write
  failure → `cache_write_failed:{fund_id}:{type}` on stderr and the merged
  snapshot is still served in-memory (existing degrade pattern from
  `_maybe_freshness_probe` :290–298). The repair does NOT run on: the
  `completed_ids` resume path (:851–852 — the fund already completed this
  run), the `rebuild_fundamentals` path, the cache-miss path, or the
  `refresh=True` full-refetch path (all of these rebuild fund-level legs
  via `build_snapshot` anyway). Tests in
  `tests/commands/test_opportunity_cmd.py`.
- **AC5 (budget classifier, 4-tuple).** `_classify_active_fund_scores`
  (:595) returns `(misses, stale_full, stale_probe_only, fund_level_repair)`.
  A cached fund counts toward `fund_level_repair` iff it is NOT a miss,
  NOT `stale_full` (data-leg gap wins — full refetch already includes the
  fund-level legs; no double count), AND
  `foreign_heavy_fund_level_gap(cached)` is True. A fund MAY count toward
  BOTH `stale_probe_only` AND `fund_level_repair` (date-stale + gapped ⇒
  runtime fires probe 1 call + repair 4 calls = 5 — the plan matches the
  expected runtime path). All unpack/patch sites updated (grep-verified
  exhaustive list): `opportunity_cmd.py:776`;
  `tests/commands/test_opportunity_cmd.py:675, :719` (3-tuple unpacks) and
  `:930` (`return_value=(0, 0, 0)` stub → 4-tuple). **[grill R1 — list
  independently re-verified 2026-07-03 by grep over `src/`, `tests/`,
  `evals/`, `scripts/`: exactly these 4 sites and nothing else; in
  particular `tests/opportunity/` and `tests/narrative/` carry ZERO
  references (the repo-memory lambda-break precedent does not recur here),
  and `fund_eval_cmd.py` / `narrative_autobuild.py` never call the
  classifier. The two positional `FetchPlan(5, 0, 0, 0, 10)` constructions
  (`tests/commands/test_opportunity_cmd.py:480`,
  `tests/commands/test_opportunity_cmd_acceptance.py:100`) bind only the
  first 5 params and are unaffected by the new defaulted field.]**
  New classifier tests:
  fresh foreign-heavy gapped cache → `(0, 0, 0, 1)`; same but data-leg gap
  too → `(0, 1, 0, 0)`; date-stale + gapped → `(0, 0, 1, 1)`.
- **AC6 (FetchPlan accounting — no 35× regression).** `FetchPlan` (:90)
  gains `active_fund_fund_level_repair: int = 0`; `total_calls()` adds
  `self.active_fund_fund_level_repair * 4` (the constant mirrors
  `per_fund_level = 4` — 1 NAV + 3 announcement endpoints, the same "+4"
  term inside `per_active`); the `FetchBudgetExceeded` message (:119–131)
  includes the new field. Tests: a repair-only fund costs exactly 4 (NOT
  `1 + top_n*3 + 4 = 35`); repair + probe-only costs 5; default plan
  (field omitted) is byte-identical to today (`total_calls` unchanged for
  all existing fixtures). Doc-sync: correct the stale "Per-fund call
  delta = 2 AkShare calls" claim in `_fetch_active_fund_level_evidence`'s
  docstring (`snapshot.py:486`) to 4, matching FetchPlan.
- **AC7 (end-to-end heal).** Integration test in
  `tests/integration/test_publishable_set_lockdown.py`: pre-write a
  fresh-by-date (`cache_probed_at = today`) foreign-heavy cache — ≥0.50
  HK-listed weight, every constituent carrying a data leg (so
  `_active_snapshot_has_required_data_leg_gap` is False), and
  `fund_level_evidence=()` — with NAV + announcement dispatch entries
  seeded to succeed. `run_opportunity` then: (a) fires the fund-level
  NAV/announcement calls for that fund and ZERO constituent-evidence calls
  (`stock_financial_abstract` / `stock_research_report_em` /
  `stock_news_em`) and ZERO `fund_portfolio_hold_em` calls (fresh cache →
  no quarter probe, no full rebuild); (b) produces a Policy-B verdict with
  `fired_rule == "2.5"` and `gap_codes == ()` for the fund (no
  `foreign_heavy_fund_level_evidence_missing` in `rejections.json` /
  `evidence_gaps`); (c) the on-disk cache file re-loads with the repaired
  `fund_level_evidence` (both legs) and `cache_probed_at` unchanged.
- **AC8 (no-repair regression locks).** Existing lockdown tests pass
  unmodified: `test_snapshot_cache_within_window_zero_akshare_calls`
  (AC15 — its fixture has empty `constituent_analyses` ⇒ foreign share 0.0
  ⇒ predicate False ⇒ still zero calls),
  `test_snapshot_cache_expired_probe_same_quarter_reuses` (AC16 — ~~CN-only
  constituent ⇒ predicate False~~ **[grill R6 — wrong rationale, verified
  in code: the `_prewrite_active_fund_cache` fixture
  (`test_publishable_set_lockdown.py:596–617`) writes
  `constituent_analyses=()`; the CN stock 600519 appears only in the PROBE
  holdings frame, which never lands on the cached snapshot]** empty
  `constituent_analyses` fixture ⇒ foreign share 0.0 ⇒ predicate False ⇒
  probe-only, exactly 1 `fund_portfolio_hold_em` call), and
  `test_snapshot_cache_probe_failure_fail_closed_refetch` (AC17). All four
  existing `_maybe_freshness_probe` unit tests
  (`tests/commands/test_opportunity_cmd.py:565–652`) pass unmodified —
  the probe's signature and semantics are untouched. New negative test:
  a fresh CN-heavy cache with `fund_level_evidence=()` (below threshold)
  triggers NO repair fetch (widening to non-foreign funds is explicitly
  deferred — see Non-goals).
- **AC9 (repeat-failure bound).** When the repair fetch yields no
  improvement (evidence still gapped): no cache write occurs (content
  unchanged), the run proceeds serving the cached snapshot (rule 2.5 gap
  re-emitted honestly), and a subsequent `_build_rows` invocation fires the
  repair again — the retry is unbounded across runs BY DESIGN (no backoff
  marker; see resolved Q5) and bounded within a run to one attempt per
  fund (snapshot_cache memoisation at :846/:913 already guarantees one
  `snap_obj` resolution per `target.key`). Test: two sequential
  `_maybe_fund_level_evidence_repair` calls with a failing fetch stub →
  fetch attempted each time, zero cache writes, snapshot served both times.
- **AC10 (test sweep + lint).** Per the signature-change test-scope rule,
  run every dir exercising the touched functions: `tests/opportunity/`
  (policy_b), `tests/fundamentals/` (new module + snapshot docstring),
  `tests/integration/test_publishable_set_lockdown.py`, and — per-file,
  the whole dir hangs — `tests/commands/test_opportunity_cmd.py` +
  `tests/commands/test_opportunity_cmd_acceptance.py`.
  `uv run ruff check src tests` clean. Any failing id replayed on main
  first to diff-scope against the 24 known pre-existing failures.
- **AC11 (bookkeeping + doc sync).** CHANGELOG `[Unreleased]` entry (no
  VERSION bump). TODOS.md line 21 marked `[x]` with
  `**Resolved 2026-07-03:**` annotation naming the predicate, the repair
  module, the trigger-condition correction (leg-gap, not `== ()`), and the
  test names. ~~CONTEXT.md "Foreign-heavy fund (rule 2.5 short-circuit)"
  entry gains one sentence documenting the cached-path repair probe
  (leg-gap trigger, 4-call cost, no backoff); ADR 0003 §7 gains a matching
  addendum sentence. No new CONTEXT term is minted — the probe is an
  operational repair inside the existing rule-2.5 vocabulary.~~
  **[grill R7 — the repair IS a third cached-active-fund fetch class
  (beside full refetch and freshness probe) with its own budget class and
  merge semantics; "operational detail" undersold it]** CONTEXT.md changes
  were applied AT GRILL TIME (2026-07-03): a new **"Fund-level evidence
  repair (repair probe)"** term (leg-gap trigger, 4-call cost, leg-wise
  monotone merge, leg-failure ⟺ leg-absence invariant, no backoff, own
  `FetchPlan` class, `cache_probed_at` untouched) plus a cross-reference
  sentence in the "Foreign-heavy fund (rule 2.5 short-circuit)" entry —
  implementation must VERIFY the as-built behavior matches the entry and
  amend it if any detail shifts. ADR 0003 §7 gains an addendum PARAGRAPH
  (not one sentence) at implementation time: repair trigger + 4-call cost +
  leg-wise merge + no-backoff rationale + `active_fund_fund_level_repair`
  budget class, AND corrects §7's stale "Fetch budget impact" claim
  ("2 additional AkShare calls … adds ~100 calls" → 4 calls
  (1 NAV + 3 announcement endpoints) … ~200 — the code's
  `per_active` "+4" term and `_FUND_ANN_TOPIC_FNS` already prove 4). No
  standalone ADR: amendment-in-place is ADR 0003's own locked structural
  choice (§7 Alternative B rejection).

## Non-goals

- **No Policy B rule change.** `evaluate_policy_b`, the six-rule
  precedence, rule 2.5's gap code and decision-rule strings are untouched;
  the new predicate is additive and read-only.
- **No citation-contract change.** `ThesisEvidence` shape, 16-hex
  `citation_id`, `[ref:...]` marker, scopes, `citation_kind` literals
  unchanged (ADR 0001). The repaired evidence has the exact shape
  `_fetch_active_fund_level_evidence` already produces.
- **No new fetch endpoints.** The repair reuses
  `fetch_fund_nav_report` + `fetch_fund_announcements` via the existing
  `_fetch_active_fund_level_evidence`; no new AkShare surface.
- **No widening beyond foreign-heavy funds.** Item 002's dual-leg thesis
  heuristic gives `fund_level_evidence` value for CN-heavy active funds
  too (union check), but those funds normally satisfy the union via
  constituent broker/news legs; extending the repair trigger to all active
  funds with a gapped fund-level surface is a SEPARATE decision, recorded
  here as deferred (locked by AC8's negative test).
- **No backoff marker / schema change.** No new field on
  `ActiveFundSnapshot` (avoids cache-migration churn); loop prevention is
  cost-bounding, not state (resolved Q5).
- **No `_maybe_freshness_probe` signature or semantics change** — the
  quarter-freshness probe and the evidence repair remain two separate,
  composable concerns (resolved Q2).
- **No narrative-path change.** `irc narrative --analyze` builds fresh
  snapshots and is Policy-B-free (CONTEXT.md "Narrative path is
  Policy-B-free"); it never serves this cache path.
- **No `irc eval-funds` change** (grill R8). `fund_eval_cmd.py` reads
  cached snapshots read-only via `load_active_fund_cache`
  (`fund_eval_cmd.py:117`) and is Policy-B-free; the repair never runs
  there. It benefits indirectly: a repair executed by `irc opportunity`
  heals the shared on-disk cache that eval-funds subsequently loads.
- **No `--rebuild-fundamentals` / miss-path change** — full builds already
  fetch the fund-level legs unconditionally.

## Constraints

- **TDD.** Failing test first for each AC (red → green → refactor); tests
  mirror sources (`policy_b.py` → `tests/opportunity/test_policy_b.py`,
  `fund_level_repair.py` → `tests/fundamentals/test_fund_level_repair.py`,
  `opportunity_cmd.py` → `tests/commands/test_opportunity_cmd.py`).
- **Purity / effects at edges.** `foreign_heavy_fund_level_gap` and
  `merge_fund_level_evidence` are pure (no I/O, no mutation, new frozen
  instances); all fetch + cache-write effects live in
  `refetch_fund_level_evidence` and `_maybe_fund_level_evidence_repair`
  (thin wrappers at the command edge).
- **Size budget.** New module <200 lines; each new function <20 lines
  ideal; `opportunity_cmd.py` (1573 lines) and `snapshot.py` (706 lines)
  are already over budget — grow them only by the ~10-line call-site
  helper and a docstring fix respectively; the predicate adds ~15 lines to
  `policy_b.py` (381 lines) because co-locating with rule 2.5 outweighs
  the size ideal (anti-drift).
- **No VERSION bump**; accumulate under CHANGELOG `[Unreleased]`
  (versioning convention).
- **TODOS.md line-21 annotation** per MASTER-SPEC
  (`**Resolved 2026-07-03:**` format).
- **Budget-trap guard.** The plan cost for a repair-only fund is 4, never
  the 35-call `per_active` term — locked by AC6. Classifier and runtime
  must agree on the trigger predicate (both call
  `foreign_heavy_fund_level_gap`) so `FetchPlan.total_calls` cannot drift
  from actual calls — **modulo the PRE-EXISTING quarter-roll under-count**
  (grill R2): a `stale_probe_only` fund whose probe discovers a rolled
  quarter goes `refresh=True` → 35 actual calls against 1 planned, today
  and unchanged by this item. A probe+repair-classified fund on that path
  costs 35, not 5+35 — the repair is skipped on the `refresh=True` arm
  (AC4), so the new class never compounds the existing under-count.
- **Known-failure diff-scoping.** Full pytest is NOT green on main (24
  pre-existing failures); replay any failing id on main before assuming a
  regression. `tests/commands/` runs per-file only (whole-dir hangs).

## Open questions resolved during brainstorming

- **Q1 — trigger: `== ()` (TODO literal) vs rule-2.5 leg mirror?**
  Leg mirror (missing data leg OR info leg). Grounded: rule 2.5 fires the
  gap on `not (has_data and has_info)` (`policy_b.py:300–315`), and the
  TODO's own motivating failure (NAV-only outage) produces a non-empty
  info-only tuple that `== ()` would never repair. The predicate lives in
  `policy_b.py` next to rule 2.5 so the two conditions are one definition.
- **Q2 — where does the check belong?** A new repair step at the single
  cached-serve call site in `_build_rows` (the `else: snap_obj = probed`
  arm), NOT inside `_maybe_freshness_probe` and NOT by widening
  `_active_snapshot_has_required_data_leg_gap`. Rationale: (a) the gap
  detector's `True` means "full 35-call refetch + `stale_full` budget
  class" — an 8.75× over-fetch for a 4-call problem, re-approaching the
  ~35× over-estimate trap class; (b) `_maybe_freshness_probe` has THREE
  `(snap, False)` return paths (fresh early-return :279, probe-success
  :299, cache-write-degrade :298) — wrapping the one call site covers all
  of them with a single insertion point and keeps quarter-freshness and
  evidence-repair as separate concerns; (c) effects stay at the command
  edge.
- **Q3 — refetch scope: fund-level legs only vs whole snapshot?**
  Fund-level legs only (4 calls). On the repair path the constituent side
  is healthy by construction (`refresh=False` ⇒ no data-leg gap, quarter
  current or un-probed-but-fresh); a full `build_snapshot` costs 35 calls
  and re-fetches evidence that cannot have changed within the disclosure
  quarter. Cost accounting: new `FetchPlan.active_fund_fund_level_repair`
  field at ×4 (mirrors `per_fund_level`), NOT reuse of `stale_full`
  (35×) or `stale_probe_only` (1× — would under-count by 4× and break the
  plan/runtime agreement). The classifier change is a 3→4 tuple signature
  change with 4 grep-verified call/patch sites (AC5).
- **Q4 — quarter-roll interaction.** None by design: the repair runs only
  after `_maybe_freshness_probe` returned `refresh=False`, so quarter
  rolls (and date-stale probes) are already resolved upstream; the repair
  never touches `cache_probed_at` (AC2), so it cannot mask a stale quarter
  or extend the freshness window.
- **Q5 — loop prevention on repeated failure.** NO backoff; the probe
  re-fires every run until healed, bounded at 4 calls/run/fund and only
  for foreign-heavy funds (single-digit population in the discovered
  watchlist). Grounded precedent: `_active_snapshot_has_required_data_leg_gap`
  already forces a 35-call full refetch EVERY run until its gap heals —
  the accepted repair-retry pattern — and 4 < 35. A backoff marker would
  need a new persisted snapshot field (cache migration, clock-skew edge
  cases) for negligible savings; the budget classifier counting the class
  honestly (AC5/AC6) is the correct pressure valve. Within-run the
  attempt count is 1 (snapshot_cache memoisation).
- **Q6 — cache-write policy on partial improvement.** Write iff
  `fund_level_evidence` changed (and `source_report_quarter` non-empty,
  P0-5). A partial heal (e.g. NAV recovered, announcements still down) is
  persisted — honest audit trail, better evidence for item 002's union —
  and the still-gapped surface re-triggers the probe next run. A no-change
  result writes nothing (idempotent, no pointless disk churn). **[grill R3
  amendment: with the leg-wise merge, the partial heal is strictly
  stronger — a fresh leg is ADDED next to the surviving cached leg instead
  of replacing the whole tuple, so under the throttle pattern (cached
  info-only, fresh data-only) the fund heals to BOTH legs in one run
  rather than oscillating between single-leg states; "changed" then
  coincides with "improved" because repair fires only on gapped caches
  (at most one cached leg) and legs are monotone under the merge.]**
- **Q7 — scope: all gapped active funds or foreign-heavy only?**
  Foreign-heavy only (the TODO's condition; conservative). For CN-heavy
  funds the fund-level legs are advisory (rule 2.5 never fires; the
  dual-leg thesis union is normally satisfied by constituent legs), so
  the marginal value is low and the blast radius of widening (every
  active fund with a transient announcement outage re-fetching weekly)
  is a separate cost/benefit decision. Locked by AC8's negative test;
  recorded in Non-goals.
- **Q8 — module placement for the merge/wrapper.** New
  `src/irc/fundamentals/fund_level_repair.py` rather than growing
  `snapshot.py` (706 lines) — respects the <200-line budget, gives the
  pure merge its own mirror test file, and keeps `snapshot.py` build-only.
  The wrapper imports the private `_fetch_active_fund_level_evidence`
  from its sibling (same-package private import; precedent:
  `opportunity_cmd.py` imports `_FUND_LEVEL_KINDS`,
  `_classify_rejection_reason`).
- **Q9 — item 002 interaction (value confirmation).** A successful repair
  restores legs to `fund_level_evidence`, which (a) lets rule 2.5 publish
  the row (`_stamp_fund_level_evidence_from_verdict` then satisfies the
  dual-coverage gate), and (b) feeds the dual-leg thesis heuristic's
  presence-only union for funds with non-empty constituent evidence —
  a data-only-constituent foreign-heavy fund can regain `intact` instead
  of `evidence_insufficient`. Both are downstream effects of healed data,
  requiring zero changes in `thesis_evidence.py` or the stamps (verified:
  both read `snapshot.fund_level_evidence` directly). **[grill R5 —
  ordering verified and DESIRED: the repair runs at `snap_obj` resolution
  in `_build_rows` (:910–912), strictly BEFORE `build_opportunity_row`
  (:935) invokes `evaluate_policy_b` and `derive_thesis_from_evidence` on
  that snapshot, so a healed fund can flip `evidence_insufficient →
  intact` (and gapped → publishable) WITHIN the same run — a single-run
  heal, not a next-run heal. ADR 0003 §8's empty-flattened guard still
  holds independently: a repair never adds constituent evidence, so an
  all-pure-failure fund stays `evidence_insufficient` even with both
  fund-level legs restored.]**

## Resolved decisions (grill 2026-07-03)

All spec code-location, call-count, and fixture claims were re-verified in
source (not trusted from the spec's own text) before these resolutions.

- **R1 — 4-tuple call/patch-site list is COMPLETE.** Grep over `src/`,
  `tests/`, `evals/`, `scripts/` finds exactly the 4 sites AC5 lists
  (`opportunity_cmd.py:776`; `test_opportunity_cmd.py:675`, `:719`,
  `:930`). `tests/opportunity/` and `tests/narrative/` have zero
  references; `fund_eval_cmd.py` and `narrative_autobuild.py` never call
  the classifier. Positional `FetchPlan(5, 0, 0, 0, 10)` constructions
  (2 sites) bind only the first 5 params — safe with the new defaulted
  field appended.
- **R2 — Budget math CONFIRMED at 4; plan/runtime agreement qualified.**
  `_fetch_active_fund_level_evidence` performs exactly 4 `_ak_call`s:
  1 × `fund_open_fund_info_em` (NAV, `akshare_fundamentals.py:577`) +
  3 × `_FUND_ANN_TOPIC_FNS` endpoints (`:619–623`, `:682–686`).
  Probe+repair = 5 is the intended charge for the date-stale + gapped
  fund. The only plan/actual divergence is the PRE-EXISTING quarter-roll
  under-count on the probe path (1 planned vs 35 actual), which the
  repair class never compounds (repair skipped on `refresh=True`).
  Constraint "Budget-trap guard" amended for honesty.
- **R3 — Merge semantics CORRECTED: full replacement → leg-wise monotone
  merge.** The spec's original "replace `fund_level_evidence` by
  `evidence`" fails its own motivating scenario: the TODO's NAV-only
  outage leaves an info-only cache; under the 2026-06-21 EastMoney
  throttle pattern the repair plausibly returns data-only (NAV recovered,
  3 announcement endpoints throttled), and full replacement would DROP
  the surviving cached info leg — swapping legs and oscillating forever
  instead of healing. Leg-wise merge (fresh leg wins when produced,
  cached leg retained when not) heals to both legs in one run. Retaining
  a cached leg is no staler than the cached-serve path itself (the whole
  snapshot is being reused inside `IRC_CACHE_FRESHNESS_DAYS`).
  Failure-reason handling re-pinned to the producer invariant:
  leg-failure string present ⟺ leg absent in MERGED evidence
  (`snapshot.py:505–506, :522–523` establish it at build time). AC2, the
  Goal, and Q6 amended; new merge test cases enumerated in AC2.
- **R4 — Cache invariants INHERITED + post-probe input pinned.** The
  repair writes via the existing `write_active_fund_cache`
  (`snapshot_cache.py:224–233`): disclosure-quarter keying and the
  `.tmp.{pid} → replace` atomic pattern come for free; the merge keeps
  `source_report_quarter` byte-identical so the write targets the SAME
  quarter path. AC4 now pins that the helper merges into the POST-probe
  snapshot (`probed`) — merging into pre-probe `cached` would roll back
  the probe-advanced `cache_probed_at` on the second write and re-trigger
  probes every run. Probe-then-repair performing two atomic writes to one
  path is benign and accepted (fusing them would re-entangle the two
  concerns Q2 separated).
- **R5 — Item 002 ordering verified, single-run heal INTENDED.** Repair
  at `snap_obj` resolution precedes `evaluate_policy_b` +
  `derive_thesis_from_evidence` inside `build_opportunity_row`; §8's
  empty-flattened guard is unaffected (repair never adds constituent
  evidence). Recorded in Q9.
- **R6 — AC16 fixture rationale corrected.** The lockdown fixture
  `_prewrite_active_fund_cache` writes `constituent_analyses=()` — the
  predicate is False via the empty guard (share 0.0), NOT via a CN-only
  constituent (600519 exists only in the probe's holdings frame, which
  never lands on the cached snapshot). Matters because an implementer
  misled by the old rationale could "fix" the test instead of the
  predicate when empty-snapshot behavior misbehaves.
- **R7 — Terminology: "Fund-level evidence repair" IS a domain term.**
  It is a third cached-active-fund fetch class beside the full refetch
  and the fail-closed freshness probe, with its own budget class, trigger
  predicate, and merge semantics. CONTEXT.md entry added at grill time
  (plus a cross-reference in the "Foreign-heavy fund" entry); AC11's "no
  new term" claim struck. No standalone ADR (fails the
  amendment-in-place bar ADR 0003 §7 itself locked); instead AC11's ADR
  0003 §7 addendum is widened to a paragraph and must also fix §7's
  stale "2 additional AkShare calls (~100)" claim (actual: 4, ~200).
- **R8 — `irc eval-funds` explicitly out of scope.** Read-only cache
  consumer, Policy-B-free; benefits indirectly once `irc opportunity`
  repairs the shared cache. Added to Non-goals.
- **R9 — Q2's three-return-path coverage re-verified.** The single
  insertion point after `_maybe_freshness_probe` covers fresh
  early-return (:278–279), probe-success (:299), and cache-write-degrade
  (:298). On the degrade path (disk failing) the repair's own cache write
  likely fails too → AC4's stderr-and-serve-in-memory degrade applies;
  no special-casing needed.
- **R10 — Verdict basis.** No unresolvable contradiction found between
  the spec and ADR 0001/0002/0003, CONTEXT.md, or the code. Two
  substantive corrections (R3 merge semantics, R6 fixture rationale) and
  one qualification (R2) were resolvable in place; the plan phase should
  treat AC2's leg-wise merge and AC4's post-probe input as the binding
  shapes.
