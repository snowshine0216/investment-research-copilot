# F4 — `thesis_news` real-content scoring (replace 50-default across the board)

**Run**: `2026-05-27-pickability-followups`
**Origin**: `docs/2026-05-27-instrument-pickability/SKIPPED.md` F4
**Phase**: spec (Opus brainstorming)
**Locked dep-scan write surface** (from MASTER-PLAN):
`src/irc/scoring/pipeline.py`, `src/irc/scoring/factors/thesis_news.py`,
`src/irc/commands/score_cmd.py`, `docs/adr/0007-thesis-news-scoring.md`,
secondary: `src/irc/templates/config/scoring.yaml`, `tests/scoring/factors/`.

---

## Goal

Make `thesis_news` actually differentiate picks instead of returning the empty-input
fallback of `50.0` for every instrument. The factor function
`src/irc/scoring/factors/thesis_news.py::score_thesis_news` already implements a
real keyword-based rubric (positive/negative lexicons in EN + ZH, momentum
formula, catalyst/risk counts). Production hits the neutral fallback because
`src/irc/commands/score_cmd.py:69` calls `run_scoring` with `news_summaries={}`,
so the call site at `src/irc/scoring/pipeline.py:117` resolves
`news_summaries.get(r.instrument_id, ())` to the empty tuple for every row.
This item is therefore **primarily a plumbing fix**: load already-persisted
research summaries (`data/research/*.md` via `load_theme_reports`) and route
them to the scoring call via a deterministic per-asset-class theme mapping. The
existing keyword rubric stays as-is; tuning the rubric (or upgrading to
LLM-scoring) is explicitly deferred to a follow-up SKIPPED entry.

## Reconciliation with `SKIPPED.md` F4

`SKIPPED.md` framed F4 as "real differentiation requires news-content scoring
against thesis keywords — an LLM-scoring task". The actual code shows the
factor function is already keyword-based and works once given real input. The
spec therefore picks **position (a)**: keep the existing keyword rubric, wire
real news content into the call site, and defer any LLM-scoring upgrade. If
post-implementation observation (the run-level verify against
`outputs/2026-05-27/`) shows the keyword rubric still fails to differentiate
≥3 of top-10 picks by ≥10 points, a new SKIPPED entry
(`F4-followup-llm-rubric`) captures the LLM-scoring upgrade for a separate
run. The rationale for (a) over (b/c) is that the empty-input fallback alone
explains 100% of the observed "all-50" symptom — there is no evidence the
rubric itself is the bottleneck until real content flows through it.

---

## Acceptance criteria

Each item below is independently verifiable by the post-ship `/verify` and the
unit-test suite. All must be green.

1. **Plumbing — `score_cmd.run_score` builds `news_summaries` from disk.**
   `news_summaries: dict[str, tuple[str, ...]]` passed to `run_scoring` is
   non-empty when `data/research/research_status.json` exists and at least one
   theme report has non-empty `report_md`. The dict is keyed by
   `instrument_id` (every watchlist row gets a key, possibly mapped to an
   empty tuple when the asset class has no mapped themes).

2. **Mapping — deterministic per-asset-class theme assignment exists as a
   pure function.** A new pure function (proposed name
   `themes_for_instrument(asset_class: str, market: str) -> tuple[str, ...]`)
   lives in `src/irc/scoring/news_summaries.py` (or a similarly-named module
   under `src/irc/scoring/`, file < 200 lines). It returns a sorted, stable
   tuple of theme names from the fixed set
   `{us_monetary, us_fiscal_politics, cn_monetary, cn_equity_property_policy,
   geopolitics, gold_drivers, holdings_sector}`. Mapping rules are defined
   in the spec table below and locked in ADR 0007.

3. **Content source — research reports load via the existing
   `load_theme_reports` API.** No new I/O surface is introduced for this
   item. The function `build_news_summaries(reports: dict[str, ThemeReport],
   watchlist: pd.DataFrame) -> dict[str, tuple[str, ...]]` is pure (no
   filesystem access inside it; reports are loaded by the command layer and
   passed in).

4. **Production differentiation.** After regenerating `scoring.json` against
   the cached `data/research/` corpus on `2026-05-27`, at least **3 of the
   top-10 picks have `thesis_news` factor scores that differ by ≥10 points**
   from at least one other top-10 pick (measured pairwise). This is the
   MASTER-SPEC §run gate item 1 verbatim.

5. **Empty-input invariant preserved.** When `news_summaries.get(iid, ())`
   returns the empty tuple, `score_thesis_news` returns `score=50.0,
   components={"data_completeness": 0.0, "neutral_default": 1.0}` — unchanged
   from current behaviour. Existing test
   `tests/scoring/factors/test_thesis_news.py::test_no_news_returns_neutral_with_low_completeness`
   stays green without modification.

6. **Determinism.** Two consecutive `uv run irc run --only score`
   invocations against the same `data/research/` snapshot produce
   byte-identical `outputs/<date>/scoring.json` files. Captured as a new
   integration test under `tests/scoring/` that compares two SHA-256 digests.

7. **Tests cover the new code paths (TDD).** New unit tests under
   `tests/scoring/test_news_summaries.py` cover: (i) `themes_for_instrument`
   for every documented asset_class × market combination present in
   `config/universe/` (parametrised); (ii) `build_news_summaries` returns
   empty tuple for missing themes; (iii) `build_news_summaries` produces
   identical output for identical inputs (pure-function property); (iv) the
   `score_cmd.run_score` integration test asserts the dict passed to
   `run_scoring` is non-empty when research fixtures exist. All tests
   written **before** implementation per CLAUDE.md TDD rule.

8. **ADR 0007 lands with this item.** A new
   `docs/adr/0007-thesis-news-scoring.md` documents: the keyword-rubric
   decision (and what defers the LLM upgrade), the theme→asset-class
   mapping rules, the determinism contract, the empty-input fallback
   invariant, and the relationship to the `thesis_state` setter rule from
   CONTEXT.md (F4 does **not** touch `thesis_state` — set only by
   `derive_thesis_from_evidence`). Grill phase finalizes ADR text inline.

9. **No regression in IRC_*_BEGIN/END markers or H3/SAME-3 invariants.**
   The publishable-set lockdown integration test
   (`tests/integration/test_publishable_set_lockdown.py` per CONTEXT.md)
   stays green. F4 changes scoring only; it does not touch
   `_write_opportunity_outputs`, `thesis_evidence`, or memo renderers.

10. **The `news_summaries={}` literal disappears from
    `commands/score_cmd.py`.** Greppable acceptance: `grep -n
    "news_summaries={}" src/irc/commands/score_cmd.py` returns no match.

### Theme → asset-class mapping (locked here; ADR 0007 captures the same table)

| `asset_class` (canonical) | Mapped themes (sorted) |
|---|---|
| `gold` / `gold_etf` / `gold_proxy` | `gold_drivers`, `us_monetary` |
| `cn_a_broad`, `cn_a_sector`, `cn_a_smart_beta` | `cn_equity_property_policy`, `cn_monetary`, `holdings_sector` |
| `cn_bond` / `cn_money_market` | `cn_monetary` (single theme; bonds rarely differentiate on news) |
| `qdii_us` / `qdii_global` | `geopolitics`, `us_fiscal_politics`, `us_monetary` |
| `qdii_hk` | `cn_equity_property_policy`, `cn_monetary`, `geopolitics` |
| anything else (unmapped) | empty tuple (falls back to neutral 50.0; documented in ADR) |

Sorted-tuple output guarantees that mapping changes are visible in diffs and
that two-run byte equality holds.

---

## Non-goals

1. **LLM-scoring upgrade.** No `irc.llm` task routing changes, no new
   `thesis_news_scoring` LLM task. Position (a) is locked; (b) is deferred
   to a `F4-followup-llm-rubric` SKIPPED entry if AC #4 fails.
2. **Keyword lexicon tuning.** `_POS` / `_NEG` in
   `scoring/factors/thesis_news.py` stay untouched. Even if review reveals
   weak ZH coverage, that's out of scope for F4.
3. **Per-instrument live news fetch.** No new AkShare / web-search calls.
   F4 reads only what `data/research/` already persists.
4. **Memo / opportunity surface changes.** No edits to
   `_write_opportunity_outputs`, `thesis_evidence`, `evidence_pool`, or
   memo renderers. (F5/F6 own those surfaces in this same run; F4 must
   not encroach.)
5. **New citation rows.** No `[ref:...]` additions to opportunity or memo
   evidence pools. F4 affects `scoring.json` only.
6. **`thesis_state` semantics.** Untouched. Set exclusively by
   `derive_thesis_from_evidence` per CONTEXT.md. F4 only adjusts the
   numeric factor score that feeds `compose_score`.
7. **`scoring.yaml` weight changes.** The 5-factor weight scheme stays
   exactly as it is on `main`. F4 changes inputs, not weights.
8. **Multi-stage pipeline orchestration.** F4 lives in `score_cmd` only;
   no changes to `irc.cli`, `pipeline_state`, `pipeline_outputs`, or
   `pipeline_halt`.

---

## Constraints

1. **TDD mandatory** (CLAUDE.md "All coding must follow TDD"). Every new
   function lands red-first: write `tests/scoring/test_news_summaries.py`
   asserting `themes_for_instrument` and `build_news_summaries` behaviour
   before either function exists. Existing
   `tests/scoring/factors/test_thesis_news.py` stays green throughout.

2. **`thesis_state` invariant** (CONTEXT.md "Policy B" / ADR 0003 /
   `_write_opportunity_outputs` rules). `OpportunityRow.thesis_state` is
   set **only** by `derive_thesis_from_evidence` — F4 must not introduce
   any code path that mutates `thesis_state`. The factor score change is
   purely numeric and feeds `compose_score`.

3. **Citation-ID format** (ADR 0001). N/A directly — F4 introduces no new
   evidence rows — but if implementation reveals a need to emit citation
   refs from the theme reports into `scoring.json`, the format
   `\[ref:[0-9a-f]{16}\]` is the only legal shape. Default is "no new
   citations" per non-goal #5.

4. **FP / immutable** (CLAUDE.md "Functional, immutable"). New code is
   pure functions: `themes_for_instrument` and `build_news_summaries`
   take inputs, return new values, mutate nothing. No module-level mutable
   state, no class wrappers. Theme mapping is a frozen dict
   (`MappingProxyType` like `FRESHNESS_DAYS_BY_THEME` in
   `theme_research.py`).

5. **Determinism is required** (orchestrator instruction; reinforced by
   AC #6). The news-summaries source MUST produce the same content on
   two consecutive runs over the same `data/research/`. This rules out
   shuffling, hash-based ordering using non-stable hashes, and any
   timestamp-influenced selection. Use sorted tuples.

6. **Effects at edges** (CLAUDE.md). `load_theme_reports` (filesystem
   read) stays in `research/persistence.py`. `score_cmd.run_score` calls
   it. `build_news_summaries` and `themes_for_instrument` are pure.

7. **File / function size budget**. New module < 200 lines. Each function
   < 20 lines (ideal). `themes_for_instrument` and
   `build_news_summaries` are both small enough naturally.

8. **No `基金概况` indicator** (CONTEXT.md "Things you'll trip over").
   Irrelevant to F4 (no fetch code), but the acceptance grep test
   continues to pass since F4 introduces no AkShare calls.

9. **Run-level branch / PR shape** (MASTER-PLAN). Branch
   `claude/pickability-followups-F4` is cut off
   `autodev/pickability-followups-feature`. PR opens against the feature
   branch, not `main`. Squash-merge after all 6 verdict files PASS.

---

## Open questions resolved during brainstorming

### Q1 — Position on keyword vs LLM scoring (the SKIPPED.md reconciliation)

**Resolved: (a) keep keyword + wire it; defer LLM to follow-up SKIPPED entry.**

Rationale: the empty-input fallback (50.0 for every pick because
`news_summaries={}`) is sufficient to explain 100% of the observed "no
differentiation" symptom. There is no evidence the existing keyword rubric is
inadequate until real content flows through it. Upgrading to LLM-scoring
without first observing keyword behaviour with real input is premature
optimisation and would inflate the change surface beyond the MASTER-PLAN
locked dep-scan. If AC #4 fails post-implementation, a new SKIPPED entry
`F4-followup-llm-rubric` captures the LLM upgrade for a future run.

### Q2 — Per-instrument news source: live fetch vs theme reports?

**Resolved: theme reports from `data/research/` via `load_theme_reports`.**

Live per-instrument fetch (e.g., AkShare news per ticker) was rejected
because: (i) introduces non-determinism (live data changes between runs,
violating AC #6); (ii) introduces a new I/O surface against the
project's "effects at edges" rule; (iii) AkShare per-ticker news is
already known-flaky from prior items. Theme reports are already
generated, persisted to disk, and read in other parts of the pipeline.

### Q3 — How to map themes to instruments without instrument-level metadata?

**Resolved: static per-asset-class mapping (see table above).**

Considered alternatives: (i) classify each instrument's name with an
LLM — rejected: adds an LLM hop just to pick a theme, fragile,
non-deterministic; (ii) ship all themes' content to every instrument —
rejected: destroys differentiation between asset classes; (iii) per-row
metadata column in the universe YAML — rejected: schema sprawl, every
new theme requires a universe-config migration. Static mapping is
deterministic, cheap, and easy to amend in ADR 0007.

### Q4 — Should holdings_sector content (which is generated from user's
actual holdings) flow into instruments matching those holdings or all
CN-A instruments?

**Resolved: all CN-A instruments receive `holdings_sector` content.**

The `holdings_sector` theme is already CN-equity-flavoured (built from
user holdings, which are mostly CN-A funds). Routing it to all CN-A
funds gives every CN-A pick a chance to react to user-relevant sector
news. This is a simplification — a future improvement could filter by
overlap of `tracked_index` with the user's holdings — but that's out of
scope per non-goal #1.

### Q5 — Do we need a new ADR or is amending an existing one enough?

**Resolved: new ADR 0007.**

MASTER-PLAN dep-scan already declared
`docs/adr/0007-thesis-news-scoring.md` as a write surface. Existing
ADRs cover citation model (0001), fetch engine (0002), Policy B (0003),
renderer determinism (0004) — none of them touch scoring rubrics, so a
new ADR is the cleanest landing. The grill phase will draft the ADR
text inline; spec only locks the scope and the keyword-first decision.

### Q6 — Two-run byte equality test: where does it live?

**Resolved: `tests/scoring/test_news_summaries_determinism.py` (new
file), using a small captured `data/research/` fixture.**

Captured fixture (2 themes × short report_md) lives under
`tests/scoring/fixtures/research/`. Test runs `run_score` twice against
the same fixture and asserts byte-identical `scoring.json`. Lives in
tests/, not under `tests/integration/`, because no real DuckDB is hit —
the fixture is small enough to keep this a unit-ish test.

### Q7 — What happens when no research has been run yet (cold-start
state)?

**Resolved: `news_summaries` becomes `{iid: () for iid in watchlist}`
(or equivalently `{}` — the call site treats both identically). Every
instrument falls back to 50.0. This is acceptable cold-start behaviour
and identical to today's production state; F4 only changes the
warm-state behaviour where research outputs exist.**

### Q8 — Could not resolve from MASTER-SPEC + code anchors alone

**None.** All eight design questions have been resolved with code +
docs evidence. The grill phase may still surface refinements (e.g., the
exact ADR wording, whether `qdii_hk` should map to `geopolitics` or
not), but those are tuning, not blockers. If the grill phase discovers
that the captured `data/research/` corpus on `2026-05-27` is too sparse
to satisfy AC #4 (i.e., even after plumbing, top-10 picks still cluster
within ±5 of 50), the spec falls back to AC #4 being **measured**
rather than **passed** — and a SKIPPED entry captures the LLM upgrade.
That contingency is documented in MASTER-SPEC §"Known risks" already.
