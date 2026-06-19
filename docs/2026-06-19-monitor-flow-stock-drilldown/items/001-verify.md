Verdict: PASS

Subagent: sonnet
Source: Fallback used: uv run python entry-point smoke
Entry point exercised:
  - `uv run python -c "..."` driving real pure-core functions (no mocks, no import-only):
    FactorInputs → build_factor_scores → compute_signal,
    holding_metrics.flow_band,
    render_drilldown.holdings_board_html / flow_rollup_html / drilldown_page_html,
    eval.structural.flow_reconciliation,
    eval.forward_score.score_forward (target_engine filter),
    evals/monitor_forward/runner._target_engine,
    eval.trace._SCHEMA_VERSION
  - `uv run irc monitor --help` (CLI wiring check)

Observed behavior:

  - (A) Flow drives the bias (D1/D2) —
    FlowAggregate(value=0.75, covered_weight_ratio=0.65) → FactorInputs(flow=...) →
    build_factor_scores("active_cn_equity", ...) → flow FactorScore: eligible=True,
    value=0.75, reason=''. compute_signal WITH flow: composite=0.6925 (ADD_BIAS,
    avail_wt=0.85). WITHOUT flow (flow=None): composite=0.6801 (ADD_BIAS, avail_wt=0.70).
    Delta=0.0124 > 0.001. 6-factor tuple confirmed:
    [trend, valuation, heat, macro_tilt, constituent, flow]. Flow wiring is live.

  - (B) Percent-point units / no inversion —
    flow_band(3.0)=1.0, flow_band(0.03)=0.0 (ratio canary in deadband — correct),
    flow_band(-3.0)=-1.0, flow_band(1.5)=0.5, flow_band(-1.5)=-0.5. All match D7.

  - (C) Per-stock board + roll-up render —
    Board HTML 569 chars. Snippet: `<td>72%</td><td>fairly_valued</td><td>3.50</td>...`
    and `<td>— <span class='na-reason'>pe_not_positive</span></td>` for negative PE;
    `<span class='na-reason'>flow_no_data</span>` for None flow. No 买入/卖出.
    Rollup: `资金流因子 = Σ(wᵢ·sᵢ)/Σ(wᵢ) = +1.0000 （覆盖 61% of 前五大；前五大 = 25% of 基金资产）· 综合 C = +0.6900 → ADD_BIAS`.
    drilldown_page_html(views) generates 1341-char full-page HTML. Lean language (→ ADD_BIAS)
    present. No imperative. — cells and na-reason spans confirmed.

  - (D) Reconciliation oracle has teeth —
    MATCH trace (board Σ=0.2, factor=0.2) → PASS.
    MISMATCH trace (board Σ=0.2, factor=0.9999) → FAIL:
      reasons=('board 0.2 != factor 0.9999',). Oracle FAILs on disagreement.
    NO-FLOW trace (no flow contribution in signal) → PASS (nothing to reconcile).

  - (E) Forward-eval engine isolation —
    Mixed ledger (2 engine="1" rows, 2 engine="2" rows) + target_engine="2":
    excl={'engine_mismatch': 2, 'null_signal_nav': 2} — the 2 engine="1" rows correctly
    excluded before prefilter. No engine_mismatch when target_engine=None (back-compat:
    excl={'null_signal_nav': 4}). _target_engine(["9","10"])="10" (numeric max, not
    lexicographic).

  - (F) Trace schema is "3" —
    _SCHEMA_VERSION='3'. PASS.

  - (CLI wiring) `uv run irc monitor --help` → Usage: irc monitor [OPTIONS] COMMAND [ARGS]...
    with `snapshot` subcommand visible. Command is registered.

Failures: none
