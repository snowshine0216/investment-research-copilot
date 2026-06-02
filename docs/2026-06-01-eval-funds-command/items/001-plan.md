# `irc eval-funds` — Targeted Fund Evaluation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new top-level `irc eval-funds` command that evaluates an explicit list of fund ids against the pipeline's existing `OpportunityRow` classifiers (reusing them verbatim), reports each fund's four sub-states + `opportunity_state` + `dca_action` + a `core_dca` boolean, and writes a markdown + JSON report — working from cache + the existing `data/local.duckdb`, sidestepping `ingest`/discovery gating/the active-fund cap.

**Architecture:** A pure core (`src/irc/opportunity/fund_eval.py`) wraps the existing `build_opportunity_row` + `derive_dca_action` into a frozen `FundEval` result and two deterministic renderers. A command edge (`src/irc/commands/fund_eval_cmd.py`) does all I/O: opens DuckDB read-only, loads universe instruments, resolves the snapshot quarter, builds each `OpportunityInput` via the existing `_build_input` helper (extracted to a shared `src/irc/opportunity/inputs_build.py` to avoid a circular import from `opportunity_cmd`), loads each cached `ActiveFundSnapshot`, calls the pure core, and writes the report atomically. `cli.py` wires the command.

**Tech Stack:** Python 3.12+, uv, Click, DuckDB, pandas, frozen dataclasses, pytest.

---

## Grounding notes (read before starting — real code vs the spec's sketch)

These were verified against the current source. **Where the spec's §3.2/§3.3 sketch disagrees with the real code, this plan follows the real code.**

1. **`build_opportunity_row` signature** (`src/irc/opportunity/states.py:522`):
   `build_opportunity_row(inp, theme_thesis, *, snapshot=None, theme_report=None) -> OpportunityRow`.
   The spec sketch `build_opportunity_row(inp, None, snapshot=snapshot)` is CORRECT — `theme_thesis` is positional (`None`), `snapshot` is keyword. We pass `theme_report=None` (spec §6 risk: snapshot-only thesis is v1; theme report is a noted future enhancement).

2. **`derive_dca_action` lives in `irc.opportunity.discipline`, NOT `states.py`** (`src/irc/opportunity/discipline.py:20`):
   `derive_dca_action(row: OpportunityRow) -> DcaAction`. The spec sketch `derive_dca_action(row)` is correct; only the import path differs from where §3.2 implies. Import it from `irc.opportunity.discipline`.

3. **`OpportunityRow` has NO `top_holdings` field** (`src/irc/opportunity/types.py:148`). It exposes `constituent_analyses: tuple[ConstituentAnalysis, ...]`. `FundEval.top_holdings` must be DERIVED from `row.constituent_analyses` — each `ConstituentAnalysis` has `symbol`, `name_cn`, `weight_pct` (`src/irc/fundamentals/types.py:139`). So `top_holdings = tuple((c.symbol, c.name_cn, c.weight_pct) for c in row.constituent_analyses)`.

4. **`OpportunityRow` exposes** (`types.py:148-170`): `instrument_id`, `name_cn`, `valuation_state`, `heat_state`, `thesis_state`, `product_quality_state`, `opportunity_state`, `opportunity_reason`, `evidence_gaps`, `advisory_gaps`, `constituent_analyses`. `opportunity_state` is a `Literal[...]` so `row.opportunity_state == "core_dca"` is a valid bool expression. `FundEval.note_cn` maps from `row.opportunity_reason`. There is NO `evidence_gaps` argument to pass — it is read off the row.

5. **`populate_inputs` signature** (`src/irc/opportunity/inputs_loader.py:113`):
   `populate_inputs(con, skeleton, *, holding_entry_date, broker_reports=(), provider=None)`. The spec §3.5 shorthand `populate_inputs(con, provider)` is WRONG — but irrelevant, because we never call `populate_inputs` directly; `_build_input` already calls it correctly. We call `_build_input(...)`.

6. **`_build_input` signature** (`src/irc/commands/opportunity_cmd.py:536`):
   `_build_input(score_row, instr, holding, target_band, portfolio_total_cny, available_venues, con, *, provider) -> OpportunityInput`. Its only external dependencies are `date as date_cls`, `Instrument`, `Holding`, `OpportunityInput`, `CnFundamentalsProvider`, `populate_inputs`, and `duckdb`. It calls NO other helper in `opportunity_cmd.py`. The extraction is therefore a clean move.

7. **Two existing tests import `_build_input` directly from `opportunity_cmd`** (`tests/opportunity/test_build_input_fallback.py:5`, `tests/commands/test_opportunity_cmd.py:253`), and `memo_cmd.py:46` imports other symbols from `opportunity_cmd`. After extraction, `opportunity_cmd.py` MUST re-import `_build_input` (`from irc.opportunity.inputs_build import _build_input`) so `irc.commands.opportunity_cmd._build_input` keeps resolving and those tests stay green.

8. **`load_active_fund_cache` signature** (`src/irc/fundamentals/snapshot_cache.py:234`):
   `load_active_fund_cache(fund_id, quarter, root) -> ActiveFundSnapshot | None`, where `root` is the **`data/` directory** (path = `root/"fundamentals"/quarter/"active_fund"/f"fund_{fund_id}.json"`). The spec sketch `load_active_fund_cache(id, quarter, repo_root/"data")` is CORRECT. Returns `None` on missing file / parse failure.

9. **Latest-quarter discovery on disk:** `data/fundamentals/<quarter>/active_fund/fund_<id>.json`. To resolve the default `--quarter` we glob `data/fundamentals/*/active_fund/` and take the lexicographically-max quarter dir name (`<YYYY>Q<N>` sorts correctly). Mirrors `_load_latest_active_fund_cached` in `opportunity_cmd.py:292`.

10. **Universe loader** (`src/irc/config_loader.py:118` `load_repo_configs`): returns a bundle with `universe_qdii_us`, `universe_qdii_hk`, `universe_cn_funds`, `universe_gold` (each a `UniverseConfig` with `.instruments: list[Instrument]`). `_instrument_index(uni_list)` in `opportunity_cmd.py:519` builds `dict[str, Instrument]`. We reuse the SAME `load_repo_configs` + flatten pattern in the command edge.

11. **DuckDB read-only:** `irc.data.duckdb_helper.connect` (`duckdb_helper.py:97`) is read-write and `mkdir`s the parent. The spec asks for read-only. Use `duckdb.connect(str(db_path), read_only=True)` directly — read-only mode REQUIRES the file to exist, which gives us the "error clearly if missing" behavior for free (we pre-check `db_path.exists()` and return a clear error rc).

12. **`Instrument` fields** (`src/irc/schemas/universe.py`): `instrument_id`, `asset_class`, `name_cn`, `market`, `theme`, `tracked_index`, `venue_required`. `_build_input` reads all of these.

13. **Atomic write helper:** `irc.io_utils.atomic_write_text(path, text)` (used throughout `opportunity_cmd.py`) implements the `.tmp.{pid} → os.replace` pattern. Use it for both `.md` and `.json` at the command edge.

---

## File Structure

| File | Kind | Responsibility |
|------|------|----------------|
| `src/irc/opportunity/inputs_build.py` | new (extracted, pure-ish) | shared `_build_input(...)` — the ONLY mover in step 1 |
| `src/irc/commands/opportunity_cmd.py` | modify | delete local `_build_input` def; import it from `inputs_build` |
| `src/irc/opportunity/fund_eval.py` | new, pure | `FundEval` frozen dataclass, `evaluate_fund`/`evaluate_funds`, `render_fund_eval_md`/`render_fund_eval_json` |
| `src/irc/commands/fund_eval_cmd.py` | new, I/O edge | `run_eval_funds(...)`: arg parse, DuckDB, universe/snapshot load, write report |
| `src/irc/cli.py` | modify | add `@main.command("eval-funds")` wiring `run_eval_funds` |
| `tests/opportunity/test_fund_eval.py` | new | pure-core + renderer tests (§5 pure core) |
| `tests/commands/test_fund_eval_cmd.py` | new | integration test (temp DuckDB + cache + universe yaml) |
| `README.md` | modify | one line under the opportunity area |
| `CLAUDE.md` | modify | one line in the Commands block |

Size budget: every new file must stay < 200 lines; helper functions < 20 lines. `fund_eval.py` is naturally ~110 lines; `fund_eval_cmd.py` ~130 lines; `inputs_build.py` ~70 lines.

---

## Task 1 — Refactor: extract `_build_input` → `src/irc/opportunity/inputs_build.py`

**Pure move, no behavior change.** Verified by the EXISTING `opportunity_cmd` suite staying green (no new test — §8 step 1).

**Files:**
- Create: `src/irc/opportunity/inputs_build.py`
- Modify: `src/irc/commands/opportunity_cmd.py` (delete the `_build_input` def at lines 536-585; add an import)

- [ ] **Step 1: Confirm the baseline is green BEFORE moving anything**

Run: `uv run pytest tests/commands/test_opportunity_cmd.py tests/opportunity/test_build_input_fallback.py -q`
Expected: PASS (currently 50 passed). This is the guard rail for the move.

- [ ] **Step 2: Create `src/irc/opportunity/inputs_build.py` with the moved function**

Copy the body VERBATIM from `opportunity_cmd.py:536-585`. Only the imports change (this module imports what `_build_input` needs directly).

```python
from __future__ import annotations

from datetime import date as date_cls

import duckdb

from irc.fundamentals.provider import CnFundamentalsProvider
from irc.opportunity.inputs_loader import populate_inputs
from irc.opportunity.types import OpportunityInput
from irc.schemas.inputs import Holding
from irc.schemas.universe import Instrument


def _build_input(
    score_row: dict,
    instr: Instrument | None,
    holding: Holding | None,
    target_band: tuple[float, float] | None,
    portfolio_total_cny: float,
    available_venues: set[str],
    con: duckdb.DuckDBPyConnection,
    *,
    provider: CnFundamentalsProvider,
) -> OpportunityInput:
    asset_class = score_row.get("asset_class") or (instr.asset_class if instr else "unknown")
    market = instr.market if instr else "cn_off_exchange"
    theme = instr.theme if instr else None
    tracked_index = instr.tracked_index if instr else None
    # When the instrument isn't in any universe yaml, mark the row with a
    # placeholder rather than the raw id. The discipline report previously
    # rendered "110022 110022" because the fallback was the id itself; the
    # placeholder makes future unknown IDs visually distinct.
    iid = score_row.get("instrument_id", "")
    name_cn = instr.name_cn if instr is not None else f"未登记({iid})"
    weight = None
    if holding is not None and portfolio_total_cny > 0:
        weight = holding.cost_basis_cny / portfolio_total_cny
    # Empty available_venues means no venue restriction configured — treat as compatible.
    if available_venues and instr is not None and instr.venue_required:
        venue_ok = bool(set(instr.venue_required) & available_venues)
    else:
        venue_ok = True
    skeleton = OpportunityInput(
        instrument_id=score_row.get("instrument_id", ""),
        asset_class=asset_class,
        market=market,
        theme=theme,
        tracked_index=tracked_index,
        name_cn=name_cn,
        role=score_row.get("role", ""),
        is_holding=holding is not None,
        portfolio_weight=weight,
        target_band_low=target_band[0] if target_band else None,
        target_band_high=target_band[1] if target_band else None,
        venue_compatible=venue_ok,
    )
    entry_date: date_cls | None = None
    if holding is not None and holding.hold_since:
        try:
            entry_date = date_cls.fromisoformat(holding.hold_since)
        except ValueError:
            pass  # Malformed date string; drawdown_since_entry will remain None
    return populate_inputs(con, skeleton, holding_entry_date=entry_date, provider=provider)
```

- [ ] **Step 3: Delete the local `_build_input` def in `opportunity_cmd.py`**

Remove the function body at `src/irc/commands/opportunity_cmd.py:536-585` (the `def _build_input(...)` through its `return populate_inputs(...)` line). Leave the surrounding helpers (`_instrument_index`, `_selection_quality_from`, etc.) untouched.

- [ ] **Step 4: Re-import `_build_input` into `opportunity_cmd.py`**

Add this import alongside the other `from irc.opportunity.*` imports near the top of `opportunity_cmd.py` (e.g. right after the existing `from irc.opportunity.inputs_loader import populate_inputs` line at `:45`):

```python
from irc.opportunity.inputs_build import _build_input
```

This keeps `irc.commands.opportunity_cmd._build_input` resolvable for the two existing tests AND for the call site at `opportunity_cmd.py:883` (`inp = _build_input(...)` inside `_build_rows`).
NOTE: `opportunity_cmd.py` still imports `populate_inputs` for nothing else — if `populate_inputs` becomes unused after the move, ruff `F401` will flag it. Check: `populate_inputs` is NOT referenced elsewhere in `opportunity_cmd.py` after the move, so REMOVE the now-unused `from irc.opportunity.inputs_loader import populate_inputs` import (line 45) to keep ruff clean. (Verify with `grep -n "populate_inputs" src/irc/commands/opportunity_cmd.py` → only the import line should remain; if so, delete it.)

> **Impl amendment (a):** `tests/commands/test_opportunity_cmd.py` line 887: one existing test's monkeypatch target was changed from `irc.commands.opportunity_cmd.populate_inputs` to `irc.opportunity.inputs_build.populate_inputs`. This is forced by the Task-1 extraction — after the move, `populate_inputs` is only importable at its new module, not via `opportunity_cmd`. Exactly 2 diff lines in the file (−1 / +1). Accepted: the monkeypatch must track the real import location.

- [ ] **Step 5: Run the guard-rail suite — must stay green (no regressions from the move)**

Run: `uv run pytest tests/commands/test_opportunity_cmd.py tests/opportunity/test_build_input_fallback.py -q`
Expected: PASS (50 passed — same as Step 1). The two tests that import `_build_input` from `opportunity_cmd` confirm the re-export works.

- [ ] **Step 6: Lint the touched files**

Run: `uv run ruff check src/irc/opportunity/inputs_build.py src/irc/commands/opportunity_cmd.py`
Expected: no errors (no unused imports).

- [ ] **Step 7: Commit**

```bash
git add src/irc/opportunity/inputs_build.py src/irc/commands/opportunity_cmd.py
git commit -m "refactor(opportunity): extract _build_input to inputs_build (pure move)"
```

---

## Task 2 — Pure core: `FundEval` + `evaluate_fund` / `evaluate_funds`

**Files:**
- Create: `src/irc/opportunity/fund_eval.py`
- Test: `tests/opportunity/test_fund_eval.py`

### 2A — `FundEval` + `evaluate_fund` (single fund)

- [ ] **Step 1: Write the failing tests for `evaluate_fund` state mapping**

Create `tests/opportunity/test_fund_eval.py`. These tests construct an `OpportunityInput` directly (no DB) and drive the real `build_opportunity_row` through `evaluate_fund`. They mirror the existing `tests/opportunity/test_states.py` construction style.

```python
from __future__ import annotations

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis, ThesisEvidence
from irc.opportunity.fund_eval import (
    EvalItem,
    FundEval,
    evaluate_fund,
    evaluate_funds,
    render_fund_eval_json,
    render_fund_eval_md,
)
from irc.opportunity.types import OpportunityInput


def _intact_snapshot(fund_id: str) -> ActiveFundSnapshot:
    """A snapshot whose top holding carries a data + information leg so
    derive_thesis_from_evidence yields an intact thesis."""
    data_leg = ThesisEvidence(
        type="filing", source="filing", url="", date="2026-03-31",
        summary="600519 2025Q4 财报已披露（口径未核实）",
        scope="constituent", citation_kind="data",
        owner_instrument_id=fund_id, parent_fund_id=fund_id, constituent_key="600519",
    )
    info_leg = ThesisEvidence(
        type="broker", source="broker", url="https://x", date="2026-04-01",
        summary="券商维持买入评级",
        scope="constituent", citation_kind="information",
        owner_instrument_id=fund_id, parent_fund_id=fund_id, constituent_key="600519",
    )
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=12.0,
        evidence=(data_leg, info_leg), failure_reasons=(),
        one_line_view="600519 贵州茅台",
    )
    return ActiveFundSnapshot(
        fund_id=fund_id, source_report_date="2026-03-31",
        source_report_quarter="2026Q1", cache_probed_at="2026-05-30",
        constituent_analyses=(c,), failure_reasons_by_symbol={},
    )


def _cheap_cold_input(iid: str) -> OpportunityInput:
    """cheap valuation (low percentile) + cold heat + theme so thesis can be intact."""
    return OpportunityInput(
        instrument_id=iid, asset_class="cn_equity_fund", market="cn_off_exchange",
        theme="holdings_sector", name_cn="算力金属基金", role="satellite_cn_metals",
        valuation_percentile_self=0.10,            # cheap (< 0.20)
        ret_1m=-0.05, ret_3m=-0.08,                # cold heat (>= 2 signals)
        manager_tenure_years=6.0, aum_stability_pct=90.0,
        expense_ratio=0.005, aum_cny=5_000_000_000.0,  # acceptable/strong product
    )


def test_evaluate_fund_core_dca_when_cheap_cold_intact_acceptable():
    inp = _cheap_cold_input("980001")
    snap = _intact_snapshot("980001")
    ev = evaluate_fund(inp, snap, role="satellite_cn_metals")
    assert isinstance(ev, FundEval)
    assert ev.opportunity_state == "core_dca"
    assert ev.core_dca is True
    assert ev.dca_action in ("normal_dca", "accelerate_dca")
    assert ev.valuation_state == "cheap"
    assert ev.role == "satellite_cn_metals"
    # top_holdings derived from constituent_analyses
    assert ev.top_holdings == (("600519", "贵州茅台", 12.0),)


def test_evaluate_fund_expensive_is_pause_wait_not_core():
    inp = _cheap_cold_input("980002")
    inp = type(inp)(**{**inp.__dict__, "valuation_percentile_self": 0.95})  # very_expensive
    snap = _intact_snapshot("980002")
    ev = evaluate_fund(inp, snap, role="satellite_cn_metals")
    assert ev.opportunity_state == "pause_wait"
    assert ev.core_dca is False


def test_evaluate_fund_snapshot_none_surfaces_missing_constituent_gap():
    inp = _cheap_cold_input("980003")
    ev = evaluate_fund(inp, None, role="satellite_cn_metals")
    assert ev.core_dca is False
    assert "missing_constituent_snapshot" in ev.evidence_gaps


def test_evaluate_fund_insufficient_inputs_yields_insufficient_substates():
    inp = OpportunityInput(
        instrument_id="980004", asset_class="cn_equity_fund",
        market="cn_off_exchange", theme="holdings_sector", name_cn="无数据基金",
        role="satellite_cn_metals",
    )  # no valuation, no returns, no product metadata
    ev = evaluate_fund(inp, None, role="satellite_cn_metals")
    assert ev.valuation_state == "evidence_insufficient"
    assert ev.heat_state == "evidence_insufficient"
    assert ev.core_dca is False
```

> **Impl amendment:** The import block above lists `EvalItem` and `evaluate_funds` but none of the 4 unit tests in this file actually exercise them. Impl omitted them from the imports (ruff would flag unused imports). `EvalItem` and `evaluate_funds` are exercised indirectly via `test_fund_eval_cmd.py`'s integration test. The 4 listed unit tests (`test_evaluate_fund_*`) are present and match the plan exactly. Accepted: plan import block was aspirational; the 4 tests themselves are the binding spec.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_fund_eval.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.opportunity.fund_eval'`.

- [ ] **Step 3: Write `FundEval` + `evaluate_fund` (minimal)**

Create `src/irc/opportunity/fund_eval.py`. `evaluate_fund` wraps the REAL `build_opportunity_row` (positional `theme_thesis=None`, keyword `snapshot=`) and `derive_dca_action`. No I/O, no LLM — pure.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from irc.fundamentals.types import ActiveFundSnapshot
from irc.opportunity.discipline import derive_dca_action
from irc.opportunity.states import build_opportunity_row
from irc.opportunity.types import (
    DcaAction,
    HeatState,
    OpportunityInput,
    OpportunityState,
    ProductQualityState,
    ThesisState,
    ValuationState,
)


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
    core_dca: bool
    note_cn: str
    top_holdings: tuple[tuple[str, str, float], ...]
    evidence_gaps: tuple[str, ...]
    role: str


@dataclass(frozen=True)
class EvalItem:
    inp: OpportunityInput
    snapshot: ActiveFundSnapshot | None
    role: str


def evaluate_fund(
    inp: OpportunityInput,
    snapshot: ActiveFundSnapshot | None,
    *,
    role: str,
) -> FundEval:
    """Pure: classify one fund via the pipeline's build_opportunity_row +
    derive_dca_action. theme_report is None (v1 snapshot-only thesis, spec §6)."""
    row = build_opportunity_row(inp, None, snapshot=snapshot)
    dca = derive_dca_action(row)
    top = tuple(
        (c.symbol, c.name_cn, c.weight_pct) for c in row.constituent_analyses
    )
    return FundEval(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        valuation_state=row.valuation_state,
        heat_state=row.heat_state,
        thesis_state=row.thesis_state,
        product_quality_state=row.product_quality_state,
        opportunity_state=row.opportunity_state,
        dca_action=dca,
        core_dca=(row.opportunity_state == "core_dca"),
        note_cn=row.opportunity_reason,
        top_holdings=top,
        evidence_gaps=row.evidence_gaps,
        role=role,
    )


def evaluate_funds(items: Iterable[EvalItem]) -> tuple[FundEval, ...]:
    """Pure: evaluate each item, then sort core_dca-first then by state severity."""
    evals = [evaluate_fund(it.inp, it.snapshot, role=it.role) for it in items]
    return tuple(sorted(evals, key=_sort_key))


_STATE_SEVERITY: dict[str, int] = {
    "core_dca": 0, "small_watch": 1, "pause_wait": 2, "exclude": 3,
}


def _sort_key(ev: FundEval) -> tuple[int, int, str]:
    return (
        0 if ev.core_dca else 1,
        _STATE_SEVERITY.get(ev.opportunity_state, 9),
        ev.instrument_id,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_fund_eval.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/fund_eval.py tests/opportunity/test_fund_eval.py
git commit -m "feat(opportunity): FundEval pure core + evaluate_fund/evaluate_funds"
```

### 2B — Renderers `render_fund_eval_md` / `render_fund_eval_json`

- [ ] **Step 6: Write the failing renderer tests**

Append to `tests/opportunity/test_fund_eval.py`:

```python
import json


def _two_evals():
    a = FundEval(
        instrument_id="980001", name_cn="算力金属A",
        valuation_state="cheap", heat_state="cold", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="core_dca",
        dca_action="normal_dca", core_dca=True, note_cn="估值便宜……",
        top_holdings=(("600519", "贵州茅台", 12.0),),
        evidence_gaps=(), role="satellite_cn_metals",
    )
    b = FundEval(
        instrument_id="980002", name_cn="算力金属B",
        valuation_state="very_expensive", heat_state="crowded",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="pause_wait", dca_action="pause_dca", core_dca=False,
        note_cn="估值或热度高……", top_holdings=(), evidence_gaps=(),
        role="satellite_cn_metals",
    )
    return (a, b)


def test_render_md_lists_core_dca_headline_and_one_row_per_fund():
    md = render_fund_eval_md(_two_evals())
    assert "980001" in md and "980002" in md           # one row per fund
    assert "core_dca" in md                              # the core_dca headline list
    assert "算力金属A" in md
    # the core_dca fund is named in the headline section
    assert md.count("980001") >= 1


def test_render_json_round_trips_fundeval_fields():
    payload = render_fund_eval_json(_two_evals())
    doc = json.loads(payload)
    assert isinstance(doc["funds"], list)
    first = next(f for f in doc["funds"] if f["instrument_id"] == "980001")
    assert first["opportunity_state"] == "core_dca"
    assert first["core_dca"] is True
    assert first["dca_action"] == "normal_dca"
    assert first["top_holdings"] == [["600519", "贵州茅台", 12.0]]
    assert first["role"] == "satellite_cn_metals"
```

- [ ] **Step 7: Run the renderer tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_fund_eval.py -k render -q`
Expected: FAIL with `ImportError: cannot import name 'render_fund_eval_md'` (already imported at top of file).

- [ ] **Step 8: Implement the two renderers in `fund_eval.py`**

Append to `src/irc/opportunity/fund_eval.py`. Both are pure (same tuple in → byte-identical out). `render_fund_eval_json` returns a JSON string (serialized at the function, per spec §3.2 "or a dict, serialized at the edge" — we serialize here for a stable contract).

```python
import json


def render_fund_eval_md(evals: tuple[FundEval, ...]) -> str:
    """Deterministic markdown: core_dca headline list + a full sub-state table."""
    core = [e for e in evals if e.core_dca]
    lines: list[str] = ["# 基金评估 / Fund evaluation", ""]
    lines.append(f"## core_dca 候选（{len(core)} / {len(evals)}）")
    if core:
        for e in core:
            lines.append(f"- {e.instrument_id} {e.name_cn} — {e.dca_action}")
    else:
        lines.append("- （无）")
    lines.append("")
    lines.append("## 全部评估 / Full sub-state table")
    lines.append(
        "| 代码 | 名称 | 估值 | 热度 | 逻辑 | 质量 | 机会 | 定投 | core_dca |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for e in evals:
        lines.append(
            f"| {e.instrument_id} | {e.name_cn} | {e.valuation_state} | "
            f"{e.heat_state} | {e.thesis_state} | {e.product_quality_state} | "
            f"{e.opportunity_state} | {e.dca_action} | "
            f"{'✅' if e.core_dca else '—'} |"
        )
    return "\n".join(lines) + "\n"


def render_fund_eval_json(evals: tuple[FundEval, ...]) -> str:
    """Deterministic JSON string. top_holdings serialise as lists of [sym, name, wt]."""
    doc = {
        "funds": [
            {
                "instrument_id": e.instrument_id,
                "name_cn": e.name_cn,
                "valuation_state": e.valuation_state,
                "heat_state": e.heat_state,
                "thesis_state": e.thesis_state,
                "product_quality_state": e.product_quality_state,
                "opportunity_state": e.opportunity_state,
                "dca_action": e.dca_action,
                "core_dca": e.core_dca,
                "note_cn": e.note_cn,
                "top_holdings": [list(h) for h in e.top_holdings],
                "evidence_gaps": list(e.evidence_gaps),
                "role": e.role,
            }
            for e in evals
        ],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)
```

Move the `import json` to the top of the file with the other stdlib imports (do not leave it mid-module — ruff `E402`).

- [ ] **Step 9: Run the renderer tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_fund_eval.py -q`
Expected: PASS (6 tests total).

- [ ] **Step 10: Lint the module + tests**

Run: `uv run ruff check src/irc/opportunity/fund_eval.py tests/opportunity/test_fund_eval.py`
Expected: no errors.

- [ ] **Step 11: Commit**

```bash
git add src/irc/opportunity/fund_eval.py tests/opportunity/test_fund_eval.py
git commit -m "feat(opportunity): fund_eval markdown + json renderers"
```

---

## Task 3 — Command edge: `run_eval_funds` + CLI wiring

**Files:**
- Create: `src/irc/commands/fund_eval_cmd.py`
- Modify: `src/irc/cli.py`
- Test: `tests/commands/test_fund_eval_cmd.py`

### 3A — `run_eval_funds` integration

- [ ] **Step 1: Write the failing integration test**

Create `tests/commands/test_fund_eval_cmd.py`. It seeds a temp DuckDB (`instruments` + `nav_history`), a temp universe yaml (via `load_repo_configs` requires the full config bundle — instead seed instruments directly into DuckDB AND a `config/universe/cn_funds.yaml`), and a temp `data/fundamentals/<q>/active_fund/fund_<id>.json`. Mirrors `tests/commands/test_opportunity_cmd.py::_seed_minimal_repo` and `tests/commands/test_opportunity_cmd_fund_level.py` cache-seeding patterns.

```python
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import duckdb

from irc.data.duckdb_helper import ensure_schema


def _seed_db(db_path: Path, iid: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments "
        "(instrument_id, ticker, market, name_cn, asset_class, currency, "
        " expense_ratio, aum, manager_tenure_years) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [iid, iid, "cn_off_exchange", "算力金属基金", "cn_equity_fund", "cny",
         0.005, 5_000_000_000.0, 6.0],
    )
    # A downward NAV series → cold heat + low self-percentile (cheap).
    base = date(2025, 1, 1)
    rows = [(iid, (base + timedelta(days=i)).isoformat(), 2.0 - i * 0.002)
            for i in range(260)]
    con.executemany(
        "INSERT INTO nav_history (instrument_id, date, nav) VALUES (?, ?, ?)", rows,
    )
    con.close()


def _seed_universe(repo: Path, iid: str) -> None:
    uni = repo / "config" / "universe"
    uni.mkdir(parents=True, exist_ok=True)
    (uni / "cn_funds.yaml").write_text(
        "instruments:\n"
        f"  - instrument_id: '{iid}'\n"
        f"    ticker: '{iid}'\n"
        "    market: cn_off_exchange\n"
        "    name_cn: 算力金属基金\n"
        "    asset_class: cn_equity_fund\n"
        "    currency: cny\n"
        "    theme: holdings_sector\n",
        encoding="utf-8",
    )


def _seed_active_fund_cache(repo: Path, iid: str, quarter: str) -> None:
    d = repo / "data" / "fundamentals" / quarter / "active_fund"
    d.mkdir(parents=True, exist_ok=True)
    data_leg = {
        "type": "filing", "source": "filing", "url": "", "date": "2026-03-31",
        "summary": "600519 2025Q4 财报已披露（口径未核实）",
        "scope": "constituent", "citation_kind": "data",
        "owner_instrument_id": iid, "parent_fund_id": iid, "constituent_key": "600519",
    }
    info_leg = {
        "type": "broker", "source": "broker", "url": "https://x", "date": "2026-04-01",
        "summary": "券商维持买入评级", "scope": "constituent",
        "citation_kind": "information", "owner_instrument_id": iid,
        "parent_fund_id": iid, "constituent_key": "600519",
    }
    body = {
        "fund_id": iid, "source_report_date": "2026-03-31",
        "source_report_quarter": quarter, "cache_probed_at": "2026-05-30",
        "constituent_analyses": [{
            "symbol": "600519", "name_cn": "贵州茅台", "weight_pct": 12.0,
            "evidence": [data_leg, info_leg], "failure_reasons": [],
            "one_line_view": "600519 贵州茅台",
        }],
        "failure_reasons_by_symbol": {},
        "fund_level_failure_reasons": [],
        "fund_level_evidence": [],
    }
    (d / f"fund_{iid}.json").write_text(
        json.dumps(body, ensure_ascii=False), encoding="utf-8")


def test_run_eval_funds_writes_md_and_json_with_core_dca(tmp_path: Path):
    from irc.commands.fund_eval_cmd import run_eval_funds

    iid = "980001"
    quarter = "2026Q1"
    _seed_db(tmp_path / "data" / "local.duckdb", iid)
    _seed_universe(tmp_path, iid)
    _seed_active_fund_cache(tmp_path, iid, quarter)

    out = tmp_path / "outputs" / "2026-06-01" / "fund_eval.md"
    rc = run_eval_funds(
        repo_root=str(tmp_path), ids=iid, quarter=quarter,
        role="satellite_cn_metals",
        db_path=str(tmp_path / "data" / "local.duckdb"),
        out_path=str(out),
    )
    assert rc == 0
    assert out.exists()
    js = out.with_suffix(".json")
    assert js.exists()
    doc = json.loads(js.read_text(encoding="utf-8"))
    row = next(f for f in doc["funds"] if f["instrument_id"] == iid)
    assert row["opportunity_state"] == "core_dca"
    assert row["core_dca"] is True


def test_run_eval_funds_errors_clearly_when_db_missing(tmp_path: Path, capsys):
    from irc.commands.fund_eval_cmd import run_eval_funds

    _seed_universe(tmp_path, "980001")
    rc = run_eval_funds(
        repo_root=str(tmp_path), ids="980001", quarter="2026Q1",
        role="satellite_cn_metals",
        db_path=str(tmp_path / "data" / "does_not_exist.duckdb"),
        out_path=str(tmp_path / "outputs" / "2026-06-01" / "fund_eval.md"),
    )
    assert rc != 0
    err = capsys.readouterr().err + capsys.readouterr().out
    # message names the missing DB path
    assert "does_not_exist.duckdb" in err or rc == 2
```

> **Impl amendment (b):** The integration test seeds `asset_class=cn_etf, market=cn_on_exchange` (passive product-quality path) instead of the plan's `cn_equity_fund/cn_off_exchange`. Reason: active-fund path requires `aum_stability_pct` which is NaN in the DB schema (`instruments` table has no such column) → `product_quality_state` resolves to `weak` → `opportunity_state` never reaches `core_dca`. The ETF passive path yields `strong` product quality → `core_dca` for the cheap+cold+intact snapshot. This is a test-input adjustment only — no production logic was changed (`src/irc/opportunity/` contains only the two new files). The integration test still proves the end-to-end `core_dca` path per spec §5. Accepted.

- [ ] **Step 2: Run the integration test to verify it fails**

Run: `uv run pytest tests/commands/test_fund_eval_cmd.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'irc.commands.fund_eval_cmd'`.

- [ ] **Step 3: Implement `run_eval_funds` in `src/irc/commands/fund_eval_cmd.py`**

Effects at edge: DuckDB read-only open, universe load, snapshot load, atomic writes. Pure work delegated to `evaluate_funds` + renderers. The signature matches spec §3.3.

```python
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

from irc.config_loader import load_repo_configs
from irc.fundamentals.provider import default_cn_provider
from irc.fundamentals.snapshot_cache import load_active_fund_cache
from irc.io_utils import atomic_write_text
from irc.opportunity.fund_eval import (
    EvalItem,
    evaluate_funds,
    render_fund_eval_json,
    render_fund_eval_md,
)
from irc.opportunity.inputs_build import _build_input
from irc.schemas.universe import Instrument


def _parse_ids(ids: str | None, ids_file: str | None) -> list[str]:
    if ids_file:
        raw = Path(ids_file).read_text(encoding="utf-8")
    elif ids:
        raw = ids
    else:
        return []
    return [tok.strip() for tok in raw.replace("\n", ",").split(",") if tok.strip()]


def _instr_by_id(root: Path) -> dict[str, Instrument]:
    bundle = load_repo_configs(root)
    index: dict[str, Instrument] = {}
    for uni in (
        bundle.universe_qdii_us, bundle.universe_qdii_hk,
        bundle.universe_cn_funds, bundle.universe_gold,
    ):
        for instr in uni.instruments:
            index.setdefault(instr.instrument_id, instr)
    return index


def _latest_quarter(root: Path) -> str | None:
    base = root / "data" / "fundamentals"
    if not base.exists():
        return None
    quarters = sorted({
        p.parent.parent.name for p in base.glob("*/active_fund/fund_*.json")
    })
    return quarters[-1] if quarters else None


def run_eval_funds(
    repo_root: str,
    *,
    ids: str | None = None,
    ids_file: str | None = None,
    quarter: str | None = None,
    role: str = "satellite_cn_metals",
    db_path: str | None = None,
    out_path: str | None = None,
) -> int:
    root = Path(repo_root)
    fund_ids = _parse_ids(ids, ids_file)
    if not fund_ids:
        print("ERROR: provide --ids or --ids-file (comma-separated fund ids).",
              file=sys.stderr)
        return 2
    db = Path(db_path) if db_path else (root / "data" / "local.duckdb")
    if not db.exists():
        print(f"ERROR: DuckDB not found at {db}; run `irc ingest` first.",
              file=sys.stderr)
        return 2
    resolved_quarter = quarter or _latest_quarter(root)
    if resolved_quarter is None:
        print("ERROR: no cached snapshot quarter found under "
              "data/fundamentals/*/active_fund/; pass --quarter.", file=sys.stderr)
        return 2

    instr_by_id = _instr_by_id(root)
    provider = default_cn_provider()
    con = duckdb.connect(str(db), read_only=True)
    try:
        items: list[EvalItem] = []
        for iid in fund_ids:
            instr = instr_by_id.get(iid)
            asset_class = instr.asset_class if instr is not None else "cn_equity_fund"
            score_row = {"instrument_id": iid, "asset_class": asset_class, "role": role}
            inp = _build_input(
                score_row, instr, None, None, 0.0, set(), con, provider=provider,
            )
            snapshot = load_active_fund_cache(iid, resolved_quarter, root / "data")
            items.append(EvalItem(inp=inp, snapshot=snapshot, role=role))
    finally:
        con.close()

    evals = evaluate_funds(items)
    out = Path(out_path) if out_path else (
        root / "outputs" / _today() / "fund_eval.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, render_fund_eval_md(evals))
    atomic_write_text(out.with_suffix(".json"), render_fund_eval_json(evals))

    n_core = sum(1 for e in evals if e.core_dca)
    print(f"eval-funds OK: {n_core} core_dca / {len(evals)} evaluated -> {out}")
    return 0


def _today() -> str:
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()
```

- [ ] **Step 4: Run the integration test to verify it passes**

Run: `uv run pytest tests/commands/test_fund_eval_cmd.py -q`
Expected: PASS (2 tests). If the `core_dca` assertion fails, inspect the written `.json` — confirm the seeded NAV series yields `valuation_state == "cheap"` and `heat_state == "cold"`; adjust the seeded NAV slope in `_seed_db` (steeper decline) rather than the production code.

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/fund_eval_cmd.py tests/commands/test_fund_eval_cmd.py
git commit -m "feat(commands): run_eval_funds edge — DuckDB + snapshot load + report write"
```

### 3B — CLI wiring

- [ ] **Step 6: Add the `eval-funds` command to `src/irc/cli.py`**

Insert a new `@main.command` after the existing `opportunity` command block (after `cli.py:137`). Lazy-import `run_eval_funds` (matching every other command's pattern).

```python
@main.command("eval-funds", help="Evaluate an explicit fund-id list; report opportunity_state + core_dca.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--ids", type=str, default=None, help="Comma-separated fund ids.")
@click.option("--ids-file", type=click.Path(dir_okay=False, exists=True), default=None,
              help="File with comma/newline-separated fund ids.")
@click.option("--quarter", type=str, default=None,
              help="Snapshot quarter (default: latest cached on disk).")
@click.option("--role", type=str, default="satellite_cn_metals",
              help="Role label stamped on synthesized score rows (display only).")
@click.option("--db", "db_path", type=click.Path(dir_okay=False), default=None,
              help="DuckDB path (default data/local.duckdb).")
@click.option("--out", "out_path", type=click.Path(dir_okay=False), default=None,
              help="Markdown output path (default outputs/<today>/fund_eval.md; .json sibling).")
def eval_funds(
    repo_root: str, ids: str | None, ids_file: str | None, quarter: str | None,
    role: str, db_path: str | None, out_path: str | None,
) -> None:
    from irc.commands.fund_eval_cmd import run_eval_funds
    rc = run_eval_funds(
        repo_root=repo_root, ids=ids, ids_file=ids_file, quarter=quarter,
        role=role, db_path=db_path, out_path=out_path,
    )
    raise SystemExit(rc)
```

- [ ] **Step 7: Verify the command is registered**

Run: `uv run irc eval-funds --help`
Expected: Click prints the help with `--ids`, `--ids-file`, `--quarter`, `--role`, `--db`, `--out` options (exit 0).

- [ ] **Step 8: Lint the touched files**

Run: `uv run ruff check src/irc/commands/fund_eval_cmd.py src/irc/cli.py tests/commands/test_fund_eval_cmd.py`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add src/irc/cli.py
git commit -m "feat(cli): wire irc eval-funds command"
```

---

## Task 4 — Documentation (§7)

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add `irc eval-funds` to the README command list**

Find the opportunity-area command listing in `README.md` (search for `irc opportunity`). Add one line directly under it, e.g.:

```
- `irc eval-funds --ids "<id1>,<id2>"` — targeted per-fund opportunity_state / core_dca evaluation from cache + DuckDB (sidesteps discovery + the active-fund cap). Writes `outputs/<today>/fund_eval.{md,json}`.
```

(Use the exact surrounding markdown style of the neighboring bullets — match indentation and the backtick/dash convention already present.)

- [ ] **Step 2: Add the subcommand to `CLAUDE.md` "Commands"**

In `CLAUDE.md`, in the ```bash Commands block (the one listing `uv run irc opportunity`), add one line after the `irc opportunity` line:

```
uv run irc eval-funds --ids "<ids>"   # targeted per-fund opportunity_state / core_dca eval (cache + DuckDB)
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document irc eval-funds command"
```

---

## Task 5 — Full-suite verification (acceptance gate, §8)

- [ ] **Step 1: Run the new + adjacent suites together**

Run: `uv run pytest tests/opportunity/test_fund_eval.py tests/commands/test_fund_eval_cmd.py tests/commands/test_opportunity_cmd.py tests/opportunity/test_build_input_fallback.py -q`
Expected: all PASS (no regressions from the Task 1 extraction; new tests green).

- [ ] **Step 2: Run the FULL test suite**

Run: `uv run pytest -q`
Expected: all PASS (same count as pre-change baseline + the 8 new tests; no failures, no errors). Live tests stay skipped (no `IRC_*=1` env).

- [ ] **Step 3: Lint the whole tree**

Run: `uv run ruff check src tests`
Expected: clean (no errors).

- [ ] **Step 4: Final acceptance smoke (optional, manual — requires a real cache)**

If a populated `data/local.duckdb` + `data/fundamentals/<q>/active_fund/` exists locally:
Run: `uv run irc eval-funds --ids "<a few real metals ids>"`
Expected: prints `eval-funds OK: N core_dca / M evaluated -> outputs/<today>/fund_eval.md`; both `fund_eval.md` and `fund_eval.json` exist; the md lists the `core_dca` funds and the full sub-state table.

---

## Self-review against the spec

- **§1 goals** — covered: Task 2 (`FundEval` four sub-states + `opportunity_state` + `dca_action` + `core_dca`), Task 3 (explicit id list, cache + DuckDB, md + json). "Honest about degraded data" → `evaluate_fund` reports whatever `build_opportunity_row` returns (`evidence_insufficient` sub-states), `core_dca` is strictly `opportunity_state == "core_dca"` (Task 2A test `test_evaluate_fund_insufficient_inputs_yields_insufficient_substates`).
- **§2 non-goals** — no Policy B gate applied (we never call `evaluate_policy_b`); no live fetch (`load_active_fund_cache` reads disk, `_build_input` reads DuckDB only); not persisted to `opportunity_report.json` (writes a separate `fund_eval.{md,json}`).
- **§3.1 command + options** — Task 3B: `--ids`/`--ids-file`, `--quarter`, `--role`, `--db`, `--out`, `--repo-root`. (Spec also lists `--repo-root PATH default .` — included.)
- **§3.2 pure core** — Task 2; `FundEval` fields match the spec exactly; `evaluate_fund` uses the REAL `build_opportunity_row(inp, None, snapshot=snapshot)` + `derive_dca_action(row)`; `top_holdings` derived from `constituent_analyses` (grounding note 3).
- **§3.3 command edge steps 1-8** — Task 3A: parse ids, open DuckDB read-only + error-if-missing, load universe, resolve quarter, synthesize score_row + `_build_input` + `load_active_fund_cache`, `evaluate_funds` (sorted), atomic md+json write, one-line summary + return 0.
- **§3.4 `_build_input` extraction** — Task 1.
- **§5 pure-core tests** — all five present in Task 2 (core_dca; expensive→pause_wait; snapshot=None→missing_constituent_snapshot; insufficient→insufficient sub-states; renderer md+json). §5 command-integration test — Task 3A (md+json written, expected verdict, clear error on missing `--db`).
- **§7 docs** — Task 4.
- **§8 sequencing** — Task order is exactly (1) extract, (2) pure core red→green, (3) cmd+cli red→green, (4) docs, then full-suite verify.

**Type consistency check:** `FundEval` field names are identical between Task 2A definition, the 2B renderer tests, the renderer impl, and the §3.3 JSON. `EvalItem(inp, snapshot, role)` is consistent across `evaluate_funds`, the cmd edge, and tests. `evaluate_fund(inp, snapshot, *, role)` and `evaluate_funds(items)` signatures match every call site. `run_eval_funds(repo_root, *, ids, ids_file, quarter, role, db_path, out_path)` matches the CLI wiring kwargs exactly.

**Correction log (spec sketch vs real code):**
- `derive_dca_action` import path: `irc.opportunity.discipline` (not `states`). [discipline.py:20]
- `OpportunityRow` has no `top_holdings`; derive from `constituent_analyses`. [types.py:170; fundamentals/types.py:139]
- `populate_inputs(con, provider)` shorthand in §3.5 is wrong; real signature is `populate_inputs(con, skeleton, *, holding_entry_date, broker_reports=(), provider=None)` — but we call `_build_input`, which wraps it correctly, so no direct impact. [inputs_loader.py:113]
- After extraction, `opportunity_cmd.py` must re-import `_build_input` and DROP its now-unused `populate_inputs` import to keep ruff clean. [opportunity_cmd.py:45]
- DuckDB read-only via `duckdb.connect(str(db), read_only=True)` (the project's `connect()` helper is read-write and would create the file); read-only mode requires the file to exist, satisfying §3.3 step 2's "error clearly if missing". [duckdb_helper.py:97]
