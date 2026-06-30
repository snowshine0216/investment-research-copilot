# Monitor Report v2 — annotations, charts, robustness, freshness

Status: design (approved in brainstorming 2026-06-30)
Scope: `irc monitor` report + command layer only. **No scoring/engine change.**

## 1. Problem

The daily `irc monitor` report (`outputs/<date>/monitor/report.html`) has five gaps surfaced while reading the 2026-06-30 run:

1. **Stale predictive panel.** The "Predictive validity" panel reads whatever `monitor_forward` eval artifact already exists and flags it stale past `STALE_EVAL_DAYS` (10). `monitor_cmd` already appends `forward_ledger.jsonl` + `nav_history.jsonl` every run, but **never runs the scorer**, so the artifact ages until someone manually runs `irc eval monitor_forward`. The 2026-06-30 report showed `⚠ stale backtest (2026-06-16)`.
2. **Thin / low-actionability signals are invisible.** QDII funds produce the only non-neutral bias today, yet they have only 3/6 eligible factors (trend/heat/macro_tilt — valuation/flow/constituent are `profile_ineligible`), are dominated by the most volatile factor (`macro_tilt`, which flipped two funds on a same-day re-fetch — see [[project-monitor-macro-tilt-instability]]), and are purchase-capped (~¥100/day). Nothing in the report communicates this fragility.
3. **No cross-fund / historical charts.** The report has per-fund NAV sparklines only. There is no cross-fund factor overview, no bias history, no per-fund contribution view.
4. **Raw citations.** Narrative text prints inline `[ref:16-hex-id]` — unreadable.
5. **Unannotated scores.** Factor values (`sᵢ ∈ [−1,1]`) and the composite `C` are bare numbers; a reader cannot tell what `flow −0.60` or `valuation +0.29` means without domain knowledge.

## 2. Goals / non-goals

**Goals:** make every score self-explaining; surface signal fragility + purchase-restriction; embed cross-fund/historical charts; clean citations; make the predictive panel structurally always-fresh.

**Non-goals (hard):**
- No change to composite-`C` math, factor weights, gating, or `_ENGINE_VERSION` (stays 3). Robustness/annotations are *render-derived*, never inputs to scoring.
- No JS, no remote refs, no I/O in the render layer. `render_report` stays PURE (its docstring contract).
- No new network calls or LLM calls (annotations are rule-based; charts reuse data already in the run).

## 3. Hard invariants (carried from existing acceptance tests)

- `render_report` and all `render_*` functions: pure, deterministic, byte-stable, no I/O/JS/remote refs.
- All new I/O (ledger read, scorer invocation, purchase-table threading) lives in `monitor_cmd.py` / the `commands` layer; pure data structures are passed into render.
- Determinism: annotations and robustness tiers are pure functions of already-computed values. Same trace → same HTML.
- Files < 200 lines, functions < 20 lines ideal; each new renderer is its own focused module.
- TDD: a failing test precedes each unit.

---

## 4. Component 0 — Anti-staleness (Approach A: inline scorer)

`monitor_cmd._write_eval_artifacts` already appends the ledger + nav_history. After that, and before `_predictive_panel_model`, invoke the forward scorer inline:

- New thin edge in `monitor_cmd`: `_run_forward_eval(root, today) -> None` that calls the existing `evals/monitor_forward/runner.py` entry (the same path `irc eval monitor_forward` dispatches to), which writes `outputs/<today>/evals/monitor_forward/report.json` + `details.json`.
- **Containment:** the scorer's WARN/`insufficient_data` is normal and its non-zero rc MUST NOT change `irc monitor`'s exit code. Wrap in try/except that logs and continues (same posture as the existing ledger/nav_history appends). A scorer failure degrades to the pre-existing "read latest artifact" behaviour — never crashes the run.
- `_predictive_panel_model` is unchanged; it now reads a same-day artifact, so `_is_stale` is false on every run (manual or scheduled). The stale banner becomes a genuine signal (only fires if the scorer truly couldn't run for ≥10 days), not routine noise.

Note: this does **not** make the forward metrics *mature* — they stay `insufficient_data` until ≥8 engine-3 days accumulate (engine switched v1→v3 on 2026-06-21). It only removes the *artifact-age* staleness. The panel will read `effective_n=0 / WARN` honestly until the engine-3 window matures.

---

## 5. Component 1 — Signal robustness + actionability (render-derived)

Two distinct, pure indicators per fund, no C-math change:

- **稳健度 / robustness** — signal quality. Inputs: `breadth = (#eligible factor_scores)/6` and `macro_share = macro_tilt.renorm_weight` (its share of available weight, from `signal.contributions`). Tier rule:
  - `脆弱 / fragile` if `breadth ≤ 0.5` (≤3 factors) **or** `macro_share ≥ 0.30`
  - `一般 / moderate` if `breadth ≤ 0.84` (≤5 factors) **or** `macro_share ≥ 0.20`
  - else `稳健 / robust`
  - (Thresholds live in a small constants block, tunable; values chosen so today's QDII = 脆弱, full-6-factor active = 稳健.)
- **限购 / actionability** — purchase restriction, reusing the table already fetched for `heat` (`fund_purchase_em` → `申购状态`, `日累计限定金额`). Render a `限购` tag when `parse_purchase_status` is True; when the daily cap `日累计限定金额` is a finite small number, show it (e.g. `限购 ¥100/日`). When unrestricted/unknown, no tag.

**New module** `src/irc/monitor/robustness.py` (pure):
```
@dataclass(frozen=True)
class RobustnessView:
    tier: str            # "robust" | "moderate" | "fragile"
    breadth: float       # eligible/6
    macro_share: float
    restricted: bool | None
    daily_cap_cny: float | None   # 日累计限定金额 when restricted & finite

def robustness_view(factor_scores, contributions, *, restricted, daily_cap) -> RobustnessView
```
**Assembly:** `monitor_cmd` (has the purchase table) builds one per fund and attaches it to `FundView` (new optional field `robustness: RobustnessView | None = None`).
**Render:** two chips after the bias badge in the card `<h2>` and the verdict block, plus a `稳健度` column in the summary table. Chips are explanatory only — they never gate, never alter `C`. For today's QDII `ADD_BIAS` the card reads `偏多 · 稳健度 脆弱 · 限购 ¥100/日`.

---

## 6. Component 2 — Per-score annotations (render-derived, pure)

Every factor score and the composite gets a deterministic plain-language gloss. **New module** `src/irc/monitor/annotate.py` (pure), keyed per factor (sign conventions from `factor_maps.py`):

| factor | rule | example phrases |
|---|---|---|
| `trend` | band on value | 强上行 / 上行 / 横盘 / 下行 / 强下行 |
| `valuation` | from value (cheap=+1…very_expensive=−1) | 便宜 / 中性偏低 / 估值中性 / 偏贵 / 很贵 |
| `flow` | from flow band score | 强净流入 / 净流入 / 均衡 / 净流出 / 强净流出 |
| `heat` | asymmetric (calm caps +0.3, overheated −1.0) | 低拥挤·平静 / 偏拥挤 / 过热 |
| `macro_tilt` | band on value, **always** append volatility caveat | 新闻面偏多 / 中性 / 偏空 · 「宏观因子波动大」 |
| `constituent` | band on value | 成分质量高 / 中等 / 偏弱 |

```
def factor_annotation(name: str, value: float | None, *, state: str | None = None) -> str   # "" when N/A
def composite_annotation(signal) -> str   # names the top ±2 contributing factors, e.g. "由 宏观/成分 抬升、资金流 拖累"
```
**Render:** add a `解读` column to the factor table (`render_factors.py`) carrying `factor_annotation`, and a `title` tooltip on the value cell with the same text. The composite verdict line (`render_cards._ok_clause`) gains `composite_annotation(signal)` so `C` says *which* factors drove it. N/A factors get an empty annotation (status column already explains the N/A reason).

---

## 7. Component 3 — Three charts (pure inline-SVG / styled HTML, no JS)

- **(a) Cross-fund factor heatmap** — `src/irc/monitor/render_heatmap.py::factor_heatmap_html(views)`. A styled HTML table: rows = funds (ordered by composite desc), cols = 6 factors + composite `C`; cell background a diverging fill, intensity ∝ |value|, `—` cells neutral. **Color follows the report's existing badge convention** (`.add_bias` green `#1a7f37` = 偏多 for positive, `.reduce_bias` red `#cf222e` = 偏空 for negative) — do not introduce a new palette or invert it; a one-line legend states 正=偏多/负=偏空 to defuse the CN red=涨 ambiguity. Each cell carries a `title` with `factor_annotation`. Inserted after the summary table. No new data.
- **(b) Bias-history timeline** — `monitor_cmd` reads `data/monitor/forward_ledger.jsonl`, dedups one row per `(fund_id, run_date)` (prefer current engine, else latest `written_at`), tags engine, and builds a frozen `BiasTimeline` passed into `src/irc/monitor/render_timeline.py::bias_timeline_html(timeline)` — a colored HTML grid (rows=funds, cols=dates) with the v1→v3 engine boundary marked. This is the **only** new data-read; it lives in the command layer, render stays pure. Bounded to the last N (≈20) run-dates.
- **(c) Per-fund contribution bars** — `src/irc/monitor/render_contrib.py::contribution_bars_svg(contributions)`. A compact inline-SVG horizontal diverging bar per factor (value × renorm-weight = contribution), rendered inside each card next to the factor table. Pure, byte-stable, geometry rounded (mirrors `svg_chart.py` style).

---

## 8. Component 4 — Citation UX (numbered + source on hover)

Build a `CitationIndex` once, in `render_html`, from the views in first-seen order (== evidence-appendix order):
```
@dataclass(frozen=True)
class CitationIndex:
    number: dict[str, int]                 # cid -> 1-based N
    meta: dict[str, tuple[str, str]]       # cid -> (source, title)
```
Thread it into `render_cards._claim_html`, replacing `[ref:cid]` with
`<sup><a href="#ev-{cid}" title="{source} — {title}">{N}</a></sup>`.
The evidence `<li id="ev-{cid}">` gains a leading `N.` so superscript ↔ appendix line up. Native `title` = source-on-hover, zero JS. Citation-ID format (`[ref:16-hex]`) is unchanged in the data model — this is render-only.

---

## 9. Data flow summary

```
monitor_cmd (EDGE / I/O):
  fetch purchase table (already done for heat)
  build views + signals (unchanged scoring)
  _write_eval_artifacts: append forward_ledger + nav_history   (unchanged)
  Component 0: _run_forward_eval(root, today)  -> writes fresh artifact (contained)
  build RobustnessView per fund (Comp 1), attach to FundView
  read forward_ledger -> BiasTimeline (Comp 3b)
  _predictive_panel_model  -> reads fresh artifact (now same-day)
  render_report(views, ..., timeline=, citation built inside)

render_report (PURE):
  CitationIndex (Comp 4)
  header + outage + explainer
  summary (+ 稳健度 col, Comp 1)
  factor_heatmap_html (Comp 3a)
  bias_timeline_html (Comp 3b)
  per fund card: verdict(+composite_annotation) + nav chart
                 + contribution_bars_svg (Comp 3c)
                 + factor table (+解读 col, Comp 2)
                 + drilldown + narrative (numbered citations, Comp 4)
                 + robustness chips (Comp 1)
  validation panel + predictive panel + evidence appendix (numbered)
```

## 10. Testing (TDD, all unit/pure unless noted)

- `annotate.py`: truth-table tests per factor (band edges, N/A → "", heat asymmetry, macro caveat always appended).
- `robustness.py`: tier truth table (QDII 3-factor+macro→fragile; 6-factor active→robust; restriction tag + cap formatting).
- `render_heatmap.py` / `render_timeline.py` / `render_contrib.py`: golden-HTML/SVG asserts; byte-stability; dark `—`/empty handling.
- `render_cards`/`render_html` citations: superscript N ↔ appendix N alignment; `title` carries source; no raw `[ref:` left in narrative output.
- Component 0: test that after a monitor run the predictive panel's `artifact_date == today` and `stale is False`; test that a scorer exception does not change monitor exit code (containment).
- Preserve existing invariants: keep/extend the acceptance tests asserting the report has no `<script>`, no remote refs; `_ENGINE_VERSION` unchanged; `基金概况` still absent.
- Signature-change discipline: `FundView` gains a field and `render_report` gains a param → run every test dir exercising them (`tests/monitor/`, `tests/commands/`), per [[feedback-test-scope-signature-changes]]. Run `tests/commands/` per-file (whole-dir hangs).

## 11. Phasing (single PR, landed together)

1. **Phase 1 — correctness + citations:** Component 0 (anti-staleness) + Component 4 (citations). Fastest correctness + readability win.
2. **Phase 2 — annotations + heatmap:** Component 2 + Component 3a.
3. **Phase 3 — robustness + contribution bars:** Component 1 + Component 3c.
4. **Phase 4 — bias timeline:** Component 3b.

Each phase is independently testable and committed atomically; all four merge in one PR via `/ship`.

## 12. Risks / open items

- **Report width.** Adding a `解读` column + `稳健度` column + heatmap + timeline grows the page. Mitigate with compact phrasing (≤6 chars) and muted styling; keep tables ≤ existing max-width.
- **Robustness thresholds are judgment calls.** Put them in a constants block with a comment tying each to an observed case; revisit if they mislabel funds.
- **Timeline ledger growth.** Bound to last ~20 run-dates; dedup is pure.
- **Annotation vocabulary** finalized against `factor_maps.py` during implementation (sign conventions already verified: valuation cheap=+1, heat calm caps +0.3).

## 13. Out of scope (possible follow-ups)

- Changing scoring to damp thin/macro-dominated biases (the "change the scoring" option was declined in favour of the render-derived robustness field).
- Per-constituent daily news (existing v2.1 open item).
- Making the forward metrics mature faster (purely a function of engine-3 day accumulation).
