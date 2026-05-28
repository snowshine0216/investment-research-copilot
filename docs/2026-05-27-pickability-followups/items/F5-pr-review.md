Verdict: PASS-WITH-NITS
Source: /code-review on PR #81
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/81#issuecomment-4560284257
Findings: 2
  - docs/adr/0008-macro-research-excerpt-depth.md + CONTEXT.md — latent-bug — ADR §1 "Trade-offs considered" and CONTEXT.md §"Macro excerpt char cap" both state LLM [N] citation markers are NOT stripped ("leave them in" / "remain verbatim"), but gold_cmd.py lines 59+245 strip them via _LLM_REF_MARKER_RE (P0 fix added in commit 997e418 after grill/ADR were written). A future developer reading the ADR would revert the stripping to align with the documented invariant, breaking the passing test and reintroducing marker collisions in §2/§3 footnote rendering. Fix: update ADR 0008 §1 and CONTEXT.md to reflect the reversed decision.
  - src/irc/commands/gold_cmd.py:59 — nit — _LLM_REF_MARKER_RE pattern r'\s*\[\d{1,2}\]\s*' only matches [0]–[99]; markers [100]+ (e.g. LLM reports citing 100+ sources) pass through unstripped and would collide with downstream footnote numerals. Fix: change \d{1,2} to \d+ or \d{1,3}.
