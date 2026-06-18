# SKIPPED — Monitor valuation + heat factor wiring

No IN-scope items were skipped. All three vertical slices from the design spec's §9 are IN scope.

## Deferred (by spec design, not an autodev skip)

- **AUM-Δ heat leg** — the overheated `−1.0` heat tier requires a per-fund QoQ AUM-Δ series.
  No per-fund live source exists (`ak.fund_scale_change_em` is aggregate-market only). Item 003
  ships `aum_delta_pct=None`; `heat_score` already handles this and reduces to the restriction
  leg (`−0.5` crowded / `+0.3` calm). Unblock path: a per-fund AUM-history data source lands →
  a future slice wires `aum_delta_pct`. Tracked in MASTER-SPEC "Out of scope".
