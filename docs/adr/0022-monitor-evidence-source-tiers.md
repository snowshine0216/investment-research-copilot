# ADR 0022 — Monitor Evidence Source Tiers Gate Ingest

**Status:** Accepted (design; implementation with report v3)
**Date:** 2026-07-02
**Deciders:** Xue Yin

---

## Context

The 2026-07-01 monitor report cited and scored junk web sources: 13 appendix
entries from `letsdatascience`, 8 from `mezha.net`, 2 from `facebook.com`, and a
comedy piece. These items feed `gather_impacts` → `macro_tilt` — the factor
already documented as volatile (MEMORY.md → "Monitor macro_tilt instability") —
so source quality is an accuracy problem, not just a readability one.

## Decision

Theme-pool (web-search) evidence passes a **source-tier gate at ingest**,
before `make_evidence_item`:

- `classify(domain) → blocked | 1 | 2 | 3` by **domain-suffix match** from a
  `source_tiers:` section in `config/monitor.yaml` (tier 1 权威 official/wire,
  tier 2 财经媒体 mainstream financial press).
- **`blocked` domains never become evidence** — never scored, never cited, no
  `citation_id`. Drop counts are logged (not traced).
- **Unknown domains are KEPT as tier 3 未分级** and visibly badged at render —
  a legit new source degrades to "visibly unvetted", never silently vanishes;
  promotion/blocking is a config edit.
- **Scope: theme pool only.** Constituent-pool evidence is snapshot-grounded
  (broker/filing summaries, synthetic `snapshot:<symbol>` items — no meaningful
  publisher domain) and sits outside the tier system with its own 快照 badge.
- Malformed/missing tier config → everything classifies tier 3 plus a logged
  warning (fail-open, visible, never fatal).
- `_ENGINE_VERSION` unchanged: the gate changes macro_tilt's *inputs* (which
  evidence exists — already run-varying by nature), not scoring math.

## Considered options (rejected)

- **Render-only demotion** — junk keeps feeding the volatile macro_tilt scorer;
  the report looks clean while the number stays polluted.
- **Dropping unknown domains at ingest** — silently loses legitimate new
  sources; the keep-and-badge path preserves coverage and makes vetting a
  visible, reversible config decision.
- **LLM source-quality judging per item** — paid, volatile, unauditable
  against a config list.

## Consequences

- The first gated run may shift `macro_tilt` values (bias flips possible on
  switchover day) — accepted; the 今日速览 flip row makes it visible.
- The tier lists are a maintained config surface; `irc config validate`
  checks the section shape.
