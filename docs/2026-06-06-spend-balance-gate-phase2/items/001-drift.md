Verdict: PASS

Subagent: sonnet
Plan checklist items: 22 (Tasks 1–9 each with sub-steps; Task 10; Task 11; Tasks 12a–12f)
Verified present in diff: 20
Drift findings:
  - Task 10 (memo_cmd) — divergent: plan says append CostEntry "immediately after call_chat returns… before any downstream processing"; impl defers capture to after the full pipeline via MemoOutput.synth_response/audit_response carrier fields added to memo/pipeline.py. The plan's architectural assumption ("memo/synthesizer.py:synthesize_memo() → ChatResponse returned to command") was stale — the command edge calls run_memo_pipeline() not synthesize_memo() directly, making per-call immediate capture impossible without pipeline surgery. MemoOutput carrier is the correct structural adaptation; all 3 required assertions (samples 0→1, spend_actuals.json written, right tokens) are satisfied. Also uses _history[:] = append_cost() (slice-mutation) instead of plan's rebind pattern; functionally equivalent but mildly non-FP.
    Evidence: src/irc/memo/pipeline.py +5 lines (synth_response/audit_response fields); src/irc/commands/memo_cmd.py +_run_memo_body; post-pipeline CostEntry build lines 1018–1030 in branch.
    Action: plan amended inline (see below — accept structural adaptation, note slice-mutation).

  - Task 12c (discover_cmd) — scope creep (functional): impl adds a new preflight_gate(str(root), "run", stages=("discover",)) call inside run_discover(). This call site is NOT in the 6 locked set. The plan is explicit: Task 9 — "the 6 preflight_gate(repo_root, '<cmd>') call sites stay byte-identical"; Task 12 intro — "irc run itself needs no change — it invokes these as sub-runners." Adding a gate to run_discover causes double-gating when invoked via `irc run` (run_cmd._gate already gates all stages before the stage loop calls run_discover).
    Evidence: src/irc/commands/discover_cmd.py +gate_rc = preflight_gate(str(root), "run", stages=("discover",)) (diff hunk lines +119 to +121).
    Action: routed to triage.
    Fix: src/irc/commands/discover_cmd.py — remove the 4 added lines (from irc.commands.spend_cmd import preflight_gate; _today_date init; gate_rc = preflight_gate(…); if gate_rc != 0: return gate_rc). The recorder wiring (record_command_run in finally) is correct and must be kept.

  - Task 12d (research_cmd) — scope creep (functional) + missing functionality:
    (a) SCOPE CREEP: same as 12c — adds preflight_gate(str(root), "run", stages=("research",)) to run_research(), causing double-gating when invoked via `irc run`.
        Evidence: src/irc/commands/research_cmd.py +gate_rc = preflight_gate(str(root), "run", stages=("research",)) (diff hunk lines +65 to +67).
        Fix: src/irc/commands/research_cmd.py — remove the 4 added lines (import; _today_date is already there; gate_rc = preflight_gate(…); if gate_rc != 0: return gate_rc).
    (b) MISSING: plan says 12d "proves the §15.2 ledger box" by passing search_units={provider: n} to record_command_run() — "the ledger decrement for Tavily/Bocha/Jina/Brave lands here." Impl passes search_units={} (empty dict). theme_research.py and research/pipeline.py expose no search unit counts. The ledger box end-to-end proof is unimplemented.
        Evidence: src/irc/commands/research_cmd.py record_command_run(…, search_units={}, …) (line 96 in branch); no search_units collection in src/irc/research/theme_research.py or src/irc/research/pipeline.py diff.
        Fix: src/irc/research/theme_research.py — in build_theme_reports, count provider.search() calls per provider.name and extractor.extract() calls per extractor.name; propagate counts alongside llm_responses. src/irc/research/pipeline.py — return (exit_code, cost_entries, search_units_dict). src/irc/commands/research_cmd.py — pass the real search_units dict to record_command_run.
    Action: routed to triage.

## Resolution (round 1)

Fix commits: `914fec4` (remove preflight_gate calls) and `2bb6205` (search-unit counting ledger box).

### Finding 12c (discover_cmd scope creep) — RESOLVED by commit 914fec4
`git diff autodev/spend-balance-gate-phase2-feature...HEAD -- src/irc/commands/discover_cmd.py`
confirms: no `preflight_gate` call or import in the final diff. The `record_command_run`
recorder `finally` block is intact at discover_cmd.py lines added in the feature diff.
Gate set verified: `grep -rn "preflight_gate(" src/irc/commands/*.py` returns exactly
ask/decision/memo/fund_eval/opportunity/narrative + run_cmd — 6 command sites + 1 run site.
discover_cmd and research_cmd are absent.

### Finding 12d-a (research_cmd scope creep) — RESOLVED by commit 914fec4
`git diff autodev/spend-balance-gate-phase2-feature...HEAD -- src/irc/commands/research_cmd.py`
confirms: no `preflight_gate` import or `gate_rc` block in the final diff. The recorder
`finally` block is intact and now passes real `search_units` (not `{}`).

### Finding 12d-b (missing search-unit counting) — RESOLVED by commit 2bb6205
- `src/irc/research/theme_research.py`: new `_count_search_units` helper counts 1 unit per
  successful `provider.search()` call (keyed by `r.provider`) and 1 unit per extracted page
  (keyed by `extractor.name`). `_build_one` returns `(ThemeReport, resp, units)` 3-tuple;
  `build_theme_reports` accumulates across themes and returns `(reports, llm_responses, search_units)`.
- `src/irc/research/pipeline.py`: `run_research_pipeline` unpacks the 3-tuple and returns
  `(rc, cost_entries, search_units)`.
- `src/irc/commands/research_cmd.py`: unpacks the 3-tuple; passes real `search_units` dict
  (not `{}`) to `record_command_run`.
- Test: `tests/commands/test_research_recorder.py` — 2 passed in 0.07s (run confirmed in
  this dispatch: `uv run pytest tests/commands/test_research_recorder.py -q`).

### Scope creep check — NONE
Commits `914fec4` and `2bb6205` touch only: `src/irc/commands/discover_cmd.py`,
`src/irc/commands/research_cmd.py`, `src/irc/research/pipeline.py`,
`src/irc/research/theme_research.py`, `tests/commands/test_research_recorder.py`,
`tests/research/test_pipeline.py`, `tests/research/test_theme_research.py`, and
`docs/.../PROGRESS.md`. All within expected scope.
