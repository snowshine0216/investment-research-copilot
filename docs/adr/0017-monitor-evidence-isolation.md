# ADR 0017 — Monitor evidence is isolated from the dual-coverage citation model

**Status:** Accepted (2026-06-15, `irc monitor` design grilling)
**Builds on:** [ADR 0001 — citation data model](0001-citation-data-model.md), [ADR 0003 — failure-mode + Policy B](0003-failure-mode-policy-b.md).
**Spec:** `docs/superpowers/specs/2026-06-15-monitor-daily-report-design.md` §4.

## Context

The opportunity/memo pipeline cites evidence as `ThesisEvidence`, whose `scope`
field (`instrument | constituent | asset_class_macro | policy`) is the load-bearing
discriminator of the **dual-coverage gate**: a publishable row needs a data leg AND
an information leg, both with `scope in {instrument, constituent}` and
`owner_instrument_id == row.instrument_id`. Macro/theme news is deliberately built
with `scope="asset_class_macro"` ([opportunity/thesis_evidence.py:143](../../src/irc/opportunity/thesis_evidence.py)) precisely so it can **never** satisfy that gate — it is supplemental context only.

The new `irc monitor` vertical produces a per-fund **directional bias** backed by
macro/theme news (the `macro_tilt` factor) and per-holding news (the `constituent`
factor). An early design proposed *promoting* that macro evidence from
`asset_class_macro` to `instrument`/`constituent` scope so it could be "bound to the
fund as owner." That is both unnecessary (ownership is already `owner_instrument_id`,
and the monitor's own coverage gate counts evidence *families*, never reading
`scope`) and dangerous: if monitor-built evidence ever shared an evidence pool or a
`build_cited_map` pass with the opportunity pipeline, a re-scoped geopolitics headline
would **falsely satisfy the dual-coverage gate** — the exact failure that
`asset_class_macro` exists to prevent.

## Decision

The monitor uses its **own `EvidenceItem`** type — `(source, title, date, url,
owner_fund_id, citation_id)` — with **no `scope` field**, and does **not** reuse
`ThesisEvidence`. Monitor evidence is owner-bound *by construction*: each fund's
evidence pool is assembled only from that fund's own themes and holdings, so there is
no scope to promote and no ownership to assert after the fact. The `citation_id` is
16 hex chars **only** so the shared `\[ref:[0-9a-f]{16}\]` marker regex matches; its
preimage is the monitor's own (e.g. `sha256(owner_fund_id:url_or_fallback:date)`) and
is independent of ADR 0001's `ThesisEvidence` preimage. The monitor's evidence
machinery and the dual-coverage gate **never touch**.

### Considered options

- *Rejected — reuse `ThesisEvidence`, re-scope macro → `instrument`.* Overloads the
  one field the dual-coverage gate keys on with semantics that contradict its
  documented meaning; a latent correctness landmine the moment any pool is shared.
- *Rejected — reuse `ThesisEvidence` with honest scopes + `owner_instrument_id`.*
  Safer (no false gate satisfaction) but still couples the monitor to a type whose
  `scope` it never uses, and pulls the dual-coverage vocabulary into a vertical that
  has no dual-coverage gate. Isolation is cleaner than disciplined reuse here.

## Consequences

- A second, smaller evidence type exists — accepted cost for **complete isolation**:
  no macro headline can ever leak into the dual-coverage gate via the monitor.
- Monitor `citation_id`s are **not comparable** to opportunity/memo `citation_id`s
  (different preimage). This is fine — the pools are separate by design.
- The monitor's coverage gate (independent evidence *families*: price-momentum,
  valuation, crowding, news) is `scope`-agnostic, so dropping `scope` costs it
  nothing.
