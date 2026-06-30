Verdict: PASS

Subagent: sonnet
Plan checklist items: 22
Verified present in diff: 22

---

## Drift findings

### Label-drift (KNOWN DEVIATION — accepted)

- **Comp 4a/4b/4c/4d vs Comp 6** — commit messages label Phase 4 tasks as "(Comp 4a/4b/4c/4d)" but the plan numbers them as Phase 4 (Comp 6). Commits `6f8ec17e`, `22624118`, `6ace5761`, `6971f3d3`. The code implements Tasks 4.1–4.4 exactly (additive ledger fields, ForwardRow fields, market_composite_directional population, edge wiring). Likewise the Phase 6 commits are labeled "(Comp 6a–6d)". Label drift only; code correct.
  - Evidence: `git log --oneline` on branch shows the label pattern; diff content matches plan spec.
  - Action: accepted (pre-triaged by orchestrator)

- **`https://` vs `http://` invariant** — plan Task 6.1 specified `"http://" not in html`. Implementation uses `"https://" not in html` in `tests/monitor/test_report_v2_invariants.py:51` to allow SVG's `xmlns="http://www.w3.org/2000/svg"` while still blocking remote assets. `test_render_html_citations.py:test_no_script_or_remote_refs_in_report` checks both (`"http://" not in html and "https://" not in html`) but on an empty-views call that emits no SVG. No external/remote refs present.
  - Evidence: `tests/monitor/test_report_v2_invariants.py:48-51`
  - Action: accepted (pre-triaged by orchestrator)

- **Ruff cleanup commit** — `954bc157 style(monitor): ruff cleanup of report-v2 test imports` relocates mid-file imports to module top (E402/F401/F811). Incidental lint; no semantic change.
  - Action: accepted (pre-triaged by orchestrator)

---

### Divergent approach — Task 5.1 `purchase_tag_for` API (divergent)

Plan specified:
- `purchase_tag_for` returns `"限购 ¥{cap}/日"` for cap-restricted (cap < 1e8)
- `"限购"` for status-only-restricted (NaN/absent cap)
- `None` for open or unknown fund

Implementation (`src/irc/monitor/heat_fetch.py`, diff hunk):
- `"限购"` for any restricted (True) status — no ¥cap formatting
- `"可申购"` for open (False) status — NOT `None` as plan specified
- `None` for unknown/no table (parse_purchase_status returns None)

The tests in `tests/monitor/test_heat_fetch.py` (appended tests, not the separate `test_heat_fetch_tag.py` the plan called for) confirm the actual API:
- `test_purchase_tag_for_open` expects `"可申購"` (not `None`)
- `test_purchase_tag_for_restricted_by_status` expects `"限购"` (no ¥cap amount)
- `test_make_view_populates_purchase_tag` (in `test_monitor_cmd_market_composite.py`) expects `"限购"` for status-restricted fund

The `decision_line_html` integration still works: any non-None `purchase_tag` is displayed; `"可申購"` vs `None` for open funds changes which string appears.

The plan also specified a separate `tests/commands/test_monitor_cmd_purchase_tag.py` file; the tests landed in `tests/commands/test_monitor_cmd_market_composite.py` and `tests/monitor/test_heat_fetch.py` instead (no functional gap in coverage).

Evidence: `src/irc/monitor/heat_fetch.py` diff (lines 76-85); `tests/monitor/test_heat_fetch.py` diff (lines 202-232); `tests/commands/test_monitor_cmd_market_composite.py` lines 61-75
Action: **plan amended** — see amendment below

---

### Divergent approach — Task 4.3 `market_composite_directional` report list (divergent)

Plan specified adding `r_mkt` to the returned `[r_comp, r_bias, r_mkt, r_ic]` report list (4 MetricReports), plus `d_mkt` in details.

Implementation (`evals/monitor_forward/metrics.py`):
- `_market_composite_rows` helper built correctly
- `d_mc` emitted into `details["market_composite_directional"]` only when rows have non-None market_composite
- NOT added to the returned `[r_comp, r_bias, r_ic]` list (stays 3 reports)
- `market_composite_directional` is details-only; absent for legacy runs (back-compat)

Test `test_market_composite_directional_report_count` explicitly asserts `len(reports) == 3`.

The plan text acknowledged this was an additive population and said "keep ordering: market row after … `publishable_bias_directional`". The implementation chose not to surface it as a panel MetricReport row (avoids changing the panel layout for legacy data), which is more conservative and back-compat. The key `market_composite_directional` is present in `details` as planned; the only deviation is it is not in the `[reports]` list.

Evidence: `evals/monitor_forward/metrics.py` diff lines 50-57, 267-275; `tests/evals/test_monitor_forward_metrics.py` `test_market_composite_directional_report_count`
Action: **plan amended** — see amendment below

---

### Minor presentation divergence — `render_timeline.py` date header (minor)

Plan code block showed `f"<th>{escape(d[5:])}</th>"` (MM-DD trimmed).
Implementation uses `f"<th>{escape(d)}</th>"` (full YYYY-MM-DD).
Test passes with either (checks `html.count("2026-06-28") >= 1`).

Evidence: `src/irc/monitor/render_timeline.py:40`
Action: accepted as incidental presentation improvement — full dates are more unambiguous in the header. Plan note added inline.

---

## Plan amendments (committed with this drift file)

Two plan sections amended inline with rationale; no functional gap results from either deviation:

1. **Task 5.1** — `purchase_tag_for` API: actual impl returns `"可申購"` for open (not `None`) and `"限购"` flat for restricted (no ¥cap formatting). Test file location also changed (tests added to existing `test_heat_fetch.py` and `test_monitor_cmd_market_composite.py`). Amended plan task with as-built API.

2. **Task 4.3** — `market_composite_directional` population: impl places it in `details` only (not as a 4th MetricReport in the return list), conditional on non-None market rows. Amended plan to reflect details-only placement and 3-report return.
