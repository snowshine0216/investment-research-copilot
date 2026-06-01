Verdict: PASS

Subagent: sonnet
Plan checklist items: 33
Verified present in diff: 33

## Verification summary

All 9 planned files touched; all 33 plan steps accounted for in the diff.

### Specific confirmations (per task instructions)

- `inputs_build.py` — contains `_build_input` verbatim (63 lines; body byte-for-byte matches plan §Task 1 Step 2 listing). CONFIRMED.
- `opportunity_cmd.py` — dropped `from irc.opportunity.inputs_loader import populate_inputs` (now unused after move); added `from irc.opportunity.inputs_build import _build_input`; deleted 52-line local `def _build_input` body. CONFIRMED.
- `fund_eval.py` — frozen `FundEval` + `EvalItem` dataclasses, `evaluate_fund`/`evaluate_funds`, `render_fund_eval_md`/`render_fund_eval_json`; no I/O in file. CONFIRMED.
- `fund_eval_cmd.py` — `duckdb.connect(str(db), read_only=True)`; pre-check `db.exists()` returns rc=2 with error message; `_instr_by_id` loads universe; `load_active_fund_cache` loads snapshots; `atomic_write_text` for both `.md` and `.json`. CONFIRMED.
- `cli.py` — `@main.command("eval-funds")` with all 6 options (`--ids`, `--ids-file`, `--quarter`, `--role`, `--db`, `--out`) + `--repo-root`; lazy-imports `run_eval_funds`. CONFIRMED.
- `README.md` — one line added in the command table under `irc opportunity` row. CONFIRMED.
- `CLAUDE.md` — one line added in the `bash` Commands block after `irc opportunity`. CONFIRMED.

## Drift findings

### Finding 1 — Deviation (a): monkeypatch target in test_opportunity_cmd.py
- Plan ref: Task 1 Step 4 (keep `irc.commands.opportunity_cmd._build_input` resolvable for existing tests)
- Classification: divergent (test-only, forced by extraction)
- Evidence: `tests/commands/test_opportunity_cmd.py` diff — exactly 2 lines changed (line 887): `"irc.commands.opportunity_cmd.populate_inputs"` → `"irc.opportunity.inputs_build.populate_inputs"`. No other changes in that file.
- Judgment: FORCED by extraction. After the move, `populate_inputs` is only reachable at `irc.opportunity.inputs_build`, not re-exported through `opportunity_cmd`. The monkeypatch must track the real import location to intercept the right name. Acceptable test-input adjustment.
- Action: plan amended inline under Task 1 Step 4 with rationale. Resolved.

### Finding 2 — Deviation: EvalItem/evaluate_funds omitted from test_fund_eval.py imports
- Plan ref: Task 2A Step 1 (import block listed `EvalItem`, `evaluate_funds`)
- Classification: divergent (small, vague plan)
- Evidence: `tests/opportunity/test_fund_eval.py` imports only `FundEval`, `evaluate_fund`, `render_fund_eval_json`, `render_fund_eval_md`. `EvalItem` and `evaluate_funds` are absent. Neither is exercised by any of the 4 unit tests in that file (confirmed: `grep evaluate_funds tests/` returns exit 1). Both are exercised by `test_fund_eval_cmd.py`'s integration test via `run_eval_funds`.
- Judgment: The plan's import block was aspirational — none of the 4 listed unit tests (`test_evaluate_fund_*`) used `EvalItem` or `evaluate_funds`. Removing unused imports is correct (ruff F401). `evaluate_funds` sorting is covered indirectly by the integration test. Small divergence, vague plan.
- Action: plan amended inline under Task 2A Step 1 with rationale. Resolved.

### Finding 3 — Deviation (b): integration test seeds cn_etf/cn_on_exchange instead of cn_equity_fund/cn_off_exchange
- Plan ref: Task 3A Step 1 (`_seed_db` / `_seed_universe` seed code)
- Classification: divergent (test-input only, vague plan note "adjust seeded NAV slope if needed")
- Evidence: `tests/commands/test_fund_eval_cmd.py` — `_seed_db` inserts `asset_class="cn_etf", market="cn_on_exchange"`; `_seed_universe` writes `asset_class: cn_etf, market: cn_on_exchange`. Comment in diff: "Use cn_etf / cn_on_exchange so passive quality path applies (avoids aum_stability_pct requirement of the active-fund path)." No changes to `src/irc/opportunity/` except the two new files (`fund_eval.py`, `inputs_build.py`). No classification thresholds altered.
- Judgment: Active-fund path requires `aum_stability_pct` which is NaN in the `instruments` DB schema → `product_quality_state=weak` → `opportunity_state` never reaches `core_dca`. The adjustment is confined to the test seed. Production logic is unchanged. The integration test still proves the end-to-end `core_dca` path (spec §5: "expected verdict for the seeded fund"). Acceptable test-input adjustment.
- Action: plan amended inline under Task 3A Step 1 with rationale. Resolved.

### Non-drift: PROGRESS.md updated
- `docs/2026-06-01-eval-funds-command/PROGRESS.md` — status cells updated from ⏳ to ✅ for impl phase. Incidental housekeeping, not a plan step. Accepted.

## Plan amendment commits
(to be filled after commit)
