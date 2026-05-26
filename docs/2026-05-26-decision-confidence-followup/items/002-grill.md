Verdict: PASS

Subagent: opus
Questions resolved: 10
Docs touched:
  - CONTEXT.md (commit a389c94)
  - docs/adr/0002-active-fund-fetch-engine.md (commit a389c94)
Spec refined: items/002-spec.md (commit a389c94)

## Resolved decisions

- Q: Should `_QDII_ASSET_CLASSES` be consolidated across all three current call sites, or only the one the spec mentions?
  A: Consolidate across all three (`decision/gates.py`, `memo/diagnostics.py`, `allocation/target_weights.py`) into the new `src/irc/scoring/qdii_premium.py`. Type unified to `frozenset` per CLAUDE.md immutability.
  Rationale: Eliminate three-way duplication that can drift; honour CLAUDE.md immutability for shared constants.
  Doc impact: spec AC21 (new); no CONTEXT.md change (implementation detail).

- Q: Is `0.0` (rather than `None`) the right semantics for off-exchange QDII feeders?
  A: `0.0` is correct — off-exchange units transact at NAV by construction; secondary-market premium concept does not apply. `None` would falsely fire `qdii_premium_unknown`.
  Rationale: Domain truth: the field is known (zero by construction), not missing.
  Doc impact: CONTEXT.md "off-exchange synthetic-zero premium policy" bullet.

- Q: Is `基金折价率` ever positive (discount), and does the spec's "positive premium" assumption hold?
  A: YES — `基金折价率` is sometimes positive. Spec sign-flip formula `premium = -(基金折价率)/100` correctly yields a NEGATIVE premium in that case. AC1 rewritten to state premium is signed; gate comparison safe under either sign.
  Rationale: Math is correct; doc text was misleading.
  Doc impact: spec AC1 rewritten; CONTEXT.md "QDII premium-to-NAV ratio" pins signed semantics.

- Q: Is the spec's live-test double-gating explicit enough vs CONTEXT.md "Live test gate"?
  A: YES. AC12 names both `pytest.mark.live_akshare` AND module-level `pytest.mark.skipif(IRC_RUN_LIVE_AKSHARE != "1", ...)`. No change.
  Rationale: Already canonical.
  Doc impact: none.

- Q: Is the threshold default `0.03` too tight versus MASTER-SPEC's `0.05`?
  A: Raise to `0.05`. Matches MASTER-SPEC + CONTEXT.md "5–15% above NAV" mental model + opt-out-gate let-it-pass bias. 3-row sample is a single snapshot, not a distribution.
  Rationale: Bias toward let-it-pass for opt-out gates; align with existing operator framing.
  Doc impact: spec AC9 corrected (struck through + replacement); CONTEXT.md `qdii_max_premium_pct` bullet pins `0.05`; `QDII_MAX_PREMIUM_DEFAULT` constant added.

- Q: Does `lru_cache(maxsize=1)` introduce concurrency or test-isolation hazards?
  A: No concurrency hazard (single-process single-threaded). Test isolation requires `_fetch_full_etf_spot_table.cache_clear()` in fixture teardown — same pattern as existing `_fetch_full_fund_table.cache_clear()`.
  Rationale: Match established hygiene pattern.
  Doc impact: spec AC20 (new); CONTEXT.md `fetch_qdii_premium_pct` bullet pins cache_clear contract.

- Q: Naming consistency — should the magic default be a named `Final` constant like `FOREIGN_HEAVY_THRESHOLD`?
  A: YES. `QDII_MAX_PREMIUM_DEFAULT: Final[float] = 0.05` in `schemas/discovery.py`, referenced by `HardFilters.qdii_max_premium_pct = Field(default=QDII_MAX_PREMIUM_DEFAULT, ...)`. YAML key stays lowercase per existing config convention.
  Rationale: Mirror item 001's naming pattern; magic numbers get names.
  Doc impact: spec AC9 rewritten with constant; CONTEXT.md `qdii_max_premium_pct` bullet names the constant.

- Q: The existing `qdii_premium_unknown` remediation text mentions "premium / FX status" — still accurate after this item lands?
  A: No. Rewrite to clarify "unknown" now means "AkShare returned no row" (distinct from "too high") and drop the "FX status" half (out of V1 scope).
  Rationale: Operator-facing text must match new behaviour; preserve audit-trail clarity between the two QDII codes.
  Doc impact: spec AC22 (new).

- Q: Does the 2026-05-25 QDII fetch reform memory conflict with this item?
  A: No. The memory governs the opportunity-stage dual-coverage gate (fund-level NAV + announcements). This item governs the decision-stage `qdii_premium_pct` gate (scoring metric). Orthogonal axes; both can be true.
  Rationale: Two orthogonal gate axes; no contradiction.
  Doc impact: none required.

- Q: Is "no new ADR; CONTEXT.md addendum + ADR 0002 §5 cross-reference" the right docs surface?
  A: YES. Fetch pattern is textbook ADR 0002 §5; new gate code is a peer of an existing code — no new architectural ground. One-sentence cross-reference (now "F6 QDII premium-to-NAV fetcher" paragraph) suffices.
  Rationale: Match docs surface to architectural delta; new code = new bullet, not new ADR.
  Doc impact: ADR 0002 §5 amended with F6 paragraph; CONTEXT.md "QDII premium-to-NAV" section added.
