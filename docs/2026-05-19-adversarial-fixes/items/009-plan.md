# 009 — Plan

## Steps

1. `src/irc/memo/auditor.py`:
   - Add pure `audit_blocks_publish(audit_text)` → `(is_blocked,
     reasons)` tuple.
   - Block when ``审核未通过`` is in the text OR when any line matches
     `^\| P\d+\b` (the existing audit's P-tier 高风险 table format).
2. `src/irc/commands/memo_cmd.py`:
   - After `run_memo_pipeline`, evaluate `audit_blocks_publish`.
   - Always write `memo_audit.txt` and `memo_traceability.json` so the
     evidence is on disk for diagnosis.
   - If blocked: write `memo_blocked.md` (with header + draft),
     unlink any stale `memo.md`, print block reasons, return rc=2.
   - If not blocked: write `memo.md` normally and return rc=0.
3. Tests at `tests/memo/test_audit_blocking.py`:
   - empty audit → not blocked
   - 审核通过 → not blocked
   - 审核未通过 → blocked
   - P1/P2/P3 table rows → blocked, reasons name the entries
   - 中风险/低风险 alone → not blocked
   - mixed (中风险 + P1) → blocked
