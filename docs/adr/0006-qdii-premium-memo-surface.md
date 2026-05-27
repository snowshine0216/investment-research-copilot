# ADR 0006 — QDII premium-to-NAV memo surface

**Status:** Accepted (2026-05-27, instrument-pickability run / item 003)
**Builds on:** [ADR 0001 — citation data model](0001-citation-data-model.md), [ADR 0002 §5 F6 — QDII premium-to-NAV fetcher](0002-active-fund-fetch-engine.md), [ADR 0004 — renderer determinism and alias policy](0004-renderer-determinism-and-alias-policy.md).
**Supersedes:** none.

## Context

The QDII premium-to-NAV fetcher (`fetch_qdii_premium_pct`), the scoring-layer routing helper (`qdii_premium_for_row`), and the decision-stage blocking gate (`qdii_premium_too_high` in `decision/gates.py`) were all built in the 2026-05-26 decision-confidence-followup run (ADR 0002 §5 F6). `outputs/2026-05-27/scoring.json` already carries `qdii_premium_pct` for every QDII row: `513690` at `-0.0034`, off-exchange feeders at synthetic `0.0`, and three watched-not-picked rows (`159941`, `513300`, `159501`) above the 5% threshold.

Yet `outputs/2026-05-27/memo_blocked.md` §6 still reads: `溢价/折价：数据未采集——请在交易前查阅各 QDII 二级市场溢价。` The fetcher works; the memo doesn't read it. The user sees "no data" while the data sits in `scoring.json`.

Closing this loop is **memo-rendering only** — no new fetcher, no new live-test surface, no allocation change. But the rendering surface has four real choices, each non-obvious and expensive to walk back:

1. **Picks-table column-add vs cell-overload.** A new `溢价` column extends the picks-table from 12 → 13 columns and forces a lockdown fixture migration. The alternative — overloading the existing 触发状态 column — would conflate "data availability" with "trigger-rule evaluation."
2. **Top-level artefact vs `data/` subdirectory.** A new derived JSON file establishes an output contract for downstream tooling. Top-level placement matches sibling artefacts (`scoring.json`, `opportunity_report.json`, …); `data/` placement would group it with the DuckDB cache.
3. **Off-exchange rendering — `—` vs `0.00%（场外申赎）`.** The synthetic-zero from off-exchange QDII feeders is economically correct but visually identical to "happened to be 0% on-exchange today." The disambiguation channel is the cell suffix.
4. **§7 hard-block surface — column glyph vs line prefix.** The §5 触发状态 column is reserved for `trade_plan.yaml::trades[*].triggers` (price/drawdown conditions). The §7 execution line is the canonical "should I even be looking?" surface.

This ADR locks all four. Reviewers reading any of `memo/picks_table.py`, `memo/qdii_premium_lines.py`, or the §7 execution-line composition six months from now should land here first.

## Decision

### 1. New `溢价` column in §5 picks-table — extend the lock to 13 columns

Insert `溢价` between `单次定投上限` and `触发状态`. The new column header is exactly two CJK characters (`溢价`); cell renderer is the pure helper `_format_qdii_premium_cell(pick: PickRow) -> str`:

| Cell input | Renders as |
|---|---|
| `qdii_premium_pct is None` (non-QDII) | `—` |
| `qdii_premium_pct == 0.0` AND `asset_class ∈ {us_etf, hk_etf, qdii_global}` | `0.00%（场外申赎）` |
| `qdii_premium_pct > 0` (on-exchange premium) | `+{pct:.2f}%` |
| `qdii_premium_pct < 0` (on-exchange discount) | `-{pct:.2f}%` |
| `qdii_premium_pct == 0.0` AND non-QDII (defensive only — structurally impossible) | `—` |

`pct = qdii_premium_pct * 100`. Sign is always rendered for the non-zero on-exchange branches so the operator never mistakes premium for discount.

The previous run's item 003 (decision-confidence-followup) locked a 12-column picks-table contract. This ADR **extends** the lock to 13 columns and amends the lockdown fixture in the SAME commit as the production code — no two-step migration. The existing test `tests/memo/test_picks_table.py::test_picks_table_header_contains_tranche_cap_and_trigger_status_columns` (lines 285–301) asserts `cols.index("触发状态") == cols.index("单次定投上限") + 1`; this assertion is migrated to walk through `单次定投上限 → 溢价 → 触发状态 → 证据` (3 increments) in the same commit.

The 溢价 column emits no `[ref:...]` markers (the cell is data-only; the underlying citation is the scoring snapshot already linked in the 证据 cell). The SAME-3 invariant from ADR 0004 is preserved — citation_ids in picks-table 证据 / evidence-pool / discipline render unchanged.

**Trade-off considered:**
- *Alternative*: overload the existing 触发状态 column with a 溢价 glyph (e.g. `溢价 ✓ / ✗ / ⚠`). Rejected — `触发状态` is reserved for `trade_plan.yaml::trades[*].triggers`. Overloading conflates "data availability" with "rule evaluation" and forces operator-facing wording to disambiguate two distinct workflows.
- *Alternative*: render a separate row beneath each QDII pick. Rejected — breaks the single-line-per-row markdown contract from the previous run's item 002.

### 2. New top-level projection artefact `outputs/<date>/qdii_premium.json`

Written by `src/irc/memo/qdii_premium_lines.py::write_qdii_premium_snapshot` via the existing `atomic_write_text` (`.tmp.{pid} → os.replace`) pattern. Schema:

```json
{
  "generated_at": "2026-05-27T15:30:00+08:00",
  "threshold_pct": 0.05,
  "evidence_cutoff": "2026-05-26",
  "rows": [
    {
      "instrument_id": "513690",
      "name_cn": "港股红利ETF博时",
      "asset_class": "hk_etf",
      "market": "cn_on_exchange",
      "qdii_premium_pct": -0.0034,
      "blocking": false,
      "render_cell": "-0.34%"
    }
  ]
}
```

**Pure projection** — every value derives from `scoring.json` rows already in scope at memo time + the memo's pick set; nothing is re-fetched. AkShare is never called from this writer.

`rows` sorted by `instrument_id` ASC for determinism. `blocking = (qdii_premium_pct is not None) AND (qdii_premium_pct > threshold_pct)`. Coverage includes ALL premium-bearing rows from `scoring.json` (picks AND watched-not-picked) so a follow-up discipline-report item can promote watched symbols without re-engineering.

**Always-written invariant** — the file is written every memo run, even when zero QDII rows exist (empty `rows: []`). The empty file is the signal of "no QDII this week," not a skip. A missing file is therefore a build error and is detectable as such.

`generated_at` uses a `now_fn: Callable[[], datetime]` parameter so tests can stub the clock; production passes `lambda: datetime.now(timezone(timedelta(hours=8)))` (UTC+8 ISO string). `evidence_cutoff` is computed via the existing `extract_evidence_cutoff` helper over the same refs scoring already used — NOT a fresh wall-clock read. Two consecutive memo runs over identical scoring inputs produce byte-identical `qdii_premium.json`.

**Trade-off considered:**
- *Alternative*: write under `outputs/<date>/data/qdii_premium.json`. Rejected — `data/` is reserved for the discovery / DuckDB cache, not memo-stage outputs. Every other memo/opportunity artefact (`scoring.json`, `opportunity_report.json`, `proposed_allocation.yaml`, `trade_plan.yaml`, `gold_regime.json`, `thesis_cards.yaml`, `memo.md`, `rejections.json`, `citation_audit.json`) lives at top level. Following the convention is more discoverable.
- *Alternative*: emit only when ≥1 QDII row exists. Rejected — a missing file becomes ambiguous ("no QDII this week" vs "memo stage crashed"); the always-written invariant makes monitoring deterministic.

### 3. Off-exchange rendering — explicit `0.00%（场外申赎）` suffix

Off-exchange QDII feeders (open-ended LOF / FOF units) transact at NAV by construction. `qdii_premium_for_row` returns the synthetic `0.0` (per CONTEXT.md "Off-exchange synthetic-zero premium policy"). The picks-table cell renders `0.00%（场外申赎）` — `0.00%` is the economically-correct value; `（场外申赎）` is the disambiguation channel.

**Trade-off considered:**
- *Alternative*: render `—` for off-exchange (same as non-QDII). Rejected — would imply "data missing" and trigger operator anxiety, while in fact the value IS known (NAV-tracking by structural design). The fetcher correctly distinguishes; the cell must too.
- *Alternative*: render bare `0.00%` (no suffix). Rejected — visually identical to an on-exchange QDII that happens to trade at NAV on the snapshot day. The suffix is the only signal that distinguishes structural NAV-tracking from a same-day coincidence.

### 4. §7 hard-block surface — line prefix, not column glyph

For each QDII pick whose `qdii_premium_pct > QDII_PREMIUM_THRESHOLD_PCT`, the §7 execution-line bullet is prefixed with `⛔ qdii_premium_too_high（{render_cell} > {threshold_pct*100:.0f}%，已暂缓）｜` followed by the existing target-weight / 建仓方式 / 触发 string verbatim. The prefix is **prepended at `commands/memo_cmd.py::_compose_execution_lines` (or its caller)** where the projection rows are already in scope — `template.py::_render_execution_section` stays a pure shape renderer over strings (FP "effects at edges").

The §6 风险提示 line block uses the same threshold value via `QDII_PREMIUM_THRESHOLD_PCT` (re-exported `= QDII_MAX_PREMIUM_DEFAULT`), wrapped in `IRC_QDII_PREMIUM_BEGIN/END` markers per the existing 6-marker-pair convention. Empty-projection case → no marker block; `compose_fx_qdii_lines` returns the legacy "数据未采集——请在交易前查阅各 QDII 二级市场溢价。" placeholder.

The §5 触发状态 column is intentionally NOT modified — that column remains glyph-encoded (`✓ ✗ ⚠`) and bound to `trade_plan.yaml` trigger evaluation.

**Trade-off considered:**
- *Alternative*: a new glyph in the 触发状态 column (e.g. `⛔` for "blocked-by-premium"). Rejected — adds a new glyph to the column vocabulary, conflates two operator workflows ("when will this fire?" vs "should I even be looking?"), and silently breaks downstream tools that parse the 触发状态 column as `{✓,✗,⚠}` only.
- *Alternative*: render the §7 prefix inside `template.py`. Rejected — would push premium-awareness into the pure shape renderer; `template.py` would need to import projection types. The composition belongs at the memo_cmd edge where the projection is built.

## Identifier unification — reuse `qdii_premium_too_high`

This ADR does NOT introduce a `qdii_premium_high` synonym. The existing `qdii_premium_too_high` from `decision/gates.py::compute_blocking_reasons` is the canonical name; it appears in:

- `decision/gates.py` (the gate computation)
- `decision/report.py::_BLOCKING_REASON_LABEL` and `_BLOCKING_REMEDIATION` (operator-facing strings)
- CONTEXT.md "QDII premium-to-NAV"
- the new §7 prefix (this ADR)
- the new `qdii_premium.json::rows[*].blocking` flag (this ADR)

A separate `qdii_premium_high` synonym would force every caller to handle both names, double-document remediation text, and risk drift. A grep over `src/irc/` for the literal token `qdii_premium_high` must return zero matches.

## Consequences

**Positive:**
- The memo §5 picks-table makes the existing `scoring.json::qdii_premium_pct` visible to the operator without leaving the memo.
- The §6 marker block discloses the freshness of the snapshot (`数据截止 {evidence_cutoff}`) so the operator knows AkShare's `fund_etf_spot_em` close-of-day snapshot may be stale intraday.
- The §7 prefix gives an explicit "暂缓执行" signal adjacent to the actual execution instruction, not buried in a separate column.
- The `qdii_premium.json` artefact is the single canonical surface a follow-up discipline-report item can promote watched-not-picked above-threshold symbols from — no re-engineering needed.
- The 13-column lock + lockdown-fixture migration in one commit closes the loop atomically — no inconsistent intermediate state.

**Negative:**
- Picks-table is now noticeably wider; rendering on narrow terminals will wrap. Acceptable — the markdown contract is the deliverable, not terminal-width fidelity.
- The lockdown fixture in `tests/memo/test_picks_table.py` and (any downstream callers of the picks-table column-order assertion) must migrate; reverting the column-add requires a second migration.
- The `qdii_premium.json` always-written invariant adds one write per memo run even on weeks with no QDII candidates. Acceptable — the file is < 200 bytes when empty.

**Defensive scope:**
- No allocation change (`trade_plan.yaml` target weights are not softened for above-threshold QDII; that's a separate allocation-time concern).
- No discipline-report rendering for watched-not-picked above-threshold symbols (the artefact carries them; the follow-up item picks them up).
- No back-fill of historical `outputs/<date>/memo.md` files (behaviour applies from the next memo run forward).
- No new live-test surface (the existing `fetch_qdii_premium_pct` live test stays as-is per CONTEXT.md "Live test gate").
- No change to `qdii_premium_unknown` semantics — when a QDII row's `qdii_premium_pct is None` (AkShare fetch failed), the cell renders `—`, the §6 marker block omits that row, and the §7 prefix is NOT applied. The existing `qdii_premium_unknown` blocking-reason continues to fire in the decision stage.

## Related

- [ADR 0001 — citation data model](0001-citation-data-model.md): `citation_id` format unchanged; the new column and §6 block emit no `[ref:...]` markers.
- [ADR 0002 §5 F6](0002-active-fund-fetch-engine.md): the QDII premium-to-NAV fetcher that produces the `qdii_premium_pct` field this ADR renders.
- [ADR 0004 — renderer determinism and alias policy](0004-renderer-determinism-and-alias-policy.md): SAME-3 invariant; the new column carries no citation_ids, so the invariant is preserved by construction.
- CONTEXT.md "QDII premium-to-NAV" — the four canonical terms (`QDII premium-to-NAV ratio`, `fetch_qdii_premium_pct`, off-exchange synthetic-zero policy, `qdii_premium_too_high`, `qdii_max_premium_pct`) plus the four new entries this ADR introduces (`QDII_PREMIUM_THRESHOLD_PCT`, 溢价 column, `qdii_premium.json` projection, `IRC_QDII_PREMIUM_BEGIN/END` marker).
- `docs/2026-05-27-instrument-pickability/items/003-spec.md`: the implementation spec this ADR governs.
