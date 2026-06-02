# `irc eval-funds` — Targeted Fund Evaluation Command — Design

**Date:** 2026-06-01
**Status:** Approved (brainstorm) → pending implementation plan
**Author:** pairing session (metals / 算力金属 sleeve)

## Context

A user discovered the 算力金属 (compute-metals) sleeve, cached active-fund holdings
snapshots for 10 previously-unsnapshotted metals/resource funds (now 83 funds under
`data/fundamentals/2026Q1/active_fund/`), and wants a per-fund **evaluation** that says,
for each fund, which `opportunity_state` it lands in — in particular **which qualify as
`core_dca`**.

The existing `irc opportunity` command already produces this classification, but only for
funds that survive `discover → score` and the active-fund **cap**, and today's full pipeline
**halts at `ingest` (exit 1)**. We therefore cannot get these specific funds evaluated by
re-running the native pipeline without unrelated work. This command provides a targeted,
deterministic path that reuses the pipeline's exact classification functions on an explicit
fund list.

## 1. Goals

- Evaluate an **explicit list of fund ids** and report each fund's four sub-states
  (valuation, heat, thesis, product-quality), its composed `opportunity_state`, its
  `dca_action`, and a boolean **`core_dca`** verdict.
- Reuse the pipeline's existing classification logic verbatim — **no new business logic**.
- Work from **cache + the existing `data/local.duckdb`**, sidestepping the broken `ingest`,
  discovery gating, and the active-fund cap.
- Produce a human-readable markdown report (knowledge about each fund) **and** a JSON
  artifact for downstream use.
- Be **honest about degraded data**: never assert `core_dca` when a sub-state is
  `insufficient_evidence`.

## 2. Non-goals

- Not fixing the `ingest` exit-1 failure (tracked separately).
- Not changing discovery, scoring, the active-fund cap, or any existing pipeline output.
- Not fetching live data — the command reads the cached snapshots and the existing DuckDB.
  (Valuation/heat come from already-ingested `nav_history`/`prices`; thesis from cached
  `ActiveFundSnapshot`s.)
- Not applying Policy B publishability as a gate — `opportunity_state`/`core_dca` are
  reported regardless of memo publishability (publishability MAY be surfaced as an
  informational flag, but does not change the verdict).
- Not persisting to the standard `opportunity_report.json` (this is a side artifact).

## 3. Architecture

### 3.1 Command — `irc eval-funds` (new top-level `@main.command`)

`opportunity` is a single `@main.command`, so `eval-funds` is added as a sibling top-level
command in `src/irc/cli.py`, lazy-importing `run_eval_funds` from
`irc.commands.fund_eval_cmd`, matching the existing command pattern.

Options:
- `--ids TEXT` (or `--ids-file PATH`) — comma-separated fund ids. One of the two required.
- `--quarter TEXT` — snapshot quarter (default: latest cached quarter discovered on disk).
- `--role TEXT` — role label stamped on synthesized score rows (default
  `satellite_cn_metals`). Affects display/role only, **not** `opportunity_state`.
- `--db PATH` — DuckDB path (default `data/local.duckdb`).
- `--out PATH` — markdown output path (default `outputs/<today>/fund_eval.md`; the JSON
  sibling is the same stem with `.json`).
- `--repo-root PATH` — default `.`.

### 3.2 Pure core — `src/irc/opportunity/fund_eval.py` (<200 lines)

A frozen result type and a pure evaluator:

```python
@dataclass(frozen=True)
class FundEval:
    instrument_id: str
    name_cn: str
    valuation_state: ValuationState
    heat_state: HeatState
    thesis_state: ThesisState
    product_quality_state: ProductQualityState
    opportunity_state: OpportunityState
    dca_action: DcaAction
    core_dca: bool                       # == (opportunity_state == "core_dca")
    note_cn: str                         # opportunity_reason
    top_holdings: tuple[tuple[str, str, float], ...]   # (symbol, name_cn, weight_pct)
    evidence_gaps: tuple[str, ...]
    role: str
```

```python
def evaluate_fund(
    inp: OpportunityInput,
    snapshot: ActiveFundSnapshot | None,
    *, role: str,
) -> FundEval:
    row = build_opportunity_row(inp, None, snapshot=snapshot)
    dca = derive_dca_action(row)
    return FundEval(... core_dca=(row.opportunity_state == "core_dca") ...)

def evaluate_funds(items: Iterable[EvalItem]) -> tuple[FundEval, ...]: ...
```

`evaluate_funds` takes already-loaded `(OpportunityInput, ActiveFundSnapshot|None, role)`
tuples (all I/O performed at the command edge) and is unit-testable without DB or network.
Plus renderers `render_fund_eval_md(evals) -> str` and `render_fund_eval_json(evals) -> str`
(or a dict, serialized at the edge).

### 3.3 Command edge — `src/irc/commands/fund_eval_cmd.py`

`run_eval_funds(repo_root, ids, quarter, role, db_path, out_path) -> int`:
1. Parse the id list (from `--ids` or `--ids-file`).
2. Open the DuckDB **read-only**; error clearly if missing.
3. Load universe instruments (existing universe loader) → `instr_by_id`.
4. Resolve `quarter` (latest cached if unset).
5. For each id: synthesize `score_row = {"instrument_id": id, "asset_class": <from instr,
   default cn_equity_fund>, "role": role}`; build the populated input via the shared
   `_build_input(...)` helper (DuckDB + provider); load the cached `ActiveFundSnapshot`
   via `load_active_fund_cache(id, quarter, repo_root/"data")`.
6. Call `evaluate_funds(...)`; sort core_dca-first then by state severity.
7. Write the `.md` and `.json` to `--out` (atomic `.tmp.{pid} → os.replace`).
8. Print a one-line summary (`N core_dca / M evaluated`) and return 0.

### 3.4 `_build_input` extraction

`_build_input` currently lives in `opportunity_cmd.py`. To avoid a circular import
(`fund_eval_cmd` ← `opportunity_cmd` pulls a large module), extract `_build_input` (and the
minimal helpers it needs) into a small shared module, e.g.
`src/irc/opportunity/inputs_build.py`, and have `opportunity_cmd` import it from there.
This is a pure move (no behavior change) covered by existing `opportunity_cmd` tests.

### 3.5 Data flow

```
universe yaml ─┐
               ├─► instr ─┐
score_row(synth)┘         ├─ _build_input + populate_inputs(con, provider) ─► OpportunityInput ─┐
data/local.duckdb ────────┘                                                                     │
active_fund/fund_<id>.json ── load_active_fund_cache ─► ActiveFundSnapshot ──────────────────────┤
                                                                                                 ▼
                                          build_opportunity_row(inp, None, snapshot) ─► OpportunityRow
                                                                                                 │
                                                          derive_dca_action(row) ─► dca_action   │
                                                                                                 ▼
                                                                          FundEval ─► md + json report
```

## 4. Component inventory

| File | Kind | Responsibility |
|------|------|----------------|
| `src/irc/opportunity/fund_eval.py` | new, pure | `FundEval`, `evaluate_fund`/`evaluate_funds`, renderers |
| `src/irc/opportunity/inputs_build.py` | new (extracted) | shared `_build_input` (+ minimal helpers) |
| `src/irc/commands/fund_eval_cmd.py` | new, I/O edge | arg parse, DuckDB, universe/snapshot load, write report |
| `src/irc/cli.py` | edit | wire `irc eval-funds` |
| `src/irc/commands/opportunity_cmd.py` | edit | import `_build_input` from `inputs_build` |
| `tests/opportunity/test_fund_eval.py` | new | pure-core + renderer tests |
| `tests/commands/test_fund_eval_cmd.py` | new | integration test (temp DuckDB + cache + universe) |

## 5. Tests (TDD)

Pure core (`test_fund_eval.py`):
- cheap + cold + intact (snapshot yields intact thesis) + acceptable product →
  `opportunity_state == "core_dca"`, `core_dca is True`, `dca_action in {normal_dca, accelerate_dca}`.
- expensive valuation → `pause_wait`, `core_dca is False`.
- `snapshot=None` → thesis falls back, `missing_constituent_snapshot` surfaces in
  `evidence_gaps`, `core_dca is False`.
- insufficient valuation/heat inputs → sub-state `insufficient_evidence`, `core_dca is False`.
- renderer: md contains the core_dca headline list and one table row per fund; json
  round-trips the `FundEval` fields.

Command integration (`test_fund_eval_cmd.py`, no network), mirroring existing
`opportunity_cmd` tests:
- temp DuckDB seeded with minimal `nav_history`/`prices`/`instruments`, a temp
  `active_fund/fund_<id>.json`, and a temp universe yaml → run `run_eval_funds` → assert
  `.md` and `.json` written, with the expected verdict for the seeded fund and a clear
  error when `--db` path is missing.

## 6. Risks and mitigations

- **`_build_input` extraction breaks `opportunity_cmd`** → pure move guarded by the existing
  `opportunity_cmd` test suite; run it green before/after.
- **Funds with no NAV in DuckDB** → valuation/heat resolve to `insufficient_evidence`;
  the command surfaces this and reports `core_dca = False` (honest), never fabricates.
- **Thesis without `theme_report`** (snapshot-only) may be more conservative than the full
  pipeline (which also feeds a metals `theme_report`) → acceptable for v1; loading the
  theme report is a noted future enhancement, not in scope.
- **`fund_metrics` table empty** → product-quality leans on defaults, identical to how the
  already-scored metals funds were handled today; no special-casing.

## 7. Documentation impact

- README: add `irc eval-funds` to the command list (one line under the opportunity area).
- CLAUDE.md "Commands": add the new subcommand line.
- No CONTEXT.md / ADR change (no new domain term or data contract; reuses existing states).

## 8. Sequencing / acceptance criteria

1. (refactor) Extract `_build_input` → `inputs_build.py`; `opportunity_cmd` suite stays green.
2. (red→green) `fund_eval.py` pure core + renderers with the §5 tests.
3. (red→green) `fund_eval_cmd.py` + `cli.py` wiring with the integration test.
4. Docs updated (§7).

**Acceptance:** `uv run irc eval-funds --ids "<15 metals ids>"` writes
`outputs/<today>/fund_eval.{md,json}`; the md lists the `core_dca` funds and a full
sub-state table; `uv run pytest tests/opportunity/test_fund_eval.py
tests/commands/test_fund_eval_cmd.py` and the existing `opportunity_cmd` suite pass;
`ruff check src tests` clean.

## 9. Open questions

- Command name: `irc eval-funds` (proposed) vs `irc opportunity-eval`. Defaulting to
  `eval-funds`; trivially renameable.
- Whether to also load the metals `theme_report` for a richer thesis — deferred (v1 is
  snapshot-only thesis).
