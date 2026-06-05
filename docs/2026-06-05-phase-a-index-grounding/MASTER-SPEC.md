# MASTER-SPEC — Phase A: Broad-index valuation grounding (NAV → PE-TTM)

**Mode:** spec (single feature, N=1)
**Run dir:** `docs/2026-06-05-phase-a-index-grounding/`
**Source spec:** [`docs/superpowers/specs/2026-06-05-phase-a-broad-index-grounding-design.md`](../superpowers/specs/2026-06-05-phase-a-broad-index-grounding-design.md)
**Date:** 2026-06-05

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | Move 18 curated broad-index ETFs (+ legit generated index funds) off NAV self-history percentile onto legulegu PE-TTM historical percentile by populating the already-wired `valuation_percentile_fundamental` slot. Fix BREAK 1 (display-name inversion), BREAK 2 (PE column = 静态 not 滚动), BREAK 3 (unconfirmed symbols). No new stage/table/fetcher. | **IN** | Single coherent feature on an already-plumbed path; touches ~5 src files + tests + docs + a before/after diff artifact. |

No OUT-scope items in spec mode (single feature). Follow-ups the source spec defers (§8) are recorded here for traceability but are **not** part of this run:

- Graduating speculative symbols (star50, chinext, chinext50, csi_dividend, csi_dividend_lc, csi_a500) as each is live-confirmed.
- The exact csindex `930782` valuation path for `003318` (Phase B).
- A disclosed-proxy policy + ADR 0012 addendum, *if* ever desired.
- Phases B (sector) / C (foreign) / 0 (gold + bond-misclass), per the ROADMAP.

## Decisions of record (from source spec §2 — carried verbatim)

- **D1** PE leg reads `滚动市盈率` (rolling/TTM) ONLY; return `None` if absent — never fall back to `静态市盈率`.
- **D2** Production symbol map = verified-exact allowlist of `{csi300, csi500, csi1000, sse50}` only. Speculative symbols in a separate, clearly-marked probe map.
- **D3** `标普红利低波50` stays on NAV (unmapped — distinct S&P-licensed index).
- **D4** `chinext` and `chinext50` are DISTINCT exact slugs — never combined. `创业板指 → chinext`, `创业板50 → chinext50`. Both speculative until live-confirmed. No ADR 0012 addendum required.
- **D5** `161721` gets a seed override stripping its `沪深300` tag.
- **D6** `003318` gets a seed override stripping its `中证500` tag → NAV/Phase D.
- **D7** Honest coverage target = ~9 funds, measured (not ~20).
- **D8** Broad ingest leg does per-key full *replace*; shared sector leg keeps *append*. Non-empty fetch required before delete.

## Acceptance gates (source spec §5)

1. Tests green (ruff + full `uv run pytest`); new behaviour TDD-first.
2. Invariants intact (H3 universal gapped-row + SAME-3 citation-set tests).
3. Coverage measured ≥ 9 non-`None` `valuation_percentile_fundamental` for broad funds.
4. Live confirmation: production allowlist hard-asserted under `IRC_RUN_LIVE_AKSHARE=1`.
5. Human diff review (hard stop): before/after artifact committed.
6. Docs synced (CONTEXT.md "Valuation inputs"; CHANGELOG `[Unreleased]`, **no VERSION bump**; ROADMAP Phase A). **No ADR 0012 addendum.**
