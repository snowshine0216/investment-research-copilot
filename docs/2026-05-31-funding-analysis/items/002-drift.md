Verdict: PASS

Subagent: sonnet
Plan checklist items: 10 tasks / ~55 steps
Verified present in diff: 10 tasks / all load-bearing steps

---

## Verification method

Every finding below is backed by reading actual diff lines from
`git diff autodev/funding-analysis-feature...claude/funding-analysis-002`, not the
impl agent's summary. Line references are diff-offset lines.

---

## Load-bearing plan commitments — verified

**Threading mechanism (grill Q-T2 lock)**
- `compose_opportunity_state` gains exactly one new parameter:
  `valuation_fundamental: ValuationFundamental | None = None` (states.py diff +44).
- `build_opportunity_row` calls it with
  `valuation_fundamental=valuation_fundamental_signal(inp)` (states.py diff +75).
- No `fundamental_blocks_core_dca` predicate; no notch-refusal belt-and-suspenders
  predicate anywhere in the diff. CONFIRMED.

**`valuation_state` NOT forced toward more-expensive**
- The only state mutation in `classify_valuation` is `state = "cheap"` when
  `fundamental == "cheap" and state in _NOTCHABLE_VALUATION_STATES` (states.py diff
  +35). The `rich` / `neutral` signal branches append reason only; `state` is
  untouched. CONFIRMED.

**All-None fundamentals → dormancy (ADR 0009)**
- `test_signal_none_when_input_none` (test_valuation_fundamental_anchor.py diff +52)
  asserts `valuation_fundamental_signal(inp) is None` for `consensus_upside_pct=None`.
- `test_build_opportunity_row_core_dca_when_consensus_upside_none` (test_states.py
  diff +57) asserts `opportunity_state == "core_dca"` when no fundamentals are set.
- `test_notch_does_not_fire_when_signal_none` locks dormancy at the notch level.
  CONFIRMED.

**Item-001 AC4 lock RENAMED (not deleted)**
- Old name `-def test_population_is_inert_classify_valuation_byte_identical` removed
  (test_inputs_loader.py diff -31).
- New name `+def test_population_consumes_consensus_upside_per_item_002` added (+36).
  ADR 0009 citation and provenance comment preserved in docstring (+44).
- `grep -rn "test_population_is_inert_classify_valuation_byte_identical" tests/ src/`
  returns no matches. CONFIRMED.

**Named constants as module-level constants**
- `CHEAP_UPSIDE_THRESHOLD: float = 0.20` (valuation_fundamental.py diff +26).
- `RICH_UPSIDE_THRESHOLD: float = -0.10` (valuation_fundamental.py diff +27).
- No magic-number thresholds appear in `valuation_fundamental_signal`. CONFIRMED.

**No edits to Policy B / thesis_state derivation / citation surface / partition**
- Changed files: `PROGRESS.md`, `states.py`, `valuation_fundamental.py` (new),
  `test_inputs_loader.py`, `test_states.py`, `test_valuation_fundamental_anchor.py` (new).
- No touch to `opportunity_row.py`, `policy_b.py`, or any `_write_opportunity_outputs`
  path. `thesis_state` and `evidence_gaps` are verified byte-identical in the AC8
  structural lock test. CONFIRMED.

**New pure helpers in new module; states.py within plan scope**
- `src/irc/opportunity/valuation_fundamental.py` created at 68 lines (well under 200).
- `states.py` additions: import block (+5), one frozenset constant (+1), equity
  annotation+notch block (+8), composer param (+1), composer docstring (+7), gate
  guard (+4), one call-site kwarg (+1) = 27 addition lines. CONFIRMED.

---

## Drift findings

None.

---

## Incidental diff — accepted

| File | Change | Rationale |
|------|--------|-----------|
| `docs/2026-05-31-funding-analysis/PROGRESS.md` | Status row update for item 002 + impl log entry | Tracking edit; incidental to feature work. Accepted. |
| `tests/opportunity/test_inputs_loader.py` line 8 | `import dataclasses` moved to top-level (was inline in the deleted test) | Cleaner than the inline import; non-functional; no plan conflict. Accepted. |

---

## Task-by-task checklist

| Task | Plan description | In diff | Status |
|------|-----------------|---------|--------|
| T1 | `valuation_fundamental_signal` + constants in new module | valuation_fundamental.py +1..68; 5 tests in anchor file | OK |
| T2 | `_fundamental_reason_phrase` + `_pe_pb_fragment` | valuation_fundamental.py +48..68; 4 reason-phrase tests | OK |
| T3 | `classify_valuation` equity caveat annotation (AC2) | states.py +29..36; 3 annotation tests | OK |
| T4 | One-notch cheap-direction adjustment (AC3) + `_NOTCHABLE_VALUATION_STATES` | states.py +21, +34..36; 6 notch tests | OK |
| T5 | `compose_opportunity_state` explicit `valuation_fundamental` param (AC4) | states.py +44..66; 4 composer tests in test_states.py | OK |
| T6 | Thread signal in `build_opportunity_row` (AC4 end-to-end) | states.py +75; 2 end-to-end tests in test_states.py | OK |
| T7 | Bond/gold/QDII byte-identical lock (AC5) | 3 lock tests in test_valuation_fundamental_anchor.py | OK |
| T8 | Evolve item-001 AC4 lock (AC7): rename + second cheap-row test | test_inputs_loader.py: old name removed, `test_population_consumes_consensus_upside_per_item_002` + `test_consensus_upside_notch_fires_on_genuinely_cheap_percentile` | OK |
| T9 | AC8 structural lock: no citation/partition/Policy-B change | `test_fundamental_block_emits_no_thesis_evidence_or_gap` in anchor file | OK |
| T10 | Full-suite + lint + size-budget verification | No source changes (verification only); PROGRESS.md logs 457 opportunity tests pass, ruff clean | OK (verification artefact in PROGRESS.md) |
