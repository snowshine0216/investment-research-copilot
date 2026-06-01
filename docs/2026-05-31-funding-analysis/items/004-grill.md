Verdict: PASS

Subagent: opus
Questions resolved: 9
Docs touched:
  - CONTEXT.md (commit 4b9f050)
Spec refined: items/004-spec.md (commit 4b9f050)

No ADR created. The wire-but-degrade-to-`None` decision and the reason-only-vs-state
trade-off are ALREADY recorded in ADR 0009 (it explicitly answers "why build a metric
that never fires?"). Item 004 is a direct re-application, not a new architectural
decision, and a reason-only fragment + one defaulted field is highly reversible — the
three-of-three ADR bar (hard-to-reverse + surprising + real trade-off) is not cleared.
A CONTEXT.md note cross-referencing ADR 0009 is the correct documentation; the spec's
D8/AC12 ADR-0010 mandate was overruled.

## Resolved decisions

- Q: G1 — return shape: frozen `KeyRatios` dataclass vs literal `dict`?
  A: Frozen `KeyRatios` dataclass.
  Rationale: every multi-scalar bundle in the codebase is a frozen dataclass (`IndexValuation`, `FilingDigest`, `BrokerReport`); the master-spec `-> {roe,…}` is field-set shorthand, not a dict mandate.
  Doc impact: CONTEXT.md term (`KeyRatios`)

- Q: G2 — exact attachment point + length cap?
  A: Per-constituent `_one_line_view` ONLY; the hard `[:60]` cap (snapshot.py:443) stays — use a compact fragment, best-effort within the cap. The `FilingDigest`/`KeyRatios` must be threaded out of `_evidence_for_constituent` (not in scope at the call site today).
  Rationale: ROE/gross_margin are per-held-stock (not fund/index-level like pe/pb); cap verified real; digest verified out-of-scope. Spec G2 understated the work.
  Doc impact: CONTEXT.md term (`compute_ratios`) | spec AC7 strikethrough

- Q: G3 — `roe` period alignment (quarterly ROE vs gross margin)?
  A: Caveat sufficient; surface ROE for ALL periods, no FY-only suppression.
  Rationale: premise partially FALSE — `gross_margin` is computed from the SAME `latest` period column as `roe`, so they are period-aligned; only residual is non-annualisation, disclaimed by `口径未核实`.
  Doc impact: CONTEXT.md term (`FilingDigest.roe`) | spec G3 strikethrough

- Q: G4 — V1 surface = available ratios only; `None` omitted (not "None")?
  A: Confirmed. ROE + gross_margin today; `debt_equity`/`fcf_yield` `None` → omitted; empty string when all four `None`.
  Rationale: mirrors `_pe_pb_fragment` and ADR 0009 wire-but-degrade-to-`None`; self-activates when item 003 lands.
  Doc impact: CONTEXT.md terms (`KeyRatios` / `compute_ratios`)

- Q: Is `compute_ratios` PURE (no LLM, no I/O)?
  A: Yes, mandatory — in-memory `FilingDigest` only; no `akshare`/`duckdb`/`llm` import; only new effect is the `净资产收益率` read inside the existing `fetch_cn_filing_digest` wrapper.
  Rationale: headline determinism; AC2 asserts it.
  Doc impact: CONTEXT.md term (`compute_ratios`)

- Q: Does 004 add a state classifier / change valuation_state/thesis_state/Policy B/core_dca/H3/SAME-3?
  A: No — reason-only, like pe/pb.
  Rationale: item 002 lifted inertness for `consensus_upside_pct` only; pe/pb stayed reason-only for lacking peer/history normalisation — absolute ROE/gross_margin share that limitation. AC8 asserts byte-identical states.
  Doc impact: CONTEXT.md term (`KeyRatios`, reason-only posture)

- Q: Filing-evidence-semantics — caveat needed? citation needed?
  A: Caveat (`口径未核实`) required; NO `[ref:...]`, NO `ThesisEvidence`; keep fragment structurally separate from the locked `财报已披露（口径未核实）` filing-summary phrase.
  Rationale: filing numbers are disclosure-existence anchors not endorsed performance (ADR 0001 §5); `consensus_upside_pct`/pe/pb surface with no citation (ADR 0009) — spec's "no citation" claim is consistent.
  Doc impact: CONTEXT.md term (`compute_ratios`)

- Q: Zero-denominator / missing-input → `None` (degrade-to-none)?
  A: Yes — explicit NaN + non-positive-denominator screening (mirrors consensus.py:29-37); never raises, never fabricates. AC6 asserts it.
  Rationale: ADR 0009 degrade-to-`None`; safety bites on the future debt_equity/fcf_yield divisions.
  Doc impact: CONTEXT.md term (`compute_ratios`)

- Q: Does this clear the three-of-three ADR bar?
  A: No — do NOT write `docs/adr/0010-*.md`; a CONTEXT.md note cross-referencing ADR 0009 suffices.
  Rationale: high reversibility; surprise + trade-off both already recorded by ADR 0009; 004 is a re-application, not a new decision. D8/AC12 overruled.
  Doc impact: spec D8 + AC12 strikethrough | none (no ADR)

## Spec claims FALSE / imprecise against the code

- ROE "extractable via the existing `_common_metric` … one-line section change": IMPRECISE. `_common_metric` (akshare_filing.py:106) hard-codes `选项 == "常用指标"` and is shared by revenue/NI/cost; a separate `盈利能力`-section read is required. The frame-level claim "ROE already in the fetched dataframe but dropped" is TRUE (the single `stock_financial_abstract` call returns all sections; `净资产收益率` is present and never extracted).
- `_one_line_view` "natural carrier, parallel to the filing fragment" (G2): UNDERSTATED. It does not receive the `FilingDigest`/`KeyRatios` (dropped in `_evidence_for_constituent`); threading required and the `[:60]` cap is a hard constraint.
- "`roe` quarterly while gross_margin annual" (G3): PARTIALLY FALSE — both read from the same `latest` period column (period-aligned); only residual is non-annualisation.
- "New ADR 0010" (D8/AC12): OVERRULED — reuses ADR 0009; bar not cleared.
