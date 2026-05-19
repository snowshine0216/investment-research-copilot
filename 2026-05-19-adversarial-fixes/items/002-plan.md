# 002 — Plan

## Steps

1. `src/irc/opportunity/thesis_evidence.py`:
   - Add `_count_trusted_citations(report)` using
     `research/source_tier.is_trusted` (item 004).
   - Tighten `_thesis_from_theme_report`: ≥3 citations AND
     ≥1 trusted-tier citation → intact. Otherwise
     evidence_insufficient with a specific reason naming the tier gap.
2. `derive_thesis_from_evidence`: Path B now preserves the specific
   evidence_insufficient reason from `_thesis_from_theme_report`
   (changed the `if state != "evidence_insufficient"` check to
   `if reason:`) so the tier-gap message reaches the caller.
3. Update `tests/opportunity/test_thesis_evidence.py::_research_theme_report`
   to use reuters.com URLs — the placeholder `https://x/N` was classified
   UNKNOWN and would otherwise fail the new tier gate.
4. Add `tests/opportunity/test_thesis_relevance_gate.py` covering:
   - mixed trusted + republisher → intact
   - all republisher → evidence_insufficient with "次级转载源"
   - all unknown-tier → evidence_insufficient
   - below min citations → evidence_insufficient
