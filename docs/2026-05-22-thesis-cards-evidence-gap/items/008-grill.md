# Item 008 — Grill summary

Auto-accepted under autonomy override 2026-05-23 (autodev backlog-mode grill subagent). No human in the loop; every recommended answer locked verbatim against existing project precedent (ADRs 0001–0004, CONTEXT.md, items 003 + 006 + 007 PR cadence).

## Verdict

**PASS.** Spec is plan-ready. All 7 open questions auto-resolved against existing code or PR precedent; 2 new ACs added (pipeline-level byte equality); 23 ACs total now lock the publishable-set baseline before item 009 flips block-mode. No new ADRs needed; CONTEXT.md gains 2 terms.

## Seven open questions resolved

| # | Question | Locked answer | Source of authority |
|---|---|---|---|
| Q1 | `run_memo` offline mocking pattern | Patch `irc.memo.synthesizer.call_chat` + `irc.memo.auditor.call_chat` per `tests/commands/test_memo_cmd_aliases.py:98–99`. Wrapped in module-level `_patch_memo_routes(synth_text)` helper. **No `run_memo_pipeline` lower-level call needed.** | Existing test precedent; `src/irc/commands/memo_cmd.py:530–532` confirms route resolution → `call_chat` chain. |
| Q2 | Env-var gates for seed helper | Four env vars via `monkeypatch.setenv`: `IRC_OPPORTUNITY_AUTOBUILD=1`, `IRC_CACHE_FRESHNESS_DAYS=7`, `IRC_FETCH_BUDGET=2000`, `IRC_ALLOW_STALE=1`. All four exist in production; none new. | `src/irc/commands/opportunity_cmd.py:71/194/199/204/1191`. |
| Q3 | QDII variant coverage | **One per variant** (`qdii_us`, `qdii_hk`, `qdii_global` = 3 rows) — locks per-variant exclusion path. | CONTEXT.md "QDII V1 exclusion"; `_build_qdii_sentinel_snapshot` routing keys off variant. |
| Q4 | Cache freshness env var name | **`IRC_CACHE_FRESHNESS_DAYS` EXISTS** at `src/irc/commands/opportunity_cmd.py:71,199` with default 7. Already documented in CONTEXT.md "Fail-closed freshness probe". No new env var, no new term, no ADR amendment. | Direct grep of production code + CONTEXT.md. |
| Q5 | Citation-id universe for AC19 | Universe = `opportunity_report.json[rows][*][thesis_evidence][*][citation_id] ∪ gold_regime.json[evidence][*][citation_id]`. **`rejections.json` EXCLUDED** — `RejectionRecord` has no `thesis_evidence` field. | `src/irc/opportunity/rejection_log.py:35–47` (dataclass fields verified). |
| Q6 | Production-fix policy in test-only PR | **Inline-fix.** Item 003 PR closed Q4-prereq drift in same PR; item 006 PR closed `_classify_fund_level_scores` over-count in same PR. Capture each fix as separate commit in `008-drift.md`. Do NOT spawn follow-up issue. | Items 003 + 006 PR shape precedent. |
| Q7 | Decision-rule encoding for AC11 | `_GAP_TO_REASON` dict-iteration order IS the precedence (qdii first key). AC11 hard-codes expected `rejection_reason` string with `# precedence per ...` comment; does NOT import the private constant. | `src/irc/opportunity/rejection_log.py:61–88`; Python ≥3.7 dict-insertion-order semantics. |

## Additional findings during grilling

### F1 — Missed invariant: pipeline-level byte equality

Item 007 locked **unit-level** two-run byte equality (`tests/memo/test_determinism.py::test_evidence_pool_byte_equal_across_runs` + `::test_compose_discipline_markdown_byte_equal_across_runs`) — pure functions over synthetic inputs. **No existing test asserts byte equality at the artifact-read level after two consecutive `run_opportunity` + `run_memo` invocations.**

Determinism bugs the unit tests cannot see:
- frozenset iteration order in `ConstituentAliases` (locked at builder level by ADR 0004 §1 but never asserted on-disk)
- `os.walk` / `glob` ordering when `_write_opportunity_outputs` reads `data/fundamentals/<quarter>/`
- dict hash order in JSON serialization across CPython process restarts
- accidental `datetime.now()` injection in a future renderer change
- non-deterministic ordering in `_GAP_TO_REASON` iteration if a future refactor switches to `set`

**Mitigation:** Added ACs 22–23 (two-run byte equality of `opportunity_report.json` + `thesis_cards.yaml` + `discipline_report.md` + `rejections.json` after `run_opportunity`; plus `memo.md` after `run_memo`). Approach: seed identically under `tmp_path_a` and `tmp_path_b`, invoke pipeline both times, sha256-compare the artifacts. Self-equality (not committed-hash anchoring) is the right shape — asserts determinism without churning on every legitimate schema change.

### F2 — AC11 implementation-detail leak avoided

The original spec considered importing `_GAP_TO_REASON` directly for AC11. Grilling caught this — the constant is private (leading underscore) and coupling item 008 to dict-iteration-order semantics is brittle. **Locked:** AC11 asserts on the observable rejection_reason string with a comment pointing to the source. The dict-iteration-order ADR 0003 precedence is the contract; the constant is the implementation.

### F3 — Q5 explicit-exclusion is load-bearing

The original spec was ambiguous about whether `rejections.json` entries' evidence count toward the AC19 citation universe. **Verified by reading `RejectionRecord` dataclass:** there is no `thesis_evidence` field. The exclusion is structural, not policy. Locked in CONTEXT.md "Publishable citation universe" as a new term so item 009's `find_missing_citations` author cannot accidentally widen the universe to include rejections.

## ADR review

3-of-3 ADR test applied to potential new ADRs:

| Candidate ADR | Hard to reverse? | Surprising without context? | Real trade-off? | Verdict |
|---|---|---|---|---|
| "Pipeline-level byte equality is the right granularity" | No (test-only) | No (extends item 007's locked precedent) | Yes (D6 in spec) | **SKIP** — locked in spec §5 D6 |
| "Publishable citation universe excludes rejections.json" | Yes (couples item 009's audit gate) | Yes (counterintuitive — rejections seem like they should have evidence) | Yes (structural vs policy exclusion) | **Mitigation:** added as CONTEXT.md term, not standalone ADR. The exclusion follows from `RejectionRecord`'s field list — already in ADR 0003. |
| "Inline-fix policy in test-only PRs" | No (workflow choice) | No (items 003 + 006 precedent) | Marginal | **SKIP** — locked in spec §4 |

**No new ADRs created.** ADR 0001–0004 stand unmodified.

## CONTEXT.md additions

Two terms appended to the "Test infrastructure" section:

1. **Publishable-set lockdown baseline** — names `tests/integration/test_publishable_set_lockdown.py` as the locked baseline; enumerates the 7 invariant families it spans; gates item 009's block-mode flip.
2. **Publishable citation universe** — the explicit `opportunity_report.json ∪ gold_regime.json` formula with `rejections.json` excluded; sourced from `RejectionRecord`'s missing `thesis_evidence` field.

## AC audit results

### Testability without live network: PASS (all 23)

Every AC seeds via `_seed_publishable_set_repo` (patches `_ak_call` + pre-writes caches under `tmp_path`); no network reachable. ACs 19/20/22/23 patch `irc.memo.synthesizer.call_chat` + `irc.memo.auditor.call_chat` per the locked precedent.

### Overlap with existing unit tests: AUDITED

- Did NOT re-prove anything already locked at unit level: AC1–AC5 assert on **on-disk JSON round-trip** (unit tests assert on in-memory dataclass shape); AC10 asserts on **four-surface partition** (unit `test_opportunity_cmd_h3_invariant.py` asserts on row-construction level only); AC20 re-asserts SAME-3 **post-disk-roundtrip** (unit `test_same_3_invariant.py` asserts in-memory).
- ACs 22–23 explicitly extend item 007's unit-level byte equality (`tests/memo/test_determinism.py`) to the pipeline level, NOT duplicate it.

### Sharpness — single binary pass/fail per AC: PASS (all 23)

Every AC has a `sha256` comparison, `set ⊆ set` membership, `regex match`, or `== literal` predicate. No "the test asserts reasonable behavior" hand-waving.

### What's-already-covered table accuracy: VERIFIED

Re-grepped the test suite: every cited test file + test name exists on commit `178ac04`. E10's "MISSING" classification confirmed — `test_opportunity_cmd_fund_level_integration.py::_universal_side` covers `_build_rows` only, not the full `run_opportunity` end-to-end across all 4 V1 + 3 QDII variants.

## Spec file diff

`docs/2026-05-22-thesis-cards-evidence-gap/items/008-spec.md` updated with:
- New "Test-isolation harness" subsection in §3 (env vars + memo route patching pattern)
- New ACs 22–23 (pipeline-level byte equality of opportunity + memo artifacts)
- AC11 sharpened with the `# precedence per ...` implementation note
- AC19 sharpened with the explicit Q5-resolved universe formula
- New §5 D6 decision on pipeline-level vs unit-level byte equality
- New §6 "Resolved open questions" replacing the original "Open questions for grill phase"
- §4 "Files explicitly NOT touched" amended with the Q6-resolved inline-fix policy
- §7 "Non-goals" amended with "No new env vars, no new ADRs"
- Spec line count: 190 → ~290 lines
- Test file LOC budget: 500–700 → 600–800

## Unresolved questions

None at grill level. The planner inherits a fully-locked spec.

## Most consequential clarification

**F1 / ACs 22–23.** Without pipeline-level byte equality, item 009's `IRC_CITATION_ENFORCE_MODE=block` flip would land on a baseline that's locked at the unit level but could silently non-determinise at the I/O boundary. The unit-level tests in `test_determinism.py` (item 007) are necessary but not sufficient — they cannot see frozenset iteration order during `os.walk` of `data/fundamentals/`, dict hash order across process restarts, or `datetime.now()` injection in a future renderer. AC22 + AC23 close the loop.

**F3 / "Publishable citation universe" term.** Without explicit exclusion of `rejections.json` from the citation universe, item 009's `find_missing_citations` matrix (E6) could widen its lookup table to include rejection-record citations — but those don't exist. Locking the term in CONTEXT.md catches the misconception structurally.
