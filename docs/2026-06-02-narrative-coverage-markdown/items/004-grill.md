Verdict: PASS

Subagent: opus
Questions resolved: 6 (+ 1 ADR decision)
Docs touched: CONTEXT.md (+SHA at commit), docs/2026-06-02-narrative-coverage-markdown/items/004-spec.md (+SHA at commit)
Spec refined: docs/2026-06-02-narrative-coverage-markdown/items/004-spec.md (+SHA at commit)
ADR: none (three-of-three rule fails — additive display-discipline change mirroring existing H3 + ADR 0004; reversible, unsurprising, no novel architectural trade-off)

## Resolved decisions

### Q1 — Are the four sub-states (估值/热度/逻辑/质量) gap-FACTS (KEEP) or H3-forbidden verdicts (SUPPRESS)?
- **A:** SUPPRESS. The original spec's single flagged judgment (KEEP the four sub-states as "gap-facts") was VERIFIED WRONG.
- **Rationale:** `src/irc/opportunity/failure_renderer.py` (lines 6-9) explicitly lists `valuation_state, heat_state, thesis_state, product_quality_state` among the conclusion fields it NEVER reads "because gapped rows have not earned conclusions"; CONTEXT.md line 56 lists `thesis_state` among the forbidden set. Decisively, `build_opportunity_row` (`states.py:538-591`) populates `evidence_gaps` and the four sub-states via INDEPENDENT classifiers — a row missing only `missing_product_metadata` is forced to `position_risk_level == "insufficient"` (`risk.py:60`) yet still carries `valuation_state=expensive` etc. as REAL verdicts. So the `子状态` line CAN leak the exact published verdicts H3 forbids (true on the `_report_from_card` path; only the `error_report` path forces all four to `evidence_insufficient`). Field-level suppression is the H3-faithful rule — value-conditional rendering is what "the renderer's signature is the enforcement mechanism" rejects. Missing legs are surfaced via `evidence_gaps` codes in the refresh line, an unambiguous fact.
- **Doc-impact:** corrected KEEP table, Goal/SUPPRESS prose, AC1/AC4/AC6, in-file Q1; new CONTEXT.md entry.

### Q2 — Does suppressing the `子状态` line also drop the `产品驱动` (`product_metrics`) segment?
- **A:** No — decouple; `product_metrics` (费率/规模/任职/跟踪误差) KEEPS on its own standalone line.
- **Rationale:** raw numeric data is a gap-fact, not a classification; the current line-coupling with the `质量=weak` label (`report.py:102-106`) is incidental layout. The `质量` verdict label is suppressed; the raw drivers stay (CONTEXT.md `质量=weak` mitigation depends on them).
- **Doc-impact:** corrected KEEP-table product-drivers row + AC4.

### Q3 — Replacement-line wording: accurate, deterministic, points at `--analyze`?
- **A:** Yes, keep the spec's bilingual line.
- **Rationale:** `--analyze` is the real refresh path (CONTEXT.md 170-171, narrative active-fund autobuild populates the cache), NOT `fundamentals snapshot` (item 001's fix). Names `evidence_gaps` (mirrors H3 `原因: {gaps}`); deterministic. Noted: `evidence_gaps` is provably non-empty on both insufficient paths, so the `risk_rationale`/literal fallbacks are defensive-unreachable.
- **Doc-impact:** note added to Resolved decisions.

### Q4 — `.md`-only suppression, `.json` unchanged — consistent with item 003 AC8 + H3?
- **A:** Yes. `_report_dict` stays unchanged (full source of truth, item 003 AC8). H3 partitions rows across files; the single-file analog is display discipline. Narrative path is Policy-B-free / no-H3-partition (CONTEXT.md) so no invariant binds `.json` to mirror `.md`.
- **Doc-impact:** captured in new CONTEXT.md entry.

### Q5 — Determinism (ADR 0004) + existing-test impact.
- **A:** ADR-0004-clean; zero existing tests break; one expected additive-test class.
- **Rationale:** single-field branch, no I/O, no unsorted iteration. `test_report_md_renders_risk_and_action_fields` uses `level="elevated"` (sufficient) → stays green. No existing test asserts the triad/sub-states on an insufficient row.
- **Doc-impact:** none.

### Q6 — Add a narrative-side forbidden-token enforcement test (mirror failure_renderer.py criterion 18)?
- **A:** Yes — strengthen AC1 to forbid sub-state verdict tokens (`expensive`, `overheated`, `falsified`, `weak`, `intact`, ...) and the `子状态` marker, not just the action-triad tokens.
- **Rationale:** H3's enforcement is a locked grep test; mirroring the discipline without the test leaves the suppression a soft convention vulnerable to silent regression.
- **Doc-impact:** strengthened AC1.

### ADR decision
- **A:** No new ADR. Three-of-three fails: reversible (additive `.md`-only branch), unsurprising (mirrors documented H3 + ADR 0004), no novel architectural trade-off (rejected alternatives are rendering-mechanics). Captured as a CONTEXT.md glossary entry.
