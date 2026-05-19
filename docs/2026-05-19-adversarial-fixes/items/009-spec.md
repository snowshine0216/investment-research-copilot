# 009 — Audit becomes a blocking gate

## Why

`outputs/2026-05-19/memo_audit.txt` says "审核未通过" with 3 high-risk
findings (P1, P2, P3). The memo was still emitted and committed to
outputs. The adversarial review (§H) demands: P-tier issues should
block publication.

## What changes

1. In `src/irc/memo/auditor.py`, after `audit_memo()` returns, add a
   pure-function classifier that scans the audit content for the
   blocking markers:

```python
def audit_blocks_publish(audit_text: str) -> tuple[bool, tuple[str, ...]]:
    """Return (is_blocked, reasons). Block when the audit explicitly says
    审核未通过, OR when ≥1 P-tier 高风险 finding is present.
    Reasons are extracted P-tier lines or the explicit verdict."""
```

   Detection rules (deterministic):
   - "审核未通过" in audit_text → blocked
   - `re.search(r"^\|\s*P\d", line)` for any line in the audit → blocked
     (the existing audit format uses a `| P1 | 🔴 高 | ...` table)
   - "审核通过" with no P-tier rows → not blocked

2. In `src/irc/memo/pipeline.py` (or wherever `audit_memo` is called):
   - After `audit_blocks_publish` returns blocked, the pipeline must
     refuse to write `memo.md` to the dated output directory.
     Instead, write `memo_blocked.md` with the draft and the audit
     reasons, and raise a `PipelineHalt` exception (or set a non-zero
     exit code).
   - The next-run resume behavior is "fix the issues, re-run".

3. Wire the halt into `src/irc/cli.py` so `irc run` exits with code 2
   when the audit blocks.

## Acceptance criteria

- Synthetic audit text containing "审核未通过" → `audit_blocks_publish`
  returns `(True, …)`.
- Synthetic audit text containing only a P1 line → blocked.
- Synthetic audit text containing only 中风险/低风险 → not blocked.
- Re-running the pipeline against a corrupted memo simulation that
  triggers a P1 finding produces a `memo_blocked.md` file, NOT a
  `memo.md`, and the CLI exits non-zero.

## Tests to add

- `tests/memo/test_audit_blocking.py` covering the four detection
  branches.
- `tests/memo/test_pipeline_audit_halt.py`: integration test that
  injects a P-tier audit and asserts `memo_blocked.md` is written and
  `memo.md` is not.
