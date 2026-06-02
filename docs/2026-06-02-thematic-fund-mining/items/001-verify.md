Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct CLI entry-point (uv run irc narrative ...)
Entry point exercised:
  - uv run irc narrative --help
  - uv run irc narrative nope --repo-root . --out /tmp/narr_verify_nope
  - uv run irc narrative compute_metals --screen-only --repo-root . --out /tmp/narr_verify1
  - uv run irc narrative compute_metals --screen-only --repo-root . --out /tmp/narr_verify2
  - diff -r /tmp/narr_verify1 /tmp/narr_verify2
  - uv run irc narrative compute_metals --analyze --repo-root . --out /tmp/narr_verify_an

Observed behavior:
  - AC1 (command wired) — `--help` shows all 8 required flags: --screen-only, --analyze,
    --min-overlap, --quarter, --db, --role, --out, --repo-root. Exit 0.

  - AC2 (missing-narrative fail-fast) — `irc narrative nope ...` exited rc=2 and printed:
    "ERROR: narrative config not found: config/narratives/nope.yaml. Available: compute_metals"
    followed by "Available narratives: compute_metals". Both requirements met.

  - AC3 (screen default path) — `irc narrative compute_metals --screen-only` exited 0.
    Wrote exactly 3 files:
      compute_metals_shortlist.md
      compute_metals_shortlist.json
      compute_metals_screen_diagnostics.json
    shortlist.json parsed as valid JSON (no bare NaN), top-level keys = ['narrative', 'funds'],
    narrative = "算力金属", funds count = 15.
    diagnostics.json keys = ['excluded'], excluded count = 31.
    First 3 excluded entries all have reason = "no_published_holdings" — no silent caps confirmed.
    AkShare network WAS reachable: 15 real funds shortlisted via live holdings fetches from
    fundf10.eastmoney.com.

  - AC4 (determinism) — second identical screen run produced 15 shortlisted, 31 excluded.
    `diff -r /tmp/narr_verify1 /tmp/narr_verify2` → empty diff (exit 0). Byte-identical.

  - AC5 (analyze gate) — `irc narrative compute_metals --analyze` exited 0 and produced
    both compute_metals_report.md and compute_metals_report.json alongside the screen files.
    report.json: keys = ['narrative', 'funds'], 15 funds each with 'position_risk_level'
    (e.g. first fund = "high") plus valuation_state, heat_state, thesis_state,
    product_quality_state, opportunity_state, dca_action, risk_action, evidence_gaps, etc.
    report.md: 36 `[ref:XXXXXXXXXXXXXXXX]`-format citations found (regex \[ref:[0-9a-f]{16}\]).
    No uncaught traceback. Path used existing snapshot cache on disk.

Failures: none
