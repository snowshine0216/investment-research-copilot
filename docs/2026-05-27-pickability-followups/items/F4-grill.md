Verdict: PASS
Subagent: opus
Questions resolved: 24
Docs touched:
  - CONTEXT.md (commit ded282c)
  - docs/adr/0007-thesis-news-scoring.md (commit ded282c)
Spec refined: items/F4-spec.md (commit ded282c)

## Resolved decisions

- Q: Does the spec's theme→asset-class mapping table use real asset_class values from config/universe/?
  A: No — the spec invented seven labels (cn_a_broad, cn_a_sector, cn_a_smart_beta, cn_money_market, cn_bond, qdii_us, qdii_hk, gold_etf, gold_proxy) that do NOT exist. Real values are seven: cn_bond_fund, cn_equity_fund, cn_etf, gold, hk_etf, qdii_global, us_etf. Table rewritten.
  Rationale: spec must align with config/universe/*.yaml, the source of truth for asset_class strings consumed by scoring/pipeline.py.
  Doc impact: CONTEXT.md "Thesis-news scoring" + ADR-0007 §2

- Q: Is `themes_for_instrument(asset_class, market)` the right signature?
  A: No — drop `market`. New signature: themes_for_instrument(asset_class: str) -> tuple[str, ...].
  Rationale: none of the seven real asset_class mappings depend on cn_on_exchange vs cn_off_exchange; the parameter would be an unused knob.
  Doc impact: CONTEXT.md "Thesis-news scoring" + ADR-0007 §2

- Q: How should `holdings_sector` route in the rewritten table?
  A: All CN-equity-flavoured asset_classes — cn_equity_fund, cn_etf, hk_etf. Bonds/gold/US/global excluded.
  Rationale: holdings_sector is built from user holdings; only equity-flavoured CN-market funds benefit.
  Doc impact: CONTEXT.md mapping table

- Q: `cn_bond_fund` mapping: single cn_monetary or expand?
  A: Single theme cn_monetary.
  Rationale: bonds correlate with monetary policy primarily; other themes add noise.
  Doc impact: CONTEXT.md mapping table

- Q: `gold` mapping: add geopolitics?
  A: Yes — (geopolitics, gold_drivers, us_monetary).
  Rationale: gold reacts to safe-haven flows during geopolitical events.
  Doc impact: CONTEXT.md mapping table + ADR-0007 §2

- Q: `us_etf` / `hk_etf` mappings?
  A: us_etf → (geopolitics, us_fiscal_politics, us_monetary); hk_etf → (cn_equity_property_policy, cn_monetary, geopolitics, holdings_sector).
  Rationale: US ETFs are USD-denominated equity; HK ETFs react to both CN policy AND geopolitics.
  Doc impact: CONTEXT.md mapping table

- Q: `qdii_global` mapping?
  A: (geopolitics, us_fiscal_politics, us_monetary) — same as us_etf.
  Rationale: global QDIIs are predominantly USD-denominated equity exposure.
  Doc impact: CONTEXT.md mapping table

- Q: Empty-input invariant: news_summaries={} and {iid: ()} treated identically?
  A: Yes — dict.get(iid, ()) returns () either way; factor returns score=50.0, components={"data_completeness": 0.0, "neutral_default": 1.0}.
  Rationale: cold-start behavior must be identical to pre-F4 production.
  Doc impact: ADR-0007 §3

- Q: Unknown asset_class: silent empty tuple or raise?
  A: Silent empty tuple. Falls back to neutral 50.0.
  Rationale: a new asset_class added to config/universe/ should not crash the scorer; ops awareness via non-fatal log at command edge.
  Doc impact: ADR-0007 §2

- Q: build_news_summaries reads report_md only, or also citations?
  A: report_md only.
  Rationale: rubric is keyword-based over prose; citation titles would dilute signal.
  Doc impact: CONTEXT.md build_news_summaries entry + ADR-0007 §4

- Q: Tuple of theme summaries, or concatenated single string?
  A: Tuple — one summary per theme.
  Rationale: existing factor function expects tuple[str, ...]; concatenation would over-weight a single long report.
  Doc impact: CONTEXT.md news_summaries entry

- Q: Theme with failed report_md (non-empty failure_reason): include empty string or skip?
  A: Skip silently.
  Rationale: empty-string summary would inflate tuple count without signal.
  Doc impact: CONTEXT.md build_news_summaries entry

- Q: End-to-end determinism: holds across all four layers?
  A: Yes — load_theme_reports → JSON list order; MappingProxyType is immutable; per-instrument tuple sorted theme-name ASC; score_thesis_news is arithmetic.
  Rationale: AC #6 demands byte-equal scoring.json across two runs; each layer must be deterministic.
  Doc impact: ADR-0007 §4

- Q: AC #4 hard-pass or measured-with-fallback?
  A: Measured. If <3 of top-10 differ by ≥10 points, add SKIPPED entry F4-followup-llm-rubric.
  Rationale: empty-input fallback explains 100% of observed symptom; rubric quality only measurable post-plumbing. Pre-committing to a hard pass risks blocking ship on a corpus that may genuinely be too sparse.
  Doc impact: ADR-0007 §5

- Q: news_summaries cached or recomputed per run_scoring?
  A: Recomputed. One-shot disk read at start of run_score.
  Rationale: caching would need invalidation logic that doesn't pay for itself.
  Doc impact: none (implementation note)

- Q: Where does _compose_news_summaries call live in score_cmd.run_score?
  A: After watchlist load, before run_scoring. news_summaries={} literal at line 69 removed (AC #10 greppable).
  Rationale: keeps the I/O at the command edge per "effects at edges".
  Doc impact: none (implementation note)

- Q: themes_for_instrument lookup inside build_news_summaries or at call site?
  A: Inside build_news_summaries.
  Rationale: pure-function contract — caller doesn't need to know about themes.
  Doc impact: CONTEXT.md build_news_summaries entry

- Q: Per-instrument tuple order: theme-mapping order or sorted?
  A: Theme-name ASC.
  Rationale: determinism is non-negotiable; sorting at the build step makes the invariant visible at the boundary, not relying on map traversal order.
  Doc impact: CONTEXT.md build_news_summaries entry + ADR-0007 §4

- Q: Does F4 touch H3, thesis_state, citation gate, or OpportunityRow?
  A: No — factor score change is purely numeric → compose_score only.
  Rationale: F4 is plumbing; thesis_state is set exclusively by derive_thesis_from_evidence per CONTEXT.md / ADR 0003.
  Doc impact: ADR-0007 "Non-goals"

- Q: IRC_*_BEGIN/END marker interaction?
  A: None. F4 changes scoring output only; memo markers are downstream.
  Rationale: spec AC #9 already locks this.
  Doc impact: none

- Q: Should ADR-0007 name the news_summaries={} literal as the historical bug?
  A: Yes.
  Rationale: without it ADR-0007 reads "we added theme-to-asset-class mapping" with no motivation.
  Doc impact: ADR-0007 §Context

- Q: Determinism gate: dict equality or scoring.json byte equality?
  A: scoring.json byte equality.
  Rationale: it's the user-visible artifact AC #6 specifies; dict-level equality is a weaker invariant.
  Doc impact: ADR-0007 §4

- Q: Does F4 affect IRC_FETCH_BUDGET or fetch-state?
  A: No — F4 reads cached data/research/ only; no AkShare, no LLM.
  Rationale: ADR 0002 §3 contracts untouched by construction.
  Doc impact: none

- Q: Does F4's test suite need the live-test gate?
  A: No — all F4 tests are pure-function tests against fixtures.
  Rationale: live-test marker is reserved for tests hitting real upstreams per CONTEXT.md "Live test gate".
  Doc impact: none
