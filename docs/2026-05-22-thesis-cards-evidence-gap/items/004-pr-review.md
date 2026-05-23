Verdict: PASS-WITH-NITS

Source: /code-review on PR #58
PR comment URL: https://github.com/snowshine0216/investment-research-copilot/pull/58#issuecomment-4524188672
Findings: 2
  - tests/fundamentals/test_fund_announcement_em_live.py:202 — latent-bug — `assert first_date is not None` silently passes when AkShare returns pd.NaT (NaT is not None in Python); a NaT date would produce a silent false-PASS in the live gate under schema drift
  - tests/fundamentals/test_fund_announcement_em_live.py:199 — latent-bug — `str(first_title).strip() != ""` passes when title is np.nan because str(np.nan) == 'nan'; a NaN title column would silently pass the live gate assertion

## Review scope

Test-only sub-PR: pytest marker config + 2 test files (live + mocked companion) + run-discipline README + 10 fixture JSONs + 6 run-dir docs. Zero src/ changes.

## Angle summary

- Angle A (line-by-line): surfaced 2 confirmed latent bugs in `_assert_non_empty_df` (NaT date + NaN title checks). Same NaN blindspot exists in legacy `_assert_announcement_df` but companion tests use controlled DataFrames — PLAUSIBLE lower-severity.
- Angle B (removed-behavior): `--strict-markers` added with simultaneous registration of both `live_akshare` and `integration` markers; pre-existing `@pytest.mark.integration` usage in `test_thesis_coverage.py` is now properly covered. No dropped guards. All candidates REFUTED.
- Angle C (cross-file tracer): companion imports (`_assert_announcement_df`, `_call_fund_announcement_em`) all preserved. No call-site breaks. All candidates REFUTED.

## Confirmed clean

- Atomic fixture writes (mkstemp + os.replace): correct.
- json.dump with default=str correctly serialises datetime.date: verified.
- Aggregate gate catches AssertionError per-cell without short-circuiting: correct.
- All custom markers registered; no unregistered markers in test suite.

## Recommended fix (non-blocking)

Replace `assert first_date is not None` with `assert first_date is not None and not pd.isnull(first_date)`.
Replace title check with `assert pd.notna(first_title) and str(first_title).strip() not in ("", "nan")`.
