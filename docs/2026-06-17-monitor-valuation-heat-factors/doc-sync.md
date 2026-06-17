Verdict: PASS

Subagent: sonnet
Items reviewed: 3
Doc changes verified:
  - CHANGELOG.md — covers all 3 slices: (1) "Added — monitor `valuation` factor: index-anchored
    path + unified 5-state vocabulary (2026-06-17)" — wiring, vocab unification, honest
    degradation, known `009225` gap; (2) "Added — monitor `valuation` factor: look-through path
    for pure active funds (2026-06-17)" — look-through wiring, coverage-floor, residual coverage
    gap note; (3) "Added — monitor `heat` factor: restriction leg (2026-06-17)" — fetch_purchase_table,
    parse_purchase_status, heat_inputs_for, AUM-Δ deferral, item-001 test-scope regression fix.
    All three entries confirmed present by reading actual diff lines.
  - TODOS.md — covers the two documented follow-ups: (1) "`monitor 009225` index valuation not lit
    — `china_internet` not an index-valuation key" (monitor-valuation-heat-001 ship review
    2026-06-17); (2) "Monitor look-through valuation coverage gap (item 002)" — no dedicated
    monitor-constituent stock-valuation ingest; (3) "Unlogged corrupt-snapshot swallow in
    `load_latest_active_fund_cached`" — observability-only silent-failure item (monitor-valuation-
    heat-002 ship silent-failure review 2026-06-17). All three confirmed present in diff.
  - CONTEXT.md / ADR — no update needed. CONTEXT.md was not modified on this branch
    (confirmed: `git diff main...HEAD -- CONTEXT.md` produces no output). The concepts wired
    here — `valuation`/`heat` factors, `profile_ineligible`, `valuation_state`/`heat_state`,
    `analysis_profile` eligibility, and the "valuation/heat decision tables" reference — are
    pre-existing in CONTEXT.md from the monitor design. No genuinely new domain terms were
    introduced: `valuation_no_anchor`, `heat_no_data`, and `valuation_unknown_state` are
    pre-existing N/A codes; the unified 5-state vocab is an internal `_VALUATION_MAP` edit.
    The new module public contracts (`resolve_valuation_state`, `heat_inputs_for`, the
    `lookthrough.py` pure helper) are implementation-detail additions fully covered by
    the design spec already committed (`docs/superpowers/specs/2026-06-17-monitor-valuation-
    heat-factors-design.md`). No new ADR warranted: the key design choices (reuse opportunity
    *pure functions* on monitor-loaded cached tables, restriction-leg-only heat, honest
    `None`-on-miss degradation) all sit within the evidence-isolation invariant already
    governed by ADR 0017. AUM-Δ deferral is recorded in TODOS.md and SKIPPED.md; it is a
    scope-management decision, not a hard-to-reverse architectural trade-off requiring a
    standalone ADR.
Missing coverage: none
