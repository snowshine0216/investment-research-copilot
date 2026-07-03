Verdict: PASS

# Item 004 grill report — fund-level evidence repair probe

## Subagent

autodev-dispatched grill subagent, 2026-07-03, branch
`autodev/todos-critical-fixes-feature`. Skill: `grill-with-docs`
(autonomous mode — recommended answers auto-accepted; every code-location,
call-count, and fixture claim in the spec was re-verified against source,
not trusted from the spec's own text).

## Questions resolved (10)

Full detail lives in the spec's new "## Resolved decisions (grill
2026-07-03)" section (R1–R10); summary:

1. **R1 — 4-tuple call/patch sites complete.** Grep over `src/`, `tests/`,
   `evals/`, `scripts/`: exactly the 4 sites AC5 lists
   (`opportunity_cmd.py:776`; `tests/commands/test_opportunity_cmd.py:675,
   :719, :930`). Zero references in `tests/opportunity/` /
   `tests/narrative/` — the repo-memory lambda-break precedent does not
   recur. Positional `FetchPlan(5, 0, 0, 0, 10)` sites (2) bind only the
   first 5 params — safe.
2. **R2 — Budget math confirmed at 4 calls.**
   `_fetch_active_fund_level_evidence` = 1 × `fund_open_fund_info_em`
   (`akshare_fundamentals.py:577`) + 3 × `_FUND_ANN_TOPIC_FNS` endpoints
   (`:682–686`). Probe+repair = 5 intended. Plan/runtime agreement
   qualified: the pre-existing quarter-roll under-count (probe charged 1,
   actual 35 on `refresh=True`) is unchanged and never compounded — the
   repair is skipped on the refresh arm.
3. **R3 — SPEC CORRECTED (plan-shape change): merge is leg-wise monotone,
   not full replacement.** Full replacement fails the TODO's own
   motivating scenario: info-only cache (NAV outage) + throttled
   announcements on repair (2026-06-21 pattern) would SWAP legs and
   oscillate forever. Leg-wise merge (fresh leg wins when produced, cached
   leg retained when not; failure string present ⟺ leg absent in merged
   evidence, matching `snapshot.py:505–523`'s producer invariant) heals to
   both legs in one run. AC2 rewritten with 4 required merge test cases.
4. **R4 — Cache invariants inherited; AC4 pinned to the POST-probe
   snapshot.** Quarter keying + `.tmp.{pid} → replace` come free from
   `write_active_fund_cache` (`snapshot_cache.py:224–233`); merging into
   pre-probe `cached` would roll back the probe-advanced `cache_probed_at`
   — now explicit in AC4. Double atomic write on probe+repair accepted.
5. **R5 — Item 002 ordering verified, single-run heal intended.** Repair
   precedes `evaluate_policy_b` + `derive_thesis_from_evidence`; ADR 0003
   §8's empty-flattened guard unaffected (repair adds no constituent
   evidence).
6. **R6 — SPEC CORRECTED: AC16 fixture rationale.** The lockdown fixture
   has `constituent_analyses=()` (predicate False via share 0.0), not a
   "CN-only constituent" — 600519 lives only in the probe frame.
7. **R7 — Terminology.** "Fund-level evidence repair (repair probe)"
   minted as a CONTEXT.md term (third fetch class: full refetch ~35 /
   freshness probe 1 / repair 4) + cross-ref in the "Foreign-heavy fund"
   entry — both applied at grill time. AC11's "no new term" claim struck.
8. **R7 (ADR judgment) — no standalone ADR.** Amendment-in-place is ADR
   0003 §7's own locked structural choice; AC11's §7 addendum widened to a
   paragraph and must ALSO fix §7's stale "2 additional AkShare calls
   (~100)" fetch-budget claim (actual 4, ~200) — same stale-count bug
   class as the `snapshot.py:486` docstring AC6 already fixes.
9. **R8 — `irc eval-funds` out of scope** (read-only cache consumer,
   Policy-B-free); added to Non-goals.
10. **R9 — Q2 three-return-path coverage re-verified** (:278–279, :298,
    :299 all funnel through the single insertion point).

## Spec corrections that change the plan's shape

- **AC2**: leg-wise monotone merge + leg-failure ⟺ leg-absence invariant
  (replaces full-replacement semantics); 4 named merge test cases.
- **AC4**: helper input is the post-probe `probed` snapshot, explicitly.
- **AC11**: CONTEXT work done at grill time (verify-as-built remains);
  ADR 0003 §7 addendum = paragraph + stale-"2 calls" fix.
- Call-site list (AC5) and 4-call budget (AC6) verified UNCHANGED — the
  plan can rely on them as written.

## Files touched at grill time

- `CONTEXT.md` — new "Fund-level evidence repair (repair probe)" entry
  (after "Fail-closed freshness probe"); cross-ref sentence appended to
  "Foreign-heavy fund (rule 2.5 short-circuit)".
- `docs/2026-07-03-todos-critical-fixes/items/004-spec.md` — refined in
  place (strike-throughs preserved) + "## Resolved decisions" section.
- No ADR file touched (deferred to AC11 implementation per R7).

Commit: `ff259456 grill(004): refine spec + sync docs`.
