# 003 — Provider degradation gate

## Why

`research_status.json` shows `brave_news: timeout` on 4 of 7 themes
(us_monetary, us_fiscal_politics, geopolitics, gold_drivers). The
pipeline publishes anyway. The adversarial review (§A4) demands:
"if N% of themes lost a provider, downgrade confidence."

## What changes

In `src/irc/research/quality_gate.py`:

1. Compute, alongside the existing pass/warn/fail verdict, a
   `provider_degradation_count` over a list of **critical themes**:
   `gold_drivers`, `cn_monetary`, `us_monetary`, `holdings_sector`.
2. If ≥2 of those critical themes lost a provider (i.e.
   `provider_failures` non-empty) OR returned no relevant sources after
   the item-001 filter, the verdict becomes WARN (or worse). Add a new
   reason string `"critical themes degraded: ..."`.

In `src/irc/research/persistence.py` (or wherever
`research_status.json` is written), include the degradation count and
list of degraded themes so memo synthesizer (item 014/010 family) can
surface it.

## Acceptance criteria

- Re-running on the 2026-05-19 inputs produces a `QualityVerdict` whose
  reasons mention at least one critical theme degraded.
- `research_status.json` includes a `provider_degradation` block
  describing which themes lost which providers.
- Unit tests cover: 0 degraded → PASS, 1 degraded → still PASS, ≥2
  degraded critical → WARN.

## Tests to add

- `tests/research/test_provider_degradation.py` with synthetic theme
  reports.
