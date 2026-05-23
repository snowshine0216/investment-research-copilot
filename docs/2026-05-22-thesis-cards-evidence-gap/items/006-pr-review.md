Verdict: PASS (post-fix)

Subagent: claude-sonnet-4-6 (code-review skill, effort=max, 3-angle × verify)
PR: https://github.com/snowshine0216/investment-research-copilot/pull/60
Base: autodev/thesis-cards-evidence-gap → 19 commits (16 impl + 1 ruff cleanup + 1 ship-blocked docs + 3 fix-round commits)

---

## High-confidence bugs

None confirmed. One latent/plausible finding below.

---

## Likely bugs (PLAUSIBLE — latent crash path)

### L1 — `missing_us_news_adapter` declared in `RejectionReasonCode` Literal but absent from `_GAP_TO_REASON` keys

**File:** `src/irc/opportunity/rejection_log.py:23–32` (Literal) vs `61–85` (`_GAP_TO_REASON`)  
**Severity:** Latent P0 (crash on first use)

`RejectionReasonCode` includes `"missing_us_news_adapter"` (spec marker `# H4 systematic-exclusion sub-class`). However, `_GAP_TO_REASON` has no entry with key `"missing_us_news_adapter"`, so no evidence-gap code can map to it. If any future code path (including the H4 US-adapter work planned for a subsequent item) stamps `evidence_gaps=("missing_us_news_adapter",)` on a row, `_classify_rejection_reason` will raise `RuntimeError("unknown evidence_gap code: 'missing_us_news_adapter'")` and halt the entire opportunity run.

**Failure scenario:** item 008/009 adds a code path that emits `"missing_us_news_adapter"` as an evidence-gap code on US-heavy active-fund rows → first production run with that code crashes `_write_opportunity_outputs` before writing any output files.

**Fix path:** add `"missing_us_news_adapter": "missing_us_news_adapter"` to `_GAP_TO_REASON`, or add a CI check that verifies every `RejectionReasonCode` Literal value appears as a `_GAP_TO_REASON` value.

**Note:** criterion 19's test only checks that 7 core codes appear in `_GAP_TO_REASON.values()`; it does not assert that all Literal members are reachable.

---

## Nits

### N1 — criterion-18 format-regex test is over-strict for names with spaces

**File:** `tests/opportunity/test_failure_renderer.py:94`  
Pattern `r"^- \*\*\S+ \S+\*\* ｜ 原因: .+ ｜ 已尝试: .+$"` uses two `\S+` tokens separated by a single space, which requires `name_cn` to be a single non-whitespace token. Chinese fund names typically don't contain spaces, but the production format string (`f"- **{r.instrument_id} {r.name_cn}**"`) is correct for any name. The test fixture uses `name_cn="易方达蓝筹精选"` (no space) so this goes undetected. A name like `"华夏 蓝筹"` would cause the test to fail even though the produced output is perfectly valid. The regex should use `.+` instead of `\S+` for the name portion: `r"^- \*\*\S+ .+\*\* ｜ 原因: .+ ｜ 已尝试: .+$"`. Production behaviour is unaffected.

### N2 — P0-1 regression test covers only one ordering of mixed-known/unknown gaps

**File:** `tests/opportunity/test_rejection_log.py:370–376`  
Only `("unknown_synthetic_gap", "holdings_fetch_failed")` (unknown first) is tested. The reverse `("holdings_fetch_failed", "unknown_synthetic_gap")` (known first) is not. The code is correct for both orderings (pre-scan validates all gaps before returning), so this is a test-coverage gap rather than a code bug. Verified by manual execution.

---

## Notes (observations; no action required)

- **`evaluate_policy_b` with empty `constituent_analyses=()`:** Rule 1 fires when `not analyses AND fund_level_failure_reasons` (returns `holdings_fetch_failed`). The defensive guard fires when `not analyses AND NOT fund_level_failure_reasons` (returns `incomplete_constituent_record` + audit_error). Both paths tested; behavior is correct and matches ADR 0003 §1.

- **`record_fund_rejection` with `snapshot=None`:** `constituent_coverage=()`, `fund_level_failure_reasons=()`. Correct for non-active-fund rows. Documented in function docstring.

- **`_classify_rejection_reason` determinism:** Iterates `row.evidence_gaps` in row order; first match wins. Policy B appends gap_codes to the END of `row.evidence_gaps + verdict.gap_codes`, so pre-existing QDII/NAV codes (stamped earlier) always precede Policy B codes. QDII precedence over Policy B is guaranteed by construction. No duplicate gap codes can arise because `build_opportunity_row` / `states.py` emit no Policy B gap codes (confirmed by grep).

- **`rejections.json` schema:** Matches plan's locked JSON shape exactly. `audit_errors` per `ConstituentCoverageEntry` (from `_build_coverage_entries` / rule-2 `audit_overrides`). Verdict-level `audit_errors` (e.g. `empty_constituent_analyses_without_failure_reason`) are NOT in the JSON — this is by design; they propagate only into `constituent_coverage[i].audit_errors` for rule 2, and are implicit in `rejection_reason` for the defensive-guard path.

- **Test isolation:** All new tests write to `tmp_path` (pytest fixture, auto-cleaned). `monkeypatch.setenv` in two new tests auto-reverts. No manual `os.environ` mutations. No writes to `outputs/` outside `tmp_path`.

- **`render_v1_systematic_exclusion_summary` count derivation:** Count is derived directly from `rejection_doc.entries` (filtered by `rejection_reason == "insufficient_info_coverage_top_half"` + `_is_us_heavy`). No separate tally; cannot drift from `rejections.json` by construction. The `missing_us_news_adapter` scenario from the scrutiny prompt would be a crash before reaching V1 summary (see L1 above), not a silent drift.

- **3 fix-commit regressions (P0-1 / P0-2 / P1-1):** The fixes are correct and complete for their stated scope. P0-1: strict pre-scan validates ALL gaps before returning. P0-2: `plan_hash` + `snapshot_cache_by_instrument` correctly threaded through `run_opportunity → _write_opportunity_outputs`. P1-1: 6 legacy gap codes added to `_GAP_TO_REASON` with correct mappings; covered by parametrized regression test.

- **Rule 5 structural unreachability:** Correctly documented (`only_failure` requires `evidence==()`, which triggers rule 3 first). `pytest.skip` is the right choice; the xfail test comment accurately explains the V1 invariant.

- **`_apply_reduction` silent evidence_gaps loss (inline review latent #1):** Still present. Out of scope for this /code-review pass; already captured in `006-review.md` with fix-path guidance.

- **`_classify_rejection_reason` misleading empty-gaps message (inline review latent #2):** Still present. Out of scope; already captured in `006-review.md`.

---

## What the inline review missed

1. **L1** — `missing_us_news_adapter` Literal/`_GAP_TO_REASON` inconsistency: the inline review checked `_GAP_TO_REASON` completeness only for legacy gap codes that were actively emitted (P1-1 scope). It did not check that all `RejectionReasonCode` Literal members are reachable via `_GAP_TO_REASON`. This is the one new finding this pass adds.

2. **N1** — criterion-18 format-regex brittleness with spaced names: the inline review confirmed the regex test passes but did not probe the fixture's name against the regex with a space variant.

## What the inline review already caught (not re-flagged)

- `_apply_reduction` ignoring `evidence_gaps` (latent #1 in `006-review.md`)
- `_classify_rejection_reason` misleading empty-gaps message (latent #2 in `006-review.md`)
- 7-tuple return smell (nit #3 in `006-review.md`)
- P0-1 / P0-2 / P1-1 blockers (all closed via fix commits)

---

## Fix round 2 (post-/code-review, pre-merge)

Closed:
- L1: df0d86d — _GAP_TO_REASON covers missing_us_news_adapter forward-declared code
- Nit-1: d8f2e19 — parametrized mixed known/unknown ordering
- Nit-2: 329026e — criterion-18 regex / fixture supports name_cn with spaces

Final verdict: PASS (all findings closed).
