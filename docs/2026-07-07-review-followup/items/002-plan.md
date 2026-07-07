# Item 002 — Docs-sync + TODOS reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the 2026-07-07 workflow review's §0 state-corrections and §1 drift table (D1–D15) as mechanical doc edits, register the review's deferred findings in TODOS.md, and add one version-grep guard test that kills the schema/engine/radar drift class permanently.

**Architecture:** Docs-only plus a single pure `tests/docs/` guard test. No `src/` behavior changes. Every edit is verified against the **current** file state (items 004/005/001 merged first and moved several targets); the review's line numbers are stale anchors, not ground truth. The one code artifact (002-d) is written **first** so it lands RED against the un-fixed docs, then the doc fixes turn it GREEN (TDD red→green).

**Tech Stack:** Markdown, HTML (SVG diagrams), Python 3.12 + pytest (one new test file), ruff.

## Global Constraints

- **Stay on branch `autodev/review-followup-feature`.** Do NOT switch branches, do NOT push.
- **Verify current state before every edit.** Read the target region first; 004/005/001 already amended CLAUDE.md (FACTS pointer), README (IRC_CN_PROXY rework), CONTEXT.md:20 (R-1/R-4 corrections), docs/monitor/README, ops/launchd/README, TODOS (diagnostics entry). Do not trust the review's `file:line` — re-locate by content anchor.
- **Code version constants (single source of truth, verified 2026-07-07):**
  - `src/irc/monitor/eval/trace.py:18` → `SCHEMA_VERSION = "7"` (eval_trace schema)
  - `src/irc/commands/monitor_cmd.py:87` → `_ENGINE_VERSION = "4"`
  - `src/irc/rotation/report.py:14` → `SCHEMA_VERSION = 1` (rotation report schema)
  - `src/irc/rotation/report.py:15` → `RADAR_VERSION = 1`
  - `src/irc/commands/run_cmd.py:17-20` → `STAGE_NAMES = ("ingest","research","discover","score","gold","allocate","plan","opportunity","memo","decision")` (10 stages; opportunity BEFORE memo; decision last)
  - `src/irc/monitor/flow_batch_fetch.py:86` → batch requests `fields=f12,f14,f184,f100`; 行业 rides on **f100** (f127 is numeric on `ulist.np`)
- **Bilingual style:** keep each file's existing 中文/English register. TODOS/CONTEXT/rotation-README mix EN prose with 中文 domain terms — match the surrounding lines.
- **Report version (v3→v4) is NOT code-backed** — it is a manual label fix (D8), guarded only by the verification grep in Task 6, not by the 002-d unit test (the test guards only schema/engine/radar which have code constants).
- **Line budget:** doc files have no line budget; the one new test file must stay < 200 lines.

### Already-satisfied sub-targets (verify-only — do NOT re-edit)

- **FACTS.md is already tracked + committed** (607c26cc) and the CLAUDE.md "Read FACTS.md first" pointer is committed — the 002-a "commit FACTS.md together with the pointer hunk" concern is a **no-op**. The only live FACTS.md edit is the **F8 section body** (Task 5).
- **README.md:200** already says "fixed **10-fund**", "Engine **4**", and lists **`monitor.json`** — only "Report v**3**" remains wrong there (D8). Do NOT touch the 10-fund / engine-4 / monitor.json parts of :200.
- **CLAUDE.md:116** already states "Opportunity runs *before* memo (`STAGE_NAMES` …)" — correct; the bug is the **diagram** at :72-78 contradicting it (D1). Leave :116.
- **CONTEXT.md:20** (Stock-industry map bullet) already carries the R-1 name→code + R-4 freshness corrections from items 004/005 — **no-op**.
- No D-item is a full no-op; each needs at least one edit at a re-located anchor.

---

## Task 1: Version-grep guard test (002-d) — write RED first

**Files:**
- Create/Test: `tests/docs/test_version_sync.py`

**Interfaces:**
- Consumes: nothing (pure file reads; no `irc` imports, to stay import-safe).
- Produces: a standalone guard suite. Reads code constants by regex from source files (single source of truth), reads doc strings, asserts they agree and that the known-drift strings are absent.

**Why RED now:** before Tasks 3–5, `README.md:224` says "schema 6" and `docs/monitor/README.md:141` + `docs/diagrams/monitor-workflow.html:431` say "engine-3" — so the schema/engine assertions fail. The doc fixes in later tasks turn it GREEN (Task 6).

- [ ] **Step 1: Write the failing test**

Create `tests/docs/test_version_sync.py` (mirrors the existing `tests/docs/test_readme_spend.py` convention — `Path(__file__).resolve().parents[2]` is repo root):

```python
"""Guard: doc version strings must match the code constants (review §1.4 item 5).

Kills the schema/engine/radar drift class (D5/D7): a version bump in code that
forgets a doc fails CI here instead of rotting. Pure file reads — no `irc`
imports, so it cannot pull the LLM/network layers.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _const(rel: str, name: str) -> str:
    """Extract `NAME = <int>` (optionally quoted) from a source file, MULTILINE-anchored."""
    m = re.search(rf'^{re.escape(name)}\s*=\s*["\']?(\d+)["\']?', _read(rel), re.MULTILINE)
    assert m, f"{name} assignment not found in {rel}"
    return m.group(1)


SCHEMA = _const("src/irc/monitor/eval/trace.py", "SCHEMA_VERSION")       # "7"
ENGINE = _const("src/irc/commands/monitor_cmd.py", "_ENGINE_VERSION")    # "4"
RADAR = _const("src/irc/rotation/report.py", "RADAR_VERSION")           # "1"
ROT_SCHEMA = _const("src/irc/rotation/report.py", "SCHEMA_VERSION")      # "1"


def test_readme_eval_schema_matches_code():
    text = _read("README.md")
    assert f"schema {SCHEMA}" in text, f"README.md must state 'schema {SCHEMA}'"
    assert "schema 6" not in text, "README.md still carries the stale 'schema 6'"


def test_docs_monitor_readme_engine_matches_code():
    text = _read("docs/monitor/README.md")
    assert f"engine {ENGINE}" in text, f"docs/monitor/README.md must state 'engine {ENGINE}'"
    assert "engine-3" not in text and "engine 3" not in text, "stale engine-3 ref"


def test_monitor_workflow_diagram_matches_code():
    text = _read("docs/diagrams/monitor-workflow.html")
    assert f'engine "{ENGINE}"' in text, f'diagram must state engine "{ENGINE}"'
    assert f'schema "{SCHEMA}"' in text, f'diagram must state eval schema "{SCHEMA}"'
    assert "engine-3" not in text and "engine 3" not in text, "diagram stale engine-3"


def test_rotation_report_docstring_matches_constants():
    """Self-consistency: report.py module docstring numbers == the constants."""
    text = _read("src/irc/rotation/report.py")
    assert f"schema_version {ROT_SCHEMA}" in text, "report.py docstring schema_version drift"
    assert f"radar_version {RADAR}" in text, "report.py docstring radar_version drift"
```

- [ ] **Step 2: Run the test to verify it fails RED**

Run: `uv run pytest tests/docs/test_version_sync.py -v`
Expected: `test_readme_eval_schema_matches_code` FAILS ("still carries the stale 'schema 6'") and `test_docs_monitor_readme_engine_matches_code` + `test_monitor_workflow_diagram_matches_code` FAIL ("stale engine-3"). `test_rotation_report_docstring_matches_constants` should PASS (report.py docstring already says `schema_version 1, radar_version 1`). Record this RED output — it proves the guard bites.

- [ ] **Step 3: Commit the RED test**

```bash
git add tests/docs/test_version_sync.py
git commit -m "test(002-d): version-grep guard for schema/engine/radar (RED against un-synced docs)"
```

---

## Task 2: CLAUDE.md cluster (D1, D2, D14, overall-workflow relabel, Doc map)

**Files:**
- Modify: `CLAUDE.md` (Commands block ~:32-52; References ~:16-27; Architecture ~:72-91)

Read `CLAUDE.md` lines 16-92 first to re-anchor (nothing here was moved by 004/005/001 except the committed FACTS pointer at :5-7).

- [ ] **Step 1: D1 — fix the `irc run` command copy (line 36-37)**

Replace line 36:
`uv run irc run                       # default 7-stage pipeline (no research, no fundamentals refresh)`
with:
`uv run irc run                       # default 10-stage pipeline (STAGE_NAMES; research optional, no fundamentals refresh)`

Replace line 37:
`uv run irc run --from <stage>        # resume from stage: ingest|research|discover|score|gold|allocate|plan`
with:
`uv run irc run --from <stage>        # resume from stage: ingest|research|discover|score|gold|allocate|plan|opportunity|memo|decision`

- [ ] **Step 2: D14 — add `monitor.json` to the monitor output list (line 47)**

In the `uv run irc monitor` line, replace `{report.html,drilldown.html,eval_trace.json}` with `{report.html,drilldown.html,monitor.json,eval_trace.json}` and, immediately after `eval_trace.json};`, leave the rest unchanged. Result fragment: `→ outputs/<date>/monitor/{report.html,drilldown.html,monitor.json,eval_trace.json}; appends data/monitor/forward_ledger.jsonl.` (`monitor.json` is the completion sentinel — the last atomic write.)

- [ ] **Step 3: D2 — add the two daily verticals + missing commands (after line 48)**

After the `uv run irc monitor snapshot` line (48), insert:

```
uv run irc monitor flow-capture      # daily 15:45 post-close: ONE ulist.np batch appends today's completed-day capital-flow row to data/monitor/fund_flow_series.json, then chains `irc rotation`. Never run before the 15:00 close.
uv run irc fundamentals stock-valuation  # per-stock PE/PB history → stock_valuation_history table (active-fund look-through valuation leg)
uv run irc rotation                  # daily 15:45 sector-rotation radar over ~200 EastMoney boards → outputs/<date>/rotation/rotation_radar.{json,md}; appends data/rotation/forward_ledger.jsonl. Advisory-only, exit 0 always (ADR 0023).
uv run irc rotation seed             # one-time/top-up board-history + stock→board-map seed → data/rotation/board_series.json (paced board-plane fetch; needs a CN-reachable egress)
```

- [ ] **Step 4: D1 — rewrite the Architecture stage-flow diagram (lines 72-78)**

Replace the block:

```
Stage flow (default `irc run`):

```
ingest → [research?] → discover → score → gold → allocate → plan → memo
                                                                     ↓
                                                  opportunity → decision   (run separately)
```
```

with:

```
Stage flow (default `irc run`) — all 10 `STAGE_NAMES` in order (`research` is optional, skipped unless `RESEARCH_ENABLED=true`):

```
ingest → [research?] → discover → score → gold → allocate → plan → opportunity → memo → decision
```

`opportunity` runs **before** `memo` (a spurious halt there suppresses the memo — see the preflight-budget note below); `decision` is last. `irc opportunity` / `irc decision` are also runnable standalone.
```

- [ ] **Step 5: D2 — add monitor + rotation to the package list (line 81)**

In line 81, change the package list from
`src/irc/{discovery,scoring,allocation,trades,memo,opportunity,decision,gold_score (under evals),fundamentals,research,news,queries}/`
to add `monitor,rotation`:
`src/irc/{discovery,scoring,allocation,trades,memo,opportunity,decision,gold_score (under evals),fundamentals,research,news,queries,monitor,rotation}/`

Then insert a new bullet immediately after line 81:

```
- `src/irc/monitor/`, `src/irc/rotation/` — the two **daily verticals**, distinct from the weekly `irc run` pipeline: `irc monitor` (10-fund daily brief; ADR 0017/0019/0020/0021/0022) and `irc rotation` (sector-rotation radar over EastMoney boards; ADR 0023). Each owns its package, types, README, and launchd agent (see the Doc map in References).
```

- [ ] **Step 6: 002-b — relabel the overall-workflow.html link (line 20)**

Replace line 20:
`- [`docs/diagrams/overall-workflow.html`](docs/diagrams/overall-workflow.html) — end-to-end pipeline diagram including the opportunity/discipline post-stages.`
with:
`- [`docs/diagrams/overall-workflow.html`](docs/diagrams/overall-workflow.html) — thesis-cards evidence pipeline (verified 2026-05-21; **predates the `monitor`/`rotation` verticals — not end-to-end**; full regen deferred, low urgency).`

- [ ] **Step 7: 002-b — add the Doc map block to References (after line 27)**

After the last existing References bullet (the "CONTEXT.md Monitor set" line near :27), insert:

```
**Doc map — five operator manuals, each the single owner of its topic:**

- [`README.md`](README.md) — user-facing operations (env, workflows by cadence, output inspection).
- [`docs/monitor/README.md`](docs/monitor/README.md) — `irc monitor` daily/weekly ops. **Single owner of factor weights + schema/engine version numbers** (other docs link here or cite the code constant; the version-grep guard `tests/docs/test_version_sync.py` enforces it).
- [`src/irc/rotation/README.md`](src/irc/rotation/README.md) — `irc rotation` radar ops + geo-block troubleshooting.
- [`evals/README.md`](evals/README.md) — the eval surface (`irc eval monitor_*`): lifecycle, metrics, thresholds.
- [`ops/launchd/README.md`](ops/launchd/README.md) — launchd scheduler runbook. **Single owner of the schedule table.**

Diagrams: [`monitor-workflow.html`](docs/diagrams/monitor-workflow.html) (monitor vertical) · [`overall-workflow.html`](docs/diagrams/overall-workflow.html) (thesis-cards pipeline, 2026-05-21) · [`stage0-ingest-to-plan.html`](docs/diagrams/stage0-ingest-to-plan.html).
```

- [ ] **Step 8: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(002-a/b): CLAUDE.md stage diagram + rotation/monitor verticals + doc map (D1/D2/D14)"
```

---

## Task 3: README.md cluster (D5, D6, D8, D10, D14, D15, Doc map, single-owner, uncommitted-hunk fixes)

**Files:**
- Modify: `README.md`

Read `README.md` lines 7-12, 130-140, 198-260, 386-410, 440-446 first to re-anchor (item 001 reworked the flow-capture rows; the IRC_CN_PROXY section was reintroduced post-review).

- [ ] **Step 1: 002-b — Doc map block in Design references (after line 11)**

After line 11 (the Monitor operations manual bullet), insert:

```
**Doc map** (five manuals — each the single owner of its topic; link, don't copy):
[`README.md`](README.md) (this file) · [`docs/monitor/README.md`](docs/monitor/README.md) (monitor ops; **owns factor weights + schema/engine numbers**) · [`src/irc/rotation/README.md`](src/irc/rotation/README.md) (rotation ops) · [`evals/README.md`](evals/README.md) (eval surface) · [`ops/launchd/README.md`](ops/launchd/README.md) (**owns the schedule table**). Diagrams: [`monitor-workflow.html`](docs/diagrams/monitor-workflow.html) · [`overall-workflow.html`](docs/diagrams/overall-workflow.html) (thesis-cards, 2026-05-21) · [`stage0-ingest-to-plan.html`](docs/diagrams/stage0-ingest-to-plan.html).
```

- [ ] **Step 2: Uncommitted-hunk fix — flow-leg proxy wording (line 133)**

Replace the fragment `So the monitor's *flow* leg works direct; only the commands below need a CN egress that can reach `clist/get` / `push2his`:`
with:
`So the monitor's *flow* leg is **routed through `IRC_CN_PROXY` when set and works direct when unset** (it doesn't *require* the proxy — unlike the board plane; matches `docs/monitor/README.md` env table + `flow_batch_fetch.py:83-86`); only the commands below need a CN egress that can reach `clist/get` / `push2his`:`

- [ ] **Step 3: Uncommitted-hunk fix — "~200 boards" caveat (line 139)**

In the `uv run irc rotation seed` table row, replace `~200 boards` with `~200 boards (pagination cap — exact universe unverified, see review R-3)`.

- [ ] **Step 4: D8 — Report v3 → v4 (line 200)**

In line 200, replace `Report v3 adds` with `Report v4 adds`. Leave the "fixed 10-fund", "Engine 4", and `monitor.json` parts of this line untouched (already correct).

- [ ] **Step 5: D8-adjacent — single-owner note above the launchd summary table (before line 246)**

Immediately before the `| Agent | Schedule (Asia/Shanghai) | What it runs |` table (~:246), insert a pointer line:

```
The **authoritative schedule table** (exact times, gates, locks, watchdogs) lives in [`ops/launchd/README.md`](ops/launchd/README.md) — the summary below links to it, never diverges from it.
```

- [ ] **Step 6: D10 — flow-capture row chains `irc rotation` (line 248)**

Replace the flow-capture row's "What it runs" cell:
`` `irc monitor flow-capture` (best-effort; data-health notify: silent-on-ok, pages on rotation abstain/degradation, one-time abstain→ok recovery notice) ``
with:
`` `irc monitor flow-capture` → **chains `irc rotation`** (sector-rotation radar, ADR 0023, advisory-only); best-effort data-health notify: silent-on-ok, pages on rotation abstain/degradation, one-time abstain→ok recovery notice ``

- [ ] **Step 7: D5 — eval_trace schema 6 → 7 (line 224)**

Replace `(schema 6)` with `(schema 7)` on line 224.

- [ ] **Step 8: D14 — cheatsheet monitor row gains `monitor.json` (line 391)**

In the `| uv run irc monitor |` cheatsheet row, replace `(self-contained daily brief + per-stock board) + `eval_trace.json`` with `(self-contained daily brief + per-stock board) + `monitor.json` (completion sentinel) + `eval_trace.json``.

- [ ] **Step 9: D15 — add rotation rows to the cheatsheet (after the flow-capture row, ~:393)**

After the `| uv run irc monitor flow-capture |` cheatsheet row, insert:

```
| `uv run irc rotation` | `outputs/<date>/rotation/rotation_radar.{json,md}` (sector-rotation radar) + appends to `data/rotation/forward_ledger.jsonl` (daily 15:45, chained after flow-capture) |
| `uv run irc rotation seed` | `data/rotation/board_series.json` (one-time / top-up board-history + stock→board-map seed) |
```

- [ ] **Step 10: D6 — "fixed 7 funds" → 10 (line 444)**

Replace `the fixed 7 funds `irc monitor` covers` with `the fixed 10 funds `irc monitor` covers` on line 444.

- [ ] **Step 11: Commit**

```bash
git add README.md
git commit -m "docs(002-a/b): README schema/funds/report-version + rotation rows + doc map + proxy wording (D5/D6/D8/D10/D14/D15)"
```

---

## Task 4: monitor/eval/context/diagram/FACTS cluster (D4, D7, D6, D11, D12, D9, D13, F7-CONTEXT, monitor-workflow labels, FACTS F8)

**Files:**
- Modify: `docs/monitor/README.md` (D4, D7)
- Modify: `evals/README.md` (D6, D11, D12)
- Modify: `CONTEXT.md` (D9, D13, F7 §12 follow-up)
- Modify: `docs/diagrams/monitor-workflow.html` (D7, D8, rotation-chain label)
- Modify: `FACTS.md` (F8 section)

Read each region first: `docs/monitor/README.md` lines 40-65, 138-145, 232-236; `evals/README.md` lines 75-80, 143-150, 185-192, 306-312; `CONTEXT.md` lines 40-45, 283-296, 324-328; `docs/diagrams/monitor-workflow.html` lines 76-80, 290-296, 304-324, 348-352, 428-440; `FACTS.md` lines 9-22.

- [ ] **Step 1: D4 — docs/monitor/README f127 → f100 (lines 44, 62, 235)**

Line 44: replace `full-basket secids, `f184`+`f127`)` with `full-basket secids, `f184`+`f100`)`; and in the same line replace `merges the `f127` 行业 names into` with `merges the `f100` 行业 names into`. (Ground truth: `flow_batch_fetch.py:86` requests `f100`; f127 is numeric on `ulist.np`.)

Line 62: replace `batch call carries `f127`;` with `batch call carries `f100`;`.

Line 235: replace `(batch-first f127; fallback merges too)` with `(batch-first f100; fallback merges too)`.

- [ ] **Step 2: D7 — docs/monitor/README engine-3 → engine-4 (line 141)**

Replace `honestly until engine-3 blocks mature` with `honestly until engine-4 blocks mature`.

- [ ] **Step 3: 002-b — single-owner declaration in docs/monitor/README (top of the "Factors and signal" section, ~:92)**

Immediately before the `### Factors and signal (engine 4)` heading (~:92), insert:

```
> **Single owner:** this manual is the canonical source for factor weights and the schema/engine version numbers. Other docs link here or cite the code constant (`trace.SCHEMA_VERSION` / `monitor_cmd._ENGINE_VERSION`); the version-grep guard `tests/docs/test_version_sync.py` enforces agreement.
```

- [ ] **Step 4: D6 — evals/README "7-fund" → "10-fund" (line 77)**

Replace `daily for the 7-fund Monitor set` with `daily for the 10-fund Monitor set`.

- [ ] **Step 5: D11 — evals/README three → four MetricReport rows (lines 186-188)**

Replace the fragment `emits **three `MetricReport` rows**\n(`raw_composite_directional`, `publishable_bias_directional`, `rank_ic`) + a `details.json` sibling` (spanning two lines) with:
`emits **four `MetricReport` rows**\n(`raw_composite_directional`, `publishable_bias_directional`, `rank_ic`, and the FU1 diagnostic\n`engine_population` — appended, never scored/gating) + a `details.json` sibling`.
(Preserve the surrounding wrapping; the key change is `three`→`four` and adding `engine_population`. Ground truth: `evals/monitor_forward/runner.py:172-175` appends `MetricReport(name="engine_population", …)`.)

- [ ] **Step 6: D12 — evals/README six → seven pure scorers (lines 146 and 310)**

Line 146: replace `A `hypothesis` (derandomized) suite over the six pure scorers` with `A `hypothesis` (derandomized) suite over the seven pure scorers`.

Line 310: replace `hybrid-oracle suite over the six pure scorers` with `hybrid-oracle suite over the seven pure scorers`. (Ground truth: CONTEXT.md M2 bullet — "seven with the `flow` factor, ADR 0019".)

- [ ] **Step 7: D13 — CONTEXT narrative categories five → six (line 42)**

Replace `The five narrative categories: `citation-resolve`, `entailment-ablation`, `attribution-honesty`, `no-numbers`, `injection`.`
with `The six narrative categories: `citation-resolve`, `entailment-ablation`, `attribution-honesty`, `no-numbers`, `injection`, `mechanism`.`
(Ground truth: `src/irc/monitor/eval/cases/narrative/` holds `mechanism_1/2.json` — a 6th `category: "mechanism"`.)

- [ ] **Step 8: D13 — CONTEXT narrative scorer metrics four → six (line 44)**

Replace `- **Narrative scorer metrics** — the four **pure** `-> float` functions in `metrics_narrative.py`: `citation_resolution` (frac of claim `citation_ids` resolving in the pool), `entailment_ablation_pass` (claim X present **iff** its one supporting `evidence_pool` item is present), `attribution_honesty` (see below), and `hallucination_rate` (see below). Same purity guard as the impact scorers.`
with:
`- **Narrative scorer metrics** — the six **pure** `-> float` functions in `metrics_narrative.py`: `citation_resolution` (frac of claim `citation_ids` resolving in the pool), `entailment_ablation_pass` (claim X present **iff** its one supporting `evidence_pool` item is present), `attribution_honesty` (see below), `injection_resistance` (frac of injection cases where the directive was ignored), `hallucination_rate` (see below), and `mechanism_validity` (frac of claims whose stated mechanism is structurally valid). Same purity guard as the impact scorers.`
(Ground truth: `metrics_narrative.py` public metric fns = `citation_resolution`, `entailment_ablation_pass`, `attribution_honesty`, `injection_resistance`, `hallucination_rate`, `mechanism_validity` = 6.)

- [ ] **Step 9: D9 — CONTEXT retire the 17:30 schedule reference (line 326)**

Replace the fragment `The 17:30 daily / Saturday-morning schedules are documented as **machine-local wall-clock targeting the operator's own timezone**;`
with:
`The current agent schedule (12:15 monitor / 15:45 flow-capture+rotation / quarterly snapshot / Sat 09:00 weekly — the **single-owner table lives in [`ops/launchd/README.md`](ops/launchd/README.md)**; the retired 17:30 daily agent is gone) is documented as **machine-local wall-clock targeting the operator's own timezone**;`
and append to the same bullet's trailing `_Avoid_:` clause: change `_Avoid_: assuming launchd honors China time.` to `_Avoid_: assuming launchd honors China time; re-stating the schedule here instead of linking the ops README.`

- [ ] **Step 10: F7 — CONTEXT §12 follow-up F7 flip to built (lines 291-296)**

Replace the bullet body starting `- **§12 follow-up F7 — board-kline turnover fetch**:` (the full multi-line bullet ending `…field codes are interface-specific — T1/f100-f127 scar).`) with:

```
- **§12 follow-up F7 — board-kline turnover fetch (BUILT, merged `4d5af11d` 2026-07-05)**: `board_fetch.py:87,136` extends `fetch_board_hist` `fields2` and parses `f61` (换手率) at row position 10 into `turnover_pct` on backfill rows — so the turn leg now has kline-sourced history, not snapshot-only. It still goes dark (`turn_leg_dark`) for a board without enough live turnover history yet, or one that dropped out of a later snapshot (stale/renamed/partial) — honest, never a fabricated 0.0. Availability-class change → **no `radar_version` bump** (f100-fix precedent).
```

- [ ] **Step 11: D7/D8 — monitor-workflow.html report v3 → v4 and engine-3 → engine-4**

In `docs/diagrams/monitor-workflow.html` make these text-content replacements (do NOT touch line 292 `prompt v3` — that is the LLM prompt version, a separate axis):

- Line 78: `→ report v3 · plus 15:45` → `→ report v4 · plus 15:45`
- Line 306: `_write_outputs · report v3` → `_write_outputs · report v4`
- Line 323: `v3 brief · 今日速览 + 3 charts` → `v4 brief · 今日速览 + 3 charts`
- Line 431: `insufficient_data until engine-3 blocks mature` → `insufficient_data until engine-4 blocks mature`
- Line 438: `report v3 · engine "4" · eval schema "7"` → `report v4 · engine "4" · eval schema "7"`

- [ ] **Step 12: 002-b — monitor-workflow.html annotate the 15:45 box with the rotation chain (line 350)**

Replace the line-350 text content `launchd 15:45 · flow-capture` with `launchd 15:45 · flow-capture → rotation`. (Light annotation only; a dedicated rotation-chain box is deferred to the full regen, per 002-b scope.)

- [ ] **Step 13: F8 — FACTS.md update the board-plane TEMPORARY section (lines 13-19)**

Replace the fragment beginning `**As of 2026-07-05 this plane is hard-blocked** on this` through `F8 is resolved.**` with:

```
  **As of 2026-07-07 this plane is INTERMITTENT at day granularity, not hard-blocked** —
  `IRC_CN_PROXY` was dropped from `.env` on 2026-07-06 and direct egress now carries it:
  full success 2026-07-06 (rotation seed completed 200 boards × 60 rows, board-PE recovered
  69/70, forward ledger started 52 rows), refused again 2026-07-07 (`RemoteDisconnected`).
  Expect a mix of ok/abstain days; `irc rotation` writes `data_status: "abstain"` only on
  refused days — cheap and safe. `push2his`-via-`$IRC_HTTPS_PROXY` (the DXY route) stays dead
  — a separate problem. See `TODOS.md` "Sector rotation radar" §0-corrected entries and
  `docs/2026-07-05-sector-rotation-radar/F8-DIAGNOSIS-FIX-PLAN.md`. **Re-verify with the CN
  egress board-plane one-liners below before acting — this describes a live incident.**
```

- [ ] **Step 14: Commit**

```bash
git add docs/monitor/README.md evals/README.md CONTEXT.md docs/diagrams/monitor-workflow.html FACTS.md
git commit -m "docs(002-a/b): monitor/eval/context/diagram/FACTS drift + F8 state-correction (D4/D6/D7/D8/D9/D11/D12/D13)"
```

---

## Task 5: TODOS.md + rotation README — D3 state-corrections + 002-c registration

**Files:**
- Modify: `TODOS.md` (rotation section rewrite + 002-c entries)
- Modify: `src/irc/rotation/README.md` (F7/F8 follow-up entries)

Read `TODOS.md` lines 12-33 and `src/irc/rotation/README.md` lines 180-196 first to re-anchor (the diagnostics entry at the tail of the rotation section was added by item 004).

- [ ] **Step 1: D3 — TODOS triage paragraph rewrite (line 14)**

Replace the whole `Triage 2026-07-05 (post-#206 merge): …F8-DIAGNOSIS-FIX-PLAN.md`) §0.` paragraph with:

```
State (2026-07-07 review §0): **F7 BUILT + merged `4d5af11d` (2026-07-05)**; **first seed DONE 2026-07-06** (`data/rotation/board_series.json` = 200 boards × 60 rows 2026-04-08→07-06, all `turnover_pct`-carrying; forward ledger = 52 rows dated 07-06; monitor board-PE recovered 69/70). **F8 is superseded**: `IRC_CN_PROXY` was dropped from `.env` 2026-07-06 and direct egress is now **intermittent at day granularity** (full success 07-06, refused 07-07 `RemoteDisconnected`) — flaky-direct, not hard-blocked. Wrapper chaining is live (flow-capture → `irc rotation`). Fix plan + matrix: [`docs/2026-07-05-sector-rotation-radar/F8-DIAGNOSIS-FIX-PLAN.md`](docs/2026-07-05-sector-rotation-radar/F8-DIAGNOSIS-FIX-PLAN.md) §0.
```

- [ ] **Step 2: D3 — flip the F7 bullet to done (the `- [ ] **F7 — board-kline turnover fetch — ⚠️ BLOCKED by F8…` bullet)**

Replace that entire bullet (one long line) with:

```
- [x] **F7 — board-kline turnover fetch — BUILT + merged `4d5af11d` (2026-07-05).** `board_fetch.py:87,136` extends `fetch_board_hist` `fields2` and parses `f61` = 换手率 at row position 10 into `turnover_pct` on backfill rows (tolerant `_f`, 11-col fixture pinned). Availability-class change → no `radar_version` bump (f100-fix precedent). The earlier "BLOCKED by F8 / probe contradicted" notes are obsolete — F8 is intermittent-direct, not hard-blocked (§0 above), and the seed ran successfully 07-06.
```

- [ ] **Step 3: D3 — flip the "DO NOW · Ops — first seed never run" bullet to done**

Replace that entire bullet with:

```
- [x] **Ops — first `irc rotation seed` DONE 2026-07-06.** `data/rotation/board_series.json` = 200 boards × 60 rows; forward ledger started (52 rows). Holdings cache was already warm (446–479 funds). Re-seed opportunistically on good egress days (resumable; skip-set now honors `fresh_slice` freshness — item 005 / R-4). ⚠️ The seed is still unpaced/breaker-less (R-5 below) — pace it before the next large opportunistic seed.
```

- [ ] **Step 4: D3 — rewrite the F8 BLOCKER bullet to the superseded state**

Replace the entire `- [ ] **⚠️ F8 · BLOCKER — board endpoints unreachable…` bullet with:

```
- [ ] **F8 — board-plane egress is INTERMITTENT, not blocked (superseded 2026-07-06, review §0).** `IRC_CN_PROXY` dropped from `.env` 07-06; direct egress: full success 07-06 (`clist/get` pn=1/2 HTTP 200, `push2his` backfill complete, seed + radar ok + board-PE 69/70), refused 07-07 (`RemoteDisconnected`). Expect a mix of ok/abstain days; the daily abstain path is cheap/safe (1 clist call, exit 0, no series/ledger mutation). *Why still open:* board-plane success rate is unproven over weeks; F1's forward clock only accrues on EM-reachable days. *Pick up:* if `data_status: ok` days stay < ~50% of trading days over 2–3 weeks, buy a CN-residential/EM-allowed egress (fixes snapshot + history + board-PE + flow in one move, zero code). `push2his`-via-`$IRC_HTTPS_PROXY` (DXY) is a separate dead route. See F8-DIAGNOSIS-FIX-PLAN.md §0.
```

- [ ] **Step 5: 002-c — record the two Tier-1 code fixes as DONE (insert after the F8 bullet)**

Insert:

```
- [x] **R-1 — candidates join (names vs codes) FIXED — item 004, PR #208 (`76359c69`).** `resolve_candidates` now translates 行业 name → BK code from the run's `BoardState` list before filtering; production-shaped integration test added. The dead join produced 0 candidates on every run (incl. the ok 07-06 run); offline replay yielded ~96 rows. (review R-1 / Tier-1 #1)
- [x] **R-4 — seed skip-set freshness FIXED — item 005, PR #209 (`6dc5d83b`).** Seed skip-set now = `fresh_slice(existing, today)`, so stale (>30-cal-day) mappings fall out and re-seed self-heals; prevents the silent exposure collapse projected ~2026-08-05. (review R-4 / Tier-1 #5)
```

- [ ] **Step 6: 002-c — DO-NOW monitor Tier-1 pointers (insert after R-1/R-4 done markers, still in the rotation section OR create the new "## Monitor daily brief" section per Step 8 and place them there). Place these THREE under the new Monitor section (Step 8):**

(hold — implement in Step 8 so they sit under the Monitor heading.)

- [ ] **Step 7: 002-c — rotation deferred findings (append at the END of the "## Sector rotation radar" section, after the existing Cosmetic entry)**

Append:

```
### Review 2026-07-07 — rotation deferred findings (why-deferred + pickup)

- [ ] **R-2 — flow warm-up gate defeated.** `composite.py:23-26` `_tail_mean` drops Nones → after ONE snapshot day, `flow5` = that single value for all 200 boards at 30% weight, `flow_leg_dark` never fires (07-06: 1 snapshot day, `dark_legs: []`, `data_status: ok`). Also seams the hysteresis series. *Why defer:* the fix (require ≥k=3–5 non-None samples, or a `degraded_flow_warmup` marker) changes the ledger's early state semantics → needs a **`radar_version` bump decision**. *Pick up:* with the R-6/R-7 history-hygiene `radar_version` decision (bundle the bump). (review R-2)
- [ ] **R-3 — universe truncation at exactly the 200 cap.** `board_fetch.py:22-23,109-126` `_PZ=100`, `_MAX_PAGES=2`, `data.total` never read, no `fid` sort key → if the real universe > 200, silent daily churn of *which* 200 appear. *Why defer:* needs a live `data.total` probe, only possible on an EM-reachable day. *Pick up:* on the **next good egress day** — one call reads `data.total`; if > 200, page to exhaustion + pin `fid`. Reconcile the "~200 (cap)" doc wording then. (review R-3)
- [ ] **R-5 — seed unpaced + breaker-less + O(n²) store I/O.** `seed.py:38-53` fires up to ~200 back-to-back `push2his` calls (the documented self-DoS shape); `series_store.py:79-90` rewrites the full 2.9 MB store per board. Spec §8 required "paced with backoff". *Why defer:* not blocking today (seed already ran); a heavy re-seed is only opportunistic. *Pick up:* **before the next large opportunistic seed / top-up** on a good egress day. (review R-5 / Tier-2 #10)
- [ ] **R-6/R-7 — rotation history hygiene.** R-6: snapshot-absent boards never pruned (`series_store.py:66-76`), frozen rows keep flow/turn non-None so dark gates never fire; row-index (not date-aligned) windows pollute percentiles. R-7: today's dark flags rewrite history (`rotation_cmd.py:180-182,114`) → one bad leg day flips `state`/`days_in_state` wholesale; ledger keeps old rows → incoherent state sequences. *Why defer:* both change the persisted series/ledger shape → **`radar_version` decision** and must land with F1's design. *Pick up:* **with F1 analysis** (the forward-eval that reads these sequences). (review R-6/R-7 / Tier-3)
- [ ] **R-8/R-9 — holdings quarter + empty-cache.** R-8: `holdings_as_of` always None (`_cmd_helpers.py:81`, `holdings_fetch.py:80`) → every candidate renders 持仓季度 N/A, `name_cn` = fund code. R-9: empty holdings cached permanently (`holdings_fetch.py:90-97` + `seed.py:61-62` skip-on-existence) → a transient empty frame zeroes a fund's exposure forever. *Why defer:* both surface only once candidates render (R-1 just unblocked that) and R-9 needs a cache-invalidation policy. *Pick up:* **at the first quarterly holdings roll** (2026 Q3 disclosures, ~late Oct 2026). (review R-8/R-9)
- [ ] **R-10/R-11 — weekend-dated ledger rows + minor cosmetics.** R-10: manual weekend/holiday runs write weekend-dated ledger rows (`rotation_cmd.py:198`) the series store prunes as non-trading days → phantom dates F1 must special-case. R-11: same-day abstain stub overwrites a successful report (`rotation_cmd.py:162-165`); `⚠追高` renders as a stray 7th cell (`report.py:24-27`); `IRC_ROTATION_TOPUP_BUDGET` is actually the chunk **size** (lowering it *increases* calls, `rotation_cmd.py:242-245`); ~331 never-mappable HK symbols refetched every seed. *Why defer:* low-frequency / cosmetic; several need the same `radar_version`/F1 window. *Pick up:* opportunistically alongside R-6/R-7. (review R-10/R-11)
```

- [ ] **Step 8: 002-c — new Monitor section with DO-NOW + deferred + needs-own-spec entries**

Immediately AFTER the entire "## Sector rotation radar (`irc rotation`)" section (before "## Reliability"), insert a new section:

```
## Monitor daily brief (`irc monitor`) — review 2026-07-07 follow-ups

**Tier-1 DO-NOW (this week, S each — see [`docs/2026-07-07-workflow-review.md`](docs/2026-07-07-workflow-review.md) §2.2/§3):**

- [ ] **M-3 (DO NOW) — Board-PE DARK silently disables the False-Cheap clamp.** `_dual_track.py:63-64` (industry N/A → `val_score = self_score`, clamp can never fire); `render_drilldown.py:198` returns `''` for DARK. On day 4+ of a board block, valuation renders at confidence 1.0/"fresh" while being exactly the value-trap-blind score ADR 0020 exists to prevent — no fund-card marker, no confidence discount. Fix (S): DARK fund-card marker ("价值陷阱检测不可用") + coverage-scaled valuation confidence. (review M-3 / Tier-1 #3)
- [ ] **M-4-stopgap (DO NOW) — first-wins forward-ledger append.** `forward_log.py:56-64` is last-write-wins → same-day reruns rewrite forward history (37 duplicate `(run_date, fund_id)` keys already; 06-30 ran 3×). Fix (S): first-wins append per `(run_date, fund_id)` or a `rerun` flag column — protects forward metrics from rerun overwrite immediately. (review M-4 stopgap / Tier-1 #2)
- [ ] **M-7 (DO NOW) — per-fund exception isolation.** One unguarded DuckDB read (`inputs_loader._stock_series_by_code`, `inputs_loader.py:221-241`) can kill the whole 10-fund brief; the fund loop has try/finally but no except (`monitor_cmd.py:1099-1113`). A concurrent `irc ingest` write-lock (a documented real event) → zero outputs instead of a degraded card. Fix (S): wrap each fund in an except → a failed fund degrades one card, not the brief. (review M-7 / Tier-1 #4)

**Tier-2 — needs its own spec (M effort; do NOT inline here):**

- [ ] **M-1 — flow freshness contract unimplemented (needs own spec).** CONTEXT/ADR 0019 specify FRESH / STALE-N (`滞后 N 个交易日`) / DARK (>3 td), but there is **no age check anywhere on the flow path** (`holding_metrics.py:76-82,193-201`, `flow_series_store.py:39-43`, `monitor_cmd.py:204-214`; `grep 滞后 src/irc/monitor/` → 0 hits). Serve-while-stale is unbounded, labeled fresh (1/30 symbols ~7 td stale today, untagged). *Why defer:* the single largest plausible-but-wrong path — a cross-module contract change deserving a locked spec + integration test (Opus-scaffolding review §4 rule: contract sentences name their enforcing test). *Pick up:* next monitor structural-trust milestone. (review M-1 / Tier-2 #7)
- [ ] **M-2 — `factor_freshness` is a hardcoded `"fresh"` constant (needs own spec).** `monitor_cmd.py:442` `{c.name: "fresh" …}` rendered verbatim (`render_factors.py:99-131`) — the report's only per-factor freshness surface is a lie by construction (also covers the self-leg valuation series, no ingest-age check; same family as TODOS #47). *Why defer:* real freshness = flow newest-covered-row date + valuation board-PE state + self-series ingest age + trend NAV as_of + heat fetched-today flag — bundled with M-1. *Pick up:* with M-1's spec. (review M-2 / Tier-2 #9)
- [ ] **M-4-full — same-day evidence pinning (needs own spec).** `monitor_cmd.py:1028-1047` / `impacts.py:52-85` re-search + re-LLM each run → macro_tilt band-flipping (today's only ADD 519069 sits 0.034 over the 0.40 band). Full fix: persist `theme_results` + validated impacts under `outputs/<date>/monitor/` on first run; reruns reuse. *Why defer:* touches ledger + evidence-pinning semantics (Policy-B-adjacent) — spec-worthy. *Pick up:* after M-4-stopgap lands, as the Tier-2 determinism milestone. (review M-4 full / Tier-2 #8)

**Deferred (P2–P3, why-deferred + pickup):**

- [ ] **M-5 — `flow_source: "batch_today"` is a misnomer / no newest-row date in the trace.** `trace.py:154-156`: store-only reads mean the newest possible row is yesterday's close, yet the trace asserts freshness the data lacks under M-1. *Why defer:* provenance-label change, cosmetic until M-1's age-gate exists. *Pick up:* fold into M-1's spec (add a newest-row-date field to the trace). (review M-5 / Tier-3)
- [ ] **M-6 — `low_factor_agreement` sign-conflict has no magnitude floor.** `signal.py:60-62`: today 519069 carries the caveat for flow = −0.008 vs five positives → caveat fatigue. *Why defer:* a threshold tweak with a false-positive/omission trade-off worth a data pass. *Pick up:* when caveat fatigue is observed across a week of briefs. (review M-6 / Tier-3)
- [ ] **M-8 — Board-PE `as_of` records fetch-date, not data-date.** `industry_valuation.py:115-117` → weekend manual runs under-count later staleness. Known-accepted design; listed for awareness. *Why defer:* only bites on manual weekend runs; low impact. *Pick up:* with M-1/M-2's freshness rework (the as_of source is the same object). (review M-8 / Tier-3)
```

- [ ] **Step 9: D3 — rotation README F7/F8 follow-up entries (lines 187-195)**

In `src/irc/rotation/README.md`, replace the `- **F7** board-kline **turnover** fetch (akshare uses `f61`) — needs its own AC1 live probe before wiring…` bullet with:

```
- **F7** board-kline **turnover** fetch — **BUILT, merged `4d5af11d` (2026-07-05)**: `board_fetch.py:87,136` parses `f61` (换手率) into `turnover_pct` on backfill rows, so the turn leg now has kline history (not snapshot-only). Still goes `turn_leg_dark` for boards without enough live turnover history yet or dropped from a later snapshot — honest, never a fabricated 0.0. No `radar_version` bump (availability class).
```

Then replace the `- **F8** board fetch off **`clist/get`**…` bullet's lead sentence to note the current regime — change `the board snapshot/history endpoints (`clist/get`, `push2his` kline) are blocked on some geo-throttled egresses that still reach `ulist.np` (see Troubleshooting).` to `the board snapshot/history endpoints (`clist/get`, `push2his` kline) are **intermittently** reachable on direct egress (ok 2026-07-06, refused 07-07) and blocked on some geo-throttled egresses that still reach `ulist.np` (see Troubleshooting).` (Leave the rest of the F8 migration-design bullet intact.)

- [ ] **Step 10: Commit**

```bash
git add TODOS.md src/irc/rotation/README.md
git commit -m "docs(002-a/c): TODOS F7/F8/seed state-correction + review deferred-findings registration (D3, R-*/M-*)"
```

---

## Task 6: Verification + exit gate

**Files:** none (verification only, then any residual fix + final grep evidence).

- [ ] **Step 1: Run the version-grep guard — must now be GREEN**

Run: `uv run pytest tests/docs/test_version_sync.py -v`
Expected: all 4 tests PASS. If any fail, the failing doc still carries a stale number — fix it (re-run Tasks 3/4 anchors) and re-run. This is the red→green closure.

- [ ] **Step 2: Run the full docs test dir + smoke (no network)**

Run: `uv run pytest tests/docs/ -v`
Expected: PASS (both `test_readme_spend.py` and the new `test_version_sync.py`).

- [ ] **Step 3: Ruff (only the new test file is Python)**

Run: `uv run ruff check tests/docs/test_version_sync.py`
Expected: clean.

- [ ] **Step 4: Re-verify EVERY D-item is fixed (grep evidence)**

Run each and confirm the expected result:

```bash
# D1: no stale diagram; command copy fixed
grep -n "10-stage pipeline\|opportunity → memo → decision" CLAUDE.md        # both present
grep -n "plan → memo" CLAUDE.md                                             # ABSENT (old diagram gone)
# D2: verticals present
grep -n "irc rotation\|monitor flow-capture\|fundamentals stock-valuation" CLAUDE.md   # present
grep -n "queries,monitor,rotation" CLAUDE.md                                # present
# D3: F7 built, F8 superseded, seed done
grep -n "F7 — board-kline turnover fetch — BUILT\|first \`irc rotation seed\` DONE\|F8 is superseded\|F8 — board-plane egress is INTERMITTENT" TODOS.md   # present
grep -n "R-1 — candidates join.*FIXED\|R-4 — seed skip-set freshness FIXED" TODOS.md   # present
# D4: f100 in docs/monitor/README, no batch f127
grep -n "f184\`+\`f100\|batch call carries \`f100\|batch-first f100" docs/monitor/README.md   # present
grep -n "f127" docs/monitor/README.md                                        # only the stock/get fallback mentions, none for the ulist.np batch
# D5/D8 README
grep -n "schema 7" README.md; grep -n "schema 6" README.md                   # 7 present, 6 ABSENT
grep -n "Report v4" README.md; grep -n "Report v3" README.md                 # v4 present, v3 ABSENT
# D6
grep -n "fixed 10 funds" README.md; grep -n "10-fund Monitor set" evals/README.md   # present
# D7 docs/monitor + diagram
grep -n "engine-4 blocks mature" docs/monitor/README.md docs/diagrams/monitor-workflow.html   # present
grep -n "engine-3" docs/monitor/README.md docs/diagrams/monitor-workflow.html                 # ABSENT
# D9 CONTEXT
grep -n "single-owner table lives in" CONTEXT.md                             # present
# D10
grep -n "chains \`irc rotation\`" README.md                                  # present
# D11/D12 evals
grep -n "four \`MetricReport\` rows\|engine_population" evals/README.md       # present
grep -n "seven pure scorers" evals/README.md                                 # present (x2)
# D13 CONTEXT
grep -n "six narrative categories\|six \*\*pure\*\*" CONTEXT.md               # present
# D14
grep -n "monitor.json" CLAUDE.md README.md                                   # present in both cheatsheet + arch
# D15
grep -n "uv run irc rotation\b" README.md                                    # cheatsheet rows present
# 002-b diagrams
grep -n "report v4\|flow-capture → rotation" docs/diagrams/monitor-workflow.html   # present
# FACTS F8
grep -n "INTERMITTENT at day granularity" FACTS.md                           # present
grep -n "hard-blocked" FACTS.md                                              # ABSENT (or only in a non-F8 historical context)
```

- [ ] **Step 5: Review the full diff**

Run: `git diff main...HEAD --stat` and `git log --oneline main..HEAD`
Confirm: only docs + `tests/docs/test_version_sync.py` changed; 6 task commits present; no `src/irc/` behavior files touched.

- [ ] **Step 6: Exit-gate checklist (every item must be YES)**

- [ ] Every D1–D15 re-verified fixed (Step 4 greps all as expected).
- [ ] `git diff` reviewed — docs-only + the one guard test (Step 5).
- [ ] Version-grep test went RED (Task 1 Step 2) → GREEN (Step 1). Evidence captured.
- [ ] FACTS.md F8 section updated to the intermittent-direct state (Step 4 FACTS greps). (FACTS.md itself was already committed at run start — this gate item = the F8 body edit, done in Task 4.)
- [ ] 002-c: R-1/R-4 recorded DONE with PR refs; M-3/M-4-stopgap/M-7 as DO-NOW; M-1/M-2/M-4-full as needs-own-spec; R-2/R-3/R-5/R-6/R-7/R-8/R-9/R-10/R-11 + M-5/M-6/M-8 deferred with why-deferred + pickup.
- [ ] 002-b: Doc map in README + CLAUDE.md; single-owner declarations (ops/launchd schedule table; docs/monitor factor/version numbers); monitor-workflow labels refreshed; overall-workflow relabeled via the CLAUDE.md link.

No final commit here — Task commits already cover the work. (This plan file itself is committed separately by the authoring session as `plan(002): docs-sync + TODOS reconciliation`.)

---

## Self-Review (author checklist — completed)

- **Spec coverage:** D1 (T2 s1/s4), D2 (T2 s3/s5), D3 (T5 s1-4/s9), D4 (T4 s1), D5 (T3 s7), D6 (T3 s10 + T4 s4), D7 (T4 s2/s11), D8 (T3 s4 + T4 s11), D9 (T4 s9), D10 (T3 s6), D11 (T4 s5), D12 (T4 s6), D13 (T4 s7/s8), D14 (T2 s2 + T3 s8), D15 (T3 s9). 002-a FACTS F8 (T4 s13). 002-b doc map (T2 s7 + T3 s1), single-owner (T3 s5 + T4 s3 + T4 s9), monitor-workflow labels (T4 s11/s12), overall-workflow relabel (T2 s6). 002-c (T5 s5-8). 002-d (T1 + T6 s1). Exit gate (T6). All covered.
- **Judgment calls:** (a) single-owner is implemented as **declaration + link**, not table deletion, to avoid conflicting with D10 (which needs the README flow-capture row edited, not removed) — light-touch per the 002-b "full regen deferred" scope; (b) the 002-d test guards only code-backed versions (schema/engine/radar) — report-version v3→v4 is guarded by the Task-6 grep, not the unit test; (c) M-items get their own `## Monitor daily brief` H2 section (mirrors the existing rotation section) rather than being buried in `## Reliability`; (d) rotation README F8 bullet keeps its migration-design body — only the "blocked" lead sentence is softened to "intermittent".
- **No placeholders:** every edit carries exact old→new text or a full insert block.
