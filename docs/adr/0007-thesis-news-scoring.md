# ADR 0007 — `thesis_news` keyword scoring + theme→asset-class plumbing

**Status:** Accepted (2026-05-27, pickability-followups item F4).
**Supersedes:** none. Builds on no prior ADR — this is the first ADR that touches the scoring stage.
**Spec:** `docs/2026-05-27-pickability-followups/items/F4-spec.md`.

## Context

`src/irc/scoring/factors/thesis_news.py::score_thesis_news` ships a real keyword-based rubric: positive/negative lexicons in EN + ZH, a momentum formula `(pos - neg) / (pos + neg)`, and catalyst/risk count bonuses. The function is well-formed and unit-tested. Production output on `outputs/2026-05-27/scoring.json`, however, shows every instrument's `thesis_news` factor stuck at `50.0` — the empty-input fallback. The root cause is one literal: `src/irc/commands/score_cmd.py:69` passes `news_summaries={}` into `run_scoring`. Every per-instrument lookup resolves to the empty tuple, so the rubric never sees real prose.

Three decisions are non-obvious, expensive to reverse, and the product of real trade-offs:

1. **Keep the keyword rubric (position a); defer LLM scoring** — the alternative is to swap the rubric for an LLM call (position b/c), but the empty-input fallback alone explains 100 % of the observed "all-50" symptom. Upgrading before observing keyword-rubric behaviour with real input is premature.
2. **Static per-asset-class theme→asset-class mapping** — the alternative is per-instrument LLM classification, which would add a new LLM hop, break determinism, and require new tests at every universe expansion.
3. **Empty-input fallback preserved as a hard invariant** — the alternative is to invent a "no research yet" sentinel score (e.g. 40 or 60), which would silently bias picks during cold-start; preserving `50.0 + data_completeness=0.0` keeps the cold-start signal honest.

This ADR locks all three. A reviewer reading `src/irc/scoring/news_summaries.py`, `commands/score_cmd.py`, or `scoring/factors/thesis_news.py` six months from now should land here first.

## Decision

### 1. Position (a) — keep keyword rubric, defer LLM upgrade

The factor function `score_thesis_news` retains its existing keyword logic:

- `_POS = ("growth", "demand", "patience", "rally", "buy", "support", "强劲", "上行", "购金")`
- `_NEG = ("hike", "tighten", "outflow", "weak", "fall", "drag", "降息", "回撤", "撤资")`
- Momentum: `(pos - neg) / (pos + neg)`; base score: `50 + momentum * 30`; ±5 for ≥3 catalysts/risks.
- Empty-summary branch unchanged: `score=50.0, components={"data_completeness": 0.0, "neutral_default": 1.0}`.

The plumbing fix (F4) routes real `data/research/` theme reports into the existing function via a new `news_summaries` dict. **No rubric tuning, no lexicon expansion, no LLM hop.** All three are deferred to a SKIPPED follow-up entry `F4-followup-llm-rubric` and trigger only if post-implementation AC #4 (≥3 of top-10 picks differ by ≥10 points pairwise) fails on `outputs/2026-05-27/scoring.json`.

**Trade-offs considered:**
- *Alternative — LLM-scoring rubric (`thesis_news_scoring` task).* Rejected for V1: introduces an LLM hop on the hot scoring path, breaks the determinism contract (LLM outputs drift between runs unless temperature=0 and seed=fixed), and inflates the change surface beyond the MASTER-PLAN locked dep-scan.
- *Alternative — keyword lexicon tuning.* Rejected: even if review reveals weak ZH coverage, that's out of scope for F4. The empty-input fallback is the bottleneck; the lexicon may be perfectly fine once given real content.

### 2. Theme→asset-class mapping is static, deterministic, and asset_class-only

The mapping function `themes_for_instrument(asset_class: str) -> tuple[str, ...]` in `src/irc/scoring/news_summaries.py` returns a sorted, stable tuple of theme names. Keyed off the **real seven `asset_class` values** present in `config/universe/*.yaml`:

| `asset_class` | Mapped themes (sorted ASC) |
|---|---|
| `gold` | `(geopolitics, gold_drivers, us_monetary)` |
| `cn_equity_fund` | `(cn_equity_property_policy, cn_monetary, holdings_sector)` |
| `cn_etf` | `(cn_equity_property_policy, cn_monetary, holdings_sector)` |
| `cn_bond_fund` | `(cn_monetary,)` |
| `hk_etf` | `(cn_equity_property_policy, cn_monetary, geopolitics, holdings_sector)` |
| `us_etf` | `(geopolitics, us_fiscal_politics, us_monetary)` |
| `qdii_global` | `(geopolitics, us_fiscal_politics, us_monetary)` |
| anything else (unknown) | `()` |

**Storage:** module-level `MappingProxyType` (mirrors `FRESHNESS_DAYS_BY_THEME` in `theme_research.py`) so the mapping is immutable at import time.

**Why `market` is not in the signature:** `cn_on_exchange` vs `cn_off_exchange` does not change which macro themes are thematically relevant to an instrument. Adding `market` would introduce an unused knob.

**Why unknown asset_class returns empty tuple (silent):** a new asset_class added to `config/universe/` should not crash the scorer. The empty tuple correctly falls back to the neutral-50 invariant. A non-fatal log line at the command edge can surface unknown classes for ops awareness; the pure mapping function itself never logs.

**Trade-offs considered:**
- *Alternative — LLM classifier picks themes per instrument.* Rejected: adds an LLM hop just to choose a theme, fragile, non-deterministic.
- *Alternative — ship all themes to every instrument.* Rejected: destroys differentiation between asset classes (a bond fund should not score against US fiscal news).
- *Alternative — per-row metadata column in the universe YAML.* Rejected: schema sprawl, every new theme requires a universe-config migration. Static mapping is deterministic, cheap, and amends here in this ADR.

### 3. Empty-input fallback invariant preserved

When `news_summaries.get(iid, ())` returns the empty tuple — either because (a) the asset_class has no mapped themes, (b) all mapped theme reports failed (non-empty `failure_reason`), or (c) no research has run yet (cold start) — `score_thesis_news` returns:

```python
FactorScore(score=50.0, raw_refs=raw_refs,
            components={"data_completeness": 0.0, "neutral_default": 1.0})
```

unchanged from the pre-F4 behaviour. Existing test `tests/scoring/factors/test_thesis_news.py::test_no_news_returns_neutral_with_low_completeness` stays green without modification. Cold-start production output is therefore identical to pre-F4 — F4 only changes the warm-state output where `data/research/` exists.

### 3a. Prose-extraction invariant — keyword rubric scores prose only (ADR amendment, 2026-05-27)

`_summary_for_theme` in `src/irc/scoring/news_summaries.py` MUST strip the
`# <theme>` heading and the `## Citations` footer before returning the summary
string. When `load_theme_reports` reads persisted `.md` files from disk the
`report_md` field contains the full `format_report_markdown` output (heading +
prose + citation lines). Passing that raw string to `score_thesis_news` causes
citation titles and URLs to be matched against the keyword lexicon, producing
false positive/negative counts.

**Single source of truth:** `extract_prose_from_report_md(report_md: str) -> str`
in `src/irc/research/persistence.py`. Both `news_summaries._summary_for_theme`
and `gold_cmd._summary_from_theme_report` MUST call this helper — not inline
equivalent logic. Regression-tested in
`tests/scoring/test_news_summaries.py::test_build_news_summaries_strips_header_and_citation_footer`.

### 4. Determinism contract — two runs over same inputs → byte-identical `scoring.json`

The plumbing chain MUST be deterministic end-to-end:

1. `load_theme_reports(root)` reads `data/research/research_status.json` in a stable order (the file is JSON, iterated as a `themes` list — order is preserved).
2. `themes_for_instrument(asset_class)` returns a sorted tuple from a `MappingProxyType` (no shuffling, no hash-based ordering).
3. `build_news_summaries(reports, watchlist)` iterates the watchlist in DataFrame row order (CSV row order, deterministic). Within each row, themes are looked up in the **sorted** order returned by `themes_for_instrument`. Empty/failed reports are skipped silently. The output per-instrument tuple is sorted by theme name ASC.
4. `score_thesis_news` is pure arithmetic over the input tuple — order-dependent only on `_POS`/`_NEG` matching, which is deterministic.

Locked by a new test `tests/scoring/test_news_summaries_determinism.py` that runs `run_score` twice against the same `data/research/` fixture and asserts byte-identical `outputs/<date>/scoring.json`.

**Trade-offs considered:**
- *Alternative — order summaries by report freshness or citation count.* Rejected: introduces a non-stable secondary key (freshness ties produce non-deterministic ordering). Theme-name ASC is the only stable canonical order.

### 5. Deferred-to-SKIPPED if rubric inadequate

If post-implementation `outputs/2026-05-27/scoring.json` shows fewer than 3 of the top-10 picks differing by ≥10 points pairwise (AC #4 of the F4 spec), a new SKIPPED entry is added to `docs/2026-05-27-pickability-followups/SKIPPED.md`:

```
F4-followup-llm-rubric
Reason: keyword rubric did not differentiate top-10 picks after real research content
was wired in (AC #4 failed). Upgrade to LLM-scoring task captured for a future run.
Unblock path: define `thesis_news_scoring` task in config/llm.yaml; replace
score_thesis_news with an LLM-routed scorer that consumes the same news_summaries
input and returns the same FactorScore shape (so call-site contract is stable).
```

AC #4 is therefore **measured rather than passed** in F4's verdict. The contingency was already documented in MASTER-SPEC §"Known risks" and the F4 spec's open-question Q8.

## Non-goals (locked)

- **No `thesis_state` mutation.** `OpportunityRow.thesis_state` is set exclusively by `derive_thesis_from_evidence`. F4's factor-score change is purely numeric and feeds `compose_score` only.
- **No new citation rows.** F4 adds no `[ref:...]` markers to opportunity or memo outputs. The 16-hex `citation_id` format from ADR 0001 is unchanged.
- **No new I/O surface.** `load_theme_reports` already exists; F4 reuses it. `build_news_summaries` is a pure function with no filesystem access.
- **No AkShare / web-search calls.** The "no `基金概况` indicator" invariant from CONTEXT.md is preserved by construction (F4 introduces no fetch code).
- **No memo / opportunity / discipline surface changes.** F5/F6 own those surfaces in this same run.

## Consequences

**Positive:**
- The thesis_news factor finally differentiates picks based on real macro/theme news instead of returning 50.0 for everyone.
- The mapping is cheap to amend — adding a new asset_class or theme is a one-line PR against this ADR + the `MappingProxyType` table.
- Determinism is preserved end-to-end — two-run byte equality of `scoring.json` holds and is regression-tested.
- The keyword rubric is left untouched, so the existing factor test suite continues to validate the math.

**Negative (acknowledged):**
- The keyword rubric's quality is bounded by `_POS` / `_NEG` lexicon coverage. ZH coverage is admittedly thin (9 terms each). If AC #4 fails, the deferred LLM upgrade is the unblock — but the cost is a future ADR amending §1 of this one.
- The theme→asset-class mapping is hardcoded. Future asset_class additions need an ADR amendment; silently adding a row would surprise the next reader.
- Cold-start behaviour is unchanged from pre-F4 (every instrument scores 50.0). Operators running `irc score` without first running `irc research` see no improvement.

## Related ADRs

- [ADR 0001 — citation data model](0001-citation-data-model.md): the `citation_id` format is untouched; F4 emits no new citations.
- [ADR 0002 — active-fund fetch engine](0002-active-fund-fetch-engine.md): the fetch-budget contract is preserved (F4 reads cached research only, no AkShare).
- [ADR 0003 — failure-mode + Policy B](0003-failure-mode-policy-b.md): `thesis_state` is set only by `derive_thesis_from_evidence`. F4's scoring change does NOT cross this boundary.
- [ADR 0004 — renderer determinism + alias policy](0004-renderer-determinism-and-alias-policy.md): SAME-3 / H3 invariants are unaffected.
- `docs/2026-05-27-pickability-followups/items/F4-spec.md`: the implementation spec this ADR governs.
- CONTEXT.md "Thesis-news scoring" — the four glossary terms (`news_summaries`, `themes_for_instrument`, theme→asset-class mapping table, `build_news_summaries`).
