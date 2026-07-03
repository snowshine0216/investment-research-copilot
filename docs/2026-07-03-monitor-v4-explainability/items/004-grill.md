Verdict: PASS

Subagent: grill-with-docs (autonomous — no user in loop; recommended answers auto-accepted per dispatch override). Upstream locks from the 2026-07-03 source-spec grill + OD-1 (batch-first f127 at both existing call sites, cross-day map store semantics ≤30d serve-while-stale/refresh-on-seen/atomic/corrupt→empty, per-symbol fallback-only, board-PE fetch-first + STALE-N ≤3td FEEDS factor math / >3td DARK, no engine bump, flow_reconciliation byte-identity, KNOWN_NA_REASONS unchanged) were NOT reopened; the grill hardened the item spec's own NEW decisions against CONTEXT.md, ADR 0019/0020, the CN-egress light-up spec (D3/D4/D5), `scripts/phase0_flow_batch_spike.py`, and the working tree.

Questions resolved: 9 (RD-1 … RD-9 in the spec's `## Resolved decisions`). 2 real defects found and fixed in-spec (RD-1 spot-check axis gap; RD-2 empty-`{}`-table stale-serving landmine — two such files are literally on disk today), 2 sharpenings (RD-3 calendar scoping; RD-7 back-compat wording strike-through), 2 guard-chains made explicit (RD-4, RD-6), 3 verifications-with-evidence (RD-5, RD-8, RD-9). Zero unresolved; the only execution-time unknown remains the environmental AC-15 live-endpoint reachability (MASTER-SPEC pause-at-verify-gate handling stands).

Docs touched:
- `CONTEXT.md` — *Board-PE freshness state* term sharpened with the two serving rules (FRESH calendar-independent; only a non-empty table serves stale); new term **Stock-industry map (cross-day store)** added adjacent (30-calendar-day vs 3-trading-day window disambiguation, absence-≠-evidence, batch-first + fallback merge). No other entries touched.
- `docs/adr/0020-monitor-dual-track-valuation.md` — new addendum **"board-PE three-state staleness + fetch-first; industry names batch-first (2026-07-03)"** (mandated by source-spec slice 5; three-of-three ADR test passes): OD-1 contract + the deliberate divergence from flow's abstain-only posture, stale-scan non-empty hygiene, calendar scoping, fetch-first reorder + capture-job refresh ordering, and the P7 batch-first amendment to D3's per-symbol transport posture.
- `docs/2026-07-03-monitor-v4-explainability/items/004-spec.md` — refined in place (AC-6, AC-9, AC-14, AC-15, AC-17, Constraints back-compat bullet, Q5; appended `## Resolved decisions`). Strike-throughs with rationale preserved, nothing deleted.

Spec refined: yes — full rationale + code citations live in the spec's `## Resolved decisions`; summary below.

## Resolved decisions

**RD-1 — AC-15 spot-check covered only the field-widening axis.** The item also widens the SECID LIST (top-5 union → full-basket union) — the request production will actually make. Fixed: request A = top-5 union + old fields, request B = full-basket union + new fields, f184 intersection 4 dp — same two live calls, both axes. Store-scope preservation itself verified structurally: `append_today` writes whatever it is given (`flow_series_store.py:87-92`), the store's only recurring writer is `run_flow_capture` (12:15 brief is read-only, D6), and top-5 union ⊆ full-basket union by construction, so AC-3's slice-back is sound.

**RD-2 — Empty-table stale-serving landmine (real defect).** `data/monitor/industry_pe/2026-06-29.json` + `2026-06-30.json` are literally `{}` on disk (pre-light-up caches; no purge per Non-goals). The original scan would serve `{}` under a `板块PE 引用 <date>` age tag while every row reads `industry_no_data` — an inverse silent-stale lie. Fixed: only a non-empty parsed table serves; empty/unreadable files skipped, scan continues older within ≤3 td; boundary test added.

**RD-3 — Calendar-unavailable → DARK scoped to the stale branch only.** FRESH is `as_of == today` string equality — calendar-independent; an outage never darkens a today-fresh table. Consistent with the #158/#162 nav-gap precedent (calendar loss degrades only the calendar-dependent check); DARK instead of a coarser fallback is justified because no honest N exists and OD-1 gates factor-math eligibility on N.

**RD-4 — Fallback-merge poisoning guard chain verified.** Throttles classify TRANSIENT (`_is_blank_info_frame`) and return None from `cache_first_fetch`; `merge_seen` skips None/blank — only a shape-constrained parsed 行业 string can enter the store. Residual (wrong-but-parsed string shielded from fallback re-fetch while served): bounded by daily batch refresh-on-seen + ≤30 d expiry — accepted, made explicit in AC-6 with a `{sym: None}`-writes-nothing test.

**RD-5 — Calendar-days (store) vs trading-days (board-PE) consistent with CONTEXT.** Both freshness-state terms use trading days for their ≤3 windows; the 30-calendar-day store window is a different object (quasi-static attribute serve-while-stale). New CONTEXT term prevents conflation.

**RD-6 — P8c fits the capture wrapper's posture.** Protective-only 300 s watchdog, no page (`run-flow-capture.sh`); worst-case added board-PE time ≈ 203 s fits. The AFTER-the-flow-append ordering promoted to an explicit load-bearing requirement (watchdog kill loses only the refresh, never the flow row).

**RD-7 — Back-compat wording corrected.** The dict → `(table, BoardPeFreshness)` return-shape change breaks every `fetch_industry_pe` caller regardless of kwargs; the constraint now states precisely what is preserved (fetch/cache semantics sans `trading_days`; Q5 degrade; capture ignores the freshness half).

**RD-8 — Verifications with evidence.** trace.py:14-17 already reserves 004's field under schema "7"; `valuation_coverage_health` bare signature + bare `_compute_gates` call confirmed (additive kwarg sound); all cited monitor_cmd line anchors re-verified (219/329-330/905-907/1028/1127); `_drilldown_block` excludes `valuation_rollup_html` (Q12 TRUE); `drilldown_page_html` variable-length row pattern exists (AC-13); phase0's private `_parse_ulist` confirmed (Q11); `_provisional_flow_for_fund` top-5-only reads (Q14).

**RD-9 — Docs verdict.** ADR 0020 addendum written (hard-to-reverse data contract + surprising serve-while-stale-feeds-math divergence from flow's posture + real honest-age-vs-dark trade-off = three of three); CONTEXT term sharpening + new store term; no new ADR number (amends ADR 0020's existing subject).
