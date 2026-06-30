Verdict: PASS
(Was FAIL — 2 spec divergences found, fixed, and re-verified. See "Resolution" below.)
Subagent: sonnet (drift) + orchestrator override + sonnet (fix)
Plan checklist items: 22
Verified present in diff: 22 (the 2 SPEC divergences are now fixed to match §9 / §10)

## Override note

The drift subagent returned PASS by AMENDING the plan (commit `e1f1ffdb`) for two
divergences. Per drift-check rules, amending the plan is legal only when the *plan was
vague* — NOT to match an impl that diverges from a *specific* requirement. Both
divergences contradict explicit **spec** wording (§9, §10/§12), so the orchestrator
reverted the plan amendment (restored `001-plan.md` to `a2a5820`) and set Verdict: FAIL.
Routed to triage-fix before ship.

## Accepted (no action) — verified against the diff

- **Commit-label drift (Phase 4):** commits "Comp 4a–4d" / "Comp 6a–6d" implement the
  plan's Phase 4 (spec Comp 6) and Phase 6. Code correct; message label only.
- **Invariant `https://` vs `http://`** (`tests/monitor/test_report_v2_invariants.py:51`):
  deliberately allows the SVG `xmlns="http://www.w3.org/2000/svg"` required by Comp 3c
  inline SVG, while still blocking remote assets (`https://`, `<script>`). Sound.
- **Extra commit `954bc157`** (orchestrator ruff cleanup of report-v2 test imports).
- **`render_timeline.py` date header** (full `YYYY-MM-DD` vs plan's MM-DD trim): incidental
  presentation; test passes either way.

## FAIL findings — routed to triage-fix

1. **Task 5.1 / spec §9 — purchase tag format & open-fund tag (divergent from spec).**
   `src/irc/monitor/heat_fetch.py::purchase_tag_for` returns `"可申购"` for OPEN funds and
   bare `"限购"` for ALL restricted funds. Spec §9 is specific: `限购 ¥{cap}/日` when
   cap-restricted, bare `限购` only when status-restricted, and **"No tag when
   open/unknown."** Impl (a) shows a tag for open funds the spec said to omit, (b) drops
   the `¥{cap}/日` daily-cap amount.
   Evidence: `src/irc/monitor/heat_fetch.py:78-84` (`return "限购" if status else "可申购"`).
   Fix: `purchase_tag_for` → `限购 ¥{cap}/日` (cap-restricted; read cap from
   `_CAP_COL="日累计限定金额"`) / `限购` (status-restricted only) / None (open OR unknown).

2. **Task 4.3 / spec §10 — market-composite forward row not rendered (missing).**
   `evals/monitor_forward/metrics.py::build_metric_reports` returns only
   `[r_comp, r_bias, r_ic]` and places `market_composite_directional` ONLY in `details`
   (and only `if mc_rows:`). `monitor_cmd._predictive_panel_model:676` builds panel rows by
   iterating `entry.report.metrics` (the MetricReport list), so the market-composite row
   **never renders in the predictive panel** — and is absent entirely until matured rows
   carry the field. Spec §10: "Panel: `predictive_validity_panel_html` renders the new
   row (it will read `insufficient_data` until engine-3 days mature — shown honestly, like
   the others)"; §1: the honest ceiling "must be rendered, never hidden"; §12:
   "`market_composite_directional` present in report.json." This is the lynchpin Comp 6's
   visible payoff — missing.
   Evidence: `evals/monitor_forward/metrics.py:269-275` (3 reports; market row details-only,
   conditional); `src/irc/commands/monitor_cmd.py:676`.
   Fix: emit `market_composite_directional` as a `MetricReport` in the
   `build_metric_reports` return list (so the panel renders it), present even when immature
   (`insufficient_data` state), parallel to `raw_composite_directional`; keep the details
   block. Update report_count test 3→4 + the omit-when-none test; re-run the
   signature-change suite (predictive panel + render tests).

## Resolution (post-fix, re-verified by orchestrator)

Both FAIL findings fixed on branch (TDD, Sonnet fix subagent) and re-verified:

- **Finding 1 → fixed in `9716f19c`.** `purchase_tag_for` now returns `限购 ¥{cap}/日`
  (cap-restricted, cap read from `_CAP_COL`), bare `限购` (status-restricted only), and
  `None` when open OR unknown — matches spec §9. Confirmed in
  `src/irc/monitor/heat_fetch.py` (no `可申购` path remains).
- **Finding 2 → fixed in `962a5893`.** `build_metric_reports` now returns
  `[r_comp, r_bias, r_ic, r_mc]` — `market_composite_directional` is ALWAYS emitted as a
  `MetricReport` (insufficient_data when immature), so `_predictive_panel_model` (iterating
  `entry.report.metrics`) renders it as a panel row — matches spec §10/§12/§1.

Re-verification evidence (orchestrator-run):
- `tests/monitor/test_heat_fetch.py` + `tests/evals/test_monitor_forward_metrics.py` +
  `tests/evals/test_monitor_forward_runner.py` + `tests/monitor/test_report_v2_invariants.py`
  → 83 passed.
- Broad `tests/monitor/` + `tests/evals/` → 1069 passed, 12 skipped, 1 pre-existing
  unrelated FAIL (`test_dag_acyclic_check_true_for_valid_imports`; `fundamentals↔data`
  cycle, identical on main, untouched by this branch).
- Per-file `tests/commands/`: predictive_panel 6, market_composite 5, eval_wiring 7,
  monitor_cmd 10 — all pass.
- ruff clean on `heat_fetch.py`, `metrics.py`, and edited tests.
- Invariants intact: `_ENGINE_VERSION` "3"; published_state/gate/full-C unchanged; render_*
  pure; no `<script>`/`https://`/`基金概况` in report.

Verdict flipped FAIL → PASS. Cleared for ship.
