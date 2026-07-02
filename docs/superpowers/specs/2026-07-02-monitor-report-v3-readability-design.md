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
- No eval_trace schema bump: ingest drops are **logged**, not traced.

## 3. Component 1 — Source tiers + ingest gate (decision: gate at ingest, badge at render)

New pure module `src/irc/monitor/source_tiers.py`; config under `source_tiers:` in `config/monitor.yaml` (and the template in `src/irc/templates/config/monitor.yaml` — the #141 trap):

```yaml
source_tiers:
  blocked: [facebook.com, x.com, twitter.com, reddit.com, letsdatascience.com, mezha.net, ...]
  tier1:   [reuters.com, bloomberg.com, xinhuanet.com, gov.cn, pbc.gov.cn, ...]   # 权威
  tier2:   [cnbc.com, ft.com, wsj.com, kitco.com, mining.com, axios.com, eastmoney.com, ...]  # 财经媒体
```

- `classify(domain) -> "blocked" | 1 | 2 | 3` — **domain-suffix match** (subdomains inherit). Unknown → **tier 3 未分级, KEPT and badged** (a legit new source degrades to "visibly unvetted", never silently vanishes; promote/block later in config).
- Applied at the evidence edges (`_search_theme` result filtering and the constituent-pool builder) **before** `make_evidence_item` — blocked items never become evidence, never reach `gather_impacts`/macro_tilt, never get cids. Drop counts logged at warning level.
- Seed the lists from the observed 07-01 domains plus the CN financial domains the constituent pool actually uses.
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
- Output JSON keyed by theme: `{theme: [{claim, attribution_strength, citation_ids}]}` — rendered as theme-labeled Chinese subsections (中国货币政策 / 地缘政治 / 黄金驱动 / …) with anchors `#macro-<theme>`.
- Fund cards render **theme chips** linking to those anchors instead of repeating macro text 10×.

**Per-fund narrative** runs **only** for funds with a non-empty constituent pool (active_cn_equity). The prompt receives **only** constituent evidence — relevance enforced by construction. Gold/QDII cards show theme chips and no fund-level narrative call. Honest absence beats boilerplate; narrative LLM calls go 10 → ~8.

**Guards (deterministic, in `narrative.py`):**
- **Language guard**: CJK-ratio check per claim — CJK ≥ 30% of non-whitespace characters (deliberately tolerant of tickers/numbers/latin brand names). Failure → retry inside the existing schema-retry loop (max stays 2 retries) with a hardened 中文-only instruction; persistent failure → **drop the claim set for that section** (absent > English).
- **Cross-fund verbatim dedup** at render: normalized-text exact match keeps first occurrence. Belt-and-braces — pools are disjoint now, expected to fire ~never.
- Kept unchanged: attribution-verb bans (主因/导致/由于 gating), unresolved-citation rejection, sanitization, empty-pool early return.

**Consequences owned:**
- Narrative **prompt version bumps** (rendered in the report header).
- `narrative.json` stays keyed by fund id at top level; the macro block is stored under the reserved key `"__macro__"` (numeric fund ids can't collide). Additive for any existing reader.
- The `monitor_narrative` live_gated eval **corpus is updated** for the two new call shapes (macro-block call; constituent-only fund call). Lifecycle unchanged: still double-gated behind `IRC_RUN_LIVE_LLM_EVAL`.

## 6. Component 4 — Citation UX v2: dedup + dates + tier badges

`build_citation_index` gains a canonical identity key **`(url or title, date)`**:
- Index maps every cid → `(number, canonical_cid)`; superscripts link `#ev-{canonical_cid}`; the appendix renders **one `<li>` per article**: `N. {title} — {source} · {date} · {tier badge}`.
- Tier badges: 权威 / 财经媒体 / 未分级 (tier 3 styled muted). Appendix order stays first-seen. Hover `title` keeps source — now with date.
- `EvidenceItem.date` already exists and is currently discarded at render; no data-model change. `[ref:[0-9a-f]{16}]` matching unchanged.
- Expected: 07-01-shaped input goes 134 → ~36 entries; post-consolidation, near-1:1.

## 7. Component 5 — 今日速览 strip

New pure `src/irc/monitor/render_overview.py::overview_html(...)`, rendered directly under the header. Three rows (decision: no "biggest movers" row); each row dropped when empty; all empty → one muted line 今日无变化，数据健康.

- **偏向变化** — bias flips vs yesterday: `名称(代码) NEUTRAL→ADD_BIAS` with colored badges. Powered by the existing `prior_signal` read (the orange-dot data).
- **可操作** — funds currently at ADD_BIAS / REDUCE_BIAS, 限购-restricted marked (purchase table already fetched for heat).
- **数据健康** — counts with jump anchors: N 个因子暗 · M 只基金被评估门禁 · 过期评估 K.

All inputs already exist in the command layer; no new I/O.

## 8. Component 6 — Dark-data rendering + stale-eval badges + timeline names

- **Flow rollup honesty**: coverage below the 0.50 floor (including 0) renders a prominent 暗·覆盖不足 chip instead of anything PASS-adjacent. The eval-panel flow row separates the axes explicitly — `一致性 PASS · 覆盖 0%`, amber whenever coverage is below the floor while the factor is dark. "PASS" can no longer read as "data fine".
- **Dead dash columns**: pure helper `all_na_columns(rows)`; columns N/A for *every* row in the holdings board / factor table collapse to a single header note carrying the structured reason code.
- **Stale-eval badges**: validation-panel stage rows (impact/narrative LLM-quality stamps) get an age check against `STALE_EVAL_DAYS = 10` → amber `⚠ 过期 (ran YYYY-MM-DD)` instead of unconditional green. Closes the gap the predictive panel already handles.
- **Bias-history timeline**: bare fund codes → `名称(代码)`.

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
  per-fund narrative calls (constituent pools only, CJK-guarded)
  render_report(views, macro_narrative, overview inputs, ...)  ← all pure
```

**Degradation**: search/LLM failure → empty pool / absent section, never a crashed run; language guard drops rather than blocks; tier config malformed → all tier 3 + warning; macro block absent → report renders without the section (like timeline/predictive panel today).

## 11. Testing (TDD, string-assert style matching existing render tests)

- `source_tiers`: classification truth table (blocked/1/2/3, suffix matching, unknown→3, malformed config→3).
- Consolidation: provider called exactly once per unique theme; per-fund pools equivalent to status quo for same hits; blocked hits absent from pools and impacts input.
- Language guard: CJK-ratio boundaries, retry path, persistent-failure drop; banned-verb guards still enforced.
- Citation index: many cids → one number; superscript anchors resolve to canonical `<li>`; date + tier badge present; first-seen order; `[ref:` closure invariant.
- Overview: flip/actionable/health row content; empty-row drop; all-empty quiet line; 限购 mark.
- Dark data: all-N/A column collapse with reason; flow chip at coverage 0 and below floor; panel amber state.
- Stale badges: 10-day boundary (9 green, 10 amber), date rendered.
- Invariants re-asserted: no `<script>`/remote refs; `基金概况` absent; engine version untouched.
- Signature-change discipline: `tests/monitor/` + `tests/commands/` per-file (whole-dir hangs) + eval tests; narrative live smoke stays double-gated.

## 12. Phasing (single PR, each phase TDD'd + committed atomically)

1. `source_tiers` module + config + ingest gate (Comp 1)
2. Theme-search consolidation (Comp 2)
3. Narrative v3: macro block + constituent-only + guards + prompt bump + corpus update (Comp 3)
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
