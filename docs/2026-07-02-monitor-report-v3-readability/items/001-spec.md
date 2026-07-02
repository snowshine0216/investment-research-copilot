# Monitor Report v3 — readability: source tiers, macro block, citation dedup, 今日速览, honest gaps

Status: design (brainstormed 2026-07-02)
Scope: `irc monitor` evidence edge + narrative + report render. **No scoring/engine-math change** (engine stays 3). WS-B of the 2026-07-02 report-reliability roadmap. Base: current `main` (post #190).

## 1. Problem (grounded in the 2026-07-01 report)

The report's numbers got trustworthy (v2); the words around them did not. Measured on `outputs/2026-07-01/monitor/report.html`:

- **Citations**: 134 appendix entries, only **36 unique titles**. Root cause is structural: `citation_id = sha256(owner_fund_id:url:date)` — the *same article* gets a *distinct* cid per fund, and the run fires ~28 theme searches for only **8 unique themes** across the 10 funds. **Zero dates** rendered. Junk sources scored and cited: 13× letsdatascience, 8× mezha.net, 2× facebook.com, 1 comedy piece.
- **Narrative**: hedged English boilerplate ("The fund's performance may have been influenced by…") repeated near-verbatim across funds; fund-irrelevant claims (KPMG risk on 4 funds; AI-boom on a metals fund whose constituent factor was −1). The prompt *already asks for Chinese*; MiniMax-Text-01 ignores the soft instruction (verified again on 2026-07-02 output). Root cause of the repetition: every fund's theme pool contains the same macro articles, so the LLM has nothing fund-specific to say.
- **Dark data disguised**: flow rollup can show `flow_coverage PASS` while coverage = 0.0 (consistency PASS ≠ data present); holdings/factor tables render whole columns of dashes.
- **Stale evals render green**: impact stamp 06-17, narrative stamp 06-16 shown without any age signal; `STALE_EVAL_DAYS = 10` exists in `eval/constants.py` but only the predictive panel applies it.
- **No "what changed today"**; bias-history timeline shows bare fund codes.

## 2. Non-goals (hard)

- No change to composite math, factor weights, bands, gating, `published_state`, or `_ENGINE_VERSION` (stays 3). The tier gate changes macro_tilt's **inputs** (which evidence exists), not scoring math — same posture as v2: evidence varies run-to-run by nature.
- Not fixed here (tracked elsewhere): constituent factor ±1 saturation (`news_factor.py:25` — batch with a future engine bump), macro_tilt same-day instability, the stalled weekly pipeline, WS-C scout.
- `render_*` stay PURE (no I/O, no JS, no remote refs). ADR 0001 16-hex `[ref:]` format unchanged. ADR 0017 owner-binding preserved (one documented extension, §4).
- Ingest drops are **logged**, not traced. One deliberate trace change (grill decision): the 宏观面 block is serialized as an additive run-level `macro_narrative` field in `eval_trace.json`, `schema_version` **5→6** (the WS-A additive-bump precedent) — the trace stays lossless for the only remaining LLM narrative. No other trace change.

## 3. Component 1 — Source tiers + ingest gate (decision: gate at ingest, badge at render)

New pure module `src/irc/monitor/source_tiers.py`; config under `source_tiers:` in `config/monitor.yaml` (and the template in `src/irc/templates/config/monitor.yaml` — the #141 trap):

```yaml
source_tiers:
  blocked: [facebook.com, x.com, twitter.com, reddit.com, letsdatascience.com, mezha.net, ...]
  tier1:   [reuters.com, bloomberg.com, xinhuanet.com, gov.cn, pbc.gov.cn, ...]   # 权威
  tier2:   [cnbc.com, ft.com, wsj.com, kitco.com, mining.com, axios.com, eastmoney.com, ...]  # 财经媒体
```

- `classify(domain) -> "blocked" | 1 | 2 | 3` — **domain-suffix match** (subdomains inherit). Unknown → **tier 3 未分级, KEPT and badged** (a legit new source degrades to "visibly unvetted", never silently vanishes; promote/block later in config).
- **Scope: the theme (web-search) pool ONLY.** The constituent pool is snapshot-grounded (`build_constituent_pool` → cached `ActiveFundSnapshot` broker/filing evidence + synthetic `snapshot:<symbol>` fallback items, sometimes url-less) — a *domain* tier is meaningless there. Snapshot-derived evidence is outside the tier system and renders its own appendix badge: **快照** (never 未分级, which would misread as "unvetted web source").
- Applied at the theme-search edge (`_search_theme` result filtering) **before** `make_evidence_item` — blocked items never become evidence, never reach `gather_impacts`/macro_tilt, never get cids. Drop counts logged at warning level.
- Seed the tier lists from the observed 07-01 report domains.
- Config missing/malformed → everything classifies tier 3 (visible, not fatal) + one logged warning. `irc config validate` checks the section shape.

## 4. Component 2 — Theme-search consolidation (28 → 8 provider calls)

`run_monitor` collects the unique themes across the monitor set (stable sorted), searches **once per theme**, and passes the results map down; `build_evidence_pool(fund, theme_results=...)` assembles each fund's pool from the shared hits, owner-binding cids per fund exactly as today.

- macro_tilt scoring shape unchanged: each fund still gets a pool for its own themes; same hits → same cids as the status quo.
- Fewer provider calls: less rate-limit pressure, faster run; identical articles across funds now share `(url, date)` — which makes citation dedup (§6) exact.
- **Signature change** → per the test-scope rule, the plan must run `tests/monitor/` AND `tests/commands/` (per-file — whole-dir hangs) and grep tests for other callers.

**ADR 0017 addendum (documented, not violated):** the macro narrative block (§5) gets its own pool whose items are owner-bound to synthetic owners `theme:<name>`. cids stay 16-hex, `resolve_in_pool` works within the macro pool, fund pools keep real fund owners, and the dual-coverage-gate isolation argument is untouched (monitor evidence never enters the gate).

## 5. Component 3 — Narrative v3: 宏观面 block + constituent-only fund commentary + guards

**宏观面速览 section** (one per report):
- One LLM call (`monitor_narrative` route, MiniMax) over the union of theme evidence, grouped by theme, capped at the 10 most recent items per theme to bound the prompt.
- Output JSON keyed by theme, **claim-shaped exactly like today's narrative**: `{theme: [{claim, attribution_strength, citation_ids}]}`, **≤3 claims per theme** — reuses the existing schema validators, attribution-verb bans, citation resolution, and sanitization wholesale. Themes with no evidence are absent from prompt and output.
- Rendered as theme-labeled Chinese subsections (中国货币政策 / 地缘政治 / 黄金驱动 / … — display-name map is a render-layer constant) with anchors `#macro-<theme>`; each theme header carries **affected-fund chips** (deterministic from `config/monitor.yaml` themes — the reverse of the card→anchor links).
- Fund cards render **theme chips** linking to those anchors instead of repeating macro text 10×.

**Per-fund LLM narrative is DROPPED entirely** (grill decision, 2026-07-02). Rationale: today's per-fund narrative reads the *theme* pool (that's the boilerplate); the only fund-specific pool (constituent) is **quarterly-static** snapshot evidence, so a daily LLM call over it would produce near-identical prose with random wording drift — paying ~7 calls/run for noise. Instead every fund card carries: v2 deterministic annotations (解读 + `composite_annotation`), the constituent drill-down, and theme chips → 宏观面 anchors. Verdict/risk blocks degrade through the **existing** empty-narrative path (the empty-pool early-return state renders today). Narrative LLM calls go 10 → **1** (the macro block). `narrative.json` keeps per-fund keys (now empty docs) + `"__macro__"`. A quarterly-cached fund-prose variant and daily-fresh constituent news both stay out of scope (v2.1 follow-up).

**Guards (deterministic, in `narrative.py`, applied to the macro block):**
- **Language guard**: CJK-ratio check per claim — CJK ≥ 30% of non-whitespace characters (deliberately tolerant of tickers/numbers/latin brand names). Failure → retry inside the existing schema-retry loop (max stays 2 retries) with a hardened 中文-only instruction; persistent failure → **drop the claim set for that theme** (absent > English).
- Kept unchanged: attribution-verb bans (主因/导致/由于 gating), unresolved-citation rejection, sanitization, empty-pool early return.
- The brainstorm's cross-fund verbatim-dedup guard is **removed** — with a single narrative call there is nothing to dedup (YAGNI).

**Consequences owned:**
- Narrative **prompt version bumps** (rendered in the report header).
- `narrative.json` stays keyed by fund id at top level; the macro block is stored under the reserved key `"__macro__"` (numeric fund ids can't collide). Additive for any existing reader.
- `eval_trace.json` gains the run-level `macro_narrative` field, schema 5→6 (see §2); old traces without the field must still load (additive back-compat test).
- The `monitor_narrative` live_gated eval **corpus is updated** for the single new call shape (the macro block). Lifecycle unchanged: still double-gated behind `IRC_RUN_LIVE_LLM_EVAL`.

## 6. Component 4 — Citation UX v2: dedup + dates + tier badges

`build_citation_index` gains a canonical identity key **`(url or title, date)`** — exact-string URL match; query-string stripping was considered and **rejected** (query-routed pages would merge wrongly; post-consolidation the same article yields byte-identical URLs anyway):
- Index maps every cid → `(number, canonical_cid)`; superscripts link `#ev-{canonical_cid}`; the appendix renders **one `<li>` per article**: `N. {title} — {source} · {date} · {tier badge}`.
- Tier badges: 权威 / 财经媒体 / 未分级 (tier 3 styled muted). Appendix order stays first-seen. Hover `title` keeps source — now with date.
- `EvidenceItem.date` already exists and is currently discarded at render; no data-model change. `[ref:[0-9a-f]{16}]` matching unchanged.
- Expected: 07-01-shaped input goes 134 → ~36 entries; post-consolidation, near-1:1.

## 7. Component 5 — 今日速览 strip

New pure `src/irc/monitor/render_overview.py::overview_html(...)`, rendered directly under the header. Three rows (decision: no "biggest movers" row); each row dropped when empty; all empty → one muted line 今日无变化，数据健康.

- **偏向变化** — bias flips **vs the prior run** (labeled with its date — on Monday that's Friday, not a calendar "yesterday"): `名称(代码) NEUTRAL→ADD_BIAS` with colored badges. Powered by the existing `prior_signal` read (the orange-dot data).
- **可操作** — funds currently at ADD_BIAS / REDUCE_BIAS **whose `published_state` is not gated** (EVAL-GATED leans never render as actionable — the gate exists precisely for this); 限购-restricted marked (purchase table already fetched for heat).
- **数据健康** — counts with jump anchors: 因子暗 per factor as eligible-fund fractions (e.g. `flow 5/7` — `profile_ineligible` N/A excluded, so gold/QDII don't inflate the count) · M 只基金被评估门禁 · 过期评估 K (suite stamps aging >10d + stale predictive artifact).

All inputs already exist in the command layer; no new I/O.

## 8. Component 6 — Dark-data rendering + stale-eval badges + timeline names

- **Flow rollup honesty** (grill-corrected): `flow_coverage_health` is a §5.E *panel-only informational* stage — "Status always PASS — observability, never a gate" — so the bug is display vocabulary: the panel prints `PASS` for a stage that isn't pass/fail. Fix: informational stages (`flow_coverage`, `valuation_coverage`) render status **观测** instead of PASS, with their coverage reasons inline (`flow_cover 0.0 · pe_cover 0.8 · …`) and amber styling when `flow_cover` < the `_COVERAGE_FLOOR = 0.50`. Gate-relevant stages (`monitor_signal`, reconciliations, LLM suite) keep PASS/WARN/FAIL/UNKNOWN. The per-card flow rollup line already renders `资金流因子 = N/A（flow_no_coverage）` when dark — add the 暗·覆盖不足 chip styling there. "PASS" can no longer read as "data fine".
- **Dead dash columns**: pure helper `all_na_columns(rows)`; columns N/A for *every* row in the holdings board / factor table collapse to a single header note carrying the structured reason code.
- **Stale-eval badges** (grill-corrected): the gate ALREADY handles hard staleness — `resolve_health` flips suite stamps to UNKNOWN(stale) at `STALE_AFTER_DAYS = 14` (funds → caveated); the 07-01 stamps (13.99d, 14.7d) slipped past the `.days > 14` integer check. The display gap is *within* the window: a 13-day-old PASS renders with no age cue. Fix: the panel `ran_at` column always shows age (`· N天前`), amber ⚠ styled when age > `STALE_EVAL_DAYS = 10` — an early "re-run the live suite" cue. **Two constants, two meanings, both unchanged**: amber(>10d)=aging heads-up; UNKNOWN(>14d)=gate acted (renders as today). No gating change.
- **Bias-history timeline**: bare fund codes → `名称(代码)`.
- **盘中提示 wiring** (obligation inherited from CONTEXT.md "Flow freshness state" — "wiring lands with the report-v3 readability spec"): the existing `_provisional_flow_note` edge (one `fetch_flow_today_batch` call, render-only, NEVER persisted — the store's newest row stays a completed day) is wired into the per-fund flow rollup line as a clearly-labeled provisional annotation (`盘中主力净流入(截至HH:MM) …·盘中值，非因子输入`). Degrades to no annotation on any error; factor math untouched. Budget note: +1 proxied data-plane call at 12:15 (the 15:45 capture job makes its own) — within the tiny-burst budget the proxy trap requires.

## 9. Report layout (v3 order)

```
header (as_of · engine · prompt · schema · spend)
今日速览 (Comp 5)
explainer/disclaimer
summary table · heatmap · timeline (names, Comp 6)
宏观面速览 (theme-keyed, Comp 3)          ← macro context before the deep-dive
per-fund cards (theme chips; constituent narrative only; dark-data honest)
validation panel (+stale badges) · predictive panel
evidence appendix (deduped · dated · tiered, Comp 4)
```

## 10. Data flow

```
run_monitor (EDGE):
  theme_results = search once per unique theme        (Comp 2)
  tier gate filters hits; blocked dropped + logged    (Comp 1)
  per-fund pools assembled from theme_results (owner-bound, as today)
  impacts / scoring: UNCHANGED shape
  macro narrative call  (theme:<name> owners, CJK-guarded)   (Comp 3)
  (no per-fund narrative calls — fund cards are deterministic + drilldown + theme chips)
  render_report(views, macro_narrative, overview inputs, ...)  ← all pure
```

**Degradation**: search/LLM failure → empty pool / absent section, never a crashed run; language guard drops rather than blocks; tier config malformed → all tier 3 + warning; macro block absent → report renders without the section (like timeline/predictive panel today).

## 11. Testing (TDD, string-assert style matching existing render tests)

- `source_tiers`: classification truth table (blocked/1/2/3, suffix matching, unknown→3, malformed config→3).
- Consolidation: provider called exactly once per unique theme; per-fund pools equivalent to status quo for same hits; blocked hits absent from pools and impacts input.
- Language guard: CJK-ratio boundaries, retry path, persistent-failure drop; banned-verb guards still enforced.
- Macro block: ≤3 claims/theme cap, empty-evidence theme absent, fund chips deterministic from config; every fund card renders correctly with an EMPTY narrative doc (verdict/risk degrade path — assert through the real builder, not dict fixtures).
- Trace: `schema_version` 5→6, run-level `macro_narrative` present, old traces without the field still load (additive back-compat).
- 今日速览 gate-respect: an EVAL-GATED ADD_BIAS fund appears in 数据健康, never in 可操作.
- Panel vocabulary: informational stages render 观测 (never PASS); amber at `flow_cover` < 0.50; suite `ran_at` age display amber at >10d while >14d still shows UNKNOWN(stale).
- Citation index: many cids → one number; superscript anchors resolve to canonical `<li>`; date + tier badge present; first-seen order; `[ref:` closure invariant.
- Overview: flip/actionable/health row content; empty-row drop; all-empty quiet line; 限购 mark.
- Dark data: all-N/A column collapse with reason; flow chip at coverage 0 and below floor; panel amber state.
- Stale badges: 10-day boundary (9 green, 10 amber), date rendered.
- Invariants re-asserted: no `<script>`/remote refs; `基金概况` absent; engine version untouched.
- Signature-change discipline: `tests/monitor/` + `tests/commands/` per-file (whole-dir hangs) + eval tests; narrative live smoke stays double-gated.

## 12. Phasing (single PR, each phase TDD'd + committed atomically)

1. `source_tiers` module + config + ingest gate (Comp 1)
2. Theme-search consolidation (Comp 2)
3. Narrative v3: macro block replaces per-fund calls + guards + prompt bump + corpus update + trace field/schema 5→6 (Comp 3)
4. Citation render v2 (Comp 4)
5. 今日速览 (Comp 5)
6. Dark-data + stale badges + timeline names (Comp 6)

## 13. ADR

- **ADR 0022 — evidence source tiers gate ingest**: junk/blocked domains are dropped before scoring; unknown domains are kept as tier 3 and badged. Alternatives rejected: render-only demotion (junk keeps feeding the volatile macro_tilt), dropping unknowns (new legit sources silently vanish).
- **ADR 0017 addendum**: synthetic `theme:<name>` owners for the macro narrative pool (§4).

## 14. Risks / open items

- **Switchover-day bias shifts**: the tier gate changes macro_tilt inputs; a fund may flip bias on the first gated run. Accepted (macro_tilt is volatile by design); the 速览 flip row makes it visible.
- **MiniMax language compliance**: if the model persistently ignores 中文 even with the hardened retry, sections drop — the report gets quieter, not worse. Monitor drop counts in logs the first week.
- **Macro-block prompt size**: 8 themes × capped items; if MiniMax quality degrades on the combined call, fall back to per-theme calls (more calls, same structure) — note as a plan-level contingency.
- **Tier list maintenance**: unknown-domain churn is expected; promoting/blocking is a config edit, no code.

## 15. Out of scope

- Constituent saturation fix, macro_tilt evidence pinning/EWMA, weekly-pipeline stall diagnosis, WS-C scout (next spec), TTL cross-day stock→industry cache (note only), per-symbol daykline retirement (after B2 proves out).
