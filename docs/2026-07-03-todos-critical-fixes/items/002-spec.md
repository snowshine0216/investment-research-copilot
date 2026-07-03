# Item 002 — `ActiveFundSnapshot` dual-leg thesis gate

Run: todos-critical-fixes (2026-07-03). Origin: TODOS.md line ~51
("`ActiveFundSnapshot` thesis path lacks the dual-leg coverage check",
eval-funds ship adversarial review 2026-06-01). MASTER-SPEC item 002.

**Location correction:** TODOS.md and MASTER-SPEC name
`src/irc/opportunity/states.py::derive_thesis_from_evidence`; the function
actually lives in `src/irc/opportunity/thesis_evidence.py` (lines 330–400;
`states.py` merely imports it). The active-fund branch is lines 375–393.

## Goal

`derive_thesis_from_evidence` (`src/irc/opportunity/thesis_evidence.py`)
sets `thesis_state="intact"` for an `ActiveFundSnapshot` whenever the
flattened constituent evidence is non-empty — without requiring both a
**data leg** (≥1 `ThesisEvidence` with `citation_kind=="data"`) and an
**information leg** (≥1 with `citation_kind=="information"`), the dual-leg
heuristic the `FundLevelSnapshot` branch already applies (lines 361–373).
Data-only (e.g. filing-only) evidence therefore reaches `intact`, and with
cheap valuation + cold heat + acceptable quality composes to `core_dca` —
false confidence surfaced prominently by `irc eval-funds` and
`irc narrative --analyze`, the two Policy-B-free consumers of
`build_opportunity_row`. The fix extends the dual-leg check to the
`ActiveFundSnapshot` branch: ~~`intact` requires ≥1 data-leg AND ≥1
information-leg entry across the union of the flattened constituent
evidence and `snapshot.fund_level_evidence`; a single-leg evidence surface
yields `evidence_insufficient`~~ **[grill R1 — as stated this is
inaccurate for one reachable published shape: empty flattened evidence +
dual-leg `fund_level_evidence` has both legs "across the union" yet must
NOT become `intact`]** — corrected: **when the flattened constituent
evidence is non-empty**, `intact` requires ≥1 data-leg AND ≥1
information-leg entry across the union of the flattened constituent
evidence and `snapshot.fund_level_evidence`; a single-leg union yields
`evidence_insufficient` (the same value the `FundLevelSnapshot`
branch yields on a missing leg). The existing **empty-flattened guard runs
FIRST and is load-bearing** (see R1): a rule-2.5-publishable fund whose
top-N constituents are all pure-failure (reachable — ADR 0003 §7
2026-06-04 reconciliation) has empty flattened evidence but dual-leg
`fund_level_evidence`; a naive union-first check would flip that
*published* row `evidence_insufficient → intact`. The returned evidence
tuple, gaps slot, and analyses slot are byte-identical to today — only
`(state, reason)` may change, and (provably) never for a
Policy-B-publishable row.

## Acceptance criteria

Each AC is independently verifiable; tests live in
`tests/opportunity/test_thesis_evidence.py` unless noted.

- **AC1 (data-only → insufficient).** `derive_thesis_from_evidence` with an
  `ActiveFundSnapshot` whose flattened constituent evidence is non-empty and
  all `citation_kind=="data"` (e.g. one filing), and
  `fund_level_evidence=()`, returns `thesis_state == "evidence_insufficient"`
  (not `"intact"`).
- **AC2 (info-only → insufficient).** Symmetrically, all
  `citation_kind=="information"` (e.g. one broker report) with
  `fund_level_evidence=()` returns `"evidence_insufficient"`.
- **AC3 (constituent dual-leg → intact, unchanged).** Flattened evidence
  carrying ≥1 `"data"` AND ≥1 `"information"` entry returns `"intact"` with
  the existing reason literal
  `f"主动基金 {len(analyses)} 个核心持仓的成分股证据已收集。"` — byte-identical
  to today.
- **AC4 (fund-level leg satisfies the gate).** Data-only flattened
  constituent evidence PLUS `fund_level_evidence` carrying an
  `citation_kind=="information"` entry (announcement shape:
  `scope="instrument"`, `owner_instrument_id=fund_id`) returns `"intact"`;
  the returned evidence tuple still equals `_flatten_analyses(analyses)`
  (fund_level_evidence is NOT merged into the return — that remains
  `_stamp_fund_level_evidence_from_verdict`'s job,
  `opportunity_cmd.py:1046`). Mirror test for the data-leg direction
  (info-only constituent evidence + fund-level NAV `citation_kind=="data"`
  → `"intact"`).
- **AC5 (empty-evidence path unchanged — TWO fixtures).** Empty flattened
  evidence still returns `"evidence_insufficient"` with the existing reason
  `"主动基金未能收集到任何成分股证据。"` (regression lock), **in BOTH of**:
  (a) `fund_level_evidence=()` (the plain empty case), AND
  (b) **`fund_level_evidence` carrying BOTH legs** (NAV `"data"` +
  announcement `"information"`) — the rule-2.5-publishable all-pure-failure
  shape. Fixture (b) is load-bearing: it pins that the empty-flattened
  guard short-circuits BEFORE the union leg check, which is what makes the
  AC10 publishable-invariance claim true (grill R1; ADR 0003 §8 property 3).
  A naive "union has both legs → intact" implementation passes (a) but
  fails (b). Note: a non-empty
  evidence set always has ≥1 leg (`citation_kind` is validated to the
  two-literal set in `ThesisEvidence.__post_init__`), so "both legs missing
  with non-empty evidence" is unreachable.
- **AC6 (missing-leg reason literals).** The single-leg outcome uses exactly
  these deterministic reason strings:
  - missing data leg: `"主动基金证据缺少数据腿（成分股财报），长期逻辑暂不背书。"`
  - missing information leg: `"主动基金证据缺少信息腿（券商/新闻/公告），长期逻辑暂不背书。"`
  No new `ThesisState` literal is introduced (the lockdown AC4 set
  `{"intact","under_pressure","falsified","evidence_insufficient"}` is
  unchanged).
- **AC7 (gaps slot unchanged).** The active branch's gaps return slot is
  byte-identical for all inputs: `()` or `("top_holdings_broker_thin",)`
  (advisory) exactly as today. No new gap code is emitted — the H3 partition
  predicate (`evidence_gaps == ()`) sees identical inputs.
- **AC8 (evidence/analyses slots unchanged).** For every input, slots 3
  (evidence) and 5 (analyses) of the 5-tuple are byte-identical to the
  current implementation; the Q-J flatten ordering test
  (`test_active_fund_thesis_evidence_flatten_ordering`) passes unmodified.
- **AC9 (eval-funds surface).** In `tests/opportunity/test_fund_eval.py`:
  `evaluate_fund` (`src/irc/opportunity/fund_eval.py`) with the existing
  `_cheap_cold_input` shape and a **data-only** snapshot (filing-only
  constituent evidence, `fund_level_evidence=()`) returns
  `opportunity_state == "small_watch"` and `core_dca is False` — the bug's
  observable `core_dca` false-positive is gone. The existing dual-leg test
  `test_evaluate_fund_core_dca_when_cheap_cold_intact_acceptable` passes
  unmodified.
- **AC10 (Policy-B-publishable invariance).** No snapshot shape that
  `evaluate_policy_b` publishes changes `thesis_state`: a rules-3+4-passing
  shape has both legs in flattened evidence (AC3); a rule-2.5-passing shape
  ~~has both legs in `fund_level_evidence` (AC4)~~ **[grill R1 — AC4 alone
  is incomplete: it covers only rule-2.5 rows with non-empty constituent
  evidence]** — has both legs in `fund_level_evidence` and splits into two
  sub-cases: non-empty constituent evidence → `intact` via the union (AC4);
  empty constituent evidence (all top-N pure-failure) → stays
  `evidence_insufficient` via the empty-first guard (AC5 fixture (b)), which
  is unchanged from today. Assert via the AC3/AC4/AC5(b)
  fixtures; the integration lockdown
  (`tests/integration/test_publishable_set_lockdown.py`) passes unmodified.
- **AC11 (other branches untouched).** `FundLevelSnapshot`, legacy
  `ConstituentSnapshot`, and theme-report paths are byte-identical: all
  existing tests in `tests/opportunity/test_thesis_evidence.py`,
  `test_thesis_relevance_gate.py`, and `test_top_holdings_broker_thin.py`
  pass unmodified.
- **AC12 (caller test sweep).** Per the signature-change test-scope rule
  (signature is unchanged but behavior-consumers must be swept): run
  `tests/opportunity/`, `tests/narrative/`,
  `tests/integration/test_publishable_set_lockdown.py`, and — per-file, the
  whole dir hangs — `tests/commands/test_opportunity_cmd.py` +
  `tests/commands/test_opportunity_cmd_acceptance.py`. `ruff check src
  tests` clean. (Survey result: no existing test asserts `intact` on a
  data-only active fixture — the data-only fixtures in
  `test_thesis_evidence.py:21`/`test_states.py:755` assert only
  evidence/analyses/fetch-type slots; expected test updates: none, only
  additions. If a stray lock surfaces, updating it is expected — name it in
  the PR.)
- **AC13 (bookkeeping).** CHANGELOG `[Unreleased]` entry (no VERSION bump);
  TODOS.md line-~51 entry annotated `**Resolved 2026-07-03:**` with the
  standard as-built note.

## Non-goals

- **No Policy B change.** `evaluate_policy_b`, its six rules, rule 2.5, and
  publishability semantics are untouched; `thesis_state` remains set ONLY by
  `derive_thesis_from_evidence` (ADR 0003; CONTEXT.md `PolicyBVerdict`).
- **No citation-contract change.** `ThesisEvidence` preimage, 16-hex
  `citation_id`, `[ref:...]` marker, scopes, and `citation_kind` literals
  unchanged (ADR 0001).
- **No `FundLevelSnapshot`-branch behavior change** (lines 348–373 stay
  byte-identical in outputs; a pure, output-identical extraction of a shared
  leg-check helper is permitted but optional).
- **No merging of `fund_level_evidence` into the returned evidence tuple**
  (stays the rule-2.5 stamp's job — avoids double-append and any SAME-3 /
  citation-set drift).
- **No new evidence_gaps codes** (H3 partition inputs unchanged); no
  weight-aware / per-holding quorum at thesis level (that is Policy B's
  territory, rules 3/4).
- **No change** to `_stamp_fund_level_evidence_from_verdict`,
  `_stamp_audit_errors_from_verdict`, the auditor
  (`find_uncited_opportunity_rows`), citation selector, renderers, or the
  monitor vertical.

## Constraints

- **TDD.** Failing test first for each AC (red → green → refactor); tests
  mirror source (`thesis_evidence.py` → `tests/opportunity/test_thesis_evidence.py`,
  `fund_eval.py` → `tests/opportunity/test_fund_eval.py`).
- **Purity.** `derive_thesis_from_evidence` stays a pure function — no I/O,
  no mutation of the snapshot; leg check reads `snapshot.fund_level_evidence`
  (a frozen field, default `()`, so pre-field cached snapshots deserialize to
  the strict data-only path — intended: their evidence surface genuinely
  lacks the fund-level legs).
- **Size budget.** `thesis_evidence.py` is already 461 lines (over the
  <200 ideal); the change must stay small (≈ a ≤10-line pure helper, e.g.
  `_has_dual_legs(evidence) -> bool` or a `(has_data, has_info)` splitter,
  plus the branch edit) — do not grow the file materially, do not nest >3
  levels, keep the branch <20 lines.
- **No VERSION bump**; accumulate under CHANGELOG `[Unreleased]`
  (versioning convention).
- **TODOS.md annotation** per MASTER-SPEC ("Resolved 2026-07-03" format).
- **H3 / SAME-3 invariants must keep holding structurally**: no new gap
  codes (H3 partition predicate unchanged), no citation-set change (evidence
  tuples byte-identical ⇒ picks/evidence-pool/discipline citation-set
  equality untouched), locked by AC7/AC8/AC10 and the lockdown suite.
- **Known-failure diff-scoping.** Full pytest is NOT green on main (24
  pre-existing failures); replay any failing id on main before assuming a
  regression. `tests/commands/` runs per-file only.

## Open questions resolved during brainstorming

- **Q1 — what are the data / information legs, and where is the
  classifier?** The classifier is the `citation_kind: CitationKind =
  Literal["data", "information"]` field on `ThesisEvidence`
  (`src/irc/fundamentals/types.py:49,72`, validated in `__post_init__`
  :85–86), stamped at the producer edge in
  `src/irc/fundamentals/snapshot.py`: constituent filings →
  `"data"` (:355 CN, :406 HK; "disclosure-existence anchor" per CONTEXT.md
  *Filing evidence semantics*), broker reports → `"information"` (:371),
  stock news → `"information"` (:387, :427); fund-level NAV snapshot →
  `"data"` (:196/:500), fund announcements → `"information"` (:216/:517).
  The check is `citation_kind`-only, mirroring the `FundLevelSnapshot`
  branch (:361–362) — no scope filter needed: every active-branch evidence
  item is `scope="constituent"` (constituent legs) or `"instrument"`
  (fund-level legs), both inside the dual-coverage gate's accepted set
  (CONTEXT.md line 71; `auditor._PUBLISHABLE_SCOPES`), and theme-report
  `asset_class_macro` evidence never enters the active branch.
- **Q2 — what should data-only evidence yield?** `"evidence_insufficient"`
  — the exact value the `FundLevelSnapshot` branch yields when a leg is
  missing (`thesis_evidence.py:369–373`, reason
  `"基金层级仅获取到部分证据。"`). NOT `under_pressure` (that is a negative
  *signal*; leg absence is missing evidence). Consistency with the existing
  branch is the default and no evidence argued otherwise.
- **Q3 — evidence surface for the leg check: constituent-only vs union with
  `fund_level_evidence`?** **Union** (flattened constituent evidence ∪
  `snapshot.fund_level_evidence`, presence-only). Rationale: (a) ADR 0003 §7
  rule 2.5 explicitly accepts `fund_level_evidence` (NAV data leg +
  announcement information leg) as "the dual-coverage gate substitute" for
  foreign-heavy funds — a constituent-only check would demote every
  rule-2.5-publishable fund to `evidence_insufficient` → `small_watch`,
  recreating at thesis level the systematic exclusion rule 2.5 was built to
  remove, and changing published thesis cards (out of scope); (b) the
  dual-coverage gate itself (CONTEXT.md line 71) accepts
  `scope="instrument"` legs with `owner_instrument_id == row.instrument_id`,
  which is exactly `fund_level_evidence`'s shape — and the main pipeline
  stamps those very legs onto rule-2.5 rows
  (`_stamp_fund_level_evidence_from_verdict`), so the union is what the
  downstream gate actually sees; (c) the union makes Policy-B-publishable
  invariance provable (AC10): rules 3+4 imply constituent dual-leg, rule 2.5
  implies fund-level dual-leg ⇒ no publishable row flips ⇒ canonical
  main-pipeline outputs byte-identical **[grill R1: this implication holds
  only WITH the empty-flattened-first guard — rule 2.5 can publish an
  all-pure-failure fund whose flattened evidence is empty, and a union-only
  check would flip it intact-ward; see AC5 fixture (b)]**. The union is presence-only: the
  returned evidence tuple stays flattened-constituent-only to avoid
  double-append with the rule-2.5 stamp and any citation-set drift.
- **Q4 — blast radius.** (i) Main `irc opportunity` pipeline: publishable
  rows unchanged (Q3c); gapped rows may flip `intact` →
  `evidence_insufficient` internally, but H3 keeps them out of
  `thesis_cards.yaml` / `opportunity_report.json` and the failure renderer
  reads only the 4 non-conclusion fields — no output change. (ii)
  `irc eval-funds` (`fund_eval.py::evaluate_fund`, Policy-B-free): the fix
  target — data-only rows drop from `core_dca` to `small_watch`
  (weak-link label `主题逻辑证据不足`), `core_dca=False`. (iii)
  `irc narrative --analyze` (`narrative/analyze.py:152`, Policy-B-free):
  same flip possible; no gaps added, so `position_risk_level`'s
  `insufficient` force (evidence_gaps-driven) does not fire. (iv) Tests
  locking current behavior: survey found NONE asserting `intact` on
  data-only active fixtures (`test_derive_thesis_returns_5_tuple_for_active_fund`,
  `test_states.py` active-fund tests, and the commands/narrative fixtures
  assert slots/fetch-types or use empty analyses / stubbed rows);
  `test_fund_eval.py::_intact_snapshot` already carries both legs.
- **Q5 — should FUND-level information evidence satisfy the leg for a fund
  whose constituent evidence is data-only?** Yes (subsumed by Q3): that is
  precisely the mixed/foreign-heavy composition ADR 0003 §7 endorses, and
  the passive `FundLevelSnapshot` precedent (CONTEXT.md "Narrative passive
  path is theme-independent") already treats NAV + announcement as
  sufficient for `intact`. Requiring constituent-level info would be a
  stricter bar than the dual-coverage gate itself imposes.
- **Q6 — rejected alternatives.** (1) Constituent-only leg check — rejected
  per Q3a. (2) Policy-B-parity quorum (per-holding data leg + weight-aware
  top-half info quorum) at thesis level — rejected: duplicates the
  publishability authority inside the thesis setter (ADR 0003 separation)
  and adds material complexity to an over-budget file for no additional
  correctness (Policy B already gates those rows in the pipeline).

## Resolved decisions (grill 2026-07-03)

All spec code-location and literal claims were re-verified in code (not
trusted from the spec's own text) before these resolutions.

- **R1 — Empty-flattened guard precedes the union leg check (LOAD-BEARING;
  new AC5 fixture (b)).** The only reachable Policy-B-publishable shape
  where the union alone would flip a published row is: rule-2.5-publishable
  fund, ALL top-N constituents pure-failure (`evidence==()`,
  `failure_reasons!=()` — passes rule 2, documented reachable by ADR 0003
  §7's 2026-06-04 reconciliation), dual-leg `fund_level_evidence`. Today it
  is `evidence_insufficient`; it must stay so. The Goal, AC5, AC10 and Q3(c)
  were amended accordingly. Resolving this shape intact-ward
  (FundLevel-parity) was considered and REJECTED for this item: it changes
  published canonical outputs, out of scope for a false-confidence bugfix
  (recorded as ADR 0003 §8 Alternative B).
- **R2 — Union decision SURVIVES the Policy-B stress test.** Exhaustive over
  verdict shapes (`policy_b.py:217–366`): publishable ⟺ (no rule fired ⇒
  rules 3+4 passed ⇒ flattened evidence dual-leg) ∨ (`fired_rule=="2.5"` ∧
  `gap_codes==()` ⇒ `fund_level_evidence` dual-leg, `policy_b.py:283–312`).
  With R1's ordering, every publishable row's `thesis_state` is byte-stable.
  QDII rows bypass Policy B entirely (`FundLevelSnapshot` path, ADR 0003 §6)
  and that branch is untouched (AC11). No contradiction with ADR 0003 rule
  2.5 or the CONTEXT.md dual-coverage gate in any published scenario.
- **R3 — Reason literals verified byte-for-byte where shared.** Existing
  literals confirmed at `thesis_evidence.py:388` (intact) and `:392`
  (empty); the FundLevel single-leg literal `"基金层级仅获取到部分证据。"`
  (`:371`) is deliberately NOT reused — the two new direction-specific AC6
  literals are better diagnostics for the Policy-B-free surfaces, and the
  FundLevel branch keeps its own literal (AC11). New-literal exposure
  audit: `thesis_reason` → `opportunity_reason` (5-segment `" | "` join,
  `states.py:684`) reaches (a) `opportunity_report.json` — publishable-only
  (H3) and no publishable row ever carries the new literals (R2); (b) memo
  evidence pool — takes `split(" | ")[0]` = state segment only
  (`evidence_pool.py:89`); (c) failure renderer — reads only the 4
  non-conclusion fields (ADR 0003 §3.4); (d) `rejections.json` —
  `RejectionRecord` (`rejection_log.py:40–51`) carries NO conclusion/reason
  field; (e) alias-builder keys on `instrument_id`/`name_cn` only. ⇒ the
  new strings can never appear in a SAME-3-relevant or citation-bearing
  artifact; they surface only in eval-funds `note_cn` and narrative reports
  (citation-free, Policy-B-free).
- **R4 — H3 partition provably unchanged.** Partition predicate is
  `evidence_gaps`-only; AC7 locks the gaps slot byte-identical
  (`top_holdings_broker_thin` confirmed in `ADVISORY_GAP_CODES`,
  `advisory_gaps.py:23–26`, routed to `advisory_gaps` by
  `states._partition_gaps` — never into `evidence_gaps`). Grep confirmed no
  existing test asserts `intact` on a data-only active fixture (all `intact`
  assertions are legacy-`ConstituentSnapshot`/theme-report/compose paths).
  Gapped-row internal flips produce zero byte change in any canonical
  output artifact.
- **R5 — eval-funds sensitivity confirmed.** `FundEval` carries
  `thesis_state`, `opportunity_state`, `core_dca`,
  `note_cn=row.opportunity_reason` (`fund_eval.py:58–72`); both renderers
  emit `thesis_state` + `core_dca`. AC9's observable surface is correct;
  `test_fund_eval.py::_intact_snapshot` verified to already carry both legs
  (so the existing core_dca test passes unmodified). `note_cn` for
  data-only funds will carry the new missing-leg literal — intended,
  operator-visible improvement.
- **R6 — Terminology: do NOT say "the dual-coverage gate now applies to
  both snapshot shapes".** That wording conflates two gates at different
  layers: the *dual-coverage gate* (CONTEXT.md) decides row publishability
  at the auditor (per contributing dimension, `_PUBLISHABLE_SCOPES`); what
  this item extends is the *thesis-level* presence-only heuristic inside
  `derive_thesis_from_evidence`. CONTEXT.md gains a new distinct term
  **"Dual-leg thesis heuristic"** (added under the citation-model section)
  instead of an addendum to the dual-coverage gate entry.
- **R7 — ADR disposition: addendum §8 to ADR 0003, not a new ADR.**
  Three-of-three met: (1) hard to reverse — reverting re-opens the
  `core_dca` false positive and the literals become regression-locked;
  (2) surprising without context — the thesis check reads
  `fund_level_evidence` while the returned tuple excludes it, and the
  empty-first ordering silently guards published-output invariance;
  (3) real trade-off — constituent-only vs presence-only union vs
  FundLevel-parity intact-ward. Amendment-in-place follows ADR 0003 §7's
  own Alternative B precedent (no sibling ADR overriding §1/§7 from
  outside).
