Verdict: PASS

## Subagent

None used — verification performed directly against the codebase (Agent tool forbidden per instructions).

## Source

- Branch verified: `autodev/monitor-v4-explainability-feature` (confirmed via `git branch --show-current`).
- Range: `main...autodev/monitor-v4-explainability-feature`, 20 commits, 38 files changed (+10522/-97).
- Merged items confirmed on branch by commit log:
  - 003 (`8a8e6994`, PR #200): divergence caveat detail — named factors + signed values.
  - 001 (`d894a644`, PR #201): caveat transparency — gate reasons, overview dedupe line, weekly eval refresh, schema 7.
  - 002 (`34d2e3bf`, PR #202): macro direction chips + strength tags + mechanism clause, prompt v3.
  - 004 confirmed **docs-only** on this branch (spec `6fbe2a03`, grill `a359596c`, plan `e13038bf`) — no `src/` changes; `git diff main...HEAD -- src/ | grep -i 'f127\|board.pe'` returns nothing. Not exercised, per instructions.

## Entry point exercised

Direct Python entry-point calls (no CLI, no network, no LLM) against the real render/eval modules:
- `irc.monitor.render_html.render_report` — the single top-level HTML entry point used by `irc monitor`.
- `irc.monitor.eval.trace.build_eval_trace` — the eval-trace entry point, fed the **same** constructed bundle.

Scratch scripts (not committed):
- `/private/tmp/claude-501/.../scratchpad/verify_cross_item.py` — primary cross-item bundle (2 funds: 008986 gold_etf, 600000 active_cn_equity).
- `/private/tmp/claude-501/.../scratchpad/probe_adjacent.py` — adjacent probe (3rd fund, validated/no-caveat, unmatched macro key, empty divergence, no themes).

## Cross-item flow observed (with evidence)

Built one realistic bundle carrying, simultaneously: a `SignalRecord` with divergence codes (`trend_valuation_conflict`, `low_factor_agreement`) and real factor contributions (003); a fund-specific `monitor_signal` WARN health row producing a caveated gate on 008986, plus two run-global suite WARNs (`monitor_impact`, `monitor_narrative`, both `stale, 12d`) producing a run-global-only caveated gate on 600000 (001); and a `MacroNarrativeDoc` block (theme `gold_drivers`) with a mechanism clause and two strength-tagged claims, joined against `ValidatedImpact` records for one of the two funds (002). Ran `render_report` ONCE over both fund views + this shared macro doc/gates/panel, then ran `build_eval_trace` over the same fund/view/gate/bundle tuples.

**003 — divergence detail (risk block)**
```
<li>趋势与估值背离：趋势 +0.55（价格动能向上） vs 估值 -0.40（估值偏贵）</li>
<li>因子分歧较大：偏多 trend +0.55、macro_tilt +0.62 ↔ 偏空 valuation -0.40</li>
```
Signed values (`+0.55`, `-0.40`) match the `FactorContribution` inputs exactly; the grouped-by-sign line correctly separates the three factors by sign.

**001 — caveat transparency**
- Overview 今日速览 caveat line (ONE run-global line, ran before flips/actionable/health rows):
  `⚠ 全部基金 caveated：LLM质量评估过期 12/12天 · 周六自动刷新`
- Caveated-badge chip anchors to `#validation-panel` with an escaped tooltip:
  `<a class="val-chip val-caveated" href="#validation-panel" title="monitor_signal: WARN (low_agreement)">⚠ caveated</a>`
- Card-level 为何有保留 line present **only** on 008986 (fund-specific WARN segment) and **absent** from 600000's card (its WARN is run-global-only, already surfaced by the one overview line) — confirms the fund-specific/run-global split does not double-render.
- `gate.reason` non-empty for both funds' `GateDecision`.

**002 — macro direction chips, strength tags, mechanism**
- `宏观面速览` section with `id="macro-gold_drivers"` anchor.
- Direction chip for 008986 (has a joined `ValidatedImpact`): `<span class="fund-chip chip-pos" title="置信度 0.7">008986 +0.62</span>` — class, sign-banded color, and formatted-signed value all reconcile with the input `ValidatedImpact(0.62, confidence=0.7)`.
- Bare chip for 600000 (no macro record for this theme): `<span class="fund-chip">600000</span>` — absence renders as absence, not zero.
- Strength tags rendered per claim: `<span class="claim-strength">方向一致</span>` and `<span class="claim-strength">已证实归因</span>`.
- Mechanism line, correctly placed between chips and claims: `<p class="macro-mechanism">对本组基金的传导：降息预期升温→实际利率下行→利多黄金</p>`.

**No interference between the three feature sets**: all three regions (risk-block `<li>`s, overview caveat line + card caveat line, macro chips/tags/mechanism) appear correctly and independently within the same HTML document; none suppressed or corrupted the others.

**build_eval_trace on the same bundle:**
```
trace["schema_version"] == "7"
trace["funds"]["008986"]["gate"]["reason"] == "monitor_signal: WARN (low_agreement)"  (non-empty)
trace["funds"]["600000"]["gate"]["reason"]  (non-empty, run-global cause)
trace["funds"]["008986"]["signal"]["divergence_codes"] == ["trend_valuation_conflict", "low_factor_agreement"]
trace["macro_narrative"]["blocks"][0]["mechanism"] == "降息预期升温→实际利率下行→利多黄金"
trace["macro_narrative"]["blocks"][0]["mechanism_dropped"] == False
```
All schema/gate/mechanism assertions hold on the identical fixture set used for the HTML render (AC6-style reconciliation).

**Adjacent probe (🔍):** added a third, fully-VALIDATED fund (no WARN/FAIL anywhere, `divergence_codes=()`, `themes=()`, and a macro impact filed under a typo'd/unmatched key) to the same render call.
- 🔍 Validated fund's badge renders a plain `<span class="val-chip val-validated">✓ validated</span>` — no anchor, no tooltip (per spec: only caveated badges get the anchor).
- 🔍 No overview caveat-line appears when all suites PASS and no fund is caveated (dedupe line correctly drops to nothing, not an empty artifact).
- 🔍 No card-level 为何有保留 on the validated fund.
- 🔍 Empty `divergence_codes` + no risk narrative renders the muted placeholder `无显著风险信号`, not a stray empty `<ul>`.
- 🔍 The unmatched macro-impact key (`typo_theme_xyz`) renders **nowhere** in the HTML — confirmed via substring absence — while `unmatched_impact_keys()` (the pure detector feeding the trace's `unmatched_impact_keys` field) correctly flags it. This is the exact "typo'd LLM key would be invisible forever" trap the item-002 field guards against, and it holds.
- Two of my own probe assertions were fixture mistakes, not code defects (documented under Findings, not Failures): I set the 3rd fund's `themes=()` so it correctly never appears in the `gold_drivers` chip block (verified by re-reading `_invert_fund_themes`, which only ever includes funds via `fund.themes`); and I gave it an evidence item with zero citing claims, so it correctly appears in the appendix without an inline `<sup>` anchor (appendix ⊇ anchors is expected — evidence pool items need not all be cited inline).

## Secondary checks

- `uv run irc --help` → exit 0, full command list intact (32 commands incl. `monitor`).
- `bash -n ops/launchd/run-weekly.sh` → exit 0 (syntax valid).

## Findings

- No item-004 (industry fill / board-PE / f127) markers found anywhere in the rendered HTML or the trace — confirms env-paused item correctly stayed off this branch's runtime surface.
- The 001/003 caveat mechanisms compose cleanly: a fund can be caveated for a *fund-specific* reason (gets the card line) or a *run-global* reason (does not, relying on the one dedupe line) or both — this bundle exercised both branches in the same render and both classified correctly.
- The macro direction-chip join is correctly keyed by exact-string `ValidatedImpact.key == theme` match; a fund present in the macro pool but absent from a theme's chip set, and a fund present in the chip set but absent from the impact join, both degrade to the documented behavior (bare chip / no chip) rather than crashing or silently mismatching.
- No JavaScript, no remote refs, and the citation anchor/appendix set closed correctly (own-script check, not just relying on existing test suite) in the primary bundle.

## Failures

None. 0 of 26 primary assertions failed; the 2 probe-script assertions that initially "failed" were traced to fixture setup (not code defects) and are documented under Findings/probe above, not as product failures.
