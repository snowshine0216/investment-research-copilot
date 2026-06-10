Verdict: PASS-WITH-NITS
Source: /ship steps 8+9
Findings (round 1, all fixed pre-push — see items/001-ship-blocked.md):
- P0 — models.py — DecisionRow lacked is_holding → 持仓行动 section always empty in real pipeline — FIXED 8039927 (+ round-trip test).
- P0 — decision_cmd.py — stale pre-001 opportunity_report.json silently degraded to all-healthy zero counts — FIXED 30d5dba (null counts + warning line + ADR 0015 addendum).
- P0-adjacent (contract) — portfolio_action.py — buy-side blockers suppressed sell signals on held rows — FIXED b3f3002 (sell-precedence, ADR 0015 §2 updated).
- P1 ×4 — falsy or-coercion, KeyError guard, section sort (ADR 0004), JSON error swallowing — FIXED 9365e16.
Remaining nits (accepted):
- Renderer `float(r.get(x) or 0.0)` falsy pattern — output correct, P2 cleanliness.
- Pre-existing: multi-account duplicate-holding weight undercount (last-write-win _holdings_index) — untriggered by current account.yaml; out of item scope.
Adversarial (step 9): RISKS — P2 only; e2e deterministic across consecutive runs; counts/section cannot diverge (mapper gates sell actions behind is_holding).
