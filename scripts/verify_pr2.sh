#!/usr/bin/env bash
# verify_pr2.sh — end-to-end verification for PR #2
# Usage: bash scripts/verify_pr2.sh
# Exit code 0 = all checks passed, non-zero = something failed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0
RESULTS=()

run_group() {
  local label="$1"
  shift
  printf '\n\033[1;34m══ %s ══\033[0m\n' "$label"
  if uv run pytest "$@" -q --tb=short 2>&1; then
    PASS=$((PASS + 1))
    RESULTS+=("  ✓  $label")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("  ✗  $label")
  fi
}

echo ""
echo "================================================================"
echo "  PR #2 Verification — data ingest + 5-step discovery + scoring"
echo "  Repo : $REPO_ROOT"
echo "  Date : $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"

# ── 1. Data layer ────────────────────────────────────────────────────
run_group "Data: atomic writer (io_utils)" \
  tests/test_io_utils.py

run_group "Data: DuckDB helper (schema + provenance)" \
  tests/data/test_duckdb_helper.py

run_group "Data: manifest writer" \
  tests/data/test_manifest.py

run_group "Data: RawRef reachability index" \
  tests/data/test_raw_ref.py

run_group "Data: OpenBB client wrapper" \
  tests/data/test_openbb_client.py

run_group "Data: AKShare client wrapper" \
  tests/data/test_akshare_client.py

# ── 2. CLI ingest command ────────────────────────────────────────────
run_group "CLI: irc ingest" \
  tests/commands/test_ingest_cmd.py

# ── 3. Discovery funnel (5 steps) ────────────────────────────────────
run_group "Discovery: universe enumeration" \
  tests/discovery/test_universe.py

run_group "Discovery: hard filter (inception/AUM/ER/volume/ban)" \
  tests/discovery/test_hard_filter.py

run_group "Discovery: quality filter (drawdown/TE/tenure)" \
  tests/discovery/test_quality_filter.py

run_group "Discovery: metrics" \
  tests/discovery/test_metrics.py

run_group "Discovery: role bucket (8 roles)" \
  tests/discovery/test_role_bucket.py

run_group "Discovery: reason writer (LLM + raw_ref citation)" \
  tests/discovery/test_reason_writer.py

run_group "Discovery: pipeline" \
  tests/discovery/test_pipeline.py

run_group "CLI: irc discover" \
  tests/commands/test_discover_cmd.py

# ── 4. Scoring pipeline (5 factors) ──────────────────────────────────
run_group "Scoring: valuation_cost factor" \
  tests/scoring/factors/test_valuation_cost.py

run_group "Scoring: risk factor" \
  tests/scoring/factors/test_risk.py

run_group "Scoring: quality factor" \
  tests/scoring/factors/test_quality.py

run_group "Scoring: macro_fit factor (LLM + neutral fallback)" \
  tests/scoring/factors/test_macro_fit.py

run_group "Scoring: thesis_news stub" \
  tests/scoring/factors/test_thesis_news.py

run_group "Scoring: instrument_score (action + conviction mapping)" \
  tests/scoring/test_instrument_score.py

run_group "Scoring: raw_ref_check" \
  tests/scoring/test_raw_ref_check.py

run_group "Scoring: Spearman sanity gate" \
  tests/scoring/test_sanity_check.py

run_group "Scoring: pipeline (parallel LLM fan-out)" \
  tests/scoring/test_pipeline.py

run_group "CLI: irc score" \
  tests/commands/test_score_cmd.py

# ── 5. End-to-end chain: init → ingest → discover → score ────────────
run_group "E2E: init → ingest → discover → score" \
  tests/test_e2e_ingest_discover_score.py

# ── 6. Full suite with coverage (excluding live network tests) ────────
printf '\n\033[1;34m══ Full suite + coverage report ══\033[0m\n'
# Install pytest-cov if not present
if ! uv run python -c "import pytest_cov" 2>/dev/null; then
  echo "Installing pytest-cov..."
  uv add --dev pytest-cov -q
fi
if uv run pytest tests/ \
    --ignore=tests/llm/test_live_smoke.py \
    --cov=irc \
    --cov-report=term-missing:skip-covered \
    --cov-fail-under=80 \
    -q --tb=short 2>&1; then
  PASS=$((PASS + 1))
  RESULTS+=("  ✓  Full suite + coverage ≥ 80%")
else
  FAIL=$((FAIL + 1))
  RESULTS+=("  ✗  Full suite + coverage ≥ 80%")
fi

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo "  Results"
echo "================================================================"
for r in "${RESULTS[@]}"; do
  echo "$r"
done
echo ""
echo "  Groups passed : $PASS"
echo "  Groups failed : $FAIL"
echo "================================================================"

if [[ $FAIL -gt 0 ]]; then
  echo ""
  echo "VERIFICATION FAILED — $FAIL group(s) had failures."
  exit 1
fi

echo ""
echo "ALL CHECKS PASSED — PR #2 implementation verified."
exit 0
