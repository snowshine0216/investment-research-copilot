# Item 006 — Memo numeric-prose sanity validator

## What

Item 004 fixes the *evidence-pool labelling* so the LLM has a glossary. We still want a programmatic safety net: when the synthesized memo prose contradicts the underlying numbers, the auditor should automatically flag it instead of relying on a human spotting it.

Specifically: if the prose contains text like "估值便宜" within close proximity to a numeric `valuation_cost=8X` (or, post-rename, `cost_grade=8X`), it's almost certainly a contradiction — but only if `valuation_state != "cheap"/"reasonable_low"`. The validator's job is to surface these for review, not to auto-edit the memo.

## Files to touch

- `src/irc/memo/numeric_audit.py` (NEW) — a small, pure-function module.
- `src/irc/memo/pipeline.py` — call the validator after synthesis; merge its warnings into `MemoOutput.audit_notes` as an auto-generated leading block.
- `tests/memo/test_numeric_audit.py` (NEW) — covers the contradiction case and the no-contradiction case.

## Acceptance criteria

- `numeric_audit.py` exposes a pure function:
  ```python
  def find_prose_data_contradictions(
      prose: str,
      evidence_lines: list[str],
  ) -> list[NumericFinding]:
      ...
  ```
  `NumericFinding` is a frozen dataclass with `instrument_id`, `kind`, `prose_excerpt`, `evidence_excerpt`.
- The first detector to ship checks exactly the bug the audit caught today:
  - For each evidence line, parse `instrument_id`, `valuation_state` (the first token in `状态=A/B/C/D`), and `cost_grade=NN`.
  - If the prose contains the instrument id within 200 chars of either "估值便宜" / "估值偏低" / "cheap"-class phrase, AND `valuation_state` is NOT in `{"cheap", "reasonable_low"}`, AND `cost_grade >= 70` — flag.
  - Symmetric: id + "估值偏高"/"expensive" + `valuation_state in {"cheap", "reasonable_low"}` + `cost_grade <= 30` — flag the inverse.
- Findings render into `audit_notes` as:
  ```
  ### 自动数值审核 (numeric audit)
  - [{instrument_id}] {kind}: prose says "{prose_excerpt}" but evidence says "{evidence_excerpt}".
  ```
- When the validator finds no contradictions, no header is added (don't pollute the auditor output).
- A new test feeds a hand-constructed prose containing "000105 估值便宜" + an evidence line with `valuation_state=expensive` and `cost_grade=85` — asserts one finding.
- A new test feeds the same with `valuation_state=cheap` — asserts zero findings.
- The validator does not call out to any external service; pure string parsing.
- The full suite is green.

## Implementation hints

- Build a small parser: split evidence lines by space, parse `key=value` tokens after the `[id name]` prefix. For `状态=cheap/normal/intact/strong`, take the first token (`cheap`).
- For prose proximity, use regex `r"\[?({id})[\s　\W]{{0,200}}估值便宜"` (and Chinese variants). Keep the regex set small and explicit — false positives are worse than false negatives for an auditor signal.
- Add the new module's import at the top of `pipeline.py`; don't reach across modules from within `numeric_audit.py`.

## Out of scope

- Detectors for thesis claims (e.g. "intact" without macro support). Could be a future addition.
- Auto-rewriting the memo. The validator only annotates `audit_notes`.
- Calling the validator from CI separately — for now it's invoked once per memo run.
