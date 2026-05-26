Verdict: PASS

Subagent: opus
Questions resolved: 10
Docs touched:
  - CONTEXT.md (commit bc4fc3a)
  - docs/2026-05-26-decision-confidence-followup/items/003-spec.md (commit bc4fc3a)
Spec refined: items/003-spec.md (commit bc4fc3a)

## Resolved decisions

- Q: §5 picks table is inside `IRC_PICKS_TABLE_BEGIN/END` — is the
     synthesizer prompt actually told to keep the new columns verbatim,
     or just "the table"?
  A: VERIFIED verbatim. `src/irc/memo/synthesizer.py:127–133` instructs
     the LLM that "the entire markdown table (header, every row,
     footnote) between the markers" must be kept byte-for-byte, with
     explicit anti-drift wording on citations. Adding columns to the
     deterministic Python renderer is safe — the LLM literally cannot
     rewrite them.
  Rationale: matches `feedback_memo_pillar_locks.md` memory — §5 is
     one of the four pillar-locked pillars.
  Doc impact: CONTEXT.md "Decision Sheet → memo §5 picks-table mirror"
     entry pins the relationship.

- Q: Do the new columns leak any new citations and break SAME-3?
  A: NO. `单次定投上限` renders as `≤ X.XX%` literal; `触发状态`
     renders as `{name} ✓/✗/⚠` joined by `<br>`. Zero `[ref:...]`
     markers in either cell by construction. SAME-3 set equality
     across picks-table 证据 cell / evidence-pool / discipline nested
     bullets is preserved (AC14 already states this).
  Rationale: glyphs and percentages carry no citation_id.
  Doc impact: none beyond the existing AC14 statement.

- Q: Is the `_read_live_decision_inputs` extraction in-scope for
     "optional polish", or scope-creep?
  A: In-scope and load-bearing. Without it, `run_memo` would duplicate
     58 lines of DuckDB I/O across two command modules (spec
     under-counted at 30; corrected via strike-through). The project's
     "effects at edges + single seam" principle (CLAUDE.md) makes the
     extraction a prerequisite, not a follow-up.
  Rationale: structural — two-place drift is the failure mode this
     refactor pre-empts.
  Doc impact: spec AC7 line-count corrected; CONTEXT.md `live_inputs.py`
     entry added.

- Q: Is the helper extraction big enough to warrant a new ADR (or
     amend ADR 0004)?
  A: NO. Renderer-determinism contract is already locked by ADR 0004;
     this item is a faithful application (pure renderer, no consumer-side
     filter, no per-surface modes). The `live_inputs.py` and
     `resolve_trigger_current_value` moves are mechanical I/O / pure-
     function relocations — no new architectural seam, no surprising
     trade-off.
  Rationale: ADR criteria (hard-to-reverse + surprising + real trade-off)
     not met. CONTEXT entries suffice.
  Doc impact: CONTEXT.md gains 5 new bullets under "Renderers +
     alias-builder"; no ADR amendment.

- Q: Compact trigger display uses `<br>` to join multi-trigger lines —
     does GFM render that in table cells, and is there project precedent?
  A: YES. `picks_table.py::_format_citations_cell` already joins multiple
     citations with `<br>` in the 证据 cell. The new helper mirrors the
     precedent exactly.
  Rationale: precedent-matching keeps the table rendering idiom
     consistent.
  Doc impact: CONTEXT.md `_format_trigger_status_compact` entry
     references the `_format_citations_cell` precedent.

- Q: Naming — should the new symbols follow item 001's
     `FOREIGN_HEAVY_THRESHOLD` / item 002's `QDII_MAX_PREMIUM_DEFAULT`
     `Final[float]` pattern?
  A: Partially. Item 003 introduces no new tuning constants (the
     existing `_BUILD_TRANCHE_COUNT = 4` in `sizing.py` is reused). The
     four new module-level names are:
       1. `MACRO_FIELD_TO_KEY` (public; was `_MACRO_FIELD_TO_KEY` —
          `_` prefix dropped on relocation).
       2. `resolve_trigger_current_value(...)` (public; was
          `_resolve_trigger_current_value` — `_` prefix dropped).
       3. `read_live_decision_inputs(...)` (public; was
          `_read_live_decision_inputs` — `_` prefix dropped).
       4. `_format_trigger_status_compact(...)` (private; lives in
          `picks_table.py` as a renderer-internal helper, matching
          `_format_citation` / `_format_citations_cell` precedent).
  Rationale: project convention — `_`-prefixed when module-private,
     dropped on cross-module export.
  Doc impact: spec AC5 / AC7 / AC8 already match this; AC7
     strike-through pins the rename.

- Q: Are there on-disk memo.md golden fixtures that need updating when
     columns are added?
  A: NO. `tests/fixtures/` carries no memo.md goldens (empirical: `find
     tests/fixtures -name memo.md` returns empty). The integration test
     `test_publishable_set_lockdown.py::test_pipeline_two_run_byte_equality`
     (AC23) hashes `outputs/<date>/memo.md` AFTER a full live `run_memo`
     into a temp dir. It is a self-consistent two-run check (both runs
     produce the new columns) — adds will not break it.
  Rationale: empirical scan; the only on-disk memo.md files live under
     `outputs/<date>/` which is gitignored.
  Doc impact: spec Q4 already states "No on-disk fixtures"; verified.

- Q: Does the spec respect frozen-dataclass backward compatibility —
     can the two new fields be appended without breaking any of the
     existing `PickRow(...)` call sites?
  A: YES. `grep -rn "PickRow("` returns 21 call sites (1 in src + 20 in
     tests); ALL use keyword arguments. Frozen dataclass + default
     values = zero call-site edits required for legacy code.
  Rationale: empirical scan.
  Doc impact: spec Constraints bullet "PickRow ordering of fields is
     stable" already states this; verified.

- Q: Does the 4-tranche `build` convention need re-justification, or can
     `suggest_tranche_pct` be reused verbatim?
  A: Verbatim reuse. `_BUILD_TRANCHE_COUNT = 4` is already documented
     in `sizing.py`'s module docstring + comment ("Project convention
     is 4 tranches (monthly)"). No new tranche-count rationale to add.
  Rationale: `suggest_tranche_pct` is the single source of sizing
     truth and is the right reuse point.
  Doc impact: none (existing comment sufficient).

- Q: What happens for the QDII case where `target_weight > 0` but the
     row is also `qdii_premium_too_high`-blocked? Does the per-tranche
     cap still render?
  A: YES — `tranche_cap_pct = target_weight / 4` renders as `≤ X.XX%`.
     The blocking is orthogonal: the picks table reports the sizing
     cap (what you would buy if the trigger fires), while the
     discipline / decision_report tells the operator the QDII gate is
     blocked. Footnote text "权重均为上限约束（≤），非强制建仓目标"
     already covers this semantically.
  Rationale: cap and execution-readiness are separate concerns by
     design.
  Doc impact: none (AC1 / footnote semantics already cover this).
