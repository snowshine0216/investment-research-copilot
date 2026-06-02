# Item 004 — Suppress action-triad / triggers on `insufficient` narrative rows (H3 discipline)

**Run:** `narrative-coverage-markdown` · **Handoff step:** #5 ("Related — lower priority")
**Primary file:** `src/irc/narrative/report.py` (`render_report_md`)
**Supporting edit:** `src/irc/narrative/report_appendix.py` (one new pure helper, to keep `report.py` < 200 lines)
**Pattern to mirror:** `src/irc/opportunity/failure_renderer.py::render_failure_section` (the H3 gapped-row
"read only the gap-facts, never the conclusions" discipline) and CONTEXT.md
**"H3 universal gapped-row invariant"**.
**Read-only references:** `src/irc/narrative/risk.py::derive_position_risk_level` (the `evidence_gaps →
insufficient` rule — NOT modified), `src/irc/narrative/analyze.py::error_report` /
`_report_from_card` (the two ways an `insufficient` `NarrativeFundReport` is built), `src/irc/narrative/schemas.py`
(`NarrativeFundReport` field set), ADR 0004 (renderer determinism), ADR 0001 (citation id format).

## Goal

Insufficient/gapped narrative rows in the `.md` still render the action triad `机会 / dca / 风险`
(e.g. `small_watch ｜ slow_dca ｜ none`) plus falsification/trim triggers and a review cadence. These
are **neutral defaults from the unconditioned card path, not earned conclusions** — `position_risk_level
== "insufficient"` means evidence is not cached (`risk.py:60`: `evidence_gaps` non-empty), so the row
has, by the project's own rule, *not earned a verdict*. A reader skimming `robots_report.md` (8/8
insufficient) currently sees 8 funds each appearing to suggest `slow_dca`.

This contradicts the spirit of the **H3 universal gapped-row invariant** (CONTEXT.md): in the
opportunity/discipline surface, gapped rows are routed away from the conclusion outputs and the failure
section reads **only 4 fields** (`instrument_id`, `name_cn`, `evidence_gaps`, `fetch_types_attempted`)
and *never* `opportunity_state` / `dca` / `risk` / `thesis_state` "because gapped rows have not earned
conclusions. The renderer's signature is the enforcement mechanism."

The narrative report is a **single-file surface** (no cross-file row partition), so the H3 analog here is
**display discipline**: on `position_risk_level == "insufficient"` rows, the `.md` SUPPRESSES the
unearned action triad + triggers + review cadence and renders an **"insufficient — refresh evidence"**
line instead, while KEEPING the honest gap-facts and diagnostics so the operator knows *what to refresh*.
The `.json` stays the full source of truth (item 003 AC8). No scorer, gate, risk rule, or invariant changes.

## Approach (recommended)

**A — early branch inside `render_report_md`'s per-fund loop; one new pure helper in `report_appendix.py`.**

After emitting the always-safe identity / risk / sub-state / drivers lines (the KEEP set), branch on
`r.position_risk_level == "insufficient"`:

- **sufficient row** (`!= "insufficient"`): emit today's output verbatim — the `机会 / dca / 风险`
  triad line, `复核节奏 / review_cadence`, `证伪触发`, `减仓触发`, then evidence / appendix / footnotes.
- **insufficient row**: SKIP the triad, the cadence, and both trigger lines; instead emit ONE
  `_insufficient_refresh_line(r, narrative)` line; then still emit whatever evidence / appendix /
  footnotes exist (partial evidence helps the operator refresh; it is never presented as a conclusion).

`report.py` is at 188 lines, so the helper lands in `report_appendix.py` (item 003 already split that
file for the budget). The renderer stays one block builder with a single early branch.

Rejected alternatives:
- **B — two separate block builders (`_sufficient_block` / `_insufficient_block`).** The blocks share
  ~70% of their lines (identity, risk, sub-states, drivers, evidence/appendix/footnotes); two builders
  duplicate that and invite drift. Rejected.
- **C — keep the triad line but blank the values (`机会 / dca / 风险: — ｜ — ｜ —`).** Still presents the
  *shape* of a recommendation (a "风险" column the skimmer reads as a verdict); doesn't honor H3's
  "expose only the gap-facts". Rejected.

## SUPPRESS vs KEEP field set (grounded in H3)

H3's failure renderer reads only `{instrument_id, name_cn, evidence_gaps, fetch_types_attempted}` and
explicitly forbids `{opportunity_state, dca, risk, note_cn, valuation_state, heat_state, thesis_state,
product_quality_state, thesis_evidence, constituent_analyses}` *as published conclusions*. The
narrative report has no `fetch_types_attempted`; its gap-fact analogs are `position_risk_level`,
`risk_rationale`, `risk_drivers`, `evidence_gaps`. The load-bearing distinction H3 enforces is
**conclusion (forward recommendation) vs fact (gap statement)** — applied to this surface:

| Field | Decision | Why |
|---|---|---|
| `opportunity_state` (机会) | **SUPPRESS** | Forward recommendation; H3-forbidden conclusion. |
| `dca_action` | **SUPPRESS** | Forward recommendation; the handoff's exact complaint ("8 funds suggesting `slow_dca`"). |
| `risk_action` | **SUPPRESS** | Forward recommendation; H3-forbidden conclusion. |
| `falsification_triggers` | **SUPPRESS** | Forward conditions on an unearned thesis. |
| `trim_triggers` | **SUPPRESS** | Forward conditions on an unearned position. |
| `review_cadence` | **SUPPRESS** | A forward action cadence (a recommendation), not a gap-fact. |
| `instrument_id`, `name_cn` | **KEEP** | H3 identity fields. |
| `position_risk_level` (=`insufficient`) | **KEEP** | The gap statement itself. |
| `risk_rationale`, `risk_drivers` | **KEEP** | Honest "why risk cannot be assessed" — narrative analog of H3 `evidence_gaps`. |
| `evidence_gaps` | **KEEP** | Surfaced in the new refresh line (H3's primary field). |
| sub-states (估值/热度/逻辑/质量) | **KEEP** | Diagnostic gap-facts (e.g. `逻辑=evidence_insufficient`), NOT a verdict — they tell the reader *which legs are missing* (the handoff's "Empty" vs "Partial" patterns). H3 forbids `thesis_state` only as a *published conclusion*; rendered as a sub-state it is a gap-fact. |
| product-drivers segment (`product_metrics`) | **KEEP** | Display-only diagnostic (item 003 / CONTEXT.md `质量=weak` note); never a recommendation. |
| `thesis_evidence` / appendix / footnotes / constituent block | **KEEP** | Partial evidence to refresh from; never a conclusion. |

## Replacement line

A single bilingual line replaces the suppressed triad + triggers + cadence:

```
- ⚠️ 证据不足 / insufficient — 行动建议已抑制 (未形成结论)；缺口: {gaps}；刷新: `uv run irc narrative {narrative} --analyze`
```

where `{gaps} = ", ".join(r.evidence_gaps)` falling back to `r.risk_rationale` then the literal
`evidence_insufficient` when both are empty, and `{narrative}` is the render argument already passed to
`render_report_md`. Bilingual (matches every other narrative `.md` line). Names `evidence_gaps`
(mirrors H3's `原因: {gaps}`). Points at `--analyze` — the *actual* refresh path — NOT `fundamentals
snapshot` (the misleading string fixed in item 001). Deterministic: `evidence_gaps` / `risk_rationale`
are stable tuple/str; `narrative` is an arg.

## Acceptance criteria

Each criterion is independently verifiable by a unit test in `tests/narrative/test_report.py` (mirroring
the existing renderer-test style) unless noted.

1. **An insufficient row renders NO action triad.** For a `NarrativeFundReport` with
   `position_risk_level == "insufficient"`, the per-fund `.md` block contains NO `机会 / dca / 风险` line
   and NO `dca_action` / `risk_action` / `opportunity_state` token from that row (e.g. no `slow_dca`,
   no `do_not_buy`, no `review_required`, no `trim_review`, no `small_watch` / `pause_wait`).
2. **An insufficient row renders NO triggers and NO cadence.** No `证伪触发` line, no `减仓触发` line, no
   `复核节奏 / review_cadence` line in that fund's block.
3. **An insufficient row renders the refresh-evidence line.** The block contains the
   `⚠️ 证据不足 / insufficient` line; it names at least one of the row's `evidence_gaps` (or its
   `risk_rationale` when gaps render empty) and points at `irc narrative {narrative} --analyze`.
4. **An insufficient row KEEPS the gap-facts + diagnostics.** The block still renders
   `position_risk_level: insufficient`, the `主因 / drivers` line, the `说明` (risk_rationale) line, the
   `子状态` line with all four sub-states (估值/热度/逻辑/质量), and the `产品驱动` drivers segment.
5. **An insufficient row KEEPS partial evidence.** When the row carries `thesis_evidence` (or constituent
   evidence), the inline evidence bullets / `持仓明细` appendix / `证据明细` footnote table still render and
   every inline `[ref:hex]` still resolves (item 003 invariants intact on insufficient rows).
6. **A sufficient row is UNCHANGED.** For a row with `position_risk_level != "insufficient"` (e.g.
   `elevated` / `low` / `high`), the `.md` block is byte-identical to the pre-004 output: the
   `机会 / dca / 风险` triad, `复核节奏`, `证伪触发`, `减仓触发` lines all still render, and the existing
   `test_report_md_renders_risk_and_action_fields` (which uses `level="elevated"`) stays green unchanged.
7. **The `.json` stays the full source of truth.** `render_report_json` / `_report_dict` are UNCHANGED:
   the per-fund `.json` for an insufficient row still carries `opportunity_state`, `dca_action`,
   `risk_action`, `falsification_triggers`, `trim_triggers`, and `review_cadence` with their real values
   (item 003 AC8 — `.json` is additive/full; the `.md` is the lossy projection).
8. **Determinism (ADR 0004).** Two `render_report_md` calls on the same insufficient-row tuple are
   byte-identical; the new helper performs no I/O and no unsorted dict/set iteration.
9. **Mixed report renders correctly.** A report tuple containing BOTH an insufficient row and a sufficient
   row renders the suppressed/refresh shape for the first and the full triad/triggers for the second in a
   single `render_report_md` call (the branch is per-row, not per-report).
10. **Tests + lint green.** `uv run pytest tests/narrative/` and `uv run ruff check src tests` pass; any
    pre-existing test that asserted triad/trigger tokens on an `insufficient` row is updated to the new
    shape (none exist today — `_report()` defaults to `level="elevated"` — but the AC documents the
    expectation if one is added).

## Non-goals

- **Changing `risk.py` / `derive_position_risk_level`.** The `evidence_gaps → insufficient` rule
  (`risk.py:60`) is unchanged. This item only changes how an already-`insufficient` row is *displayed*.
- **Changing the scorer / `classify_*` / `build_opportunity_row` / `analyze.py`.** No field population
  changes; `error_report` and `_report_from_card` keep emitting the same `NarrativeFundReport` (the
  `.json` still carries everything).
- **The coverage-gap work (items 001 / 002).** Active-fund autobuild and passive-ETF fund-level wiring
  are out of scope. (More cached evidence will move some rows from insufficient → sufficient — that
  interaction is correct and needs no 004 change.)
- **M1 / M2 markdown enrichment (item 003).** The inline-summary segment, evidence appendix, footnote
  table, product-drivers segment, and weak-floor legend are item 003's and are reused as-is on the KEEP
  side; 004 adds no new evidence/metrics rendering.
- **Touching the opportunity/discipline `failure_renderer.py` or its H3 partition.** 004 mirrors that
  discipline in the narrative renderer; it does not modify the opportunity surface.

## Constraints

- **H3 field discipline** (CONTEXT.md "H3 universal gapped-row invariant"): the SUPPRESS set must be the
  forward-recommendation fields (triad + triggers + cadence); the KEEP set is identity + gap-facts +
  diagnostics + partial evidence. Do not invent a new field taxonomy — mirror the conclusion-vs-fact
  split `failure_renderer.py` already enforces.
- **Renderer determinism (ADR 0004):** the suppressed/replacement rendering is pure; two calls are
  byte-identical; no I/O, no unsorted iteration.
- **`.json` is the full source of truth** (item 003 AC8): suppression is `.md`-only.
- **SAME-3 / citation invariants (ADR 0001/0004):** unchanged on the KEEP side — `select_citations(cap=3)`
  inline cap and `[ref:[0-9a-f]{16}]` footnotes still apply to any evidence rendered on an insufficient row.
- **TDD:** red → green → refactor; test file mirrors source (`report.py` / `report_appendix.py` →
  `tests/narrative/test_report.py`).
- **Size budget:** files < 200 lines, functions < 20 lines; the helper extraction keeps `report.py`
  under budget.
- **Effects at edges / frozen dataclasses:** the renderer reads `NarrativeFundReport` and returns a string;
  no mutation, no module state.

## Open questions — resolved

- **Q1 — SUPPRESS vs KEEP set.** RESOLVED (see table above). SUPPRESS = `opportunity_state`,
  `dca_action`, `risk_action`, `falsification_triggers`, `trim_triggers`, `review_cadence`. KEEP =
  `instrument_id`, `name_cn`, `position_risk_level`, `risk_rationale`, `risk_drivers`, `evidence_gaps`,
  the four sub-states, product-drivers segment, and any partial evidence/appendix/footnotes.
  *Rationale:* H3's load-bearing split is conclusion (forward recommendation) vs fact (gap statement).
  The triad + triggers + cadence are forward recommendations; everything else is an honest gap-fact or
  diagnostic that tells the operator what to refresh — the narrative analog of H3's
  `evidence_gaps` / `fetch_types_attempted`. Sub-states render as gap-facts (`逻辑=evidence_insufficient`),
  not as the `thesis_state` *verdict* H3 forbids.
- **Q2 — Replacement line wording.** RESOLVED. Single bilingual line
  `⚠️ 证据不足 / insufficient — 行动建议已抑制 (未形成结论)；缺口: {gaps}；刷新: \`uv run irc narrative {narrative} --analyze\``,
  naming `evidence_gaps` (fallback `risk_rationale`) and pointing at `--analyze`.
  *Rationale:* bilingual matches the surface; naming gaps mirrors H3's `原因: {gaps}`; `--analyze` is the
  real refresh path (not the `fundamentals snapshot` string item 001 corrects).
- **Q3 — .md vs .json scope.** RESOLVED. `.md`-only; `.json` unchanged.
  *Rationale:* item 003 AC8 locks the `.json` as the additive full source of truth. H3 partitions *rows
  across files*; the single-file narrative analog is "don't *display* unearned conclusions in the
  human-facing `.md`". The machine-readable surface stays complete for downstream consumers.
- **Q4 — Determinism.** RESOLVED. Branch is on a single field; the helper emits a fixed-shape line from
  already-deterministic tuples/strings; no I/O. Existing sufficient-row tests stay green; new
  insufficient-row tests cover the changed shape (expected per the directive).
- **Q5 — Scope guard.** RESOLVED. Renderer-only; `risk.py`, the scorer, `analyze.py`, and items 001/002/003
  are untouched.

No open question remained unresolved from MASTER-SPEC / handoff / code.
