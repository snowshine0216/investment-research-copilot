# Item 005 — Stamp evidence cutoff date into the memo

## What

The memo audit flagged the risk-notes line "行情/净值通常 T+1；本备忘录数值以证据池为准" as inadequate disclosure: it's vague boilerplate with no actual cutoff date.

Every `raw_ref` in `scoring.json` already carries the date — e.g. `akshare:nav_history:000105:2026-05-15`. Surface that max date as `evidence_cutoff` in the memo and rewrite the risk-notes line.

## Files to touch

- `src/irc/memo/template.py` — add `evidence_cutoff: str` to `MemoInputs` (typed as ISO date string; tolerant of `None` for back-compat).
- `src/irc/memo/pipeline.py` — extract the cutoff from the raw_ref pool: split each ref on `:`, parse the trailing token as a date when it matches `YYYY-MM-DD`, take the max.
- `src/irc/commands/memo_cmd.py` (or wherever `MemoInputs` is built) — populate `evidence_cutoff`.
- `tests/memo/test_template.py` — add the assertion.
- `tests/memo/test_pipeline.py` (or `tests/memo/test_evidence_cutoff.py`) — add the date-extraction test.

## Acceptance criteria

- `MemoInputs` has a new `evidence_cutoff: str | None = None` field (default `None` for back-compat).
- A new helper `extract_evidence_cutoff(refs: list[str]) -> str | None` lives in the memo module. It returns the max ISO date found in the refs, or `None` if no ref carries a date.
- When `evidence_cutoff` is non-None, the rendered risk-notes section's last bullet is rewritten to read:
  > 数据时效：证据池截止 `{cutoff}` (akshare 净值/价格快照)。境内净值/价格通常滞后 1 个交易日；QDII 跨境结算可能滞后更长；遇节假日、停牌或跨境延迟时滞后时间进一步延长。所有数值不代表实时市场状态，执行前须自行核实。
- When `evidence_cutoff` is None, the line falls back to today's boilerplate. Don't break the path that has no refs.
- The full suite is green.
- One existing test in `tests/memo/` covers the case where the refs are empty and confirms the fallback path renders.

## Implementation hint

Where to call `extract_evidence_cutoff` — at the start of `run_memo_pipeline`, before `render_skeleton`. Pass the cutoff into `MemoInputs` via a new field; the template's risk-notes generator reads it. If `MemoInputs.risk_notes` already contains a literal "行情/净值通常 T+1" string and it's coming from a *caller* (in `memo_cmd.py`), update the caller to compose the line from the cutoff. Don't hard-code the line in the template if the current shape is "caller passes pre-formatted risk_notes" — check first.

## Out of scope

- Adding per-source cutoffs (akshare separately from theme_research). Today the akshare snapshot date is the binding constraint; one date is enough.
- Validating that the cutoff is recent. Item 004 of the prior loop (`freshness gate`) already handles ingest freshness.
