# 001 — Spec stub (plan mode)

**Goal (inferred from plan):** Make the discovery pipeline pick CN-fund universe members on quality rather than fund_code order, and let global-mandate QDII active funds bucket separately from domestic broad-active equity.

**Why:** Today `_candidate_rank` ties on `fund_code` ascending, silently dropping high-numbered strong performers like `270023 广发全球精选股票(QDII)` (ranked 5087/5545). A global-mandate QDII fund also has to compete against 5,500+ broad-active domestic funds for the same 40 slots.

**Acceptance:**
- `270023` lands in the regenerated universe with `asset_class: qdii_global`
- `_apply_caps` with `returns={}` is order-equivalent to today (backward-compatible)
- No downstream test regression; new asset class handled by any callers that branch on `asset_class`

**Authoritative plan:** see `items/001-plan.md` (verbatim copy of `docs/superpowers/plans/2026-05-21-universe-quality-ranking-and-qdii-global.md`).
