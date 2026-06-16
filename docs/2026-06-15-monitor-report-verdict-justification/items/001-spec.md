# 001 — Re-surface verdict justification in the monitor report renderer

Status: spec authored from approved brainstorming design (this session). Pre-grilled.

## Goal

Make each per-fund card in `outputs/<date>/monitor/report.html` explain *why* the fund
earned its bias, using data the signal engine already computes. Five additions/fixes,
matching mockup `monitor_card_redesign_mockup`.

## Background / current state (verified)

- `compute_signal` (`src/irc/monitor/signal.py:68`) returns a `SignalRecord` with:
  `status`, `bias`, `composite` (C, 4dp), `signal_confidence` (4dp), `available_weight`,
  `present_families`, `contributions: tuple[FactorContribution,...]`, `divergence_codes`.
- `FactorContribution` (`src/irc/monitor/types.py:46`): `name, renorm_weight (w'ᵢ),
  value (sᵢ), contribution (w'ᵢ·sᵢ), confidence, eligible, reason`. **Only the present
  (eligible & non-None) factors are in `contributions`.**
- `_make_view` (`src/irc/commands/monitor_cmd.py:211`) builds `FundView` with the full
  `SignalRecord` on `.signal`, plus `missing_factor_reasons = (f"{s.name}: {s.reason}"
  for s in scores if not s.eligible)`. **`return_table` is hardcoded `{}`.** The full
  ordered `scores: tuple[FactorScore,...]` is passed into `_make_view` but only used to
  build `missing_factor_reasons`.
- `render_html.py` renders per card: `<h2>`+badge, SVG chart, `_returns_html` (empty),
  `_narrative_html` (price_action ++ signal_rationale ++ risk merged into identical
  `<p>`s), `<ul class='missing'>`. **No factor table, no composite, no verdict reasoning,
  no labeled risk.**
- `trend.py` computes only a single 60d return internally (`_r60`); the
  `[5,20,60,120,250]d` window table the design references is computed nowhere → that is
  why `return_table` is empty.
- `signal.json` on disk is intentionally lossy (`{status, bias}` per fund) — it is the
  prior-signal contract for the changed-since-yesterday flag. **Do not change it.**

## Requirements

### R1 — Verdict block (top of each card)
- A **deterministic** one-line clause derived from numbers only (renders even if the
  narrative degraded):
  - `status == ok`: `综合分 C = <C> 落在 [<sell>, <buy>] → <bias label>` with the band
    relationship made explicit (≥ buy → ADD_BIAS; ≤ sell → REDUCE_BIAS; else within
    dead-band → NEUTRAL).
  - `status != ok`: state the gate failure, e.g. `insufficient_evidence — trend present
    but <n> family / available_weight <w> < 0.60 → NO_CALL`, or `low_confidence —
    signal_confidence <c> < <min> → NO_CALL`. Use the available `SignalRecord` fields.
- The **concise MiniMax comment**: render `narrative.signal_rationale_commentary`
  (the LLM's "why this signal"), capped to the lead claim(s) — keep it short. Visually
  set apart (quoted prose). Each claim's `[ref:…]` markers appended deterministically
  (existing `_claim_html` pattern). If `narrative.status != "ok"`, show the degraded note
  and rely on the deterministic clause alone.

### R2 — Factor-contribution table (deterministic)
- Canonical factor order: `["trend", "valuation", "heat", "macro_tilt", "constituent"]`.
- Present factors (from `signal.contributions`): columns `因子 | 值 sᵢ | 权重 w'ᵢ |
  贡献 w'ᵢ·sᵢ | 置信 | 状态(fresh/cached)`. Round values to 2–4 dp consistently.
- N/A factors (in canonical order but absent from `contributions`): a dimmed row with
  `—` in numeric columns and the eligibility reason in the 状态 column. Source the reason
  from the full factor-score set (see R6 wiring) so the reason text is structured, not
  string-split from `missing_factor_reasons`.
- Footer row: `综合 C = <composite> · 置信 <signal_confidence> · available wt
  <available_weight> · families: <present_families>`.
- Replaces the bare `<ul class='missing'>`.

### R3 — Returns table (fix empty `{}`)
- New **pure** helper computing total returns over `[5,20,60,120,250]` trading-day
  windows from the acc-NAV series (`COALESCE(nav_acc, nav)` is already what
  `nav.acc_series` carries). Each window: `acc[-1]/acc[-1-w] - 1`, or N/A / `—` when
  fewer than `w+1` points. Round to a fixed precision for byte-stability.
- Wire the result into `FundView.return_table` at the edge (`_make_view`); render it as a
  labeled table.

### R4 — Risk & divergence block (labeled, distinct)
- Map each `divergence_code` to a fixed plain-language caveat:
  `trend_valuation_conflict`, `trend_macro_conflict`, `low_factor_agreement` →
  human-readable Chinese strings (deterministic map in code).
- Plus the MiniMax `narrative.risk_commentary` claims (with `[ref:…]`).
- Render under a distinct labeled, color-set heading (mockup uses a warning surface).
  If no divergence codes and no risk claims, render nothing (or a muted "无显著风险信号").

### R5 — Sectioned narrative
- Split `_narrative_html`: `price_action_commentary` in its own labeled section
  (e.g. 价格走势 / Price action). `signal_rationale_commentary` now lives in the verdict
  block (R1); `risk_commentary` now lives in the risk block (R4). No undifferentiated
  merge. Avoid duplicating the same claim in two places.

### R6 — Wiring (edge only, `monitor_cmd.py` + `render_types.py`)
- `FundView` gains the full ordered factor data needed for the all-factors table
  (cleanest: add `factor_scores: tuple[FactorScore, ...]` carrying every factor incl.
  N/A with its reason; keep `signal.contributions` for the numeric rows). Populate it in
  `_make_view` from the `scores` already passed in.
- Populate `return_table` in `_make_view` from the new returns helper (needs the acc-NAV
  series — `nav.acc_series`).
- `_make_view` and any new helpers stay at the edge; all render + returns + divergence-map
  logic stays pure.

## Invariants to preserve (tests must guard)

- **Byte-stable** render given identical inputs (incl. injected `prior_signal`, `now`).
  Refresh the golden-file fixture/test.
- **XSS:** every untrusted title/snippet/url and all LLM prose HTML-escaped (existing
  hostile-title fixture extended to the new sections).
- **H3 universal rows:** every fund appears in summary + has a card, incl. NO_CALL /
  data-gap funds.
- **Citation closure:** set of rendered `[ref:…]` anchors == set of evidence-appendix ids
  (no orphans, no uncited clutter). The verdict/risk/narrative refs all resolve.
- `NO_CALL` (`bias=null`) ≠ `NEUTRAL` — the badge + verdict block must distinguish them.

## File touchpoints (indicative — plan finalizes)

- `src/irc/monitor/returns.py` — NEW, pure: acc-NAV series → `{window: return}`. TDD.
- `src/irc/monitor/render_types.py` — `FundView` += `factor_scores`; `return_table` used.
- `src/irc/monitor/render_html.py` — bulk: `_verdict_block`, `_factor_table`,
  `_risk_block`, `_returns_html` (populated), sectioned narrative, CSS. Canonical factor
  order + divergence→caveat map live here (pure).
- `src/irc/commands/monitor_cmd.py` — `_make_view` wiring (factor_scores + return_table).
- Tests mirror each: `tests/irc/monitor/test_returns.py`,
  `tests/irc/monitor/test_render_html.py` (extend), golden fixture refresh.

## Exit gate (acceptance)

Regenerate today's `outputs/2026-06-15/monitor/report.html`. Prefer reusing cached
`impacts.json` / `narrative.json` (hash-stable same-day rerun reuses them per design §6 →
no new LLM spend); if a full `uv run irc monitor` is blocked (keys / spend gate /
network), use a render-from-cache path that recomputes the pure factor→signal stage from
cached impacts + NAV and re-renders. Confirm each per-fund card shows the verdict block,
factor table (incl. N/A rows), returns table, and risk block, matching the mockup.
Capture evidence (structural assertions + a look at the rendered card).

## TDD

Red → green → refactor. Test file mirrors source. Pure helpers unit-tested without mocks;
the `_make_view` wiring is the only edge change and is exercised via the render golden +
a small integration assertion.
