Verdict: PASS

Subagent: orchestrator (run-level, spec-mode N=1 — per-item verify is the run-level verify)
Source: offline smoke (live network DEFERRED — limiter in deep cooldown)
Entry point exercised:
  - `uv run irc --help` → exit 0
  - `uv run python -c "from irc.fundamentals.legulegu_fetch import ...; from irc.fundamentals.akshare_index_valuation import ...; from irc.data.index_valuation_ingestor import ..."` → all merged modules import cleanly
  - `uv run pytest tests/fundamentals/ tests/data/ tests/commands/test_ingest_index_valuation_wiring.py` → 557 passed / 39 skipped
  - `uv run ruff check` on the 3 merged source files → All checks passed!

Cross-item flow observed:
  - N=1 single feature — no cross-item interaction surface. The integrated feature
    branch boots, imports, and passes the full affected offline suite.

Failures: none.

Deferred to operator (live network — each in its OWN recovered cold window, never chained):
  - Gate #4: `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare tests/fundamentals/test_index_valuation_live.py -v -s -x` → 4 passed (`-x` load-bearing).
  - Gate #3: `uv run irc run --from ingest` then `count_grounded.py outputs/<date>/opportunity_report.json` → ≥ 9 grounded; csi500/sse50 land.
  - Gate #5: steps 1–5 in `docs/2026-06-05-phase-a-broad-grounding/before-after.md`.
  - (Optional) speculative sweep: `IRC_RUN_LIVE_AKSHARE=1 IRC_RUN_LEGULEGU_SPECULATIVE=1 uv run pytest ...`.
