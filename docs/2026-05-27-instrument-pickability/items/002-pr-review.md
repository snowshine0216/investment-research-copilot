Verdict: PASS-WITH-NITS

Source: /code-review on PR #77
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/77#issuecomment-4551869999
Findings: 3
  - src/irc/commands/memo_cmd.py:291 — latent-bug — _format_concentration_bullet adds "- " prefix to each bullet, but the template risk_notes renderer also adds "- " to every item → "- - 008382 fund_a ↔ 008555 fund_b：…" (double-dash, malformed Markdown) in published memo.md. No test catches it because the template integration test only checks "in md" membership.
  - src/irc/commands/memo_cmd.py:878 — nit — comment "Prepended last so it renders FIRST in §6" is stale; concentration_lines is now prepended after evidence_gap_lines, making concentration first, not evidence_gap.
  - src/irc/memo/synthesizer.py:142 — nit — hardcoded marker literal "<!-- IRC_CONCENTRATION_BEGIN -->" instead of importing CONCENTRATION_MARKER_BEGIN constant; consistent with all five existing marker guards in this file, but rename of the constant won't auto-propagate.

Previously-addressed items (commit 60d5469) — not re-raised:
  - P0 duplicate-symbol undercount in _top_n_by_weight (fixed)
  - P1 set-iteration non-determinism → sorted() (fixed)
  - P1 FP boundary on threshold → round(overlap, 1) >= THRESHOLD (fixed)
  - P1 missing n=5 boundary test (fixed)

## Fix-loop resolution (commit `79f88d7`)

The single latent-bug finding (double-dash markdown in concentration
bullets) is addressed in commit `79f88d7`. Two new regression tests
pin the invariant at the formatter level and through the full
`render_skeleton` integration:

- `test_format_concentration_bullet_does_not_double_prefix_dash` — RED
  before the fix, GREEN after; asserts the formatter does NOT self-prefix
  `"- "`.
- `test_concentration_bullet_renders_single_dash_through_template` — RED
  before, GREEN after; asserts `"- - 008382 ..."` does NOT appear in the
  rendered memo while `"- 008382 ..."` does.

Existing format-equality test updated to assert the dash-free payload
(template.py:80 prepends `"- "` once per `risk_notes` entry).

Full suite after fix: 797 passed, 1 skipped (zero regressions).

The 2 remaining nits (stale comment at `memo_cmd.py:878`, marker literal
at `synthesizer.py:142`) are documented but accepted — both are cosmetic
and the marker literal pattern is consistent with all five existing
`IRC_*_BEGIN/END` guards in the file (a rename would require a separate
refactor PR touching all six guards uniformly).

## Final effective verdict on PR HEAD (post-fix): PASS-WITH-NITS

Latent-bug resolved with regression tests; only cosmetic nits remain.
Loop exit contract satisfied: zero blocker bugs, zero high-confidence
latent bugs on the current PR HEAD (`79f88d7`).
