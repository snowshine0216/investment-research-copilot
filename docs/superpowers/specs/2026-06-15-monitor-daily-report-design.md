# Design — Focused daily monitor brief (`irc monitor`) + configurable LLM provider + schedule rework

Date: 2026-06-15
Status: Approved design, revised after grilling (pending implementation plan)

> **Revision note (2026-06-15, grill-with-docs):** this supersedes the
> `…-watchlist-daily-report-design.md` draft. Nine decisions changed: the vertical
> is renamed `watchlist → monitor` (the word "watchlist" is reserved for the
> *discovered* set — see `CONTEXT.md`); the LLM change is **configurable provider
> routing**, not a global DeepSeek→MiniMax swap (DeepSeek retained); secrets are
> validated at the call edge; the per-fund output is a two-field tagged union
> (`status` + `bias`), not a three-field `direction/status/action`; monitor evidence
> is isolated from the dual-coverage gate ([ADR 0017](../../adr/0017-monitor-evidence-isolation.md));
> the schedule is a morning brief (09:00 + 13:00 retry, Asia/Shanghai); badge
> stability is handled statelessly; and factor-eligibility + weight vectors are
> per-`analysis_profile`. Details inline.

## 1. Goal

Replace the broad, universe-wide daily pipeline with a **focused daily brief on a
fixed, user-editable list of 7 funds** — the **monitor set**. For each fund the brief
shows:

1. **Current price** (latest unit NAV + date),
2. **The trend** (price history + line chart),
3. **A directional bias** (research signal — *not* an executable trade),
4. **The reason** — a causal, evidence-cited narrative explaining *why* the price
   moved and why the current bias, weighting world/macro news and constituent
   look-through.

Output is a **self-contained HTML report**, generated each trading morning on a
schedule. It is a **morning brief as of the prior trading day's close**: at the 09:00
fire time the latest *published* NAV is the previous trading day's (CN open-end NAV
publishes in the evening; QDII lags T+1/T+2), surfaced per-fund via `as_of_date`.
Two adjacent changes ship with it: make **LLM provider routing fully configurable**
(env-driven base_url + key + model, MiniMax added, DeepSeek retained), and **remove
the existing scheduled jobs**, replacing them with a focused daily monitor job + an
auto quarterly constituent-snapshot job.

### Non-goals

- No broad fund discovery / watchlist generation (the 7 funds are fixed input; the
  *discovered watchlist* is a different, generated concept — see `CONTEXT.md`).
- No executable portfolio actions (buy/trim/exit). Output is a *research bias* only;
  [ADR 0015](../../adr/0015-portfolio-action-emission-contract.md) owns action
  semantics and requires holdings/weights/thesis inputs this engine deliberately does
  not consume. **The monitor types never use the bare word "action".**
- No position-aware sizing (no `account.yaml` holdings dependency).

## 2. Architecture — new dedicated vertical (`irc monitor`)

A new command/stage package that orchestrates a **narrow** pipeline and reuses
existing **pure** internals (`research`, `fundamentals` look-through, `opportunity`
classifiers, `llm` gateway, spend gate) without disturbing the legacy `irc run`
pipeline, which remains runnable manually but unscheduled.

```
config/monitor.yaml  (7 funds — sole source of truth)
        │
        ▼
[narrow prefetch]  NAV history (7 ids) + index_valuation_history (their indices only)
        │                                   ── effects at the edge ──
        ▼
[research]  world/macro news per fund's explicit themes  +  per-holding news
        │
        ▼
[impacts]  MiniMax structured per-theme/holding impact  → impacts.json (persisted)
        │
        ▼
[signal]   pure: factors → eligibility gates → coverage gate → composite → bias  → signal.json
        │
        ▼
[narrative] MiniMax calibrated causal prose (no numbers, no markers) → narrative.json
        │
        ▼
[render]   pure: → self-contained report.html  (+ monitor.json machine summary)
```

**Contract:** the command reads **only** `config/monitor.yaml` for its funds and
themes. It never falls back to `config/universe/*`, `inputs/preferences.yaml`, the
research `_DEFAULT_THEMES`, `_derive_holdings_keywords` (preferences-derived), or any
discovered watchlist. Enforced by an acceptance test.

## 3. Section 1 — The monitor file (control surface)

Path: `config/monitor.yaml` (correct home: like `config/universe/*` it is a curated
fund list + scoring tuning with **no holdings** — `inputs/` is reserved for personal
portfolio data). Registered in `_FILENAME_TO_SCHEMA` (`config_loader.py:19`) so
`irc config validate` validates its **shape**.

**Loader split (sole-source contract).** The `irc monitor` *command* must **not** call
`load_repo_configs` — `ConfigBundle` has no monitor member and always loads `account`
/ `preferences` / `universe`, so reusing it (a) re-introduces the very
universe/preferences inputs the contract forbids and (b) makes the command fail when
unrelated *legacy* config is invalid. Instead add a **dedicated
`load_monitor_config(root)`** that loads only `config/monitor.yaml` (+ `llm.yaml` +
the spend configs the gate needs). Regression test: deliberately poison
`inputs/preferences.yaml` and `config/universe/*`, and `irc monitor` still runs.

Concerns are **separated** (the prior overload of `asset_class` was wrong — NAV
routing keys off `market == "cn_off_exchange"` + numeric ticker, see
`ingest_cmd.py:169`/`:605`):

- `market` — drives NAV fetch routing.
- `analysis_profile` — drives valuation / look-through behaviour, **factor
  eligibility, and the default weight vector** (a code-side registry, so it cannot be
  mis-set in the file). See the registry below.
- `themes` — static macro news streams (equal weight by default, or `{theme: weight}`
  map).
- `constituent_news` — directive to build fund-specific queries from cached top
  holdings (replaces the generic `holdings_sector` stream).

```yaml
# config/monitor.yaml — SOLE source of truth for `irc monitor`.
schema_version: 1

history:
  minimum_observations: 251        # ≥1 trading-year of valid NAV points required
  fetch_calendar_days: 550         # window fetched to guarantee that many
                                   # (QDII + CN/US holiday gaps make 365 too few)

defaults:
  return_windows: [5, 20, 60, 120, 250]    # trading-day windows reported
  signal_weights:                  # EQUITY default vector; per-profile vectors
    trend: 0.30                    # (in the analysis_profile registry) override this
    valuation: 0.20                # for thin profiles. VALIDATED: sum == 1.0 (±1e-6)
    heat: 0.15
    macro_tilt: 0.20
    constituent: 0.15
  signal_bands:                    # composite ∈ [-1,1]; VALIDATED buy > sell, both ∈ [-1,1]
    buy: 0.40                      # ≥ → ADD_BIAS  (widened from 0.33: stateless
    sell: -0.40                    # ≤ → REDUCE_BIAS  dead-band cuts daily flicker)
  minimum_confidence: 0.50         # signal_confidence < this → low_confidence / NO_CALL

funds:                             # name_cn is DISPLAY-ONLY (never used for routing)
  - { id: "008986", name_cn: 广发上海金ETF联接A,            market: cn_off_exchange, analysis_profile: gold,                   themes: [gold_drivers, geopolitics, us_monetary],                                constituent_news: false }
  - { id: "270023", name_cn: 广发全球精选股票(QDII)人民币A,  market: cn_off_exchange, analysis_profile: qdii_global,            themes: [global_growth, us_monetary, us_fiscal_politics, geopolitics, fx_cny],     constituent_news: true }
  - { id: "519069", name_cn: 汇添富价值精选混合,             market: cn_off_exchange, analysis_profile: active_cn_equity,       themes: [cn_monetary, cn_equity_property_policy],                                  constituent_news: true }
  - { id: "260112", name_cn: 景顺长城能源基建混合A,          market: cn_off_exchange, analysis_profile: active_cn_equity,       themes: [cn_equity_property_policy, cn_monetary, geopolitics],                     constituent_news: true }
  - { id: "006533", name_cn: 易方达科融混合,                market: cn_off_exchange, analysis_profile: active_cn_equity,       themes: [cn_monetary, geopolitics],                                               constituent_news: true }   # geopolitics = chip export-controls (tech/growth); 2nd theme satisfies the macro ≥2 gate
  - { id: "009225", name_cn: 天弘中证美互联网QDII,          market: cn_off_exchange, analysis_profile: qdii_china_us_internet, themes: [us_monetary, geopolitics, cn_equity_property_policy],                     constituent_news: true }
  - { id: "000083", name_cn: 汇添富消费行业混合,            market: cn_off_exchange, analysis_profile: active_cn_equity,       themes: [cn_monetary, cn_equity_property_policy],                                  constituent_news: true }
```

**Profiles registry** (code, `analysis_profile` → behaviour). The registry owns three
things per profile: look-through, **factor eligibility**, and the **default weight
vector** (so a profile never allocates weight to a factor it structurally cannot
fill — see §4/§5 for why this matters to the coverage gate):

| profile | look-through | valuation | eligible factors / default weights | notes |
|---|---|---|---|---|
| `gold` | none | **N/A** — commodity, no fundamental anchor (cf. `CONTEXT.md` Commodity-cyclical NAV-anchor exclusion) | `trend 0.45, macro_tilt 0.35, heat 0.20` | no equity constituents; `heat` is a bonus, not a lifeline |
| `qdii_global` | fund-level snapshot holdings | **N/A** — actively-managed global fund, no single tracking-index PE and no cached global stock-valuation histories | `trend 0.35, macro_tilt 0.35, heat 0.15, constituent 0.15` | not assumed US-heavy |
| `active_cn_equity` | active-fund snapshot holdings | **eligible** — holdings-weighted CN index PE/PB | full equity vector (`defaults.signal_weights`) | the 4 active mixed funds |
| `qdii_china_us_internet` | fund-level snapshot holdings | **eligible** — index-tracking (中证美互联网) has an index-PE anchor | full equity vector | **bypasses** the `us_etf` S&P/Nasdaq alias path (`lookthrough.py:142`) |

Per-fund `signal_weights` overrides in `config/monitor.yaml` compose on top of the
profile default vector (sum must still validate to 1.0).

**Themes** are owned by the monitor vertical (a theme→query-seed registry, decoupled
from research `_DEFAULT_THEMES`). Reused keys: `gold_drivers, geopolitics, us_monetary,
us_fiscal_politics, cn_monetary, cn_equity_property_policy`. **New keys** with their
own seeds: `global_growth`, `fx_cny`.

**Schema / validation** (new `MonitorConfig`, `src/irc/schemas/monitor.py`):
`schema_version` required; strict `^\d{6}$` ids; **duplicate-id rejection**;
`market`/`analysis_profile` required enums; per-fund `signal_weights` / `themes` /
`signal_bands` overrides allowed; effective `signal_weights` (profile default ⊕
override) sum to 1.0; `buy > sell`, both ∈ [-1,1]; `name_cn` documented display-only.

## 4. Section 2 — Factors, retrieval, scoring

Each factor → **[-1,+1]** or **N/A**. "Current price" = latest **unit** NAV (display
only); **all performance math uses `COALESCE(nav_acc, nav)`** (total return,
distribution-safe — `discover_cmd.py:83` already uses this pattern). **Factor
eligibility is per-`analysis_profile`** (§3): a factor a profile does not list is N/A
by construction and carries no weight, so a coverage-gate failure means a genuine
evidence gap, never a structural weight-allocation mismatch.

| Factor | Measures | Retrieval (explicit) | Freshness | → [-1,+1] |
|---|---|---|---|---|
| **trend** | momentum & structure | `fetch_fund_nav_history()` (`akshare_client.py:136`, returns `date, nav, nav_acc`) → `nav_history`; returns over `[5,20,60,120,250]`d on **acc**, MA20×MA60, MA60 slope, 250d drawdown | **fresh daily** | deterministic blend of medium-term acc-return + MA structure. **The exact `→[-1,+1]` blend MUST be pinned in the implementation plan and TDD'd first** — `trend` is the highest-weighted factor *and* gates the entire directional call |
| **valuation** | cheap ↔ expensive | **cached** `index_valuation_history` (PE/PB pctile; `_index_valuation_metrics`, "R3 — no live fetch", `inputs_loader.py:162`); active funds also need `lookthrough_cfg.enabled` + cached holdings + cached stock-valuation histories + coverage gate | cached (narrow-prefetched) | `valuation_state` → fixed map. **Eligible only where the profile has a real anchor + cached data** (`active_cn_equity`, `qdii_china_us_internet`); N/A for `gold` (commodity) and `qdii_global` (active, no anchor) |
| **heat** | **crowding** (not returns) | 限购 subscription-restriction status (fresh) + AUM/share QoQ Δ (snapshot). **Drops `_heat_score`** — it averages `ret_1m/3m/6m/12m` (`states.py:344`) and for off-exchange funds (null premium/flow) would duplicate trend | fresh + cached | restriction + rapid inflow → − (overheated); no data → N/A |
| **macro_tilt** | weighted world/macro news | `research` pipeline w/ the monitor's **explicit** themes → evidence pool; MiniMax `monitor_impact` per theme | **fresh daily** | deterministic `Σ θ_wt·impact·confidence`, clamped |
| **constituent** | top-holdings health | holdings identities/weights from **cached snapshot** (read-only; snapshot bundles holdings+filings+broker+news per `snapshot.py:313`); **separate daily news fetch** per top holding, merged in-memory (snapshot never rewritten); MiniMax `monitor_impact` per holding | holdings cached / news fresh | weight-weighted `Σ holding_wt·impact·confidence`, clamped |

**Deterministic numeric maps** (code, configurable):
- `valuation_state`: `cheap=+1.0, fair_cheap=+0.5, fair=0, fair_expensive=-0.5,
  expensive=-1.0`; else N/A.
- `heat`: crowding index {限购 tier, AUM Δ%} → overheated `-1` … calm `+0.3`; no data
  → N/A.
- `macro_tilt`/`constituent`: numeric by construction; N/A when evidence pool empty.

**Per-factor eligibility gate** — a numeric value alone is not enough; a factor enters
the present-set `P` only if (a) its profile lists it eligible AND (b) its quality gate
passes, else it is N/A with a recorded reason:
- `trend`: ≥ `minimum_observations` (251) valid acc-NAV points.
- `valuation`: profile-eligible + cached history present + min-history gate (+ active:
  lookthrough coverage).
- `heat`: 限购 status or AUM Δ present.
- `macro_tilt`: ≥2 themes each with ≥1 *valid* citation. **Consequence:** a fund
  configured with a single theme permanently forfeits its `macro_tilt` weight (→ N/A,
  renormalized away). Every fund in the sample now carries ≥2 themes so none is
  silently macro-blind; a single-theme fund is a deliberate, surfaced forfeiture.
- `constituent`: profile-eligible + holdings coverage ≥ threshold and ≥1 holding with
  a valid news citation.

**Evidence + citation contract ([ADR 0017](../../adr/0017-monitor-evidence-isolation.md)):**
the monitor uses its **own `EvidenceItem`** — `(source, title, date, url,
owner_fund_id, citation_id)`, **no `scope` field** — and does **not** reuse
`ThesisEvidence`. Evidence is owner-bound *by construction* (each fund's pool is built
only from that fund's themes/holdings), so there is no scope to promote. `citation_id`
is 16 hex chars only so the shared `\[ref:[0-9a-f]{16}\]` marker regex matches; its
preimage is the monitor's own (e.g. `sha256(owner_fund_id:url_or_fallback:date)`),
independent of ADR 0001's `ThesisEvidence` preimage. Every `citation_id` in a
structured impact must resolve in the supplied (per-fund) evidence pool; unknown id →
reject + retry. The monitor evidence machinery and the dual-coverage gate **never
touch** — a macro headline can never leak in as instrument-scoped evidence.

**Per-fund provenance** (report + JSON): `as_of_date` (latest NAV date), per-factor
freshness (fresh/cached + cache date), `available_weight`, `missing_factor_reasons[]`.

## 5. Section 3 — Signal engine (pure)

Output is a **research bias**, never an executable action
([ADR 0015](../../adr/0015-portfolio-action-emission-contract.md)). The per-fund
classification is a **two-field tagged union** — there is no stored `action` field:

- `status ∈ {ok, insufficient_evidence, low_confidence}` — the gate outcome.
- `bias ∈ {ADD_BIAS, NEUTRAL, REDUCE_BIAS} | null` — **null iff `status ≠ ok`**.
- **`NO_CALL`** is a *derived render label* (= `status ≠ ok`), **not** a stored field.
- **Contract: `NO_CALL` ≠ `NEUTRAL`.** Structural — they are different fields (one is
  `status ≠ ok`, the other is `bias = NEUTRAL`), so nothing *can* fold them. A
  consumer that maps `bias=null` → NEUTRAL is a bug; a test guards it.

1. **Present set & available weight.** `P` = factors passing the per-profile
   eligibility gate; `available_weight = Σ_{i∈P} wᵢ` over the **effective** (profile
   ⊕ override) weights. Because the profile vector never allocates weight to
   structurally-N/A factors, a thin fund (gold) can still reach the threshold off its
   genuine families.
2. **Coverage gate (counts independent evidence *families*, not factor names).**
   Families: `{price-momentum: trend}`, `{valuation}`, `{crowding: heat}`,
   `{news: macro_tilt, constituent}`. Directional call requires: `trend` eligible
   **and** ≥2 families present **and** `available_weight ≥ 0.60`. Else
   `insufficient_evidence` (→ `bias = null`, render `NO_CALL`).
3. **Combine.** `w'ᵢ = wᵢ / available_weight`; `C = Σ w'ᵢ·sᵢ`, **rounded 4 dp**.
4. **Confidence GATE (fully specified; bands never move).** Deterministic factors
   (trend/valuation/heat) → `conf = 1.0` (gate guarantees quality). News factors →
   `conf = Σ(θ_wt·item_conf) / Σ θ_wt` over themes returning a valid structured impact
   (impact 0 included); missing item-confidence → `0`. `signal_confidence = Σ
   w'ᵢ·confᵢ`, rounded 4 dp. `signal_confidence < minimum_confidence` (config, default
   0.50) → `low_confidence` (→ `bias = null`, render `NO_CALL`).
5. **Bands (fixed, config; default ±0.40):** `C ≥ buy` → ADD_BIAS; `C ≤ sell` →
   REDUCE_BIAS; else NEUTRAL. Applied only when `status = ok`.
6. **Divergence predicates** (explicit thresholds on the [-1,1] scale — *not* the
   percentile `valuation_divergence_code`): `trend_valuation_conflict` (`trend ≥ +0.3
   ∧ valuation ≤ -0.3`, symmetric); `trend_macro_conflict` (`sign(trend) ≠
   sign(macro_tilt) ∧ |·| ≥ 0.3`); `low_factor_agreement` (stdev ≥ 0.5 or split
   signs). Emitted as reason codes + narrative caveats.
7. **Reproducibility.** The LLM structured impacts are persisted as an immutable
   artifact (`impacts.json`); the signal is a **pure function of** that artifact + NAV
   + cached valuation. Same artifacts → identical signal. (temp 0 alone is
   insufficient across model drift.)

**Badge stability (stateless; v1).** Two stateless mechanisms cut the daily badge
flicker a hard-band classifier would show on a brief read every morning:
- **Wider bands** (±0.40 default) give NEUTRAL a genuine center so only decisive
  composites earn a directional badge.
- **Distance-to-edge + changed-since-yesterday** are rendered (§7). The pure signal
  function stays today-inputs-only; the *renderer* takes an **optional injected
  `prior_signal`** (the edge reads yesterday's `signal.json`; missing/corrupt → `None`
  → the changed-flag is simply absent, never blocks). No cross-run state feeds the
  computation, so the v2-hysteresis safety problem is not reintroduced.

**Hysteresis — OFF in v1.** v1 = pure per-day classification, no cross-run state in
the *computation*. Recorded v2 spec, to build only with tests proving a stale signal
can never survive an evidence failure:
```
NEUTRAL→ADD_BIAS:    C ≥ 0.45      ADD_BIAS→NEUTRAL:    C < 0.35
NEUTRAL→REDUCE_BIAS: C ≤ -0.45     REDUCE_BIAS→NEUTRAL: C > -0.35
ADD_BIAS↔REDUCE_BIAS: only via the far band (no direct flip)
precedence: insufficient_evidence / low_confidence ⇒ NO_CALL ALWAYS wins; prior never survives as actionable
prior ignored when: missing/corrupt artifact, age > 7d, or weights/engine-version hash changed; same-day rerun reuses (idempotent)
```

**Per-fund record:** `status, bias, C, signal_confidence, present_families,
available_weight`, per-factor contribution table (`w'ᵢ·sᵢ`, conf, eligibility/reason),
divergence codes, provenance, impacts-artifact ref.

## 6. Section 4 — Causal narrative (MiniMax)

The narrative **explains** the computed signal; it never alters it (mirrors the
existing memo pillar-lock pattern: deterministic sections authoritative; LLM prose
delimited). Two MiniMax tasks: `monitor_impact` (structured impacts, §4) and
`monitor_narrative` (prose). Both temp 0.

1. **Calibrated attribution — no false causation.** The LLM emits structured claims,
   never free causal verbs:
   ```json
   { "claim": "实际利率上行可能对金价构成逆风",
     "attribution_strength": "consistent_with",  // supported_attribution | consistent_with | possible_driver | unknown
     "citation_ids": ["…"] }
   ```
   The renderer maps tier → fixed hedge wording and **bans 主因/导致/由于 unless
   `supported_attribution`** (a source explicitly attributes the move). Strong-verb ban
   enforced in the renderer + tested.
2. **No LLM-authored markers.** The model emits only `{claim, attribution_strength,
   citation_ids}`. The renderer validates each `citation_id` (16-hex, resolves in the
   fund's pool, owner-bound) and **then appends `[ref:…]` markers deterministically** —
   marker/array can't drift. *Honest limit:* validation proves the source exists + is
   owner-bound, not that it semantically supports the claim — hence the declared tier,
   hedged rendering, and an evidence appendix (original-language title + date +
   snippet) for human check. (v2 optional: a second LLM judge scores claim↔source
   support; deferred — doubles cost.)
3. **No number restatement.** LLM fields are qualitative only
   (`price_action_commentary`, `signal_rationale_commentary`, `risk_commentary`). The
   deterministic renderer places the locked return table + factor contributions beside
   the prose.
4. **Local schema enforcement** (the chat payload sends only
   `model/messages/temperature/max_tokens` — `http_client.py:49` — no provider JSON
   mode): extract JSON → Pydantic validate → schema-invalid success triggers a
   **separate schema-retry policy** (max 2), distinct from `retry_call_chat`'s
   transport retries (`retry.py:103`). **Every completed-but-invalid call is billed and
   recorded.** Typed failure reasons: `schema_invalid`, `unresolved_citation`,
   `banned_verb`, `empty_pool`.
5. **Prompt-injection boundary.** Titles/snippets are untrusted: reuse memo's
   `sanitize_refs_for_auditor` injection-pattern redaction (`pipeline.py:102`), wrap
   evidence in explicit delimiters, instruct the model that delimited content is data,
   not instructions.
6. **Persistence with input identity.** `narrative.json` + `impacts.json` each record
   `fund_id, input_hash, evidence_hash, signal_hash, prompt_version, schema_version,
   provider, model, generated_at, status`. **Never reuse when any hash changes.**
   Atomic write (`.tmp.{pid}→os.replace`).
7. **Spend wiring** (so preflight prices it — `resolve_scope` returns empty for unknown
   commands, `scope.py:49`): add both tasks to `config/llm.yaml`;
   `COMMAND_TASKS["monitor"] = ("monitor_impact","monitor_narrative")` plus a **new
   `COMMAND_SEARCH_PROVIDERS`** table (`monitor → tavily/brave/bocha/jina`) with
   `resolve_scope` extended to return it for commands; add `config/spend_pricing.yaml`
   seeds; **dynamic** call estimate = f(fund_count, themes/fund, holding-queries/fund,
   schema-retry budget) — not hard-coded 7. The estimator is **seed-table + static
   `UsageProfile`** (`estimator.py`), so this requires building a real per-run
   `UsageProfile` from the monitor config counts, not a fixed seed — else preflight
   undercounts search/retry cost. Satisfies
   `test_every_llm_yaml_task_is_mapped_somewhere`.

**Degradation contract:** narrative may fail and the report still ships **iff**: no
partial/invalid prose rendered; `narrative_status` + typed reason shown; deterministic
facts/signal/evidence intact; spend from failed/invalid completed calls still recorded.

**Language:** Chinese-primary + English machine labels
(`ADD_BIAS/NEUTRAL/REDUCE_BIAS/NO_CALL`); evidence appendix preserves original-language
source titles to avoid translation-induced claim drift.

## 7. Section 5 — Self-contained HTML report

**Pure renderer:** `(signal_records, narratives, evidence_pool, provenance,
prior_signal, now) → html_string`. No I/O inside; deterministic; `now` and
`prior_signal` injected so tests pin them (`prior_signal` is `None`-tolerant — its only
effect is the optional changed-since-yesterday flag). Atomic write to
`outputs/<date>/monitor/report.html`, beside `signal.json`, `impacts.json`,
`narrative.json`, `monitor.json`.

**Self-contained & offline (hard requirement).** Zero external requests — no CDN /
remote fonts / remote JS. Interactivity via **native primitives, no JS framework**:
collapsible evidence → `<details>/<summary>`; chart tooltips → SVG `<title>`. v1 ships
**no JavaScript** → fully static, deterministic, opens anywhere.

**Charts — server-side inline SVG** from the **acc-NAV** series: price `<path>` with
coordinates **rounded to fixed precision** (byte-stable); deterministic axis ticks;
**causal-event markers** at each dated impact item (snapped to nearest NAV date,
colored by impact sign, `<title>` = claim + source + date) — the visual "why it
moved"; off-window events noted in the appendix.

**Layout:** (1) run header — `as_of_date`, per-factor freshness, engine/prompt/schema
versions, spend; (2) summary table — all 7 funds: name · NAV+date · one **bias badge**
(`ADD_BIAS/NEUTRAL/REDUCE_BIAS` when `status=ok`, else a distinct **`NO_CALL`** badge)
· composite `C` + distance-to-edge · changed-since-yesterday flag; (3) per-fund card —
header → SVG chart w/ markers → locked return table → factor-contribution table →
narrative commentary with deterministic `[ref:…]` anchors → divergence caveats; (4)
evidence appendix — collapsible, original-language titles + date + source + snippet +
anchor targets.

**XSS/escaping:** every untrusted title/snippet/url and all LLM prose is
**HTML-escaped** before interpolation — no raw HTML. Tested with a hostile-title
fixture.

**Report invariants (mirroring H3 / SAME-3, ADR 0004):** every fund appears in the
summary + has a card, including `NO_CALL`/data-gap funds (no silent drops); the set of
rendered `[ref:…]` anchors == the set of ids in the evidence appendix (no orphans / no
uncited clutter). Enforced by test.

**Determinism:** byte-stable given identical inputs (incl. `prior_signal`); funds in
monitor order; coordinates rounded; the only volatile field (`generated_at`) rendered
in one controlled, test-injectable spot. Golden-file test asserts stability.

## 8. Section 6 — Configurable LLM provider routing (env-driven base_url + model)

The change is **configurability**, not a one-way swap: generalize provider routing so
base_url + key + model are env-indirected and per-task selectable, add MiniMax as a
provider, point only the new `monitor_*` tasks at it, and **leave the legacy tasks on
DeepSeek**. Adding a third provider later is a `config/llm.yaml` edit, not a code
change. **DeepSeek is retained** (not removed).

- **Schema** (`schemas/llm.py`): `ProviderConfig` gains optional `base_url_env` +
  `default_model_env`; `base_url` optional; `model_validator` requires **exactly one**
  of `base_url`/`base_url_env`. `TaskRoute.model` optional → resolved from the
  provider's `default_model_env` when omitted (validator requires resolvability).
- **Edge resolution** (`http_client.py`): add `_resolve_base_url` / `_resolve_model`
  beside `_resolve_key`, reading env at call time. **Re-run `_validate_base_url`
  (SSRF guard) on the env-resolved URL** — env must not bypass the private-IP check.
  `resolve_route` stays pure (`ResolvedRoute` extended with names + literals).
- **`config/llm.yaml`:**
  ```yaml
  providers:
    deepseek: { base_url: https://api.deepseek.com, api_key_env: DEEPSEEK_API_KEY }   # retained
    minimax:  { base_url_env: MINIMAX_BASE_URL, api_key_env: MINIMAX_API_KEY, default_model_env: MINIMAX_MODEL }
    # openrouter: { … }   # add later by config alone
  tasks:
    # legacy tasks stay on deepseek (unchanged):
    memo_synthesis:   {provider: deepseek}
    memo_audit:       {provider: deepseek}
    watchlist_reason: {provider: deepseek}
    …all existing tasks…
    # new monitor tasks → minimax, model omitted (→ MINIMAX_MODEL):
    monitor_impact:    {provider: minimax}
    monitor_narrative: {provider: minimax}
  ```
- **Required-secret model (resolves the prior "blocker").** `settings.py:18` currently
  makes `deepseek_api_key` **required** (`Field(min_length=1)`), and `research_cmd.py:65`
  constructs `Settings()` directly. Make **neither** key required at `Settings()`
  construction — both `deepseek_api_key` and `minimax_api_key` become `Optional` — and
  validate the key **at the call edge**, when a task resolves to its provider. So
  `irc monitor` (only `monitor_*` → MiniMax) needs only `MINIMAX_*`; `irc run` (DeepSeek
  tasks) needs `DEEPSEEK_API_KEY`; each raises a clear "missing key for provider X" only
  if that provider is actually invoked. Update CLAUDE.md / README, which currently state
  `DEEPSEEK_API_KEY` is required for full validation. **Acceptance test:** `MINIMAX_*`
  present + `DEEPSEEK_API_KEY` absent → `irc monitor` reaches provider routing without
  raising; and `DEEPSEEK_API_KEY` present + `MINIMAX_*` absent → legacy `irc run` LLM
  tasks still route.
- **`irc config validate` stays secret-free** (structural only; env presence checked at
  call time).
- **Per-model spend pricing (env-resolved model).** Pricing/seeds are keyed by **model
  name** (`config/spend_pricing.yaml`), but the MiniMax model comes from `MINIMAX_MODEL`
  at runtime. The preflight gate must find a pricing seed for whatever `MINIMAX_MODEL`
  resolves to; add a MiniMax seed (and a documented fallback when the exact model id is
  unseeded) so preflight neither crashes nor silently prices at zero. DeepSeek seeds are
  unchanged.
- **Integration risks to verify in build (not assume):** path `…minimaxi.com/v1` →
  `/v1/chat/completions` (confirm via one `RUN_LIVE_LLM_TESTS` smoke call); **MiniMax
  can return HTTP 200 with an error envelope** (`base_resp.status_code ≠ 0`) —
  `_parse_response` must detect a non-zero `base_resp` and raise.

## 9. Section 7 — Schedule rework

- **Remove both** current jobs: `ops/launchd/uninstall.sh` boots out + deletes
  `com.irc.daily` and `com.irc.weekly-full`. Run it.
- **Add `com.irc.monitor` + `run-monitor.sh`**, modeled on the proven `run-daily.sh`:
  trading-day gate (`TZ=Asia/Shanghai`, skip weekend/holiday), fresh per-run log,
  **StandardOut/Err → /dev/null** (the provenance-xattr fix), **retry-only idempotency
  guard** (skip if today's `report.html` exists — `report.html` is the atomic
  end-of-run success artifact, so a failed fire leaves none and the next retries; no
  `PIPELINE_HALTED` equivalent needed), runs `uv run irc monitor`, then `notify-status`.
  Schedule **Mon–Fri 09:00 (primary) + 13:00 (retry)**. Rationale: a morning brief reads
  the prior trading day's *complete* published NAV and the overnight global session's
  news — the partial-evening-publication problem disappears; 13:00 fires only if 09:00
  failed (nothing material changes intraday). Staleness/QDII lag surfaced via
  `as_of_date`, not chased.
  **Notify semantics:** add a **new `monitor` run-kind** to `notify-status` whose
  success detection looks for `outputs/<date>/monitor/report.html` — otherwise a
  successful run notifies as "failed / no output."
- **Add `com.irc.fundamentals-quarterly` + `run-fundamentals.sh`** — auto refreshes
  constituent data for the 7 funds once a quarter. **Blocker fixed by a monitor-aware
  snapshot path:** the existing `irc fundamentals snapshot --target` expands registry
  names and builds every target as `LookthroughTarget(kind="broad_index", …)`
  (`fundamentals_cmd.py:61`); fund-level / active-fund snapshots only happen when callers
  pass typed `LookthroughTarget`s with `provider_symbol` (`snapshot.py`). Add a new
  **`irc monitor snapshot`** subcommand that, per each fund's `analysis_profile`,
  constructs `active_fund` (active_cn_equity) or `fund_level` (gold / qdii_*) targets
  keyed by `provider_symbol = fund_id`. The quarterly job calls **that**, not the
  broad-index path (which would silently refresh the wrong domain).
- **Cold-start bootstrap.** Because the per-profile weights put `valuation` +
  `constituent` on data that comes *only* from the snapshot, the active funds are
  degraded (those factors N/A → possibly `NO_CALL`) until the first snapshot exists.
  `install.sh` (and the monitor README setup steps) **run `irc monitor snapshot` once at
  install** so day-one briefs aren't half-empty; the quarterly job then maintains it. If
  the quarterly job later lapses, the affected factors → N/A (surfaced, not silent).
- `install.sh`/`uninstall.sh` `LABELS`+`WRAPPERS` arrays updated for the two new jobs.
  **launchd, not cloud** — needs local AkShare + `.env` + DuckDB + the repo.
- **Self-sufficiency:** the daily job is self-contained for NAV + news + valuation (it
  narrow-prefetches `index_valuation_history` for **only** the 7 funds' reference
  indices — not a broad universe ingest). Constituent holdings come from the quarterly
  snapshot.
- **Docs/acceptance:** updating `README.md` and `ops/launchd/README.md` is part of the
  work — new fire times (09:00/13:00), the new labels (`com.irc.monitor`,
  `com.irc.fundamentals-quarterly`), removed labels, and the required-secret change
  (call-edge validation; `DEEPSEEK_API_KEY` no longer hard-required). Stale times/labels
  in plists/README count as acceptance failures.

## 10. Proposed module layout

```
src/irc/monitor/
  __init__.py
  types.py            # frozen dataclasses: MonitorFund, FactorScore, SignalRecord, Claim, NarrativeDoc, EvidenceItem (no scope; owner_fund_id)
  profiles.py         # analysis_profile → behaviour registry (look-through + factor-eligibility + default weight vector); theme → query-seed registry
  fetch.py            # (edge) narrow NAV + index-valuation prefetch for the 7 ids
  trend.py            # pure: acc-NAV series → returns/MA/drawdown → trend sub-score (blend pinned in plan)
  factors.py          # pure: per-profile + per-factor eligibility gates + numeric maps → FactorScore
  signal.py           # pure: coverage gate → composite → confidence gate → (status, bias) + divergence
  impacts.py          # (edge) MiniMax monitor_impact: structured per-theme/holding impacts + persist
  narrative.py        # (edge) MiniMax monitor_narrative: calibrated claims + persist
  render_html.py      # pure: (…, prior_signal, now) → self-contained report.html
  snapshot_targets.py # pure: monitor fund + analysis_profile → typed LookthroughTarget (active_fund / fund_level, provider_symbol=id)
src/irc/schemas/monitor.py       # MonitorConfig (+ validation)
src/irc/config_loader.py         # + load_monitor_config(root) — narrow loader (NOT load_repo_configs)
src/irc/settings.py              # deepseek_api_key + minimax_api_key both Optional; validated at call edge
src/irc/commands/monitor_cmd.py  # thin: load_monitor_config, preflight_gate, orchestrate, write, record_command_run; + `snapshot` subcommand
ops/launchd/run-monitor.sh, com.irc.monitor.plist
ops/launchd/run-fundamentals.sh, com.irc.fundamentals-quarterly.plist  # calls `irc monitor snapshot`
```
CLI: `irc monitor` and `irc monitor snapshot` (in `cli.py`).

## 11. Testing strategy (TDD)

- **Schema:** id regex, duplicate rejection, effective-weights-sum-1.0 (profile ⊕
  override), buy>sell bounds, base_url XOR base_url_env, model resolvability.
- **Profiles:** per-profile factor-eligibility (gold: valuation/constituent N/A;
  qdii_global: valuation N/A; qdii_china_us_internet + active_cn_equity: valuation
  eligible); per-profile default weight vectors sum to 1.0.
- **Factors:** each eligibility gate (pass/N-A + reason); numeric maps;
  distribution-safe returns on acc-NAV; heat-not-trend (null premium/flow → heat N/A,
  not a return echo).
- **Signal:** coverage gate (family counting, the **gold worked example** — passes off
  trend+macro with the gold weight vector even when heat is N/A); confidence gate →
  NO_CALL; **`NO_CALL` (bias=null) ≠ NEUTRAL** (the tagged-union guard); band edges
  (±0.40); divergence predicates; reproducibility (same artifacts → identical signal).
- **Impacts/narrative:** citation resolution + owner-binding (own `EvidenceItem`, no
  scope), unknown-id reject, banned-verb reject, schema-retry counts billed, injection
  sanitization, persistence hash invalidation, MiniMax `base_resp` error detection.
- **Render:** golden-file determinism (incl. injected `prior_signal`), hostile-title
  XSS escape, universal-rows + citation-closure invariants, `NO_CALL` badge distinct,
  changed-since-yesterday flag present/absent on prior-signal present/missing.
- **Scope/spend:** `monitor` command resolves the right tasks + search providers;
  dynamic estimate scales with fund/theme/holding counts; completeness test green.
- **Contract:** the command reads neither `inputs/preferences.yaml` nor
  `config/universe/*` and passes explicit themes; runs even when those legacy files are
  poisoned/invalid (via `load_monitor_config`).
- **Settings:** `MINIMAX_*` present + `DEEPSEEK_API_KEY` absent → `irc monitor` reaches
  provider routing without raising; `DEEPSEEK_API_KEY` present + `MINIMAX_*` absent →
  legacy LLM tasks still route.
- **Snapshot:** `irc monitor snapshot` builds `active_fund` / `fund_level` targets keyed
  by `provider_symbol=fund_id` (never `broad_index`) for the 7 ids.
- **Notify:** the `monitor` run-kind reports success iff
  `outputs/<date>/monitor/report.html` exists.
- **Live (double-gated):** `RUN_LIVE_LLM_TESTS` MiniMax smoke; `IRC_RUN_LIVE_AKSHARE`
  NAV fetch for the 7 ids.

## 12. Open verification items (resolve during build, not assumed)

1. MiniMax OpenAI-compatible path + auth header (one live smoke call).
2. MiniMax `base_resp` error-envelope shape on HTTP 200.
3. AkShare 限购 / AUM-change endpoints actually available for these 7 ids; if not,
   `heat` ships as N/A (per-profile weights + coverage gate already tolerate it — gold
   no longer depends on heat to earn a bias).
4. QDII NAV publication lag for 270023 / 009225 (affects `as_of_date`, not correctness).
5. `qdii_china_us_internet` index-PE anchor + cached history actually available for
   009225; if not, valuation degrades to N/A for that profile (surfaced).
6. `fetch_calendar_days: 550` actually yields ≥251 valid acc-NAV points for the QDII ids
   given holiday gaps; widen if not.

## 13. Decisions log

- Architecture: **A** — new dedicated `irc monitor` vertical (renamed from `watchlist`
  to avoid colliding with the *discovered watchlist*; see `CONTEXT.md`).
- Signal: directional **bias** (ADD_BIAS/NEUTRAL/REDUCE_BIAS) + **NO_CALL** as a
  two-field tagged union (`status` + `bias`); no stored `action` field; "action" banned
  from monitor types; not executable actions; no holdings dependency.
- Evidence: monitor's own `EvidenceItem`, no `scope`, walled off from the dual-coverage
  gate ([ADR 0017](../../adr/0017-monitor-evidence-isolation.md)).
- Coverage: factor-eligibility + default weight vectors are **per-`analysis_profile`**;
  fixes the gold `NO_CALL` cliff and the valuation contradiction.
- Data: narrow per-fund fresh NAV + fresh news + deep causal analysis; **not** a broad
  universe search.
- Report: **self-contained HTML**, no JS, SVG charts + event markers; stateless badge
  stability (±0.40 bands + injected `prior_signal` changed-flag).
- LLM: **configurable provider routing** (base_url + key + model from `.env`); MiniMax
  added; **DeepSeek retained**; secrets validated at the call edge.
- Hysteresis: **off** in v1 (v2 spec recorded).
- Schedule: **remove both** old jobs; add daily monitor (**09:00 + 13:00 retry**,
  retry-only) + **auto quarterly** fundamentals snapshot via `irc monitor snapshot`;
  cold-start bootstrap at install.
- Language: Chinese-primary + English machine labels.

## 14. Provenance — review + grilling

**Adversarial review (2026-06-15, read-only pass)** — seven findings verified against
the code and folded in (settings DeepSeek requirement → call-edge validation §8;
quarterly snapshot domain → `irc monitor snapshot` §9/§10; spend preflight dynamic
estimate §6/§8; sole-source vs ConfigBundle → `load_monitor_config` §3; single-theme
macro block → §3 sample + §4 forfeiture rule; notify run-kind → `monitor` run-kind §9;
docs/plist drift → §9 acceptance).

**Grilling (2026-06-15, grill-with-docs)** — nine decisions resolved and reflected
above; terminology captured in `CONTEXT.md` (Monitor set, Directional bias, NO_CALL,
`analysis_profile`, `EvidenceItem`) and the evidence-isolation boundary in
[ADR 0017](../../adr/0017-monitor-evidence-isolation.md).
