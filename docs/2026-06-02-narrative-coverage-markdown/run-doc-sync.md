Verdict: FAIL
    Subagent: sonnet
    Items reviewed: 4
    Doc changes verified:
      - CONTEXT.md — covers all required terms (verified from git diff origin/main...HEAD -- CONTEXT.md):
          - "Narrative active-fund autobuild" (item 001) — present; includes IRC_NARRATIVE_AUTOBUILD env var, Policy-B-free declaration, independent kill-switch rationale.
          - "Narrative path is Policy-B-free" (item 001) — present; explains no evaluate_policy_b / rule-2.5 stamping, thesis_state set only by derive_thesis_from_evidence (ADR 0003).
          - "Analyze deepens, then reads cache" (item 001) — replaces the old "Analyze is cache-only" term; _Avoid_ note added.
          - "Narrative passive fund-level autobuild" (item 002) — present; eligibility via resolved target.kind, shared IRC_NARRATIVE_AUTOBUILD kill-switch, instrument-index requirement.
          - "Narrative passive path is theme-independent" (item 002) — present; theme_report=None is by-design, FundLevelSnapshot branch never reads theme_report.
          - "NAV-derived quarter (latest-nav/ probe)" (item 002) — present; distinguishes from active-fund holdings-quarter probe.
          - "Narrative report is a display-only, non-SAME-3 surface" (item 003) — present; appendix/footnotes are exempt from citation-set equality; mirrors thesis_debate.md exemption.
          - "Active-fund 质量=weak is a scorer floor, not a product judgment (today)" (item 003) — present; aum_stability_pct universal-drop explanation, F-1 follow-up flagged.
          - "Narrative .md insufficient-row display discipline (H3 analog)" (item 004) — present; SUPPRESS set (action triad + sub-state verdicts), KEEP set (gap-facts + raw product_metrics), .md-only, locked grep test.
      - CHANGELOG.md — covers all 4 items under [Unreleased]:
          - Item 001: "Active-fund autobuild for --analyze (2026-06-02)" — IRC_NARRATIVE_AUTOBUILD, rc=3 budget trip, corrected error string.
          - Item 002: "Passive-ETF fund-level deepening for --analyze (2026-06-02)" — dual-leg thesis derivation, shared FetchPlan preflight, snapshot_cache.py refactor.
          - Item 003: "Narrative report .md enrichment (2026-06-02)" — evidence prose, citation footnote appendix, product-quality drivers, F-1 scorer floor note.
          - Item 004: "H3 display discipline for insufficient narrative rows (2026-06-02)" — action triad + sub-state suppression, bilingual refresh line, .md-only.
      - README.md — GAP (see below)
      - docs/adr/ — no new ADR created; confirmed consistent with all four grill decisions (three-of-three rule failed for each item; all reuse ADR 0002/0003/0004).
    Missing coverage:
      - README.md lines 213-215 still read: "# Prerequisites — the analyze phase READS CACHE (like `irc opportunity`); it does not fetch live." followed by `uv run irc fundamentals snapshot --target all --top-n 10  # quarterly; several minutes (builds the snapshot cache)`. Item 001 changed this behavior: --analyze now auto-builds active-fund snapshots by default (IRC_NARRATIVE_AUTOBUILD=1) and items 001+002 fixed the misleading error string that told users to run fundamentals snapshot. The README prerequisite block continues to give the wrong instruction (fundamentals snapshot cannot populate the active-fund or nav cache for narrative-discovered funds) and omits IRC_NARRATIVE_AUTOBUILD. Line 221 also tells users "run fundamentals snapshot first for a complete read" which contradicts the corrected behavior. This is the same misleading instruction item 001 explicitly fixed in the CLI error string — leaving it in README means a reader following the user-facing manual will do the wrong thing.
    Manual fix path: Update README.md lines 213-221 (the --analyze prerequisites comment + the trailing "run fundamentals snapshot" sentence) to reflect autobuild-first behavior and mention IRC_NARRATIVE_AUTOBUILD=0 as the opt-out, mirroring the CHANGELOG entry for item 001.
