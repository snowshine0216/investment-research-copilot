# Ship blocked — /ship steps 8+9 findings (round 1)

Status: BLOCKED pre-push (adversarial verdict BREAKS). Fix round dispatched; /ship re-invokes after.

## P0 (must fix)
1. [adversarial, REPRODUCED] `narrative_macro.py:169-214` parse path catches only `(json.JSONDecodeError, _MacroNarrErr)`; valid-JSON-wrong-shape LLM output (theme value = string, row = non-dict) raises AttributeError that escapes uncaught; call site `monitor_cmd.py:1006` has no guard → entire daily run dies BEFORE report.html / eval_trace.json / forward_ledger writes, under launchd, no resume marker. Violates spec §10 degradation ("LLM failure → absent section, never a crashed run"). Repro: `_parse_theme_claims("brief note", pool, hardened=False)` → AttributeError.

## P1 (fix in same round unless noted)
2. [adversarial] `citation_ids` returned as bare string iterates char-by-char → garbage 1-char cids fail `resolve_in_pool`, burning the hardened retry reserved for CJK failure with no distinguishing signal. Type-validate → schema failure with distinct reason.
3. [silent-failure] Second `source_tiers` read at `monitor_cmd.py:1035` swallows failure UNLOGGED (first read inside `_build_theme_results` logs) → all badges silently render 未分级 with no breadcrumb. Fix: log at this site (mirror the first site's warning). Full threading consolidation deferred (polish; signature-change ripple not worth it pre-merge).
4. [code-reviewer] `render_drilldown.py:81-87` `_row_reason` or-chain falls through to UNRELATED reason fields for columns without a dedicated `{column}_reason` key → e.g. all-dark PB column labeled `flow_no_data`. Only the industry path is tested (fallback happens to be correct there), masking it. Fix: honest column→reason mapping; no borrowing unrelated reasons.

## Deferred to PR body (polish, reviewer-rated non-blocking)
- `_capture_union_symbols` called twice per run; config loaded 3× (cheap local reads) — consolidation follow-up.

Subagents: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter, general-purpose adversarial. Notes: HTML escaping verified at every web-content render site; `_age_days` naive/aware handling verified; ADR 0022 fail-open confirmed intentional.
