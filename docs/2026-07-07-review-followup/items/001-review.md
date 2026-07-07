Verdict: PASS-WITH-NITS
Source: /ship steps 8+9

Reviewers: pr-review-toolkit:code-reviewer, pr-review-toolkit:silent-failure-hunter (step 8), general-purpose adversarial (step 9). Initial adversarial verdict BREAKS → all findings fixed in-branch (`690eb0ea`) → adversarial re-verification live against its own attack shapes: CLEAN. Codex secondary running at capture time — triages before merge.

## Findings

- [fixed `690eb0ea`] P0 (adversarial, live-verified) — builders total only at top level; `funds:"x"` / `board_pe_freshness:12345` / `macro_snapshots:null` / non-dict fund records raised through run_notify_status; wrapper `|| echo` swallowed it → NO notification. Fixed both layers: isinstance-total builders + `_safe_health` edge net; e2e re-verified rc=0 all shapes.
- [fixed `690eb0ea`] P0 (silent-failure) — missing/corrupt `fund_flow_series.json` folded to an empty digest (false clean). Now an explicit unreadable warn item.
- [fixed `690eb0ea`] P0 (silent-failure) — corrupt historical radar day read as "unknown", breaking the consecutive-degraded scan → recovery notice suppressed. Unreadable days now dropped with a log warning; ok/abstain/corrupt/ok fires correctly.
- [fixed `690eb0ea`] P1 (code-review, live-verified) — missing today's radar made recent_statuses[-1] = yesterday → false 恢复 text inside a `failed` page. Recovery now gated on today's radar existing.
- [nit, documented — locked G-Q7 deferral] same-day manual notify-status re-run re-fires the recovery push (no persisted notified-state by design; TODOS).
- [nit, log-only] `_read_json` valid-JSON-but-non-dict returns None without a log line (degrades correctly).
- [nit, comment suggestion] `_flow_items` if/elif renders only one of flow_symbol_stale/flow_stale per run — intentional v1 lock, worth a code comment.

## Classification

Blockers: 0 remaining. Latent bugs: 0 remaining (all four fixable findings fixed pre-push and adversarially re-verified). Nits: 3 (documented above).

## Codex-secondary addendum (post-capture, pre-merge — 2026-07-07)

Codex returned AFTER the initial verdict with 2 real findings, both fixed + TDD'd before merge:
- [fixed `d9a06161`] P0 SPEC GAP — spec line 89/§3.3 mandates the flow-capture coverage check (store delta, <80% → warn "flow-capture: N/M"); the plan under-wired it, so a soft capture failure (EM batch fails, rc still 0) with ok rotation was silent at 15:45. Now implemented (pure `flow_capture_health` + edge `_capture_coverage_items`); CLI-level proof: staged 7/30 day renders `degraded · flow-capture: 7/30`, notify True. (Plan-vs-spec hole — drift-vs-plan could not catch it; Codex did.)
- [fixed `d9a06161`] P1 REGRESSION (rounds-1 fixes interacting) — corrupt TODAY radar passed the `exists()` recovery gate while statuses dropped the unreadable day → bogus forced 恢复 page. Recovery now anchored on the parsed radar's own `data_status == "ok"`.
- [fixed `fb9316da`] pr-review nit — 5th shape sibling (`signal: null`) guarded; "total" docstring claim now true.

Verdict unchanged: PASS-WITH-NITS (remaining nits: G-Q7 same-day re-fire, `_read_json` non-dict log, flow_items comment).
