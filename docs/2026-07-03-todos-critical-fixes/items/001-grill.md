Verdict: PASS

Subagent: claude-fable-5
Questions resolved: 12
Docs touched:
  - CONTEXT.md (commit eac76b3d) — annotation sync only: four report-v3 "not yet built"
    parentheticals → "shipped 2026-07-03"; "(ADR 0022 when written.)" → "(ADR 0022.)";
    "(ADR 0017 addendum when built)" → "(ADR 0017 addendum)"; dual-track
    "**not yet built**" → "built 2026-06-21". No new/changed terms; below the ADR bar.
Spec refined: items/001-spec.md (commit eac76b3d)

## Resolved decisions

- Q: Does the `schema_invalid:` message-prefix convention exist here, and does the spec's
  proposed error message match it?
  A: Yes — the guard reuses the existing `narrative_macro.py:124` raise verbatim
  (`schema_invalid: bad attribution_strength {strength!r}`); the prefix family is
  documented in `impact_validate.py:8`.
  Rationale: the fix is a pure widening of which inputs reach an existing raise.
  Doc impact: none
- Q: Is the prefix "used for `last_err` classification" as the spec claimed?
  A: No — overstated; clause struck in the spec. Only status logic anywhere is
  `doc.status != "ok"` (`render_html.py:402`); trace/dump serialize verbatim; no
  `startswith`/prefix parsing in `src/` or `evals/`.
  Rationale: convention, not a consumed contract — spec must not imply otherwise.
  Doc impact: none (spec strike-through)
- Q: Does AC5's "exactly 3 calls" match the retry budget constant?
  A: Yes — `_MAX_SCHEMA_RETRIES = 2`, loop `range(_MAX_SCHEMA_RETRIES + 1)` = 3 attempts;
  one CostEntry per successful call before parse, so AC4 (2) / AC5 (3) counts are exact.
  Rationale: counts derived from the constant, verified in code.
  Doc impact: none
- Q: Can the new "bad attribution_strength" degraded status break the eval layer?
  A: No — `metrics_narrative` consumes theme-keyed claim dicts, never status strings;
  `eval/trace.py` stores status additively; render omits any non-"ok" macro section.
  Rationale: grep-verified absence of any status-prefix consumer.
  Doc impact: none
- Q: Is the non-goal "narrative.py:40 twin is production-dead" true?
  A: Yes — only `tests/monitor/test_narrative.py` and
  `tests/commands/test_monitor_cmd_theme_consolidation.py:150` import it;
  `metrics_narrative` copies `_BANNED_VERBS` rather than importing.
  Rationale: verified importer graph; deletion stays with the orchestrator.
  Doc impact: none
- Q: Hardened attempt — raise or drop (AC6)?
  A: Raise — only the language guard has hardened-`continue` semantics
  (`narrative_macro.py:137-140`); the strength check precedes it, hardened-agnostic.
  Rationale: AC6 pins the as-built asymmetry.
  Doc impact: none
- Q: Is the cited blanket guard location (`monitor_cmd.py:1008-1013`) accurate?
  A: Yes — `except Exception → gather_error: {exc}` at exactly those lines.
  Rationale: confirms the failure narrative (TypeError escapes to whole-block degrade).
  Doc impact: none
- Q: Do the AC-referenced test scaffolds exist?
  A: Yes — `_fake_resp` (L100), `calls = {"n": 0}` (L205), `# ── F1/F2 ──` headers
  (L247/L316) in `tests/monitor/test_narrative_macro.py`; new section is F3.
  Rationale: ACs are writable against real conventions.
  Doc impact: none
- Q: CHANGELOG `[Unreleased]` present for the `Fixed` line?
  A: Yes — dated Changed/Added subsections exist; item adds `### Fixed`. No VERSION bump.
  Rationale: matches project versioning convention.
  Doc impact: none
- Q: CONTEXT.md says 宏观面速览 is "not yet built" but the spec targets its built code —
  contradiction?
  A: Stale glossary; synced. Report v3 shipped 2026-07-03 (`b04bc6d1`); all five stale
  build-status annotations corrected (four report-v3 + dual-track, wired via
  `holding_metrics` → `monitor_cmd`).
  Rationale: plan phase reads spec + glossary together; the denial was a real hazard.
  Doc impact: CONTEXT.md
- Q: Does the same crash class exist in the sibling impacts leg?
  A: Yes, latent and out of scope — `impact_validate.py:33` `tuple(...)` TypeError and
  `impacts.py:80` `.get` AttributeError both escape `impacts.py:83`'s except tuple.
  Rationale: recorded for the orchestrator, same treatment as the narrative.py non-goal.
  Doc impact: none
- Q: ADR warranted?
  A: No — fails all three of hard-to-reverse / surprising / real-trade-off; the rejected
  alternative (except-tuple widening) is already locked as AC8 in the spec.
  Rationale: three-of-three rule.
  Doc impact: none
