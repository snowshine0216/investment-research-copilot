Verdict: PASS

Subagent: sonnet (re-check after doc-fix 4aa2062)
Items reviewed: 2
Doc changes verified:
  - README.md — covers `irc eval monitor_signal` (free, in `--all`); `irc eval monitor_impact` / `monitor_narrative` (live_gated, SKIPPED rc 3 without `IRC_RUN_LIVE_LLM_EVAL`, excluded from `--all`, budgeted by `eval-live` spend gate); `IRC_RUN_LIVE_LLM_EVAL=1` env var; `outputs/<date>/monitor/eval_trace.json`; `data/monitor/forward_ledger.jsonl`; EVAL-GATED badge, validation chips, Validation panel; updated `irc monitor` output table row and new eval-command table rows
  - CLAUDE.md — `irc monitor` command updated with `eval_trace.json` + `forward_ledger.jsonl` outputs; new `irc eval monitor_signal` entry (free, in `--all`); `IRC_RUN_LIVE_LLM_EVAL=1 irc eval monitor_impact/monitor_narrative` with SKIPPED rc 3 / exclusion from `--all` / eval-live budget note; `IRC_RUN_LIVE_LLM_EVAL=1 uv run pytest -m live_llm` in Tests block
  - CONTEXT.md — full monitor-eval terminology section: `eval_trace.json`, `FundTraceBundle`, `StageHealth`, `GateDecision`, `published_state`, `EVAL_GATED`, validation badge/chip, forward ledger, `live_gated`, `eval-live`; M1 terms: eval corpus/case, impact/narrative scorer metrics, `citation_validity`/`citation_resolution`, `attribution_strength`/`supported_attribution`, `hallucination_rate`, eval-live paid surface, `live_llm` marker; `NO_CALL` cross-reference updated
  - docs/adr/0017-monitor-evidence-isolation.md — M0 data contracts (eval_trace unified pool design, forward ledger append-mode JSONL rationale) + M1 data contracts (versioned corpora contract, sole-paid-surface invariant)
  - CHANGELOG.md — M0 spine entry + M1 LLM suites entry (2026-06-16)
Missing coverage: none
