# Item 003 — Verdict: axis already ON, no flip performed

**Run:** `docs/2026-06-10-actionable-ops` · **Item:** 003 · **Date:** 2026-06-10
**Outcome:** verification + regression-lock + documentation. No production code-path change.

## Valuation axis state (AC1)

- **Phase D active-fund look-through axis is already `enabled: true`** in the packaged
  template `src/irc/templates/config/valuation_buckets.yaml`
  (`active_fund_lookthrough.enabled: true`, `coverage_floor: 0.50`), committed `cb1642d`
  (Phase D PR2, PR #111, 2026-06-05; gate #5 signed off, ADR 0012 addendum 2026-06-05).
  **No flag flip was performed — there is nothing to flip.** This item only adds a
  regression test (`tests/templates/test_valuation_buckets_template.py`) pinning the
  shipped value so it cannot silently regress.
- **The consensus-upside axis (`consensus_upside_pct` → `valuation_fundamental_signal`)
  stays `None` by the ADR 0009 contract.** Lighting it up requires an out-of-scope
  target-price source (Tushare) and would violate the recorded degrade-to-`None`
  decision. Left dormant by design; out of scope for this item.

## Memo routing (AC3/AC4)

- The packaged template `src/irc/templates/config/llm.yaml` routes `memo_synthesis` and
  `memo_audit` through OpenRouter Anthropic models (the **Memo LLM routing (shipped
  default)**, CONTEXT.md). README already described this; this item sharpened the note to
  name the packaged-template-vs-runtime-config distinction (CONTEXT.md "Config: packaged
  template vs runtime"). A `deepseek-reasoner` memo routing only ever arises from a
  machine-local **runtime config** override (`config/llm.yaml`, gitignored).

## Behavioural drift (AC5)

- No `src/irc/**` production module was modified. The new tests only *read* packaged
  templates and assert values; `OpportunityInput` is compute-only (never serialised).
  README / CHANGELOG / this verdict are docs. Therefore `valuation_state` and the
  opportunity-state distribution from `irc opportunity` / `irc decision` are unchanged.

## No new ADR

- The axis-ON decision (`enabled: true`, `coverage_floor: 0.50`, gate #5) is already
  durably recorded in ADR 0012's 2026-06-05 addendum. Per the grill (Q2), re-recording it
  fails the three-of-three ADR bar. This verdict is the verification record.
