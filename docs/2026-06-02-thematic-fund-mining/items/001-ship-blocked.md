# 001 — /ship pre-landing review (steps 8+9): blockers → fix before push

Source: /ship steps 8 (pr-review-toolkit:code-reviewer + silent-failure-hunter) + 9 (adversarial). Adversarial verdict: **BREAKS** (P0 found). Per ship.md "/ship review can demand fixes before push" → triage-fix BEFORE opening the PR, then re-review.

## MUST-FIX (P0 — wrong/invalid results or spec §4 violation)

- **F1 `score_overlap` duplicate-symbol double-count** (`src/irc/narrative/screen.py`) — AkShare can return duplicate rows for one symbol; the linear loop adds weight + appends to `matched` per occurrence, inflating `basket_weight_pct`/`overlap_count` and putting dups in `matched_symbols`. Fix: dedupe by symbol (keep highest-weight) at the `_parse` edge AND make `score_overlap` count each symbol once (defensive). Tests at both layers.
- **F2 `NaN`/`inf` weight → invalid JSON** (`src/irc/narrative/holdings_fetch.py:_to_holding`) — `float(nan)` passes the TypeError/ValueError guard; `round(nan,4)=nan`; `json.dumps` emits bare `NaN` (invalid RFC-8259), breaking the determinism/JSON acceptance. Fix: sanitize NaN/inf → 0.0 at the edge. Test.
- **F3 per-fund `analyze_fund` crash aborts the whole run** (`src/irc/commands/narrative_cmd.py:_run_analyze`, `analyze.py`) — one fund raising in `build_opportunity_row`/`build_thesis_card` propagates an uncaught traceback; `_run_analyze` returns None → misleading "run `irc ingest`". Violates spec §4 ("surfaced not crashed"). Fix: guard each fund; on error emit an `insufficient` report (evidence_gaps reason) and continue; return partial results. None stays ONLY for the genuine prerequisites-absent case. Test.

## SHOULD-FIX (P1 — repo "no silent caps")

- **F4 silent exception swallowing** — log WARNING (project observability logger) in `fetch_top_holdings` except, `_read_cache` except, and `_open_analyze_context` connect-failure. Edge-only (allowed). Removes the "AkShare outage makes every fund look like no_published_holdings, silently" failure mode.
- **F5** `config/narratives/compute_metals.yaml` comment: `min_overlap_count` counts basket-hits + SW-industry credits, not just "distinct basket names". Correct the comment.
- **F6** `load_narrative_basket`: reject empty/missing `basket:` with a clear `ValueError` (fail-fast, matches the existing malformed-config rejection). Test.
- **F7 (nit)** `h.__dict__` → `dataclasses.asdict(h)` in `report.py`/`holdings_fetch.py` (idiom + nested-field safety).

## DEFER (documented gap / P2 cosmetic — recorded, not fixed)

- `metrics={}` so `drawdown_3y`/`volatility` never fire in analyze → **documented spec §3.6 gap** (those fields are not on `OpportunityRow`/`OpportunityInput`; "fire only when available, never fabricate"). Flagged to user in the PR.
- `--out` resolves to an existing file → `mkdir` crash (P2, rare misuse).
- `--screen-only` + `--analyze` both passed → screen-only wins silently (P2 UX).
- `narrative_id` in YAML disagrees with filename stem (P2 cosmetic).
- `top_n=0` → empty shortlist (P2; config-controlled, not user-facing).

After F1–F7 land + tests green, re-run the adversarial check, then push + open the PR and capture the clean review into `items/001-review.md`.
