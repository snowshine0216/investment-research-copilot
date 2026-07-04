# Item 001 — WS-1 Caveat Transparency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every `⚠ caveated` badge self-explanatory (age-stamped reasons → gate → tooltip/anchor + ONE 今日速览 line + card 为何有保留 + panel hint) and self-healing (Saturday wrapper refreshes both LLM eval suites), carrying the ONE eval-trace schema bump 6→7.

**Architecture:** Slice 1 populates reasons in the pure eval layer (`staleness.py` age-stamp, `gate.py` caveated-branch assembly + `RUN_GLOBAL_STAGES` literal). Slice 2 renders them (chip anchor/tooltip in `render_html.py`, dedupe line + label helpers in `render_overview.py`, id + hint in `panel.py`). Slice 2b unifies `SCHEMA_VERSION` and bumps to `"7"`. Slice 3 appends two best-effort watchdog-bounded eval runs to `ops/launchd/run-weekly.sh`.

**Tech Stack:** Python 3.12, uv, pytest, ruff; bash launchd wrapper; no new dependencies.

**Spec:** `docs/2026-07-03-monitor-v4-explainability/items/001-spec.md` (honor corrected lines RD-1…RD-9, not struck ones).

## Global Constraints

- Branch: work happens on `claude/monitor-v4-explainability-001` (already cut). Commit per task; do NOT push.
- Pure functions, no clock reads in render code (ages parsed from `stale, {N}d` strings, never recomputed); effects at edges (the ONLY I/O change is the shell wrapper).
- No mutation of arguments; frozen dataclasses stay frozen; functions < 20 lines ideal.
- `apply_eval_gate` / `resolve_health` / `render_report` signatures unchanged; `overview_html` gains exactly ONE keyword-only param.
- No new fields on `GateDecision` / `StageHealth` / trace shape — only the existing `gate.reason` string gets populated.
- Schema bump `"6"` → `"7"` EXACTLY ONCE (Task 7); `_ENGINE_VERSION` untouched; forward-ledger append logic untouched (`src/irc/monitor/eval/forward_log.py` must show no diff).
- Gate semantics unchanged: caveated never suppresses; `GATING_STAGES_M1` membership unchanged; `STALE_AFTER_DAYS` stays 14; `STALE_EVAL_DAYS` stays 10.
- Citation/HTML security: all reason/tooltip strings HTML-escaped before entering `title`/body.
- Test commands: `uv run pytest tests/monitor/ -q` (includes `tests/monitor/eval/`), `uv run pytest tests/ops/ -q`, per-file `uv run pytest tests/commands/test_monitor_cmd_trace.py -q` etc. — **NEVER run the whole `tests/commands/` dir (it hangs)**. Lint: `uv run ruff check src tests` (line-length 100).
- `VERSION` NOT bumped; CHANGELOG `[Unreleased]` entry added (Task 9).
- CONTEXT.md glossary entries (今日速览 fourth row, Validation badge/chip, *Caveat reason*) were added at grill time — implementation must match them (verified in Task 10); amend only on mismatch.

---

### Task 1: Staleness age-stamp (`("stale",)` → `("stale, {N}d",)`)

**Files:**
- Modify: `src/irc/monitor/eval/staleness.py:25-26`
- Test: `tests/monitor/eval/test_staleness.py`

**Interfaces:**
- Produces: `resolve_health(...)` now emits `StageHealth(stage, "UNKNOWN", ("stale, 15d",))` on the stale branch. `absent`/`skipped`/`corrupt_ran_at` reasons unchanged. Stale iff `(now - ran_at).days > stale_after_days` (strict `>`, as-built) — minimum stamp under the default 14 is `15d`.
- Consumed by: Task 2 (gate reason), Task 3 (tooltip 上次质量评估已过期), Task 5 (overview age parse).

- [ ] **Step 1: Write the failing tests**

Append to `tests/monitor/eval/test_staleness.py` (the file already imports `StageReport`, `resolve_health`, `_NOW`, `timedelta` and defines `_report`):

```python
# ── report v4 item 001: age-stamped stale reason ─────────────────────────────


def test_stale_reason_is_age_stamped_15d():
    old = _NOW - timedelta(days=15)
    h = resolve_health(_report("PASS", ran_at=old), now=_NOW, stale_after_days=14,
                       stage="monitor_impact")
    assert h.status == "UNKNOWN"
    assert h.reasons == ("stale, 15d",)


def test_stale_reason_is_age_stamped_16d():
    old = _NOW - timedelta(days=16)
    h = resolve_health(_report("PASS", ran_at=old), now=_NOW, stale_after_days=14,
                       stage="monitor_narrative")
    assert h.reasons == ("stale, 16d",)


def test_exactly_stale_after_days_is_not_stale_unchanged_boundary():
    # As-built semantics: stale iff .days > stale_after_days (strict) — exactly
    # 14d passes through. The minimum stamped age is therefore 15d (RD-7).
    boundary = _NOW - timedelta(days=14)
    h = resolve_health(_report("PASS", ran_at=boundary), now=_NOW, stale_after_days=14,
                       stage="monitor_impact")
    assert h.status == "PASS"


def test_absent_skipped_corrupt_reasons_unchanged_no_age():
    assert resolve_health(None, now=_NOW, stale_after_days=14,
                          stage="monitor_impact").reasons == ("absent",)
    assert resolve_health(_report("SKIPPED", ran_at=_NOW), now=_NOW,
                          stale_after_days=14,
                          stage="monitor_impact").reasons == ("skipped",)
    bad = StageReport(stage="monitor_impact", ran_at="NOT-A-DATE", based_on=[],
                      metrics=[], overall="PASS")
    assert resolve_health(bad, now=_NOW, stale_after_days=14,
                          stage="monitor_impact").reasons == ("corrupt_ran_at",)
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `uv run pytest tests/monitor/eval/test_staleness.py -q`
Expected: 2 failures (`test_stale_reason_is_age_stamped_15d`, `test_stale_reason_is_age_stamped_16d` — reasons are `("stale",)`); the boundary and unchanged tests pass.

- [ ] **Step 3: Implement the age-stamp**

In `src/irc/monitor/eval/staleness.py`, replace:

```python
    if (now - ran_at).days > stale_after_days:
        return StageHealth(report.stage, "UNKNOWN", ("stale",))
```

with:

```python
    age_days = (now - ran_at).days
    if age_days > stale_after_days:
        return StageHealth(report.stage, "UNKNOWN", (f"stale, {age_days}d",))
```

- [ ] **Step 4: Run tests to verify green**

Run: `uv run pytest tests/monitor/eval/test_staleness.py -q`
Expected: all pass (existing `test_stale_report_is_unknown_stale` uses substring `"stale" in h.reasons[0]` and survives — RD-7).

Run: `uv run pytest tests/monitor/eval/ -q`
Expected: all pass (blast radius verified empty by RD-7: `test_gate.py:31` / `test_determinism.py:199` are self-contained fixtures).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/staleness.py tests/monitor/eval/test_staleness.py
git commit -m "feat(monitor): age-stamp the stale suite-health reason (stale, Nd)"
```

---

### Task 2: Gate caveat-reason assembly + `RUN_GLOBAL_STAGES` literal

**Files:**
- Modify: `src/irc/monitor/eval/gate.py`
- Test: `tests/monitor/eval/test_gate.py`, `tests/monitor/eval/test_gate_flip_m1.py`

**Interfaces:**
- Produces: `RUN_GLOBAL_STAGES: frozenset[str] = frozenset({"monitor_impact", "monitor_narrative"})` (explicit literal, importable). Caveated `GateDecision.reason` format (locked P1): one segment per considered WARN/UNKNOWN stage in `health` order, `"{stage}: {status} ({reasons joined ', '})"`, parenthetical omitted when the reasons tuple is empty, segments joined `"; "`. FAIL branch byte-identical to today. Validated reason stays `""`.
- Consumed by: Task 3 (tooltip input + `RUN_GLOBAL_STAGES` via render helpers), Task 4 (panel hint trigger), Task 5 (overview classification), Task 6 (segment filter), Task 7 (trace `gate.reason`).

- [ ] **Step 1: Write the failing tests**

In `tests/monitor/eval/test_gate.py`, replace the import line:

```python
from irc.monitor.eval.gate import apply_eval_gate, published_state, GATING_STAGES_M0
```

with:

```python
from irc.monitor.eval.gate import (
    GATING_STAGES_M0, GATING_STAGES_M1, RUN_GLOBAL_STAGES, apply_eval_gate,
    published_state,
)
```

Append to the file:

```python
# ── report v4 item 001: RUN_GLOBAL_STAGES literal + caveat-reason assembly ────


def test_run_global_stages_is_explicit_literal_matching_m1_minus_m0():
    # RD-2 guard: the pin only has teeth against a LITERAL definition. If a
    # future per-fund gating stage joins GATING_STAGES_M1, this breaks loudly
    # and forces a conscious run-global-vs-fund-specific classification.
    assert RUN_GLOBAL_STAGES == frozenset({"monitor_impact", "monitor_narrative"})
    assert RUN_GLOBAL_STAGES == GATING_STAGES_M1 - GATING_STAGES_M0


def test_caveated_reason_unknown_stale_with_age_matches_p1_verbatim():
    h = (StageHealth("monitor_impact", "UNKNOWN", ("stale, 15d",)),
         StageHealth("monitor_narrative", "UNKNOWN", ("stale, 16d",)))
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.badge == "caveated" and g.suppressed is False
    assert g.reason == ("monitor_impact: UNKNOWN (stale, 15d); "
                        "monitor_narrative: UNKNOWN (stale, 16d)")


def test_caveated_reason_warn_only_monitor_signal():
    h = (StageHealth("monitor_signal", "WARN", ("gap 12d",)),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.reason == "monitor_signal: WARN (gap 12d)"


def test_caveated_reason_mixed_warn_and_unknown_preserves_health_order():
    h = (StageHealth("monitor_signal", "WARN", ("missed 3 trading days", "obs<2")),
         StageHealth("monitor_impact", "UNKNOWN", ("stale, 15d",)),
         StageHealth("monitor_narrative", "PASS", ()))
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.reason == ("monitor_signal: WARN (missed 3 trading days, obs<2); "
                        "monitor_impact: UNKNOWN (stale, 15d)")


def test_caveated_reason_segment_split_survives_commas_and_colons():
    # RD-7 test-shape note: reason strings may contain ", " and ": " — only
    # "; " is the segment joiner, so renderer prefix-filtering stays unambiguous.
    h = (StageHealth("monitor_signal", "WARN", ("unresolved: abcd1234, twice",)),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.reason == "monitor_signal: WARN (unresolved: abcd1234, twice)"
    assert "; " not in g.reason


def test_caveated_reason_omits_parenthetical_when_reasons_empty():
    h = (StageHealth("monitor_signal", "WARN", ()),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.reason == "monitor_signal: WARN"


def test_validated_reason_stays_empty():
    h = (StageHealth("monitor_signal", "PASS", ()),
         StageHealth("monitor_impact", "PASS", ()),
         StageHealth("monitor_narrative", "PASS", ()))
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.badge == "validated" and g.reason == ""


def test_gated_fail_branch_reason_byte_identical_to_today():
    # FAIL wins over WARN/UNKNOWN and keeps the OLD assembly (raw reasons,
    # no stage prefix) — unchanged by this item.
    h = (StageHealth("monitor_signal", "FAIL", ("nav_quality FAIL",)),
         StageHealth("monitor_impact", "UNKNOWN", ("stale, 15d",)))
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.suppressed is True and g.badge == "gated"
    assert g.reason == "nav_quality FAIL"
```

(`StageHealth` and `_signal` already exist in the file.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/eval/test_gate.py -q`
Expected: FAIL — `ImportError: cannot import name 'RUN_GLOBAL_STAGES'`.

- [ ] **Step 3: Implement in `gate.py`**

Replace the full contents of `src/irc/monitor/eval/gate.py` with:

```python
"""PURE eval gate (roadmap §3.5). M0 gating set = {monitor_signal} only."""
from __future__ import annotations
from irc.monitor.eval.types import GateDecision, StageHealth
from irc.monitor.types import SignalRecord

GATING_STAGES_M0 = frozenset({"monitor_signal"})
GATING_STAGES_M1 = GATING_STAGES_M0 | frozenset({"monitor_impact", "monitor_narrative"})

# Run-global vs fund-specific caveat-cause classification (report v4 item 001,
# RD-2). EXPLICIT literal, deliberately NOT derived as M1 - M0: "run-global"
# means the health is resolved once per run at the edge (_suite_eval) and is
# identical for every fund — a resolution-locality property, NOT derivable from
# gating-set membership. A future per-fund gating stage added to
# GATING_STAGES_M1 must not silently classify as run-global; the equality guard
# test in tests/monitor/eval/test_gate.py breaks loudly instead.
RUN_GLOBAL_STAGES = frozenset({"monitor_impact", "monitor_narrative"})


def _caveat_reason(considered: list[StageHealth]) -> str:
    """P1 format (locked): one segment per WARN/UNKNOWN stage, in health order —
    "{stage}: {status} ({reasons joined ', '})", parens omitted on an empty
    reasons tuple, segments joined "; "."""
    segments = []
    for h in considered:
        if h.status not in ("WARN", "UNKNOWN"):
            continue
        joined = ", ".join(h.reasons)
        segments.append(f"{h.stage}: {h.status} ({joined})" if joined
                        else f"{h.stage}: {h.status}")
    return "; ".join(segments)


def apply_eval_gate(
    signal: SignalRecord, *, health: tuple[StageHealth, ...], gating_stages: frozenset[str],
) -> GateDecision:
    considered = [h for h in health if h.stage in gating_stages]
    failed = tuple(h.stage for h in considered if h.status == "FAIL")
    if failed:
        reason = "; ".join(r for h in considered if h.status == "FAIL" for r in h.reasons)
        return GateDecision(signal.fund_id, True, failed, "gated", reason or "fresh FAIL")
    if any(h.status in ("WARN", "UNKNOWN") for h in considered):
        return GateDecision(signal.fund_id, False, (), "caveated", _caveat_reason(considered))
    return GateDecision(signal.fund_id, False, (), "validated", "")


def published_state(signal: SignalRecord, gate: GateDecision) -> str:
    if signal.status != "ok":
        return "NO_CALL"
    if gate.suppressed:
        return "EVAL_GATED"
    return signal.bias  # type: ignore[return-value]
```

- [ ] **Step 4: Add the e2e reason assertion (criterion 9 path)**

In `tests/monitor/eval/test_gate_flip_m1.py`, function `test_missing_suite_reports_fail_open`, after the line `assert gates[0].badge == "caveated"  # Finding 1: missing report must be caveated, not validated` append:

```python
    # report v4 item 001: the caveated reason is populated end-to-end through
    # _suite_eval -> _compute_gates (absent reports carry no age).
    assert gates[0].reason == ("monitor_impact: UNKNOWN (absent); "
                               "monitor_narrative: UNKNOWN (absent)")
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/monitor/eval/test_gate.py tests/monitor/eval/test_gate_flip_m1.py -q`
Expected: all pass.

Run: `uv run pytest tests/monitor/eval/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/eval/gate.py tests/monitor/eval/test_gate.py tests/monitor/eval/test_gate_flip_m1.py
git commit -m "feat(monitor): populate caveated GateDecision.reason + RUN_GLOBAL_STAGES literal"
```

---

### Task 3: Chip tooltip + anchor (+ label helpers, CSS rule, golden regen)

**Files:**
- Modify: `src/irc/monitor/render_overview.py` (label map + `caveat_tooltip` + `fund_specific_segments`)
- Modify: `src/irc/monitor/render_html.py` (`_chip` helper, `_badge`, `_CSS`, import)
- Modify: `tests/monitor/golden/report.html` (regenerated — CSS-only diff)
- Test: `tests/monitor/test_render_overview.py`, `tests/monitor/test_render_html_eval.py`

**Interfaces:**
- Produces: `caveat_tooltip(reason: str) -> str` — Chinese-labeled, UNESCAPED (badge escapes at the HTML edge). `fund_specific_segments(reason: str) -> tuple[str, ...]` — segments whose stage-prefix ∉ `RUN_GLOBAL_STAGES`. Both in `render_overview.py` (spec constraint: render additions live in `render_overview.py`/`panel.py`).
- Consumed by: Task 6 (`fund_specific_segments` for the card line).

- [ ] **Step 1: Write the failing helper unit tests**

Append to `tests/monitor/test_render_overview.py`:

```python
# ── report v4 item 001: caveat label map / tooltip / segment classification ──


def test_caveat_tooltip_maps_stage_labels_and_stale_age():
    from irc.monitor.render_overview import caveat_tooltip
    reason = ("monitor_impact: UNKNOWN (stale, 15d); "
              "monitor_narrative: UNKNOWN (stale, 16d)")
    assert caveat_tooltip(reason) == (
        "影响评分质量评估: UNKNOWN (上次质量评估已过期 15天); "
        "叙事质量评估: UNKNOWN (上次质量评估已过期 16天)")


def test_caveat_tooltip_unmapped_stage_and_reasons_pass_raw():
    # P2 locks only the three Chinese labels — monitor_signal and raw metric
    # strings (gap 12d etc.) pass through untranslated (open question 11).
    from irc.monitor.render_overview import caveat_tooltip
    assert caveat_tooltip("monitor_signal: WARN (gap 12d)") == "monitor_signal: WARN (gap 12d)"
    assert caveat_tooltip("") == ""


def test_fund_specific_segments_filters_run_global_prefixes():
    from irc.monitor.render_overview import fund_specific_segments
    reason = ("monitor_signal: WARN (gap 12d); "
              "monitor_impact: UNKNOWN (stale, 15d)")
    assert fund_specific_segments(reason) == ("monitor_signal: WARN (gap 12d)",)
    assert fund_specific_segments("") == ()
    assert fund_specific_segments(
        "monitor_impact: UNKNOWN (stale, 15d); monitor_narrative: UNKNOWN (stale, 16d)"
    ) == ()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_render_overview.py -q`
Expected: FAIL — `ImportError: cannot import name 'caveat_tooltip'`.

- [ ] **Step 3: Implement the helpers in `render_overview.py`**

In `src/irc/monitor/render_overview.py`, add `import re` after `from __future__ import annotations`, and extend the gate import:

```python
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import date, datetime
from html import escape

from irc.monitor.eval.gate import RUN_GLOBAL_STAGES, published_state
```

Append at the end of the file:

```python
# ── Caveat reason surfaces (report v4 item 001, P2) ───────────────────────────
# The three locked Chinese labels (P2); everything else passes through raw.
_SUITE_LABELS_CN = {"monitor_impact": "影响评分质量评估",
                    "monitor_narrative": "叙事质量评估"}
_STALE_REASON_RE = re.compile(r"stale, (\d+)d")


def caveat_tooltip(reason: str) -> str:
    """PURE: gate caveat reason -> Chinese-labeled tooltip text. Stage prefixes
    map via _SUITE_LABELS_CN; a `stale, {N}d` reason renders 上次质量评估已过期
    {N}天; unmapped stages / other reason strings pass through raw. Returns
    UNESCAPED text — the badge escapes at the HTML edge."""
    segments = []
    for seg in reason.split("; "):
        head, sep, rest = seg.partition(": ")
        body = _STALE_REASON_RE.sub(lambda m: f"上次质量评估已过期 {m.group(1)}天", rest)
        segments.append(f"{_SUITE_LABELS_CN.get(head, head)}{sep}{body}")
    return "; ".join(segments)


def fund_specific_segments(reason: str) -> tuple[str, ...]:
    """PURE: caveat-reason segments NOT attributed to a run-global stage
    (prefix before ': ' not in RUN_GLOBAL_STAGES) — today: monitor_signal WARNs.
    Only "; " splits segments; reason strings may contain ", "/": " (RD-7)."""
    return tuple(seg for seg in reason.split("; ")
                 if seg and seg.partition(": ")[0] not in RUN_GLOBAL_STAGES)
```

- [ ] **Step 4: Run helper tests green**

Run: `uv run pytest tests/monitor/test_render_overview.py -q`
Expected: all pass.

- [ ] **Step 5: Write the failing chip tests**

Append to `tests/monitor/test_render_html_eval.py`:

```python
# ── report v4 item 001: caveated chip = anchor + Chinese tooltip ─────────────


def test_caveated_chip_is_anchor_with_chinese_tooltip():
    reason = ("monitor_impact: UNKNOWN (stale, 15d); "
              "monitor_narrative: UNKNOWN (stale, 16d)")
    html = _render(_view(bias="ADD_BIAS"), _gate(badge="caveated", reason=reason))
    assert '<a class="val-chip val-caveated" href="#validation-panel"' in html
    assert "影响评分质量评估: UNKNOWN (上次质量评估已过期 15天)" in html
    assert "叙事质量评估: UNKNOWN (上次质量评估已过期 16天)" in html
    assert ">⚠ caveated</a>" in html


def test_caveated_tooltip_is_html_escaped():
    html = _render(_view(), _gate(badge="caveated",
                                  reason='monitor_signal: WARN (gap "12d" & more)'))
    assert 'title="monitor_signal: WARN (gap &quot;12d&quot; &amp; more)"' in html


def test_validated_chip_stays_plain_span_no_anchor_no_tooltip():
    html = _render(_view(), _gate(badge="validated"))
    assert '<span class="val-chip val-validated">✓ validated</span>' in html
    assert '<a class="val-chip val-validated"' not in html
```

- [ ] **Step 6: Run to verify failure**

Run: `uv run pytest tests/monitor/test_render_html_eval.py -q`
Expected: 2 new tests FAIL (chip is still a span); the validated test passes.

- [ ] **Step 7: Implement the chip in `render_html.py`**

(a) Extend the `render_overview` import (lines 27-29) to:

```python
from irc.monitor.render_overview import (
    caveat_tooltip, compute_actionable, compute_data_health, compute_flips,
    overview_html,
)
```

(b) Add a `_chip` helper directly above `_badge` and rewrite `_badge`'s chip block. Replace:

```python
def _badge(view: FundView, gate: GateDecision | None) -> str:
    if gate is None:
        if view.signal.status != "ok":
            return f'<span class="badge no-call">{_NO_CALL}</span>'
        return f'<span class="badge {view.signal.bias.lower()}">{escape(view.signal.bias)}</span>'
    state = published_state(view.signal, gate)
    if state == _NO_CALL:
        return f'<span class="badge no-call">{_NO_CALL}</span>'
    if state == _EVAL_GATED:
        return '<span class="badge eval-gated">EVAL-GATED 🛡</span>'
    chip = ""
    cls_label = _CHIP.get(gate.badge)
    if cls_label:
        cls, label = cls_label
        chip = f'<span class="val-chip {cls}">{label}</span>'
    return f'<span class="badge {state.lower()}">{escape(state)}</span>{chip}'
```

with:

```python
def _chip(gate: GateDecision) -> str:
    """P2: caveated chip = anchor to #validation-panel with the Chinese-labeled
    caveat reason as an escaped tooltip; validated stays a plain span (no
    tooltip, no anchor — an anchor with an empty tooltip invites misreading)."""
    cls_label = _CHIP.get(gate.badge)
    if not cls_label:
        return ""
    cls, label = cls_label
    if gate.badge != "caveated":
        return f'<span class="val-chip {cls}">{label}</span>'
    title = escape(caveat_tooltip(gate.reason))
    return (f'<a class="val-chip {cls}" href="#validation-panel" '
            f'title="{title}">{label}</a>')


def _badge(view: FundView, gate: GateDecision | None) -> str:
    if gate is None:
        if view.signal.status != "ok":
            return f'<span class="badge no-call">{_NO_CALL}</span>'
        return f'<span class="badge {view.signal.bias.lower()}">{escape(view.signal.bias)}</span>'
    state = published_state(view.signal, gate)
    if state == _NO_CALL:
        return f'<span class="badge no-call">{_NO_CALL}</span>'
    if state == _EVAL_GATED:
        return '<span class="badge eval-gated">EVAL-GATED 🛡</span>'
    return f'<span class="badge {state.lower()}">{escape(state)}</span>{_chip(gate)}'
```

(c) In `_CSS`, directly after the line `".val-chip{font-size:11px;margin-left:6px;padding:1px 4px;border-radius:3px}"` insert:

```python
    "a.val-chip{text-decoration:none}"
```

NOTE (RD-6 judgment, encode as-is): do NOT add `color:inherit` — `a.val-chip` (specificity 0,1,1) would beat `.val-caveated{color:#bf8700}` (0,1,0) and kill the amber. The UA default link color already loses to any author rule, so only the underline needs resetting. Tests pin element/href/title only — the CSS rule is not test-pinned.

- [ ] **Step 8: Run chip tests green**

Run: `uv run pytest tests/monitor/test_render_html_eval.py -q`
Expected: all pass.

- [ ] **Step 9: Regenerate the golden report (CSS-only diff)**

Run:

```bash
uv run python -c "
from pathlib import Path
from tests.monitor import test_render_html as t
html = t.render_report((t._view(),), t._prov(), prior_signal=None, now=t._NOW, now_dt=t._NOW_DT)
Path('tests/monitor/golden/report.html').write_text(html, encoding='utf-8')
"
git diff --stat tests/monitor/golden/report.html
```

Expected: `1 file changed, 1 insertion(+), 1 deletion(-)` (the single `<style>` line). Verify the only change is the CSS rule:

```bash
git diff tests/monitor/golden/report.html | grep -c "a.val-chip{text-decoration:none}"
```

Expected output: `1`

- [ ] **Step 10: Run the render suite**

Run: `uv run pytest tests/monitor/test_render_html.py tests/monitor/test_render_html_eval.py tests/monitor/test_render_overview.py -q`
Expected: all pass (golden + byte-stable tests green again).

- [ ] **Step 11: Commit**

```bash
git add src/irc/monitor/render_overview.py src/irc/monitor/render_html.py tests/monitor/test_render_overview.py tests/monitor/test_render_html_eval.py tests/monitor/golden/report.html
git commit -m "feat(monitor): caveated chip -> #validation-panel anchor with Chinese-labeled tooltip"
```

---

### Task 4: Validation panel — anchor id + remediation hint

**Files:**
- Modify: `src/irc/monitor/eval/panel.py`
- Test: `tests/monitor/eval/test_panel.py`

**Interfaces:**
- Produces: panel `<section>` carries `id="validation-panel"` (the Task 3 anchor target). Remediation hint `<p>` rendered iff any row with `stage ∈ RUN_GLOBAL_STAGES` has status UNKNOWN or WARN; exact hint text `IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact / monitor_narrative（受 eval-live 花费闸门约束）`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/monitor/eval/test_panel.py`:

```python
# ── report v4 item 001: anchor id + remediation hint ─────────────────────────

_HINT = ("IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact / "
         "monitor_narrative（受 eval-live 花费闸门约束）")


def test_panel_section_carries_validation_panel_anchor_id():
    html = validation_panel_html(rows=(_row("monitor_signal", "PASS"),),
                                 badge_counts={}, now=_NOW)
    assert '<section class="validation-panel" id="validation-panel">' in html


def test_panel_remediation_hint_when_suite_row_unknown():
    rows = (_row("monitor_signal", "PASS"),
            _row("monitor_impact", "UNKNOWN", ("stale, 15d",)))
    html = validation_panel_html(rows=rows, badge_counts={}, now=_NOW)
    assert _HINT in html


def test_panel_remediation_hint_when_suite_row_warn():
    # Open question 10: WARN (fresh-unhealthy) is remedied by the same command.
    rows = (_row("monitor_narrative", "WARN", ("attribution_validity",)),)
    html = validation_panel_html(rows=rows, badge_counts={}, now=_NOW)
    assert _HINT in html


def test_panel_no_remediation_hint_when_suites_healthy():
    # A monitor_signal WARN is fund-specific — the hint keys on suite rows only.
    rows = (_row("monitor_signal", "WARN", ("gap 12d",)),
            _row("monitor_impact", "PASS"),
            _row("monitor_narrative", "PASS"))
    html = validation_panel_html(rows=rows, badge_counts={}, now=_NOW)
    assert _HINT not in html
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/eval/test_panel.py -q`
Expected: 3 FAIL (id + 2 hint tests); the no-hint test passes.

- [ ] **Step 3: Implement in `panel.py`**

(a) Add the import after the existing `constants` import (`gate` has no import back to `panel` — no cycle):

```python
from irc.monitor.eval.constants import STALE_EVAL_DAYS
from irc.monitor.eval.gate import RUN_GLOBAL_STAGES
from irc.monitor.eval.types import ValidationPanelRow
```

(b) Add below `_FLOW_COVER_RE`:

```python
_REMEDIATION_HINT = (
    '<p class="muted remediation">IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval '
    "monitor_impact / monitor_narrative（受 eval-live 花费闸门约束）</p>"
)


def _remediation(rows: tuple[ValidationPanelRow, ...]) -> str:
    """Hint iff any run-global LLM-suite row is UNKNOWN/WARN (open question 10:
    absent/skipped/corrupt/warn are all remedied by the same manual command)."""
    unhealthy = any(r.stage in RUN_GLOBAL_STAGES and r.status in ("UNKNOWN", "WARN")
                    for r in rows)
    return _REMEDIATION_HINT if unhealthy else ""
```

(c) In `validation_panel_html`, replace the return statement:

```python
    return (
        '<section class="validation-panel"><h2>Validation</h2>'
        f"{summary}"
        '<table class="validation"><tr><th>stage</th><th>overall</th>'
        '<th>ran_at</th></tr>'
        f"{body}</table></section>"
    )
```

with:

```python
    return (
        '<section class="validation-panel" id="validation-panel"><h2>Validation</h2>'
        f"{summary}"
        '<table class="validation"><tr><th>stage</th><th>overall</th>'
        '<th>ran_at</th></tr>'
        f"{body}</table>{_remediation(rows)}</section>"
    )
```

- [ ] **Step 4: Run tests green**

Run: `uv run pytest tests/monitor/eval/test_panel.py tests/monitor/test_eval_panel.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/eval/panel.py tests/monitor/eval/test_panel.py
git commit -m "feat(monitor): validation panel anchor id + manual eval remediation hint"
```

---

### Task 5: Run-global dedupe — the ONE 今日速览 caveat line

**Files:**
- Modify: `src/irc/monitor/render_overview.py` (`caveat_row` + private helpers; `overview_html` gains one keyword-only param)
- Modify: `src/irc/monitor/render_html.py` (`render_report` wiring — the only `overview_html` caller)
- Test: `tests/monitor/test_render_overview.py`, `tests/monitor/test_render_html_eval.py`

**Interfaces:**
- Produces: `caveat_row(panel_rows: tuple, gates: dict) -> str` — full `<div class="overview-row caveat-line">…</div>` or `""`. `overview_html(*, flips, actionable, health, caveat_row_html: str = "")` — caveat line FIRST (RD-5), counts as a row for the all-empty check (its presence suppresses 今日无变化). Ages ONLY parsed from `stale, {N}d` strings — never a clock.
- Wording (locked + RD-4): prefix `全部基金` iff caveated-badge count == len(gates), else `{N}只基金`; line absent when no suite row is WARN/UNKNOWN **or** no fund is actually caveated (CONTEXT.md: "present only when a run-global suite cause caveats funds" — a fund can be gated instead, never overstate). Cause: both-stale → `LLM质量评估过期 {a}/{b}天`; both absent/skipped → `LLM质量评估缺失`; anything else → per-suite `{中文label}：{fragment}` (`过期 {N}天` / `缺失` for absent/skipped/corrupt_ran_at / raw status), joined ` · `. Suffix ` · 周六自动刷新` always.

- [ ] **Step 1: Write the failing tests**

Append to `tests/monitor/test_render_overview.py`:

```python
def _panel_row(stage, status, reasons=()):
    from irc.monitor.eval.types import ValidationPanelRow
    return ValidationPanelRow(stage=stage, status=status,
                              ran_at="2026-06-16T09:00:00+08:00", reasons=reasons)


def _gate_d(fid, badge, reason=""):
    from irc.monitor.eval.types import GateDecision
    return GateDecision(fid, badge == "gated", (), badge, reason)


def test_caveat_row_all_funds_both_stale_locked_wording():
    from irc.monitor.render_overview import caveat_row
    rows = (_panel_row("monitor_impact", "UNKNOWN", ("stale, 15d",)),
            _panel_row("monitor_narrative", "UNKNOWN", ("stale, 16d",)))
    gates = {f"f{i}": _gate_d(f"f{i}", "caveated", "x") for i in range(10)}
    html = caveat_row(rows, gates)
    assert "全部基金 caveated：LLM质量评估过期 15/16天 · 周六自动刷新" in html
    assert html.startswith('<div class="overview-row caveat-line">')


def test_caveat_row_count_wording_when_not_all_funds_caveated():
    from irc.monitor.render_overview import caveat_row
    rows = (_panel_row("monitor_impact", "UNKNOWN", ("stale, 15d",)),
            _panel_row("monitor_narrative", "UNKNOWN", ("stale, 16d",)))
    gates = {"a": _gate_d("a", "caveated", "x"),
             "b": _gate_d("b", "caveated", "x"),
             "c": _gate_d("c", "gated", "nav_quality FAIL")}
    html = caveat_row(rows, gates)
    assert "2只基金 caveated：" in html
    assert "全部基金" not in html


def test_caveat_row_absent_when_both_suites_healthy():
    from irc.monitor.render_overview import caveat_row
    rows = (_panel_row("monitor_impact", "PASS"),
            _panel_row("monitor_narrative", "PASS"),
            _panel_row("monitor_signal", "WARN", ("gap 12d",)))  # fund-specific, not run-global
    gates = {"a": _gate_d("a", "caveated", "monitor_signal: WARN (gap 12d)")}
    assert caveat_row(rows, gates) == ""


def test_caveat_row_absent_when_no_fund_actually_caveated():
    # Run-global cause but every fund gated (FAIL wins) -> no line (never overstates).
    from irc.monitor.render_overview import caveat_row
    rows = (_panel_row("monitor_impact", "UNKNOWN", ("stale, 15d",)),
            _panel_row("monitor_narrative", "UNKNOWN", ("stale, 16d",)))
    gates = {"a": _gate_d("a", "gated", "nav_quality FAIL")}
    assert caveat_row(rows, gates) == ""


def test_caveat_row_all_absent_locked_wording_no_age():
    from irc.monitor.render_overview import caveat_row
    rows = (_panel_row("monitor_impact", "UNKNOWN", ("absent",)),
            _panel_row("monitor_narrative", "UNKNOWN", ("skipped",)))
    gates = {"a": _gate_d("a", "caveated", "x")}
    html = caveat_row(rows, gates)
    assert "全部基金 caveated：LLM质量评估缺失 · 周六自动刷新" in html


def test_caveat_row_mixed_stale_plus_absent_falls_back_to_per_suite_grammar():
    # RD-4 pinned fallback example.
    from irc.monitor.render_overview import caveat_row
    rows = (_panel_row("monitor_impact", "UNKNOWN", ("stale, 15d",)),
            _panel_row("monitor_narrative", "UNKNOWN", ("absent",)))
    gates = {"a": _gate_d("a", "caveated", "x")}
    html = caveat_row(rows, gates)
    assert "影响评分质量评估：过期 15天 · 叙事质量评估：缺失 · 周六自动刷新" in html


def test_caveat_row_single_fresh_warn_suite_uses_raw_status():
    # RD-4: fresh-unhealthy -> raw status, no invented translation.
    from irc.monitor.render_overview import caveat_row
    rows = (_panel_row("monitor_impact", "WARN", ("magnitude_band_pass",)),
            _panel_row("monitor_narrative", "PASS"))
    gates = {"a": _gate_d("a", "caveated", "x")}
    html = caveat_row(rows, gates)
    assert "影响评分质量评估：WARN · 周六自动刷新" in html


def test_overview_html_caveat_line_suppresses_quiet_line_and_renders_first():
    # RD-5: first-position row; counts as a row for the all-empty check.
    health = DataHealthCounts(dark_factor_fractions={}, gated_fund_count=0,
                              stale_eval_count=0)
    line = '<div class="overview-row caveat-line">⚠ x</div>'
    html = overview_html(flips=(), actionable=(), health=health,
                         caveat_row_html=line)
    assert "今日无变化" not in html
    assert "今日速览" in html


def test_overview_html_caveat_line_precedes_other_rows():
    fund = ActionableFund(fund_id="519069", name_cn="B基金", bias="ADD_BIAS",
                          purchase_restricted=False)
    health = DataHealthCounts(dark_factor_fractions={}, gated_fund_count=0,
                              stale_eval_count=0)
    line = '<div class="overview-row caveat-line">⚠ x</div>'
    html = overview_html(flips=(), actionable=(fund,), health=health,
                         caveat_row_html=line)
    assert html.index("caveat-line") < html.index("可操作")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_render_overview.py -q`
Expected: FAIL — `ImportError: cannot import name 'caveat_row'` and `TypeError: overview_html() got an unexpected keyword argument 'caveat_row_html'`.

- [ ] **Step 3: Implement in `render_overview.py`**

(a) Replace `overview_html` with:

```python
def overview_html(
    *, flips: tuple[BiasFlip, ...], actionable: tuple[ActionableFund, ...],
    health: DataHealthCounts, caveat_row_html: str = "",
) -> str:
    """PURE: 今日速览 strip. Caveat line FIRST (RD-5 — it sets the trust level
    for everything below) and counts as a row for the all-empty check; other
    rows dropped when empty; all-empty -> quiet line."""
    rows = "".join((caveat_row_html, _flip_row(flips), _actionable_row(actionable),
                    _health_row(health)))
    if not rows:
        return '<section class="overview"><p class="muted">今日无变化，数据健康</p></section>'
    return f'<section class="overview"><h2>今日速览</h2>{rows}</section>'
```

(b) Append at the end of the file (after the Task 3 helpers):

```python
_MISSING_SUITE_REASONS = frozenset({"absent", "skipped", "corrupt_ran_at"})


def _stale_age(reasons: tuple[str, ...]) -> int | None:
    """Age from an already-stamped `stale, {N}d` reason — NEVER re-clocked
    (open question 4: tooltip/trace/panel/overview cannot disagree)."""
    for r in reasons:
        m = _STALE_REASON_RE.search(r)
        if m:
            return int(m.group(1))
    return None


def _suite_fragment(row) -> str:
    """RD-4 fallback fragment: 过期 {N}天 (stale) / 缺失 (absent, skipped,
    corrupt_ran_at) / the raw status (fresh-unhealthy — no invented Chinese)."""
    age = _stale_age(row.reasons)
    if age is not None:
        return f"过期 {age}天"
    if any(r in _MISSING_SUITE_REASONS for r in row.reasons):
        return "缺失"
    return row.status


def _cause_text(rows: tuple) -> str:
    """Locked wordings for both-stale and both-absent/skipped; every other
    combination -> per-suite `{中文label}：{fragment}` joined ` · ` (RD-4)."""
    ages = [_stale_age(r.reasons) for r in rows]
    if len(rows) == 2 and all(a is not None for a in ages):
        return f"LLM质量评估过期 {ages[0]}/{ages[1]}天"
    if len(rows) == 2 and all(
            any(x in ("absent", "skipped") for x in r.reasons) for r in rows):
        return "LLM质量评估缺失"
    return " · ".join(
        f"{_SUITE_LABELS_CN.get(r.stage, r.stage)}：{_suite_fragment(r)}" for r in rows)


def caveat_row(panel_rows: tuple, gates: dict) -> str:
    """PURE: the ONE run-global 今日速览 caveat line (P2 dedupe, RD-4/RD-5).
    Suite causes come from the structured panel rows (stage ∈ RUN_GLOBAL_STAGES,
    status WARN/UNKNOWN); the fund count from the gate map. "" when both suites
    are healthy OR when no fund's badge is actually caveated (a fund can be
    gated instead — the line never overstates, open question 9)."""
    rows = tuple(r for r in panel_rows
                 if r.stage in RUN_GLOBAL_STAGES and r.status in ("WARN", "UNKNOWN"))
    if not rows:
        return ""
    n = sum(1 for g in gates.values() if g.badge == "caveated")
    if n == 0:
        return ""
    prefix = "全部基金" if n == len(gates) else f"{n}只基金"
    text = f"{prefix} caveated：{_cause_text(rows)} · 周六自动刷新"
    return f'<div class="overview-row caveat-line">⚠ {escape(text)}</div>'
```

- [ ] **Step 4: Run overview tests green**

Run: `uv run pytest tests/monitor/test_render_overview.py -q`
Expected: all pass.

- [ ] **Step 5: Write the failing e2e once-only test**

Append to `tests/monitor/test_render_html_eval.py`:

```python
def test_run_global_caveat_renders_once_in_overview_not_per_card():
    # P2 dedupe: ONE overview line, never repeated per card; trace-side reason
    # stays per-fund and complete regardless (criterion 9).
    from irc.monitor.render_html import render_report
    from irc.monitor.eval.types import ValidationPanelRow
    reason = ("monitor_impact: UNKNOWN (stale, 15d); "
              "monitor_narrative: UNKNOWN (stale, 16d)")
    rows = (ValidationPanelRow("monitor_impact", "UNKNOWN", "—", ("stale, 15d",)),
            ValidationPanelRow("monitor_narrative", "UNKNOWN", "—", ("stale, 16d",)))
    prov = Provenance("1", "1", "1", "")
    html = render_report((_view(),), prov, prior_signal=None, now=_NOW, now_dt=_NOW_DT,
                         gates={"008986": _gate(badge="caveated", reason=reason)},
                         panel_rows=rows)
    assert html.count("全部基金 caveated：LLM质量评估过期 15/16天 · 周六自动刷新") == 1
```

- [ ] **Step 6: Run to verify failure**

Run: `uv run pytest tests/monitor/test_render_html_eval.py::test_run_global_caveat_renders_once_in_overview_not_per_card -q`
Expected: FAIL (`render_report` does not compute the line yet — count is 0).

- [ ] **Step 7: Wire `render_report`**

In `src/irc/monitor/render_html.py`:

(a) Extend the `render_overview` import to:

```python
from irc.monitor.render_overview import (
    caveat_row, caveat_tooltip, compute_actionable, compute_data_health,
    compute_flips, overview_html,
)
```

(b) In `render_report`, replace:

```python
    overview = overview_html(flips=flips, actionable=actionable, health=health)
```

with:

```python
    overview = overview_html(flips=flips, actionable=actionable, health=health,
                             caveat_row_html=caveat_row(panel_rows, g))
```

- [ ] **Step 8: Run the render suites green**

Run: `uv run pytest tests/monitor/test_render_html_eval.py tests/monitor/test_render_html.py tests/monitor/test_render_overview.py -q`
Expected: all pass. (The golden render passes `gates=None` → `g={}` → `caveat_row((), {})` → `""` — golden bytes unchanged from Task 3's regeneration.)

- [ ] **Step 9: Commit**

```bash
git add src/irc/monitor/render_overview.py src/irc/monitor/render_html.py tests/monitor/test_render_overview.py tests/monitor/test_render_html_eval.py
git commit -m "feat(monitor): ONE run-global caveat line, first row of 今日速览 (RD-4/RD-5 grammar)"
```

---

### Task 6: Card-level 为何有保留 line (fund-specific causes only)

**Files:**
- Modify: `src/irc/monitor/render_html.py` (`_card_caveat` helper + `_card` wiring + import)
- Test: `tests/monitor/test_render_html_eval.py`

**Interfaces:**
- Consumes: `fund_specific_segments` (Task 3). Renders ONLY for `badge == "caveated"` — a gated fund's FAIL reason has no stage-prefixed segments and must never produce a 为何有保留 line (judgment call: the FAIL-branch reason format is prefix-free, so an unguarded segment filter would misclassify it as fund-specific; `有保留` is the caveated vocabulary).

- [ ] **Step 1: Write the failing tests**

Append to `tests/monitor/test_render_html_eval.py`:

```python
# ── report v4 item 001: card-level 为何有保留 (fund-specific causes only) ────


def test_card_caveat_line_for_fund_specific_cause():
    html = _render(_view(), _gate(badge="caveated",
                                  reason="monitor_signal: WARN (gap 12d)"))
    assert "为何有保留：monitor_signal: WARN (gap 12d)" in html


def test_no_card_caveat_line_for_run_global_only_cause():
    reason = ("monitor_impact: UNKNOWN (stale, 15d); "
              "monitor_narrative: UNKNOWN (stale, 16d)")
    html = _render(_view(), _gate(badge="caveated", reason=reason))
    assert "为何有保留" not in html


def test_card_caveat_line_mixed_shows_only_fund_specific_segment():
    reason = ("monitor_signal: WARN (gap 12d); "
              "monitor_impact: UNKNOWN (stale, 15d)")
    html = _render(_view(), _gate(badge="caveated", reason=reason))
    assert "为何有保留：monitor_signal: WARN (gap 12d)</p>" in html


def test_no_card_caveat_line_when_validated():
    html = _render(_view(), _gate(badge="validated"))
    assert "为何有保留" not in html


def test_no_card_caveat_line_when_gated():
    # FAIL-branch reasons are prefix-free; the guard is badge == "caveated".
    html = _render(_view(), _gate(badge="gated", suppressed=True,
                                  reason="nav_quality FAIL"))
    assert "为何有保留" not in html
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/test_render_html_eval.py -q`
Expected: `test_card_caveat_line_for_fund_specific_cause` and `test_card_caveat_line_mixed_shows_only_fund_specific_segment` FAIL; the three negative tests pass.

- [ ] **Step 3: Implement in `render_html.py`**

(a) Extend the `render_overview` import to its final form:

```python
from irc.monitor.render_overview import (
    caveat_row, caveat_tooltip, compute_actionable, compute_data_health,
    compute_flips, fund_specific_segments, overview_html,
)
```

(b) Add above `_card`:

```python
def _card_caveat(gate: GateDecision | None) -> str:
    """P2: 为何有保留 — fund-specific caveat segments only. Run-global causes
    dedupe to the ONE overview line; gated funds (prefix-free FAIL reasons)
    and validated funds render nothing."""
    if gate is None or gate.badge != "caveated":
        return ""
    segments = fund_specific_segments(gate.reason)
    if not segments:
        return ""
    return f'<p class="card-caveat muted">为何有保留：{escape("; ".join(segments))}</p>'
```

(c) In `_card`, insert the line directly after the `<h2>` element. Replace:

```python
        f"<h2>{escape(view.name_cn)} ({view.fund_id}) {_badge(view, gate)}</h2>"
        f"{decision_line_html(view.market_view, purchase_tag=view.purchase_tag)}"
```

with:

```python
        f"<h2>{escape(view.name_cn)} ({view.fund_id}) {_badge(view, gate)}</h2>"
        f"{_card_caveat(gate)}"
        f"{decision_line_html(view.market_view, purchase_tag=view.purchase_tag)}"
```

- [ ] **Step 4: Run tests green**

Run: `uv run pytest tests/monitor/test_render_html_eval.py tests/monitor/test_render_html.py -q`
Expected: all pass (golden unchanged — its render has `gate=None`).

- [ ] **Step 5: Commit**

```bash
git add src/irc/monitor/render_html.py tests/monitor/test_render_html_eval.py
git commit -m "feat(monitor): card-level 为何有保留 line for fund-specific caveat causes"
```

---

### Task 7: Schema bump 6→7 + `SCHEMA_VERSION` unification (the ONE bump)

**Files:**
- Modify: `src/irc/monitor/eval/trace.py:13,201`
- Modify: `src/irc/commands/monitor_cmd.py:58,485`
- Test: `tests/monitor/eval/test_trace.py`, `tests/monitor/test_acceptance_eval.py`, `tests/commands/test_monitor_cmd_trace.py` (per-file ONLY)

**Interfaces:**
- Produces: public `SCHEMA_VERSION = "7"` exported from `irc.monitor.eval.trace` (rename of module-private `_SCHEMA_VERSION` — RD-1); `monitor_cmd`'s `Provenance` consumes it, so report header and trace can never drift. Trace shape otherwise unchanged. Items 002/004 land their fields under `"7"` and must NOT bump again.

- [ ] **Step 1: Update the pins + add the two new tests (red)**

(a) `tests/monitor/eval/test_trace.py` — replace:

```python
def test_schema_version_is_6():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="3", run_date="2026-06-21")
    assert t["schema_version"] == "6"
```

with:

```python
def test_schema_version_is_7():
    t = build_eval_trace(((_fund(), _good_view(), _stub_gate(_good_view()), _bundle()),),
                         engine_version="3", run_date="2026-06-21")
    assert t["schema_version"] == "7"


def test_caveated_gate_reason_lands_in_trace_non_empty():
    # Criterion 10: schema 7's only content change — gate.reason stops being
    # empty for caveated funds; shape is untouched.
    from irc.monitor.eval.types import GateDecision
    reason = ("monitor_impact: UNKNOWN (stale, 15d); "
              "monitor_narrative: UNKNOWN (stale, 16d)")
    gate = GateDecision("008986", False, (), "caveated", reason)
    t = build_eval_trace(((_fund(), _good_view(), gate, _bundle()),),
                         engine_version="4", run_date="2026-07-03")
    entry = t["funds"]["008986"]
    assert entry["validation_badge"] == "caveated"
    assert entry["gate"]["reason"] == reason
```

(b) `tests/monitor/test_acceptance_eval.py` — in `test_trace_carries_missing_trading_days_from_calendar` change:

```python
    assert trace["schema_version"] == "6"
```

to:

```python
    assert trace["schema_version"] == "7"
```

and append to the file:

```python
def test_report_header_schema_cannot_drift_from_trace(monkeypatch, tmp_path: Path):
    """RD-1: monitor_cmd's Provenance consumes trace.SCHEMA_VERSION — the report
    header and eval_trace.json move together by construction."""
    from irc.monitor.eval.trace import SCHEMA_VERSION
    funds = [_fund("008986")]
    _patch(monkeypatch, funds, [_stale_view("008986")])
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    out = tmp_path / "outputs" / "2026-06-16" / "monitor"
    html = (out / "report.html").read_text(encoding="utf-8")
    trace = json.loads((out / "eval_trace.json").read_text(encoding="utf-8"))
    assert f"schema {SCHEMA_VERSION}" in html
    assert trace["schema_version"] == SCHEMA_VERSION == "7"
```

(c) `tests/commands/test_monitor_cmd_trace.py` — replace:

```python
def test_eval_trace_schema_version_is_6():
    from irc.monitor.eval.trace import build_eval_trace
    trace = build_eval_trace((), engine_version="3", run_date="2026-07-02")
    assert trace["schema_version"] == "6"
```

with:

```python
def test_eval_trace_schema_version_is_7():
    from irc.monitor.eval.trace import build_eval_trace
    trace = build_eval_trace((), engine_version="3", run_date="2026-07-02")
    assert trace["schema_version"] == "7"
```

Do NOT touch `test_old_trace_without_macro_narrative_field_still_loads` (the `"5"` back-compat fixture, RD-1).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/monitor/eval/test_trace.py tests/monitor/test_acceptance_eval.py -q`
Expected: FAIL — schema is still `"6"`, `SCHEMA_VERSION` not importable.

- [ ] **Step 3: Bump + unify**

(a) `src/irc/monitor/eval/trace.py` — replace:

```python
_SCHEMA_VERSION = "6"
```

with:

```python
# Public: also consumed by monitor_cmd's Provenance so the report header can
# never drift from the trace (RD-1). Bumped 6->7 by report v4 item 001 (shape
# unchanged — gate.reason just stops being empty); items 002/004 land their
# fields under "7" WITHOUT bumping again.
SCHEMA_VERSION = "7"
```

and in `build_eval_trace` replace:

```python
        "schema_version": _SCHEMA_VERSION,
```

with:

```python
        "schema_version": SCHEMA_VERSION,
```

(b) `src/irc/commands/monitor_cmd.py` — replace the import line:

```python
from irc.monitor.eval.trace import build_eval_trace
```

with:

```python
from irc.monitor.eval.trace import SCHEMA_VERSION, build_eval_trace
```

and in `_write_outputs` replace:

```python
    prov = Provenance(_ENGINE_VERSION, "2", "6", "")
```

with:

```python
    prov = Provenance(_ENGINE_VERSION, "2", SCHEMA_VERSION, "")
```

- [ ] **Step 4: Run the pin files green (per-file for tests/commands!)**

```bash
uv run pytest tests/monitor/eval/test_trace.py -q
uv run pytest tests/monitor/test_acceptance_eval.py -q
uv run pytest tests/commands/test_monitor_cmd_trace.py -q
```

Expected: all pass, each invocation separately.

- [ ] **Step 5: Verify no stray `_SCHEMA_VERSION`/`"6"` schema references remain**

Run: `grep -rn "_SCHEMA_VERSION" src/irc/monitor/ tests/monitor/ | grep -v __pycache__`
Expected: no output.

Run: `grep -rn 'Provenance(_ENGINE_VERSION' src/irc/commands/monitor_cmd.py`
Expected: exactly one line, containing `SCHEMA_VERSION` (no literal).

- [ ] **Step 6: Commit**

```bash
git add src/irc/monitor/eval/trace.py src/irc/commands/monitor_cmd.py tests/monitor/eval/test_trace.py tests/monitor/test_acceptance_eval.py tests/commands/test_monitor_cmd_trace.py
git commit -m "feat(monitor): eval-trace schema 6->7; unify SCHEMA_VERSION into Provenance (RD-1)"
```

---

### Task 8: Weekly wrapper — best-effort live LLM eval refresh (OD-3)

**Files:**
- Modify: `ops/launchd/run-weekly.sh`
- Test: `tests/ops/test_launchd_weekly.py` (existing pattern: `bash -n` + text pins — extend it; no bats)

**Interfaces:**
- Produces: two `run_with_watchdog "${IRC_WEEKLY_EVAL_TIMEOUT:-900}" env IRC_RUN_LIVE_LLM_EVAL=1 "$UV_BIN" run irc eval monitor_{impact,narrative}` invocations AFTER `notify-status`, BEFORE `exit "$rc"`, each `|| echo`-guarded. The `env` prefix is LOAD-BEARING (RD-3): `run_with_watchdog` executes `"$@" &` (lib-run.sh:58) — a bare `VAR=1` word from `"$@"` is exec'd as a command name (rc 127, masked by the guard) because bash assignment parsing precedes word expansion. Wrapper rc stays the pipeline's `rc`. Early exits (sentinel line ~38, lock ~48) precede the append point, so criterion 13 holds structurally; `acquire_lock`'s EXIT trap keeps `.weekly.lock` held through the evals (correct — no overlap with a manual weekly run's paid eval calls). Spend gate untouched (`eval_cmd._run_live_gated`, no code change).

- [ ] **Step 1: Write the failing tests**

Append to `tests/ops/test_launchd_weekly.py`:

```python
def test_weekly_wrapper_appends_best_effort_live_llm_eval_refresh() -> None:
    """OD-3 / report v4 item 001: two live eval runs, each watchdog-bounded and
    individually || echo-guarded; the wrapper's exit code stays the pipeline rc.
    The `env` prefix is LOAD-BEARING (RD-3): run_with_watchdog execs "$@" — a
    bare IRC_RUN_LIVE_LLM_EVAL=1 word would be exec'd as a command NAME
    (rc 127, silently masked by the best-effort guard) because bash parses
    assignments before word expansion. Pin the exact env form."""
    text = _wrapper()
    assert text.count(
        'run_with_watchdog "${IRC_WEEKLY_EVAL_TIMEOUT:-900}" env IRC_RUN_LIVE_LLM_EVAL=1'
    ) == 2
    assert "irc eval monitor_impact" in text
    assert "irc eval monitor_narrative" in text


def test_weekly_eval_refresh_after_notify_and_never_changes_wrapper_rc() -> None:
    """Placement (open question 6): after notify-status (a hung eval can never
    delay paging), before exit "$rc" (eval outcomes never touch the rc). The
    sentinel/lock early-exits precede the append point, so a skipped day skips
    the evals too (criterion 13)."""
    text = _wrapper()
    notify_pos = text.index("notify-status --run-kind weekly")
    impact_pos = text.index("irc eval monitor_impact")
    narrative_pos = text.index("irc eval monitor_narrative")
    exit_pos = text.rindex('exit "$rc"')
    assert notify_pos < impact_pos < narrative_pos < exit_pos
    assert text.rstrip().endswith('exit "$rc"')
    assert text.index('SENTINEL=') < impact_pos
    assert text.index('acquire_lock "outputs/_logs/.weekly.lock"') < impact_pos
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/ops/test_launchd_weekly.py -q`
Expected: the 2 new tests FAIL (`ValueError: substring not found` / count 0); existing tests pass.

- [ ] **Step 3: Implement in `run-weekly.sh`**

Replace the final two lines of `ops/launchd/run-weekly.sh`:

```bash
"$UV_BIN" run irc notify-status --run-kind weekly --last-exit-code "$rc" \
  || echo "[$TODAY] notify-status failed (rc=$?) — weekly rc was $rc (see above)"
exit "$rc"
```

with:

```bash
"$UV_BIN" run irc notify-status --run-kind weekly --last-exit-code "$rc" \
  || echo "[$TODAY] notify-status failed (rc=$?) — weekly rc was $rc (see above)"

# Weekly LLM-suite refresh (OD-3, report v4 item 001): keep monitor_impact /
# monitor_narrative fresh under STALE_AFTER_DAYS=14 so daily briefs stop
# caveating on stale suites. Best-effort by construction: runs AFTER notify (a
# hung eval can never delay paging), each bounded by its own watchdog, and
# `|| echo` keeps any failure (rc=3 env-skip, rc=5 spend-gate, rc=124 timeout)
# from aborting under `set -e`. The wrapper exits with the PIPELINE's rc.
# The `env` prefix is LOAD-BEARING: run_with_watchdog execs "$@" — a bare
# IRC_RUN_LIVE_LLM_EVAL=1 word would be exec'd as a command NAME (rc 127),
# because bash parses assignments before word expansion (RD-3).
run_with_watchdog "${IRC_WEEKLY_EVAL_TIMEOUT:-900}" env IRC_RUN_LIVE_LLM_EVAL=1 \
  "$UV_BIN" run irc eval monitor_impact \
  || echo "[$TODAY] weekly monitor_impact eval refresh failed (rc=$?) — best-effort, not paging"
run_with_watchdog "${IRC_WEEKLY_EVAL_TIMEOUT:-900}" env IRC_RUN_LIVE_LLM_EVAL=1 \
  "$UV_BIN" run irc eval monitor_narrative \
  || echo "[$TODAY] weekly monitor_narrative eval refresh failed (rc=$?) — best-effort, not paging"
exit "$rc"
```

- [ ] **Step 4: Verify syntax + tests green**

```bash
bash -n ops/launchd/run-weekly.sh
uv run pytest tests/ops/ -q
```

Expected: `bash -n` silent (exit 0); all `tests/ops/` pass (including the pre-existing `test_weekly_wrapper_parses` bash -n test).

- [ ] **Step 5: Commit**

```bash
git add ops/launchd/run-weekly.sh tests/ops/test_launchd_weekly.py
git commit -m "feat(ops): weekly wrapper best-effort live LLM eval refresh (env prefix, RD-3)"
```

---

### Task 9: Docs + CHANGELOG + post-merge ops note

**Files:**
- Modify: `docs/monitor/README.md`, `ops/launchd/README.md`, `evals/README.md`, `docs/diagrams/monitor-workflow.html`, `CHANGELOG.md`
- Create: `docs/2026-07-03-monitor-v4-explainability/items/001-postmerge-ops.md`

No test cycle (docs-only); each edit is exact old→new text. `VERSION` file untouched.

- [ ] **Step 1: `docs/monitor/README.md` — maintenance row (line ~194)**

Replace:

```markdown
| Monthly-ish (paid, manual) | Live LLM eval suites — the only check on MiniMax output *quality*; without a fresh report the daily gate fails open to ⚠ caveated | `IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact` (same for `monitor_narrative`) |
```

with:

```markdown
| Weekly, automated (Saturday wrapper, best-effort) | Live LLM eval suites — the only check on MiniMax output *quality*; without a fresh report the daily gate fails open to ⚠ caveated (the chip tooltip + 今日速览 line now name the stale suite and its age). `run-weekly.sh` refreshes both suites after notify (900 s watchdog each via `IRC_WEEKLY_EVAL_TIMEOUT`; failures never page; eval-live spend gate applies). Manual remediation / fallback — e.g. after a same-day manual run preempted the Saturday fire: | `IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact` (same for `monitor_narrative`) |
```

- [ ] **Step 2: `docs/monitor/README.md` — Weekly process section (~line 148)**

After the paragraph ending `set it in `.env` for research-backed weekly runs.` insert a new paragraph:

```markdown
After `notify-status`, the wrapper best-effort refreshes the two live LLM eval
suites (`env IRC_RUN_LIVE_LLM_EVAL=1 … irc eval monitor_impact` /
`monitor_narrative`, each under its own `IRC_WEEKLY_EVAL_TIMEOUT` watchdog,
default 900 s) so the daily brief's suite healths stay fresh under
`STALE_AFTER_DAYS = 14`. Eval failures/timeouts are logged breadcrumbs — they
never change the weekly exit code and never page. Edge case: a same-day manual
`irc run` (idempotency-sentinel skip) also skips that Saturday's eval refresh —
the daily report degrades to the stale caveat chip + validation-panel hint;
run the manual command from the maintenance table below to clear it.
```

- [ ] **Step 3: `ops/launchd/README.md` — env-var table + weekly paragraph (~line 68)**

(a) After the table row:

```markdown
| `run-weekly.sh` | `IRC_WEEKLY_TIMEOUT` (7200s / 2h) | `rc=124` → `notify-status --run-kind weekly` pages **"timeout"** |
```

add:

```markdown
| `run-weekly.sh` — eval-refresh step | `IRC_WEEKLY_EVAL_TIMEOUT` (900s per suite) | `rc=124` **logged, does NOT page** (best-effort; runs after notify; wrapper rc unchanged) |
```

(b) In the `**`com.irc.weekly`**` paragraph, after `Its per-run logs are `outputs/_logs/run-weekly.<ts>.log`.` append:

```markdown
After notify, the wrapper best-effort refreshes the two live LLM eval suites
(`env IRC_RUN_LIVE_LLM_EVAL=1 "$UV_BIN" run irc eval monitor_impact` /
`monitor_narrative`) under per-run `IRC_WEEKLY_EVAL_TIMEOUT` watchdogs —
failures/timeouts are logged, never paged, and never alter the wrapper's exit
code (OD-3, report v4 item 001; the `env` prefix is required because
`run_with_watchdog` execs its argv — a bare `VAR=1` word would be run as a
command name).
```

- [ ] **Step 4: `evals/README.md:94` — stale schema reference**

Replace:

```markdown
- **`outputs/<date>/monitor/eval_trace.json`** — `schema_version "5"`, per-fund projection:
```

with:

```markdown
- **`outputs/<date>/monitor/eval_trace.json`** — `schema_version "7"`, per-fund projection:
```

- [ ] **Step 5: `docs/diagrams/monitor-workflow.html` — 5 exact line edits**

(a) Replace `eval_trace schema "6" · engine "4"` with `eval_trace schema "7" · engine "4"` (line ~301).

(b) Replace `WARN/stale → ⚠ caveated · inline monitor_forward re-score` with `WARN/stale → ⚠ caveated（带原因） · inline monitor_forward re-score` (line ~300).

(c) Replace `schema "6" · eval spine input` with `schema "7" · eval spine input` (line ~335).

(d) Replace `forward (weekly) · impact/narrative (live-gated, paid)` with `forward (weekly) · impact/narrative (Sat wrapper auto, paid)` (line ~375 — the weekly wrapper now fires them; string kept short to fit the 220px box).

(e) Replace `<li>• 今日速览: 偏向变化 · 可操作 · 数据健康 (all gate-respecting)</li>` with `<li>• 今日速览: run-global caveat 行（首行） · 偏向变化 · 可操作 · 数据健康 (all gate-respecting)</li>` (line ~430).

(f) In the footer, replace `report v3 · engine "4" · eval schema "6"` with `report v3 · engine "4" · eval schema "7"` (line ~438).

Verify: `grep -c 'schema "6"' docs/diagrams/monitor-workflow.html` → expected output `0`.

- [ ] **Step 6: CHANGELOG entry**

In `CHANGELOG.md`, directly under `## [Unreleased]` (above the existing `### Added — monitor report: divergence caveats…` block), insert:

```markdown
### Added — monitor report: self-explanatory caveats + weekly LLM-suite auto-refresh (2026-07-03)

- **⚠ caveated is now self-explanatory and self-healing** (report-v4
  explainability WS-1 / P1+P2+OD-3, item 001). `resolve_health` age-stamps the
  stale reason (`("stale, 15d",)`); `apply_eval_gate`'s caveated branch
  populates `GateDecision.reason` (`monitor_impact: UNKNOWN (stale, 15d); …` —
  FAIL branch unchanged); the caveated chip becomes an anchor to the Validation
  panel with a Chinese-labeled tooltip; run-global LLM-suite causes dedupe to
  ONE first-position 今日速览 line
  (`全部基金 caveated：LLM质量评估过期 15/16天 · 周六自动刷新`); fund-specific
  (`monitor_signal`) causes render per-card as 为何有保留; the Validation panel
  gains its anchor id + a manual-refresh remediation hint. New explicit
  `RUN_GLOBAL_STAGES` literal in `eval/gate.py` (equality-guarded vs `M1 − M0`).
  `ops/launchd/run-weekly.sh` appends two best-effort watchdog-bounded live
  eval runs (`env IRC_RUN_LIVE_LLM_EVAL=1 …`, `IRC_WEEKLY_EVAL_TIMEOUT` default
  900 s, after notify — never affects the wrapper rc or paging; eval-live spend
  gate unchanged) so a weekly cadence keeps both suites fresh under
  `STALE_AFTER_DAYS = 14`. eval-trace `schema_version` "6" → **"7"** (shape
  unchanged — `gate.reason` just stops being empty); the constant is unified
  (`trace.SCHEMA_VERSION` now feeds the report-header `Provenance`, RD-1). No
  `_ENGINE_VERSION` change; forward ledger untouched (rows carry no
  schema_version; `gate_reason` is write-only — RD-8).
```

- [ ] **Step 7: Create the post-merge ops note (NOT code)**

Create `docs/2026-07-03-monitor-v4-explainability/items/001-postmerge-ops.md`:

```markdown
# Item 001 — post-merge ops (manual, after roll-up merge to main)

1. **Reinstall the launchd agents** so the templated `run-weekly.sh` picks up
   the eval-refresh step: `bash ops/launchd/install.sh`. Verify the installed
   wrapper contains `IRC_WEEKLY_EVAL_TIMEOUT` and `launchctl list | grep
   com.irc` shows all agents loaded.
2. **One manual live eval run at rollout** to clear the current stale caveats
   immediately (the next Saturday fire would otherwise be the first refresh):
   `IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact` then
   `IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_narrative` (eval-live spend
   gate applies).
3. Next `uv run irc monitor` brief: suite-caused chips should flip to
   ✓ validated; any remaining 为何有保留 lines are genuinely fund-specific.
```

- [ ] **Step 8: Commit**

```bash
git add docs/monitor/README.md ops/launchd/README.md evals/README.md docs/diagrams/monitor-workflow.html CHANGELOG.md docs/2026-07-03-monitor-v4-explainability/items/001-postmerge-ops.md
git commit -m "docs(monitor): weekly eval auto-refresh + caveat surfaces; schema refs 6->7; CHANGELOG"
```

---

### Task 10: Full verification sweep

**Files:** none created/modified (fix-forward only if a step fails).

- [ ] **Step 1: Lint**

Run: `uv run ruff check src tests`
Expected: `All checks passed!` (line-length 100 — if any new line exceeds it, wrap and re-commit as `style: wrap long lines`).

- [ ] **Step 2: Monitor suites (fast)**

Run: `uv run pytest tests/monitor/ -q`
Expected: all pass, 0 failures (includes `tests/monitor/eval/`).

- [ ] **Step 3: Ops suite**

Run: `uv run pytest tests/ops/ -q`
Expected: all pass.

- [ ] **Step 4: Touched commands tests — PER FILE ONLY (whole dir hangs)**

```bash
uv run pytest tests/commands/test_monitor_cmd_trace.py -q
uv run pytest tests/commands/test_monitor_cmd.py -q
uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -q
uv run pytest tests/commands/test_monitor_cmd_forward_eval.py -q
```

Expected: each passes independently.

- [ ] **Step 5: Invariant guards (criterion 11)**

```bash
git diff autodev/monitor-v4-explainability-feature -- src/irc/commands/monitor_cmd.py | grep '^[-+]_ENGINE_VERSION' ; echo "engine-check rc=$?"
git diff autodev/monitor-v4-explainability-feature -- src/irc/monitor/eval/forward_log.py | head -1
grep -rn '"6"' src/irc/monitor/eval/trace.py src/irc/commands/monitor_cmd.py | grep -i schema
```

Expected: first command prints nothing before `engine-check rc=1` (no `_ENGINE_VERSION` line changed); second prints nothing (forward_log untouched); third prints nothing.

- [ ] **Step 6: CONTEXT.md consistency check (RD-8 doc lock)**

```bash
grep -n "Caveat reason" CONTEXT.md
grep -n "周六自动刷新" CONTEXT.md
```

Expected: the *Caveat reason* glossary entry and the 今日速览 fourth-row wording exist (added at grill time) and match the as-built format (`"{stage}: {status} ({reasons, comma-joined})"`, `stale, {N}d`, `RUN_GLOBAL_STAGES`, first-position line, 为何有保留). If any wording diverges from what was built, amend CONTEXT.md in this commit; otherwise NO edit.

- [ ] **Step 7: Final commit (only if Steps 1–6 produced fixes)**

```bash
git status --short
```

Expected: clean tree. If fixes were needed: `git add -A && git commit -m "fix: verification-sweep fixes for item 001"`.

---

## Self-review notes (spec → task map)

| Spec criterion | Task |
|---|---|
| 1 (age-stamp) | 1 |
| 2 (reason assembly + all badge branches) | 2 |
| 3 (RUN_GLOBAL_STAGES literal + guard) | 2 |
| 4 (chip anchor/tooltip + CSS, RD-6) | 3 |
| 5 (panel id) | 4 |
| 6 (overview line, RD-4 grammar, RD-5 placement) | 5 |
| 7 (card 为何有保留) | 6 |
| 8 (remediation hint) | 4 |
| 9 (no-hover reachability + non-empty trace reason e2e) | 2 (gate-flip e2e), 5 (once-only e2e), 7 (trace tests) |
| 10 (schema "7" + constant unification + pins) | 7 |
| 11 (no engine bump, ledger untouched) | 7, verified in 10 |
| 12 (wrapper env-prefixed watchdog evals + pins) | 8 |
| 13 (early-exit skip, manual-preempt documented) | 8 (structural pins), 9 (ops-manual doc) |
| 14 (docs: README rows, diagram, ops README table, evals README, post-merge note, CONTEXT consistency) | 9, 10 |
| 15 (CHANGELOG, no VERSION bump) | 9 |
| 16 (ruff + suites green) | 10 |

Judgment calls encoded above (all grounded in the spec/grill): CSS rule is `a.val-chip{text-decoration:none}` without `color:inherit` (specificity would kill the amber; RD-6 leaves the exact rule open, tests don't pin it); the overview line requires ≥1 actually-caveated fund (CONTEXT.md wording "present only when a run-global suite cause caveats funds"; never overstates per open question 9); the card line is guarded on `badge == "caveated"` (gated FAIL reasons are prefix-free and would otherwise misclassify as fund-specific); both locked overview wordings apply only when BOTH suites are unhealthy (RD-4 routes every other combination to the fallback grammar, corrupt_ran_at included).
