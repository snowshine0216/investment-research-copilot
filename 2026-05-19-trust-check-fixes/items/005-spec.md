# 005 — Surface memo_audit P1 in decision_report Verdict

## Why

Trust-check A6 / priority #2: `memo_audit.txt` for 2026-05-19 had:

- 4 numeric-audit P1 contradictions (`[005561] cheap_claim_vs_state`
  etc.)
- "**P1（必改）**" rows in the priority table (§三, 修改优先级汇总)
- Final verdict: `**本备忘录审核结果：条件通过**` (Conditionally
  passed) — needs P1 fixes before execution.

Prior 009's `audit_blocks_publish` only recognises `| P1 |` table
rows or the literal `审核未通过` token — neither match the current
audit format (`| **P1（必改）** |` and `条件通过`). So the audit
did NOT block memo publication and `decision_report.md` is also
silent. A non-finance reader has no way to know the memo flunked its
own compliance check.

## What changes

1. New pure function `extract_audit_summary` in
   `src/irc/memo/auditor.py`:

   ```python
   def extract_audit_summary(audit_text: str) -> dict:
       """Return {"verdict": str, "p1_count": int, "p1_findings": list[str]}.

       verdict ∈ {"审核通过", "条件通过", "审核未通过", "未知"}.
       p1_findings: trimmed lines/rows where 'P1' appears (table row,
       bold marker, numeric-audit list). Capped at 10."""
   ```

2. `src/irc/commands/decision_cmd.py`:
   - Read `memo_audit.txt` if present in the output dir.
   - Call `extract_audit_summary`.
   - Pass `audit_summary` into `compose_decision_report`.

3. `src/irc/decision/report.py`:
   - `compose_decision_report` accepts `audit_summary` kwarg; store it
     in the report dict (`report["audit_summary"]`).
   - `render_decision_markdown` emits a bilingual banner under the
     Verdict line when verdict ≠ `审核通过` OR `p1_count > 0`.

## Banner format

```markdown
> 🛑 **合规审核未达标 / Memo compliance audit failed**: 审核结论
> "{verdict}", 含 P1 必改项 {p1_count} 条 (见 memo_audit.txt).
> 本周决策应视 memo §5 为草稿，**不应**直接执行。
```

## Acceptance criteria

- Audit text containing `条件通过` and a P1 line → banner appears,
  verdict reads "条件通过", p1_count ≥ 1.
- Audit text containing only `审核通过` → no banner.
- Audit text containing `审核未通过` with no P-tier lines → banner
  appears (verdict-only block).
- `audit_summary` field present in report dict.
- Decision_cmd integration: reading the 2026-05-19 audit produces the
  expected non-empty summary.

## Tests to add

- `tests/memo/test_audit_summary.py`:
  - extract_audit_summary on 条件通过 + P1 → verdict + count + findings
  - extract_audit_summary on 审核通过 → verdict_only, count 0
  - extract_audit_summary on 审核未通过 → blocked, optional P-tier lines
  - extract_audit_summary on empty text → 未知, count 0

- `tests/decision/test_three_section_markdown.py`:
  - banner appears when audit_summary has p1_count > 0
  - banner suppressed when audit_summary is None or verdict 审核通过
  - audit_summary key present in report dict
