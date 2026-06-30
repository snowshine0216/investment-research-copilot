Verdict: PASS

Subagent: sonnet
Source: /verify — Fallback used: render-pipeline exercise (real `render_report` called directly; live `irc monitor` not attempted due to missing MINIMAX_* keys + live network)
Entry point exercised: `uv run python scratchpad/render_v2_smoke.py` (imports `irc.monitor.render_html.render_report` with multi-fund input exercising all v2 surfaces) + `uv run pytest tests/monitor/test_report_v2_invariants.py -q`

Observed behavior:

- §5 market composite decision line — observed `市場面 決策鑥: <b>NEUTRAL</b> (+0.29) · 新聞疊加 +0.20 (易變) · 限購 ¥100/日` for fund 519069 and `市場面 決策鑥: <b>NEUTRAL</b> (+0.22) · 新聞疊加 +0.24 (易變)` for fund 270023; both carry `<div class="decision-line">`.
- §5 honesty line naming trend-only ~0.54 — observed `市场面综合分 前瞻验证累积中 · 目前仅趋势单因子有历史命中 ~0.54` in `<span class="honesty muted">` on both fund cards.
- §5 summary 市场面 column — observed `<td>市场面 +0.29 NEUTRAL</td>` and `<td>市场面 +0.22 NEUTRAL</td>` in the summary table rows.
- §6 解读 column — observed `<th>解读</th>` in the factor table header; annotation cells include `强上行`, `中性偏低`, `净流出`, `低拥挤·平静`.
- §6 news factors carry ·新闻面 — observed `新闻面偏多·新闻面·易变` for `macro_tilt` and `成分质量高·新闻面` for `constituent` in both the factor table 解读 cells and the heatmap cell `title=` attributes.
- §7 heatmap with 市场面C + 完整C — observed `<th>市场面C</th>` and `<th>完整C</th>` in `<table class="heatmap-table">` under `<h2>跨基金因子热力图</h2>`; diverging fill `background:#1a7f37;opacity:0.75` and `background:#cf222e;opacity:0.40` present.
- §7 bias timeline — observed `<table class="timeline-table">` with `engine-boundary` class on cells where engine tag changes from "1" to "3"; `no-data` class present for absent (fund, date) cell; `引擎切换以边框标记 (engine-boundary)` note rendered.
- §7 per-fund contribution bars (inline SVG) — observed 2 `<svg class="contrib" viewBox="0 0 260.00 ...">` elements inline in fund cards; `class="news-bar"` and `fill="url(#hatch)"` distinguish news factors; market bars use solid `fill="#1a7f37"` / `fill="#cf222e"`.
- §8 numbered citations: `<sup>` superscripts with `title=` — observed `<sup><a href="#ev-fdc92f975c484638" title="Wind资讯 — 央行出台定向降准政策，利好中证500成分股">1</a></sup>` and `<sup><a href="#ev-12e58bb039ed541f" title="Bloomberg — Fed holds rates; emerging market inflows accelerate">2</a></sup>`.
- §8 numbered appendix `<li>` — observed `<li id="ev-fdc92f975c484638">1. 央行出台定向降准政策…</li>` and `<li id="ev-12e58bb039ed541f">2. Fed holds rates…</li>`; superscript N == appendix N confirmed for both.
- §8 no raw `[ref:` remaining — confirmed: 0 occurrences of `[ref:` in produced HTML.
- §9 限购 tag on restricted fund — observed `限购 ¥100/日` in fund 519069's decision-line; fund 270023's decision-line contains no `限购`.
- §10 market_composite_directional predictive panel row — observed `<td>market_composite_directional</td><td>+0.000</td><td>WARN</td><td>CI pending</td><td>n/a</td><td>n/a</td><td>n/a</td><td>insufficient_data</td><td>0</td>` inside `<section class="predictive-panel">`.
- Invariant: no `<script` — confirmed absent.
- Invariant: no `https://` remote refs — confirmed absent (SVG `xmlns="http://..."` is allowed; confirmed present).
- Invariant: no `基金概況` / `基金概况` — confirmed absent.
- Unit smoke: `uv run pytest tests/monitor/test_report_v2_invariants.py -q` → `5 passed in 0.24s`.

Failures: none
