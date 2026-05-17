# Item 007 — Rewrite memo traceability scorer (drop fake `coverage_ratio`)

## Problem

`outputs/2026-05-17/memo_traceability.json` reports `{coverage_ratio: 0.0, n_refs: 1.0, n_covered: 0.0}`. The scorer at `src/irc/memo/traceability.py` does naive token matching — requires ≥60% of the `>=3-char` tokens in each evidence string to reappear in the memo text. This is a broken metric for two reasons:
1. Chinese tokens don't survive: `阿里巴巴` is one token here; the LLM may write `阿里` or `BABA` — both fail the substring check.
2. The metric doesn't measure what it claims. `coverage_ratio = 0.0` does NOT mean the memo ignored the evidence; it means the LLM paraphrased instead of quoting verbatim.

## Approach (decided)

Option (b) from the original plan: drop `coverage_ratio` entirely. Report only what we can honestly measure:
- `n_refs_provided` (how many evidence strings the synthesizer was given)
- `n_refs_quoted_verbatim` (how many of those strings appear verbatim in the memo — exact substring match)

Option (a) — inject `[ref:ID]` markers into the LLM prompt and parse them back — is rejected because it adds variance to the LLM call and makes the assertion fragile against prompt drift.

## Acceptance criteria

- `outputs/<date>/memo_traceability.json` schema: `{n_refs_provided: int, n_refs_quoted_verbatim: int}`. `coverage_ratio` and `n_covered` are removed. `n_refs` is retained as an alias for `n_refs_provided` (back-compat, since `memo_audit.txt` may quote it).
- `check_traceability()` in `traceability.py` is rewritten to do exact substring matching, not token overlap.
- A test verifies: given an evidence ref `"[BABA 阿里巴巴] score=75.5"` and a memo containing the exact substring, `n_refs_quoted_verbatim == 1`; given a memo that paraphrases (`"Alibaba scored 75.5"`), it's `0`.
- The pipeline still calls the new function the same way — no consumer changes needed.

## Files (expected)

- `src/irc/memo/traceability.py` — rewrite the scorer.
- `src/irc/memo/pipeline.py` or `src/irc/commands/memo_cmd.py` — adjust the keys written to `memo_traceability.json`.
- `tests/memo/test_traceability.py` (or wherever the existing test lives) — update.

## Non-goals

- Changing the LLM prompt for the memo synthesizer.
- Adding `[ref:ID]` markers.
- Touching `memo_audit.txt` (separate file).
- Changing what evidence gets included in the synthesizer's input (that's items 5/6/8/9).
