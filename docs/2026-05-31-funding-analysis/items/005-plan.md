# Item 005 — Bull/bear debate behind `--adversarial` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `--adversarial` flag to `irc opportunity` that, when set, runs a paired bull (`thesis_defend`) / bear (`thesis_falsify`) LLM debate per publishable `OpportunityRow` and writes one advisory `thesis_debate.md`; default OFF keeps the stage byte-identical to today.

**Architecture:** A new pure module `src/irc/opportunity/debate.py` holds two frozen result types (`DefenseResult`, `FalsificationResult` — card-shaped, single-tuple, parallel), pure prompt builders, JSON parse/sanitise, a pure pairing into `ThesisDebate`, and a deterministic `compose_thesis_debate_markdown` renderer. Two thin `call_chat` effect wrappers (`run_defend`, `run_falsify`) live in the same module; an orchestrator `run_debates(rows, route)` pairs both halves per row. `commands/opportunity_cmd.py` threads a `adversarial: bool = False` flag through `run_opportunity` → `_write_opportunity_outputs`, which writes the 6th additive file **only** when the flag is on, after and independently of the five canonical artifacts. No state/gate/classifier/citation/memo change.

**Tech Stack:** Python 3.12, frozen dataclasses, Click, DeepSeek `deepseek-reasoner` via `irc.llm` task-by-name routing, `call_chat`, `atomic_write_text`, pytest (offline mocks + one double-gated live test).

---

## Source-of-truth references (read before starting)

- Spec: `docs/2026-05-31-funding-analysis/items/005-spec.md` (REFINED — honour the `## Resolved decisions` block; D11's "no new ADR" is STRUCK — ADR 0011 exists).
- Binding decision: `docs/adr/0011-adversarial-debate-advisory-only.md` (advisory-only; `thesis_debate.md` EXEMPT from two-run byte-equality; fresh card-shaped runner; NOT reuse `research/falsification.py`).
- Grill verdict: `docs/2026-05-31-funding-analysis/items/005-grill.md` (G2 = FRESH card-shaped runner; G1 = Markdown; G3 = row-level; G4 = `--adversarial` permitted on canonical paths; G5 = file is exempt).
- Skeleton to MIRROR (do NOT import/reuse): `src/irc/research/falsification.py`.
- Live-test convention: `tests/llm/test_live_smoke.py` (`RUN_LIVE_LLM_TESTS=1` + `DEEPSEEK_API_KEY` double-gate).

## Verified anchors (pinned by reading the real code)

- `src/irc/research/falsification.py:8-39` — `FalsificationResult(conditions: tuple[str, ...])`, `_SYS` prompt, `_MAX_CONDITIONS=10`, `_MAX_CONDITION_LEN=300`, `_sanitize_condition` (strip + `replace("\n"," ")` + `replace("\r","")` + `[:300]`), `call_chat(route, messages=[...], timeout_s=30, temperature=0.2)`, `json.loads`, `except Exception: return FalsificationResult(conditions=())`. THE structure to mirror.
- `src/irc/llm/http_client.py:96-112` — `call_chat(route, messages, timeout_s=30.0, temperature=None, ...) -> ChatResponse(text=...)`. Import as `from irc.llm.http_client import call_chat`.
- `src/irc/llm/gateway.py:14-28` — `resolve_route(task, config) -> ResolvedRoute` (raises `KeyError` on unknown task). `ResolvedRoute` from `irc.llm._types`.
- `src/irc/schemas/llm.py:78-92` — `LLMConfig`; `REQUIRED_TASKS=("memo_synthesis","memo_audit")` only → extra tasks (`thesis_defend`) ALLOWED, won't break validation.
- `config/llm.yaml:15` & `src/irc/templates/config/llm.yaml:15` — `thesis_falsify: { provider: deepseek, model: deepseek-reasoner }`. Add `thesis_defend` sibling in BOTH files.
- `src/irc/opportunity/types.py:148-171` — `OpportunityRow`: `instrument_id`, `name_cn`, `thesis_state`, `opportunity_reason`, `evidence_gaps`, `thesis_evidence: tuple[ThesisEvidence, ...]`. `ThesisEvidence.summary` is the prose field to feed the LLM (`src/irc/fundamentals/types.py:69`).
- `src/irc/cli.py:115-131` — `opportunity` command + `run_opportunity(...)` call. `--adversarial` attaches here, same layer as `--rebuild-fundamentals`.
- `src/irc/commands/opportunity_cmd.py:1211-1454` — `_write_opportunity_outputs`: H3 partition at `:1243` (`publishable_rows = [r for r in kept_rows if not r.evidence_gaps]`); citation-gate may demote rows so `publishable_rows` is rebound; five canonical artifacts via `atomic_write_text` (`opportunity_report.json:1402`, `thesis_cards.yaml:1409`, `rejections.json` via `write_rejections_json:1431`, `discipline_report.md:1448`); print summary at `:1450`.
- `src/irc/commands/opportunity_cmd.py:1457-1540` — `run_opportunity(...)`: `bundle = load_repo_configs(root)` at `:1478` (`bundle.llm: LLMConfig`); calls `_write_opportunity_outputs(...)` at `:1521`.
- `src/irc/io_utils.py` — `atomic_write_text(path, text)` (imported at `opportunity_cmd.py:46`).
- `tests/commands/test_opportunity_cmd_h3_invariant.py:13-76` — `_row(...)` + `_position()` fixture helpers; the canonical pattern for calling `_write_opportunity_outputs` directly in a test. REUSE this shape.
- `tests/research/test_falsification.py:6-22` — mock pattern: `@patch("<module>.call_chat")` returning `MagicMock(text='{...}')`, `route=MagicMock()`.

## Judgment calls (made by the planner — cite the spec section)

1. **`run_opportunity` resolves the route only when the flag is ON (spec D6/AC3).** AC3 requires "no thesis-LLM call is made on the default path." `resolve_route("thesis_defend", cfg)` is pure (no network) but to keep flag-OFF provably side-effect-free and avoid a `KeyError` surface on configs lacking the new task, the route is resolved inside `run_opportunity` ONLY when `adversarial=True`, then passed into `_write_opportunity_outputs(..., debate_route=route)`. When `adversarial=False`, `debate_route=None` and the debate code path is never entered. (Spec §D6, AC3, AC5.)

2. **The orchestrator `run_debates` is the effect seam, called from `_write_opportunity_outputs` (spec D9/D11).** D9 splits pure (prompt/parse/pair/render) from effect (`call_chat`). D11 places the thin runner in `debate.py` "orchestrated from `commands/opportunity_cmd.py`." Decision: `debate.py` owns `run_defend`/`run_falsify`/`run_debates` (the effect wrappers + per-row orchestration with per-row try/except degrade); `_write_opportunity_outputs` calls `run_debates(publishable_rows, debate_route)` then `compose_thesis_debate_markdown(...)` then `atomic_write_text`. The two `call_chat` effects live behind `run_defend`/`run_falsify` which unit tests patch. (Spec §D9, D11, D12.)

3. **`thesis_debate.md` is written from the FINAL `publishable_rows`, after the citation gate (spec D10/AC5).** D10/AC5: "publishable rows only (the H3 `evidence_gaps == ()` set ... after the citation gate)." `_write_opportunity_outputs` rebinds `publishable_rows` after Step 2a/2c demotion (`opportunity_cmd.py:1282,1308`). Decision: the debate hook runs AFTER `discipline_report.md` is written (`:1448`), reading the post-demotion `publishable_rows`, so a citation-gate-demoted row gets no debate. This also guarantees the five canonical artifacts are fully written before any debate `call_chat`, satisfying D12 ("never blocks the canonical artifacts"). (Spec §D7, D10, D12, AC5, AC6.)

3b. **Per-row failure isolation wraps each half independently (spec D12/AC12).** `run_defend`/`run_falsify` each have their own `except Exception → empty result` (mirroring `generate_falsification`). `run_debates` additionally wraps each row so an unexpected pairing error cannot abort the loop. A row whose BOTH halves are empty renders the `（本行未能生成辩论）` placeholder. (Spec §D12, AC12.)

4. **Evidence prose fed to the LLM is the top-N `ThesisEvidence.summary` (spec D2).** D2: "the top-N `thesis_evidence` summaries." Decision: `_evidence_lines(row, n=5)` takes `row.thesis_evidence[:5]` and joins `e.summary`. No `[ref:...]` id is ever emitted into the prompt or the markdown — the debate quotes prose only (spec AC9). N=5 is the planner's bound (spec says "top-N"; 5 mirrors falsify's `3-5` framing). (Spec §D2, AC9.)

5. **Markdown section shape (spec D7/AC6).** Per spec D7: `### {iid} {name_cn}` → a derived-state line → `**看多**` (defend) bullets → `**看空**` (falsify) bullets. Empty-both rows → the placeholder line. The exact byte-shape is locked by Task 4's tests so it is deterministic (spec AC10). (Spec §D7, AC6, AC10.)

---

## File structure

| File | Responsibility | Create/Modify |
| --- | --- | --- |
| `src/irc/opportunity/debate.py` | `DefenseResult` + `FalsificationResult` types, `ThesisDebate` type, pure prompt builders, JSON parse/sanitise, `run_defend`/`run_falsify` (effect wrappers), `run_debates` (orchestrator), pure `pair_debate` + `compose_thesis_debate_markdown`. | Create |
| `tests/opportunity/test_debate.py` | Unit tests: result parse/degrade (mocked `call_chat`), pairing, deterministic renderer, placeholder, call-count. | Create |
| `tests/opportunity/test_debate_live.py` | Single double-gated live LLM test. | Create |
| `config/llm.yaml` | Add `thesis_defend: { provider: deepseek, model: deepseek-reasoner }`. | Modify (`:15`, after `thesis_falsify`) |
| `src/irc/templates/config/llm.yaml` | Same `thesis_defend` entry (template). | Modify (`:15`) |
| `tests/llm/test_thesis_defend_route.py` | `resolve_route("thesis_defend", cfg)` resolves to `deepseek-reasoner`; config still validates. | Create |
| `src/irc/cli.py` | Add `--adversarial` flag; thread into `run_opportunity(..., adversarial=...)`. | Modify (`:115-131`) |
| `src/irc/commands/opportunity_cmd.py` | Add `adversarial: bool = False` to `run_opportunity`; resolve route when ON; add `debate_route` param to `_write_opportunity_outputs` + the write hook. | Modify (`:1211-1223`, `:1450-1454`, `:1457-1526`) |
| `tests/commands/test_opportunity_cmd_adversarial.py` | Flag-OFF byte-identical (no `thesis_debate.md`, no `call_chat`); flag-ON writes file + `2 × n_publishable` calls; not in canonical/SAME-3 set; gapped rows get no debate; per-row failure isolation. | Create |
| `CONTEXT.md` | Add `thesis_defend` / `DefenseResult` / `ThesisDebate` / `thesis_debate.md` / `--adversarial` glossary entries (new "Adversarial debate (advisory)" section). | Modify |

**Size budget:** `debate.py` MUST stay < 200 lines. The two result types + `ThesisDebate` (~12 lines), 2 prompt builders + parse/sanitise (~30 lines), `run_defend`/`run_falsify`/`run_debates` (~30 lines), `pair_debate` + `compose_thesis_debate_markdown` (~30 lines) ≈ 110 lines — comfortably within budget. If it exceeds 200, split the renderer into `debate_render.py`. Each function < 20 lines (extract `_sanitize`, `_evidence_lines`, `_render_section` helpers).

---

## Task 1: Register the `thesis_defend` LLM task

**Files:**
- Modify: `config/llm.yaml:15`
- Modify: `src/irc/templates/config/llm.yaml:15`
- Test: `tests/llm/test_thesis_defend_route.py`

- [ ] **Step 1: Write the failing test**

Create `tests/llm/test_thesis_defend_route.py`:

```python
from __future__ import annotations
from importlib import resources
import yaml
from irc.llm.gateway import resolve_route
from irc.schemas.llm import LLMConfig


def _load_template_cfg() -> LLMConfig:
    text = resources.files("irc.templates.config").joinpath("llm.yaml").read_text(encoding="utf-8")
    return LLMConfig.model_validate(yaml.safe_load(text))


def test_thesis_defend_resolves_to_deepseek_reasoner():
    cfg = _load_template_cfg()
    route = resolve_route("thesis_defend", cfg)
    assert route.model == "deepseek-reasoner"
    assert route.provider == "deepseek"


def test_thesis_defend_matches_thesis_falsify_model():
    cfg = _load_template_cfg()
    assert resolve_route("thesis_defend", cfg).model == resolve_route("thesis_falsify", cfg).model


def test_config_still_validates_with_extra_task():
    # Extra tasks are allowed (REQUIRED_TASKS = memo_synthesis/memo_audit only).
    cfg = _load_template_cfg()
    assert "thesis_defend" in cfg.tasks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/llm/test_thesis_defend_route.py -q`
Expected: FAIL — `KeyError: "unknown task: 'thesis_defend'"`.

- [ ] **Step 3: Add the task to both YAML files**

In `config/llm.yaml`, add immediately after the `thesis_falsify` line (`:15`):

```yaml
  thesis_defend:      { provider: deepseek,   model: deepseek-reasoner }
```

In `src/irc/templates/config/llm.yaml`, add the identical line immediately after its `thesis_falsify` line (`:15`):

```yaml
  thesis_defend:      { provider: deepseek,   model: deepseek-reasoner }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/llm/test_thesis_defend_route.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add config/llm.yaml src/irc/templates/config/llm.yaml tests/llm/test_thesis_defend_route.py
git commit -m "feat(005): register thesis_defend LLM task (deepseek-reasoner)"
```

---

## Task 2: Result types + pure prompt builders + parse/sanitise

**Files:**
- Create: `src/irc/opportunity/debate.py`
- Test: `tests/opportunity/test_debate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/opportunity/test_debate.py`:

```python
from __future__ import annotations
from unittest.mock import patch, MagicMock

from irc.opportunity.debate import (
    DefenseResult,
    FalsificationResult,
    run_defend,
    run_falsify,
)


def _row(iid="X1", name_cn="测试基金", thesis_state="intact",
         opportunity_reason="长期逻辑完整", evidence_summaries=("证据A", "证据B")):
    from irc.fundamentals.types import ThesisEvidence
    from irc.opportunity.types import LookthroughTarget, OpportunityRow
    evidence = tuple(
        ThesisEvidence(
            type="filing", source="src", url=f"https://x/{iid}/{i}", date="2024-04-15",
            summary=s, scope="instrument", citation_kind="data",
            owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
            holding_weight_pct=None,
        )
        for i, s in enumerate(evidence_summaries)
    )
    return OpportunityRow(
        instrument_id=iid, name_cn=name_cn, asset_class="cn_equity_fund", theme=None,
        lookthrough_target=LookthroughTarget("active_fund", f"fund_{iid}", name_cn, iid),
        valuation_state="fair", heat_state="normal", thesis_state=thesis_state,
        product_quality_state="acceptable", opportunity_state="core_dca",
        opportunity_reason=opportunity_reason, evidence_gaps=(),
        thesis_evidence=evidence,
    )


@patch("irc.opportunity.debate.call_chat")
def test_run_defend_parses_arguments(mock_chat):
    mock_chat.return_value = MagicMock(text='{"arguments": ["盈利持续", "估值合理"]}')
    out = run_defend(_row(), route=MagicMock())
    assert isinstance(out, DefenseResult)
    assert out.arguments == ("盈利持续", "估值合理")


@patch("irc.opportunity.debate.call_chat")
def test_run_defend_invalid_json_returns_empty(mock_chat):
    mock_chat.return_value = MagicMock(text="not json")
    assert run_defend(_row(), route=MagicMock()).arguments == ()


@patch("irc.opportunity.debate.call_chat")
def test_run_defend_raises_returns_empty(mock_chat):
    mock_chat.side_effect = RuntimeError("boom")
    assert run_defend(_row(), route=MagicMock()).arguments == ()


@patch("irc.opportunity.debate.call_chat")
def test_run_falsify_parses_conditions(mock_chat):
    mock_chat.return_value = MagicMock(text='{"conditions": ["盈利转负"]}')
    out = run_falsify(_row(), route=MagicMock())
    assert isinstance(out, FalsificationResult)
    assert out.conditions == ("盈利转负",)


@patch("irc.opportunity.debate.call_chat")
def test_run_defend_sanitizes_newlines_and_caps(mock_chat):
    long = "a" * 400
    mock_chat.return_value = MagicMock(text='{"arguments": ["line1\\nline2", "%s"]}' % long)
    out = run_defend(_row(), route=MagicMock())
    assert "\n" not in out.arguments[0]
    assert len(out.arguments[1]) == 300


@patch("irc.opportunity.debate.call_chat")
def test_run_defend_caps_item_count(mock_chat):
    items = ", ".join(['"x"'] * 20)
    mock_chat.return_value = MagicMock(text='{"arguments": [%s]}' % items)
    assert len(run_defend(_row(), route=MagicMock()).arguments) <= 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_debate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.opportunity.debate'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/opportunity/debate.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass

from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat
from irc.opportunity.types import OpportunityRow

__all__ = [
    "DefenseResult",
    "FalsificationResult",
    "ThesisDebate",
    "run_defend",
    "run_falsify",
    "run_debates",
    "pair_debate",
    "compose_thesis_debate_markdown",
]


@dataclass(frozen=True)
class DefenseResult:
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class FalsificationResult:
    conditions: tuple[str, ...]


@dataclass(frozen=True)
class ThesisDebate:
    instrument_id: str
    name_cn: str
    thesis_state: str
    defense: DefenseResult
    falsification: FalsificationResult


_DEFEND_SYS = (
    "Given an investment thesis card (name, derived state, summary, evidence), "
    "steelman the BULL case: list 3-5 arguments for why the long-term logic is "
    'alive. Output JSON: {"arguments": ["...", "..."]}'
)
_FALSIFY_SYS = (
    "Given an investment thesis card (name, derived state, summary, evidence), "
    "steelman the BEAR case: list 3-5 falsification conditions that, if observed, "
    'would invalidate the thesis. Output JSON: {"conditions": ["...", "..."]}'
)

_MAX_ITEMS = 10
_MAX_ITEM_LEN = 300


def _sanitize(s: str) -> str:
    """Strip whitespace, flatten newlines, cap length (mirrors falsification.py)."""
    return str(s).strip().replace("\n", " ").replace("\r", "")[:_MAX_ITEM_LEN]


def _evidence_lines(row: OpportunityRow, n: int = 5) -> str:
    return "; ".join(e.summary for e in row.thesis_evidence[:n])


def _thesis_card(row: OpportunityRow) -> str:
    return (
        f"name: {row.name_cn}\n"
        f"derived_thesis_state: {row.thesis_state}\n"
        f"summary: {row.opportunity_reason}\n"
        f"evidence: {_evidence_lines(row)}"
    )


def run_defend(row: OpportunityRow, route: ResolvedRoute) -> DefenseResult:
    try:
        resp = call_chat(route, messages=[
            {"role": "system", "content": _DEFEND_SYS},
            {"role": "user", "content": _thesis_card(row)},
        ], timeout_s=30, temperature=0.2)
        items = json.loads(resp.text).get("arguments", [])[:_MAX_ITEMS]
        return DefenseResult(arguments=tuple(_sanitize(i) for i in items))
    except Exception:
        return DefenseResult(arguments=())


def run_falsify(row: OpportunityRow, route: ResolvedRoute) -> FalsificationResult:
    try:
        resp = call_chat(route, messages=[
            {"role": "system", "content": _FALSIFY_SYS},
            {"role": "user", "content": _thesis_card(row)},
        ], timeout_s=30, temperature=0.2)
        items = json.loads(resp.text).get("conditions", [])[:_MAX_ITEMS]
        return FalsificationResult(conditions=tuple(_sanitize(i) for i in items))
    except Exception:
        return FalsificationResult(conditions=())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_debate.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/debate.py tests/opportunity/test_debate.py
git commit -m "feat(005): debate result types + defend/falsify LLM-edge runners"
```

---

## Task 3: Pure pairing — `pair_debate` + `run_debates` orchestrator

**Files:**
- Modify: `src/irc/opportunity/debate.py`
- Test: `tests/opportunity/test_debate.py` (append)

- [ ] **Step 1: Write the failing test (append to `tests/opportunity/test_debate.py`)**

```python
from irc.opportunity.debate import ThesisDebate, pair_debate, run_debates


def test_pair_debate_is_pure():
    row = _row(iid="P1", thesis_state="intact")
    d = DefenseResult(arguments=("a",))
    f = FalsificationResult(conditions=("c",))
    debate = pair_debate(row, d, f)
    assert isinstance(debate, ThesisDebate)
    assert debate.instrument_id == "P1"
    assert debate.thesis_state == "intact"
    assert debate.defense == d
    assert debate.falsification == f


@patch("irc.opportunity.debate.call_chat")
def test_run_debates_calls_both_halves_per_row(mock_chat):
    mock_chat.return_value = MagicMock(text='{"arguments": ["a"], "conditions": ["c"]}')
    rows = [_row(iid="R1"), _row(iid="R2")]
    debates = run_debates(rows, route=MagicMock())
    # 2 rows × (defend + falsify) = 4 calls.
    assert mock_chat.call_count == 4
    assert len(debates) == 2
    assert {d.instrument_id for d in debates} == {"R1", "R2"}


@patch("irc.opportunity.debate.call_chat")
def test_run_debates_isolates_per_row_failure(mock_chat):
    # First row's defend raises; the run must still produce 2 debates.
    calls = {"n": 0}

    def _side(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("row1 defend down")
        return MagicMock(text='{"arguments": ["a"], "conditions": ["c"]}')

    mock_chat.side_effect = _side
    debates = run_debates([_row(iid="R1"), _row(iid="R2")], route=MagicMock())
    assert len(debates) == 2
    # R1's defense degraded to empty, falsify still ran.
    r1 = next(d for d in debates if d.instrument_id == "R1")
    assert r1.defense.arguments == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_debate.py -q`
Expected: FAIL — `ImportError: cannot import name 'pair_debate'`.

- [ ] **Step 3: Append implementation to `src/irc/opportunity/debate.py`**

```python
def pair_debate(
    row: OpportunityRow, defense: DefenseResult, falsification: FalsificationResult,
) -> ThesisDebate:
    return ThesisDebate(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        thesis_state=row.thesis_state,
        defense=defense,
        falsification=falsification,
    )


def _debate_one(row: OpportunityRow, route: ResolvedRoute) -> ThesisDebate:
    return pair_debate(row, run_defend(row, route), run_falsify(row, route))


def run_debates(
    rows: list[OpportunityRow], route: ResolvedRoute,
) -> tuple[ThesisDebate, ...]:
    """Effect orchestrator: one defend + one falsify per row, per-row isolated."""
    out: list[ThesisDebate] = []
    for row in rows:
        try:
            out.append(_debate_one(row, route))
        except Exception:
            out.append(pair_debate(row, DefenseResult(()), FalsificationResult(())))
    return tuple(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_debate.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add src/irc/opportunity/debate.py tests/opportunity/test_debate.py
git commit -m "feat(005): pure pair_debate + run_debates orchestrator (per-row isolated)"
```

---

## Task 4: Deterministic markdown renderer `compose_thesis_debate_markdown`

**Files:**
- Modify: `src/irc/opportunity/debate.py`
- Test: `tests/opportunity/test_debate.py` (append)

- [ ] **Step 1: Write the failing test (append to `tests/opportunity/test_debate.py`)**

```python
from irc.opportunity.debate import compose_thesis_debate_markdown


def _debate(iid, name, state, args, conds):
    return ThesisDebate(
        instrument_id=iid, name_cn=name, thesis_state=state,
        defense=DefenseResult(arguments=tuple(args)),
        falsification=FalsificationResult(conditions=tuple(conds)),
    )


def test_renderer_section_shape():
    md = compose_thesis_debate_markdown((
        _debate("R1", "测试基金", "intact", ["盈利持续"], ["盈利转负"]),
    ))
    assert "### R1 测试基金" in md
    assert "intact" in md
    assert "**看多**" in md
    assert "盈利持续" in md
    assert "**看空**" in md
    assert "盈利转负" in md


def test_renderer_empty_both_renders_placeholder():
    md = compose_thesis_debate_markdown((_debate("R2", "空辩论", "intact", [], []),))
    assert "（本行未能生成辩论）" in md


def test_renderer_is_deterministic():
    debates = (
        _debate("R1", "甲", "intact", ["a1", "a2"], ["c1"]),
        _debate("R2", "乙", "under_pressure", ["b1"], ["d1", "d2"]),
    )
    assert compose_thesis_debate_markdown(debates) == compose_thesis_debate_markdown(debates)


def test_renderer_emits_no_citation_marker():
    import re
    md = compose_thesis_debate_markdown((
        _debate("R1", "甲", "intact", ["see [ref:abc] note"], ["c"]),
    ))
    # The renderer introduces no NEW 16-hex citation id of its own.
    assert not re.search(r"\[ref:[0-9a-f]{16}\]", md)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_debate.py -q`
Expected: FAIL — `ImportError: cannot import name 'compose_thesis_debate_markdown'`.

- [ ] **Step 3: Append implementation to `src/irc/opportunity/debate.py`**

```python
_PLACEHOLDER = "（本行未能生成辩论）"


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {i}" for i in items)


def _render_section(d: ThesisDebate) -> str:
    head = f"### {d.instrument_id} {d.name_cn}\n\n推导 thesis_state: {d.thesis_state}\n"
    if not d.defense.arguments and not d.falsification.conditions:
        return f"{head}\n{_PLACEHOLDER}\n"
    bull = f"\n**看多**\n\n{_bullets(d.defense.arguments)}\n" if d.defense.arguments else ""
    bear = f"\n**看空**\n\n{_bullets(d.falsification.conditions)}\n" if d.falsification.conditions else ""
    return f"{head}{bull}{bear}"


def compose_thesis_debate_markdown(debates: tuple[ThesisDebate, ...]) -> str:
    """Pure, deterministic: same ThesisDebate tuple → byte-identical Markdown."""
    header = "# 多空辩论 / Bull-Bear Debate (advisory)\n"
    sections = "\n".join(_render_section(d) for d in debates)
    return f"{header}\n{sections}\n" if debates else f"{header}\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/opportunity/test_debate.py -q`
Expected: PASS (13 passed).

- [ ] **Step 5: Verify size budget**

Run: `wc -l src/irc/opportunity/debate.py`
Expected: < 200 lines. (If ≥ 200, extract the renderer into `src/irc/opportunity/debate_render.py` and re-export from `debate.py`; re-run the test file — still green.)

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/debate.py tests/opportunity/test_debate.py
git commit -m "feat(005): deterministic compose_thesis_debate_markdown renderer"
```

---

## Task 5: `--adversarial` flag + threading + write hook

**Files:**
- Modify: `src/irc/cli.py:115-131`
- Modify: `src/irc/commands/opportunity_cmd.py` (`_write_opportunity_outputs` signature `:1211-1223` + write hook after `:1448`; `run_opportunity` `:1457-1526`)
- Test: `tests/commands/test_opportunity_cmd_adversarial.py`

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_opportunity_cmd_adversarial.py`:

```python
"""Item 005 — --adversarial bull/bear debate (advisory file)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from irc.opportunity.discipline import PositionContext


def _row(iid, name_cn="x", opportunity_state="core_dca", evidence_gaps=()):
    """Mirrors tests/commands/test_opportunity_cmd_h3_invariant.py::_row."""
    from irc.fundamentals.types import ThesisEvidence
    from irc.opportunity.types import LookthroughTarget, OpportunityRow
    if not evidence_gaps:
        ev = (
            ThesisEvidence(
                type="filing", source="src", url=f"https://x/{iid}/d", date="2024-04-15",
                summary="data leg", scope="instrument", citation_kind="data",
                owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
                holding_weight_pct=None,
            ),
            ThesisEvidence(
                type="filing", source="src", url=f"https://x/{iid}/i", date="2024-04-16",
                summary="info leg", scope="instrument", citation_kind="information",
                owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
                holding_weight_pct=None,
            ),
        )
    else:
        ev = ()
    return OpportunityRow(
        instrument_id=iid, name_cn=name_cn, asset_class="cn_equity_fund", theme=None,
        lookthrough_target=LookthroughTarget("active_fund", f"fund_{iid}", name_cn, iid),
        valuation_state="evidence_insufficient", heat_state="evidence_insufficient",
        thesis_state="intact", product_quality_state="evidence_insufficient",
        opportunity_state=opportunity_state, opportunity_reason="r",
        evidence_gaps=evidence_gaps, thesis_evidence=ev,
    )


def _position():
    return PositionContext(
        portfolio_weight=None, target_band_low=None, target_band_high=None,
        drawdown_since_entry=None, is_holding=False,
    )


_CANONICAL = {
    "opportunity_report.json", "thesis_cards.yaml", "discipline_report.md", "rejections.json",
}


@patch("irc.commands.opportunity_cmd.run_debates")
def test_flag_off_writes_no_debate_and_no_llm_call(mock_debates, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
        debate_route=None,
    )
    assert not (tmp_path / "thesis_debate.md").exists()
    mock_debates.assert_not_called()
    written = {p.name for p in tmp_path.glob("*") if p.is_file()}
    assert _CANONICAL.issubset(written)


def test_flag_off_byte_identical_default_call(tmp_path):
    # Default (no debate_route kwarg) must behave exactly like today.
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
    )
    assert not (tmp_path / "thesis_debate.md").exists()


@patch("irc.opportunity.debate.call_chat")
def test_flag_on_writes_debate_and_runs_both_halves(mock_chat, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    mock_chat.return_value = MagicMock(text='{"arguments": ["a"], "conditions": ["c"]}')
    pub = [_row("A"), _row("B")]
    gapped = _row("G", evidence_gaps=("qdii_information_unavailable",))
    _write_opportunity_outputs(
        kept_rows=pub + [gapped],
        positions={"A": _position(), "B": _position(), "G": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
        debate_route=MagicMock(),
    )
    md = (tmp_path / "thesis_debate.md").read_text(encoding="utf-8")
    assert "### A x" in md and "### B x" in md
    assert "### G" not in md  # gapped rows get no debate
    # 2 publishable rows × (defend + falsify) = 4 calls.
    assert mock_chat.call_count == 4


@patch("irc.opportunity.debate.call_chat")
def test_debate_file_not_a_canonical_artifact(mock_chat, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    mock_chat.return_value = MagicMock(text='{"arguments": ["a"], "conditions": ["c"]}')
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
        debate_route=MagicMock(),
    )
    assert "thesis_debate.md" not in _CANONICAL
    assert (tmp_path / "thesis_debate.md").exists()


@patch("irc.opportunity.debate.call_chat")
def test_per_row_failure_renders_placeholder_and_keeps_canonical(mock_chat, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    mock_chat.side_effect = RuntimeError("llm down")
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
        debate_route=MagicMock(),
    )
    md = (tmp_path / "thesis_debate.md").read_text(encoding="utf-8")
    assert "（本行未能生成辩论）" in md
    # Canonical artifacts still written despite LLM failure.
    assert (tmp_path / "opportunity_report.json").exists()
    assert (tmp_path / "thesis_cards.yaml").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_opportunity_cmd_adversarial.py -q`
Expected: FAIL — `TypeError: _write_opportunity_outputs() got an unexpected keyword argument 'debate_route'`.

- [ ] **Step 3: Add `debate_route` param + write hook to `_write_opportunity_outputs`**

In `src/irc/commands/opportunity_cmd.py`, change the signature (`:1219-1223`) to add the new keyword param:

```python
def _write_opportunity_outputs(
    kept_rows: list[OpportunityRow],
    positions: dict[str, PositionContext],
    qualities: dict[str, SelectionQuality],
    roles: dict[str, str],
    holdings: dict[str, Holding],
    out_dir: Path,
    today: str,
    *,
    pending_verdicts: dict[str, PolicyBVerdict] | None = None,
    snapshot_cache_by_instrument: dict[str, object] | None = None,
    plan_hash: str = "",
    debate_route: object | None = None,
) -> None:
```

Then add the debate hook AFTER the existing `atomic_write_text(out_dir / "discipline_report.md", discipline_md)` line (`:1448`) and BEFORE the `print(...)` summary (`:1450`):

```python
    # Item 005 — advisory bull/bear debate (ADR 0011). Written ONLY when
    # --adversarial set; 6th additive file, NOT a canonical artifact, NOT in
    # H3/SAME-3, EXEMPT from two-run byte-equality. Runs on the FINAL
    # post-citation-gate publishable_rows, AFTER all canonical artifacts.
    if debate_route is not None:
        debates = run_debates(publishable_rows, debate_route)
        atomic_write_text(
            out_dir / "thesis_debate.md",
            compose_thesis_debate_markdown(debates),
        )
```

Add the import near the other `irc.opportunity` imports (after `:62`):

```python
from irc.opportunity.debate import compose_thesis_debate_markdown, run_debates
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `uv run pytest tests/commands/test_opportunity_cmd_adversarial.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Thread `adversarial` through `run_opportunity` + resolve route only when ON**

In `src/irc/commands/opportunity_cmd.py`, change the `run_opportunity` signature (`:1457-1463`):

```python
def run_opportunity(
    repo_root: str,
    *,
    output_dir: str | None = None,
    limit: int | None = None,
    rebuild_fundamentals: bool = False,
    adversarial: bool = False,
) -> int:
```

After `bundle = load_repo_configs(root)` (`:1478`), add:

```python
    debate_route = None
    if adversarial:
        from irc.llm.gateway import resolve_route
        debate_route = resolve_route("thesis_defend", bundle.llm)
```

Wait — both halves must resolve. Replace with resolving BOTH and passing them through. Use a small tuple. Update the hook to take both routes. Concretely, after `:1478`:

```python
    debate_route = None
    if adversarial:
        from irc.llm.gateway import resolve_route
        debate_route = (
            resolve_route("thesis_defend", bundle.llm),
            resolve_route("thesis_falsify", bundle.llm),
        )
```

And in the `_write_opportunity_outputs(...)` call (`:1521-1526`), add `debate_route=debate_route`:

```python
        _write_opportunity_outputs(
            kept_rows, positions, qualities, roles, holdings, out_dir, today,
            pending_verdicts=pending_verdicts,
            plan_hash=plan_hash,
            snapshot_cache_by_instrument=snapshot_cache_by_instrument,
            debate_route=debate_route,
        )
```

> NOTE — TWO ROUTES. `run_defend` and `run_falsify` take DIFFERENT routes (`thesis_defend` / `thesis_falsify`). Update Task 3's `run_debates` and the hook to thread both. Apply the Step 5b correction below before re-running.

- [ ] **Step 5b: Correct `run_debates` + `_debate_one` to take two routes**

In `src/irc/opportunity/debate.py`, change `_debate_one` and `run_debates` to accept `(defend_route, falsify_route)`:

```python
def _debate_one(
    row: OpportunityRow, defend_route: ResolvedRoute, falsify_route: ResolvedRoute,
) -> ThesisDebate:
    return pair_debate(
        row, run_defend(row, defend_route), run_falsify(row, falsify_route),
    )


def run_debates(
    rows: list[OpportunityRow],
    routes: tuple[ResolvedRoute, ResolvedRoute],
) -> tuple[ThesisDebate, ...]:
    """Effect orchestrator: one defend + one falsify per row, per-row isolated.

    `routes` = (defend_route, falsify_route).
    """
    defend_route, falsify_route = routes
    out: list[ThesisDebate] = []
    for row in rows:
        try:
            out.append(_debate_one(row, defend_route, falsify_route))
        except Exception:
            out.append(pair_debate(row, DefenseResult(()), FalsificationResult(())))
    return tuple(out)
```

Update the Task 3 tests in `tests/opportunity/test_debate.py` that call `run_debates(rows, route=MagicMock())` to pass a 2-tuple:

```python
    debates = run_debates(rows, routes=(MagicMock(), MagicMock()))
```

(Apply to both `test_run_debates_calls_both_halves_per_row` and `test_run_debates_isolates_per_row_failure`. The call-count assertion `== 4` is unchanged — 2 rows × 2 halves.)

In `tests/commands/test_opportunity_cmd_adversarial.py`, the `debate_route=MagicMock()` kwargs must become a 2-tuple `debate_route=(MagicMock(), MagicMock())`. Update all four ON-path tests accordingly.

In `_write_opportunity_outputs`'s hook, `debate_route` is now the 2-tuple; pass it straight to `run_debates`:

```python
    if debate_route is not None:
        debates = run_debates(publishable_rows, debate_route)
        atomic_write_text(
            out_dir / "thesis_debate.md",
            compose_thesis_debate_markdown(debates),
        )
```

- [ ] **Step 6: Add the `--adversarial` CLI flag (`src/irc/cli.py:115-131`)**

Replace the `opportunity` command body to add the flag + thread it:

```python
@main.command(help="Run opportunity/thesis/discipline layer; writes 3 outputs.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--output-dir", type=click.Path(file_okay=False), default=None,
              help="Override the default outputs/<today>/ directory.")
@click.option("--limit", type=int, default=None,
              help="Cap cn_equity_fund autobuild rows (rejected on canonical paths).")
@click.option("--rebuild-fundamentals", is_flag=True, default=False,
              help="Force full re-fetch of active-fund caches (skip freshness probe).")
@click.option("--adversarial", is_flag=True, default=False,
              help="Emit advisory bull/bear thesis_debate.md (opt-in; doubles thesis-LLM calls).")
def opportunity(
    repo_root: str, output_dir: str | None, limit: int | None,
    rebuild_fundamentals: bool, adversarial: bool,
) -> None:
    from irc.commands.opportunity_cmd import run_opportunity
    rc = run_opportunity(
        repo_root=repo_root,
        output_dir=output_dir,
        limit=limit,
        rebuild_fundamentals=rebuild_fundamentals,
        adversarial=adversarial,
    )
    raise SystemExit(rc)
```

- [ ] **Step 7: Run the full debate + adversarial + cli suites**

Run: `uv run pytest tests/opportunity/test_debate.py tests/commands/test_opportunity_cmd_adversarial.py -q`
Expected: PASS (all green — 13 debate + 5 adversarial).

Run: `uv run pytest tests/test_cli.py -q` (if present) or `uv run irc opportunity --help`
Expected: `--adversarial` appears in the help output.

- [ ] **Step 8: Commit**

```bash
git add src/irc/cli.py src/irc/commands/opportunity_cmd.py src/irc/opportunity/debate.py \
        tests/opportunity/test_debate.py tests/commands/test_opportunity_cmd_adversarial.py
git commit -m "feat(005): --adversarial flag + thesis_debate.md write hook"
```

---

## Task 6: Live double-gated LLM test

**Files:**
- Create: `tests/opportunity/test_debate_live.py`

- [ ] **Step 1: Write the live test (skipped by default)**

Create `tests/opportunity/test_debate_live.py`:

```python
"""Live smoke for the bull/bear debate. Skipped unless RUN_LIVE_LLM_TESTS=1
AND DEEPSEEK_API_KEY set (project live-LLM double-gate)."""
from __future__ import annotations

import json
import os
from importlib import resources

import pytest
import yaml

from irc.llm.gateway import resolve_route
from irc.llm.http_client import call_chat
from irc.opportunity.debate import _DEFEND_SYS, _FALSIFY_SYS
from irc.schemas.llm import LLMConfig

_RUN = os.environ.get("RUN_LIVE_LLM_TESTS") == "1"
_HAS_DS = bool(os.environ.get("DEEPSEEK_API_KEY"))


def _cfg() -> LLMConfig:
    text = resources.files("irc.templates.config").joinpath("llm.yaml").read_text(encoding="utf-8")
    return LLMConfig.model_validate(yaml.safe_load(text))


@pytest.mark.skipif(not (_RUN and _HAS_DS), reason="set RUN_LIVE_LLM_TESTS=1 + DEEPSEEK_API_KEY")
def test_live_thesis_defend_returns_parseable_json():
    cfg = _cfg()
    route = resolve_route("thesis_defend", cfg)
    assert route.model == "deepseek-reasoner"
    resp = call_chat(route, messages=[
        {"role": "system", "content": _DEFEND_SYS},
        {"role": "user", "content": "name: 测试\nderived_thesis_state: intact\nsummary: 长期逻辑完整\nevidence: 盈利增长"},
    ], timeout_s=60, temperature=0.2)
    data = json.loads(resp.text)
    assert isinstance(data.get("arguments"), list)


@pytest.mark.skipif(not (_RUN and _HAS_DS), reason="set RUN_LIVE_LLM_TESTS=1 + DEEPSEEK_API_KEY")
def test_live_thesis_falsify_returns_parseable_json():
    cfg = _cfg()
    route = resolve_route("thesis_falsify", cfg)
    resp = call_chat(route, messages=[
        {"role": "system", "content": _FALSIFY_SYS},
        {"role": "user", "content": "name: 测试\nderived_thesis_state: intact\nsummary: 长期逻辑完整\nevidence: 盈利增长"},
    ], timeout_s=60, temperature=0.2)
    data = json.loads(resp.text)
    assert isinstance(data.get("conditions"), list)
```

- [ ] **Step 2: Verify it SKIPS by default**

Run: `uv run pytest tests/opportunity/test_debate_live.py -q`
Expected: `2 skipped` (no `RUN_LIVE_LLM_TESTS`).

- [ ] **Step 3: Commit**

```bash
git add tests/opportunity/test_debate_live.py
git commit -m "test(005): double-gated live LLM smoke for defend/falsify"
```

---

## Task 7: Regression locks — no state/citation/memo change + full suite + lint

**Files:**
- Test: `tests/commands/test_opportunity_cmd_adversarial.py` (append)

- [ ] **Step 1: Write the regression-lock tests (append)**

These assert AC7 (no state change vs with/without flag) and AC9 (no new citation in the debate file) at the `_write_opportunity_outputs` level by reading the canonical artifacts before/after.

```python
import json


def _read_report(tmp_path):
    return json.loads((tmp_path / "opportunity_report.json").read_text(encoding="utf-8"))


@patch("irc.opportunity.debate.call_chat")
def test_canonical_artifacts_byte_identical_with_vs_without_flag(mock_chat, tmp_path):
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    mock_chat.return_value = MagicMock(text='{"arguments": ["a"], "conditions": ["c"]}')

    off = tmp_path / "off"
    on = tmp_path / "on"
    for d in (off, on):
        d.mkdir()

    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=off, today="2026-05-23",
    )
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=on, today="2026-05-23",
        debate_route=(MagicMock(), MagicMock()),
    )
    for name in _CANONICAL:
        assert (off / name).read_bytes() == (on / name).read_bytes(), name
    # The ON dir additionally has the advisory file; the OFF dir does not.
    assert (on / "thesis_debate.md").exists()
    assert not (off / "thesis_debate.md").exists()


@patch("irc.opportunity.debate.call_chat")
def test_debate_file_introduces_no_citation_id(mock_chat, tmp_path):
    import re
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    mock_chat.return_value = MagicMock(
        text='{"arguments": ["see [ref:abc] prose"], "conditions": ["c"]}'
    )
    _write_opportunity_outputs(
        kept_rows=[_row("A")], positions={"A": _position()},
        qualities={}, roles={}, holdings={}, out_dir=tmp_path, today="2026-05-23",
        debate_route=(MagicMock(), MagicMock()),
    )
    md = (tmp_path / "thesis_debate.md").read_text(encoding="utf-8")
    assert not re.search(r"\[ref:[0-9a-f]{16}\]", md)
```

- [ ] **Step 2: Run to verify they pass**

Run: `uv run pytest tests/commands/test_opportunity_cmd_adversarial.py -q`
Expected: PASS (7 passed total).

- [ ] **Step 3: Run the regression-sensitive existing suites (must stay green)**

Run:
```bash
uv run pytest tests/opportunity tests/commands/test_opportunity_cmd_h3_invariant.py \
  tests/commands/test_opportunity_cmd_citation_gate.py \
  tests/integration/test_publishable_set_lockdown.py -q
```
Expected: PASS — H3, citation-gate, and publishable-set-lockdown invariants unchanged (the debate path is gated OFF in every existing test, which omits `debate_route`).

- [ ] **Step 4: Confirm `irc memo` does not read the debate file (AC8)**

Run: `grep -rn "thesis_debate" src/irc/memo/ src/irc/commands/memo_cmd.py`
Expected: NO matches (the debate file is not a memo input). If any match appears, it is a bug — STOP and remove it.

- [ ] **Step 5: Confirm the `基金概况` acceptance grep stays green (constraints)**

Run: `grep -rn "基金概况" src/irc/opportunity/debate.py`
Expected: NO matches (no new fetch code; the forbidden literal must not appear).

- [ ] **Step 6: Lint + full suite**

Run: `uv run ruff check src tests`
Expected: no errors (line-length 100, py312).

Run: `uv run pytest -q`
Expected: full suite green; the 2 live tests skipped.

- [ ] **Step 7: Commit**

```bash
git add tests/commands/test_opportunity_cmd_adversarial.py
git commit -m "test(005): lock canonical byte-equality + no-citation under --adversarial"
```

---

## Task 8: Documentation — CONTEXT.md glossary

**Files:**
- Modify: `CONTEXT.md`

- [ ] **Step 1: Add the glossary section**

Append a new section to `CONTEXT.md` (place near the opportunity/discipline terminology):

```markdown
## Adversarial debate (advisory) — `--adversarial`

- **`--adversarial`** — opt-in flag on `irc opportunity` (default OFF). When OFF, the
  stage makes zero thesis-LLM calls and outputs are byte-identical to today. When ON,
  for each **publishable** `OpportunityRow` (the H3 `evidence_gaps == ()` set, after the
  citation gate) it runs a paired bull/bear debate and writes one advisory file. Permitted
  on canonical `outputs/<date>/` paths (unlike `--limit`, it touches no row).
- **`thesis_defend` / `thesis_falsify`** — sibling LLM tasks (`config/llm.yaml`), both
  `deepseek-reasoner`. `thesis_defend` steelmans the BULL case; `thesis_falsify` steelmans
  the BEAR case, over the **same** thesis card (`name_cn` / derived `thesis_state` /
  `opportunity_reason` / top-N `thesis_evidence`).
- **`DefenseResult(arguments)` / card-shaped `FalsificationResult(conditions)`** — frozen,
  single-tuple result types in `src/irc/opportunity/debate.py`. DISTINCT from the
  theme-shaped `research/falsification.py::FalsificationResult` (which argues over a free-text
  theme summary, has zero callers, and is NOT reused — ADR 0011 §3).
- **`ThesisDebate`** — a paired (`defense`, `falsification`) per publishable row.
- **`thesis_debate.md`** — the 6th, additive advisory artifact. NOT one of the five canonical
  artifacts, NOT in the H3 partition, NOT in SAME-3 set-equality, NOT a memo input, and
  **EXEMPT from the two-run byte-equality / publishable-set-lockdown determinism contract**
  (it is an LLM artifact — ADR 0011 §2). The pure renderer
  `compose_thesis_debate_markdown` IS deterministic; only the upstream LLM
  `arguments`/`conditions` are not. Advisory-only: sets no state, owns no citation
  (`derive_thesis_from_evidence` remains the sole `thesis_state` owner; Policy B unchanged).
```

- [ ] **Step 2: Commit**

```bash
git add CONTEXT.md
git commit -m "docs(005): CONTEXT.md adversarial-debate glossary"
```

---

## Acceptance-criteria → task map (self-review)

| AC | Covered by |
| --- | --- |
| AC1 — `thesis_defend` registered | Task 1 |
| AC2 — `--adversarial` flag, default off | Task 5 (Steps 5–6) |
| AC3 — flag-off byte-identical + no LLM call | Task 5 (`test_flag_off_*`), Task 7 (`test_canonical_artifacts_byte_identical_*`) |
| AC4 — `DefenseResult` mirrors `FalsificationResult` | Task 2 |
| AC5 — both halves run only when on (`2 × n`) | Task 5 (`test_flag_on_writes_debate_and_runs_both_halves`) |
| AC6 — advisory file only | Task 5 (`test_debate_file_not_a_canonical_artifact`) |
| AC7 — no state/gate/classifier/Policy-B change | Task 7 (`test_canonical_artifacts_byte_identical_*`) + Step 3 (existing suites green) |
| AC8 — memo pillars untouched | Task 7 (Step 4 grep) |
| AC9 — no new citation | Task 4 (`test_renderer_emits_no_citation_marker`) + Task 7 (`test_debate_file_introduces_no_citation_id`) |
| AC10 — pure logic unit-testable; renderer deterministic | Task 2 (mocked), Task 3 (`pair_debate`), Task 4 (`test_renderer_is_deterministic`) |
| AC11 — LLM at the edge; live double-gated | Task 2/3 (mocked `call_chat`), Task 6 (live) |
| AC12 — per-row failure isolation | Task 3 (`test_run_debates_isolates_per_row_failure`), Task 5 (`test_per_row_failure_renders_placeholder_*`) |
| AC13 — cost opt-in (`2 × n` vs 0) | Task 5 call-count assertions; documented in CONTEXT.md (Task 8) |
| AC14 — size + TDD budget | Task 4 Step 5 (`wc -l`), red-first ordering throughout, `tests/opportunity/test_debate.py` mirrors source, CONTEXT.md (Task 8) |

## Final verification (run after all tasks)

```bash
uv run pytest -q                         # full suite green; 2 live tests skipped
uv run ruff check src tests              # clean
wc -l src/irc/opportunity/debate.py      # < 200
uv run irc opportunity --help            # lists --adversarial
```
