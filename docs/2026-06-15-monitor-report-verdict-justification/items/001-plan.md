# Re-surface verdict justification in the monitor report renderer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each per-fund card in `outputs/<date>/monitor/report.html` explain *why* the fund earned its bias — a deterministic verdict block, an all-factors contribution table (incl. N/A rows), a real `[5,20,60,120,250]d` returns table, a labelled risk/divergence block, and a sectioned narrative — using data the signal engine already computes.

**Architecture:** The renderer (`render_html.py`) is near its size budget, so the verdict / factor-table / risk / narrative HTML builders move into two new **pure** modules (`render_cards.py`, `render_factors.py`); `render_html.py` keeps `render_report`, the page shell, CSS, summary, appendix. A new **pure** `returns.py` computes window returns from the acc-NAV series. The **only** edge changes are in `monitor_cmd.py::_make_view` (populate the new `FundView.factor_scores` + `return_table`) and a `factor_scores` field added to `FundView` in `render_types.py`. Band thresholds (`buy`/`sell`/`minimum_confidence`) live on `MonitorFund`, not on `SignalRecord`/`FundView`; rather than thread numbers through, the verdict clause renders the **band relationship qualitatively** from `bias` + `status` + `composite` (decision D2 below) so no new threshold plumbing is needed.

**Tech Stack:** Python 3.12, frozen dataclasses, pytest, ruff (line-length 100). No new deps. No JS, no remote refs — render stays byte-stable & self-contained.

---

## Decisions locked (spec left these open — these are the calls)

- **D1 — Canonical factor order:** `("trend", "valuation", "heat", "macro_tilt", "constituent")`. Matches `build_factor_scores` order exactly (`src/irc/monitor/factors.py:79-82`), so `factor_scores` is already in canonical order at the edge and the renderer iterates it as-is.
- **D2 — Band relationship without literal thresholds:** `bands`/`minimum_confidence` are on `MonitorFund`, absent from `FundView`. We do **not** add them. The `ok` verdict clause states the band relationship qualitatively from the already-derived `bias`: `>= 买入阈值` (ADD_BIAS) / `<= 卖出阈值` (REDUCE_BIAS) / `落在中性带内` (NEUTRAL). `composite` is shown as the literal number; the threshold itself is named but not numerically quoted. This keeps the renderer a pure function of `FundView` and avoids a band-plumbing change that the spec flags as optional.
- **D3 — MiniMax verdict comment source & cap:** `narrative.signal_rationale_commentary`, **lead 1 claim only** (`[:1]`), rendered via the existing `_claim_html` pattern (deterministic `[ref:…]` append). If empty → render nothing for the comment (the deterministic clause stands alone). If `narrative.status != "ok"` → show the existing degraded note and rely on the clause.
- **D4 — All-factors table source:** add `factor_scores: tuple[FactorScore, ...]` to `FundView` (carries every factor incl. N/A + structured `reason`). Numeric rows come from `signal.contributions` (keyed by name); N/A rows come from `factor_scores` entries whose name is absent from `contributions`. The reason text is the structured `FactorScore.reason`, NOT string-split from `missing_factor_reasons`.
- **D5 — Returns module:** new pure `src/irc/monitor/returns.py`, `window_returns(acc_nav, windows=(5,20,60,120,250)) -> dict[int, float | None]`. Formula `acc[-1]/acc[-1-w] - 1`; `None` when `len < w+1` OR denominator is falsy. Round each value to **6 dp** for byte-stability (renderer formats to `%`). Returned dict has all five windows as keys (value `None` for N/A), so the table column set is fixed.
- **D6 — Divergence→caveat map (literal Chinese strings):**
  - `trend_valuation_conflict` → `趋势与估值背离：价格动能与估值方向相反`
  - `trend_macro_conflict` → `趋势与宏观背离：价格动能与宏观信号方向相反`
  - `low_factor_agreement` → `因子分歧较大：各因子方向/强度不一致`
  - Unknown code (defensive) → the raw code string, escaped.
- **D7 — Module split:** extract `_verdict_block`, `_factor_table`, `_returns_html`, `_risk_block`, sectioned-narrative helpers into `render_cards.py` (card-level prose/blocks) + `render_factors.py` (factor table + returns table + divergence map). `render_html.py` retains `render_report`, `_badge`, `_summary_row`, `_appendix`, `_markers`, page shell, CSS. This keeps every file < 200 lines.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `src/irc/monitor/returns.py` | PURE: acc-NAV series → `{window: return|None}` | **Create** |
| `src/irc/monitor/render_factors.py` | PURE: canonical order, divergence→caveat map, `_factor_table`, `_returns_html` | **Create** |
| `src/irc/monitor/render_cards.py` | PURE: `_verdict_block`, `_risk_block`, sectioned `_narrative_sections`, `_card` | **Create** |
| `src/irc/monitor/render_types.py` | `FundView` += `factor_scores: tuple[FactorScore,...]` | **Modify** |
| `src/irc/monitor/render_html.py` | page shell, CSS (extended), summary, appendix, `render_report` delegating card build to `render_cards` | **Modify** |
| `src/irc/commands/monitor_cmd.py` | `_make_view` wiring: `factor_scores` + `return_table` | **Modify** |
| `tests/monitor/test_returns.py` | unit tests for `window_returns` | **Create** |
| `tests/monitor/test_render_factors.py` | unit tests for factor table + divergence map | **Create** |
| `tests/monitor/test_render_cards.py` | unit tests for verdict block + risk block + sections | **Create** |
| `tests/monitor/test_render_html.py` | extend: byte-stability, XSS, NO_CALL, citation closure, golden refresh | **Modify** |
| `tests/monitor/golden/report.html` | regenerated golden fixture | **Regenerate** |
| `tests/commands/test_monitor_cmd.py` | `_make_view` wiring assertions | **Modify** |

---

## Task 1: Pure returns helper (`returns.py`)

**Files:**
- Create: `src/irc/monitor/returns.py`
- Test: `tests/monitor/test_returns.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/monitor/test_returns.py
import math
from irc.monitor.returns import window_returns


def _series(vals):
    return tuple((f"2026-01-{i % 28 + 1:02d}", float(v)) for i, v in enumerate(vals))


def test_all_windows_present_as_keys():
    rt = window_returns(_series([1.0 + 0.001 * i for i in range(300)]))
    assert set(rt) == {5, 20, 60, 120, 250}


def test_window_return_is_acc_ratio_minus_one():
    vals = [1.0 + 0.001 * i for i in range(300)]
    rt = window_returns(_series(vals))
    assert math.isclose(rt[60], round(vals[-1] / vals[-61] - 1.0, 6), rel_tol=0, abs_tol=0)


def test_short_window_is_none_when_too_few_points():
    rt = window_returns(_series([1.0, 1.01, 1.02]))  # 3 points
    assert rt[5] is None and rt[20] is None
    assert rt[60] is None and rt[120] is None and rt[250] is None


def test_exactly_w_plus_one_points_yields_a_value():
    rt = window_returns(_series([1.0] * 5 + [1.1]))  # 6 points → 5d valid
    assert rt[5] == round(1.1 / 1.0 - 1.0, 6)


def test_zero_denominator_is_none_not_zero_division():
    vals = [0.0] * 6 + [1.0] * 300  # acc[-1-5] far back is positive; force a zero at -6
    rt = window_returns(_series([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]))
    assert rt[5] is None  # acc[-6] == 0.0 → None, no ZeroDivisionError


def test_values_rounded_to_six_dp_for_byte_stability():
    vals = [1.0] * 5 + [1.0 + 1.0 / 3.0]
    rt = window_returns(_series(vals))
    assert rt[5] == round((1.0 + 1.0 / 3.0) / 1.0 - 1.0, 6)


def test_empty_series_all_none():
    rt = window_returns(())
    assert all(v is None for v in rt.values()) and set(rt) == {5, 20, 60, 120, 250}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/test_returns.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.returns'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/returns.py
from __future__ import annotations

_WINDOWS = (5, 20, 60, 120, 250)


def _one(vals: list[float], w: int) -> float | None:
    if len(vals) < w + 1:
        return None
    denom = vals[-1 - w]
    if not denom:
        return None
    return round(vals[-1] / denom - 1.0, 6)


def window_returns(
    acc_nav: tuple[tuple[str, float], ...],
    windows: tuple[int, ...] = _WINDOWS,
) -> dict[int, float | None]:
    """PURE: total acc-NAV return over each trading-day window.
    return[w] = acc[-1]/acc[-1-w] - 1, rounded 6dp; None when < w+1 points
    or denominator is falsy. All windows always present as keys."""
    vals = [v for _, v in acc_nav]
    return {w: _one(vals, w) for w in windows}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_returns.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/returns.py tests/monitor/test_returns.py
git commit -m "feat(monitor): pure window_returns helper for [5,20,60,120,250]d returns table"
```

---

## Task 2: `FundView` gains `factor_scores`

**Files:**
- Modify: `src/irc/monitor/render_types.py`
- Test: `tests/monitor/test_types.py` (add one assertion) — or extend `tests/commands/test_monitor_cmd.py`; use `test_types.py` here.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/monitor/test_types.py
def test_fundview_carries_factor_scores():
    from irc.monitor.render_types import FundView
    from irc.monitor.types import FactorScore, SignalRecord, NarrativeDoc
    rec = SignalRecord("x", "ok", "NEUTRAL", 0.0, 1.0, 1.0, (), (), ())
    narr = NarrativeDoc("x", (), (), (), "ok")
    fs = (FactorScore("trend", 0.1, True, "", 1.0),)
    v = FundView(
        fund_id="x", name_cn="n", latest_nav=1.0, as_of_date="2026-06-15",
        nav_series=(), signal=rec, narrative=narr, evidence_pool=(),
        return_table={}, factor_freshness={}, missing_factor_reasons=(),
        factor_scores=fs,
    )
    assert v.factor_scores == fs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/monitor/test_types.py::test_fundview_carries_factor_scores -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'factor_scores'`

- [ ] **Step 3: Add the field** — `src/irc/monitor/render_types.py`, in `FundView`, **before** the defaulted `impacts_status` field (a non-defaulted field cannot follow a defaulted one). Add an import of `FactorScore`.

```python
from irc.monitor.types import EvidenceItem, FactorScore, NarrativeDoc, SignalRecord
```

```python
    missing_factor_reasons: tuple[str, ...]
    factor_scores: tuple[FactorScore, ...] = ()
    impacts_status: str = "ok"   # mirrors impacts.status; surfaced so schema/provider errors aren't silently dropped
```

(Defaulting `factor_scores = ()` keeps every existing `FundView(...)` construction in the test suite valid until each is migrated.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/monitor/test_types.py::test_fundview_carries_factor_scores -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_types.py tests/monitor/test_types.py
git commit -m "feat(monitor): FundView carries ordered factor_scores for the all-factors table"
```

---

## Task 3: Factor table + divergence map (`render_factors.py`)

**Files:**
- Create: `src/irc/monitor/render_factors.py`
- Test: `tests/monitor/test_render_factors.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/monitor/test_render_factors.py
from irc.monitor.types import FactorScore, FactorContribution, SignalRecord
from irc.monitor.render_factors import (
    CANONICAL_FACTOR_ORDER, divergence_caveat, factor_table_html, returns_table_html,
)


def test_canonical_order_is_locked():
    assert CANONICAL_FACTOR_ORDER == ("trend", "valuation", "heat", "macro_tilt", "constituent")


def test_divergence_map_strings_are_exact():
    assert divergence_caveat("trend_valuation_conflict") == "趋势与估值背离：价格动能与估值方向相反"
    assert divergence_caveat("trend_macro_conflict") == "趋势与宏观背离：价格动能与宏观信号方向相反"
    assert divergence_caveat("low_factor_agreement") == "因子分歧较大：各因子方向/强度不一致"


def test_unknown_divergence_code_is_escaped_passthrough():
    assert divergence_caveat("<x>") == "&lt;x&gt;"


def _rec(contribs, divergence=()):
    return SignalRecord(
        fund_id="x", status="ok", bias="NEUTRAL", composite=0.0, signal_confidence=1.0,
        available_weight=0.8, present_families=("price-momentum",),
        contributions=contribs, divergence_codes=divergence,
    )


def test_present_factor_renders_numeric_row():
    c = FactorContribution("trend", 0.5625, 0.6, 0.3375, 1.0, True, "")
    scores = (FactorScore("trend", 0.6, True, "", 1.0),)
    html = factor_table_html(_rec((c,)), scores, {"trend": "fresh"})
    assert "trend" in html
    assert "0.6000" in html or "0.6" in html  # value sᵢ formatted
    assert "fresh" in html


def test_na_factor_renders_dim_row_with_structured_reason():
    scores = (
        FactorScore("trend", 0.6, True, "", 1.0),
        FactorScore("heat", None, False, "heat_no_data", 1.0),
    )
    c = FactorContribution("trend", 1.0, 0.6, 0.6, 1.0, True, "")
    html = factor_table_html(_rec((c,)), scores, {"trend": "fresh"})
    assert "factor-na" in html           # dim class present
    assert "heat_no_data" in html        # structured reason, not string-split
    assert html.count("—") >= 3          # dashed numeric cells on the N/A row


def test_factor_rows_render_in_canonical_order():
    scores = (
        FactorScore("constituent", 0.2, True, "", 1.0),
        FactorScore("trend", 0.6, True, "", 1.0),
    )
    cs = (
        FactorContribution("constituent", 0.4, 0.2, 0.08, 1.0, True, ""),
        FactorContribution("trend", 0.6, 0.6, 0.36, 1.0, True, ""),
    )
    html = factor_table_html(_rec(cs), scores, {"trend": "fresh", "constituent": "fresh"})
    assert html.index(">trend<") < html.index(">constituent<")


def test_footer_row_has_composite_confidence_weight_families():
    c = FactorContribution("trend", 1.0, 0.6, 0.6, 1.0, True, "")
    html = factor_table_html(_rec((c,)), (FactorScore("trend", 0.6, True, "", 1.0),), {"trend": "fresh"})
    assert "综合 C" in html and "0.0000" in html  # composite
    assert "available wt" in html and "price-momentum" in html


def test_returns_table_renders_na_for_none_windows():
    html = returns_table_html({5: 0.0123, 20: None, 60: None, 120: None, 250: None})
    assert "+1.23%" in html
    assert "—" in html  # None windows show dash, not crash
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/test_render_factors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.render_factors'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/render_factors.py
from __future__ import annotations
from html import escape
from irc.monitor.types import FactorScore, SignalRecord

CANONICAL_FACTOR_ORDER = ("trend", "valuation", "heat", "macro_tilt", "constituent")

_DIVERGENCE_CAVEATS = {
    "trend_valuation_conflict": "趋势与估值背离：价格动能与估值方向相反",
    "trend_macro_conflict": "趋势与宏观背离：价格动能与宏观信号方向相反",
    "low_factor_agreement": "因子分歧较大：各因子方向/强度不一致",
}


def divergence_caveat(code: str) -> str:
    """PURE: divergence code → fixed Chinese caveat; unknown → escaped raw code."""
    return _DIVERGENCE_CAVEATS.get(code, escape(code))


def _num(x: float) -> str:
    return f"{x:.4f}"


def _present_row(c, fresh: str) -> str:
    return (
        f"<tr><td>{escape(c.name)}</td><td>{_num(c.value)}</td>"
        f"<td>{_num(c.renorm_weight)}</td><td>{_num(c.contribution)}</td>"
        f"<td>{_num(c.confidence)}</td><td>{escape(fresh)}</td></tr>"
    )


def _na_row(s: FactorScore) -> str:
    return (
        f'<tr class="factor-na"><td>{escape(s.name)}</td>'
        "<td>—</td><td>—</td><td>—</td><td>—</td>"
        f"<td>{escape(s.reason)}</td></tr>"
    )


def factor_table_html(
    rec: SignalRecord, scores: tuple[FactorScore, ...], freshness: dict[str, str],
) -> str:
    """PURE: all-factors contribution table in canonical order, N/A rows dimmed."""
    by_contrib = {c.name: c for c in rec.contributions}
    by_score = {s.name: s for s in scores}
    rows = []
    for name in CANONICAL_FACTOR_ORDER:
        if name in by_contrib:
            rows.append(_present_row(by_contrib[name], freshness.get(name, "fresh")))
        elif name in by_score:
            rows.append(_na_row(by_score[name]))
    head = (
        "<tr><th>因子</th><th>值 sᵢ</th><th>权重 w'ᵢ</th>"
        "<th>贡献 w'ᵢ·sᵢ</th><th>置信</th><th>状态</th></tr>"
    )
    fams = "、".join(escape(f) for f in rec.present_families)
    footer = (
        f'<tr class="factor-foot"><td colspan="6">综合 C = {_num(rec.composite)} · '
        f"置信 {_num(rec.signal_confidence)} · available wt {_num(rec.available_weight)} · "
        f"families: {fams}</td></tr>"
    )
    return f"<table class='factors'>{head}{''.join(rows)}{footer}</table>"


def _ret_cell(w: int, v: float | None) -> str:
    return f"<td>{w}d: —</td>" if v is None else f"<td>{w}d: {v:+.2%}</td>"


def returns_table_html(rt: dict[int, float | None]) -> str:
    """PURE: [5,20,60,120,250]d returns row; None → —."""
    cells = "".join(_ret_cell(w, rt.get(w)) for w in (5, 20, 60, 120, 250))
    return f"<table class='returns'><tr>{cells}</tr></table>"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_render_factors.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_factors.py tests/monitor/test_render_factors.py
git commit -m "feat(monitor): pure factor-contribution + returns tables with canonical order and divergence map"
```

---

## Task 4: Verdict block, risk block, sectioned narrative (`render_cards.py`)

**Files:**
- Create: `src/irc/monitor/render_cards.py`
- Test: `tests/monitor/test_render_cards.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/monitor/test_render_cards.py
from irc.monitor.types import SignalRecord, NarrativeDoc, Claim
from irc.monitor.render_cards import verdict_block_html, risk_block_html, narrative_sections_html


def _rec(status="ok", bias="ADD_BIAS", c=0.5563, conf=0.9, fams=("price-momentum", "news"),
         aw=0.8, div=()):
    return SignalRecord(
        fund_id="x", status=status, bias=bias, composite=c, signal_confidence=conf,
        available_weight=aw, present_families=fams, contributions=(), divergence_codes=div,
    )


def _narr(sig=(), risk=(), pa=(), status="ok"):
    return NarrativeDoc("x", pa, sig, risk, status)


def test_ok_add_bias_clause_states_band_relationship():
    html = verdict_block_html(_rec(bias="ADD_BIAS", c=0.5563), _narr())
    assert "0.5563" in html
    assert "买入阈值" in html and "ADD_BIAS" in html


def test_ok_reduce_bias_clause():
    html = verdict_block_html(_rec(bias="REDUCE_BIAS", c=-0.6), _narr())
    assert "卖出阈值" in html and "REDUCE_BIAS" in html


def test_ok_neutral_clause_says_dead_band():
    html = verdict_block_html(_rec(bias="NEUTRAL", c=0.05), _narr())
    assert "中性带" in html and "NEUTRAL" in html


def test_insufficient_evidence_clause_names_gate_and_no_call():
    html = verdict_block_html(_rec(status="insufficient_evidence", bias=None, fams=("news",), aw=0.3), _narr())
    assert "insufficient_evidence" in html and "NO_CALL" in html
    assert "0.30" in html  # available_weight surfaced


def test_low_confidence_clause_names_confidence_and_no_call():
    html = verdict_block_html(_rec(status="low_confidence", bias=None, conf=0.3), _narr())
    assert "low_confidence" in html and "NO_CALL" in html
    assert "0.3" in html  # signal_confidence surfaced


def test_minimax_comment_renders_lead_claim_with_ref():
    narr = _narr(sig=(Claim("动能强劲", "consistent_with", ("a" * 16,)),
                      Claim("第二条不应出现", "consistent_with", ("b" * 16,))))
    html = verdict_block_html(_rec(), narr)
    assert "[ref:" + "a" * 16 + "]" in html
    assert "第二条不应出现" not in html  # capped to lead claim


def test_degraded_narrative_shows_note_not_comment():
    html = verdict_block_html(_rec(), _narr(status="schema_invalid: x"))
    assert "narrative" in html.lower()
    assert "schema_invalid" in html


def test_risk_block_maps_divergence_codes_to_caveats():
    html = risk_block_html(_rec(div=("trend_valuation_conflict",)), _narr())
    assert "趋势与估值背离" in html


def test_risk_block_includes_risk_claims_with_refs():
    narr = _narr(risk=(Claim("回撤风险上升", "consistent_with", ("c" * 16,)),))
    html = risk_block_html(_rec(), narr)
    assert "回撤风险上升" in html and "[ref:" + "c" * 16 + "]" in html


def test_risk_block_empty_renders_muted_placeholder():
    html = risk_block_html(_rec(div=()), _narr())
    assert "无显著风险信号" in html


def test_narrative_sections_only_price_action():
    narr = _narr(pa=(Claim("价格上行", "consistent_with", ()),),
                 sig=(Claim("不应在此", "consistent_with", ()),),
                 risk=(Claim("也不应在此", "consistent_with", ()),))
    html = narrative_sections_html(narr)
    assert "价格上行" in html
    assert "不应在此" not in html  # signal_rationale lives in verdict block
    assert "也不应在此" not in html  # risk lives in risk block
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/test_render_cards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.monitor.render_cards'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/irc/monitor/render_cards.py
from __future__ import annotations
from html import escape
from irc.monitor.types import Claim, NarrativeDoc, SignalRecord
from irc.monitor.render_factors import divergence_caveat

_BAND_PHRASE = {
    "ADD_BIAS": "≥ 买入阈值",
    "REDUCE_BIAS": "≤ 卖出阈值",
    "NEUTRAL": "落在中性带内",
}


def _claim_html(claim: Claim) -> str:
    text = escape(claim.claim)
    refs = "".join(f"[ref:{cid}]" for cid in claim.citation_ids)
    return f"<p>{text} {refs}</p>"


def _ok_clause(rec: SignalRecord) -> str:
    rel = _BAND_PHRASE.get(rec.bias or "NEUTRAL", "落在中性带内")
    return (
        f'综合分 C = {rec.composite:.4f}（{rel}）→ '
        f'<b>{escape(rec.bias)}</b>'
    )


def _gate_clause(rec: SignalRecord) -> str:
    if rec.status == "insufficient_evidence":
        return (
            f"insufficient_evidence — families {len(rec.present_families)} / "
            f"available_weight {rec.available_weight:.2f} 未达门槛 → <b>NO_CALL</b>"
        )
    return (
        f"low_confidence — signal_confidence {rec.signal_confidence:.4f} "
        f"低于最低置信 → <b>NO_CALL</b>"
    )


def _comment(narr: NarrativeDoc) -> str:
    if narr.status != "ok":
        return f'<p class="narr-degraded">narrative unavailable: {escape(narr.status)}</p>'
    lead = narr.signal_rationale_commentary[:1]
    return "".join(f'<blockquote>{_claim_html(c)}</blockquote>' for c in lead)


def verdict_block_html(rec: SignalRecord, narr: NarrativeDoc) -> str:
    """PURE: deterministic verdict clause + capped MiniMax comment."""
    clause = _ok_clause(rec) if rec.status == "ok" else _gate_clause(rec)
    return f'<div class="verdict"><p class="verdict-clause">{clause}</p>{_comment(narr)}</div>'


def risk_block_html(rec: SignalRecord, narr: NarrativeDoc) -> str:
    """PURE: divergence caveats + MiniMax risk claims; muted placeholder if empty."""
    caveats = [f"<li>{divergence_caveat(code)}</li>" for code in rec.divergence_codes]
    risk_claims = (
        [_claim_html(c) for c in narr.risk_commentary] if narr.status == "ok" else []
    )
    if not caveats and not risk_claims:
        return '<div class="risk"><p class="muted">无显著风险信号</p></div>'
    cav_html = f"<ul class='caveats'>{''.join(caveats)}</ul>" if caveats else ""
    return (
        '<div class="risk"><h3>风险 / Risk</h3>'
        + cav_html + "".join(risk_claims) + "</div>"
    )


def narrative_sections_html(narr: NarrativeDoc) -> str:
    """PURE: only price_action_commentary in its own section (signal→verdict, risk→risk)."""
    if narr.status != "ok":
        return ""
    if not narr.price_action_commentary:
        return ""
    body = "".join(_claim_html(c) for c in narr.price_action_commentary)
    return f'<div class="price-action"><h3>价格走势 / Price action</h3>{body}</div>'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_render_cards.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_cards.py tests/monitor/test_render_cards.py
git commit -m "feat(monitor): pure verdict block, risk block, sectioned narrative"
```

---

## Task 5: Assemble the card in `render_html.py` (CSS + delegation)

**Files:**
- Modify: `src/irc/monitor/render_html.py`
- Test: `tests/monitor/test_render_html.py` (add structural assertions before the golden refresh in Task 6)

- [ ] **Step 1: Write the failing tests** — append to `tests/monitor/test_render_html.py`. Update the module-level `_view()` factory FIRST so it supplies `factor_scores` (a present `trend` + an N/A `heat`), then add the new assertions.

In `_view()`, change the `FundView(...)` return to include:

```python
        factor_scores=(
            FactorScore("trend", 0.6, True, "", 1.0),
            FactorScore("valuation", None, False, "valuation_no_index", 1.0),
            FactorScore("heat", None, False, "heat_no_data", 1.0),
            FactorScore("macro_tilt", None, False, "macro_no_rows", 1.0),
            FactorScore("constituent", None, False, "constituent_no_snapshot", 1.0),
        ),
```

and add `FactorScore` to the imports from `irc.monitor.types`. New tests:

```python
def test_card_has_verdict_block():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert 'class="verdict"' in html
    assert "综合分 C" in html


def test_card_has_factor_table_with_na_rows():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert "class='factors'" in html
    assert "factor-na" in html               # at least one N/A factor row
    assert "heat_no_data" in html            # structured reason surfaced


def test_card_has_real_returns_table():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert "class='returns'" in html
    assert "60d:" in html and "250d:" in html  # the full window set


def test_card_has_risk_block_or_placeholder():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert 'class="risk"' in html


def test_old_missing_ul_is_gone():
    html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
    assert "class='missing'" not in html      # replaced by the factor table


def test_no_call_card_keeps_gate_clause_and_no_neutral_label():
    v = _view(status="insufficient_evidence", bias=None)
    html = render_report((v,), _prov(), prior_signal=None, now=_NOW)
    assert "NO_CALL" in html
    # NO_CALL ≠ NEUTRAL: the verdict clause must not assert a NEUTRAL call
    assert "落在中性带内" not in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/monitor/test_render_html.py -v`
Expected: FAIL — `verdict` / `factors` / `factor-na` not in html; `class='missing'` still present.

- [ ] **Step 3: Rewrite `_card` + `_narrative_html` removal + CSS** in `render_html.py`.

Replace the imports block (top of file):

```python
from __future__ import annotations
from html import escape
from irc.monitor.render_types import FundView, Provenance
from irc.monitor.render_cards import (
    narrative_sections_html, risk_block_html, verdict_block_html,
)
from irc.monitor.render_factors import factor_table_html, returns_table_html
from irc.monitor.svg_chart import EventMarker, render_nav_chart
```

Delete `_claim_html`, `_narrative_html`, and `_returns_html` from `render_html.py` (they now live in `render_cards.py` / `render_factors.py`). Keep `_NO_CALL`, `_badge`, `_markers`, `_summary_row`, `_appendix`, `render_report`.

Extend `_CSS` (append these rules inside the existing `<style>` string, before `</style>`):

```python
    ".verdict{margin:8px 0;padding:8px;border-left:3px solid #0969da;background:#f6f8fa}"
    ".verdict-clause{font-weight:600;margin:0 0 4px}"
    ".verdict blockquote{margin:4px 0;padding-left:8px;border-left:2px solid #d0d7de;color:#57606a}"
    ".factors{border-collapse:collapse;width:100%;max-width:680px;margin:8px 0;font-size:13px}"
    ".factors th,.factors td{border:1px solid #d0d7de;padding:3px 6px;text-align:right}"
    ".factors th:first-child,.factors td:first-child{text-align:left}"
    ".factor-na{color:#8c959f;background:#f6f8fa}"
    ".factor-foot td{text-align:left;background:#f6f8fa;font-size:12px}"
    ".returns{border-collapse:collapse;margin:8px 0;font-size:13px}"
    ".returns td{border:1px solid #d0d7de;padding:3px 8px}"
    ".risk{margin:8px 0;padding:8px;border-left:3px solid #cf222e;background:#fff8f6}"
    ".risk h3{margin:0 0 4px;color:#cf222e;font-size:14px}"
    ".price-action h3{font-size:14px;margin:8px 0 4px}"
    ".muted{color:#8c959f}"
```

Rewrite `_card`:

```python
def _card(view: FundView) -> str:
    chart = render_nav_chart(view.nav_series, markers=_markers(view))
    return (
        f'<section class="fund-card" id="fund-{view.fund_id}">'
        f"<h2>{escape(view.name_cn)} ({view.fund_id}) {_badge(view)}</h2>"
        f"{verdict_block_html(view.signal, view.narrative)}"
        f"{chart}"
        f"{returns_table_html(view.return_table)}"
        f"{factor_table_html(view.signal, view.factor_scores, view.factor_freshness)}"
        f"{narrative_sections_html(view.narrative)}"
        f"{risk_block_html(view.signal, view.narrative)}"
        "</section>"
    )
```

Note `view.return_table` is now `dict[int, float | None]`; `returns_table_html` (Task 3) already handles `None`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/monitor/test_render_html.py -v`
Expected: PASS for the new structural tests. **`test_golden_file` will FAIL** (golden not yet regenerated) — that is fixed in Task 6. All other invariant tests (XSS, citation closure, byte-stability, NO_CALL badge, changed-flag) must already PASS.

- [ ] **Step 5: Run the invariant guards explicitly**

Run: `uv run pytest tests/monitor/test_render_html.py -k "escaped or anchor or byte_stable or no_call or javascript or changed" -v`
Expected: PASS (these guard XSS, citation closure, byte-stability, NO_CALL≠NEUTRAL, no-JS, changed-flag).

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/render_html.py tests/monitor/test_render_html.py
git commit -m "feat(monitor): card assembles verdict/factor/returns/risk blocks; drop bare missing list"
```

---

## Task 6: Regenerate the golden fixture

**Files:**
- Regenerate: `tests/monitor/golden/report.html`
- Test: `tests/monitor/test_render_html.py::test_golden_file`

- [ ] **Step 1: Confirm the golden test currently fails**

Run: `uv run pytest tests/monitor/test_render_html.py::test_golden_file -v`
Expected: FAIL — assertion error (rendered HTML now differs from the stale golden).

- [ ] **Step 2: Regenerate the golden from the exact `_view()`/`_prov()`/`_NOW` fixture**

Run this one-off generator (mirrors the test inputs byte-for-byte; only `now=_NOW` is the volatile field and it is pinned):

```bash
uv run python -c "
from tests.monitor.test_render_html import _view, _prov, _NOW
from irc.monitor.render_html import render_report
from pathlib import Path
html = render_report((_view(),), _prov(), prior_signal=None, now=_NOW)
Path('tests/monitor/golden/report.html').write_text(html, encoding='utf-8')
print('golden bytes:', len(html))
"
```

(If `tests` is not importable as a package, prepend `import sys; sys.path.insert(0, '.')` — but `tests/monitor/__init__.py` already exists, so the import path works from repo root.)

- [ ] **Step 3: Run the golden test to verify it passes**

Run: `uv run pytest tests/monitor/test_render_html.py::test_golden_file -v`
Expected: PASS

- [ ] **Step 4: Eyeball the regenerated golden** — confirm it contains, in order: `class="verdict"`, the navchart `<svg>`, `class='returns'` with `5d:…250d:`, `class='factors'` with a `factor-na` row carrying `heat_no_data`, optional `price-action`, and `class="risk"`. Confirm no `class='missing'`.

Run: `grep -o "class=.verdict.\|class=.factors.\|factor-na\|class=.returns.\|class=.risk.\|class=.missing." tests/monitor/golden/report.html | sort -u`
Expected: lists verdict, factors, factor-na, returns, risk — and NOT missing.

- [ ] **Step 5: Commit**

```bash
git add tests/monitor/golden/report.html
git commit -m "test(monitor): regenerate golden report fixture for verdict-justification card"
```

---

## Task 7: Edge wiring in `_make_view` (`monitor_cmd.py`)

**Files:**
- Modify: `src/irc/commands/monitor_cmd.py:211-235` (`_make_view`)
- Test: `tests/commands/test_monitor_cmd.py`

- [ ] **Step 1: Write the failing tests** — add to `tests/commands/test_monitor_cmd.py`. These exercise the edge wiring without network (pure inputs).

```python
def test_make_view_populates_factor_scores_and_return_table():
    from irc.commands.monitor_cmd import _make_view
    from irc.monitor.fetch import NavFetchResult
    from irc.monitor.types import (
        FactorScore, SignalRecord, NarrativeDoc, MonitorFund,
    )
    fund = MonitorFund(
        id="008986", name_cn="n", market="cn_off_exchange", analysis_profile="gold",
        themes=(), constituent_news=False, weights={"trend": 1.0},
        bands={"buy": 0.4, "sell": -0.4}, minimum_confidence=0.5,
    )
    acc = tuple((f"2026-01-{i % 28 + 1:02d}", 1.0 + 0.001 * i) for i in range(300))
    nav = NavFetchResult(latest_nav=acc[-1][1], as_of_date="2026-06-15", acc_series=acc)
    rec = SignalRecord("008986", "ok", "ADD_BIAS", 0.6, 0.9, 1.0, ("price-momentum",),
                       (), ())
    scores = (
        FactorScore("trend", 0.6, True, "", 1.0),
        FactorScore("heat", None, False, "heat_no_data", 1.0),
    )
    narr = NarrativeDoc("008986", (), (), (), "ok")
    view = _make_view(fund, nav, rec, scores, narr, ())
    assert view.factor_scores == scores            # full ordered set incl. N/A
    assert set(view.return_table) == {5, 20, 60, 120, 250}
    assert view.return_table[60] is not None       # 300 points → all windows valued


def test_make_view_no_nav_yields_all_none_returns():
    from irc.commands.monitor_cmd import _make_view
    from irc.monitor.types import SignalRecord, NarrativeDoc, MonitorFund, FactorScore
    fund = MonitorFund("x", "n", "m", "gold", (), False, {}, {"buy": .4, "sell": -.4}, .5)
    rec = SignalRecord("x", "insufficient_evidence", None, 0.0, 0.0, 0.0, (), (), ())
    narr = NarrativeDoc("x", (), (), (), "ok")
    view = _make_view(fund, None, rec, (FactorScore("trend", None, False, "no_nav", 1.0),), narr, ())
    assert all(v is None for v in view.return_table.values())
    assert view.factor_scores[0].name == "trend"
```

(Check the real `NavFetchResult` field names with `grep -n "class NavFetchResult\|acc_series\|latest_nav\|as_of_date" src/irc/monitor/fetch.py` and adjust the constructor in the test if they differ — the production `_process_fund` already passes `nav.acc_series`, `nav.latest_nav`, `nav.as_of_date`, so those three are the contract.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_monitor_cmd.py -k make_view -v`
Expected: FAIL — `factor_scores` defaults to `()` (not populated) and `return_table` is `{}` (empty, not the 5-key dict).

- [ ] **Step 3: Wire the edge** — edit `_make_view` in `src/irc/commands/monitor_cmd.py`. Add the import near the other monitor imports at the top of the file:

```python
from irc.monitor.returns import window_returns
```

Change the `FundView(...)` construction in `_make_view`:

```python
    return FundView(
        fund_id=fund.id,
        name_cn=fund.name_cn,
        latest_nav=nav.latest_nav if nav else 0.0,
        as_of_date=nav.as_of_date if nav else "N/A",
        nav_series=nav.acc_series if nav else (),
        signal=signal,
        narrative=narr_doc,
        evidence_pool=pool,
        return_table=window_returns(nav.acc_series if nav else ()),
        factor_freshness={c.name: "fresh" for c in signal.contributions},
        missing_factor_reasons=tuple(
            f"{s.name}: {s.reason}" for s in scores if not s.eligible
        ),
        factor_scores=tuple(scores),
        impacts_status=impacts_status,
    )
```

(`missing_factor_reasons` is kept — other consumers / JSON dumps may still read it; only the renderer stopped using it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/commands/test_monitor_cmd.py -k make_view -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/irc/commands/monitor_cmd.py tests/commands/test_monitor_cmd.py
git commit -m "feat(monitor): wire factor_scores + window_returns into _make_view at the edge"
```

---

## Task 8: Full monitor suite green + lint + migrate stale FundView constructions

**Files:**
- Modify (as needed): any test that constructs `FundView(...)` positionally and now breaks.

- [ ] **Step 1: Run the whole monitor + command suite**

Run: `uv run pytest tests/monitor tests/commands/test_monitor_cmd.py -v`
Expected: ALL PASS. The `factor_scores=()` default (Task 2) keeps keyword-only constructions valid; only **positional** `FundView(...)` calls past `missing_factor_reasons` would break. If any test fails on `FundView` arity, add `factor_scores=(...)` explicitly to that construction (do NOT remove the default).

- [ ] **Step 2: Lint**

Run: `uv run ruff check src/irc/monitor src/irc/commands/monitor_cmd.py tests/monitor tests/commands/test_monitor_cmd.py`
Expected: `All checks passed!` (line-length 100). Fix any long lines by extracting locals — do not raise the limit.

- [ ] **Step 3: Confirm file-size budget held**

Run: `wc -l src/irc/monitor/render_html.py src/irc/monitor/render_cards.py src/irc/monitor/render_factors.py src/irc/monitor/returns.py`
Expected: each < 200 lines (render_html.py should now be ~110-130 after extraction).

- [ ] **Step 4: Commit any migration fixes**

```bash
git add -A
git commit -m "test(monitor): migrate FundView constructions to carry factor_scores"
```

---

## Task 9: Exit-gate — regenerate today's report from cache, capture evidence

**Goal:** produce `outputs/2026-06-15/monitor/report.html` with the new card, **without new LLM spend**, then eyeball one card. Cached `impacts.json` / `narrative.json` exist at `outputs/2026-06-15/monitor/` (verified). Per MASTER-SPEC §6 / design §6, a same-day rerun reuses hash-matching cached impacts/narrative.

- [ ] **Step 1: Preferred path — `uv run irc monitor`** (reuses cached impacts/narrative on a hash-stable same-day rerun; no new LLM calls).

Run: `MINIMAX_API_KEY=$MINIMAX_API_KEY uv run irc monitor`
Expected: exit 0; `outputs/2026-06-15/monitor/report.html` rewritten. If the spend gate / key check / network blocks this (exit 5 or a key error), fall through to Step 2.

- [ ] **Step 2: Fallback — render-from-cache (no LLM, no network)** — recompute the pure factor→signal stage from cached NAV + reuse the cached narrative/impacts JSON, then re-render. Use a throwaway script (do not commit it):

```bash
uv run python -c "
import json
from pathlib import Path
from irc.commands.monitor_cmd import run_monitor
# run_monitor reuses cached impacts/narrative on same-day rerun; only re-renders.
rc = run_monitor(repo_root='.', today='2026-06-15')
print('rc', rc)
"
```

If `run_monitor` still attempts a live LLM call (cache miss / hash drift), instead drive the pure path directly: load cached `outputs/2026-06-15/monitor/narrative.json` + `impacts.json`, rebuild each `FundView` via the pure `build_factor_scores → compute_signal → window_returns` chain against `nav_series_for(fund_id)` (no network if NAV is DuckDB-cached), reconstruct `NarrativeDoc`s from the cached JSON, and call `render_report`. The point of the gate is the **renderer output**, not a fresh fetch.

- [ ] **Step 3: Structural assertions on the produced report**

```bash
grep -c 'class="fund-card"' outputs/2026-06-15/monitor/report.html   # expect 7
grep -o "class=.verdict.\|class=.factors.\|factor-na\|class=.returns.\|class=.risk." outputs/2026-06-15/monitor/report.html | sort | uniq -c
```

Expected: 7 fund-cards (H3 universal rows — every Monitor-set fund has a card, incl. any NO_CALL); verdict / factors / returns / risk all present; at least one `factor-na` row across the report.

- [ ] **Step 4: Citation closure check on the live report**

```bash
uv run python -c "
import re
h = open('outputs/2026-06-15/monitor/report.html', encoding='utf-8').read()
anchors = set(re.findall(r'\[ref:([0-9a-f]{16})\]', h))
appendix = set(re.findall(r'id=\"ev-([0-9a-f]{16})\"', h))
print('orphans', anchors - appendix)
print('uncited', appendix - anchors)
assert anchors <= appendix, 'orphan refs'
"
```

Expected: no orphan refs (`anchors ⊆ appendix`).

- [ ] **Step 5: Capture a card visually** — open `outputs/2026-06-15/monitor/report.html`, confirm one card shows verdict block (clause + MiniMax comment), returns table with all five windows, factor table with N/A rows, and the risk block. Save a screenshot as the acceptance evidence.

- [ ] **Step 6: Final full-suite sanity** (scoped — the full repo suite is ~61 min and known-non-green on main; run the monitor surface only):

Run: `uv run pytest tests/monitor tests/commands/test_monitor_cmd.py tests/test_cli_monitor.py -q`
Expected: all green.

---

## Self-Review (spec coverage)

- **R1 verdict block** → Task 4 (`verdict_block_html`: ok-clause band relationship via D2, gate clauses for `insufficient_evidence`/`low_confidence`, capped MiniMax comment via D3, degraded note) + Task 5 (rendered into card).
- **R2 factor table** → Task 3 (`factor_table_html`: canonical order D1, present numeric rows from `contributions`, dimmed N/A rows with structured `reason` D4, footer with composite/confidence/available_weight/families).
- **R3 returns table** → Task 1 (`window_returns`) + Task 7 (wired into `return_table`) + Task 3 (`returns_table_html` with `—` for None).
- **R4 risk block** → Task 4 (`risk_block_html`: divergence→caveat map D6 + MiniMax risk claims + muted placeholder).
- **R5 sectioned narrative** → Task 4 (`narrative_sections_html`: price-action only; no merge; signal→verdict, risk→risk — no duplication).
- **R6 wiring** → Task 2 (`FundView.factor_scores`) + Task 7 (`_make_view` populates `factor_scores` + `return_table`).
- **Invariants** → byte-stability (`test_byte_stable...`, `test_golden_file`), XSS (`test_hostile_title_is_escaped` — extended sections inherit escaping via `escape()` in every builder), H3 universal rows (Task 9 Step 3 expects 7 cards), citation closure (`test_anchor_set_equals_appendix_id_set` + Task 9 Step 4), NO_CALL≠NEUTRAL (`test_no_call_card_keeps_gate_clause_and_no_neutral_label`).

## Risks / watch-outs

- **`signal_rationale_commentary` may be empty in production** — many funds carry no LLM rationale claim; D3 renders nothing, so the deterministic clause must always stand alone. Good (intended), but means the MiniMax comment is often absent — not a bug.
- **`NavFetchResult` constructor in Task 7 tests** — confirm its real field names before writing the test (grep noted in Task 7 Step 1). Production already passes `acc_series`/`latest_nav`/`as_of_date`, so those are safe.
- **Golden drift from SVG geometry** — the navchart SVG is the bulk of the golden bytes and is unchanged by this work; regenerating from the same `_view()` fixture keeps it stable. Only the new blocks are added around it.
- **`return_table` type change** (`dict[int, float]` → `dict[int, float | None]`) — `_summary_row` does not read `return_table`, and `returns_table_html` handles `None`; no other consumer reads it. The `monitor.json`/`impacts.json` dumps do not include `return_table`. Verified no downstream break.
- **XSS on new prose** — every new builder routes untrusted text through `html.escape`; the `[ref:…]` markers are renderer-appended (never from LLM text), preserving the existing trust boundary. The hostile-title fixture covers evidence titles; the verdict/risk claim text is escaped in `_claim_html`.
- **Exit-gate cache reuse** — if same-day hash drift forces a live call, Step 2 fallback drives the pure render path from cached JSON, satisfying the no-new-spend constraint. Do not commit the throwaway generator scripts.
