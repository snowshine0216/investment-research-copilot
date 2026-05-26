Verdict: PASS

Subagent: sonnet
Source: /verify  (Fallback used: direct CLI smoke + import smoke)
Entry point exercised:
  - uv run irc --help  → printed full command list, exit 0
  - uv run irc config validate  → "OK: all 14 YAML files validated." (14 YAML, 455 instruments, 10 LLM tasks)
  - uv run python -c "from irc.opportunity.policy_b import _compute_foreign_listed_share, FOREIGN_HEAVY_THRESHOLD, evaluate_policy_b; print('rule 2.5 wired')"  → rule 2.5 wired
  - uv run python -c "from irc.opportunity.policy_b import PolicyBVerdict; ... 'fired_rule' in fields"  → True
  - uv run python -c "from irc.fundamentals.types import ActiveFundSnapshot; ... 'fund_level_evidence' in fields"  → True
  - uv run python -c "from irc.scoring.qdii_premium import qdii_premium_for_row, _QDII_ASSET_CLASSES; ..."  → qdii premium router: frozenset({'us_etf', 'hk_etf', 'qdii_global'})
  - uv run python -c "from irc.data.akshare_client import fetch_qdii_premium_pct, _fetch_full_etf_spot_table; ..."  → CacheInfo(hits=0, misses=0, maxsize=1, currsize=0)
  - uv run python -c "from irc.schemas.discovery import HardFilters; HardFilters(qdii_max_premium_pct=0.0)"  → ValidationError raised (gt=0 OK)
  - uv run python -c "from irc.memo.picks_table import PickRow, _format_trigger_status_compact; ... {'tranche_cap_pct','trigger_status'} <= fields"  → True
  - uv run python -c "from irc.decision.sizing import MACRO_FIELD_TO_KEY, resolve_trigger_current_value; from irc.decision.live_inputs import read_live_decision_inputs; ..."  → public symbols + new module wired
  - uv run pytest tests/opportunity/test_policy_b.py tests/scoring/test_qdii_premium.py tests/memo/test_picks_table.py tests/decision/test_three_section_markdown.py -q  → 127 passed, 1 skipped in 0.29s

Cross-item flow observed:
  - Item 001 × Item 003: PolicyBVerdict.fired_rule accessible + resolve_trigger_current_value callable simultaneously — observed fields ['gap_codes', 'audit_errors', 'decision_rule', 'fired_rule', ...], MACRO_FIELD_TO_KEY keys present
  - Item 002 × Item 003: qdii_premium_for_row + _format_trigger_status_compact imported in same process — both callable, no import collision

Failures: none
