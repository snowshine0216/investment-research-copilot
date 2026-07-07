# Monitor operations manual — daily brief + weekly research loop

This is the operations manual for the **monitor vertical** (`irc monitor`) and the
cadenced processes around it. The main [README](../../README.md) covers install and
the full pipeline; this file is what you read to *run the monitoring practice*:
what fires automatically every day, what you do weekly, how to read the brief, and
what to do when something pages.

Design references: ADR 0017 (evidence isolation), 0018 (profiles/weights), 0019
(flow factor + CN egress), 0020 (dual-track valuation), 0021 (report v2 market
composite), 0022 (source tiers) under [`docs/adr/`](../adr/), the
[workflow diagram](../diagrams/monitor-workflow.html), and the eval companion
[`evals/README.md`](../../evals/README.md).

## The two loops

The system runs two deliberately separate loops:

| Loop | Cadence | Question it answers | Universe | Command |
|---|---|---|---|---|
| **Monitor** (this manual) | Daily, automated | "For the funds I already track, which way is the evidence leaning today?" | Fixed 10-fund **Monitor set** in `config/monitor.yaml` | `irc monitor` |
| **Research pipeline** | Weekly, automated (Sat 09:00) | "What should I actually buy/hold/trim, and did anything new become attractive?" | Full configured universe (~500 candidates → discovery → scoring → opportunity states) | `irc run` |

The monitor is **self-contained** (own NAV fetch, own evidence pool, own caches —
ADR 0017); it does not need the weekly pipeline to run. The weekly pipeline is the
only place *new* funds are screened and the only layer that produces buy/trim/exit
decisions (`decision_status`, `今日唯一行动`). The monitor produces **directional
biases** (研究参考信号, not orders) on funds you already care about.

**The Monitor set** (source of truth: `config/monitor.yaml`): 7 `active_cn_equity`
funds + 1 gold (008986) + 1 `qdii_global` (270023) + 1 `qdii_china_us_internet`
(009225). Adding/removing a fund is a manual config edit — see
[Promoting a fund into the Monitor set](#promoting-a-fund-into-the-monitor-set).

## Daily process (automated)

Four launchd agents (installed via `bash ops/launchd/install.sh`) run the
pipeline unattended; the weekly one is covered in
[Weekly process](#weekly-process). **The authoritative schedule** (exact
times, gates, locks, watchdogs, notify semantics) **lives only in
[`ops/launchd/README.md`](../../ops/launchd/README.md)** — the table below is
a cadence summary, not a second source of truth.

| Time (Asia/Shanghai) | Agent | Purpose |
|---|---|---|
| 12:15 daily | `com.irc.monitor` | Daily brief (`irc monitor`) + notify. No same-day retry on failure — re-run `uv run irc monitor` by hand. |
| 15:45 daily | `com.irc.flow-capture` | Capital-flow capture → chained `irc rotation`; see [What the 15:45 run does](#what-the-1545-flow-capture-run-does) below. |
| 08:00 on Jan/Apr/Jul/Oct 1st | `com.irc.fundamentals-quarterly` | Refreshes the typed per-fund constituent caches the valuation/constituent factors read. |

The 12:15 slot is after the CN morning session closes, leaving the 15:00
close ahead for same-day decisions.

### What the 15:45 flow-capture run does

One batched EastMoney `ulist.np` call (full-basket secids, `f184`+`f100`)
appends today's **completed-day** capital-flow row to
`data/monitor/fund_flow_series.json` (top-5-union scope, ~25 trading-day
retention) and merges the `f100` 行业 names into
`data/monitor/stock_industry_map.json`; it then best-effort refreshes the
board-PE day cache in the rested window (so next morning's stale fallback is
at worst 1 day old). **Never run this manually before the 15:00 close** — the
manual path is unguarded. Watchdog/lock/notify semantics (incl. the
data-health notify on rotation abstain/degradation):
[`ops/launchd/README.md`](../../ops/launchd/README.md).

### What one 12:15 run does

Run-level, in order (`src/irc/commands/monitor_cmd.py::run_monitor`):

1. **Spend preflight** — paid-API budget gate; insufficient balance halts with exit 5.
2. Load `config/monitor.yaml` + `config/llm.yaml`; open `data/local.duckdb` if present.
3. **One purchase-table fetch** (heat factor + 限购 tag), **one flow-store slice**
   (completed days, union of active-fund top-5 symbols) + **one provisional
   intraday flow batch** (盘中提示 annotation only — rendered, never persisted).
   - **行业 is batch-first (ADR 0020 addendum 2026-07-03):** the one `ulist.np`
     batch call carries `f100`; names accumulate cross-day in
     `data/monitor/stock_industry_map.json` (serve-while-stale ≤ 30 calendar
     days, refresh-on-seen). The per-symbol `stock/get` path fires only for
     symbols absent from that map (~never in steady state). Board PE is
     fetched ONCE at run level before the per-fund loop; on failure the most
     recent non-empty cached table ≤ 3 trading days old feeds factor math with
     an explicit `板块PE 引用 <date> · N个交易日前` tag (FRESH / STALE-N / DARK —
     see CONTEXT.md *Board-PE freshness state*).
4. **Theme search once per unique theme** (~8 provider calls, not per-fund). The
   **source-tier gate** (ADR 0022) drops blocked domains at ingest; everything else
   is kept and badged (tier 1 权威 / tier 2 财经媒体 / unknown 未分级).
5. **Per-fund loop × 10**: NAV series (min 251 obs) → per-fund evidence pool
   (pure assembly from the shared theme results, citation ids owner-bound) →
   `monitor_impact` LLM scoring (macro rows; plus constituent rows for
   look-through profiles; schema-validated, ≤2 retries) → dual-track valuation +
   per-stock holding metrics → 6 factor scores → coverage-gated signal → bias.
6. **One `monitor_narrative` LLM call** (prompt v3) builds the run-level 宏观面速览
   macro block (≤3 claims/theme, attribution-verb guard, CJK guard, citations
   resolved, plus an optional ≤60-char per-theme 传导 mechanism clause —
   invalid mechanisms are dropped, never truncated, never retried). The old 10
   per-fund narratives are gone.
7. **Eval spine**: in-run health per fund → M1 gate (`monitor_signal` /
   `monitor_impact` / `monitor_narrative` FAIL ⇒ **EVAL-GATED 🛡**, WARN/stale ⇒
   ⚠ caveated), validation panel, inline `monitor_forward` re-score (so the
   predictive panel is same-day fresh), `eval_trace.json` (schema 7),
   `forward_ledger.jsonl` + `nav_history.jsonl` appends.
8. **Render + write** (atomic, fixed order): `report.html` → `signal.json` →
   `impacts.json` → `narrative.json` → `monitor.json` (the completion sentinel),
   plus `drilldown.html` and `eval_trace.json`. Record spend to the ledger.

> **Single owner:** this manual is the canonical source for factor weights and the schema/engine version numbers. Other docs link here or cite the code constant (`trace.SCHEMA_VERSION` / `monitor_cmd._ENGINE_VERSION`); the version-grep guard `tests/docs/test_version_sync.py` enforces agreement.

### Factors and signal (engine 4)

Weights live in `src/irc/monitor/profiles.py` (per profile; optional per-fund
`signal_weights` override in `config/monitor.yaml`):

| Profile | trend | valuation | flow | heat | macro_tilt | constituent |
|---|---|---|---|---|---|---|
| `gold` | 0.45 | — | — | 0.20 | 0.35 | — |
| `qdii_global` | 0.35 | — | — | 0.15 | 0.35 | 0.15 |
| `qdii_china_us_internet` | 0.30 | 0.20 | — | 0.15 | 0.20 | 0.15 |
| `active_cn_equity` | 0.25 | 0.20 | 0.15 | 0.10 | 0.15 | 0.15 |

- **trend** — accumulated-NAV momentum (deterministic).
- **valuation** — bottom-up dual-track per stock: `0.60·self-history + 0.40·industry-relative`,
  with the **False-Cheap clamp** (cheap vs. own history but PE ≥ 1.2× industry ⇒ score 0),
  aggregated over the full disclosed basket, ≥ 0.40 NAV coverage floor (ADR 0020).
- **flow** — 主力净流入净占比, `0.4·5d + 0.6·20d` blend over top-5 holdings, ≥ 0.50
  coverage floor; reads the completed-day store the 15:45 job maintains (ADR 0019).
- **heat** — purchase-restriction status + AUM delta.
- **macro_tilt / constituent** — LLM-scored news impact rows (theme-level / per-holding).
- A factor that can't be filled ships **N/A + a reason code** — never a silent zero.

Signal: renormalized weighted composite → `ADD_BIAS` above +0.40, `REDUCE_BIAS`
below −0.40, else `NEUTRAL`; coverage gate requires trend + ≥ 2 factor families +
Σweight ≥ 0.60, and confidence ≥ 0.50 — otherwise `NO_CALL`
(insufficient/low-confidence). The report additionally shows the **market
composite** (市场面综合分, ADR 0021): the same composite with the two news factors
excluded — the stable, fact-backed anchor — with the news contribution displayed
as a labeled overlay delta. The full composite stays the canonical
published/forward-tracked signal.

### Reading the report (30-second daily check)

Open `outputs/<date>/monitor/report.html`:

1. **今日速览** (top strip): 偏向变化 (bias flips vs. the prior run), 可操作
   (actionable, gate-respecting), 数据健康 (dark-factor fractions, gated count,
   stale evals). All-quiet renders one muted line.
2. **Summary table**: per fund — bias badge (or **EVAL-GATED 🛡** / `NO_CALL`),
   ✓ validated / ⚠ caveated chip, composite vs. market composite.
3. If a bias moved: the fund card explains it — market-composite decision line,
   contribution bars (market vs. 新闻面 marked), factor table with N/A reasons,
   NAV chart with evidence markers, 宏观面速览 direction chips (signed per-theme
   impact, 绿 ≥ +0.15 · 红 ≤ −0.15 · 灰其间; 无数值 = 当日无记录) with claim
   strength tags (可能主因/方向一致/已证实归因/归因未知) and a per-theme
   对本组基金的传导 line, and the per-stock drill-down (PE/PB + industry leg +
   value-trap badge + flow) for active funds.
4. **Validation panel** + **predictive panel**: informational stages render 观测
   (never PASS); suite ages go amber at ≥ 10 days, UNKNOWN at ≥ 14; the forward
   panel says `insufficient_data` honestly until engine-4 blocks mature — the only
   accrued track record it cites is trend-only (~0.54 hit rate).

Treat a bias as **research lean, not an order** — anything actionable goes through
the weekly loop's decision layer before money moves.

### Notifications

`irc notify-status` (macOS always; Feishu when `IRC_FEISHU_WEBHOOK_URL` is set)
pages on `failed` / `halted` / `stale` / `action` / timeout; clean runs emit a
quiet notification by default (`IRC_NOTIFY_ON_CLEAN=0` to silence). A *missing*
12:15 notification means the schedule itself broke — check
`launchctl print gui/$(id -u)/com.irc.monitor` and `outputs/_logs/run-monitor.*.log`.

## Weekly process

The weekly loop is automated by the **`com.irc.weekly` launchd agent (Saturday
09:00 Asia/Shanghai)**: full `irc run` under a single-instance lock + 2h
watchdog, completion keyed on `decision_report.json`, then
`irc notify-status --run-kind weekly`. Install/refresh agents with
`bash ops/launchd/install.sh`; the wrapper does not force `RESEARCH_ENABLED` —
set it in `.env` for research-backed weekly runs.

After `notify-status`, the wrapper best-effort refreshes the two live LLM eval
suites (`env IRC_RUN_LIVE_LLM_EVAL=1 … irc eval monitor_impact` /
`monitor_narrative`, each under its own `IRC_WEEKLY_EVAL_TIMEOUT` watchdog,
default 900 s) so the daily brief's suite healths stay fresh under
`STALE_AFTER_DAYS = 14`. Eval failures/timeouts are logged breadcrumbs — they
never change the weekly exit code and never page. Edge case: a same-day manual
`irc run` (idempotency-sentinel skip) also skips that Saturday's eval refresh —
the daily report degrades to the stale caveat chip + validation-panel hint;
run the manual command from the maintenance table below to clear it.

**Promotion notification is built in**: the decision stage diffs today's
`opportunity_report.json` against the most recent prior run's; any fund newly
reaching `core_dca` (or `dca_action` → `accelerate_dca`) lands in the
decision report's 新晋关注 section, in `summary.promotion_count` /
`promotion_ids`, and pages as an **action** notification with the fund ids —
you no longer have to diff the reports by hand.

Your weekly read, after the Saturday page (or a manual run):

```bash
open outputs/$(date +%F)/memo.md            # 今日唯一行动 banner + consolidated picks
cat outputs/$(date +%F)/decision_report.md  # verdicts + 新晋关注 promotions section
uv run irc eval monitor_forward             # forward-validity read on the monitor signal

# If the pipeline halted, fix the named stage then resume (same day):
uv run irc run --resume
```

Screening transparency lives in the run artifacts: `discovered_watchlist.csv`
(passed), `discovery_rejections.csv` (every excluded instrument + reason),
`discovery_diagnostics.csv` (stage funnel counts), and
`opportunity_report.json` (`opportunity_state` + `evidence_gaps` /
`advisory_gaps` per row).

## Promoting a fund into the Monitor set

The weekly run now *notifies* you when a fund turns promising (新晋关注), but
entry into the daily Monitor set stays a deliberate manual edit:

1. **Find it** in the weekly artifacts (new `core_dca` / high scorer), or via
   `uv run irc narrative <name>` (thematic holdings look-through screen), or check
   a specific candidate with `uv run irc eval-funds --ids "<id>"`.
2. **Add it** to `config/monitor.yaml` (`funds:` — id, name, `analysis_profile`,
   themes) and run `uv run irc config validate`.
3. **Warm its caches**: `uv run irc monitor snapshot` (constituent snapshot for the
   new fund; otherwise valuation/constituent stay N/A until the quarterly job).
4. Next 12:15 brief covers it. Expect `NO_CALL` until 251 NAV observations exist
   and warm-up N/A on flow until the store accumulates its symbols.

## Monthly / quarterly maintenance

| Cadence | Task | Command |
|---|---|---|
| Monthly | Rebuild the generated CN fund universe (feeds weekly discovery) | `uv run irc universe build-cn-funds && uv run irc config validate` |
| Weekly, automated (Saturday wrapper, best-effort) | Live LLM eval suites — the only check on MiniMax output *quality*; without a fresh report the daily gate fails open to ⚠ caveated (the chip tooltip + 今日速览 line now name the stale suite and its age). `run-weekly.sh` refreshes both suites after notify (900 s watchdog each via `IRC_WEEKLY_EVAL_TIMEOUT`; failures never page; eval-live spend gate applies). Manual remediation / fallback — e.g. after a same-day manual run preempted the Saturday fire: | `IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact` (same for `monitor_narrative`) |
| Quarterly (automated) | Monitor constituent snapshots | `uv run irc monitor snapshot` (also run once when onboarding a fund) |
| Quarterly / on holdings roll | Per-stock PE/PB history refresh backing dual-track valuation | `uv run irc fundamentals stock-valuation` (30-day freshness skip makes reruns cheap) |
| Quarterly | Broad-pipeline fundamentals (weekly loop's thesis evidence) | `uv run irc fundamentals snapshot --target all --top-n 10` |
| Yearly | Refresh the CN market holiday list the wrappers grep | `config/cn_market_holidays.yaml` |

## Outputs reference

| Path | What it is |
|---|---|
| `outputs/<date>/monitor/report.html` | The daily brief (self-contained, no JS) |
| `outputs/<date>/monitor/drilldown.html` | Per-stock valuation + flow board per active fund |
| `outputs/<date>/monitor/monitor.json` | Machine summary — **written last; the completion/idempotency sentinel** |
| `outputs/<date>/monitor/signal.json` / `impacts.json` / `narrative.json` | Per-fund signal, LLM impact rows, macro block (`__macro__`) |
| `outputs/<date>/monitor/eval_trace.json` | Eval spine input (schema 7, engine 4) |
| `data/monitor/forward_ledger.jsonl` | Append-only per-fund-per-day rows (incl. `market_composite`/`market_bias`) scored by `monitor_forward` |
| `data/monitor/fund_flow_series.json` | Completed-day flow store (written only by the 15:45 job) |
| `data/monitor/stock_industry_map.json` | Cross-day stock→行业 store (batch-first f100; fallback merges too) |
| `data/monitor/industry_pe/<date>.json` | Board-PE day cache (non-empty parses only; stale-served ≤ 3 td with an age tag) |
| `outputs/_logs/run-*.log` | Per-fire wrapper logs (14-day retention) |

## Environment

| Variable | Purpose |
|---|---|
| `MINIMAX_API_KEY` / `MINIMAX_BASE_URL` / `MINIMAX_MODEL` | Required for `irc monitor`. **`MINIMAX_MODEL` must be a fast non-reasoning chat model** (e.g. `MiniMax-Text-01`); reasoning models overrun call deadlines → `NO_CALL`. |
| `IRC_CN_PROXY` (+ `IRC_CN_PROXY_MODE=on\|off`) | CN-egress proxy for the EastMoney data plane (batch flow, industry PE, per-stock PE/PB). Needed when the host egresses from a non-CN IP (geo-throttled otherwise — ADR 0019). |
| `IRC_HTTPS_PROXY` | Separate: LLM / web-search / Jina / DXY egress. Do not point it at the CN proxy. |
| `IRC_MONITOR_TIMEOUT` / `IRC_FLOW_CAPTURE_TIMEOUT` / `IRC_SNAPSHOT_TIMEOUT` | Wrapper watchdogs (1800 / 300 / 3600 s). |
| `IRC_SKIP_SPEND_GATE=1`, `IRC_SPEND_MARGIN` | Spend-gate bypass / margin override (exit 5 = insufficient balance). |
| `IRC_FEISHU_WEBHOOK_URL`, `IRC_NOTIFY_ON_CLEAN` | Notification channel + clean-run verbosity. |
| `IRC_RUN_LIVE_LLM_EVAL=1` | Unlocks the paid live LLM eval suites (skipped rc 3 otherwise). |
| Weekly loop only: `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `RESEARCH_ENABLED`, search keys | See the main README's environment table. |

## Troubleshooting

| Symptom | Likely cause → fix |
|---|---|
| Funds fall to `NO_CALL`, narratives degrade | `MINIMAX_MODEL` is a reasoning model → switch to a fast chat model |
| 资金流因子 N/A across funds | Store warm-up (< 5d/20d windows), coverage < 0.50, or CN-egress geo-block → check `IRC_CN_PROXY`, wait for the 15:45 job to accumulate |
| **EVAL-GATED 🛡** on a fund | A gating stage FAILed (stale/missing NAV, broken citation, fresh suite FAIL) — read the validation panel reasons; the bias is suppressed on purpose |
| Everything ⚠ caveated | LLM suite reports stale (≥ 14 d) — run the live suites (see maintenance table) |
| Page with `rc=124` | Watchdog killed a hung run (usually an unbounded upstream socket) — re-run manually; check the per-run log |
| Schedule silently dead, `last exit code = 78` | launchd log-file provenance trap — see [`ops/launchd/README.md`](../../ops/launchd/README.md) |
| Weekly `irc run` halted | `outputs/<date>/PIPELINE_HALTED.md` names the stage; fix, then `uv run irc run --resume` (same day) or re-run |
| Run stops with exit 5 | Spend gate: top up / edit `config/spend_balances.yaml` / `IRC_SKIP_SPEND_GATE=1` |
| 行业/行业PE columns dark | Check the panel's `board_pe FRESH/STALE-N/DARK` reason + `stock_industry_map.json` coverage; a DARK board PE ≤ 3 td heals from the 15:45 refresh (P8c) |

## One-time ops (historical, completed)

Kept for the record; do not re-run unless re-bootstrapping.

- **CN-egress light-up day-1 order** (2026-07-02, done): install 15:45 job → post-close
  D7 seed (`irc monitor flow-capture`) → D8 valuation backfill
  (`irc fundamentals stock-valuation --force`) → verify Tier-2 at the next brief
  (flow ≥ 5/7 active funds, `industry_cover > 0` above the 0.40 floor).
- **GATE-2 4dp equivalence** (flow batch `f184` ≈ next-day `daykline.净占比`):
  `scripts/phase0_flow_batch_spike.py --use-cn-proxy` capture, then
  `--equiv-against <capture>` next day. `max|Δ| ≤ 4dp` keeps `_ENGINE_VERSION`
  at "3"; a material gap escalates to an engine bump + ADR 0019 addendum **before**
  flow forward-metrics are trusted.
