Verdict: PASS

Subagent: sonnet
Items reviewed: 4
Doc changes verified:
  - README.md — covers autobuild + IRC_NARRATIVE_AUTOBUILD opt-out; no stale fundamentals-snapshot prereq. The old `uv run irc fundamentals snapshot --target all --top-n 10` prerequisite line is removed; new text explicitly states `--analyze` auto-builds missing active (`cn_equity_fund`) and passive (`cn_etf`/QDII/`us_etf`/`hk_etf`) snapshots; `IRC_NARRATIVE_AUTOBUILD=0` opt-out documented; prerequisite comment now names `irc ingest` (not `fundamentals snapshot`); `fundamentals snapshot` mentioned only as a pre-warming option (explicitly "not a prerequisite"). CLI error path (rc=2) and budget-trip (rc=3) both documented.
  - CONTEXT.md — 9 new/updated terms: NAV-derived quarter (latest-nav/ probe), Narrative active-fund autobuild, Narrative passive fund-level autobuild, Narrative passive path is theme-independent, Narrative path is Policy-B-free, Narrative .md insufficient-row display discipline (H3 analog), Narrative report is a display-only non-SAME-3 surface, Active-fund 質量=weak is a scorer floor. "Analyze is cache-only" corrected to "Analyze deepens, then reads cache" with _Avoid_ note.
  - CHANGELOG.md — 4 [Unreleased] entries confirmed: (001) Active-fund autobuild for --analyze 2026-06-02; (002) Passive-ETF fund-level deepening for --analyze 2026-06-02; (003) Narrative report .md enrichment 2026-06-02; (004) H3 display discipline for insufficient narrative rows 2026-06-02.
Missing coverage: none
