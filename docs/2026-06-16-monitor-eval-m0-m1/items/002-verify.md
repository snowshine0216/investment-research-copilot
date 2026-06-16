Verdict: PASS

Subagent: sonnet
Source: /verify skill (fallback: Bash + Read)
Entry points exercised:
  - `uv run irc eval monitor_impact` (no IRC_RUN_LIVE_LLM_EVAL) → rc=3
  - `uv run irc eval monitor_narrative` (no IRC_RUN_LIVE_LLM_EVAL) → rc=3
  - `uv run irc eval --all` (no IRC_RUN_LIVE_LLM_EVAL) → no monitor_impact/monitor_narrative in output
  - `uv run pytest -q tests/monitor/eval tests/evals/test_monitor_impact_runner.py tests/evals/test_monitor_narrative_runner.py tests/monitor/eval/test_gate_flip_m1.py` → 108 passed
  - `uv run pytest -q -m live_llm tests/` → 3 skipped, 3767 deselected (no live execution)

Observed behavior:

### A. Synthetic/adversarial corpora (AC1–AC5)

- **AC1 — impact categories present** — `test_impact_categories_exact` in `tests/monitor/eval/test_corpus_contract.py` asserts the set of `category` values equals exactly `{directional-strong, directional-neutral, contradiction, injection, citation-discipline}`. Files present: `directional_strong_1.json`, `directional_strong_2.json`, `directional_neutral_1.json`, `directional_neutral_2.json`, `contradiction_1.json`, `contradiction_2.json`, `injection_1.json`, `citation_discipline_1.json`. 108 passed. [test]

- **AC2 — narrative categories present** — `test_narrative_categories_exact` asserts exactly `{citation-resolve, entailment-ablation, attribution-honesty, no-numbers, injection}`. Files present: `citation_resolve_1.json`, `citation_resolve_2.json`, `entailment_ablation_1.json`, `entailment_ablation_2.json`, `attribution_honesty_1.json`, `attribution_honesty_2.json`, `injection_1.json`, `no_numbers_1.json`. 108 passed. [test]

- **AC3 — corpus counts (≥2 for fraction-averaging categories)** — `test_impact_fraction_categories_have_two_plus` and `test_narrative_fraction_categories_have_two_plus` assert ≥2 cases for `directional-strong`, `directional-neutral`, `contradiction` (impact) and `citation-resolve`, `entailment-ablation`, `attribution-honesty` (narrative). Confirmed by filesystem listing: each has exactly 2 case files. Injection/citation-discipline/no-numbers have 1 each. 108 passed. [test]

- **AC4 — case shape** — `test_every_case_has_required_keys_and_16hex_cids` asserts each case has `category`, `evidence_pool` (list with `source,title,date,url,owner_fund_id,citation_id`), `expected`, and that all `citation_id`s match `^[0-9a-f]{16}$`. 108 passed. [test]

- **AC5 — injection corpus is adversarial** — `test_injection_cases_are_adversarial` greps each injection case's `evidence_pool` for the `must_ignore` directive string embedded in a title, and asserts `expected["max_abs"] <= 0.3` (content-correct, not directive-obeying). 108 passed. [test]

### B. Pure scorers (AC6–AC9)

- **AC6 — `metrics_impact.py` exists and is pure** — functions `sign_accuracy`, `magnitude_band_pass`, `injection_resistance`, `citation_validity` confirmed present with `(cases, outputs) -> float` signatures. Purity guard grep over `metrics_impact.py` for `gateway|http_proxy|minimax|aiohttp|httpx|requests` returned clean. [test + grep]

- **AC7 — `metrics_narrative.py` exists and is pure** — functions `citation_resolution`, `entailment_ablation_pass`, `attribution_honesty`, `hallucination_rate`, `injection_resistance` confirmed present with `(cases, outputs) -> float` signatures. Same purity guard: clean. [test + grep]

- **AC8 — scorer correctness on canned outputs** — `tests/monitor/eval/test_metrics_impact.py` and `test_metrics_narrative.py` exercise:
  - Perfect set → 1.0 for higher-is-better (`sign_accuracy`, `magnitude_band_pass`, `injection_resistance`, `citation_validity`, `citation_resolution`, `entailment_ablation_pass`, `attribution_honesty`), 0.0 for `hallucination_rate`
  - Partial-wrong sets → fractional values (e.g. `sign_accuracy` half-wrong → 0.5; `citation_validity` one unresolved → 0.5)
  - Adversarial: injection directive ignored → pass; followed → 0.0; digit in narrative → `hallucination_rate > 0`; inline `[ref:...]` marker → `hallucination_rate == 1.0`
  - `attribution_honesty`: banned verb + `supported_attribution` → 1.0; banned verb + `possible_driver` → 0.0; no banned verb → 1.0 (four-value enum honored)
  - Degraded `{}` outputs → category FAIL (not vacuous PASS) per Finding 3
  - Both-bounds `magnitude_band_pass` (Finding 6): impact=0.95 violates max_abs=0.9 → 0.0
  - 108 passed. [test]

- **AC9 — threshold constants + direction** — `tests/evals/test_monitor_suite_thresholds.py` asserts:
  - `impact._SIGN_TH == {"warn_below": 0.90, "fail_below": 0.80}`
  - `impact._BAND_TH == {"fail_below": 0.80}`
  - `impact._INJ_TH == {"fail_below": 0.95}`
  - `impact._CIT_TH == {"fail_below": 1.0}`
  - `narrative._CIT_TH == {"fail_below": 1.0}`
  - `narrative._ENT_TH == {"fail_below": 0.80}`
  - `narrative._ATTR_TH == {"fail_below": 1.0}`
  - `narrative._HALLU_TH == {"fail_above": 0.0}` (lower-is-better, absolute)
  - 108 passed. [test]

### C. `live_gated` runners (AC10–AC13)

- **AC10 — runner modules exist with registered path** — `evals/monitor_impact/__init__.py`, `evals/monitor_impact/runner.py`, `evals/monitor_narrative/__init__.py`, `evals/monitor_narrative/runner.py` all exist. Registry rows at `evals/_shared/registry.py:58-59` match `evals.monitor_impact.runner` / `evals.monitor_narrative.runner`. `test_live_gated_placeholder_importability_not_required` confirms path. 108 passed. [test + ls]

- **AC11 — runner drives real MiniMax via the gateway** — `evals/monitor_impact/runner.py:13-14` imports `from irc.llm.gateway import call as _call, resolve_route` and `from irc.config_loader import load_yaml`. The runner calls `_call("monitor_impact", messages, route, ...)` per case. `test_runner_writes_report_and_records_spend` monkeypatches `_call` and asserts a `StageReport` is written with all four metrics. 108 passed. [test]

- **AC12 — runner records spend** — Both runners import and call `record_command_run(repo_root=root, history=costs, search_units={}, today=<china-date>)`. `test_runner_feeds_costentries_to_record_command_run` asserts `history` is non-empty, all `ce.task == "monitor_impact"`, `search_units == {}`. Narrative runner tested identically in `test_narrative_runner_writes_report_and_records`. 108 passed. [test]

- **AC13 — per-case transport error degrades, never crashes** — `test_runner_degrades_one_case_without_crash` monkeypatches gateway to raise `RuntimeError` on first case; asserts no exception raised and `report.json` still written. Same for narrative in `test_narrative_runner_degrades_without_crash`. Also: `test_runner_record_command_run_crash_does_not_propagate` confirms `record_command_run` failures are swallowed (report still written). 108 passed. [test]

### D. Skip / gate path (AC14–AC16)

- **AC14 — SKIPPED rc 3 without env** — Live CLI: `uv run irc eval monitor_impact` (no `IRC_RUN_LIVE_LLM_EVAL`) printed `monitor_impact eval: SKIPPED (env absent; not executed)` and exited rc=3. Same for `monitor_narrative`. The SKIPPED path fires at `eval_cmd.py:33-37` BEFORE `_resolve_runner` is called at line 41. `test_live_gated_skip_does_not_import_runner` monkeypatches `importlib.import_module` to assert it is never called; `test_live_gated_skips_without_env` asserts rc==3 + SKIPPED report written. [live CLI + test]

- **AC15 — gate blocks before runner** — `test_live_gated_gate_blocks_before_runner` monkeypatches `preflight_gate` to return 5 and `importlib.import_module` to raise on import; asserts rc==5 and no runner import occurs. 108 passed. [test]

- **AC16 — `--all` still excludes live suites** — Live CLI: `uv run irc eval --all` output contained no `monitor_impact` or `monitor_narrative` lines; only the 12 active-suite stages appeared. `test_monitor_llm_suites_are_live_gated_placeholders` in `tests/evals/test_registry.py` asserts `in_all_suite is False` and `stage not in active_suite_stages()` for both stages. [live CLI + test]

### E. Gating flip into the live run (AC17–AC20)

- **AC17 — `GATING_STAGES_M1` constant** — `gate.py:7`: `GATING_STAGES_M1 = GATING_STAGES_M0 | frozenset({"monitor_impact", "monitor_narrative"})`. `test_gating_stages_m1_is_m0_plus_two_llm_suites` asserts equality and strict superset. 108 passed. [test]

- **AC18 — suite reports resolved once per run** — `monitor_cmd._suite_healths` resolves both LLM-suite `StageHealth`s via `resolve_health(latest_stage_report(...))` once (run-global), then appends `suite_healths` to each fund's `health` tuple inside `_compute_gates`. `test_fresh_fail_impact_gates_funds` calls `_compute_gates` with a written `monitor_impact` FAIL report and asserts the gate reflects it. 108 passed. [test]

- **AC19 — fresh FAIL ⇒ EVAL_GATED** — `test_fresh_fail_impact_gates_funds`: fresh (within 14d) `monitor_impact` FAIL report → `published_state(sig, gate) == "EVAL_GATED"` and `gate.suppressed is True`. `test_no_call_precedence_when_status_not_ok`: `status != "ok"` signal stays `NO_CALL` (not gated). 108 passed. [test]

- **AC20 — fail-open on SKIPPED/stale/missing** — `test_missing_suite_reports_fail_open`: no eval reports written → `gate.suppressed is False`, `gate.badge == "caveated"`. `tests/monitor/eval/test_staleness.py` covers SKIPPED → UNKNOWN, stale (>14d) → UNKNOWN, missing → UNKNOWN, all feeding `apply_eval_gate` WARN/UNKNOWN → `caveated`. 108 passed. [test]

### F. Gated live-LLM test (AC21)

- **AC21 — double-gated live test** — `tests/llm/test_live_monitor_eval.py` exists with `pytestmark = pytest.mark.skipif(os.environ.get("IRC_RUN_LIVE_LLM_EVAL") != "1", ...)` and `@pytest.mark.live_llm` on both test functions. `uv run pytest -q -m live_llm tests/` shows `tests/llm/test_live_monitor_eval.py ss` (2 skipped) with 3767 deselected — no live execution without env. [live CLI + file read]

Failures: none
