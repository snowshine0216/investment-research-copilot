Verdict: PASS

Subagent: sonnet
Source: Fallback used: manual step execution (no /verify skill needed; steps self-contained)
Entry point exercised:
  - uv run pytest tests/monitor/test_signal_property.py tests/monitor/test_factors_property.py tests/monitor/test_trend_property.py tests/monitor/test_factor_maps_oracle.py tests/monitor/test_news_factor_property.py -q  (x2)
  - uv run pytest tests/monitor -q
  - uv run python - (D2 recompute throwaway snippet)
  - grep -n GATING_STAGES src/irc/monitor/eval/gate.py
  - uv run pytest tests/monitor/eval/test_panel_rows.py -q
  - uv run irc --help
  - uv run irc eval --help

Observed behavior:
  - D1 determinism (hypothesis derandomize profile, offline, sub-second) — observed: 26 passed in 1.47s both runs; identical count and timing; derandomize=True profile registered in tests/monitor/conftest.py (verified by grep); hypothesis>=6.100 present in both [dependency-groups].dev and [project.optional-dependencies].dev in pyproject.toml.
  - D1+D2 full monitor suite green, fast, offline — observed: 335 passed, 7 skipped in 2.02s; no network calls; 7 skips are live-marker tests (expected).
  - D2 behavioral exercise (recompute path catches stale/malformed metadata) — observed: clean trace → `status=PASS, reasons=()`; corrupted composite (0.0 instead of ~0.556) → `status=FAIL, reasons=('composite',)`; missing `available_weight` key → `status=FAIL, reasons=('available_weight',)`. All three assertions passed without error.
  - No new eval registry stage — observed: `irc eval --help` shows the same STAGE list (monitor_signal, monitor_impact, monitor_narrative); no `deterministic_scoring` entry; confirmed by grep that `determinism.py` comment explicitly states the stage is never added to GATING_STAGES_*.
  - No gating stage — observed: `grep -n GATING_STAGES src/irc/monitor/eval/gate.py` returns only `GATING_STAGES_M0 = frozenset({"monitor_signal"})` and `GATING_STAGES_M1 = GATING_STAGES_M0 | frozenset({"monitor_impact", "monitor_narrative"})`; `deterministic_scoring` absent from both. `uv run pytest tests/monitor/eval/test_panel_rows.py -q` → 4 passed in 0.04s (guard test green).
  - CLI imports cleanly — observed: `uv run irc --help` exits 0; `uv run irc eval --help` exits 0.
  - Fully offline — observed: full monitor suite runs in 2.02s with no network; no live markers triggered; 7 skips are live-gated tests.
  - ValidationPanelRow frozen dataclass — confirmed by test_validation_panel_row_is_frozen_dataclass passing in monitor suite.
  - fund_id P0 fix — observed: recompute_signal_from_trace("008986", fund) correctly stamps rec.fund_id == "008986" (clean trace PASS test exercised directly).

Failures: none
