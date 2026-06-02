# `irc narrative` — Thematic Fund Mining + Full-Spectrum Per-Fund Analysis — Design

**Date:** 2026-06-02
**Status:** Approved (brainstorm) → pending implementation plan
**Author:** pairing session (narrative mining: 算力金属 / AI / robots)

## Context

A user wants to analyse the funds tied to a *narrative* — first **算力金属** (compute-demand
metals), later **AI** and **robots** — and decide, per fund, **whether to invest and at what
risk level**. Two problems block this today:

1. **Selection.** `irc eval-funds` only accepts an explicit `--ids` / `--ids-file` list
   (`src/irc/commands/fund_eval_cmd.py:22`). There is no way to go from a narrative keyword to a
   fund set. The `Theme` vocabulary is a fixed 13-value `Literal` (`src/irc/schemas/_types.py:17`);
   the closest concept is the coarse `metals` theme, and `算力金属` / `robots` are not modelled at
   all. These narratives are **cross-cutting** — they don't map cleanly to one fund-name keyword or
   one theme (compute-metals = copper/aluminium/tin driven by AI-datacenter demand; AI spans
   算力/芯片/光模块; robots spans 机器人/智能制造).
2. **Risk read.** The deep analysis machinery exists (5 state dimensions + `risk_action` +
   thesis cards + cited evidence, via `build_opportunity_row` / `derive_risk_action`), but
   `risk_action` (exit/trim/review) is for **positions already held**. There is no consolidated
   **risk level** for a *prospective* buy.

This command adds a narrative-driven selector in front of the existing opportunity-grade
analysis, plus a new prospective-buy risk level. It reuses the pipeline's classification cores
verbatim and keeps the new "selector" concern off the load-bearing determinism / citation
invariants.

## 1. Goals

- Resolve a narrative (e.g. `compute_metals`) to a ranked **shortlist of funds** by
  **holdings look-through**: a fund qualifies when its disclosed top-10 overlaps a curated,
  frozen **reference basket** of stocks/industries.
- Run the system's **deepest per-fund analysis** (opportunity-grade) on the shortlist:
  5 sub-states, `opportunity_state`, `dca_action`, `risk_action`, falsification/trim triggers,
  review cadence, and cited thesis evidence (holdings-level **and** fund-level).
- Emit a new, deterministic **`position_risk_level`** ∈ `{low, moderate, elevated, high,
  insufficient}` for the invest decision, with a rationale naming the dominant drivers.
- Be **reusable** for new narratives (AI, robots) by adding a config file — **no code change**.
- Keep a **screen → analyze gate**: the cheap screen runs by default; the slow snapshot is opt-in.
- Reuse existing cores (`enumerate_universe`, `build_opportunity_row`,
  `derive_thesis_from_evidence`, `derive_risk_action`, snapshot cache). New logic is limited to
  holdings-overlap scoring, the narrative config, and the risk level.

## 2. Non-goals

- **Not** adding narratives to the fixed `Theme` `Literal` or the `discover → … → opportunity`
  role taxonomy (rejected Approach C — too invasive to H3 / SAME-3 / citation invariants).
- **Not** screening the whole CN fund market; the screen runs over the curated universe
  (`config/universe/cn_funds.generated.yaml`), expandable later via `universe build-cn-funds`.
- **Not** regenerating the basket per run from an LLM/web search (rejected — breaks determinism).
- **Not** changing `eval-funds`, `discover`, `score`, `opportunity`, or any existing output.
- **Not** producing the portfolio-level memo/decision (those stay separate; this is per-fund).

## 3. Architecture

### 3.1 Command — `irc narrative <name>` (new top-level `@main.command`)

Added as a sibling top-level command in `src/irc/cli.py`, lazy-importing `run_narrative` from
`irc.commands.narrative_cmd`, matching the existing command pattern.

```
irc narrative <name> [--screen-only | --analyze]
                     [--top-n 15] [--min-overlap PCT] [--quarter 2026Q1]
                     [--out PATH] [--db PATH] [--repo-root .]
```

- `<name>` — narrative id; resolves to `config/narratives/<name>.yaml`.
- `--screen-only` — stop after the light screen; print + write the ranked shortlist
  (network = top-10 holdings fetches only). **This is also the default** when neither flag is
  given (cheap by default; the slow path is opt-in, mirroring `irc opportunity` /
  `fundamentals snapshot`).
- `--analyze` — run the screen, then deep-analyse the shortlist (the slow snapshot runs here,
  on the shortlist only).
- `--top-n` — max shortlist size after thresholding (default 15).
- `--min-overlap PCT` — min basket-weight % to qualify. Default `None` → use the config's
  `thresholds.min_basket_weight_pct`; when given, the CLI value overrides the config.
- `--quarter` — snapshot quarter for the analyze phase (default: latest cached on disk).
- `--out` — output dir/stem (default `outputs/<today>/narrative/<name>_*`).
- `--db`, `--repo-root` — as elsewhere.

### 3.2 New package — `src/irc/narrative/` (each file < 200 lines)

| File | Purpose | Purity |
|---|---|---|
| `schemas.py` | `NarrativeBasket`, `BasketStock`, `Holding`, `OverlapResult`, `ShortlistRow`, `NarrativeFundReport`, `RiskLevel` | frozen types |
| `screen.py` | `score_overlap(holdings, basket) -> OverlapResult`; `rank_shortlist(matches, thresholds, top_n) -> tuple[ShortlistRow, ...]` | **pure** |
| `risk.py` | `derive_position_risk_level(eval_row, overlap, metrics) -> (RiskLevel, rationale)` | **pure** |
| `report.py` | `render_shortlist_{md,json}`, `render_report_{md,json}` | **pure** |
| `holdings_fetch.py` | `fetch_top_holdings(fund_id, *, cache_dir) -> tuple[Holding, ...]` (AkShare, cached) | I/O edge |
| `config.py` | load + validate `config/narratives/*.yaml` → `NarrativeBasket` | I/O edge |

Orchestration lives in `src/irc/commands/narrative_cmd.py` (thin: load → screen →
(snapshot → eval) → render → write).

### 3.3 Narrative config — `config/narratives/<name>.yaml`

Curated, frozen, citable domain data (no secrets; mirrors the universe-config pattern).

```yaml
narrative_id: compute_metals
display_name_cn: 算力金属
display_name_en: Compute-demand metals
thesis_cn: AI 数据中心建设拉动铜/铝/锡等工业金属与 PCB 用金需求
basket:                                   # the stocks that DEFINE the narrative
  - { symbol: "601899", name_cn: 紫金矿业,  metal: copper_gold }
  - { symbol: "603993", name_cn: 洛阳钼业,  metal: copper_cobalt }
  - { symbol: "600362", name_cn: 江西铜业,  metal: copper }
  - { symbol: "000630", name_cn: 铜陵有色,  metal: copper }
  # … seeded as a draft, user-approved, then frozen
industries_sw: [有色金属/工业金属, 有色金属/贵金属]   # coarser fallback credit
thresholds:
  min_basket_weight_pct: 15.0             # ≥15% of top-10 sits in the basket …
  min_overlap_count: 2                    # … OR ≥2 distinct basket names appear
```

### 3.4 Data flow

```
config/narratives/compute_metals.yaml ──load──▶ NarrativeBasket
        │
[SCREEN] enumerate curated universe (cn_funds.generated.yaml)
        │   per fund: fetch_top_holdings()          ← light AkShare, cached
        ▼   score_overlap() → rank_shortlist(top-N, min-overlap)
   outputs/<date>/narrative/<name>_shortlist.{md,json}            ◀── REVIEW GATE
   outputs/<date>/narrative/<name>_screen_diagnostics.json        (excluded + reason)
        │   (--analyze)
[ANALYZE] per shortlisted fund:
        │   ensure fundamentals snapshot (heavy fetch if missing/stale)
        │   build_opportunity_row()                 ← REUSED, untouched
        │   derive_position_risk_level()            ← NEW
        ▼   render per-fund card + narrative roll-up
   outputs/<date>/narrative/<name>_report.{md,json}
```

### 3.5 Screen matching

`score_overlap` matches a fund's disclosed top-10 against the basket by **symbol first,
`name_cn` second**, sums in-basket weight %, counts distinct hits, and credits holdings whose
SW industry ∈ `industries_sw`. `rank_shortlist` keeps funds meeting **either** threshold
(`min_basket_weight_pct` OR `min_overlap_count`), sorts by basket-weight desc → overlap-count
desc → `instrument_id` (stable), truncates to `top_n`. Funds with **no published holdings** are
**not silently dropped** — they go to `<name>_screen_diagnostics.json` with the reason
(repo "no silent caps" rule).

### 3.6 The new `position_risk_level` (pure)

`risk_action` (exit/trim/review) targets *held* positions; the invest decision needs a
*prospective* level. `derive_position_risk_level` is a pure function of the eval row + overlap +
discovery metrics, producing a level + a rationale naming the **dominant drivers**:

| Driver | Raises risk when… |
|---|---|
| `valuation_state` | expensive / very_expensive |
| `heat_state` | crowded / overheated |
| `thesis_state` | under_pressure / falsified |
| `product_quality_state` | weak / poor |
| holdings concentration | top-1 / top-3 weight very high (single-name fragility) |
| narrative concentration | overlap is one thin slice (e.g. a single metal) |
| drawdown_3y / volatility | from discovery metrics, when available |
| `evidence_gaps` | non-empty → `insufficient` (never fabricate a level) |

Example output: *"elevated — very_expensive valuation + overheated heat; 38% in top holding"*,
each driver backed by the same `[ref:…]` citations the opportunity eval already emits.

## 4. Error handling & determinism

- **Missing/invalid narrative config** → fail fast, message lists available narratives.
- **Fund has no published holdings** (screen) → excluded + logged to diagnostics; never silent.
- **Snapshot fetch fails / never disclosed** (analyze) → row `evidence_insufficient`,
  `evidence_gaps` populated, `position_risk_level = insufficient`, surfaced not crashed.
  `FetchBudgetExceeded` honoured as the existing fatal sentinel.
- **`--analyze` with no prior shortlist** → runs the screen first in the same invocation;
  the gate is `--screen-only` (stops early), so there is no orphan-state error.
- **Determinism** → stable sort (basket-weight → overlap-count → `instrument_id`); citation IDs
  keep the locked 16-hex `[ref:...]` format; no wall-clock/random in cores (timestamps injected
  at the edge) → same inputs produce byte-identical outputs.

## 5. Testing (TDD, red → green → refactor)

- **Pure unit (no mocks):** `score_overlap` (symbol vs name match, weight sum, industry credit),
  `rank_shortlist` (threshold cutoff, stable order, top-N truncation),
  `derive_position_risk_level` (each driver, `insufficient` on gaps), renderers (md/json shape,
  citation regex).
- **Config:** narrative YAML → `NarrativeBasket` parses; malformed config rejected clearly.
- **Integration (no network):** fixture universe + fixture holdings → expected shortlist;
  fixture snapshots → expected report (asserts states, risk level, citations present).
- **I/O edge:** `fetch_top_holdings` double-gated by `pytest.mark.live_akshare` +
  `IRC_RUN_LIVE_AKSHARE=1`.
- **Acceptance (greps):** forbidden `基金概况` indicator stays absent; `\[ref:[0-9a-f]{16}\]`
  holds; determinism (run twice, diff empty).

## 6. Module/file budget

All new files < 200 lines, functions < 20 lines (extract helpers). Pure cores
(`screen`, `risk`, `report`) are unit-testable without mocks; I/O (`holdings_fetch`, `config`,
`narrative_cmd`) is confined to thin edges. Tests mirror `src/irc/narrative/` 1:1 under
`tests/narrative/`.

## 7. Seeding the first narrative

`compute_metals` basket is seeded as a draft (copper/aluminium/tin + PCB-gold names tied to
AI-datacenter demand) for user approval, then frozen. `ai` and `robots` configs are added in
follow-up work using the same schema — no code change required.
