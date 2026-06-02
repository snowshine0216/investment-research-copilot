# MASTER-SPEC — `irc narrative` coverage gap + markdown rendering

**Mode:** backlog (consolidated to 4 IN items from the handoff's 6 suggested steps)
**Project type:** non-web (Python CLI — post-ship gate is `/verify`)
**Source:** `/tmp/claude-501/handoff-narrative-coverage-gap-and-markdown.md` (2026-06-02)
**Run dir:** `docs/2026-06-02-narrative-coverage-markdown/`

## Background (from the handoff diagnosis — no code changed that session)

`irc narrative --analyze` screens funds it cannot deepen. The deterministic rule
`derive_position_risk_level` (`src/irc/narrative/risk.py:60`) returns `insufficient`
whenever `view.evidence_gaps` is non-empty — so "insufficient" means "evidence not
cached," not a market judgment. `analyze_fund` (`src/irc/narrative/analyze.py:92`) is
cache-only and active-fund-shaped: it loads only `load_active_fund_cache(...)`
(`analyze.py:107`) and hardcodes `theme_report=None` (`analyze.py:108`). No supported
command fetches/builds a snapshot for a narrative-*discovered* fund (those funds are
absent from `scoring.json`, so `opportunity` autobuild never reaches them; `fundamentals
snapshot` only writes index `nav/` snapshots and rejects fund IDs). The `.md` reports are
a lossy projection of the `.json` and under-render the evidence.

## IN-scope items

| id  | Title | Handoff steps | Primary files | Notes |
|-----|-------|---------------|---------------|-------|
| 001 | Active-fund autobuild in `narrative --analyze` + fix misleading error string | #1, #6 | `src/irc/narrative/analyze.py`, `src/irc/commands/narrative_cmd.py` | Mirror `opportunity_cmd.py:840` autobuild path; build via `build_snapshot(...)` + `write_active_fund_cache(...)` for `cn_equity_fund` shortlist funds missing cache. Fix the error string at `narrative_cmd.py:159` that tells users to run `fundamentals snapshot` (which can't populate this cache). Recovers `ai_report` actives. **Highest leverage.** |
| 002 | Passive-ETF fund-level + `theme_report` wiring into `analyze_fund` | #2 | `src/irc/narrative/analyze.py`, `src/irc/fundamentals/snapshot.py` | Detect passive `cn_etf` asset class; load fund-level NAV snapshot (`_build_fund_level_snapshot` → `nav/`); feed fund-level evidence (NAV data leg + announcement info leg) + a theme report into thesis derivation. Machinery exists (`FundLevelSnapshot`); not wired into narrative path. Recovers `robots_report`. Larger change. |
| 003 | Markdown report enrichment (M1 evidence prose/citations + M2 product metrics) | #3, #4 | `src/irc/narrative/report.py` | M1: render narrative prose (`one_line_view` per constituent + short excerpts of cited news/filings) + resolvable citation footnotes mapping `[ref:hex]` → human-readable source line; keep the SAME-3 cap on the inline cell, expose the deeper pool as an appendix. M2: surface product-quality drivers (AUM, expense ratio, track-record length) next to `质量=weak` so genuine-weak is distinguishable from scorer-floored-on-thin-metadata. |
| 004 | Suppress action-triad / triggers on `insufficient` rows | #5 | `src/irc/narrative/report.py` | On `position_risk_level == "insufficient"`, suppress the `机会/dca/风险` triad + falsification/trim triggers; render an "insufficient — refresh evidence" line instead, mirroring the H3 gapped-row field discipline (CONTEXT.md). |

## OUT-scope items

None. All 6 handoff suggested steps are covered by the 4 consolidated IN items. SKIPPED.md is empty.

## Invariants the plans MUST respect (CONTEXT.md / ADRs)

- **Citation ID format** locked at 16 hex chars; regex `\[ref:[0-9a-f]{16}\]` (ADR 0001).
- **SAME-3 display invariant** — `select_citations(cap=3)`; picks/evidence-pool/discipline citation-set equality (ADR 0004 / CONTEXT.md).
- **H3 universal gapped-row invariant** — gapped rows "have not earned conclusions"; expose only 4 fields (drives item 004).
- **Policy B** — active-fund publishability; `thesis_state` set only by `derive_thesis_from_evidence`, never by Policy B (ADR 0003).
- **`基金概况` indicator is forbidden** in production fetch code (acceptance test greps for the literal). Info-leg citations come only from `fetch_fund_announcements`.
- **Effects at edges / TDD / frozen dataclasses + `dataclasses.replace`** — repo conventions (CLAUDE.md).
