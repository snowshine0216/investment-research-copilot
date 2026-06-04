# SKIPPED — items deferred out of the autodev loop

These are **not** abandoned. Each is explicitly out of the loop's reach per the spec, with an unblock path. They block on a human decision or live network the loop must not perform.

## PR2 — flip the flag (`active_fund_lookthrough.enabled: true`)

**Blocker:** Depends on the gate-#5 human review choosing the final `coverage_floor` (0.50 vs 0.40 vs other). A flag-flip cannot be planned well without the review outcome (spec §3.8, §10).
**Unblock path:** After PR1 merges, the user runs `irc fundamentals stock-valuation` + `irc opportunity` on real cached data, reviews the diff report (gate #5), and chooses the floor. Then PR2 = set `enabled: true` + chosen floor, record before/after output diff, write the ADR 0012 addendum + CHANGELOG + CONTEXT.md. Spec §10: "PR2 needs no new spec." A small plan or direct change suffices unless gate #5 surfaces a methodology flaw (→ back to brainstorming).

## Gate #4 — live-symbol confirmation (`IRC_RUN_LIVE_AKSHARE=1`)

**Blocker:** Hits real AkShare/EastMoney. The project double-gates live tests (pytest marker + `IRC_*=1`). Spec §10 names this a hard gate that "must stop the loop." Running it autonomously violates the cached-evidence discipline and is slow/flaky.
**Unblock path:** PR1 ships the live-gated fetcher test (`-m live_akshare`). The user runs it with `IRC_RUN_LIVE_AKSHARE=1` to confirm `stock_value_em` returns real rows with the expected `数据日期`/`PE(TTM)`/`市净率` columns for a known A-share, and that the `(date, pe_ttm, pb)` extraction holds. No silently-guessed column strings ship to prod without this.

## Gate #5 — human review of the diff report

**Blocker:** Non-negotiable human sign-off on the would-flip bands, Δpercentile, per-metric coverage, source mix, current-basket caveat, and floor-sensitivity table — on real cached data. Also where the final floor is chosen.
**Unblock path:** PR1 produces the diff-report command + artifact. The user reviews it and signs off (or bounces a methodology flaw back to spec).
