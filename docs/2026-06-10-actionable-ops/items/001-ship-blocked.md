# Ship-blocked findings — item 001 (pre-push review round 1)

P0-1 (code-reviewer + silent-failure-hunter): DecisionRow lacks is_holding field.
decide_row receives is_holding but never stores it; to_dict()/asdict() omits it; report.py
_holdings_action_section filters r.get("is_holding") → always falsy → 持仓行动 section
always renders 「（无持仓调整建议）」 in the real pipeline. Tests used hand-built dicts and
missed it. FIX: add is_holding field to DecisionRow, thread from decide_row, add
round-trip test decide_row(is_holding=True, risk_action="exit_review") → to_dict()
preserves is_holding True + section renders the row.

P0-2 (silent-failure-hunter): stale opportunity_report.json (pre-001, no risk_action keys
on any row) silently degrades to all-no_trade, zero trim/exit/review counts — masked sell
signals. FIX: in decision_cmd, detect artifact-wide absence of "risk_action" key; when
absent: set trim_count/exit_count/review_count to null in decision_report.json summary and
render a visible warning line in the 持仓行动 section ("sell-side signals unavailable —
re-run irc opportunity"). Add tests for both paths. Document the null-counts contract in
ADR 0015 addendum (item 002's notifier must treat null as unknown, not 0).

P0-3 (silent-failure-hunter; adjudicate vs ADR 0015): map_portfolio_action returns
no_trade whenever blocking_reasons is non-empty, even for held rows with
risk_action=exit_review/trim_review — sell signal suppressed by buy-side blockers
(venue/opportunity_excluded block BUYING, not selling what you already hold). FIX:
sell-side precedence — for is_holding rows, exit/trim/review mapping fires BEFORE the
blocking_reasons short-circuit. Update ADR 0015 with the precedence correction + test.

P1-1 (both): gates.py:168 `portfolio_weight or 0.0` → explicit None check
(`0.0 if portfolio_weight is None else portfolio_weight`); same in weight_delta.
P1-2: opportunity_cmd.py discipline_by_id build uses positions[dr.instrument_id] —
switch to .get() guard so a future caller mismatch degrades with a clear skip, not KeyError.
P1-3 (ADR 0004): _holdings_action_section must sort held rows explicitly
(sorted by instrument_id) instead of inheriting upstream order.
P1-4: decision_cmd JSONDecodeError catches return silently — add a visible
"WARNING: could not parse opportunity_report.json" print before fallback.
