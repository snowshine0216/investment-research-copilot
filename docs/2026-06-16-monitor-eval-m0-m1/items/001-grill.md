Verdict: PASS

Subagent: opus
Questions resolved: 7
Docs touched:
  - CONTEXT.md (commit 64c5aec)
  - docs/adr/0017-monitor-evidence-isolation.md (commit 64c5aec)
Spec refined: items/001-spec.md (commit 64c5aec)

The grill hardened the M0 spec for **terminology precision and domain-model fit** only — no §7
pinned decision and no resolved P0/P1/P2 finding was re-opened. Every spec claim grounded against
`src/irc/monitor/` and `evals/_shared/` checked out (e.g. `compute_signal` reads only
`id`/`weights`/`bands`/`minimum_confidence`; `FundView.evidence_pool` is macro-only; `as_of_date`
is `str`; `Provenance.engine_version` exists; `status.py`/`registry.py`/`missing_input.py` match the
"add X" deltas; `preflight_gate(repo_root, command)` returns 5 when blocked). No spec line was
factually wrong, so there are no strike-throughs — one inline precision note was added to AC #9
(the `GateDecision` naming-collision guard). Verdict PASS: nothing contradicts a load-bearing ADR or
current code in a way doc updates cannot resolve.

## Resolved decisions

- Q: Are the ten new M0-eval terms (`eval_trace`, `FundTraceBundle`, `StageHealth`, `GateDecision`,
    `published_state`, `EVAL_GATED`, validation badge/chip, forward ledger, `live_gated`, `eval-live`)
    defined in CONTEXT.md?
  A: No — added a new "Monitor eval spine (validation track)" sub-section with one entry per term in
    the existing CONTEXT.md style.
  Rationale: ten load-bearing terms had zero prior glossary coverage; the plan phase needs canonical
    definitions.
  Doc impact: CONTEXT.md (10 new terms)

- Q: Does `published_state` collide with the existing `NO_CALL` / `Directional bias` render semantics?
  A: It is the NEW single render-label selector that supersedes the bare `NO_CALL`/`bias` decision,
    precedence `NO_CALL` (status≠ok) > `EVAL_GATED` (suppressed) > `bias`; `NO_CALL ≠ NEUTRAL` and
    `NO_CALL`-wins-over-`EVAL_GATED` recorded as structural invariants.
  Rationale: keeps AC #14 precedence consistent with CONTEXT.md's `NO_CALL`; prevents reading it as a
    fourth independent field.
  Doc impact: CONTEXT.md term `published_state` + updated `NO_CALL` cross-reference

- Q: Naming collision — `irc.monitor.eval.types.GateDecision` vs the pre-existing
    `irc.spend.types.GateDecision`?
  A: Real domain-language collision (spend verdict `blocked/warnings/ok` vs eval verdict
    `fund_id/suppressed/failed_stages/badge/reason`). Keep both names (M0 name is the rev-3 §2.2 pinned
    interface), disambiguate in the glossary, require qualified-module-path imports.
  Rationale: Python namespaces them safely but the vocabulary must stay sharp; a bare dual import would
    be latent confusion.
  Doc impact: CONTEXT.md `GateDecision` (monitor eval) term + inline grill note on AC #9

- Q: The forward ledger writes to `data/monitor/forward_ledger.jsonl`, but CLAUDE.md/ADR 0006 say
    `data/` is "reserved for the DuckDB cache" — is `data/` the right home?
  A: Yes — `data/` already holds non-DuckDB cumulative state (`fundamentals/`, `spend/`, `research/`);
    the ledger is cross-run cumulative track-record state, the opposite of a date-partitioned
    `outputs/<date>/` artifact.
  Rationale: deliberate, non-obvious, hard-to-reverse placement; a reader must not "normalize" it into
    `outputs/` and silently reset the track record.
  Doc impact: CONTEXT.md `Forward ledger` term + ADR 0017 §"Monitor-eval data contracts"

- Q: Does `eval_trace.json` clear the ADR three-of-three bar, and does serializing a *unified*
    evidence pool contradict ADR 0017's isolation invariant?
  A: Clears the bar (hard to reverse / surprising / new-artifact-vs-extend-signal.json). Does NOT
    contradict ADR 0017 — "unified" = macro ⊕ constituent within one fund's own scope-less monitor
    pool (never reaching `build_cited_map`/the dual-coverage gate), not monitor ⊕ opportunity.
  Rationale: the contract's surprise/reversibility is rooted in ADR 0017's isolation rule → extend it
    rather than spawn a new ADR.
  Doc impact: ADR 0017 §"Monitor-eval data contracts" (eval_trace) + CONTEXT.md
    (`eval_trace.json`, `FundTraceBundle`)

- Q: Does the append-mode JSONL ledger writer clear the ADR bar (it deviates from the project's atomic
    `.tmp→replace` convention)?
  A: Clears the bar (hard to reverse / surprising vs convention / real append-vs-atomic trade-off,
    chosen so concurrent/rerun rows are never lost; single JSONL line < `PIPE_BUF` ⇒ atomic on POSIX).
    Folded into the same ADR 0017 extension; distinct from the source §9 ablation/calibration ADR
    (still M2–M4 out of scope).
  Rationale: same monitor-eval lineage; a deliberate deviation from a documented convention is exactly
    what an ADR flags.
  Doc impact: ADR 0017 §"Monitor-eval data contracts" (forward-ledger sub-section)

- Q: Does `StageHealth.status` (`UNKNOWN`) collide with the eval suite's whole-stage `overall` status
    (`PASS/WARN/FAIL/SKIPPED`)?
  A: Different vocabularies on purpose — `StageHealth` is the gate's input (`UNKNOWN` for absent/
    skipped/stale resolved reports); `overall` is the report's verdict (`SKIPPED` whole-stage). The
    one mapping is `resolve_health`. Keeping the literal sets separate is what lets `worst_status`
    rank only PASS/WARN/FAIL (AC #21).
  Rationale: unifying the literals would break the `worst_status`-never-sees-SKIPPED invariant.
  Doc impact: CONTEXT.md `StageHealth` term notes the distinction (no spec change)
