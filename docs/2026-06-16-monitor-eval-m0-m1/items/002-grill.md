Verdict: PASS

Subagent: opus
Questions resolved: 8
Docs touched:
  - CONTEXT.md (commit b1f15d3)
  - docs/adr/0017-monitor-evidence-isolation.md (commit b1f15d3)
Spec refined: items/002-spec.md (commit b1f15d3)

Grilled the M1 (LLM suites) spec for terminology precision and domain-model fit
against CONTEXT.md, ADR 0017, the merged M0 code (gate.py, staleness.py,
latest_report.py, registry.py, scope.py, eval_cmd.py, monitor_signal/runner.py,
status.py), and the production `src/irc/monitor/{narrative,impacts,evidence,types}.py`.
This was hardening, NOT redesign: the five resolved OQs (A–E) and the §7 pinned
decisions are preserved verbatim. No contradiction with a load-bearing ADR or
merged code that docs could not resolve → PASS. The one real domain-model conflict
found (AC8 framing `attribution_strength` as a two-value enum vs the four-value
`AttributionStrength` literal) was a wording/terminology fix, not a rule change —
the rule itself already matched production `narrative._banned_verb_present`.

## Resolved decisions

- Q: Does the `attribution_honesty` scorer gate on a two-value enum?
  A: No — it reproduces production `narrative._banned_verb_present` verbatim (pass iff
     no banned verb OR `attribution_strength=="supported_attribution"`).
     `AttributionStrength` is a FOUR-value literal (supported_attribution /
     consistent_with / possible_driver / unknown); the other three are valid outputs
     the scorer does not reject.
  Rationale: AC8's binary framing contradicted the domain model; the rule was right,
     only the wording implied two values.
  Doc impact: spec AC8 strike-through correction; CONTEXT.md
     `attribution_strength` / `supported_attribution` entry.

- Q: What exactly is `hallucination_rate`?
  A: Fraction of claims whose text has a digit OR an unresolved `\[ref:[0-9a-f]{16}\]`
     marker (16-hex ref not in the case `evidence_pool`); lower-is-better,
     `fail_above:0.0`. Any inline `[ref:]` is suspect — production claims carry
     structured `citation_ids`, not markers.
  Rationale: "unresolved [ref:]" was ambiguous given the prod narrative emits no
     inline markers.
  Doc impact: spec AC8 clause; CONTEXT.md `hallucination_rate` entry.

- Q: Are the corpora a versioned data contract, and what do we call them?
  A: Canonical term "eval corpus / eval case" (avoid bare "fixture"). Versioned data
     contract on the same footing as `eval_trace.json`; loaded identically by pure
     scorer tests and the live runner; editing a case silently shifts pass/fail once
     thresholds calibrate (M4).
  Rationale: clears the 3-of-3 ADR bar (hard to reverse, surprising, real alternative
     of test-inline cases); rooted in ADR 0017's scope-free-EvidenceItem invariant.
  Doc impact: CONTEXT.md `Eval corpus / eval case` entry; ADR 0017
     §"M1 LLM-suite data contracts" → "Eval corpora — versioned data fixtures".

- Q: Is "the live runner is the only paid surface" ADR-worthy?
  A: Yes. The `live_gated` runner is the sole M1 LLM-spend path; scorers + corpus
     loaders are pure (no gateway/http import, enforced by an import guard); the runner
     is triple-gated (env `IRC_RUN_LIVE_LLM_EVAL` + `preflight_gate("eval-live")` +
     `record_command_run`).
  Rationale: clears the ADR bar — surprising (why may a scorer not call the LLM?),
     hard to reverse (free-unit-test contract rests on it), real alternative (score
     inline / scorers call the LLM).
  Doc impact: CONTEXT.md `Eval-live paid surface (M1)` entry; ADR 0017
     §"M1 LLM-suite data contracts" → "Live runner is the sole paid LLM surface".

- Q: OQ-A pins `IRC_RUN_LIVE_LLM_EVAL` but pyproject documents `live_llm` with
     `RUN_LIVE_LLM_TESTS=1` — contradiction?
  A: No contradiction — the `live_llm` marker is env-var-agnostic (the env gate is in
     each test's `skipif`, not the marker), so one marker hosts both env families.
     Honor OQ-A; no marker/pyproject change. The pyproject line is a non-exhaustive
     example.
  Rationale: prevents a future "unification" of the two env vars that would break the
     "test runs ⟺ runner would run" property OQ-A pins.
  Doc impact: CONTEXT.md `live_llm marker (env-agnostic)` entry. No code change.

- Q: `citation_validity` (impact) vs `citation_resolution` (narrative) — two checks?
  A: One primitive (returned 16-hex `citation_id`s ⊆ pool ids), three names across
     separate modules/stages (incl. M0 `monitor_signal.citation_resolution`). Keep the
     names; document the shared primitive.
  Rationale: stops the three names being read as three different gates.
  Doc impact: CONTEXT.md `citation_validity / citation_resolution (shared primitive)`
     entry.

- Q: How does the pure `entailment_ablation_pass` scorer detect claim presence in
     free Chinese text?
  A: The case `expected` carries both the supporting `citation_id` (`present_iff_item`)
     and a declared claim-presence probe (substring/keyword) the scorer greps —
     deterministic, no semantic matching, scorer stays pure over `(case, output)`.
  Rationale: claims are free text; presence must be a corpus-declared signal, not a
     model judgment. Implementation detail → spec/plan, not glossary.
  Doc impact: spec Resolved decisions only. No CONTEXT term.

- Q: `eval-live` scope is the union of both tasks even for single-stage runs —
     surprising?
  A: Inherited from M0, unchanged. Conservative over-estimate (may pre-empt a fitting
     run, never under-budgets); the runner records actual per-call costs so the ledger
     is exact.
  Rationale: surfaced because M1 is where the runner actually spends; confirmed the
     over-estimate is the safe direction.
  Doc impact: CONTEXT.md `eval-live (spend scope)` entry extended. No code change.
