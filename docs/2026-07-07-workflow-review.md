# Workflow Review — 2026-07-07

Full-repo review of the active workflows (monitor + rotation focus), commissioned 2026-07-07.
Method: 4 parallel read-only audit passes (doc drift / monitor logic / rotation logic /
EastMoney dependency + artifact evidence), findings verified against code and on-disk
artifacts. Every claim cites `file:line` or a real artifact path.

**TL;DR**

1. **State correction first**: F8 is partially superseded. `IRC_CN_PROXY` was removed from
   `.env` on 2026-07-06; direct egress worked that day — the rotation **seed completed**
   (200 boards × 60 rows), the forward ledger started (52 rows), and monitor board-PE
   recovered (69/70). 07-07 the board plane failed again → the regime is now
   **"flaky direct at day granularity"**, not hard-blocked. TODOS.md F8/seed entries and
   the session memory are stale on this.
2. **P0 in rotation**: the L2 candidates join is dead code — the stock→board map stores
   行业 *names*, the join filters on BK *codes* → `candidates` is **always empty**, even on
   the successful 07-06 run (21 emerging/hot boards, warm 446-fund holdings cache, 0
   candidates). Offline replay with a name→code translation yields **96 candidate rows**.
   The rotation workflow's entire discovery purpose currently cannot produce output.
3. **P0-class in monitor**: the flow factor's documented freshness contract
   (FRESH / STALE-N / DARK) was **never implemented** — stale flow rows serve indefinitely,
   labeled "fresh" (one symbol is ~7 trading days stale in today's store, untagged), and
   `factor_freshness` in the report is a hardcoded `"fresh"` constant.
4. **Silent weekly casualty**: DXY macro series is stale since **2026-06-16** (push2his via
   `IRC_HTTPS_PROXY` is blocked); the 07-04 gold regime published a 3-week-old DXY without
   listing it in `drivers_unavailable`.
5. Doc drift: 16 verified items (3 HIGH), plus 2 issues in the uncommitted README edit.

---

## 0. State corrections (read before acting on TODOS.md / memory)

| Stale claim | Where | Reality (verified 2026-07-07) |
|---|---|---|
| "Seed never run, `data/rotation/` absent" | TODOS.md:17-18, session memory | Seed ran 2026-07-06: `data/rotation/board_series.json` = 200 boards × 60 rows (2026-04-08→07-06), all rows carry `turnover_pct` (post-F7). Ledger: 52 rows dated 07-06. |
| "F8 hard-blocked; only CN egress fixes it" | TODOS.md:14,18, FACTS.md:10-19 | `.env` edited 07-06 10:00 removing `IRC_CN_PROXY`. Direct egress: full success 07-06 (clist pn=1/2 → HTTP 200, push2his backfill complete), failed again 07-07 (`RemoteDisconnected`). Intermittent, not dead. |
| "F7 unbuilt, blocked by F8" | TODOS.md:16, `src/irc/rotation/README.md:187-189`, CONTEXT.md:290-295 | F7 merged 2026-07-05 (`4d5af11d`): `board_fetch.py:87,136` parses f61 turnover. |
| "Monitor board-PE dark since 06-30" | TODOS.md:18 | Recovered 07-06 (`data/monitor/industry_pe/2026-07-06.json`, 10.5 KB). 07-07 12:15 fetch failed → serving 07-06 as `STALE age_td=1` (within the ≤3-td policy). |

---

## 1. Document drift (Q1)

### 1.1 HIGH — wrong information an operator/model would act on

| # | Doc (location) | Ground truth | Mismatch |
|---|---|---|---|
| D1 | CLAUDE.md:72-77, :36-40 | `src/irc/commands/run_cmd.py:17-20` | Stage diagram shows `…plan → memo` with opportunity/decision "run separately"; actual `STAGE_NAMES` is a 10-stage default run with **opportunity before memo**, decision last. CLAUDE.md:116 contradicts its own diagram. |
| D2 | CLAUDE.md (whole file) | `src/irc/cli.py:279-294`, `src/irc/rotation/` | `irc rotation` / `irc rotation seed` — a daily scheduled vertical with its own package, README, ADR 0023 — is **entirely absent** from CLAUDE.md. Arch package list (:81) also omits `monitor` and `rotation`; `monitor flow-capture` and `fundamentals stock-valuation` undocumented there too. |
| D3 | TODOS.md:14-17 | commit `4d5af11d` | F7 marked unbuilt/blocked; it merged to main 07-05. "Run seed after F7 lands" is moot (both done). |
| D4 | docs/monitor/README.md:44,62,235 | `src/irc/monitor/flow_batch_fetch.py:3-16,63` | Ops manual says the batch carries `f127` for 行业; code requests/parses **`f100`** (the f127-on-ulist.np bug fixed 07-04). This is the exact interface-specific-field-code trap FACTS.md warns about, sitting in the doc an operator debugs from. |

### 1.2 MED — inconsistent numbers/terms across docs

| # | Doc | Truth | Item |
|---|---|---|---|
| D5 | README.md:224 "schema 6" | `src/irc/monitor/eval/trace.py:18` = "7" | eval_trace schema version |
| D6 | README.md:444, evals/README.md:77 "7 funds" | `config/monitor.yaml:21-30` = 10 | Monitor set size |
| D7 | docs/monitor/README.md:141-142, monitor-workflow.html:431 "engine-3 blocks mature" | `monitor_cmd.py:87` `_ENGINE_VERSION="4"` | Stale engine ref (both files elsewhere say 4 — internally inconsistent) |
| D8 | README.md:200, monitor-workflow.html:78,438 "Report v3" | v4 shipped 07-03/04 (schema 7) | Stale report-version label |
| D9 | CONTEXT.md:323-325 | ops/launchd/README.md:8-16 + plists | Describes the retired 17:30-daily schedule; current agents are 12:15/15:45/quarterly/Sat-09:00 |
| D10 | README.md:248 | `ops/launchd/run-flow-capture.sh` | flow-capture row omits the chained `irc rotation` run |
| D11 | evals/README.md:187-188 "three MetricReport rows" | `evals/monitor_forward/runner.py:163-169` | Omits the FU1 `engine_population` diagnostic row (CONTEXT.md:64 is correct) |
| D12 | evals/README.md:146-148,310 "six pure scorers" | CONTEXT.md:55 + code | Seven with `flow` |
| D13 | CONTEXT.md:43 "four pure functions" | `metrics_narrative.py` has six | Narrative metrics count (evals/README is correct); also :41 "five categories" vs six on disk |
| D14 | CLAUDE.md:47, README.md:391 | `monitor_cmd._write_outputs` | Monitor output list omits `monitor.json` — **the** completion sentinel (LOW, but sentinel-adjacent) |
| D15 | README.md:389-409 | `rotation_cmd.py:47-60,158` | No rotation row in the output-inspection cheatsheet (LOW) |

### 1.3 Uncommitted working-tree changes

- **CLAUDE.md** (+7 lines, "Read FACTS.md first"): good, no drift — but `FACTS.md` is
  **untracked**; commit them together or the link dangles on other checkouts.
- **README.md** (+CN-proxy section): mostly a genuine drift *fix* (env vars verified against
  `http_proxy.py:38-47`). Two problems:
  1. **"~200 boards"** vs "~86" everywhere else (CONTEXT.md:267, rotation README:132). Note:
     neither number is verified — the store holds *exactly 200*, which is the pagination
     **cap** (`board_fetch.py:22-23`), so the real universe may be >200 (see R-3 below).
     Reconcile after a one-call `data.total` check; until then say "~200 (cap; exact count
     unverified)".
  2. Says the monitor flow leg "works direct" implying it isn't proxied — but
     `flow_batch_fetch.py:83-84` routes it through `resolve_cn_proxy()` **when set**,
     matching docs/monitor/README.md:244. "Doesn't need the proxy" ≠ "isn't routed through
     it"; align the wording.

### 1.4 Readability / reference-ability

- **No single doc index.** Root README "Design references" and CLAUDE.md "References" are
  two partial, disagreeing indexes; neither lists all five manuals (root README,
  docs/monitor/README, rotation README, evals/README, ops/launchd/README).
- **Duplication hotspots where the drift actually happened** (≥3 copies each): launchd
  schedule table, monitor-set size, schema/engine/report version numbers, MINIMAX
  non-reasoning warning (5 copies), `IRC_CN_PROXY` semantics (now 5 copies, diverging).
- **Diagrams**: `monitor-workflow.html` is well-linked but carries stale "report v3" labels
  and no 15:45 rotation chain. `overall-workflow.html` is actually the 2026-05-21
  thesis-cards diagram — zero mentions of monitor or rotation — and is linked from
  CLAUDE.md as "the end-to-end pipeline diagram including post-stages". Misleading.
- **Recommendations** (one S-effort docs pass):
  1. Fix the countable numbers in one commit: D3-D8, D11-D13, plus F7 status flips in
     TODOS/rotation-README/CONTEXT.
  2. Declare a single owner per topic: launchd table lives only in ops/launchd/README;
     factor/version numbers only in docs/monitor/README (or "see code constant") — all
     other docs link instead of copying.
  3. Add a "Doc map" block (root README + CLAUDE.md) listing the five manuals + diagrams.
  4. Rewrite CLAUDE.md Commands/Stage-flow from `STAGE_NAMES` and add the two daily
     verticals; refresh monitor-workflow.html labels; retire or regenerate
     overall-workflow.html.
  5. Enforcement idea: a tiny test that greps doc version strings against
     `SCHEMA_VERSION`/`_ENGINE_VERSION`/`radar_version` constants, so version drift fails CI
     instead of accumulating.

---

## 2. Logic / implementation flaws (Q2)

### 2.1 Rotation (`src/irc/rotation/`)

| # | Sev | Finding |
|---|---|---|
| R-1 | **P0** | **Candidates join is dead: names vs codes.** `seed.py:73-99` stores f100 行业 **names** in the map; `_cmd_helpers.py:101-105` feeds them to `build_exposure` as `board_code`; `candidates.py:28-33` filters `r.board_code in active` keyed by **BK codes**. Zero matches, always. 07-06's real `ok` run: 21 active boards, 446-fund holdings cache, `candidates: 0`. Offline replay with name→code translation → **96 rows** (BK1036 58, BK0465 19, BK0727 15…). Tests mask it: fixtures put `"BK1"` in the industry slot (`tests/rotation/test_seed.py:88`). Also `build_exposure`'s `board_names` param is never used (`exposure.py:17-49`) and `industry_map_store.py:16-18`'s docstring claims codes are stored (false). **Fix (S)**: translate name→code in `resolve_candidates` from `BoardState` (which carries both), + one integration test through the real seed-written shape. |
| R-2 | P1 | **Flow warm-up gate defeated.** `composite.py:23-26` `_tail_mean` drops Nones → after ONE snapshot day, `flow5` = that day's single value for all 200 boards; `flow_leg_dark` never fires. 07-06 report: 1 snapshot day, `dark_legs: []`, `data_status: "ok"` — a 1-sample "5-day mean" carrying 30% weight labeled ok, contradicting composite.py:74-76 / rotation_cmd.py:174-178 / README:100,107. Also creates a weighting seam inside the hysteresis series (`rotation_cmd.py:74-85`) — some of the 52 ledger state rows are seam artifacts. Fix: require ≥k non-None samples (k=3–5) or a `degraded_flow_warmup` marker; decide `radar_version` bump. |
| R-3 | P1 | **Universe truncation at exactly the 200 cap.** `board_fetch.py:22-23,109-126`: `_PZ=100`, `_MAX_PAGES=2`, `data.total` never read, no `fid` sort key → if the universe is >200, silent truncation with daily churn of *which* 200 appear. Store holds exactly 200 (the cap). Verify `data.total` on the next good egress day; page to exhaustion + pin `fid`. |
| R-4 | P1 | **Stale-map heal gap.** Seed skip-set = all existing keys regardless of age (`seed.py:87-88`), daily join uses `fresh_slice` ≤30 days (`_cmd_helpers.py:101`, `industry_map_store.py:31,86-90`). Only the ~60 monitor symbols get refreshed daily → by ~2026-08-05 the other ~640 mappings expire, exposure collapses, and re-seeding skips them forever. Fix (S): skip-set = `fresh_slice(existing, today)`. |
| R-5 | P2 | **Seed is unpaced + breaker-less** against a burst-throttling endpoint (`seed.py:38-53`: up to ~200 back-to-back push2his calls, no sleep/backoff — the documented self-DoS shape), and O(n²) on store I/O (per-board full 2.9 MB rewrite, `series_store.py:79-90`). Spec §8 required "paced with backoff". |
| R-6 | P2 | **Snapshot-absent boards never pruned**; their frozen rows keep flow/turn non-None so dark gates never fire, and row-index (not date-aligned) windows (`composite.py:32-39`) let them pollute percentiles indefinitely (`series_store.py:66-76`). |
| R-7 | P2 | **Today's dark flags rewrite history**: `rotation_cmd.py:180-182,114` force today's `flow_dark`/`turn_dark` onto every historical percentile slice (composite.py:105-108 already self-gates) → one bad leg day can flip `state`/`days_in_state` wholesale; ledger keeps the old rows → incoherent state sequences for F1. |
| R-8 | P2 | `holdings_as_of` always None (`_cmd_helpers.py:81`; `holdings_fetch.py:80` never persists the quarter) → every candidate renders 持仓季度 N/A; `name_cn` is the fund code. Spec's "staleness stated, never hidden" unimplemented. |
| R-9 | P3 | Empty holdings cached permanently (`holdings_fetch.py:90-97` writes `{"holdings": []}`; `seed.py:61-62` skips on file existence) — a transient empty frame zeroes a fund's exposure forever. |
| R-10 | P3 | Weekend/holiday manual run writes weekend-dated ledger rows (`rotation_cmd.py:198`) that the series store prunes as non-trading days — phantom dates F1 must special-case. |
| R-11 | P3 | Minor: same-day abstain stub overwrites a successful report (rotation_cmd.py:162-165); `⚠追高` renders as a stray 7th table cell (report.py:24-27); `IRC_ROTATION_TOPUP_BUDGET` is actually the chunk **size** — lowering the "budget" increases calls (rotation_cmd.py:242-245); ~331 never-mappable HK symbols refetched every seed. |

### 2.2 Monitor (`src/irc/monitor/`)

| # | Sev | Finding |
|---|---|---|
| M-1 | **P0-class** | **Flow freshness contract unimplemented — unbounded serve-while-stale labeled fresh.** CONTEXT.md/ADR 0019 specify FRESH / STALE-N (`滞后 N 个交易日`) / DARK (>3 td). Code has **no age check anywhere on the flow path**: `holding_metrics.py:76-82,193-201`, `flow_series_store.py:39-43`, `monitor_cmd.py:204-214`. `grep 滞后 src/irc/monitor/` → 0 hits. If capture fails K days, every brief computes flow from pre-outage rows at coverage 1.0 / confidence 1.0 / "fresh" for up to ~5 weeks (25-td store window). Live instance today: 1/30 symbols is ~7 td stale, untagged, still "covered". |
| M-2 | P1 | **`factor_freshness` is a hardcoded constant**: `monitor_cmd.py:442` `{c.name: "fresh" ...}` rendered verbatim (`render_factors.py:99-131`). The report's only per-factor freshness surface is a lie by construction (also covers the self-leg valuation series, which has no ingest-age check — same family as TODOS #47). |
| M-3 | P1 | **Board-PE DARK silently disables the False-Cheap clamp**: `_dual_track.py:63-64` (industry N/A → `val_score = self_score`, clamp can never fire); `render_drilldown.py:198` returns `''` for DARK. On day 4+ of a board block, valuation renders at confidence 1.0/"fresh" while being exactly the value-trap-blind score ADR 0020 exists to prevent. No fund-card marker, no confidence discount (ADR 0020's own deferred item). Severity of the "ADR-0020-tolerated" framing in TODOS is understated — the ADR tolerates ≤3 td STALE with a tag, not unbounded DARK without one. |
| M-4 | P1 | **Same-day reruns flip calls AND rewrite forward history.** No pinning of theme_results/impacts (`monitor_cmd.py:1028-1047`, `impacts.py:52-85` — fresh search + LLM each run); ledger is last-write-wins (`forward_log.py:56-64`; **37 duplicate `(run_date, fund_id)` keys already**, 06-30 ran 3×). Today's only ADD (519069, C=0.4342, margin **0.034** over the 0.40 band, with 0.13 of C from LLM-derived factors) would plausibly flip to NEUTRAL on rerun — and the rerun's row replaces the one you acted on in every forward metric. |
| M-5 | P2 | `flow_source: "batch_today"` is a misnomer on every trace (store-only reads mean newest possible row is yesterday's close; `trace.py:154-156`) and asserts freshness the data doesn't have under M-1. No newest-row date in the trace. |
| M-6 | P2 | `low_factor_agreement` sign-conflict trigger has no magnitude floor (`signal.py:60-62`): today 519069 carries the caveat for flow = −0.008 vs five positives → caveat fatigue. |
| M-7 | P2 | One unguarded DuckDB read can kill the whole 10-fund brief: `_process_fund` → `inputs_loader._stock_series_by_code` (`inputs_loader.py:221-241`) unguarded; fund loop has try/finally but no except (`monitor_cmd.py:1099-1113`). A concurrent `irc ingest` write-lock (a documented real event) → zero outputs instead of a degraded card. |
| M-8 | P2 | Board-PE `as_of` records fetch-date, not data-date (`industry_valuation.py:115-117`) — weekend manual runs under-count later staleness. Known accepted design; listed for awareness. |

Cross-checks that came back clean: `FactorInputs` ctor passes all 6 factors
(`monitor_cmd.py:996-1010`) with per-factor wiring tests; forward metrics already exclude
non-ok rows (`evals/monitor_forward/metrics.py:67,198`) so degraded days don't poison
hit-rates (the poisoning vector is M-4's rerun overwrite). Residual: `flow_reconciliation`
/`valuation_reconciliation` PASS when the factor is absent (`structural.py:147-149,214-215`)
— a dark-ctor regression would not trip them.

---

## 3. Reliability enhancements for investment decisions (Q3)

Ranked by (decision-impact ÷ effort). "S/M" = effort.

**Tier 1 — this week, mostly S:**
1. **R-1 candidates join fix** (S) — unlocks the rotation vertical's entire deliverable;
   the data to produce ~96 candidate rows already sits in the store.
2. **M-4 stopgap: first-wins ledger append** per `(run_date, fund_id)` (or a `rerun` flag
   column) (S) — protects forward history from reruns immediately.
3. **M-3: DARK marker on the fund card** ("价值陷阱检测不可用") + coverage-scaled valuation
   confidence (S) — makes degradation visible at the point of decision.
4. **M-7: per-fund exception isolation** (S) — a failed fund degrades one card, not the brief.
5. **R-4 seed skip-set freshness** (S) — prevents silent exposure collapse ~2026-08-05.
6. **Docs sync pass** (§1.4, S).

**Tier 2 — the two structural trust fixes (M):**
7. **M-1: implement the flow freshness contract as documented** — age-gate the store slice
   (newest covered row ≤3 td else `flow_no_data`; per-fund staleness = oldest covered top-5
   member), render `滞后 N 个交易日`. The single largest plausible-but-wrong path in the
   current flaky-EM environment.
8. **M-4 full fix: same-day evidence pinning** — persist theme_results + validated impacts
   under `outputs/<date>/monitor/` on first run; reruns reuse. Makes the daily brief
   deterministic per day and neutralizes macro_tilt band-flipping.
9. **M-2: real `factor_freshness`** — flow = newest covered row date; valuation = board-PE
   state + self-series ingest age; trend = NAV as_of age; heat = fetched-today flag.
10. **R-2 flow warm-up gate + R-3 pagination fix + R-5 paced seed** (S–M each) — makes
    "opportunistic seed/top-up on good egress days" safe and honest.
11. **DXY reroute** (S–M) — `_fetch_dxy_via_akshare` is the only AkShare call routed through
    `IRC_HTTPS_PROXY` (`akshare_client.py:415-434`) and push2his-via-that-proxy is dead
    (stale since 06-16). Options: try direct (1 call/week is below burst-throttle), or a
    non-EM DXY source (stooq/OpenBB). Gold regime consumes this — see §5.

**Tier 3 — later:** R-6/R-7/R-8 (rotation history hygiene, needs a `radar_version`
decision), M-6 magnitude floor, M-5 provenance enum, R-9/R-10/R-11.

---

## 4. What Opus needs to reach ~90% of Fable on this repo (Q4)

Interpretation: guidance/guardrails to encode in the repo so sessions driven by Opus
(cheaper daily driver) perform close to Fable. The core asymmetry: **Fable compensates for
doc drift by reading code; Opus follows docs more literally and under-wires assembly**
(the repo's own M3 lesson: "Opus plan under-wired runner/metrics ASSEMBLY — caught by ship
steps 8+9, not drift"). So the highest-leverage items are doc accuracy and executable
invariants, not more prose:

1. **Fix the HIGH drift first (D1–D4).** CLAUDE.md's wrong stage diagram and missing
   rotation vertical directly mislead any model that trusts it; the f127/f100 error in the
   ops manual is a live trap. This review's §1 list is the work order.
2. **Keep FACTS.md current — it went stale within 2 days.** The F8 "hard-blocked" entry
   (marked TEMPORARY) was already superseded by the 07-06 seed success at review time. Add
   a rule to the FACTS header: any entry describing a *live incident* gets a date and must
   be re-verified before being acted on (the two verification one-liners already in FACTS
   are the right pattern — Opus should run them, not trust the prose).
3. **Convert prose invariants into tests.** Both P0s in this review were prose-only
   contracts: the flow freshness contract existed only in CONTEXT.md/ADR text (M-1), and
   the candidates join was pinned by fixtures that used the wrong data shape (R-1,
   `tests/rotation/test_seed.py:88`). Rule for specs: every "contract" sentence names the
   test that enforces it, and integration fixtures must use **production-shaped** data
   (copy a real store/cache file into the fixture, don't hand-craft it).
4. **Assembly checklists in every plan.** Opus's known failure mode here is wiring, not
   logic. Require an explicit end-to-end assertion per feature: "factor X moves the
   composite from `_process_fund`" / "candidate rows non-empty through the real seed→join
   path". The existing per-factor wiring tests under `tests/commands/` are the model.
5. **Keep the existing scar-tissue rules mechanical, not judgment calls** — they're already
   written down, Opus just needs them surfaced at the right moment (FACTS.md does this):
   per-file pytest (never whole `tests/commands/`), requests-not-curl for EM, unsandboxed
   EM probes only, interface-specific field codes, `monitor.json` as the only sentinel,
   the literal "Calling the Agent tool is FORBIDDEN" line in every worker dispatch,
   test-scope sweep on signature changes (grep callers in tests/, not just the mirror dir).
6. **Version-number greps as CI** (§1.4 item 5) — removes a whole drift class from the
   model's responsibility.
7. **Route by task, not globally.** Opus + this scaffolding is fine for: implementation
   against a locked spec, doc syncs, ops checks, eval runs. Keep Fable (or add an extra
   adversarial-review pass) for: spec design/grilling, cross-module invariant changes
   (renorm/dark-factor semantics), anything touching Policy B / SAME-3 / ledger semantics,
   and post-build "did we wire it" reviews — the categories where this repo's history shows
   single-pass weaker-model output shipping latent P0s.

---

## 5. Strategy assessment: monitor for daily, rotation for discovery (Q5)

**The architecture is right.** Fixed-set daily state (monitor) + breadth discovery
(rotation) + weekly deep pipeline is a clean separation with honest degradation philosophy,
and the deferral discipline (F1 forward validation before F2–F4 surface hooks) is exactly
correct. Two execution gaps currently break the trust chain:

- **Rotation cannot deliver its purpose today** (R-1): zero candidates ever, so "check if
  any new candidates warrant eyes on" has been returning a false negative. After the S-size
  fix, the radar immediately produces ~96 candidate rows from existing data. But note: the
  signal is **unvalidated** (F1 needs 4–6 weeks of ledger, which only accrues on
  EM-reachable days) and R-2's warm-up seam means early `emerging/hot` states are partly
  artifacts. Treat candidates as "eyes on" prompts only — do not size positions off the
  radar until F1 reads out. That was always the plan; it still holds.
- **Monitor is decision-grade for trend-dominated calls, not band-adjacent ones.** Today's
  only ADD (519069) sits 0.034 over the 0.40 band with ~0.13 of composite from
  LLM-nondeterministic factors (macro_tilt ±0.3–0.5 rerun swing) — a coin-flip
  recommendation presented with full confidence. Until Tier-2 fixes land, adopt a free
  operator rule: **act on ADD/REDUCE only when |C − band| ≥ ~0.10, or when the same call
  repeats two consecutive days.** Gold/QDII funds are macro_tilt-dominated (35–41% of live
  weight) — treat their band crossings with extra suspicion.
- **Gold view is the weakest link right now**: macro_tilt is its largest factor AND the
  weekly gold regime consumed a DXY value stale since 06-16 without flagging it
  (`outputs/2026-07-04/gold_regime.json` lists only `etf_holdings_gld` in
  `drivers_unavailable`). Fix the DXY route (Tier 2 #11) before leaning on the gold signal.

**Verdict**: keep the strategy; fix R-1 + M-4-stopgap this week, M-1/M-4-full next; apply
the band-margin rule immediately at zero cost.

---

## 6. push2.eastmoney.com blocking — impact evaluation (Q6)

### What was actually lost (artifact-verified)

| Signal | Outage window | Evidence |
|---|---|---|
| Monitor industry-valuation leg (board PE) | **≥06-23 → 07-03** (~2 trading weeks), recovered 07-06, STALE-1 today | `eval_trace.json` industry fill 0/70 through 07-03; `industry_pe/2026-06-29.json`, `06-30.json` = `{}`; 69/70 on 07-06/07 |
| Monitor flow factor | 06-30 (7/30), 07-01 (3/30), 07-02 partial-history, 07-03 (0 — ProxyError) | `data/monitor/fund_flow_series.json` per-day coverage |
| **DXY macro series → gold regime** | **06-16 → ongoing** | DuckDB `macro_series` last DXY row 06-16; weekly log 07-04 "skipping macro series DXY"; 07-04 gold_regime published 06-16 DXY, not listed unavailable |
| Rotation daily radar | abstained 07-05, 07-07; ok 07-06 | `outputs/*/rotation/rotation_radar.json` `data_status` |
| Weekly `irc run` | **Unaffected** — 07-04 ran clean end-to-end (memo 40/40 refs); ETF history rode the Sina fallback | `run-weekly.20260704-090004.log` |

**Never affected** (non-push2 EastMoney hosts — `fund.`, `fundf10.`, `datacenter-web.`,
`push2delay`): NAV/trend factor, heat/限购, fundamentals snapshots, per-stock PE/PB
self-history (+ Tushare fallback armed), QDII premium. **The majority of the monitor's
composite ran on unaffected hosts throughout.**

### Current regime (since `.env` dropped the proxy, 07-06)

- **Flow plane (`ulist.np`)**: healthiest surface — worked 07-06 15:45 (29/30) and 07-07
  12:15; direct egress, burst-throttle-sensitive but functioning.
- **Board plane (`clist/get` + `push2his`)**: intermittent at day granularity — full success
  07-06 (seed + radar ok + board PE), refused 07-07. Expect a mix of ok/abstain days.
- **push2his via `IRC_HTTPS_PROXY`**: dead (DXY). Different route from the CN story — needs
  its own fix.

### Cost of leaving it as-is

- The daily abstain path is **cheap and safe**: 1 clist call, ~seconds, exit 0, honest
  abstain stub, no series/ledger mutation, no self-DoS (the risk lives in the unpaced seed,
  R-5). No notification fires, so abstains are invisible unless you open the report —
  acceptable for an advisory chain, but worth one line in the daily notify if you want
  visibility.
- The **real cost is clock time**: F1's forward validation only accrues on EM-reachable
  days, and maturity/forward windows stretch accordingly. A multi-month outage would also
  effectively force a re-seed (60-row `_KEEP_TD` window vs a new anchor date).
- Under a resumed *full* block (the 06-30→07-05 pattern), with M-1/M-2/M-3 unfixed, the
  monitor keeps publishing nominal-confidence composites while **~35% of active-fund
  composite weight (flow 0.15 frozen-but-"fresh" + valuation 0.20 trap-blind) is silently
  degraded** — that's the scenario the Tier-2 fixes exist for.

### Recommendation ladder

1. **Stay on direct egress** (proxy off for CN planes) and make the seed/top-up path safe
   for opportunistic use on good days (R-5 pacing) — the 07-06 success shows good days come.
2. **Fix the DXY route now** (small, decoupled, and it's silently corrupting the gold view).
3. **Land M-1/M-2/M-3** so any future block degrades *visibly* instead of silently.
4. If board-plane success rate stays <~50% of trading days over the next 2–3 weeks, buy a
   CN-residential/EM-allowed egress — it fixes snapshot + history + board-PE + flow in one
   move with zero code. (Track it simply: count `data_status: ok` days.)
5. **Source-swap (THS/Tushare) is last resort** — every candidate loses the flow and/or PE
   legs and a taxonomy switch restarts the accumulation clock per ADR 0023 D1. Not worth it
   while direct egress works intermittently.

---

## Suggested immediate action list

1. Fix R-1 (candidates join) + integration test with production-shaped map data. [S]
2. First-wins forward-ledger append (M-4 stopgap). [S]
3. DARK fund-card marker + valuation confidence discount (M-3). [S]
4. R-4 seed skip-set freshness. [S]
5. Docs sync pass (§1.4) incl. TODOS/FACTS state corrections and the two uncommitted-README
   fixes; commit FACTS.md together with the CLAUDE.md pointer hunk. [S]
6. DXY reroute. [S–M]
7. Then: M-1 flow freshness contract, M-4 evidence pinning, M-2 real factor_freshness. [M]
