# Monitor Report v2 — market composite anchor, news overlay, charts, annotations, freshness

Status: design (grilled 2026-06-30 via grill-with-docs)
Scope: `irc monitor` report + command + forward-eval ledger. **No scoring/engine-version change** (engine stays 3). Base: current `main` (post #178/#179/#180/#181).

## 1. Problem & reframe

The original ask (annotations, charts, robustness chip, citations, freshness) was reframed during grilling around one realization: **the report's job is to produce a *reliable, fact-backed number* a reader can act on, not a "fragile" sticker.** A "forever fragile" label is useless for deciding.

The codebase already has the bones. `signal.py` `_FAMILY_OF` classifies every factor:

| family | factors | nature |
|---|---|---|
| price-momentum / valuation / capital-flow / crowding | `trend`, `valuation`, `flow`, `heat` | **market data — deterministic, reproducible** |
| **news** | `macro_tilt`, `constituent` | **LLM-scored — volatile (flips on same-day re-fetch, [[project-monitor-macro-tilt-instability]])** |

So the reliable number is the **market composite** (the four market-data factors, news excluded & renormalized), and the volatile part is the **news overlay** (macro + constituent). Both terms are now in CONTEXT.md.

**Honest ceiling (must be rendered, never hidden):** the only component with a *measured* forward hit-rate is **trend-only** (the retro evidence-free sub-composite — `backtest.py`: "Trend is the only present factor") at **~0.54 (n≈17,919)** — barely above coin-flip. The market composite (4-factor) is fact-backed but its forward edge is **unmeasured** until it's logged + matures (Component 6). The full composite's forward eval is still `insufficient_data` (engine v1→v3 transition). The report must say this plainly.

## 2. Non-goals (hard)

- No change to composite-`C` math, factor weights, gating, `published_state`, or `_ENGINE_VERSION` (stays 3). Market composite / news overlay / annotations are **render-derived**, never scoring inputs.
- The **full composite `C` stays the canonical published/tracked signal** — header badge, `monitor.json`, `forward_ledger.raw_composite`, the gate, `EVAL_GATED`, the validation panel — all unchanged.
- `render_report` and every `render_*` stay PURE (no I/O, no JS, no remote refs). All new I/O stays in `monitor_cmd` / the `evals/` runner.
- No new network or LLM calls (annotations rule-based; charts reuse run data; market composite is render-derived).

## 3. Glossary (added to CONTEXT.md during grilling)

- **Market composite (市场面综合分)** — render-time composite over `trend`/`valuation`/`flow`/`heat` (news family excluded, weights renormalized). The brief's fact-backed decision anchor; render-derived only. **Distinct** from the trend-only **evidence-free sub-composite / "deterministic core"** (the existing retro/eval term — a *smaller* subset, the one measured at ~0.54).
- **News overlay (新闻叠加)** — the `macro_tilt`+`constituent` contribution, surfaced as the delta `C − market_composite`. The volatile part.

---

## 4. Component 0 — Anti-staleness (inline forward scorer)

`monitor_cmd._write_eval_artifacts` already appends `forward_ledger.jsonl` + `nav_history.jsonl` each run but never runs the scorer, so the `monitor_forward` artifact ages until a manual `irc eval monitor_forward` (the 2026-06-30 report showed `⚠ stale backtest (2026-06-16)`).

- New thin edge `monitor_cmd._run_forward_eval(root, today)` invokes the `evals/monitor_forward/runner.py` entry (the same path `irc eval monitor_forward` dispatches) after the ledger/nav_history appends, before `_predictive_panel_model`.
- **Containment:** the scorer's WARN/`insufficient_data` is normal; its non-zero rc MUST NOT change `irc monitor`'s exit code. try/except logs + continues (same posture as the existing appends); a scorer failure degrades to the pre-existing "read latest artifact" path — never crashes the run.
- `_predictive_panel_model` is unchanged; it now reads a **same-day** artifact ⇒ `_is_stale` false on every run. The stale banner becomes a genuine signal (scorer truly couldn't run for ≥`STALE_EVAL_DAYS`=10), not routine noise.
- **Sentinel-safe:** the idempotency guard is in `run-monitor.sh` (skips the whole job if today's `monitor.json` exists, #179 fix). The inline eval runs exactly when `irc monitor` runs fully; no hole reintroduced.
- Does **not** make forward metrics mature faster — they stay `insufficient_data` until ≥8 engine-3 days accrue. It removes only artifact-age staleness.

## 5. Component 1 — Market composite anchor + news overlay (render-derived)

The reframed centerpiece. Per fund, **purely from `signal.contributions`** (no engine change):

- **Market composite** = renormalize the contributions of the non-news factors (`trend`,`valuation`,`flow`,`heat`) to sum-of-weights 1 and sum `Σ w'·value`; map to bias via the **same `fund.bands`** (`_bias`) the full signal uses → a `market_bias`.
- **News overlay delta** = `C − market_composite`.
- New pure module `src/irc/monitor/market_composite.py`:
  ```
  @dataclass(frozen=True)
  class MarketCompositeView:
      composite: float      # renormalized market-only composite
      bias: str             # _bias(composite, fund.bands)
      news_delta: float     # C - composite
      eligible_market_factors: int   # for the displayed explanation
  def market_composite_view(signal, *, bands) -> MarketCompositeView | None  # None iff no market factors present
  ```
  Reuse `_FAMILY_OF` from `signal.py` so the market/news split has one source of truth (shared with `backtest.py`).

**Presentation (Q7):**
- **Header badge stays `published_state`** (full, gated) — gating/eval continuity intact.
- **Decision line** directly beneath, e.g.:
  `市场面 决策锚: NEUTRAL (+0.24) · 新闻叠加 +0.20 (易变) · 限购 ¥100/日`
- **Honesty line**, precise (0.54 is trend-only, not the market composite):
  `市场面综合分 前瞻验证累积中 · 目前仅趋势单因子有历史命中 ~0.54`
- Reading order per card: gated published lean → fact-backed market anchor → how much volatile news pushes it → tradability → honest "anchor track-record accruing".

This **replaces** the original "robustness tier." There is no `robust/moderate/fragile` enum; reliability is the concrete market-vs-news split a reader can see.

## 6. Component 2 — Per-score annotations (render-derived, pure)

New pure module `src/irc/monitor/annotate.py` (sign conventions from `factor_maps.py`):

| factor | rule | phrases |
|---|---|---|
| `trend` | value band | 强上行 / 上行 / 横盘 / 下行 / 强下行 |
| `valuation` | from value (cheap=+1…very_expensive=−1) | 便宜 / 中性偏低 / 估值中性 / 偏贵 / 很贵 |
| `flow` | flow-band score | 强净流入 / 净流入 / 均衡 / 净流出 / 强净流出 |
| `heat` | asymmetric (calm caps +0.3, overheated −1.0) | 低拥挤·平静 / 偏拥挤 / 过热 |
| `macro_tilt` | value band, **always append** `·新闻面·易变` (it's news overlay) | 新闻面偏多 / 中性 / 偏空 |
| `constituent` | value band, **mark `·新闻面`** | 成分质量高 / 中等 / 偏弱 |

```
def factor_annotation(name, value, *, state=None) -> str   # "" when N/A
def composite_annotation(signal) -> str   # names market vs news drivers, e.g. "市场面中性，新闻叠加偏多"
```
Render: a `解读` column in the factor table + a `title` tooltip on the value cell. The two **news** factors carry the `·新闻面` mark so a reader sees which annotations belong to the volatile overlay. The composite verdict gains `composite_annotation`.

## 7. Component 3 — Three charts (pure inline-SVG / styled HTML, no JS)

- **(a) Cross-fund heatmap** `render_heatmap.py::factor_heatmap_html(views)`. Rows=funds (by `C` desc); columns **grouped: market block (trend/valuation/flow/heat) | news block (macro/constituent) | 市场面C | 完整C**. Diverging fill **using the report's existing badge convention** (`.add_bias` green `#1a7f37`=偏多 positive, `.reduce_bias` red `#cf222e`=偏空 negative — no new/ inverted palette), intensity ∝ |value|, `—` neutral; one-line legend `正=偏多/负=偏空`. Cell `title` = `factor_annotation`. After the summary table.
- **(b) Bias-history timeline** `render_timeline.py::bias_timeline_html(timeline)`. `monitor_cmd` reads `forward_ledger.jsonl`, dedups one row per `(fund_id, run_date)` (prefer current engine, else latest `written_at`), tags engine, builds a frozen `BiasTimeline` (bounded ~20 run-dates), passes it in. Colored HTML grid; v1→v3 engine boundary marked. Only new render-data read; lives in command layer.
- **(c) Per-fund contribution bars** `render_contrib.py::contribution_bars_svg(contributions)`. Compact inline-SVG diverging bar per factor inside each card; **market factors vs news factors visually distinguished** (e.g. news bars hatched/muted) so the overlay is obvious. Byte-stable, geometry rounded.

## 8. Component 4 — Citation UX (numbered + source on hover)

`render_html` builds a `CitationIndex` (cid → 1-based N + (source,title), first-seen = appendix order) and threads it into `render_cards._claim_html`, replacing `[ref:cid]` with `<sup><a href="#ev-{cid}" title="{source} — {title}">{N}</a></sup>`. Evidence `<li id="ev-{cid}">` gains a leading `N.`. Native `title` tooltip, zero JS. Data-model `[ref:16-hex]` unchanged (render-only).

## 9. Component 5 — 限购 / actionability tag (separate axis)

Reuse the purchase table already fetched for `heat` (`fund_purchase_em` → `申购状态`, `日累计限定金额`; restricted iff `parse_purchase_status` True, i.e. status ∉ {开放申购} or cap < `_RESTRICTION_CAP_THRESHOLD`=1e8). Render a `限购 ¥{cap}/日` tag (or `限购` when only status-restricted) on restricted funds, in the decision line. **Orthogonal to the market/news split** — it answers "can you act?", not "how reliable?". No tag when open/unknown.

## 10. Component 6 — Log + score the market composite (the lynchpin)

The market composite is the decision anchor, so its forward edge must be *measured*, not assumed. It's logged by nothing today.

- **Ledger (additive, back-compat):** `forward_log.ledger_row` adds `market_composite: float | None` (and `market_bias`) to each `forward_ledger.jsonl` row. Additive field; existing readers (`latest_per_key`) unaffected; rerun dedup unchanged.
- **Forward scorer:** `forward_score.py` adds a `market_composite_directional` population (matured rows, sign of `market_composite`), parallel to `raw_composite_directional` — same maturity join / zero-return exclusion / block bootstrap.
- **Panel:** `predictive_validity_panel_html` renders the new row (it will read `insufficient_data` until engine-3 days mature — shown honestly, like the others).
- This is the only path that turns the anchor from "fact-backed but unproven" into "proven," exactly as trend-only earned its 0.54. Component 0 keeps the eval fresh so it accrues from day one.

## 11. Data flow

```
monitor_cmd (EDGE):
  fetch purchase table (already, for heat)
  build views + signals (unchanged scoring; full C is canonical)
  market_composite_view per fund (Comp 1, from signal.contributions)
  _write_eval_artifacts: append ledger (+ market_composite, Comp 6) + nav_history
  Component 0: _run_forward_eval(root, today)  -> fresh artifact (contained; scores market_composite_directional, Comp 6)
  read forward_ledger -> BiasTimeline (Comp 3b)
  _predictive_panel_model  -> fresh same-day artifact (+ market row)
  render_report(views, market_views, timeline, predictive_panel)

render_report (PURE):
  CitationIndex (Comp 4)
  header + outage + explainer
  summary (+ 市场面 col)
  factor_heatmap (market|news|市场面C|完整C, Comp 3a)
  bias_timeline (Comp 3b)
  per fund card:
    header badge = published_state (unchanged)
    decision line: market_bias + composite + news_delta + 限购 + honesty (Comp 1/5)
    nav chart + contribution bars (market vs news, Comp 3c)
    factor table (+解读 col w/ 新闻面 marks, Comp 2)
    drilldown + narrative (numbered citations, Comp 4)
  validation panel + predictive panel (+ market row, Comp 6) + evidence appendix (numbered)
```

## 12. Testing (TDD)

- `market_composite.py`: renorm math truth table (QDII trend+heat only; full active 4-factor; news-delta = C − market; bands applied; None when no market factor present); cross-check against `signal.compute_signal` renorm conventions.
- `annotate.py`: per-factor band truth tables, heat asymmetry, the `·新闻面·易变` mark always on macro/constituent, N/A → "".
- `render_heatmap/timeline/contrib`: golden HTML/SVG, byte-stability, market/news grouping, dark `—` handling, engine-boundary marker.
- citations: superscript N ↔ appendix N alignment; `title` carries source; no raw `[ref:` left in narrative.
- Component 0: post-run `artifact_date == today` & `stale is False`; scorer exception doesn't change monitor exit code.
- Component 6: ledger row carries `market_composite`; `market_composite_directional` present in report.json; additive-field back-compat (old rows w/o the field don't crash the scorer).
- Invariants preserved: report has no `<script>`/remote refs; `_ENGINE_VERSION` unchanged; `published_state`/gate/full-`C` unchanged; `基金概况` absent.
- Signature-change discipline ([[feedback-test-scope-signature-changes]]): `FundView`/`render_report` gain params, `ledger_row`/`forward_score` change → run `tests/monitor/` **and** `tests/commands/` (per-file; whole-dir hangs) **and** `evals/monitor_forward/` tests.

## 13. Phasing (single PR, off current main)

1. **Anti-staleness + citations** (Comp 0 + 4) — correctness + readability.
2. **Market composite + news overlay + presentation + annotations** (Comp 1 + 2) — the reframe core.
3. **Charts** (Comp 3a/b/c).
4. **Log + score market composite** (Comp 6) — ledger + forward scorer + panel.
5. **限购 tag** (Comp 5).

Each phase TDD'd + committed atomically; all merge in one PR via `/ship`.

## 14. ADR

A monitor ADR is warranted (hard-to-reverse + surprising + real trade-off): *"the report's decision anchor is the market composite (news-excluded), the full composite remains the published/tracked signal, and the market composite is logged + forward-scored to earn its own track record."* Alternatives rejected: making the market composite the published signal (re-baselines ledger/eval), an engine change to down-weight news (engine bump + re-baseline), or a render-only "robustness" sticker (no decision value). → `docs/adr/0021-monitor-market-composite-decision-anchor.md`.

## 15. Risks / open items

- **Report width** — decision line + 解读 col + heatmap + timeline grow the page; compact phrasing (≤6 chars), muted styling, tables ≤ existing max-width.
- **Market composite vs retro core confusion** — mitigated by distinct CONTEXT.md terms + the rendered honesty line naming trend-only explicitly.
- **Delayed payoff** — market-composite forward row reads `insufficient_data` for weeks (engine transition); honest by design.
- **Ledger contract** — `market_composite` is additive; document in ADR 0017 §"Monitor-eval data contracts" alongside the existing row fields.

## 16. Out of scope

- Changing scoring to down-weight news / make market composite the published signal (engine change — declined).
- Per-constituent daily news (existing v2.1 item).
- Faster forward maturation (purely a function of engine-3 day accrual).
