Verdict: PASS

Subagent: claude-fable-5
Questions resolved: 12
Docs touched:
  - none (CONTEXT.md unchanged — no new domain term, G10; no ADR — three-of-three bar fails, G12)
Spec refined: items/003-spec.md (commit fc3b541b)

## Resolved decisions

- Q: What is the name of the promoted σ-threshold constant?
  A: `_LOW_AGREEMENT_STDEV = 0.5` in `src/irc/monitor/signal.py`, beside `_DIVERGE = 0.3`.
  Rationale: mirrors the `low_factor_agreement` code it gates; underscore cross-module import follows the existing `annotate.py` ← `signal._FAMILY_OF` precedent.
  Doc impact: none
- Q: σ comparison vs display rounding — which value gates?
  A: Compare the raw recomputed `pstdev` (gate parity); display σ 2dp, threshold via `{:g}` (`0.5`, never `0.50`).
  Rationale: comparison-before-rounding makes a false `σ=… ≥ 0.5` claim impossible.
  Doc impact: none
- Q: Do pairwise branches recheck the trigger predicate (honesty parity with spec Q9)?
  A: No — render whenever both named factors are present.
  Rationale: the pairwise line asserts nothing beyond the values it prints; duplicating `_divergence`'s predicates in the renderer invites the exact drift the constant promotion avoids; codes and contributions come from one frozen `SignalRecord`.
  Doc impact: none
- Q: Import hygiene at `render_cards.py:5` after the swap?
  A: Import line replaces `divergence_caveat` with `divergence_caveat_detail` (no unused import; ruff-enforced); old function stays public in `render_factors`.
  Rationale: single production caller swaps; exact-string tests keep importing the fallback directly.
  Doc impact: none
- Q: How do the four AC-5 fallback cases route?
  A: All delegate to `divergence_caveat(code)` — one fallback carrier; never read `_DIVERGENCE_CAVEATS` directly.
  Rationale: one code path; unknown-code escape-passthrough comes for free.
  Doc impact: none
- Q: AC-7 test shape given `test_render_cards.py:11` `_rec` hardcodes `contributions=()`?
  A: Extend `_rec` with a `contribs=()` keyword param (existing call sites unchanged), no parallel builder.
  Rationale: same-file convention, zero churn.
  Doc impact: none
- Q: Are 偏多/偏空 sign-group labels honest for `heat` (inverted crowding semantics)?
  A: Yes — verified in `annotate.py`: all factor values share the positive-supports-ADD convention (heat caps calm at +0.3), so sign-grouping is consistent for every factor.
  Rationale: the convention is what makes the composite a weighted sum; no per-factor exception.
  Doc impact: none
- Q: Negative zero (`-0.00`) in the 中性 group?
  A: Normalize `value + 0.0` before formatting so `-0.0` renders `+0.00`.
  Rationale: IEEE `-0.0 + 0.0 == 0.0`; blanket no-op for nonzero values.
  Doc impact: none
- Q: `、` separator before the trailing 中性 group — misparse risk?
  A: Keep as spec'd.
  Rationale: the inline 中性 label disambiguates; exact-zero floats are defensive-rare; format already pinned by AC-3's exact-string test.
  Doc impact: none
- Q: New CONTEXT.md term for the group labels or `divergence_caveat_detail`?
  A: None — 偏多/偏空/中性 reuse the report-wide direction-gloss vocabulary (`annotate._market_dir`); the function is a render implementation detail, not a domain term.
  Rationale: factor-direction glosses are never Directional-bias values; glossary bloat avoided.
  Doc impact: none
- Q: Is AC-4's "no behavior change" claim safe against the eval layer (AC-9 forbids eval edits)?
  A: Yes — `eval/determinism.py:94` recomputes through the same `_divergence` (pure rename invisible); `tests/monitor/test_signal.py` has no source-literal `0.5` assertion; `各因子方向/强度不一致` appears only in `tests/monitor/test_render_factors.py` (no golden-bytes lock).
  Rationale: verified by grep + read, not assumed.
  Doc impact: none
- Q: Does this item need a new ADR?
  A: No — three-of-three fails on all prongs (cheap to reverse, unsurprising, no hard trade-off); ADR 0018's "caveats, never suppressors" posture is preserved; ADR 0004 determinism satisfied by fixed-order iteration + ASCII `{:+.2f}`.
  Rationale: render-detail class, exactly as the dispatch anticipated.
  Doc impact: none

Additional verification (no strike-throughs required): every factual claim in the spec re-checked against current code — call site `render_cards.py:102` exact, import at line 5, `render_factors.py` = 80 lines, exact-string tests at `test_render_factors.py:13-26`, `signal._contributions` copies `s.value` verbatim, `divergence_caveat` has exactly one production caller.
