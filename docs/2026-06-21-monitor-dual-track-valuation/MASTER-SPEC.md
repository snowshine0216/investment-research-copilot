# MASTER-SPEC — Monitor dual-track valuation + False-Cheap clamp

**Mode:** spec (single feature)
**Run dir:** `docs/2026-06-21-monitor-dual-track-valuation/`
**Source spec:** [`docs/superpowers/specs/2026-06-19-monitor-dual-track-valuation-design.md`](../superpowers/specs/2026-06-19-monitor-dual-track-valuation-design.md) (grilled & revised 2026-06-21)
**Surface:** `irc monitor` (Monitor vertical — ADR 0017)
**Builds on:** #168 (per-stock drill-down + `flow` factor), ADR 0017/0018/0019 D4.

## Scope classification

| # | Item | Class | Rationale |
|---|------|-------|-----------|
| 001 | Re-base the look-through valuation factor as a bottom-up per-stock **dual-track** score (self-history 0.60 + industry-relative 0.40) with a **False-Cheap clamp** (value-trap → NEUTRAL); new `industry_valuation.py` edge fetch; full-basket aggregation with a 0.40 monitor coverage floor; report board columns + value-trap badge; eval schema/determinism/reconciliation; engine `"2"→"3"`; new ADR 0020. | **IN** | The evidence-**independent** leg of ADR 0019 D4. Fully grilled (Q1–Q8 resolved inline + memory). Ready to build. |

**OUT (deferred — the evidence-gated post-composite veto tier):** conflict hard-suppression, flow-reversal sign-agreement guard, Amihud tradability veto. Per spec §10 these are judged against forward evidence that resets to engine `"3"` here and are a **separate future spec**. Not in scope this run. (No SKIPPED rows — these are explicitly out-of-scope deferrals named in the source spec, not items the user asked autodev to do.)

## Notes
- Single IN-scope item → degenerate N=1 loop.
- All work lands on feature branch `autodev/monitor-dual-track-valuation-feature`; final roll-up PR opened (not merged) into `main` for user review — no "merge to main" opt-in given this turn.
