# MASTER-SPEC — Phase D active-fund look-through (PR1 shadow compute)

**Mode:** spec (single-task, N=1)
**Source spec:** [`docs/superpowers/specs/2026-06-04-phase-d-active-lookthrough-design.md`](../superpowers/specs/2026-06-04-phase-d-active-lookthrough-design.md) (copied verbatim to `items/001-spec.md`)
**Run started:** 2026-06-04

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | **Phase D PR1 — shadow compute (flag OFF)**: per-stock valuation fetchers (EastMoney primary + Tushare fallback), `stock_valuation_history` table + ingestor, `irc fundamentals stock-valuation` command, pure aggregation core `opportunity/lookthrough_valuation.py`, flag-gated `inputs_loader` active-fund branch, config flag in `valuation_buckets.yaml`, and the gate-#5 diff report. | **IN** | The spec (§10) declares PR1's code + tests autodev-able. Flag default OFF → prod byte-identical → contained blast radius. |

## Out of scope (see SKIPPED.md)

| Item | Why out of the autodev loop |
|------|-----------------------------|
| **PR2 — flip the flag (`enabled: true`)** | Spec §3.8/§10: PR2 runs only *after* the gate-#5 human review chooses the final `coverage_floor`. It is a config flip + recorded output diff + ADR addendum, not new design — and it is gated on a human decision the loop cannot make. |
| **Gate #4 — live-symbol confirmation** (`IRC_RUN_LIVE_AKSHARE=1`) | Hits real AkShare/EastMoney. The project double-gates live tests (marker + env). Spec §10: "gates #4 and #5 are not [autodev-able], and must stop the loop." The loop ships the live-gated test *code* but does not execute it autonomously. |
| **Gate #5 — human review of the diff report** | Non-negotiable human sign-off on real cached data; also where the final `coverage_floor` is chosen. Cannot be automated. |

## Acceptance (PR1, from spec §9/§10)

- Aggregation core unit-tested (harmonic worked example, `/100` coverage-floor unit boundary, non-positive-PE exclusion, per-date renormalization, PE 120/180 maturity gate vs PB `<30` floor, degrade-to-None on every gap).
- Flag-off byte-identical regression (dormancy lock) + flag-on population test; index path unchanged.
- H3 universal gapped-row + SAME-3 invariants intact with flag both off and on.
- `irc config validate` accepts the new `active_fund_lookthrough` config block.
- Live-gated fetcher tests authored (NOT run) for gate #4.
- Diff report command produces the gate-#5 artifact (runs regardless of `enabled`).
- `uv run ruff check src tests` clean.
