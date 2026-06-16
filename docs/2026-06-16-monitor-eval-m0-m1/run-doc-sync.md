Verdict: FAIL

Subagent: sonnet
Items reviewed: 2
Doc changes verified:
  - CONTEXT.md — 10 new M0 terms (eval_trace, FundTraceBundle, StageHealth, GateDecision, published_state, EVAL_GATED, validation badge/chip, forward ledger, live_gated, eval-live); M1 terms (eval corpus/eval case, impact scorer metrics, narrative scorer metrics, citation_validity/citation_resolution, attribution_strength/supported_attribution, hallucination_rate, eval-live paid surface, live_llm marker); NO_CALL cross-reference updated (committed 64c5aec + b1f15d3)
  - docs/adr/0017-monitor-evidence-isolation.md — §"Monitor-eval data contracts (2026-06-16)" covering eval_trace.json unified pool design + forward ledger append-mode JSONL rationale (M0); §"M1 LLM-suite data contracts" covering eval corpora versioned contract + sole-paid-surface invariant (M1)
  - CHANGELOG.md — M0 spine entry + M1 LLM suites entry, both 2026-06-16

Missing coverage:
  - README.md — no mention of `irc eval monitor_signal` (now included in `irc eval --all`), `irc eval monitor_impact` / `irc eval monitor_narrative` (live_gated, SKIPPED rc=3 without `IRC_RUN_LIVE_LLM_EVAL`), the `IRC_RUN_LIVE_LLM_EVAL=1` env var, the new per-run artifact `outputs/<date>/monitor/eval_trace.json`, the new cumulative ledger `data/monitor/forward_ledger.jsonl`, the EVAL-GATED badge / Validation panel added to `report.html`, or the `eval-live` spend scope. The existing "Daily monitor brief" section and the "Output inspection cheatsheet" table for `irc monitor` are unchanged.
  - CLAUDE.md — the Commands block lists `irc monitor` + `irc monitor snapshot` but has no entry for `irc eval monitor_signal` (now wired into `--all`), no mention of `IRC_RUN_LIVE_LLM_EVAL`, no mention of the new artifacts (`eval_trace.json`, `forward_ledger.jsonl`), and no note that `irc eval monitor_impact`/`monitor_narrative` without the env var returns SKIPPED (rc 3). The Tests block also lacks the `IRC_RUN_LIVE_LLM_EVAL=1 uv run pytest -m live_llm tests/llm/test_live_monitor_eval.py` invocation.

Manual fix path: Add an `irc eval` monitor-suite sub-section to README.md (under the "Daily monitor brief" section) covering `irc eval monitor_signal`, `IRC_RUN_LIVE_LLM_EVAL=1 irc eval monitor_impact/monitor_narrative`, the SKIPPED rc=3 behaviour without the env var, `eval_trace.json` and `forward_ledger.jsonl` outputs, and the EVAL-GATED badge — and mirror the new `irc eval monitor_signal` command + `IRC_RUN_LIVE_LLM_EVAL` env var + new artifacts in CLAUDE.md's Commands and Tests blocks.
