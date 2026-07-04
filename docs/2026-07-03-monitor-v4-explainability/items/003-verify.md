Verdict: PASS

Subagent: sonnet
Source: /verify
Entry point exercised: `uv run python <scratchpad>/verify_003.py` and `verify_003_probe.py` — real production render path `risk_block_html()` (src/irc/monitor/render_cards.py) and its callee `divergence_caveat_detail()` (src/irc/monitor/render_factors.py), driven with constructed `SignalRecord`/`FactorContribution` inputs (the same shape the pure signal-scoring stage produces). No network, no LLM, no `uv run irc monitor`.

Observed behavior:
  - AC-1 (new pure function exists, deterministic, no I/O/mutation) — imported and called `divergence_caveat_detail(code, contributions)` directly from `render_factors.py`; same inputs produced byte-identical outputs across repeated calls; no I/O performed.
  - AC-2 (pairwise exact formats) — `trend_macro_conflict` → `趋势与宏观背离：趋势 -0.75（价格动能向下） vs 宏观 +0.62（新闻/宏观偏多）`; `trend_valuation_conflict` → `趋势与估值背离：趋势 +0.45（价格动能向上） vs 估值 -0.80（估值偏贵）`; `valuation_flow_conflict` → `估值与资金流背离：估值 +0.80（估值偏便宜） vs 资金流 -0.45（资金净流出）`. All three matched the spec-locked strings exactly.
  - AC-3 (mixed-sign grouped) — contributions `heat +0.30, macro_tilt +0.62, trend -0.75` → `因子分歧较大：偏多 heat +0.30、macro_tilt +0.62 ↔ 偏空 trend -0.75` (exact). Adding a zero-valued `constituent +0.00` appended a trailing group → `…↔ 偏空 trend -0.75、中性 constituent +0.00` (exact).
  - AC-4 (dispersion-only) — same-sign values `1.20, 0.08` (pstdev 0.5600, not mixed-sign) → `因子分歧较大：强度离散 σ=0.56 ≥ 0.5` (matches locked example exactly, including `{:g}` threshold rendering `0.5` not `0.50`).
  - AC-5 (fallback paths) — pairwise code with `macro_tilt` absent from contributions → fell back to the exact static string `趋势与宏观背离：价格动能与宏观信号方向相反` (== `divergence_caveat(code)`). `low_factor_agreement` with only 1 contribution → static fallback `因子分歧较大：各因子方向/强度不一致`. Same-sign values with sigma below threshold (0.10, 0.15 → pstdev 0.025) → static fallback, no false `σ ≥ 0.5` claim. Unknown code `<x>` → `&lt;x&gt;` escaped passthrough.
  - AC-6 (call-site swap) — confirmed by direct read: `render_cards.py:5` imports `divergence_caveat_detail` (not the old name), `risk_block_html` (line 100-105) calls `divergence_caveat_detail(code, rec.contributions)`. Exercised live: `risk_block_html()` with a real `SignalRecord` carrying `divergence_codes=("trend_macro_conflict",)` and matching contributions rendered `<li>趋势与宏观背离：趋势 -0.75（价格动能向下） vs 宏观 +0.62（新闻/宏观偏多）</li>` inside the `<div class="risk">` block — the actual production wrapper, not just the bare function.
  - AC-7 (no bare static string when data available) — the same render above was asserted to NOT contain `各因子方向/强度不一致` — confirmed absent.
  - AC-8 (HTML safety) — hostile factor name `<b>evil</b>` fed through the `low_factor_agreement` grouped path rendered as `&lt;b&gt;evil&lt;/b&gt;` both from the bare function and through the full `risk_block_html()` wrapper; no raw `<b>` tag present in final HTML.
  - AC-9 (schema/engine neutrality) — `git diff main... --stat -- src/irc/monitor/eval/` returned empty; `git diff main... --stat` full listing (13 files including docs/tests/CHANGELOG) shows only `render_cards.py`, `render_factors.py`, `signal.py` touched under `src/`; grep for `schema_version`/`_ENGINE_VERSION` in those 3 files found none.
  - Probe (adversarial): two divergence codes on one fund card rendered as two independent `<li>` lines, each with correct detail text, in a single `risk_block_html()` call — no cross-contamination.
  - Probe (adversarial): a fund with zero divergence codes rendered the pre-existing `无显著风险信号` muted placeholder, confirming the change is additive and does not disturb the baseline no-risk path.
  - Probe (adversarial): supplying the two pairwise factors in reversed tuple-insertion order (`macro_tilt` before `trend`) still rendered `趋势 … vs 宏观 …` in code-defined order — output ordering is not accidentally insertion-order-dependent.

Failures: none.
