# MASTER-SPEC — Decision Confidence Followup

**Mode:** backlog
**Date:** 2026-05-26
**Source:** `/tmp/handoff-2026-05-26-decision-confidence.md`
**Base branch:** main (protected) → synthesized feature branch `autodev/decision-confidence-followup-feature`
**PR shape:** A (per-item PRs into the feature branch)
**Project type:** non-web (Python CLI — `irc`)

## IN-scope items

| id  | Title                                                | Source item | Effort | Priority |
|-----|------------------------------------------------------|-------------|--------|----------|
| 001 | Foreign-fund Policy B relaxation (unblock 006809)    | handoff #2  | M      | 1        |
| 002 | QDII premium-to-NAV fetcher (unblock 8 instruments)  | handoff #3  | M      | 2        |
| 003 | Mirror Decision Sheet into memo §5 picks table       | handoff #4  | S      | 3        |

### 001 — Foreign-fund Policy B relaxation

**Goal.** When a fund's top-N constituent weight is ≥ 50% non-CN-listed, accept fund-level NAV + announcements as the data leg instead of requiring per-holding filings. Mirrors the 2026-05-25 QDII fetch reform (memory: `project_qdii_fetch_reform.md`).

**Why now.** 006809 is currently labeled `blocked / opportunity_excluded` with a remediation pointer, but the underlying gate still rejects it. `outputs/2026-05-26/rejections.json` shows: `data leg missing for 10 of 10 holdings: ['00005', ...]`.

**Files to touch.**
- `src/irc/opportunity/policy_b.py` — `evaluate_policy_b`: add new precedence rule between current rules 2 and 3 that short-circuits to `gap_codes=()` when foreign-share ≥ threshold AND fund-level NAV+announcement evidence is present.
- `src/irc/commands/opportunity_cmd.py` lines 952–982 — review dispatch between `ActiveFundSnapshot` (Policy B) and `FundLevelSnapshot` (skip-Policy-B, QDII reform).
- `src/irc/fundamentals/types.py` lines 226–305 — confirm snapshot dataclasses expose what's needed.
- `tests/opportunity/test_policy_b.py` — TDD: failing test first.

**Acceptance criteria.**
- New precedence rule lands in `evaluate_policy_b` and is unit-tested for the foreign-share ≥ threshold path.
- 006809 (or a representative fixture mirroring it) is accepted by Policy B with `gap_codes=()` after the change.
- All existing Policy B tests stay green.
- ADR 0003 (or a new ADR) updated to reflect the relaxation; CONTEXT.md "Failure-mode + audit policy" rewording if needed.

**Approach (not prescribed).** Add `_infer_exchange`-style aggregation in Policy B to compute foreign-listed weight share from constituent exchange codes, then a new precedence rule (`rule_2_5`) between current rules 2 and 3.

### 002 — QDII premium-to-NAV fetcher

**Goal.** Wire an akshare premium-to-NAV fetcher into the scoring pass so QDII feeder ETFs no longer block on `qdii_premium_unknown`. Block only when premium > threshold OR data missing.

**Why now.** The largest remaining blocked bucket — 8 instruments today (517641, 019172, 161716, 159691, 513690, 513650, 016452, 019547) — all have `qdii_premium_unknown` as their sole blocking reason.

**Files to touch.**
- `src/irc/data/akshare_client.py` — new fetcher wrapping `fund_etf_fund_info_em(symbol)` (exposes `溢价率` / `折价率`). Same indirection pattern as `fetch_macro_series_akshare`.
- `src/irc/scoring/` — populate `qdii_premium_pct` on the score row for QDII fund/ETF rows.
- `src/irc/commands/score_cmd.py` — wire the fetcher in.
- `src/irc/decision/gates.py:128` — already reads `score.get("qdii_premium_pct")`; confirm gate path with new threshold.
- `config/discovery.yaml` — new knob `qdii_max_premium_pct: 0.05` (or similar).
- `tests/scoring/test_qdii_premium.py` — new test file (TDD).
- `tests/data/test_akshare_client.py` — test the new fetcher (with stubbed akshare).

**Acceptance criteria.**
- New akshare fetcher returns the premium-to-NAV percentage for a QDII ETF symbol (live test double-gated per CONTEXT "Live test gate").
- Scoring pass populates `qdii_premium_pct` for QDII rows.
- Gate blocks only when `premium > qdii_max_premium_pct` OR premium data missing — not when premium is healthy.
- Default threshold lives in `config/discovery.yaml`; pydantic-settings reads it through normal channels.
- `config validate` passes; full pipeline can run end-to-end.
- ADR addendum or CONTEXT.md note if QDII premium semantics affect downstream gates.

### 003 — Mirror Decision Sheet into memo §5 picks table

**Goal.** Add `单次定投上限` and `触发状态` columns to memo §5 picks table so a reader of just `memo.md` sees per-tranche caps and current trigger state. Pure renderer.

**Why later (but in-scope).** Polish, but small surface and uses existing helpers (`irc.decision.sizing.suggest_tranche_pct` + `format_why_when_line`). Worth shipping to close the visibility gap between `decision_report.md` and `memo.md`.

**Files to touch.**
- `src/irc/memo/picks_table.py` — `PickRow` dataclass + `render_picks_table`. Add the two new columns; populate via existing helpers.
- `tests/memo/test_picks_table.py` (or equivalent) — TDD for the new columns and their formatting.

**Acceptance criteria.**
- Memo §5 picks table includes `单次定投上限` and `触发状态` columns for every actionable pick.
- Renderer reuses `suggest_tranche_pct` and `format_why_when_line`; no duplicate sizing logic.
- Output is deterministic (no random ordering or float drift).
- Existing memo snapshot tests updated to reflect new columns.

## OUT-of-scope items

See [SKIPPED.md](SKIPPED.md).

## Tripwires (from handoff)

- `inputs/account.yaml` has TWO accounts — read it before assuming venue capability.
- `outputs/` and `data/` are gitignored — never `git add` them.
- `decision_sheet.md` was a manual one-shot; pipeline now generates the equivalent inside `decision_report.md`. Don't recreate it.
- TDD enforced — failing test before implementation.
- `基金概况` indicator forbidden in production fetch code (CLAUDE.md).
- Memory: `project_qdii_fetch_reform.md` (2026-05-25 QDII fetch reform) — Item 001 mirrors that reform's design.
- Memory: `project_memo_macro_evidence_pillar.md` (2026-05-25) — memo §2/§3 already consume macro_series + theme reports through `gold_regime.json["evidence"]`; Item 003 is §5 only.
