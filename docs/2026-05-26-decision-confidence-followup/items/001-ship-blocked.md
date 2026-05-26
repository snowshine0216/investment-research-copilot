# Ship blocked — item 001 (round 1)

Source: `/ship` steps 8 (pre-landing review) + 9 (adversarial review).
PR not yet opened — fix these blockers and re-invoke `/ship`.

## P0 — must fix before landing

### P0-1 · FetchPlan.total_calls() undercount (in-branch)

File: `src/irc/commands/opportunity_cmd.py:97`

`per_active = 1 + self.top_n * 3` doesn't account for the new fetches added by item 001 in `_fetch_active_fund_level_evidence`:
- `fetch_fund_nav_report` → 1 `_ak_call` (`fund_open_fund_info_em`)
- `fetch_fund_announcements` → 3 `_ak_call`s (`fund_announcement_dividend_em`, `fund_announcement_report_em`, `fund_announcement_personnel_em`)

**Delta:** +4 calls per active fund (miss or stale).

The pre-fetch budget guard at line 841 silently underestimates cost by `4 × (active_fund_misses + active_fund_stale)`. With 50 active funds this is 200 untracked calls.

**Fix:** change line 97 to `per_active = 1 + self.top_n * 3 + 4  # +4 = 1 NAV + 3 announcement endpoints (item 001)`.

Update existing tests in `tests/commands/test_opportunity_cmd.py`:
- Line 410: `5 × (1 + 10*3 + 4)` = `5 × 35` = **175** (was 155)
- Line 420: `(2+3) × 35 + 4×2 + 1×2` = `175 + 10` = **185** (was 165)
- Update the inline comments on lines 410 and 420 accordingly.

Also check `test_fetch_budget_exceeded_carries_breakdown` at line 424 — `total=155` parameter is just a string-formatted display, not asserted as computed, so may not need updating. Read first; only update if asserted.

### P0-2 · Dead outer try/except in `_fetch_active_fund_level_evidence` masks failure type (in-branch)

File: `src/irc/fundamentals/snapshot.py:460-486`

Both `fetch_fund_nav_report` and `fetch_fund_announcements` are documented "Never raises" / "degrade-to-None". The outer `try: ... except Exception as exc:` blocks at lines 460-464 and 480-486 are unreachable — `fund_nav_fetch_failed:...` and `fund_announcements_fetch_failed:...` codes can never be emitted.

This causes two related defects:
1. **Misleading failure code.** When NAV fetch fails (e.g. AkShare schema mismatch returning `None`), the failure is recorded as `fund_nav_unavailable:{fund_id}` — indistinguishable from genuinely-empty NAV data.
2. **Dead code.** Confuses readers about the error contract.

**Fix:** Remove the outer `try/except Exception as exc:` blocks. Inline the calls:

```python
nav = fetch_fund_nav_report(fund_id)
if nav is not None:
    evidence.append(ThesisEvidence(... existing ...))
else:
    failures.append(f"fund_nav_unavailable:{fund_id}")

anns = fetch_fund_announcements(fund_id)
if anns:
    for a in anns[:_FUND_LEVEL_INFO_CAP]:
        evidence.append(ThesisEvidence(... existing ...))
else:
    failures.append(f"fund_announcements_unavailable:{fund_id}")
```

Behavior is unchanged for the happy path; the only difference is that the dead `fund_nav_fetch_failed:*` / `fund_announcements_fetch_failed:*` codes are removed from the lexicon. **Search the codebase + tests for those string literals before removing** — if any test asserts them, that test must be deleted or rewritten (those codes were never reachable, so any such test was incorrectly testing dead code).

## P1 — latent bugs worth fixing in this PR

### P1-1 · Fragile `decision_rule.startswith("foreign-heavy")` discriminator

File: `src/irc/commands/opportunity_cmd.py:1112` and `src/irc/opportunity/policy_b.py` (`PolicyBVerdict` + `evaluate_policy_b` rule 2.5 path)

`_stamp_fund_level_evidence_from_verdict` discriminates rule 2.5 verdicts via `verdict.decision_rule.startswith("foreign-heavy")`. `decision_rule` is a free-text string. A typo or reformat of the rule 2.5 message would silently disable evidence stamping for ALL rule 2.5 verdicts on that run — funds pass Policy B but the dual-coverage gate then blocks them with no diagnostic.

**Fix:** Add a structural discriminator to `PolicyBVerdict`:

```python
@dataclass(frozen=True)
class PolicyBVerdict:
    gap_codes: tuple[str, ...]
    audit_errors: tuple[str, ...]
    decision_rule: str
    material_symbols: tuple[str, ...]
    constituent_coverage: tuple[ConstituentCoverageEntry, ...]
    fired_rule: str = ""  # new: "1", "2", "2.5", "3", "4", "5", or "" for default
```

Populate `fired_rule` in `evaluate_policy_b` at each rule's emit point. Update `_stamp_fund_level_evidence_from_verdict` to check `verdict.fired_rule == "2.5"` instead of the `startswith` match. Existing tests should keep passing — `fired_rule` defaults to `""` so callers that don't read it aren't affected.

Add one new test in `tests/opportunity/test_policy_b.py`:
```python
def test_evaluate_policy_b_rule_2_5_sets_fired_rule_literal() -> None:
    """Rule 2.5 verdict carries `fired_rule="2.5"` for structural discrimination."""
```

Also add a test in `tests/commands/test_opportunity_cmd.py` (or wherever `_stamp_fund_level_evidence_from_verdict` is currently tested) that constructs a `PolicyBVerdict` with `fired_rule="2.5"` and verifies stamping; and one with `fired_rule="3"` and verifies skip.

## P2 — defer to followup (note in PR body, do NOT fix here)

- `_EXCHANGE_FROM_SYMBOL_PREFIX` missing `"5": "SH"` (Shanghai-listed ETFs like `510300`). Conservative under-count only — never causes incorrect publish. Low impact.
- Mixed-fund stale cache with `fund_level_evidence=()` not force-retried by `_active_snapshot_has_required_data_leg_gap`. Fund stays blocked for up to one cache-freshness cycle (default 7 days) until a full refetch is triggered. Worth a separate followup item: add a freshness probe for `fund_level_evidence == () AND any CN constituent passes data leg check AND foreign-heavy threshold met`. Out of scope here.
- `_ak_call` has no timeout enforcement. Pre-existing; +4 calls per active fund increases exposure but doesn't change the underlying issue. Document under "Coverage notes" in the PR body.

## Verification commands after fix

```bash
uv run pytest tests/opportunity/ tests/fundamentals/ tests/commands/test_opportunity_cmd.py -q
uv run ruff check src tests
```

Then re-invoke `/ship`.
