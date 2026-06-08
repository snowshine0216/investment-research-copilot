# Phase A — broad-index grounding: before/after

**STATUS: LIVE CAPTURE COMPLETE (operator gates #4 + #3 + #5) — 2026-06-08.**

Captured after the legulegu rate-limit hardening (ADR 0014, PR #121→#122, on `main` `b7c5bda`).
The pre-fix baseline is the documented state from the same day's earlier probing (re-running the
**old** naive 8-rapid-call loop live purely to regenerate a table was deliberately NOT done — it
would re-trip the very limiter this fix exists to avoid).

---

## Gate #4 — single-shot live fetch (cold-window check), 12:48 CST

All four production broad symbols returned rolling PE **and** PB live, paced, with **zero throttling**:

| symbol | PE | PB |
|--------|----|----|
| csi1000 (中证1000) | 36.62 | 2.81 |
| csi300 (沪深300) | 13.65 | 1.43 |
| **csi500 (中证500)** | **29.2** | **2.51** |
| **sse50 (上证50)** | **11.05** | **1.17** |

`4 passed, 1 skipped in 36.63s` — the clean-path timing (8 paced calls × ~4s GAP, no 30s cooldown
sleeps). **GAP=4s defeats the burst limiter across all 8 calls; no calibration needed.**

## Gate #3 — production ingest + grounding, 13:21–14:09 CST

`uv run irc run --from ingest` completed exit 0 (`ingest, research, discover, score, gold,
allocate, plan, opportunity, memo, decision`). The broad legulegu leg ran with **no
`LeguleguCooldownExhausted`, no sweep suspension, no `replace skipped` warning** — it landed cleanly.

### `index_valuation_history` cache — all 4 broad indices now complete

| slug | rows | PE rows | PB rows | latest |
|------|------|---------|---------|--------|
| csi300 | 5140 | 5140 | 5140 | 2026-06-05 |
| **csi500** | **4711** | **4711** | **4711** | 2026-06-05 |
| csi1000 | 2828 | 2828 | 2828 | 2026-06-05 |
| **sse50** | **5200** | **5200** | **5200** | 2026-06-05 |

`csi500` and `sse50` went from **0 rows (never landed)** → full PE+PB coverage. This is the core win.

### Grounding count (`count_grounded.py`)

| | BEFORE (pre-fix, 2026-06-08 earlier) | AFTER (gate #3) |
|---|---|---|
| broad_index rows | 7 | 7 |
| grounded (real PE-TTM) | **4** (csi300×4) | **6** (csi300×4, **csi500×1**, **sse50×1**) |
| csi500 / sse50 | `None` (series never landed) | **grounded** ✅ |

**`grounded ≥ 9` target: NOT met (6).** This is **watchlist composition, not the fix.** The ≥9 target
assumed `csi300×4, csi500×2, csi1000×2, sse50×1`; this run's `discover` stage surfaced
`csi300×4, csi500×1, sse50×1` and **no csi1000-tracking ETF** (plus one non-allowlist
`512960 中证国新央企科技引领`). Every broad-index ETF present grounded (6/6, 100%). Because the
csi1000 series **is** cached (2828 PE rows), any csi1000 fund that appears in a future watchlist will
ground without re-fetching.

## Gate #5 — eyeball checks ✅

- **valuation_state flips to PE-TTM grounding:** all 6 grounded broad funds (510300/510310/510330/159919
  沪深300, 510050 上证50, 510500 中证500) show `valuation_state=fair` — fundamental PE-TTM percentile, not
  the NAV fallback. Across all 80 rows only 1 is `evidence_insufficient`.
- **Seed/QDII funds excluded from broad grounding:** `161721` not in report; `003318` on its own
  fund-level path (`lookthrough_key=fund_003318`, `very_expensive`), not the broad allowlist;
  `标普红利低波50` absent. ✅

## Verdict

The rate-limit fix is **proven in production**: paced fetch lands all four broad indices with complete
PE+PB, the previously-chronic csi500/sse50 failures are resolved, grounding rose 4→6 (every broad ETF
present grounds), and the ingest no longer hammers or loses calls under the limiter. The numeric `≥9`
gate is below target this run **only** because discovery surfaced fewer broad-index ETFs (no csi1000
fund); the grounding machinery and cached data are complete for all four indices.

---

*Live capture by operator follow-up on 2026-06-08 (gates #4 + #3 + #5). Pre-fix baseline per the
documented 2026-06-08 probing state; see `project_phase_a_gate_status` memory + ADR 0014.*
