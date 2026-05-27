Verdict: PASS

Source: /ship steps 8+9
PR: https://github.com/snowshine0216/investment-research-copilot/pull/78

## Step 8 — pre-landing parallel review

### Subagent 1: pr-review-toolkit:code-reviewer

Findings (0 P0, 2 P1):

1. **P1 — Hardcoded absolute cwd in AC13 test** (`tests/commands/test_memo_cmd.py:262`)
   - `cwd="/Users/snow/Documents/Repository/investment-research-copilot"` would fail on any other machine/CI runner. Adversarial elevated this to P0.
   - **Fixed in commit `b509385`**: `Path(__file__).resolve().parents[2]`.
2. **P1 — No boundary test for premium == exactly 5.0% (strict-`>` semantic)** (`tests/memo/test_qdii_premium_lines.py`)
   - Future refactor to `>=` would silently change semantics; no regression lock.
   - **Fixed in commit `b509385`**: `test_project_row_exactly_threshold_5pct_does_not_block` + `test_project_row_just_above_threshold_does_block`.

Notes: Data flow through all four paths (§5 cell / §6 marker block / §7 prefix / projection JSON) is correct, no silent `None` drop. H3 invariant untouched. Citation IDs untouched. No double-dash markdown issue (sub-string inside a single risk_notes entry, not raw risk_notes lines).

### Subagent 2: pr-review-toolkit:silent-failure-hunter

Findings (0 P0, 2 P1, 4 P2/Notes):

1. **P1 — `_coerce_premium` + duplicate `_coerce_optional_float` pass `nan`/`inf` through**
   - `nan > THRESHOLD` evaluates `False`, silently bypassing the §7 hard-block; renders `"nan%"` in §5 + emits literal `NaN` (invalid per RFC 8259) in `qdii_premium.json`.
   - **Fixed in commit `b509385`**: `math.isfinite` guard at both call sites with matching docstring so the two paths stay aligned. 3 new regression tests.
2. **P1 — Two coerce paths duplicated**
   - Functional drift risk if one is later strengthened.
   - **Accepted**: docstring at both sites now explicitly references the other, future drift will be caught in code review.
3. **P2 (notes)**: `generated_at` non-determinism (documented in artifact + plan; not in two-run byte-equality scope), §7 double-prefix risk (analyzed — prefix is rebuilt per call from raw trade dict, no accumulation), empty-case projection (`{}` with metadata correct), legacy fallback placeholder.

## Step 9 — adversarial review

Initial verdict: BREAKS (1 P0 + 1 P1 + 4 CLEAN + 1 P2).

1. **P0 — Hardcoded absolute cwd at `tests/commands/test_memo_cmd.py:262`**
   - Adversarial classified this as P0 (CI-fatal) rather than P1 (the code-reviewer's grade): subprocess.run with non-existent cwd raises FileNotFoundError or returns `returncode=2` (grep error in non-existent dir) — neither equals the asserted `returncode==1`. AC13 unverified on CI; suite green on dev only.
   - **Fixed in commit `b509385`**: see code-reviewer P1.1 above.
2. **P1 — `nan` passthrough in `_coerce_premium`** (`src/irc/memo/qdii_premium_lines.py:73-80`)
   - Same finding as silent-failure-hunter P1.1; fixed.
3. **CLEAN — exact-5% boundary agreement** between memo (`pct > THRESHOLD`) and decision gate (`premium_value > qdii_max_premium_pct`); both resolve to `QDII_MAX_PREMIUM_DEFAULT = 0.05`.
4. **CLEAN — two-run byte equality** scope excludes `qdii_premium.json` (only `memo.md` is hashed).
5. **CLEAN — §7 prefix double-application**: `prefix_by_iid` rebuilt fresh each call from raw `trades` dict.
6. **CLEAN — `qdii_premium.json` downstream consumers**: no current consumer reads the file; write-only from memo stage.
7. **P2 — off-exchange None miscategorisation**: a genuine fetch failure for an on-exchange ETF surfaces as None and is filtered out → cell renders `—`. `qdii_premium_unknown=True` flag is set elsewhere. Documented, not new.

Final verdict: PASS after in-branch fix of P0 + P1.

## Final verdict rationale

- 1 P0 fixed (CI portability)
- 3 P1 fixed (nan/inf guard at both coerce sites, 5.0% strict boundary regression locks)
- 2 P1 accepted as designed (duplication tolerated via docstring cross-reference, generated_at non-determinism documented)
- All P2 accepted

Loop exit contract satisfied: zero blocker bugs, zero latent bugs remaining on PR HEAD.
