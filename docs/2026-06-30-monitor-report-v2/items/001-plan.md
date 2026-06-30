# Monitor Report v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe the `irc monitor` daily brief around a fact-backed **market composite** decision anchor + **news overlay** delta, add per-score annotations, three pure charts, numbered citations, a 限购 actionability tag, an inline forward-scorer (anti-staleness), and log+score the market composite — all with **no change to composite-`C` math, weights, gating, `published_state`, or `_ENGINE_VERSION` (stays "3")**.

**Architecture:** All scoring stays untouched. New value is **render-derived** from the existing `signal.contributions` (Comp 1/2/3) or **additive** to the eval ledger/scorer (Comp 0/6). Five new pure modules under `src/irc/monitor/` are unit-tested in isolation; the only new I/O is the inline forward-eval invocation in `monitor_cmd` (contained, never changes exit code) and one new ledger field. `render_report` and every `render_*` stay PURE (no I/O, no JS, no remote refs).

**Tech Stack:** Python 3.12+, `uv`, pytest, frozen dataclasses, pure-function cores, inline SVG/HTML (no JS). Entry: `uv run pytest`, `uv run ruff check`.

---

## Source-of-truth grounding (read before any task)

Spec: `docs/2026-06-30-monitor-report-v2/items/001-spec.md`. Conventions: `CLAUDE.md` (TDD red→green→refactor, pure functions, frozen dataclasses, files <200 lines, functions <20 lines, I/O at edges), `CONTEXT.md` (Market composite / News overlay / `_FAMILY_OF` / dual-coverage gate / 16-hex citation IDs / `基金概况` forbidden).

**Real symbols this plan depends on (verified against code, NOT invented):**

- `src/irc/monitor/signal.py` — `_FAMILY_OF` (dict: trend→price-momentum, valuation→valuation, heat→crowding, macro_tilt→news, constituent→news, flow→capital-flow), `_bias(c: float, bands: dict[str,float]) -> str` (returns `ADD_BIAS`/`REDUCE_BIAS`/`NEUTRAL`; uses `bands["buy"]`/`bands["sell"]`), `compute_signal`, `_contributions` (sets `renorm_weight = w/avail`).
- `src/irc/monitor/types.py` — `FactorContribution(name, renorm_weight, value, contribution, confidence, eligible, reason)`, `SignalRecord(fund_id, status, bias, composite, signal_confidence, available_weight, present_families, contributions, divergence_codes)`, `MonitorFund(... bands ...)`, `FactorScore`.
- `src/irc/monitor/factor_maps.py` — `_VALUATION_MAP` (cheap=1.0, reasonable_low=0.5, fair=0.0, expensive=-0.5, very_expensive=-1.0), `_FLOW_BANDS`, `heat_score` (calm caps +0.3, overheated -1.0).
- `src/irc/monitor/heat_fetch.py` — `parse_purchase_status(table, fund_id) -> bool|None`, `heat_inputs_for(fund_id, *, purchase_table) -> (restricted, aum_delta_pct)`, `_RESTRICTION_CAP_THRESHOLD=1e8`, `_CODE_COL="基金代码"`, `_STATUS_COL="申购状态"`, `_CAP_COL="日累计限定金额"`, `_OPEN_STATUSES={"开放申购"}`.
- `src/irc/monitor/render_html.py` — `render_report(views, provenance, *, prior_signal, now, gates=None, panel_rows=(), predictive_panel=None)`, `_card`, `_summary_row`, `_appendix`, `_CSS`, `_badge`, `_markers`.
- `src/irc/monitor/render_cards.py` — `_claim_html(claim) -> str` (renders `[ref:{cid}]`), `verdict_block_html`, `narrative_sections_html`, `risk_block_html`.
- `src/irc/monitor/render_factors.py` — `factor_table_html(rec, scores, freshness)`, `CANONICAL_FACTOR_ORDER`, `_present_row`, `_na_row`.
- `src/irc/monitor/render_types.py` — `FundView(...)`, `Provenance(...)`.
- `src/irc/monitor/eval/forward_log.py` — `ledger_row(*, run_date, fund_id, written_at, signal, nav_acc, nav_unit, as_of_date, published_state, gate, manifest_versions) -> dict`, `latest_per_key`, `append_ledger`.
- `src/irc/monitor/eval/forward_score.py` — `ForwardRow` (frozen), `score_forward(...) -> (list[ForwardRow], excl)`.
- `evals/monitor_forward/metrics.py` — `build_metric_reports(*, forward_rows, retro_points, seed, momentum_by_key) -> (list[MetricReport], details)`, `_hit_rate_report`, `_composite_rows`.
- `evals/monitor_forward/runner.py` — `run(repo_root: Path) -> int` (this is what `irc eval monitor_forward` dispatches via the registry `EvalStageSpec("monitor_forward", "evals.monitor_forward.runner", "active", False)`).
- `src/irc/monitor/eval/predictive_panel.py` — `predictive_validity_panel_html(*, model)`, reads `PredictiveMetricView` rows.
- `src/irc/commands/monitor_cmd.py` — `_ENGINE_VERSION="3"`, `_write_eval_artifacts`, `_predictive_panel_model`, `_is_stale`, `STALE_EVAL_DAYS` (imported from `irc.monitor.eval.constants`), `_process_fund`, `run_monitor`, `_write_outputs`, `_now_iso`, `fetch_purchase_table` (one call/run), `_make_view`.

**Symbol-name judgment calls (spec text vs real code):**
1. Spec §10 says "`forward_score.py` adds a `market_composite_directional` population". The real hit-rate builder lives in `evals/monitor_forward/metrics.py::build_metric_reports` (which imports `ForwardRow` from `src/irc/monitor/eval/forward_score.py`). `ForwardRow` carries the per-row data; `build_metric_reports` builds populations. **This plan adds `market_composite`/`market_bias` fields to `ForwardRow` (Task 4.2) and the `market_composite_directional` population in `metrics.py` (Task 4.4).** Both files are touched, consistent with the spec's data-vs-population split.
2. Spec §4 names the inline edge `_run_forward_eval(root, today)`. The dispatch target is `evals.monitor_forward.runner.run(repo_root)` — it takes only `repo_root: Path`, NOT `today` (it computes `today` internally). **The new edge wraps `runner.run(root)`; `today` is unused by the runner but kept in the signature for symmetry with the spec and to gate the post-run staleness assertion. The plan documents this.**
3. Spec §12 / §5 talk about a "summary table" `市场面` column and a per-card `decision line`. The real summary builder is `_summary_row` and cards are built in `_card`. Plan wires there.
4. `STALE_EVAL_DAYS` is in `src/irc/monitor/eval/constants.py` (imported by `monitor_cmd`). No new constant needed.

**Hard non-goals to honor in EVERY task (spec §2/§16):**
- No change to composite-`C` math, factor weights, gating, `published_state`, or `_ENGINE_VERSION` (stays `"3"`).
- Full composite `C` stays the canonical published/tracked signal (header badge, `monitor.json`, `forward_ledger.raw_composite`, the gate, `EVAL_GATED`, validation panel — all unchanged).
- `render_report` + every `render_*` stay PURE (no I/O, no JS, no remote refs).
- No new network or LLM calls.
- `market_composite` ledger field is **additive / back-compat** (old rows without it must not crash the scorer).

---

## File structure (created / modified)

**New pure modules:**
- `src/irc/monitor/market_composite.py` — `MarketCompositeView` + `market_composite_view` (Comp 1).
- `src/irc/monitor/annotate.py` — `factor_annotation` + `composite_annotation` (Comp 2).
- `src/irc/monitor/render_heatmap.py` — `factor_heatmap_html` (Comp 3a).
- `src/irc/monitor/render_timeline.py` — `BiasTimeline` + `bias_timeline_html` (Comp 3b).
- `src/irc/monitor/render_contrib.py` — `contribution_bars_svg` (Comp 3c).

**New test files (mirror src):**
- `tests/monitor/test_market_composite.py`
- `tests/monitor/test_annotate.py`
- `tests/monitor/test_render_heatmap.py`
- `tests/monitor/test_render_timeline.py`
- `tests/monitor/test_render_contrib.py`
- `tests/monitor/test_render_html_citations.py` (Comp 4)
- `tests/commands/test_monitor_cmd_forward_eval.py` (Comp 0)
- `tests/commands/test_monitor_cmd_market_composite.py` (Comp 1/6 wiring at the edge)
- `tests/commands/test_monitor_cmd_purchase_tag.py` (Comp 5 wiring)

**Modified:**
- `src/irc/monitor/eval/forward_log.py` + `tests/monitor/eval/test_forward_log.py` (Comp 6 ledger field)
- `src/irc/monitor/eval/forward_score.py` + `tests/monitor/eval/test_forward_score.py` (Comp 6 ForwardRow field)
- `evals/monitor_forward/metrics.py` + `tests/evals/test_monitor_forward_metrics.py` (Comp 6 population)
- `src/irc/monitor/render_types.py` (Comp 1/5: `FundView` gains `market_view`, `purchase_tag`)
- `src/irc/monitor/render_cards.py` + `tests/monitor/test_render_cards.py` (Comp 2/4: decision line, numbered citations)
- `src/irc/monitor/render_factors.py` + `tests/monitor/test_render_factors.py` (Comp 2: 解读 column)
- `src/irc/monitor/render_html.py` + `tests/monitor/test_render_html.py` (Comp 1/3/4: orchestration, CitationIndex, summary col, charts)
- `src/irc/commands/monitor_cmd.py` + tests above (Comp 0/1/5/6 edge wiring)
- `docs/adr/0021-monitor-market-composite-decision-anchor.md` (new, §14)
- `docs/adr/0017-monitor-evidence-isolation.md` (§15: ledger contract note)
- `CONTEXT.md` (§3: terms already present — verify, no-op if so)
- `tests/monitor/golden/report.html` (regenerate golden once render changes land)

---

## Signature-change test discipline (apply where flagged)

Per [[feedback-test-scope-signature-changes]] (memory) and spec §12: when `FundView`, `render_report` params, `ledger_row`, or `ForwardRow`/`score_forward` change, you MUST run, after the change:
- `uv run pytest tests/monitor/` (whole dir is fine)
- `tests/commands/` **PER FILE** — the whole `tests/commands/` directory HANGS due to suite-ordering. Iterate file-by-file:
  ```
  uv run pytest tests/commands/test_monitor_cmd.py
  uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py
  uv run pytest tests/commands/test_monitor_cmd_predictive_panel.py
  uv run pytest tests/commands/test_monitor_cmd_nav_history.py
  uv run pytest tests/commands/test_monitor_cmd_heat.py
  uv run pytest tests/commands/test_monitor_cmd_trace.py
  uv run pytest tests/commands/test_monitor_cmd_valuation.py
  uv run pytest tests/commands/test_monitor_cmd_drilldown.py
  uv run pytest tests/commands/test_monitor_constituent.py
  uv run pytest tests/commands/test_monitor_cmd_forward_eval.py
  uv run pytest tests/commands/test_monitor_cmd_market_composite.py
  uv run pytest tests/commands/test_monitor_cmd_purchase_tag.py
  ```
- `uv run pytest tests/monitor/eval/ tests/evals/` (forward ledger/scorer/metrics)

Each step that triggers this discipline says **"RUN SIGNATURE-CHANGE SUITE"** and lists the exact commands.

---

# PHASE 1 — Anti-staleness + citations (Comp 0 + 4)

## Task 1.1: Inline forward-eval edge `_run_forward_eval` (Comp 0)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py`
- Test: `tests/commands/test_monitor_cmd_forward_eval.py`

- [ ] **Step 1: Write the failing test (edge contained + exit-code-safe)**

Create `tests/commands/test_monitor_cmd_forward_eval.py`:

```python
from __future__ import annotations
from pathlib import Path
import pytest
from irc.commands import monitor_cmd


def test_run_forward_eval_invokes_runner(monkeypatch, tmp_path):
    called = {}

    def fake_run(repo_root):
        called["root"] = repo_root
        return 1  # WARN — normal for monitor_forward

    monkeypatch.setattr(monitor_cmd, "_forward_eval_run", fake_run)
    rc = monitor_cmd._run_forward_eval(tmp_path, "2026-06-30")
    assert rc == 1
    assert called["root"] == tmp_path


def test_run_forward_eval_swallows_exception(monkeypatch, tmp_path):
    def boom(repo_root):
        raise RuntimeError("scorer blew up")

    monkeypatch.setattr(monitor_cmd, "_forward_eval_run", boom)
    # MUST NOT raise — Comp 0 containment: a scorer failure never crashes the run
    rc = monitor_cmd._run_forward_eval(tmp_path, "2026-06-30")
    assert rc is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_monitor_cmd_forward_eval.py -v`
Expected: FAIL — `AttributeError: module 'irc.commands.monitor_cmd' has no attribute '_run_forward_eval'` (and `_forward_eval_run`).

- [ ] **Step 3: Write minimal implementation**

In `src/irc/commands/monitor_cmd.py`, add near the other eval imports (after line 63):

```python
from evals.monitor_forward.runner import run as _forward_eval_run
```

Then add this helper after `_write_eval_artifacts` (after line 558, before `_is_stale`):

```python
def _run_forward_eval(root: Path, today: str) -> int | None:
    """EDGE (Comp 0): run the monitor_forward scorer inline so its artifact is
    same-day fresh. `today` is unused by the runner (it computes its own) but kept
    for symmetry with the spec + the staleness contract. Contained: a non-zero rc
    or any exception MUST NOT change `irc monitor`'s exit code — degrade to the
    pre-existing 'read latest artifact' path. Returns the scorer rc, or None on
    exception."""
    try:
        return _forward_eval_run(root)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("inline monitor_forward eval failed", exc_info=True)
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_monitor_cmd_forward_eval.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_forward_eval.py
git commit -m "feat(monitor): inline forward-eval edge (Comp 0, contained)"
```

## Task 1.2: Wire `_run_forward_eval` into `run_monitor` (Comp 0)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py:784-787` (the orchestration sequence in `run_monitor`)
- Test: `tests/commands/test_monitor_cmd_forward_eval.py` (extend)

- [ ] **Step 1: Write the failing test (ordering: eval runs after ledger append, before predictive panel; exit code unaffected)**

Append to `tests/commands/test_monitor_cmd_forward_eval.py`:

```python
def test_forward_eval_runs_after_ledger_before_panel(monkeypatch, tmp_path):
    order = []
    monkeypatch.setattr(monitor_cmd, "_write_eval_artifacts",
                        lambda *a, **k: order.append("artifacts"))
    monkeypatch.setattr(monitor_cmd, "_run_forward_eval",
                        lambda root, today: order.append("forward_eval") or 1)
    monkeypatch.setattr(monitor_cmd, "_predictive_panel_model",
                        lambda root, *, today: order.append("panel") or _PANEL_STUB)
    monkeypatch.setattr(monitor_cmd, "_write_outputs", lambda *a, **k: None)
    monkeypatch.setattr(monitor_cmd, "_write_drilldown", lambda *a, **k: None)
    monkeypatch.setattr(monitor_cmd, "record_command_run", lambda **k: None)
    _patch_min_pipeline(monkeypatch, tmp_path)  # see helper below

    rc = monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-30")
    assert rc == 0  # scorer WARN (rc 1) MUST NOT change monitor exit code
    assert order == ["artifacts", "forward_eval", "panel"]
```

Add the shared `_PANEL_STUB` + `_patch_min_pipeline` at the top of the file (mirror `test_monitor_cmd_eval_wiring.py`'s `_patch_pipeline` style — preflight_gate→0, load_monitor_config→`_Cfg`, resolve_funds→`[]`, load_yaml→`{}`, fetch_purchase_table→None, build providers/llm stubbed; reuse a minimal fund list of `[]` so `_process_fund` is never entered):

```python
from irc.monitor.eval.types import PredictivePanelModel
_PANEL_STUB = PredictivePanelModel(present=False, stale=False, artifact_date=None,
                                   metrics=(), review_flag=False)


class _Cfg:
    class history:
        minimum_observations = 2


def _patch_min_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(monitor_cmd, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(monitor_cmd, "load_monitor_config", lambda root: _Cfg())
    monkeypatch.setattr(monitor_cmd, "resolve_funds", lambda cfg: [])
    monkeypatch.setattr(monitor_cmd, "load_yaml", lambda *a, **k: {})
    monkeypatch.setattr(monitor_cmd, "fetch_purchase_table", lambda: None)
    monkeypatch.setattr(monitor_cmd, "load_trading_days", lambda *a, **k: None)
    monkeypatch.setattr(monitor_cmd, "_suite_eval", lambda *a, **k: ((), ()))
    monkeypatch.setattr(monitor_cmd, "_read_prior_signal", lambda *a, **k: None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_monitor_cmd_forward_eval.py::test_forward_eval_runs_after_ledger_before_panel -v`
Expected: FAIL — `order == ["artifacts", "panel"]` (forward_eval not yet called), assertion error.

- [ ] **Step 3: Write minimal implementation**

In `run_monitor`, between `_write_eval_artifacts(...)` (line 784-785) and `predictive_panel = _predictive_panel_model(...)` (line 786), insert:

```python
    _run_forward_eval(root, _today)  # Comp 0: same-day-fresh artifact; contained
```

So the sequence becomes:
```python
    _write_eval_artifacts(out, root, list(funds), views, bundles, gates,
                          run_date=_today, trading_days=trading_days)
    _run_forward_eval(root, _today)  # Comp 0: same-day-fresh artifact; contained
    predictive_panel = _predictive_panel_model(root, today=_today)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_monitor_cmd_forward_eval.py -v`
Expected: PASS (all three tests).

- [ ] **Step 5: RUN SIGNATURE-CHANGE SUITE** (run_monitor body changed — verify no regression)

Run (per-file, NOT the whole dir):
```
uv run pytest tests/commands/test_monitor_cmd.py tests/commands/test_monitor_cmd_eval_wiring.py tests/commands/test_monitor_cmd_predictive_panel.py
```
Expected: PASS for all.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_forward_eval.py
git commit -m "feat(monitor): run forward-eval inline after ledger, before panel (Comp 0)"
```

## Task 1.3: CitationIndex — numbered citations data model (Comp 4)

**Files:**
- Modify: `src/irc/monitor/render_html.py`
- Test: `tests/monitor/test_render_html_citations.py`

- [ ] **Step 1: Write the failing test (1-based N in appendix first-seen order; cid→source/title)**

Create `tests/monitor/test_render_html_citations.py`:

```python
from __future__ import annotations
import re
from irc.monitor.render_html import build_citation_index
from irc.monitor.evidence import make_evidence_item
from irc.monitor.render_types import FundView
from irc.monitor.types import NarrativeDoc, SignalRecord


def _view(fid, evs):
    rec = SignalRecord(fid, "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    return FundView(fund_id=fid, name_cn="x", latest_nav=1.0, as_of_date="2026-06-30",
                    nav_series=(), signal=rec, narrative=NarrativeDoc(fid, (), (), (), "ok"),
                    evidence_pool=evs, return_table={}, factor_freshness={},
                    missing_factor_reasons=(), factor_scores=())


def test_citation_index_numbers_in_appendix_first_seen_order():
    a = make_evidence_item("Reuters", "title A", "2026-06-30", "https://a", "001")
    b = make_evidence_item("Bloomberg", "title B", "2026-06-30", "https://b", "001")
    idx = build_citation_index((_view("001", (a, b)),))
    assert idx.number(a.citation_id) == 1
    assert idx.number(b.citation_id) == 2
    assert idx.source(a.citation_id) == "Reuters"
    assert idx.title(a.citation_id) == "title A"


def test_citation_index_dedups_repeated_cid():
    a = make_evidence_item("Reuters", "title A", "2026-06-30", "https://a", "001")
    idx = build_citation_index((_view("001", (a,)), _view("002", (a,))))
    assert idx.number(a.citation_id) == 1
    assert len(idx.entries) == 1


def test_citation_index_unknown_cid_returns_none():
    idx = build_citation_index((_view("001", ()),))
    assert idx.number("deadbeefdeadbeef") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_html_citations.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_citation_index'`.

- [ ] **Step 3: Write minimal implementation**

In `src/irc/monitor/render_html.py`, add after the imports (after line 14) and before `_NO_CALL`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class CitationIndex:
    """PURE cid → 1-based N + (source, title), first-seen = appendix order."""
    entries: tuple[tuple[str, str, str], ...]   # (cid, source, title)

    def _pos(self, cid: str) -> int | None:
        for i, (c, _, _) in enumerate(self.entries):
            if c == cid:
                return i
        return None

    def number(self, cid: str) -> int | None:
        p = self._pos(cid)
        return None if p is None else p + 1

    def source(self, cid: str) -> str | None:
        p = self._pos(cid)
        return None if p is None else self.entries[p][1]

    def title(self, cid: str) -> str | None:
        p = self._pos(cid)
        return None if p is None else self.entries[p][2]


def build_citation_index(views: tuple[FundView, ...]) -> CitationIndex:
    """PURE: appendix-order (first-seen) cid index over every fund's evidence pool.
    Same iteration order as _appendix so superscript-N == appendix-N."""
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for v in views:
        for ev in v.evidence_pool:
            if ev.citation_id in seen:
                continue
            seen.add(ev.citation_id)
            out.append((ev.citation_id, ev.source, ev.title))
    return CitationIndex(tuple(out))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_html_citations.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_html.py tests/monitor/test_render_html_citations.py
git commit -m "feat(monitor): CitationIndex (numbered, first-seen order) (Comp 4)"
```

## Task 1.4: Thread CitationIndex into `_claim_html` (numbered superscript anchors) (Comp 4)

**Files:**
- Modify: `src/irc/monitor/render_cards.py:21-24` (`_claim_html`) and the three callers (`_comment`, `risk_block_html`, `narrative_sections_html`)
- Test: `tests/monitor/test_render_cards.py` (extend)

- [ ] **Step 1: Write the failing test (superscript anchor + title; no raw `[ref:` left)**

Append to `tests/monitor/test_render_cards.py` (match existing imports/fixtures; add what's missing):

```python
import re
from irc.monitor.render_html import CitationIndex
from irc.monitor.render_cards import _claim_html
from irc.monitor.types import Claim


def test_claim_html_renders_numbered_superscript_with_title():
    cid = "0123456789abcdef"
    idx = CitationIndex(((cid, "Reuters", "real yields up"),))
    claim = Claim("金价承压", "consistent_with", (cid,))
    html = _claim_html(claim, idx)
    assert f'href="#ev-{cid}"' in html
    assert "<sup>" in html and "</sup>" in html
    assert ">1</a>" in html
    assert 'title="Reuters — real yields up"' in html
    assert "[ref:" not in html  # no raw marker leaks


def test_claim_html_unknown_cid_drops_marker_no_raw_ref():
    idx = CitationIndex(())
    claim = Claim("x", "unknown", ("ffffffffffffffff",))
    html = _claim_html(claim, idx)
    assert "[ref:" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_cards.py::test_claim_html_renders_numbered_superscript_with_title -v`
Expected: FAIL — `_claim_html() takes 1 positional argument but 2 were given`.

- [ ] **Step 3: Write minimal implementation**

In `src/irc/monitor/render_cards.py`, replace `_claim_html` (lines 21-24) with:

```python
def _sup(cid: str, idx) -> str:
    """One numbered superscript anchor; '' when the cid isn't in the index."""
    n = idx.number(cid)
    if n is None:
        return ""
    title = escape(f"{idx.source(cid)} — {idx.title(cid)}")
    return f'<sup><a href="#ev-{cid}" title="{title}">{n}</a></sup>'


def _claim_html(claim: Claim, idx) -> str:
    text = escape(claim.claim)
    refs = "".join(_sup(cid, idx) for cid in claim.citation_ids)
    return f"<p>{text} {refs}</p>"
```

Update the three callers in the same file to thread `idx`:
- `_comment(narr)` → `_comment(narr, idx)`; its body `"".join(f'<blockquote>{_claim_html(c)}</blockquote>' for c in lead)` → `_claim_html(c, idx)`.
- `verdict_block_html(rec, narr)` → `verdict_block_html(rec, narr, idx)`; pass `idx` to `_comment`.
- `risk_block_html(rec, narr)` → `risk_block_html(rec, narr, idx)`; `[_claim_html(c) for c in narr.risk_commentary]` → `_claim_html(c, idx)`.
- `narrative_sections_html(narr)` → `narrative_sections_html(narr, idx)`; `"".join(_claim_html(c) for c in narr.price_action_commentary)` → `_claim_html(c, idx)`.

- [ ] **Step 4: Run the card tests (existing callers now require idx — they will fail until Task 1.5 updates render_html; pass an empty CitationIndex in the new tests only)**

Run: `uv run pytest tests/monitor/test_render_cards.py -v`
Expected: the two NEW tests PASS; pre-existing tests that call `verdict_block_html`/`risk_block_html`/`narrative_sections_html` with the old arity will FAIL. **Fix them now** by passing `CitationIndex(())` (or a populated one matching the claim cids) as the new `idx` arg in each existing test in this file. After the fix, re-run:

Run: `uv run pytest tests/monitor/test_render_cards.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_cards.py tests/monitor/test_render_cards.py
git commit -m "feat(monitor): numbered superscript citations in claims (Comp 4)"
```

## Task 1.5: Numbered appendix `<li>` + thread idx through `render_report`/`_card` (Comp 4)

**Files:**
- Modify: `src/irc/monitor/render_html.py` (`_appendix`, `_card`, `render_report`)
- Test: `tests/monitor/test_render_html_citations.py` (extend), `tests/monitor/test_render_html.py` (update for new render output)

- [ ] **Step 1: Write the failing test (appendix `N.` prefix + alignment with superscript)**

Append to `tests/monitor/test_render_html_citations.py`:

```python
import re
from irc.monitor.render_html import render_report
from irc.monitor.render_types import Provenance
from irc.monitor.types import Claim


def test_appendix_numbers_align_with_superscripts():
    a = make_evidence_item("Reuters", "title A", "2026-06-30", "https://a", "001")
    rec = SignalRecord("001", "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    narr = NarrativeDoc("001",
                        price_action_commentary=(Claim("c", "consistent_with", (a.citation_id,)),),
                        signal_rationale_commentary=(), risk_commentary=(), status="ok")
    view = FundView(fund_id="001", name_cn="x", latest_nav=1.0, as_of_date="2026-06-30",
                    nav_series=(), signal=rec, narrative=narr, evidence_pool=(a,),
                    return_table={}, factor_freshness={}, missing_factor_reasons=(),
                    factor_scores=())
    html = render_report((view,), Provenance("3", "1", "1", ""),
                         prior_signal=None, now="2026-06-30T09:00:00+08:00")
    # appendix li carries a leading "1." and id ev-{cid}
    assert f'<li id="ev-{a.citation_id}">1.' in html
    # the in-text superscript anchor links to the same id with number 1
    assert f'href="#ev-{a.citation_id}" title="Reuters — title A">1</a>' in html
    # no raw [ref:cid] survives anywhere
    assert "[ref:" not in html


def test_no_script_or_remote_refs_in_report():
    html = render_report((), Provenance("3", "1", "1", ""), prior_signal=None,
                         now="2026-06-30T09:00:00+08:00")
    assert "<script" not in html.lower()
    assert "http://" not in html and "https://" not in html
    assert "基金概况" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_html_citations.py::test_appendix_numbers_align_with_superscripts -v`
Expected: FAIL — appendix still emits `<code>[ref:cid]</code>` (no leading `N.`), superscript not present.

- [ ] **Step 3: Write minimal implementation**

In `render_html.py`:

(a) Replace `_appendix(views)` (lines 183-200) to number `<li>` in first-seen order and drop the raw `[ref:]` code marker:

```python
def _appendix(views: tuple[FundView, ...], idx: CitationIndex) -> str:
    items = []
    for n, (cid, source, title) in enumerate(idx.entries, start=1):
        items.append(
            f'<li id="ev-{cid}">{n}. {escape(title)} — {escape(source)}</li>'
        )
    return (
        "<details><summary>证据 / Evidence</summary><ol>"
        + "".join(items)
        + "</ol></details>"
    )
```

> Note: the appendix loses its dependence on per-view dedup since `idx.entries` is already first-seen-deduped (Task 1.3). `views` kept in the signature for call-site symmetry; mark it used or drop the param — drop it: change to `def _appendix(idx: CitationIndex) -> str:` and remove `views`. (Date was previously shown; the spec's appendix line is `N. {title} — {source}` with `title` tooltip carrying source on the in-text anchor. The appendix date is dropped to match spec §8 wording — acceptable presentation change; the golden test will be regenerated.)

(b) Thread `idx` through `_card`:

```python
def _card(view: FundView, gate: GateDecision | None, idx: CitationIndex) -> str:
    chart = render_nav_chart(view.nav_series, markers=_markers(view))
    return (
        f'<section class="fund-card" id="fund-{view.fund_id}">'
        f"<h2>{escape(view.name_cn)} ({view.fund_id}) {_badge(view, gate)}</h2>"
        f"{verdict_block_html(view.signal, view.narrative, idx)}"
        f"{chart}"
        f"{returns_table_html(view.return_table)}"
        f"{factor_table_html(view.signal, view.factor_scores, view.factor_freshness)}"
        f"{_drilldown_block(view)}"
        f"{narrative_sections_html(view.narrative, idx)}"
        f"{risk_block_html(view.signal, view.narrative, idx)}"
        "</section>"
    )
```

(c) In `render_report`, build the index once and thread it:

```python
    idx = build_citation_index(views)
    ...
    cards = "".join(_card(v, g.get(v.fund_id), idx) for v in views)
    ...
        + header + outage_note + _EXPLAINER + summary + cards + panel + predictive
        + _appendix(idx) + "</body></html>"
```

(d) Update the CSS string `_CSS`: no functional CSS change needed for `<sup>` (browser default). Optionally add `"sup a{text-decoration:none}"` inside `_CSS` for cleaner rendering (still byte-stable). Add it to keep the golden stable.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_html_citations.py -v`
Expected: PASS (all 5 tests in this file).

- [ ] **Step 5: Fix + regenerate the golden + existing render_html tests**

Run: `uv run pytest tests/monitor/test_render_html.py tests/monitor/test_render_html_eval.py tests/monitor/test_render_html_predictive.py -v`
Expected: some FAIL on the changed appendix / superscript output and the golden `report.html` (`test_golden_file` at `tests/monitor/test_render_html.py:158`).

**Golden regeneration (no auto-regen helper exists — it is a deliberate byte-for-byte overwrite).** The golden is produced by exactly `render_report((_view(),), _prov(), prior_signal=None, now=_NOW)` (see `test_golden_file`). Regenerate it with a one-shot script run from the repo root:
```bash
uv run python -c "
import sys; sys.path.insert(0, 'tests/monitor')
from test_render_html import _view, _prov, _NOW
from irc.monitor.render_html import render_report
from pathlib import Path
html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
Path('tests/monitor/golden/report.html').write_text(html, encoding='utf-8')
print('golden regenerated', len(html), 'bytes')
"
```
**Before overwriting, eyeball the new output** for the expected v2 changes (numbered `<sup>`, numbered `<ol>` appendix, no `[ref:`, decision line, 解读 column) and confirm NO `<script>`/`http`/`基金概况` — only then commit the fixture. For assertion-based tests, update expected strings to the numbered form (no `[ref:`). Re-run until green.

- [ ] **Step 6: RUN SIGNATURE-CHANGE SUITE** (`_card`/`render_report` render output changed; `render_report` params unchanged but cards differ)

Run:
```
uv run pytest tests/monitor/
uv run pytest tests/commands/test_monitor_cmd.py tests/commands/test_monitor_cmd_eval_wiring.py tests/commands/test_monitor_cmd_trace.py
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/irc/monitor/render_html.py tests/monitor/ 
git commit -m "feat(monitor): numbered appendix + threaded CitationIndex; regen golden (Comp 4)"
```

---

# PHASE 2 — Market composite + news overlay + presentation + annotations (Comp 1 + 2)

## Task 2.1: `market_composite.py` core (Comp 1)

**Files:**
- Create: `src/irc/monitor/market_composite.py`
- Test: `tests/monitor/test_market_composite.py`

- [ ] **Step 1: Write the failing test (renorm truth table)**

Create `tests/monitor/test_market_composite.py`:

```python
from __future__ import annotations
import math
from irc.monitor.market_composite import MarketCompositeView, market_composite_view
from irc.monitor.types import FactorContribution, SignalRecord

_BANDS = {"buy": 0.40, "sell": -0.40}


def _sig(contribs, composite):
    return SignalRecord(fund_id="x", status="ok", bias=None, composite=composite,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=(), contributions=tuple(contribs),
                        divergence_codes=())


def _c(name, renorm_weight, value):
    return FactorContribution(name, renorm_weight, value, renorm_weight * value, 1.0, True, "")


def test_full_active_four_market_factors_renormalized():
    # market factors w'=.25 each summing to 1.0 already (no news present)
    contribs = [_c("trend", .25, .8), _c("valuation", .25, .4),
                _c("flow", .25, -.2), _c("heat", .25, .0)]
    sig = _sig(contribs, composite=round(sum(c.contribution for c in contribs), 4))
    v = market_composite_view(sig, bands=_BANDS)
    # only market factors → renorm is identity; market composite == C
    assert math.isclose(v.composite, sig.composite, abs_tol=1e-9)
    assert v.news_delta == 0.0
    assert v.eligible_market_factors == 4
    assert v.bias == "ADD_BIAS"  # .25*.8 + .25*.4 + .25*-.2 + 0 = .25 -> wait: see next


def test_market_excludes_news_and_renormalizes():
    # market w' = trend .3, flow .2 (sum .5); news macro_tilt .5 value 1.0
    contribs = [_c("trend", .3, 1.0), _c("flow", .2, 0.0), _c("macro_tilt", .5, 1.0)]
    C = round(sum(c.contribution for c in contribs), 4)  # .3 + 0 + .5 = .8
    sig = _sig(contribs, C)
    v = market_composite_view(sig, bands=_BANDS)
    # market-only: renorm over (.3,.2) → (.6,.4); composite = .6*1.0 + .4*0.0 = .6
    assert math.isclose(v.composite, 0.6, abs_tol=1e-9)
    assert math.isclose(v.news_delta, C - 0.6, abs_tol=1e-9)  # .8 - .6 = .2
    assert v.eligible_market_factors == 2
    assert v.bias == "ADD_BIAS"  # .6 >= .40


def test_qdii_trend_and_heat_only():
    contribs = [_c("trend", .7, -.5), _c("heat", .3, .3)]
    C = round(sum(c.contribution for c in contribs), 4)
    sig = _sig(contribs, C)
    v = market_composite_view(sig, bands=_BANDS)
    assert math.isclose(v.composite, C, abs_tol=1e-9)  # no news → identity
    assert v.news_delta == 0.0
    assert v.eligible_market_factors == 2
    assert v.bias == "REDUCE_BIAS"  # -.5*.7 + .3*.3 = -.35+.09 = -.26? NEUTRAL


def test_none_when_no_market_factor_present():
    contribs = [_c("macro_tilt", .6, 1.0), _c("constituent", .4, .5)]
    sig = _sig(contribs, round(sum(c.contribution for c in contribs), 4))
    assert market_composite_view(sig, bands=_BANDS) is None
```

> NOTE TO IMPL: re-derive each `assert v.bias == ...` from the actual arithmetic before finalizing; the comments above are guidance, not gospel. Bands buy=+0.40/sell=-0.40. For `test_qdii_trend_and_heat_only`: composite = -0.26 → NEUTRAL (not REDUCE). Fix that assertion to `NEUTRAL`. For `test_full_active_four_market_factors_renormalized`: composite = 0.25 → NEUTRAL; fix to `NEUTRAL`. Compute exactly, then lock the expected.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_market_composite.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.market_composite'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/market_composite.py`:

```python
"""PURE Comp 1: render-derived market composite (news-excluded, renormalized) +
news overlay delta. NO engine change — reads signal.contributions only. The
market/news split reuses signal._FAMILY_OF (one source of truth, shared with
backtest.py)."""
from __future__ import annotations
from dataclasses import dataclass
from irc.monitor.signal import _FAMILY_OF, _bias
from irc.monitor.types import SignalRecord

_NEWS_FAMILY = "news"


@dataclass(frozen=True)
class MarketCompositeView:
    composite: float          # renormalized market-only composite
    bias: str                 # _bias(composite, fund.bands)
    news_delta: float         # C - composite
    eligible_market_factors: int


def _is_market(name: str) -> bool:
    return _FAMILY_OF.get(name) != _NEWS_FAMILY


def market_composite_view(
    signal: SignalRecord, *, bands: dict[str, float],
) -> MarketCompositeView | None:
    """Renormalize the non-news contributions to sum-of-weights 1 and map the
    market-only composite to a bias via the SAME bands the full signal uses.
    Returns None iff no market factor is present."""
    market = [c for c in signal.contributions if _is_market(c.name)]
    total_w = sum(c.renorm_weight for c in market)
    if not market or total_w <= 0:
        return None
    composite = round(sum((c.renorm_weight / total_w) * c.value for c in market), 4)
    return MarketCompositeView(
        composite=composite,
        bias=_bias(composite, bands),
        news_delta=round(signal.composite - composite, 4),
        eligible_market_factors=len(market),
    )
```

- [ ] **Step 4: Lock expected biases, then run to verify it passes**

Re-derive each expected `bias`/`composite` arithmetically, fix the test asserts, then:
Run: `uv run pytest tests/monitor/test_market_composite.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/market_composite.py tests/monitor/test_market_composite.py
git commit -m "feat(monitor): market_composite_view (news-excluded anchor) (Comp 1)"
```

## Task 2.2: `annotate.py` core — per-factor + composite annotations (Comp 2)

**Files:**
- Create: `src/irc/monitor/annotate.py`
- Test: `tests/monitor/test_annotate.py`

- [ ] **Step 1: Write the failing test (per-factor band truth tables + news marks + N/A)**

Create `tests/monitor/test_annotate.py`:

```python
from __future__ import annotations
import pytest
from irc.monitor.annotate import factor_annotation, composite_annotation
from irc.monitor.types import FactorContribution, SignalRecord


@pytest.mark.parametrize("value,expected", [
    (0.8, "强上行"), (0.4, "上行"), (0.0, "横盘"), (-0.4, "下行"), (-0.8, "强下行"),
])
def test_trend_bands(value, expected):
    assert factor_annotation("trend", value) == expected


@pytest.mark.parametrize("value,expected", [
    (1.0, "便宜"), (0.5, "中性偏低"), (0.0, "估值中性"), (-0.5, "偏贵"), (-1.0, "很贵"),
])
def test_valuation_bands(value, expected):
    assert factor_annotation("valuation", value) == expected


@pytest.mark.parametrize("value,expected", [
    (1.0, "强净流入"), (0.5, "净流入"), (0.0, "均衡"), (-0.5, "净流出"), (-1.0, "强净流出"),
])
def test_flow_bands(value, expected):
    assert factor_annotation("flow", value) == expected


@pytest.mark.parametrize("value,expected", [
    (0.3, "低拥挤·平静"), (-0.5, "偏拥挤"), (-1.0, "过热"),
])
def test_heat_asymmetric(value, expected):
    assert factor_annotation("heat", value) == expected


def test_macro_tilt_always_marks_news_volatile():
    assert factor_annotation("macro_tilt", 0.6) == "新闻面偏多·新闻面·易变"
    assert factor_annotation("macro_tilt", 0.0) == "中性·新闻面·易变"
    assert factor_annotation("macro_tilt", -0.6) == "偏空·新闻面·易变"


def test_constituent_marks_news():
    assert factor_annotation("constituent", 0.6) == "成分质量高·新闻面"
    assert factor_annotation("constituent", 0.0) == "中等·新闻面"
    assert factor_annotation("constituent", -0.6) == "偏弱·新闻面"


def test_na_value_returns_empty():
    assert factor_annotation("trend", None) == ""
    assert factor_annotation("valuation", None) == ""


def test_unknown_factor_returns_empty():
    assert factor_annotation("mystery", 0.5) == ""


def test_composite_annotation_names_market_vs_news():
    contribs = (
        FactorContribution("trend", .5, .1, .05, 1.0, True, ""),
        FactorContribution("macro_tilt", .5, .8, .40, 1.0, True, ""),
    )
    sig = SignalRecord("x", "ok", "ADD_BIAS", 0.45, 1.0, 1.0, (), contribs, ())
    text = composite_annotation(sig)
    assert "市场面" in text and "新闻叠加" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_annotate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.annotate'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/annotate.py`:

```python
"""PURE Comp 2: render-derived per-factor + composite annotations. Sign
conventions match factor_maps.py. The two news factors (macro_tilt, constituent)
carry a ·新闻面 mark so a reader sees which annotations belong to the volatile
overlay. NO engine change — annotations are presentation only."""
from __future__ import annotations
from irc.monitor.signal import _FAMILY_OF
from irc.monitor.types import SignalRecord

_NEWS_MARK = "·新闻面"
_MACRO_MARK = "·新闻面·易变"


def _band(value: float, cuts: tuple[tuple[float, str], ...], lo: str) -> str:
    """Descending cuts: first (threshold, phrase) with value >= threshold; else lo."""
    for thr, phrase in cuts:
        if value >= thr:
            return phrase
    return lo


_TREND = ((0.6, "强上行"), (0.2, "上行"), (-0.2, "横盘"), (-0.6, "下行"))
_VALUATION = ((0.75, "便宜"), (0.25, "中性偏低"), (-0.25, "估值中性"), (-0.75, "偏贵"))
_FLOW = ((0.75, "强净流入"), (0.25, "净流入"), (-0.25, "均衡"), (-0.75, "净流出"))
_MACRO = ((0.25, "新闻面偏多"), (-0.25, "中性"))
_CONSTITUENT = ((0.25, "成分质量高"), (-0.25, "中等"))


def _heat(value: float) -> str:
    # asymmetric: heat_score caps calm at +0.3, overheated at -1.0
    if value >= 0.0:
        return "低拥挤·平静"
    if value > -0.75:
        return "偏拥挤"
    return "过热"


def factor_annotation(name: str, value: float | None, *, state=None) -> str:
    """PURE: factor name + value → short Chinese phrase; '' when value is None or
    the factor is unknown."""
    if value is None:
        return ""
    if name == "trend":
        return _band(value, _TREND, "强下行")
    if name == "valuation":
        return _band(value, _VALUATION, "很贵")
    if name == "flow":
        return _band(value, _FLOW, "强净流出")
    if name == "heat":
        return _heat(value)
    if name == "macro_tilt":
        return _band(value, _MACRO, "偏空") + _MACRO_MARK
    if name == "constituent":
        return _band(value, _CONSTITUENT, "偏弱") + _NEWS_MARK
    return ""


def _market_dir(contribs) -> str:
    s = sum(c.contribution for c in contribs if _FAMILY_OF.get(c.name) != "news")
    return "偏多" if s > 0.05 else ("偏空" if s < -0.05 else "中性")


def _news_dir(contribs) -> str:
    s = sum(c.contribution for c in contribs if _FAMILY_OF.get(c.name) == "news")
    return "偏多" if s > 0.05 else ("偏空" if s < -0.05 else "中性")


def composite_annotation(signal: SignalRecord) -> str:
    """PURE: name the market vs news drivers, e.g. '市场面中性，新闻叠加偏多'."""
    return f"市场面{_market_dir(signal.contributions)}，新闻叠加{_news_dir(signal.contributions)}"
```

> IMPL NOTE: the parametrized band boundaries above are illustrative; the chosen cuts (e.g. trend >=0.6 → 强上行) must produce EXACTLY the test's expected phrases for the test's input values (0.8, 0.4, 0.0, -0.4, -0.8 etc). Verify each parametrize case against `_band`. E.g. trend 0.4: 0.4 >= 0.6? no; >= 0.2? yes → "上行" ✓. trend 0.0: >=0.2? no; >=-0.2? yes → "横盘" ✓. valuation 0.5: >=0.75? no; >=0.25? yes → "中性偏低" ✓. Adjust cuts only if a case mismatches.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_annotate.py -v`
Expected: PASS (all parametrized + named tests).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/annotate.py tests/monitor/test_annotate.py
git commit -m "feat(monitor): per-factor + composite annotations (Comp 2)"
```

## Task 2.3: `FundView` gains `market_view` (Comp 1 plumbing)

**Files:**
- Modify: `src/irc/monitor/render_types.py`
- Test: `tests/monitor/test_render_types.py` (extend)

- [ ] **Step 1: Write the failing test (new optional field defaults None)**

Append to `tests/monitor/test_render_types.py`:

```python
from irc.monitor.market_composite import MarketCompositeView


def test_fundview_market_view_defaults_none():
    from irc.monitor.render_types import FundView
    from irc.monitor.types import NarrativeDoc, SignalRecord
    rec = SignalRecord("x", "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    v = FundView(fund_id="x", name_cn="x", latest_nav=1.0, as_of_date="d",
                 nav_series=(), signal=rec, narrative=NarrativeDoc("x", (), (), (), "ok"),
                 evidence_pool=(), return_table={}, factor_freshness={},
                 missing_factor_reasons=())
    assert v.market_view is None
    assert v.purchase_tag is None
    mv = MarketCompositeView(0.3, "NEUTRAL", 0.1, 2)
    v2 = dataclasses_replace(v, market_view=mv, purchase_tag="限购 ¥100/日")
    assert v2.market_view.composite == 0.3
    assert v2.purchase_tag == "限购 ¥100/日"


def dataclasses_replace(obj, **kw):
    import dataclasses
    return dataclasses.replace(obj, **kw)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_types.py::test_fundview_market_view_defaults_none -v`
Expected: FAIL — `TypeError: ... got an unexpected keyword argument 'market_view'`.

- [ ] **Step 3: Write minimal implementation**

In `src/irc/monitor/render_types.py`, add the import and two new optional fields to `FundView` (append after `holding_metrics` so existing positional construction is unaffected):

```python
from irc.monitor.market_composite import MarketCompositeView
```

```python
    holding_metrics: tuple[HoldingMetric, ...] = ()  # per-stock drill-down (Slice 2+)
    market_view: MarketCompositeView | None = None   # Comp 1: render-derived anchor
    purchase_tag: str | None = None                  # Comp 5: 限购 actionability tag
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_types.py -v`
Expected: PASS.

- [ ] **Step 5: RUN SIGNATURE-CHANGE SUITE** (`FundView` gained fields — additive with defaults, but discipline requires the full sweep)

Run:
```
uv run pytest tests/monitor/
uv run pytest tests/commands/test_monitor_cmd.py tests/commands/test_monitor_cmd_eval_wiring.py tests/commands/test_monitor_cmd_trace.py tests/commands/test_monitor_cmd_nav_history.py
uv run pytest tests/monitor/eval/test_trace.py
```
Expected: PASS (defaults keep existing constructions valid).

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/render_types.py tests/monitor/test_render_types.py
git commit -m "feat(monitor): FundView.market_view + purchase_tag (Comp 1/5 plumbing)"
```

## Task 2.4: Decision line + honesty line in the card (Comp 1)

**Files:**
- Modify: `src/irc/monitor/render_cards.py` (new `decision_line_html`), `src/irc/monitor/render_html.py` (`_card` calls it)
- Test: `tests/monitor/test_render_cards.py` (extend)

- [ ] **Step 1: Write the failing test (decision line + honesty line content)**

Append to `tests/monitor/test_render_cards.py`:

```python
from irc.monitor.render_cards import decision_line_html
from irc.monitor.market_composite import MarketCompositeView


def test_decision_line_market_bias_composite_news_and_honesty():
    mv = MarketCompositeView(composite=0.24, bias="NEUTRAL", news_delta=0.20,
                             eligible_market_factors=4)
    html = decision_line_html(mv, purchase_tag="限购 ¥100/日")
    assert "市场面" in html and "决策锚" in html
    assert "NEUTRAL" in html
    assert "+0.24" in html
    assert "新闻叠加" in html and "+0.20" in html and "易变" in html
    assert "限购 ¥100/日" in html
    # honesty line: 0.54 is trend-only, NOT the market composite
    assert "前瞻验证累积中" in html
    assert "趋势单因子" in html and "0.54" in html


def test_decision_line_none_market_view_renders_nothing():
    assert decision_line_html(None, purchase_tag=None) == ""


def test_decision_line_no_tag_when_open():
    mv = MarketCompositeView(0.1, "NEUTRAL", 0.0, 2)
    html = decision_line_html(mv, purchase_tag=None)
    assert "限购" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_cards.py::test_decision_line_market_bias_composite_news_and_honesty -v`
Expected: FAIL — `ImportError: cannot import name 'decision_line_html'`.

- [ ] **Step 3: Write minimal implementation**

In `src/irc/monitor/render_cards.py`, add:

```python
from irc.monitor.market_composite import MarketCompositeView

_HONESTY = ("市场面综合分 前瞻验证累积中 · 目前仅趋势单因子有历史命中 ~0.54")


def decision_line_html(mv: MarketCompositeView | None, *, purchase_tag: str | None) -> str:
    """PURE Comp 1: the fact-backed decision line beneath the published badge.
    market anchor + news overlay delta (+易变) + optional 限购 tag + honesty line.
    '' when no market factor is present (mv is None)."""
    if mv is None:
        return ""
    tag = f' · {escape(purchase_tag)}' if purchase_tag else ""
    anchor = (
        f'市场面 决策锚: <b>{escape(mv.bias)}</b> ({mv.composite:+.2f}) · '
        f'新闻叠加 {mv.news_delta:+.2f} (易变){tag}'
    )
    return (
        f'<div class="decision-line">{anchor}'
        f'<span class="honesty muted">{_HONESTY}</span></div>'
    )
```

In `render_html.py` `_card`, insert the decision line directly after the `<h2>` badge line and before `verdict_block_html`:

```python
        f"<h2>{escape(view.name_cn)} ({view.fund_id}) {_badge(view, gate)}</h2>"
        f"{decision_line_html(view.market_view, purchase_tag=view.purchase_tag)}"
        f"{verdict_block_html(view.signal, view.narrative, idx)}"
```

Add `from irc.monitor.render_cards import decision_line_html` to the `render_html.py` import block (line 4-6 group), and add CSS to `_CSS`:
```python
    ".decision-line{margin:6px 0;padding:6px 8px;background:#f6f8fa;"
    "border-left:3px solid #1a7f37;font-size:13px;line-height:1.5}"
    ".decision-line .honesty{display:block;margin-top:3px;font-size:12px}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_cards.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_cards.py src/irc/monitor/render_html.py tests/monitor/test_render_cards.py
git commit -m "feat(monitor): decision line + honesty line in card (Comp 1)"
```

## Task 2.5: 解读 column in factor table (Comp 2)

**Files:**
- Modify: `src/irc/monitor/render_factors.py` (`_present_row`, `_na_row`, header, `factor_table_html`)
- Test: `tests/monitor/test_render_factors.py` (extend)

- [ ] **Step 1: Write the failing test (解读 column + news marks + title tooltip + composite verdict)**

Append to `tests/monitor/test_render_factors.py`:

```python
from irc.monitor.render_factors import factor_table_html
from irc.monitor.types import FactorContribution, FactorScore, SignalRecord


def test_factor_table_has_jiedu_column_with_annotation_and_title():
    contribs = (
        FactorContribution("trend", 0.6, 0.8, 0.48, 1.0, True, ""),
        FactorContribution("macro_tilt", 0.4, 0.6, 0.24, 1.0, True, ""),
    )
    rec = SignalRecord("x", "ok", "ADD_BIAS", 0.72, 1.0, 1.0, ("price-momentum", "news"),
                       contribs, ())
    scores = (FactorScore("trend", 0.8, True, "", 1.0),
              FactorScore("macro_tilt", 0.6, True, "", 1.0))
    html = factor_table_html(rec, scores, {"trend": "fresh", "macro_tilt": "fresh"})
    assert "解读" in html              # new column header
    assert "强上行" in html            # trend annotation
    assert "新闻面" in html            # macro carries the news mark
    assert 'title="强上行"' in html    # value-cell tooltip
    # composite verdict line gains composite_annotation
    assert "市场面" in html and "新闻叠加" in html


def test_factor_table_na_row_jiedu_blank():
    rec = SignalRecord("x", "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    scores = (FactorScore("heat", None, False, "heat_no_data", 1.0),)
    html = factor_table_html(rec, scores, {})
    # N/A row: 解读 cell present but empty (—)
    assert "heat_no_data" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_factors.py::test_factor_table_has_jiedu_column_with_annotation_and_title -v`
Expected: FAIL — `解读` not in output; column count mismatch.

- [ ] **Step 3: Write minimal implementation**

In `src/irc/monitor/render_factors.py`:

Add import: `from irc.monitor.annotate import factor_annotation, composite_annotation`.

Replace `_present_row`:
```python
def _present_row(c: FactorContribution, fresh: str) -> str:
    ann = factor_annotation(c.name, c.value)
    val_cell = f'<td title="{escape(ann)}">{_num(c.value)}</td>' if ann else f"<td>{_num(c.value)}</td>"
    return (
        f"<tr><td>{escape(c.name)}</td>{val_cell}"
        f"<td>{_num(c.renorm_weight)}</td><td>{_num(c.contribution)}</td>"
        f"<td>{_num(c.confidence)}</td><td>{escape(fresh)}</td>"
        f"<td>{escape(ann)}</td></tr>"
    )
```

Replace `_na_row`:
```python
def _na_row(s: FactorScore) -> str:
    return (
        f'<tr class="factor-na"><td>{escape(s.name)}</td>'
        "<td>—</td><td>—</td><td>—</td><td>—</td>"
        f"<td>{escape(s.reason)}</td><td>—</td></tr>"
    )
```

Update the header (add `<th>解读</th>`) and the footer colspan 6→7, and append the composite annotation to the footer. In `factor_table_html`:
```python
    head = (
        "<tr><th>因子</th><th>值 sᵢ</th><th>权重 w'ᵢ</th>"
        "<th>贡献 w'ᵢ·sᵢ</th><th>置信</th><th>状态</th><th>解读</th></tr>"
    )
    fams = "、".join(escape(f) for f in rec.present_families)
    verdict = escape(composite_annotation(rec))
    footer = (
        f'<tr class="factor-foot"><td colspan="7">综合 C = {_num(rec.composite)} · '
        f"置信 {_num(rec.signal_confidence)} · available wt {_num(rec.available_weight)} · "
        f"families: {fams} · {verdict}</td></tr>"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_factors.py -v`
Expected: PASS. Fix any pre-existing factor-table assertion that hard-codes `colspan="6"` to `colspan="7"`.

- [ ] **Step 5: Regenerate golden + sweep**

Run: `uv run pytest tests/monitor/test_render_html.py -v` — regenerate `tests/monitor/golden/report.html` if the golden test fails (same procedure as Task 1.5 Step 5).
Run: `uv run pytest tests/monitor/`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/render_factors.py tests/monitor/ 
git commit -m "feat(monitor): 解读 column + composite verdict in factor table (Comp 2)"
```

## Task 2.6: Wire `market_view` + summary `市场面` column at the edge (Comp 1)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (`_make_view` sets `market_view`), `src/irc/monitor/render_html.py` (`_summary_row` gains 市场面 col)
- Test: `tests/commands/test_monitor_cmd_market_composite.py`, `tests/monitor/test_render_html.py` (extend)

- [ ] **Step 1: Write the failing test (edge populates market_view; summary col present)**

Create `tests/commands/test_monitor_cmd_market_composite.py`:

```python
from __future__ import annotations
from irc.commands.monitor_cmd import _make_view
from irc.monitor.types import (
    MonitorFund, SignalRecord, FactorContribution, NarrativeDoc, FactorScore,
)


def _fund():
    return MonitorFund(id="519069", name_cn="x", market="CN",
                       analysis_profile="active_cn_equity", themes=(),
                       constituent_news=False,
                       weights={"trend": .4, "flow": .2, "macro_tilt": .4},
                       bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.0)


def _signal():
    contribs = (
        FactorContribution("trend", .5, .8, .4, 1.0, True, ""),
        FactorContribution("flow", .2, .0, .0, 1.0, True, ""),
        FactorContribution("macro_tilt", .3, 1.0, .3, 1.0, True, ""),
    )
    return SignalRecord("519069", "ok", "ADD_BIAS", 0.7, 1.0, 1.0,
                        ("price-momentum", "capital-flow", "news"), contribs, ())


def test_make_view_populates_market_view():
    fund = _fund()
    view = _make_view(fund, None, _signal(), (), NarrativeDoc("519069", (), (), (), "ok"), ())
    assert view.market_view is not None
    assert view.market_view.eligible_market_factors == 2  # trend + flow (macro excluded)
    assert view.market_view.news_delta != 0.0
```

Append to `tests/monitor/test_render_html.py`:

```python
def test_summary_row_has_market_composite_column():
    from irc.monitor.render_html import _summary_row
    from irc.monitor.market_composite import MarketCompositeView
    v = _view()  # existing helper
    import dataclasses
    v = dataclasses.replace(v, market_view=MarketCompositeView(0.24, "NEUTRAL", 0.2, 4))
    html = _summary_row(v, None, None)
    assert "市场面" in html or "+0.24" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```
uv run pytest tests/commands/test_monitor_cmd_market_composite.py -v
uv run pytest tests/monitor/test_render_html.py::test_summary_row_has_market_composite_column -v
```
Expected: FAIL — `market_view` is None (edge not wired); summary has no 市场面 cell.

- [ ] **Step 3: Write minimal implementation**

In `monitor_cmd.py` `_make_view`, compute the market view from the signal + fund bands. The fund is NOT currently passed to `_make_view` — it receives `fund`. It does. Add at the end of `_make_view`'s `FundView(...)` construction:

First add import at the top of `monitor_cmd.py`:
```python
from irc.monitor.market_composite import market_composite_view
```

Then in `_make_view`, before the `return FundView(...)`, compute:
```python
    mv = market_composite_view(signal, bands=fund.bands)
```
and add `market_view=mv,` to the `FundView(...)` kwargs.

In `render_html.py` `_summary_row`, add a 市场面 cell. Insert after the `C=` cell:
```python
def _market_cell(view: FundView) -> str:
    mv = view.market_view
    if mv is None:
        return "<td class='muted'>—</td>"
    return f"<td>市场面 {mv.composite:+.2f} {escape(mv.bias)}</td>"
```
and in `_summary_row`'s returned `<tr>`, insert `f"{_market_cell(view)}"` between the `C=` cell and the `changed` cell.

- [ ] **Step 4: Run test to verify it passes**

Run:
```
uv run pytest tests/commands/test_monitor_cmd_market_composite.py -v
uv run pytest tests/monitor/test_render_html.py -v
```
Expected: PASS. Regenerate golden if needed.

- [ ] **Step 5: RUN SIGNATURE-CHANGE SUITE** (`_make_view` output + `_summary_row` output changed)

Run:
```
uv run pytest tests/monitor/
uv run pytest tests/commands/test_monitor_cmd.py tests/commands/test_monitor_cmd_eval_wiring.py tests/commands/test_monitor_cmd_market_composite.py tests/commands/test_monitor_cmd_trace.py
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/monitor_cmd.py src/irc/monitor/render_html.py tests/commands/test_monitor_cmd_market_composite.py tests/monitor/
git commit -m "feat(monitor): wire market_view at edge + 市场面 summary column (Comp 1)"
```

---

# PHASE 3 — Charts (Comp 3a/b/c)

## Task 3.1: `render_heatmap.py` — cross-fund heatmap (Comp 3a)

**Files:**
- Create: `src/irc/monitor/render_heatmap.py`
- Test: `tests/monitor/test_render_heatmap.py`

- [ ] **Step 1: Write the failing test (market|news|市场面C|完整C grouping, badge palette, byte-stable, dark —, title)**

Create `tests/monitor/test_render_heatmap.py`:

```python
from __future__ import annotations
import re
from irc.monitor.render_heatmap import factor_heatmap_html
from irc.monitor.market_composite import MarketCompositeView
from irc.monitor.render_types import FundView
from irc.monitor.types import FactorContribution, FactorScore, NarrativeDoc, SignalRecord


def _view(fid, C, market_c, contribs, scores):
    rec = SignalRecord(fid, "ok", "ADD_BIAS", C, 1.0, 1.0, (), tuple(contribs), ())
    return FundView(fund_id=fid, name_cn=fid, latest_nav=1.0, as_of_date="d",
                    nav_series=(), signal=rec, narrative=NarrativeDoc(fid, (), (), (), "ok"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=(), factor_scores=tuple(scores),
                    market_view=MarketCompositeView(market_c, "ADD_BIAS", C - market_c, 2))


def _views():
    c = [FactorContribution("trend", .5, .8, .4, 1.0, True, ""),
         FactorContribution("macro_tilt", .5, -.4, -.2, 1.0, True, "")]
    s = [FactorScore("trend", .8, True, "", 1.0), FactorScore("macro_tilt", -.4, True, "", 1.0),
         FactorScore("valuation", None, False, "valuation_no_index", 1.0)]
    return (_view("AAA", 0.2, 0.4, c, s),)


def test_heatmap_groups_market_then_news_then_composites():
    html = factor_heatmap_html(_views())
    # column order tokens appear left-to-right
    assert html.index("trend") < html.index("macro") < html.index("市场面")
    assert html.index("市场面") < html.index("完整")


def test_heatmap_uses_badge_palette_not_inverted():
    html = factor_heatmap_html(_views())
    assert "#1a7f37" in html  # add_bias green for positive
    assert "#cf222e" in html  # reduce_bias red for negative


def test_heatmap_na_cell_is_dash():
    html = factor_heatmap_html(_views())
    assert "—" in html  # valuation N/A


def test_heatmap_cell_title_is_annotation():
    html = factor_heatmap_html(_views())
    assert 'title="强上行"' in html


def test_heatmap_legend_present():
    html = factor_heatmap_html(_views())
    assert "正=偏多" in html and "负=偏空" in html


def test_heatmap_byte_stable():
    assert factor_heatmap_html(_views()) == factor_heatmap_html(_views())


def test_heatmap_no_script_no_remote():
    html = factor_heatmap_html(_views())
    assert "<script" not in html.lower() and "http" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_heatmap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.render_heatmap'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/render_heatmap.py` (keep <200 lines, functions <20):

```python
"""PURE Comp 3a: cross-fund factor heatmap. Rows=funds (by full C desc), columns
grouped market(trend,valuation,flow,heat) | news(macro_tilt,constituent) | 市场面C |
完整C. Diverging fill reuses the report's badge convention (add_bias green / reduce_bias
red), intensity ∝ |value|. No JS, no remote refs. Byte-stable."""
from __future__ import annotations
from html import escape
from irc.monitor.annotate import factor_annotation

_MARKET = ("trend", "valuation", "flow", "heat")
_NEWS = ("macro_tilt", "constituent")
_GREEN = "#1a7f37"
_RED = "#cf222e"


def _fill(value: float | None) -> str:
    if value is None:
        return ""
    a = min(abs(value), 1.0)
    colour = _GREEN if value > 0 else (_RED if value < 0 else "")
    if not colour:
        return ""
    return f'background:{colour};opacity:{a:.2f}'


def _value_of(view, name: str) -> float | None:
    for c in view.signal.contributions:
        if c.name == name:
            return c.value
    return None


def _cell(view, name: str) -> str:
    v = _value_of(view, name)
    if v is None:
        return '<td class="muted">—</td>'
    ann = escape(factor_annotation(name, v))
    return f'<td style="{_fill(v)}" title="{ann}">{v:+.2f}</td>'


def _composite_cell(value: float | None) -> str:
    if value is None:
        return '<td class="muted">—</td>'
    return f'<td style="{_fill(value)}">{value:+.2f}</td>'


def _row(view) -> str:
    mc = view.market_view.composite if view.market_view else None
    cells = "".join(_cell(view, n) for n in (*_MARKET, *_NEWS))
    return (f"<tr><td>{escape(view.name_cn)}</td>{cells}"
            f"{_composite_cell(mc)}{_composite_cell(view.signal.composite)}</tr>")


def _header() -> str:
    cols = "".join(f"<th>{escape(n)}</th>" for n in (*_MARKET, *_NEWS))
    return f"<tr><th>基金</th>{cols}<th>市场面C</th><th>完整C</th></tr>"


def factor_heatmap_html(views: tuple) -> str:
    if not views:
        return ""
    ordered = sorted(views, key=lambda v: v.signal.composite, reverse=True)
    body = "".join(_row(v) for v in ordered)
    legend = '<p class="muted heatmap-legend">正=偏多 / 负=偏空</p>'
    return ('<section class="heatmap"><h2>跨基金因子热力图</h2>'
            f'<table class="heatmap-table">{_header()}{body}</table>{legend}</section>')
```

> NOTE: column-name display tokens must contain `macro` substring for the test (`macro_tilt` does). `市场面` and `完整` literals appear in the header — index order test passes.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_heatmap.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_heatmap.py tests/monitor/test_render_heatmap.py
git commit -m "feat(monitor): cross-fund factor heatmap (Comp 3a)"
```

## Task 3.2: `render_timeline.py` — BiasTimeline + bias-history grid (Comp 3b)

**Files:**
- Create: `src/irc/monitor/render_timeline.py`
- Test: `tests/monitor/test_render_timeline.py`

- [ ] **Step 1: Write the failing test (frozen BiasTimeline + grid + engine boundary marker + byte-stable)**

Create `tests/monitor/test_render_timeline.py`:

```python
from __future__ import annotations
from irc.monitor.render_timeline import BiasTimeline, bias_timeline_html


def _tl():
    return BiasTimeline(
        run_dates=("2026-06-28", "2026-06-29", "2026-06-30"),
        rows=(
            ("519069", (("ADD_BIAS", "1"), ("NEUTRAL", "3"), ("NEUTRAL", "3"))),
            ("008986", (("REDUCE_BIAS", "1"), ("REDUCE_BIAS", "3"), ("ADD_BIAS", "3"))),
        ),
    )


def test_timeline_renders_one_cell_per_run_date():
    html = bias_timeline_html(_tl())
    assert html.count("2026-06-28") >= 1
    assert "519069" in html and "008986" in html


def test_timeline_marks_engine_boundary():
    html = bias_timeline_html(_tl())
    # v1->v3 boundary marked where engine tag changes ("1" -> "3")
    assert "engine-boundary" in html or "引擎切换" in html


def test_timeline_uses_badge_classes():
    html = bias_timeline_html(_tl())
    assert "add_bias" in html and "reduce_bias" in html and "neutral" in html


def test_timeline_empty_renders_nothing():
    assert bias_timeline_html(BiasTimeline(run_dates=(), rows=())) == ""


def test_timeline_byte_stable():
    assert bias_timeline_html(_tl()) == bias_timeline_html(_tl())


def test_timeline_no_script_no_remote():
    html = bias_timeline_html(_tl())
    assert "<script" not in html.lower() and "http" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_timeline.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/render_timeline.py`:

```python
"""PURE Comp 3b: bias-history timeline grid. Frozen BiasTimeline (built at the
edge from forward_ledger.jsonl) → colored HTML grid; the v1→v3 engine boundary is
marked where a fund's engine tag changes between adjacent run dates. No JS, no
remote refs. Byte-stable."""
from __future__ import annotations
from dataclasses import dataclass
from html import escape

# one (bias, engine) pair per run date, ordered oldest→newest
_Cell = tuple[str, str]


@dataclass(frozen=True)
class BiasTimeline:
    run_dates: tuple[str, ...]
    rows: tuple[tuple[str, tuple[_Cell, ...]], ...]   # (fund_id, cells)


def _cell_html(prev_eng: str | None, cell: _Cell) -> str:
    bias, eng = cell
    cls = bias.lower()
    boundary = " engine-boundary" if prev_eng is not None and eng != prev_eng else ""
    label = {"ADD_BIAS": "+", "REDUCE_BIAS": "−", "NEUTRAL": "·"}.get(bias, "?")
    return f'<td class="tl-cell {cls}{boundary}">{label}</td>'


def _row_html(fund_id: str, cells: tuple[_Cell, ...]) -> str:
    out = []
    prev_eng: str | None = None
    for cell in cells:
        out.append(_cell_html(prev_eng, cell))
        prev_eng = cell[1]
    return f"<tr><td>{escape(fund_id)}</td>{''.join(out)}</tr>"


def bias_timeline_html(timeline: BiasTimeline) -> str:
    if not timeline.run_dates or not timeline.rows:
        return ""
    head = "<tr><th>基金</th>" + "".join(
        f"<th>{escape(d[5:])}</th>" for d in timeline.run_dates) + "</tr>"
    body = "".join(_row_html(fid, cells) for fid, cells in timeline.rows)
    note = '<p class="muted">引擎切换以边框标记 (engine-boundary)</p>'
    return ('<section class="timeline"><h2>方向性倾向历史</h2>'
            f'<table class="timeline-table">{head}{body}</table>{note}</section>')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_timeline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_timeline.py tests/monitor/test_render_timeline.py
git commit -m "feat(monitor): bias-history timeline grid (Comp 3b)"
```

## Task 3.3: Build BiasTimeline at the edge from forward_ledger (Comp 3b)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (new `_build_bias_timeline`), thread into `render_report`
- Test: `tests/commands/test_monitor_cmd_market_composite.py` (extend — timeline build)

- [ ] **Step 1: Write the failing test (read ledger, dedup one row per (fund, run_date), bounded)**

Append to `tests/commands/test_monitor_cmd_market_composite.py`:

```python
import json
from pathlib import Path
from irc.commands import monitor_cmd


def test_build_bias_timeline_dedups_and_bounds(tmp_path):
    led = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    led.parent.mkdir(parents=True)
    rows = [
        {"run_date": "2026-06-29", "fund_id": "519069", "raw_bias": "ADD_BIAS",
         "written_at": "2026-06-29T09:00:00+08:00", "manifest_versions": {"engine": "3"}},
        {"run_date": "2026-06-29", "fund_id": "519069", "raw_bias": "NEUTRAL",
         "written_at": "2026-06-29T13:00:00+08:00", "manifest_versions": {"engine": "3"}},
        {"run_date": "2026-06-30", "fund_id": "519069", "raw_bias": "NEUTRAL",
         "written_at": "2026-06-30T09:00:00+08:00", "manifest_versions": {"engine": "3"}},
    ]
    led.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    tl = monitor_cmd._build_bias_timeline(tmp_path)
    assert tl.run_dates == ("2026-06-29", "2026-06-30")
    # dedup: latest written_at wins for 2026-06-29 → NEUTRAL
    fund_row = dict(tl.rows)["519069"]
    assert fund_row[0][0] == "NEUTRAL"   # deduped 06-29
    assert fund_row[1][0] == "NEUTRAL"   # 06-30


def test_build_bias_timeline_missing_ledger_empty(tmp_path):
    tl = monitor_cmd._build_bias_timeline(tmp_path)
    assert tl.run_dates == () and tl.rows == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_monitor_cmd_market_composite.py::test_build_bias_timeline_dedups_and_bounds -v`
Expected: FAIL — `_build_bias_timeline` not defined.

- [ ] **Step 3: Write minimal implementation**

In `monitor_cmd.py`, add imports:
```python
from irc.monitor.eval.forward_log import append_ledger, ledger_row, latest_per_key
from irc.monitor.render_timeline import BiasTimeline
```
(`append_ledger, ledger_row` already imported — extend that line to add `latest_per_key`.)

Add the helper (keep it <20 lines via a small parse helper):
```python
_TIMELINE_MAX_DATES = 20


def _read_ledger_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return rows


def _build_bias_timeline(root: Path) -> BiasTimeline:
    """EDGE-read Comp 3b: forward_ledger → deduped one row per (fund, run_date)
    (latest written_at wins), bounded to the most recent _TIMELINE_MAX_DATES run
    dates. Engine tag from manifest_versions.engine (default '0')."""
    rows = latest_per_key(_read_ledger_rows(
        root / "data" / "monitor" / "forward_ledger.jsonl"))
    dates = sorted({r["run_date"] for r in rows})[-_TIMELINE_MAX_DATES:]
    by_fund: dict[str, dict[str, tuple[str, str]]] = {}
    for r in rows:
        if r["run_date"] not in dates:
            continue
        eng = str((r.get("manifest_versions") or {}).get("engine", "0"))
        by_fund.setdefault(r["fund_id"], {})[r["run_date"]] = (r.get("raw_bias") or "NEUTRAL", eng)
    out_rows = tuple(
        (fid, tuple(by_fund[fid].get(d, ("NEUTRAL", "0")) for d in dates))
        for fid in sorted(by_fund)
    )
    return BiasTimeline(run_dates=tuple(dates), rows=out_rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_monitor_cmd_market_composite.py -v`
Expected: PASS.

- [ ] **Step 5: Commit (wiring into render comes in Task 3.5)**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_market_composite.py
git commit -m "feat(monitor): build BiasTimeline from forward_ledger at edge (Comp 3b)"
```

## Task 3.4: `render_contrib.py` — per-fund contribution bars (Comp 3c)

**Files:**
- Create: `src/irc/monitor/render_contrib.py`
- Test: `tests/monitor/test_render_contrib.py`

- [ ] **Step 1: Write the failing test (diverging SVG bars, market vs news distinguished, byte-stable, rounded)**

Create `tests/monitor/test_render_contrib.py`:

```python
from __future__ import annotations
import re
from irc.monitor.render_contrib import contribution_bars_svg
from irc.monitor.types import FactorContribution


def _contribs():
    return (
        FactorContribution("trend", .5, .8, .40, 1.0, True, ""),
        FactorContribution("flow", .2, -.5, -.10, 1.0, True, ""),
        FactorContribution("macro_tilt", .3, 1.0, .30, 1.0, True, ""),
    )


def test_contrib_bars_is_svg():
    svg = contribution_bars_svg(_contribs())
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")


def test_contrib_bars_distinguish_news_visually():
    svg = contribution_bars_svg(_contribs())
    # news bars carry a distinct marker (hatch pattern id or muted opacity class)
    assert "news-bar" in svg or "url(#hatch)" in svg


def test_contrib_bars_diverging_colors():
    svg = contribution_bars_svg(_contribs())
    assert "#1a7f37" in svg and "#cf222e" in svg


def test_contrib_bars_geometry_rounded_2dp():
    svg = contribution_bars_svg(_contribs())
    # no coordinate has > 2 decimal places
    assert not re.search(r"\d+\.\d{3,}", svg)


def test_contrib_bars_byte_stable():
    assert contribution_bars_svg(_contribs()) == contribution_bars_svg(_contribs())


def test_contrib_bars_empty():
    svg = contribution_bars_svg(())
    assert svg.startswith("<svg") and "</svg>" in svg


def test_contrib_bars_no_script():
    assert "<script" not in contribution_bars_svg(_contribs()).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_contrib.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/irc/monitor/render_contrib.py` (model the rounding helper on `svg_chart._r`):

```python
"""PURE Comp 3c: compact inline-SVG diverging contribution bars per factor inside a
fund card. Market factors vs news factors are visually distinguished (news bars use
a hatch fill) so the overlay is obvious. Geometry rounded to 2dp; byte-stable. No
JS, no remote refs."""
from __future__ import annotations
from html import escape
from irc.monitor.signal import _FAMILY_OF
from irc.monitor.types import FactorContribution

_W, _ROW_H, _PAD = 260.0, 16.0, 4.0
_MID = _W / 2.0
_HALF = _MID - _PAD
_GREEN, _RED = "#1a7f37", "#cf222e"
_HATCH = ('<defs><pattern id="hatch" width="4" height="4" '
          'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
          '<line x1="0" y1="0" x2="0" y2="4" stroke="#8c959f" stroke-width="1"/>'
          '</pattern></defs>')


def _r(x: float) -> str:
    return f"{x:.2f}"


def _bar(c: FactorContribution, y: float) -> str:
    is_news = _FAMILY_OF.get(c.name) == "news"
    mag = min(abs(c.contribution), 1.0) * _HALF
    if c.contribution >= 0:
        x, w, colour = _MID, mag, _GREEN
    else:
        x, w, colour = _MID - mag, mag, _RED
    cls = ' class="news-bar"' if is_news else ""
    fill = 'url(#hatch)' if is_news else colour
    rect = (f'<rect{cls} x="{_r(x)}" y="{_r(y)}" width="{_r(w)}" '
            f'height="{_r(_ROW_H - 4)}" fill="{fill}" stroke="{colour}"/>')
    label = f'<text x="2" y="{_r(y + _ROW_H - 6)}" font-size="10">{escape(c.name)}</text>'
    return label + rect


def contribution_bars_svg(contributions: tuple[FactorContribution, ...]) -> str:
    n = len(contributions)
    height = max(_ROW_H, n * _ROW_H)
    bars = "".join(_bar(c, i * _ROW_H + 2) for i, c in enumerate(contributions))
    axis = f'<line x1="{_r(_MID)}" y1="0" x2="{_r(_MID)}" y2="{_r(height)}" stroke="#d0d7de"/>'
    return (f'<svg class="contrib" viewBox="0 0 {_r(_W)} {_r(height)}" '
            f'xmlns="http://www.w3.org/2000/svg">{_HATCH}{axis}{bars}</svg>')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_contrib.py -v`
Expected: PASS. If `test_contrib_bars_geometry_rounded_2dp` trips on the `font-size`/`width` integer literals, ensure all coordinate emissions go through `_r`.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_contrib.py tests/monitor/test_render_contrib.py
git commit -m "feat(monitor): per-fund contribution bars SVG (Comp 3c)"
```

## Task 3.5: Wire all three charts into `render_report` (Comp 3a/b/c)

**Files:**
- Modify: `src/irc/monitor/render_html.py` (render_report gains `timeline` param; heatmap after summary; contrib bars in card), `src/irc/commands/monitor_cmd.py` (`_write_outputs`/`run_monitor` pass timeline)
- Test: `tests/monitor/test_render_html.py` (extend), `tests/commands/...`

- [ ] **Step 1: Write the failing test (heatmap after summary, timeline present, contrib bars in card)**

Append to `tests/monitor/test_render_html.py`:

```python
def test_render_report_includes_charts():
    from irc.monitor.render_html import render_report
    from irc.monitor.render_types import Provenance
    from irc.monitor.render_timeline import BiasTimeline
    from irc.monitor.market_composite import MarketCompositeView
    import dataclasses
    v = dataclasses.replace(_view(), market_view=MarketCompositeView(0.3, "ADD_BIAS", 0.1, 2))
    tl = BiasTimeline(run_dates=("2026-06-30",),
                      rows=(("008986", (("ADD_BIAS", "3"),)),))
    html = render_report((v,), Provenance("3", "1", "1", ""), prior_signal=None,
                         now=_NOW, timeline=tl)
    assert 'class="heatmap"' in html
    assert 'class="timeline"' in html
    assert 'class="contrib"' in html
    # heatmap appears after the summary table, before cards
    assert html.index("summary") < html.index('class="heatmap"') < html.index("fund-card")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_render_html.py::test_render_report_includes_charts -v`
Expected: FAIL — `render_report() got an unexpected keyword argument 'timeline'`.

- [ ] **Step 3: Write minimal implementation**

In `render_html.py`:
- Add imports: `from irc.monitor.render_heatmap import factor_heatmap_html`, `from irc.monitor.render_timeline import BiasTimeline, bias_timeline_html`, `from irc.monitor.render_contrib import contribution_bars_svg`.
- Add `timeline: BiasTimeline | None = None` to `render_report`'s signature (after `predictive_panel`).
- In `_card`, insert `contribution_bars_svg(view.signal.contributions)` right after the nav `chart`:
  ```python
        f"{chart}"
        f"{contribution_bars_svg(view.signal.contributions)}"
        f"{returns_table_html(view.return_table)}"
  ```
- In the `render_report` return assembly, insert heatmap after `summary` and timeline after heatmap:
  ```python
      heatmap = factor_heatmap_html(views)
      timeline_html = bias_timeline_html(timeline) if timeline is not None else ""
      ...
          + header + outage_note + _EXPLAINER + summary + heatmap + timeline_html
          + cards + panel + predictive + _appendix(idx) + "</body></html>"
  ```
- Add CSS to `_CSS` for `.heatmap-table`, `.timeline-table`, `.tl-cell`, `.engine-boundary`, `.contrib`, `.news-bar` (compact, muted, ≤ existing max-width):
  ```python
      ".heatmap-table,.timeline-table{border-collapse:collapse;font-size:12px;margin:8px 0}"
      ".heatmap-table td,.heatmap-table th,.timeline-table td,.timeline-table th"
      "{border:1px solid #d0d7de;padding:2px 5px;text-align:center}"
      ".tl-cell.add_bias{color:#1a7f37}.tl-cell.reduce_bias{color:#cf222e}.tl-cell.neutral{color:#6e7781}"
      ".engine-boundary{border-left:2px solid #bf8700}"
      ".contrib{width:100%;max-width:280px;height:auto;display:block;margin:6px 0}"
      ".heatmap-legend{font-size:11px}"
  ```

In `monitor_cmd.py`:
- Build the timeline in `run_monitor` after `_write_eval_artifacts` (so it includes today's just-appended rows) and pass it through `_write_outputs`:
  ```python
      _write_eval_artifacts(...)
      _run_forward_eval(root, _today)
      timeline = _build_bias_timeline(root)
      predictive_panel = _predictive_panel_model(root, today=_today)
      _write_outputs(out, views, prior, gates, panel_rows,
                     predictive_panel=predictive_panel, timeline=timeline)
  ```
- Extend `_write_outputs` signature with `timeline: BiasTimeline | None = None` and pass `timeline=timeline` into the `render_report(...)` call.
- Add `from irc.monitor.render_timeline import BiasTimeline` import (added in Task 3.3).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_html.py -v`
Expected: PASS. Regenerate `tests/monitor/golden/report.html` (same procedure).

- [ ] **Step 5: RUN SIGNATURE-CHANGE SUITE** (`render_report` + `_write_outputs` gained params; `_card` output changed)

Run:
```
uv run pytest tests/monitor/
uv run pytest tests/commands/test_monitor_cmd.py tests/commands/test_monitor_cmd_eval_wiring.py tests/commands/test_monitor_cmd_market_composite.py tests/commands/test_monitor_cmd_predictive_panel.py tests/commands/test_monitor_cmd_trace.py
uv run pytest tests/monitor/eval/
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/render_html.py src/irc/commands/monitor_cmd.py tests/monitor/
git commit -m "feat(monitor): wire heatmap + timeline + contrib bars into report (Comp 3)"
```

---

# PHASE 4 — Log + score the market composite (Comp 6)

## Task 4.1: `ledger_row` gains `market_composite` + `market_bias` (additive) (Comp 6)

**Files:**
- Modify: `src/irc/monitor/eval/forward_log.py`
- Test: `tests/monitor/eval/test_forward_log.py` (extend)

- [ ] **Step 1: Write the failing test (additive fields; None-safe; latest_per_key unaffected)**

Append to `tests/monitor/eval/test_forward_log.py`:

```python
from irc.monitor.eval.forward_log import ledger_row, latest_per_key
from irc.monitor.eval.types import GateDecision
from irc.monitor.types import SignalRecord


def _sig():
    return SignalRecord("519069", "ok", "ADD_BIAS", 0.7, 1.0, 1.0, (), (), ())


def _gate():
    return GateDecision("519069", False, (), "validated", "")


def test_ledger_row_carries_market_composite():
    row = ledger_row(run_date="2026-06-30", fund_id="519069", written_at="t",
                     signal=_sig(), nav_acc=2.0, nav_unit=2.0, as_of_date="2026-06-30",
                     published_state="ADD_BIAS", gate=_gate(),
                     manifest_versions={"engine": "3"},
                     market_composite=0.6, market_bias="ADD_BIAS")
    assert row["market_composite"] == 0.6
    assert row["market_bias"] == "ADD_BIAS"


def test_ledger_row_market_composite_defaults_none():
    row = ledger_row(run_date="2026-06-30", fund_id="519069", written_at="t",
                     signal=_sig(), nav_acc=2.0, nav_unit=2.0, as_of_date="2026-06-30",
                     published_state="ADD_BIAS", gate=_gate(),
                     manifest_versions={"engine": "3"})
    assert row["market_composite"] is None
    assert row["market_bias"] is None


def test_latest_per_key_ignores_new_field():
    a = ledger_row(run_date="d", fund_id="f", written_at="1", signal=_sig(),
                   nav_acc=1.0, nav_unit=1.0, as_of_date="d", published_state="x",
                   gate=_gate(), manifest_versions={}, market_composite=0.1)
    b = ledger_row(run_date="d", fund_id="f", written_at="2", signal=_sig(),
                   nav_acc=1.0, nav_unit=1.0, as_of_date="d", published_state="x",
                   gate=_gate(), manifest_versions={}, market_composite=0.2)
    kept = latest_per_key([a, b])
    assert len(kept) == 1 and kept[0]["market_composite"] == 0.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_forward_log.py -v`
Expected: FAIL — `ledger_row() got an unexpected keyword argument 'market_composite'`.

- [ ] **Step 3: Write minimal implementation**

In `src/irc/monitor/eval/forward_log.py`, extend `ledger_row` with two keyword-only params (defaulted, so all existing callers stay valid) and emit them:

```python
def ledger_row(
    *, run_date: str, fund_id: str, written_at: str, signal: SignalRecord,
    nav_acc: float | None, nav_unit: float, as_of_date: str,
    published_state: str, gate: GateDecision, manifest_versions: dict,
    market_composite: float | None = None, market_bias: str | None = None,
) -> dict:
    """PURE: one forward-ledger row. nav_acc is COALESCE(nav_acc, nav) perf basis.
    market_composite/market_bias (Comp 6) are ADDITIVE/back-compat — old readers
    (latest_per_key) and old rows without the field are unaffected."""
    return {
        "run_date": run_date,
        "fund_id": fund_id,
        "written_at": written_at,
        "raw_status": signal.status,
        "raw_bias": signal.bias,
        "raw_composite": signal.composite,
        "signal_confidence": signal.signal_confidence,
        "published_state": published_state,
        "gate_reason": gate.reason,
        "nav_acc": nav_acc,
        "nav_unit": nav_unit,
        "nav_basis": "coalesce(nav_acc,nav)",
        "as_of_date": as_of_date,
        "manifest_versions": manifest_versions,
        "market_composite": market_composite,
        "market_bias": market_bias,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_forward_log.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/forward_log.py tests/monitor/eval/test_forward_log.py
git commit -m "feat(monitor): additive market_composite ledger fields (Comp 6)"
```

## Task 4.2: `ForwardRow` gains `market_composite`/`market_bias`; `score_forward` reads them back-compat (Comp 6)

**Files:**
- Modify: `src/irc/monitor/eval/forward_score.py`
- Test: `tests/monitor/eval/test_forward_score.py` (extend)

- [ ] **Step 1: Write the failing test (ForwardRow carries field; missing-field rows default None, no crash)**

Append to `tests/monitor/eval/test_forward_score.py`:

```python
from irc.monitor.eval.forward_score import ForwardRow, score_forward


def test_forward_row_has_market_composite_field():
    r = ForwardRow(run_date="d", fund_id="f", as_of_date="d", raw_status="ok",
                   raw_composite=0.5, raw_bias="ADD_BIAS", entry_nav_date="e",
                   fwd_ret=0.01, from_latest_nav=0.0, market_composite=0.6,
                   market_bias="ADD_BIAS")
    assert r.market_composite == 0.6


def test_score_forward_back_compat_rows_without_market_field():
    # a legacy ledger row WITHOUT market_composite must not crash the scorer
    ledger = [{
        "run_date": "2026-06-01", "fund_id": "f", "written_at": "t",
        "raw_status": "ok", "raw_bias": "ADD_BIAS", "raw_composite": 0.5,
        "signal_confidence": 1.0, "published_state": "ADD_BIAS", "gate_reason": "",
        "nav_acc": 1.0, "nav_unit": 1.0, "nav_basis": "coalesce(nav_acc,nav)",
        "as_of_date": "2026-06-01", "manifest_versions": {"engine": "3"},
    }]
    nav = {"f": [{"fund_id": "f", "nav_date": "2026-06-01", "nav_acc": 1.0},
                 {"fund_id": "f", "nav_date": "2026-06-30", "nav_acc": 1.1}]}
    rows, _excl = score_forward(ledger, nav, h=1, today="2026-07-15", target_engine="3")
    # should not raise; market_composite defaults None on the produced ForwardRow
    assert all(r.market_composite is None for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -v`
Expected: FAIL — `ForwardRow.__init__() got an unexpected keyword argument 'market_composite'`.

- [ ] **Step 3: Write minimal implementation**

In `src/irc/monitor/eval/forward_score.py`:

Add the two optional fields to `ForwardRow` (defaulted — additive):
```python
@dataclass(frozen=True)
class ForwardRow:
    run_date: str
    fund_id: str
    as_of_date: str
    raw_status: str
    raw_composite: float
    raw_bias: str | None
    entry_nav_date: str
    fwd_ret: float
    from_latest_nav: float           # as_of-anchored diagnostic ONLY (look-ahead)
    market_composite: float | None = None    # Comp 6
    market_bias: str | None = None            # Comp 6
```

In `score_forward`, when constructing each `ForwardRow`, read the optional fields with `.get` (back-compat for legacy rows):
```python
        out.append(ForwardRow(
            run_date=r["run_date"], fund_id=r["fund_id"], as_of_date=r["as_of_date"],
            raw_status=r["raw_status"], raw_composite=float(r["raw_composite"]),
            raw_bias=r.get("raw_bias"),
            entry_nav_date=eo.entry_nav_date, fwd_ret=eo.fwd_ret,
            from_latest_nav=_from_latest_nav(series, r["run_date"], eo.outcome_idx),
            market_composite=(None if r.get("market_composite") is None
                              else float(r["market_composite"])),
            market_bias=r.get("market_bias"),
        ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/eval/test_forward_score.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/forward_score.py tests/monitor/eval/test_forward_score.py
git commit -m "feat(monitor): ForwardRow carries market_composite (back-compat) (Comp 6)"
```

## Task 4.3: `market_composite_directional` population in metrics (Comp 6)

**Files:**
- Modify: `evals/monitor_forward/metrics.py`
- Test: `tests/evals/test_monitor_forward_metrics.py` (extend)

- [ ] **Step 1: Write the failing test (new population parallel to raw_composite_directional)**

Append to `tests/evals/test_monitor_forward_metrics.py`:

```python
from irc.monitor.eval.forward_score import ForwardRow
from evals.monitor_forward.metrics import build_metric_reports


def _row(rd, fid, mc, fwd):
    return ForwardRow(run_date=rd, fund_id=fid, as_of_date=rd, raw_status="ok",
                      raw_composite=mc, raw_bias="ADD_BIAS", entry_nav_date="e",
                      fwd_ret=fwd, from_latest_nav=0.0, market_composite=mc,
                      market_bias="ADD_BIAS")


def test_market_composite_directional_present():
    rows = [_row("2026-06-0%d" % i, "f", 0.3, 0.01) for i in range(1, 6)]
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[],
                                            seed=1, momentum_by_key={})
    names = [m.name for m in reports]
    assert "market_composite_directional" in names
    assert "market_composite_directional" in details


def test_market_composite_directional_skips_none_market_rows():
    # rows whose market_composite is None are excluded from THIS population only
    rows = [
        _row("2026-06-01", "f", 0.3, 0.01),
        ForwardRow("2026-06-02", "f", "2026-06-02", "ok", 0.4, "ADD_BIAS", "e",
                   0.01, 0.0, market_composite=None, market_bias=None),
    ]
    reports, details = build_metric_reports(forward_rows=rows, retro_points=[],
                                            seed=1, momentum_by_key={})
    d = details["market_composite_directional"]
    # only 1 market row scored; excluded count surfaced
    assert d.get("excluded", {}).get("null_market_composite", 0) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_monitor_forward_metrics.py -v`
Expected: FAIL — `market_composite_directional` not in names/details.

- [ ] **Step 3: Write minimal implementation**

In `evals/monitor_forward/metrics.py`:

Add a population builder mirroring `_composite_rows`, but reading `market_composite` and excluding None rows:
```python
def _market_rows(rows: Sequence[ForwardRow]) -> tuple[list[dict], dict[str, int]]:
    out: list[dict] = []
    excl: dict[str, int] = {}
    for r in rows:
        if r.market_composite is None:
            excl["null_market_composite"] = excl.get("null_market_composite", 0) + 1
            continue
        out.append({"run_date": r.run_date, "fund_id": r.fund_id,
                    "pred": sign(r.market_composite), "label": sign(r.market_composite),
                    "fwd": r.fwd_ret})
    return out, excl
```

In `build_metric_reports`, after building `r_comp`/`r_bias`, add the market population (same maturity join / zero-return exclusion / block bootstrap as the others — `_hit_rate_report` already implements all of that):
```python
    market, market_excl = _market_rows(forward_rows)
    r_mkt, d_mkt = _hit_rate_report("market_composite_directional", market,
                                    seed=seed + 30, momentum_by_key=mbk)
    if market_excl:
        d_mkt["excluded"] = {**d_mkt.get("excluded", {}), **market_excl}
```

Add `market_composite_directional` to `details` only (NOT to the returned `[reports]` list). The panel layout must stay stable for legacy runs that have no market_composite rows — so this key is omitted entirely when no rows carry the field:

```python
    # Additive market_composite_directional (Comp 4c): omitted when no rows carry the field
    mc_rows = _market_composite_rows(forward_rows)
    if mc_rows:
        _, d_mc = _hit_rate_report("market_composite_directional", mc_rows,
                                   seed=seed + 30, momentum_by_key=mbk)
        details["market_composite_directional"] = d_mc
    return [r_comp, r_bias, r_ic], details
```

> **AS-BUILT AMENDMENT (drift reconciliation 2026-06-30):** The original plan added `r_mkt` as a 4th MetricReport in the return list. The implementation places `market_composite_directional` in `details` only (not the report list), conditional on at least one non-None market_composite row. This keeps the panel layout stable for legacy runs (3 reports, no breakage) while still surfacing the market directional data for display. Test `test_market_composite_directional_report_count` asserts `len(reports) == 3`.

> CRITICAL non-goal guard: this is an ADDITIVE entry. Do NOT change the existing `raw_composite_directional`/`publishable_bias_directional`/`rank_ic`/`engine_population` rows or their details. The runner's `engine_population` headline trigger still keys on `publishable_bias_directional` — unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_monitor_forward_metrics.py -v`
Expected: PASS.

- [ ] **Step 5: RUN SIGNATURE-CHANGE SUITE** (metrics output changed — runner consumes it)

Run:
```
uv run pytest tests/evals/test_monitor_forward_metrics.py tests/evals/test_monitor_forward_runner.py tests/evals/test_registry_monitor_forward.py
uv run pytest tests/monitor/eval/
```
Expected: PASS. The runner's `engine_population` direct-index `details["publishable_bias_directional"]` still resolves (unchanged key).

- [ ] **Step 6: Commit**

```bash
git add evals/monitor_forward/metrics.py tests/evals/test_monitor_forward_metrics.py
git commit -m "feat(monitor): market_composite_directional forward population (Comp 6)"
```

## Task 4.4: Write `market_composite`/`market_bias` into the ledger at the edge (Comp 6)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (`_write_eval_artifacts` ledger_row call)
- Test: `tests/commands/test_monitor_cmd_market_composite.py` (extend) OR `tests/commands/test_monitor_cmd_eval_wiring.py`

- [ ] **Step 1: Write the failing test (ledger row carries market_composite from the view)**

Append to `tests/commands/test_monitor_cmd_market_composite.py`:

```python
from irc.commands.monitor_cmd import _write_eval_artifacts
from irc.monitor.eval.types import GateDecision, FundTraceBundle
from irc.monitor.render_types import FundView
from irc.monitor.market_composite import MarketCompositeView
from irc.monitor.types import NarrativeDoc


def test_eval_artifacts_logs_market_composite(tmp_path, monkeypatch):
    fund = _fund()
    sig = _signal()
    mv = MarketCompositeView(0.6, "ADD_BIAS", 0.1, 2)
    view = FundView(fund_id=fund.id, name_cn="x", latest_nav=2.0, as_of_date="2026-06-30",
                    nav_series=(("2026-06-30", 2.0),), signal=sig,
                    narrative=NarrativeDoc(fund.id, (), (), (), "ok"), evidence_pool=(),
                    return_table={}, factor_freshness={}, missing_factor_reasons=(),
                    factor_scores=(), market_view=mv)
    gate = GateDecision(fund.id, False, (), "validated", "")
    bundle = FundTraceBundle(fund.id, (), (), ())
    out = tmp_path / "out"; out.mkdir()
    _write_eval_artifacts(out, tmp_path, [fund], [view], [bundle], (gate,),
                          run_date="2026-06-30", trading_days=None)
    led = (tmp_path / "data" / "monitor" / "forward_ledger.jsonl").read_text()
    import json
    row = json.loads(led.splitlines()[0])
    assert row["market_composite"] == 0.6
    assert row["market_bias"] == "ADD_BIAS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_monitor_cmd_market_composite.py::test_eval_artifacts_logs_market_composite -v`
Expected: FAIL — `row["market_composite"]` is `None` (edge not passing it).

- [ ] **Step 3: Write minimal implementation**

In `monitor_cmd.py` `_write_eval_artifacts`, in the `ledger_row(...)` call inside the list comprehension, add the two fields from the view's market_view:
```python
            ledger_row(
                run_date=run_date, fund_id=fund.id, written_at=written_at,
                signal=view.signal,
                nav_acc=(view.nav_series[-1][1] if view.nav_series else None),
                nav_unit=view.latest_nav, as_of_date=view.as_of_date,
                published_state=published_state(view.signal, gate), gate=gate,
                manifest_versions={"engine": _ENGINE_VERSION},
                market_composite=(view.market_view.composite if view.market_view else None),
                market_bias=(view.market_view.bias if view.market_view else None),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_monitor_cmd_market_composite.py -v`
Expected: PASS.

- [ ] **Step 5: Add the predictive-panel market row test (it flows through automatically)**

The panel reads every metric row from the report (`_predictive_panel_model` builds a `PredictiveMetricView` per `entry.report.metrics`), so the new `market_composite_directional` row renders with no panel-code change. Add a regression assertion to `tests/commands/test_monitor_cmd_predictive_panel.py` by adding `MetricReport("market_composite_directional", 0.5, "WARN", 4, {}, rel)` to that test's `metrics` list and asserting the resulting model has a `market_composite_directional` metric:

```python
def test_predictive_panel_surfaces_market_row(tmp_path):
    # extend _write_report's metric list with the market row, then:
    ...
    model = _predictive_panel_model(tmp_path, today="2026-07-01")
    assert any(m.name == "market_composite_directional" for m in model.metrics)
```
(Add `"market_composite_directional": {...}` to the `details` dict in `_write_report` too, mirroring the others, so `_metric_view` resolves.)

Run: `uv run pytest tests/commands/test_monitor_cmd_predictive_panel.py -v`
Expected: PASS.

- [ ] **Step 6: RUN SIGNATURE-CHANGE SUITE** (`_write_eval_artifacts` ledger payload changed)

Run:
```
uv run pytest tests/commands/test_monitor_cmd.py tests/commands/test_monitor_cmd_eval_wiring.py tests/commands/test_monitor_cmd_nav_history.py tests/commands/test_monitor_cmd_market_composite.py tests/commands/test_monitor_cmd_predictive_panel.py
uv run pytest tests/monitor/eval/ tests/evals/
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_market_composite.py tests/commands/test_monitor_cmd_predictive_panel.py
git commit -m "feat(monitor): log market_composite to forward ledger + panel row (Comp 6)"
```

---

# PHASE 5 — 限购 / actionability tag (Comp 5)

## Task 5.1: `purchase_tag` builder (Comp 5)

**Files:**
- Modify: `src/irc/monitor/heat_fetch.py` (add `purchase_tag_for` pure helper) — OR put it in `monitor_cmd`. Spec §9 says "reuse the purchase table already fetched for heat". Put the pure cap/status → tag logic in `heat_fetch.py` (its home) and call it at the edge.
- Test: `tests/monitor/test_heat_fetch.py` (or create `tests/monitor/test_heat_fetch_tag.py`)

- [ ] **Step 1: Write the failing test**

> **AS-BUILT AMENDMENT (drift reconciliation 2026-06-30):** The as-built `purchase_tag_for` API differs from the original plan. The implementation simplified the return values to a three-way: `"限购"` for any restricted status (no per-cap ¥amount formatting), `"可申购"` for confirmed open status, and `None` for unknown/no-table. Tests were added to the existing `tests/monitor/test_heat_fetch.py` (not a separate `test_heat_fetch_tag.py` file), and purchase-tag wiring tests landed in `tests/commands/test_monitor_cmd_market_composite.py`. The rationale: the ¥cap format added complexity with limited decision value (the key question is "can you buy?" not "exactly how much?"). All callers of `purchase_tag_for` are updated accordingly.

Append to `tests/monitor/test_heat_fetch.py`:

```python
def test_purchase_tag_for_open():
    from irc.monitor.heat_fetch import purchase_tag_for
    table = _table([{"基金代码": "519069", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    assert purchase_tag_for("519069", purchase_table=table) == "可申购"


def test_purchase_tag_for_restricted_by_status():
    from irc.monitor.heat_fetch import purchase_tag_for
    table = _table([{"基金代码": "519069", "申购状态": "暂停申购", "日累计限定金额": 1e11}])
    assert purchase_tag_for("519069", purchase_table=table) == "限购"


def test_purchase_tag_for_none_table():
    from irc.monitor.heat_fetch import purchase_tag_for
    assert purchase_tag_for("519069", purchase_table=None) is None


def test_purchase_tag_for_fund_absent():
    from irc.monitor.heat_fetch import purchase_tag_for
    table = _table([{"基金代码": "999999", "申购状态": "开放申购", "日累计限定金额": 1e11}])
    assert purchase_tag_for("519069", purchase_table=table) is None
```

- [ ] **Step 3: Write minimal implementation**

In `src/irc/monitor/heat_fetch.py`, add the simplified helper:

```python
def purchase_tag_for(fund_id: str, *, purchase_table: pd.DataFrame | None) -> str | None:
    """PURE: '可申购' | '限购' | None.
    None means data unavailable — never a fabricated tag."""
    status = parse_purchase_status(purchase_table, fund_id)
    if status is None:
        return None
    return "限购" if status else "可申购"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_heat_fetch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/heat_fetch.py tests/monitor/test_heat_fetch.py
git commit -m "feat(monitor): purchase_tag_for 限购 actionability tag (Comp 5)"
```

## Task 5.2: Wire `purchase_tag` into the view at the edge (Comp 5)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py` (`_process_fund` → `_make_view` sets `purchase_tag`)
- Test: `tests/commands/test_monitor_cmd_purchase_tag.py`

- [ ] **Step 1: Write the failing test (restricted fund's view carries tag; decision line shows it)**

Create `tests/commands/test_monitor_cmd_purchase_tag.py`:

```python
from __future__ import annotations
import pandas as pd
from irc.commands.monitor_cmd import _make_view
from irc.monitor.types import (
    MonitorFund, SignalRecord, FactorContribution, NarrativeDoc,
)


def _fund():
    return MonitorFund(id="519069", name_cn="x", market="CN",
                       analysis_profile="active_cn_equity", themes=(),
                       constituent_news=False, weights={"trend": 1.0},
                       bands={"buy": 0.4, "sell": -0.4}, minimum_confidence=0.0)


def _signal():
    return SignalRecord("519069", "ok", "NEUTRAL", 0.1, 1.0, 1.0, (),
                        (FactorContribution("trend", 1.0, 0.1, 0.1, 1.0, True, ""),), ())


def test_make_view_sets_purchase_tag_for_restricted_fund():
    table = pd.DataFrame({"基金代码": ["519069"], "申购状态": ["开放申购"],
                          "日累计限定金额": [100.0]})
    view = _make_view(_fund(), None, _signal(), (),
                      NarrativeDoc("519069", (), (), (), "ok"), (),
                      purchase_table=table)
    assert view.purchase_tag == "限购 ¥100/日"


def test_make_view_no_tag_when_open():
    table = pd.DataFrame({"基金代码": ["519069"], "申购状态": ["开放申购"],
                          "日累计限定金额": [2e8]})
    view = _make_view(_fund(), None, _signal(), (),
                      NarrativeDoc("519069", (), (), (), "ok"), (),
                      purchase_table=table)
    assert view.purchase_tag is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/commands/test_monitor_cmd_purchase_tag.py -v`
Expected: FAIL — `_make_view() got an unexpected keyword argument 'purchase_table'`.

- [ ] **Step 3: Write minimal implementation**

In `monitor_cmd.py`:
- Add import: `from irc.monitor.heat_fetch import fetch_purchase_table, heat_inputs_for, purchase_tag_for` (extend the existing line 17 import).
- Extend `_make_view` signature with `purchase_table=None` (keyword) and compute the tag:
  ```python
  def _make_view(
      fund, nav, signal, scores, narr_doc, pool, impacts_status="ok", *,
      holding_metrics=(), purchase_table=None,
  ) -> FundView:
      mv = market_composite_view(signal, bands=fund.bands)
      tag = purchase_tag_for(fund.id, purchase_table=purchase_table)
      return FundView(
          ...,
          holding_metrics=holding_metrics,
          market_view=mv,
          purchase_tag=tag,
      )
  ```
  (Merge with the `market_view=mv` added in Task 2.6 — single FundView construction.)
- In `_process_fund`, pass `purchase_table` through to `_make_view`:
  ```python
      view = _make_view(fund, nav, signal, scores, narr.doc, pool, impacts.status,
                        holding_metrics=holding_metrics, purchase_table=purchase_table)
  ```
  (`purchase_table` is already a parameter of `_process_fund` — line 649.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/commands/test_monitor_cmd_purchase_tag.py -v`
Expected: PASS.

- [ ] **Step 5: RUN SIGNATURE-CHANGE SUITE** (`_make_view` signature changed)

Run:
```
uv run pytest tests/monitor/
uv run pytest tests/commands/test_monitor_cmd.py tests/commands/test_monitor_cmd_eval_wiring.py tests/commands/test_monitor_cmd_heat.py tests/commands/test_monitor_cmd_market_composite.py tests/commands/test_monitor_cmd_purchase_tag.py tests/commands/test_monitor_cmd_trace.py
```
Expected: PASS. (`_make_view` callers in tests that omit `purchase_table` still work — it defaults None.)

- [ ] **Step 6: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd_purchase_tag.py
git commit -m "feat(monitor): wire 限购 tag into view at edge (Comp 5)"
```

---

# PHASE 6 — Invariant guards + docs (spec §12, §14, §15)

## Task 6.1: Invariant-guard test suite (spec §12)

**Files:**
- Create: `tests/monitor/test_report_v2_invariants.py`

- [ ] **Step 1: Write the invariant tests (these MUST all pass against the now-built code)**

Create `tests/monitor/test_report_v2_invariants.py`:

```python
from __future__ import annotations
import re
import irc.commands.monitor_cmd as mc
from irc.monitor.render_html import render_report
from irc.monitor.render_types import Provenance


def test_engine_version_unchanged():
    assert mc._ENGINE_VERSION == "3"


def test_report_has_no_script_or_remote_refs():
    html = render_report((), Provenance("3", "1", "1", ""), prior_signal=None,
                         now="2026-06-30T09:00:00+08:00")
    assert "<script" not in html.lower()
    assert "http://" not in html and "https://" not in html
    assert "基金概况" not in html


def test_citation_id_regex_format_locked():
    # any [ref:...] that survives anywhere in render code must be 16 hex — but the
    # rendered report must contain NONE (all converted to numbered anchors)
    from irc.monitor.evidence import make_evidence_item
    from irc.monitor.render_types import FundView
    from irc.monitor.types import NarrativeDoc, SignalRecord, Claim
    ev = make_evidence_item("Reuters", "t", "2026-06-30", "https://r", "519069")
    assert re.fullmatch(r"[0-9a-f]{16}", ev.citation_id)
    rec = SignalRecord("519069", "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    narr = NarrativeDoc("519069",
                        (Claim("c", "consistent_with", (ev.citation_id,)),), (), (), "ok")
    v = FundView("519069", "x", 1.0, "2026-06-30", (), rec, narr, (ev,), {}, {}, ())
    html = render_report((v,), Provenance("3", "1", "1", ""), prior_signal=None,
                         now="2026-06-30T09:00:00+08:00")
    assert "[ref:" not in html


def test_superscript_appendix_numbers_align():
    from irc.monitor.evidence import make_evidence_item
    from irc.monitor.render_types import FundView
    from irc.monitor.types import NarrativeDoc, SignalRecord, Claim
    ev = make_evidence_item("Reuters", "t", "2026-06-30", "https://r", "519069")
    rec = SignalRecord("519069", "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    narr = NarrativeDoc("519069",
                        (Claim("c", "consistent_with", (ev.citation_id,)),), (), (), "ok")
    v = FundView("519069", "x", 1.0, "2026-06-30", (), rec, narr, (ev,), {}, {}, ())
    html = render_report((v,), Provenance("3", "1", "1", ""), prior_signal=None,
                         now="2026-06-30T09:00:00+08:00")
    assert f'href="#ev-{ev.citation_id}" title="Reuters — t">1</a>' in html
    assert f'<li id="ev-{ev.citation_id}">1.' in html


def test_published_state_helper_unchanged_import():
    # gate / published_state still the canonical published signal path
    from irc.monitor.eval.gate import published_state  # noqa: F401
```

- [ ] **Step 2: Run the suite**

Run: `uv run pytest tests/monitor/test_report_v2_invariants.py -v`
Expected: PASS (all). If `[ref:` appears, a renderer still leaks the raw marker — fix the offending render_* before proceeding.

- [ ] **Step 3: Acceptance-grep guard for `基金概况` (already enforced project-wide — confirm new files clean)**

Run: `grep -rn "基金概况" src/irc/monitor/market_composite.py src/irc/monitor/annotate.py src/irc/monitor/render_heatmap.py src/irc/monitor/render_timeline.py src/irc/monitor/render_contrib.py`
Expected: no matches (empty output).

- [ ] **Step 4: Commit**

```bash
git add tests/monitor/test_report_v2_invariants.py
git commit -m "test(monitor): report v2 invariant guards (engine/script/citation/基金概况)"
```

## Task 6.2: ADR 0021 (spec §14)

**Files:**
- Create: `docs/adr/0021-monitor-market-composite-decision-anchor.md`

- [ ] **Step 1: Confirm 0021 is free**

Run: `ls docs/adr/ | grep 0021`
Expected: empty (latest is `0020-monitor-dual-track-valuation.md`). **0021 is free.**

- [ ] **Step 2: Write the ADR**

Create `docs/adr/0021-monitor-market-composite-decision-anchor.md`:

```markdown
# ADR 0021 — Monitor report decision anchor: the market composite

Status: accepted (2026-06-30)
Context: `irc monitor` report v2 (run `monitor-report-v2`, spec
`docs/2026-06-30-monitor-report-v2/items/001-spec.md`).

## Decision

The daily brief's **decision anchor** is the **market composite (市场面综合分)** — a
render-derived composite over the four market-data factors (`trend`, `valuation`,
`flow`, `heat`), with the **news family** (`macro_tilt`, `constituent`) excluded and
the surviving weights renormalized (see `src/irc/monitor/market_composite.py`). The
volatile **news overlay (新闻叠加)** is surfaced as the labeled delta `C − market_composite`.

The **full composite `C` remains the canonical published/tracked signal**: header
badge, `monitor.json`, `forward_ledger.raw_composite`, the gate, `EVAL_GATED`, and
the validation panel are all unchanged. `_ENGINE_VERSION` stays `"3"`. The market
composite is **render-derived only** — never a scoring input, never gated.

To earn a track record (like trend-only earned its ~0.54 retro hit-rate), the market
composite is **logged and forward-scored**: `forward_ledger.jsonl` rows carry an
additive `market_composite`/`market_bias` field, and `monitor_forward` adds a
`market_composite_directional` population alongside `raw_composite_directional`. It
reads `insufficient_data` until engine-3 days mature — honest by design.

## Alternatives rejected

- **Make the market composite the published signal** — re-baselines the ledger/eval
  (the published-state clock would reset), losing the accruing full-`C` track record.
- **Engine change to down-weight news** — an `_ENGINE_VERSION` bump + full re-baseline
  for a presentation goal; declined (spec §16).
- **A render-only "robustness" sticker (robust/moderate/fragile)** — a forever-fragile
  label has no decision value; replaced by the concrete market-vs-news split a reader
  can see (spec §1, §5).

## Consequences

- Readers get a fact-backed anchor + an explicit "how much rests on volatile news"
  delta, without any change to what is published or tracked.
- The market composite's forward edge is **unproven until it matures** — the report
  states this plainly (honesty line names trend-only ~0.54 explicitly, NOT the market
  composite).
- The market/news split has ONE source of truth: `signal._FAMILY_OF` (shared by
  `market_composite.py`, `annotate.py`, `backtest.py`).
```

- [ ] **Step 3: Commit**

```bash
git add docs/adr/0021-monitor-market-composite-decision-anchor.md
git commit -m "docs(adr): 0021 monitor market composite decision anchor"
```

## Task 6.3: ADR 0017 ledger-contract note + CONTEXT.md verify (spec §3, §15)

**Files:**
- Modify: `docs/adr/0017-monitor-evidence-isolation.md` (§"Monitor-eval data contracts")
- Verify: `CONTEXT.md` (Market composite / News overlay terms — confirm present)

- [ ] **Step 1: Verify CONTEXT.md terms already present (added during grilling per spec §3)**

Run: `grep -n "市场面综合分\|新闻叠加" CONTEXT.md`
Expected: both present (lines ~10-11). **No CONTEXT.md edit needed** — if either is missing, add the term block matching spec §3. (Confirmed present at plan-authoring time.)

- [ ] **Step 2: Add the additive-ledger-field note to ADR 0017's data-contracts section**

In `docs/adr/0017-monitor-evidence-isolation.md`, in the "Forward ledger — real append-mode JSONL" subsection (after line ~94), append a paragraph:

```markdown
**Additive field (2026-06-30, report v2 / ADR 0021).** Forward-ledger rows gained an
additive `market_composite` / `market_bias` pair (the render-derived market-composite
anchor — ADR 0021). It is **back-compat**: `latest_per_key` ignores it, legacy rows
without the field deserialize fine (`score_forward` reads it via `.get`, defaulting
None), and the `market_composite_directional` forward population excludes None-market
rows under `null_market_composite`. The full composite `C` (`raw_composite`) remains
the canonical published/tracked field; the market composite is logged ONLY to earn its
own forward track record.
```

- [ ] **Step 3: Commit**

```bash
git add docs/adr/0017-monitor-evidence-isolation.md
git commit -m "docs(adr): 0017 note additive market_composite ledger field (report v2)"
```

## Task 6.4: Final full-sweep verification

**Files:** none (verification only)

- [ ] **Step 1: Lint**

Run: `uv run ruff check src tests evals`
Expected: PASS (line-length 100, py312). Fix any new-file lint (unused imports, line length).

- [ ] **Step 2: Full monitor + eval unit suites**

Run:
```
uv run pytest tests/monitor/
uv run pytest tests/monitor/eval/
uv run pytest tests/evals/
```
Expected: PASS.

- [ ] **Step 3: Commands per-file (whole dir HANGS — do NOT run `tests/commands/` as a dir)**

Run each:
```
uv run pytest tests/commands/test_monitor_cmd.py
uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py
uv run pytest tests/commands/test_monitor_cmd_predictive_panel.py
uv run pytest tests/commands/test_monitor_cmd_nav_history.py
uv run pytest tests/commands/test_monitor_cmd_heat.py
uv run pytest tests/commands/test_monitor_cmd_trace.py
uv run pytest tests/commands/test_monitor_cmd_valuation.py
uv run pytest tests/commands/test_monitor_cmd_drilldown.py
uv run pytest tests/commands/test_monitor_constituent.py
uv run pytest tests/commands/test_monitor_cmd_forward_eval.py
uv run pytest tests/commands/test_monitor_cmd_market_composite.py
uv run pytest tests/commands/test_monitor_cmd_purchase_tag.py
```
Expected: PASS for each.

- [ ] **Step 4: Confirm golden regenerated + byte-stable**

Run: `uv run pytest tests/monitor/test_render_html.py -v`
Expected: PASS (golden `tests/monitor/golden/report.html` matches the v2 output).

- [ ] **Step 5: Final commit (if golden/lint touched anything)**

```bash
git add -A
git commit -m "chore(monitor): report v2 final lint + golden sweep"
```

---

## Self-review checklist (completed by plan author)

**Spec coverage:**
- §4 Comp 0 (anti-staleness) → Tasks 1.1, 1.2 ✓
- §5 Comp 1 (market composite + presentation) → Tasks 2.1, 2.3, 2.4, 2.6 ✓
- §6 Comp 2 (annotations) → Tasks 2.2, 2.5 ✓
- §7 Comp 3a/b/c (charts) → Tasks 3.1, 3.2, 3.3, 3.4, 3.5 ✓
- §8 Comp 4 (citations) → Tasks 1.3, 1.4, 1.5 ✓
- §9 Comp 5 (限购 tag) → Tasks 5.1, 5.2 ✓
- §10 Comp 6 (log + score market composite) → Tasks 4.1, 4.2, 4.3, 4.4 ✓
- §12 invariants → Task 6.1 ✓
- §14 ADR 0021 → Task 6.2 ✓
- §15/§3 CONTEXT + ADR 0017 → Task 6.3 ✓

**Non-goals honored:** no engine/weight/gate/published_state/`_ENGINE_VERSION` change (Task 6.1 guards `_ENGINE_VERSION=="3"`); full `C` stays canonical (ledger keeps `raw_composite`; market fields additive); render_* stay pure (no I/O/JS/remote — guarded); no new network/LLM (charts/annotations/market composite all render-derived; 限购 reuses the existing one-call purchase table); ledger field additive/back-compat (Tasks 4.1/4.2 tests).

**Signature-change discipline encoded:** Tasks 1.2, 1.5, 2.3, 2.6, 3.5, 4.3, 4.4, 5.2 each carry a "RUN SIGNATURE-CHANGE SUITE" step listing tests/monitor/ + per-file tests/commands/ + tests/monitor/eval/ + tests/evals/.

**Phase count:** 5 spec phases (1-5) + a 6th docs/invariants phase. **Task count:** 22 tasks across 6 phases.
```
