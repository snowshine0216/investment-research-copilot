# ADR 0004 — Renderer determinism + alias-builder collision policy + SAME-3 invariant

**Status:** Accepted (2026-05-23, item 007)
**Supersedes:** none. Builds on [ADR 0001 — citation data model](0001-citation-data-model.md), [ADR 0002 — active-fund fetch engine](0002-active-fund-fetch-engine.md), [ADR 0003 — failure-mode + Policy B](0003-failure-mode-policy-b.md).
**Spec:** `docs/2026-05-22-thesis-cards-evidence-gap/items/007-spec.md`

## Context

Item 007 is the renderer slice: `memo.md` evidence pool + `[stock:{symbol}] [ref:{citation_id}]` markers, `discipline_report.md` nested thesis_evidence bullets + inline top-5 holdings + `## 持仓明细` appendix, and the new `src/irc/memo/aliases.py` alias-builder consumed by item 009's `find_uncited_conclusions`.

Three contracts are non-obvious, expensive to reverse, and the product of real trade-offs:

1. **`ConstituentAliases` shape — `frozenset[tuple[str, str]]` (NOT `list` or `sorted tuple`).** The choice affects determinism, mutation safety, and traversal idioms across every downstream consumer.
2. **`InstrumentAliasCollisionError` raised at BUILD time (NOT lazy at lookup).** Determines whether collision is loud-fast or silent-flaky.
3. **SAME-3 invariant across three rendering surfaces.** Picks-table, evidence-pool, and discipline nested bullets MUST emit the same 3 `citation_id`s per row. Pre-filter discipline at the consumer level (the "obvious" optimisation) silently breaks this.

This ADR locks all three. Reviewers reading `aliases.py`, `evidence_pool.py`, `report.py::_render_section`, or `report.py::_render_appendix_section` six months from now should land here.

## Decision

### 1. `ConstituentAliases` is `dict[str, frozenset[tuple[str, str]]]` — multi-owner via frozenset; mandatory sort at traversal

Type:

```python
ConstituentAliases = dict[str, frozenset[tuple[str, str]]]
# stock identifier (symbol OR name_cn) → frozenset of (instrument_id, constituent_key)
```

A multi-owner stock (e.g. `贵州茅台 / 600519` held by both `005827` and `163417`) accumulates a 2-tuple frozenset:

```python
constituent_aliases["600519"] == frozenset({("005827", "600519"), ("163417", "600519")})
constituent_aliases["贵州茅台"] == frozenset({("005827", "600519"), ("163417", "600519")})
```

**Storage is order-free** (frozenset). The map is in-memory only, never serialised — there is no JSON/YAML round-trip that would require a canonical order at storage time. Determinism is enforced at the **traversal boundary** instead:

> Any code path that traverses a `ConstituentAliases` frozenset AND its output (rendered string, audit finding, error message) participates in byte-equal regression contracts MUST `sorted(fs)` before iterating.

The canonical sort is `(instrument_id, constituent_key)` ascending. This includes:
- Item 009's `find_uncited_conclusions` when it emits `NumericFinding(kind="ambiguous_constituent_reference", evidence_excerpt=...)` — the excerpt joins sorted tuples.
- The renderer-side defensive logging if a multi-owner case ever surfaces during render (current spec emits no such logs — purity invariant — but the contract pre-empts future drift).
- Any test that asserts on `repr(fs)` or stringifies a frozenset.

**Trade-off considered:**

- *Alternative A — `sorted tuple[tuple[str, str], ...]`.* Rejected. Tuples are sequences; appending a new owner requires reconstructing a new sorted tuple on every insert during `build_alias_maps`. The build cost is amortised O(n log n) per multi-owner key vs O(1) for frozenset. More importantly, `tuple` traversal is order-preserving — a contributor who forgets that "the tuple is sorted by construction" can silently rely on insertion order in a downstream consumer, masking determinism bugs until the build order changes. Frozenset makes the unorderedness loud at every traversal.
- *Alternative B — `list[tuple[str, str]]`.* Rejected. Mutable. Violates the project-wide FP / immutability invariant from `~/.claude/CLAUDE.md`. A defensive `tuple(sorted(fs))` at every consumer is the same boilerplate either way; frozenset signals "this is set semantics, not sequence semantics" to the reader.
- *Alternative C — `dict[str, tuple[tuple[str, str], ...]]` with build-time canonical sort.* Rejected for the same insertion-cost reason as A, and because the API contract becomes "this is sorted iff `build_alias_maps` is the producer" — fragile to a future contributor producing the map from a different code path.

### 2. `InstrumentAliasCollisionError` raised at build time, not at lookup

The collision check is implemented as:

```python
def build_alias_maps(rows):
    working: dict[str, set[str]] = {}        # alias_key → set of instrument_ids
    for r in rows:
        for alias in (r.instrument_id, r.name_cn, ...):
            if not alias:
                continue
            working.setdefault(alias, set()).add(r.instrument_id)
    # Final pass: collapse + collision check.
    aliases: dict[str, str] = {}
    for alias, iids in working.items():
        if len(iids) > 1:
            raise InstrumentAliasCollisionError(
                f"alias {alias!r} resolves to multiple instrument_ids: "
                f"{sorted(iids)}"
            )
        aliases[alias] = next(iter(iids))
    return aliases, constituent_aliases
```

Two rows sharing the same `instrument_id` (a soft-collision — already a bug in item 006's H3 partition) accumulate into a `set` of size 1; no raise. The collision is HARD only when the alias-string resolves to two DIFFERENT `instrument_id` values.

**Trade-off considered:**

- *Alternative A — lazy raise at lookup site (item 009).* Rejected. Some runs would pass (no paragraph in `memo.md` mentions the colliding name) and some would fail (a paragraph happens to mention it). Test flakiness across runs is the worst category of failure. Builder-time raise is loud-fast-deterministic.
- *Alternative B — silently keep the first occurrence; log a warning.* Rejected. Pure functions don't log. And "silently keep the first" turns a malformed `opportunity_report.json` into a silently-wrong audit (the paragraph's prose mention maps to the wrong fund's evidence). The whole point of the alias-builder is to make `find_uncited_conclusions` precise.
- *Alternative C — make the alias map a `dict[str, set[str]]` and let consumers handle the multi-id case.* Rejected. Pushes the collision semantics onto every consumer. Item 009 would then need its own collision raise. The cost of raising at one well-defined site (build_alias_maps) is much lower than the cost of every consumer carrying the burden.

### 3. SAME-3 invariant — three rendering surfaces consume `select_citations` directly with no pre-filter

`select_citations(row.thesis_evidence, cap=3)` is called from THREE producers:

1. `_build_pick_rows` (item 002, shipped) — populates `PickRow.citations` for the memo picks-table.
2. `build_evidence_pool` (item 007, this slice) — emits `[stock:...] [ref:...]` lines after the state-codes line.
3. `_render_section` (item 007, this slice) — emits nested `- [ref:...] {type} · {source} · {date}` bullets under discipline-report row lines.

**Locked invariant:** all three consumers receive the IDENTICAL `tuple[ThesisEvidence, ...]` for a given row, with NO pre-filtering or pre-sorting at the consumer level. The selector is the single locus of any future filter (e.g. "drop URL-less entries", "exclude `scope=asset_class_macro`"). Locked by a regression test in `tests/memo/test_evidence_pool.py` that takes 8 entries, runs all three code paths, and asserts byte-equal `citation_id` sets.

**Trade-off considered:**

- *Alternative — discipline renderer pre-filters to constituent-scope entries only (since active-fund rows have flattened constituent evidence in `thesis_evidence`).* Rejected. Breaks the invariant silently — picks-table would show 3 citations, discipline would show different 3 citations, evidence-pool would show yet another 3. The audit (item 009's `find_uncited_discipline_rows`) couldn't reason about cross-surface citation consistency.
- *Alternative — pass `(citations_already_selected_by_caller,)` to each renderer.* Rejected. Tighter coupling at the call site. The renderer would not be a self-contained pure function — every call site would need to thread the selector output through. Calling `select_citations` inside the renderer is O(n log n) per row, well within the perf budget, and keeps the renderer composable.

## Consequences

**Positive:**
- Two memo runs over the same `opportunity_report.json` produce byte-identical `memo.md` and `discipline_report.md` (locked by AC25, AC26, AC27).
- The three citation-rendering surfaces never drift: any test that fails the SAME-3 invariant fails immediately, not weeks later when an audit catches a paragraph mismatched against picks.
- A future contributor introducing a multi-owner stock (e.g. a new fund universe overlap) gets a frozenset of size > 1 — no schema change, no migration, no audit-finding emission until item 009's lookup logic decides whether disambiguation is possible.
- Builder-time collision raise means malformed upstream data (duplicate `name_cn` across unrelated funds) fails the run loudly, with both `instrument_id` values in the error message — the operator sees the bug in `opportunity_report.json` directly.

**Negative (acknowledged):**
- Every traversal of a `ConstituentAliases` frozenset that affects output ordering must `sorted(fs)` — easy to forget. Mitigated by: (a) the CONTEXT.md "Determinism rule" entry, (b) item 007's tests assert on rendered strings (which would fail if a future contributor relied on frozenset iteration order in a renderer), (c) item 009 owns the lookup site and is the most likely consumer to break this — its own tests must include a multi-owner fixture.
- The SAME-3 invariant prevents per-surface filtering optimisations. If a future contributor wants the discipline report to show different evidence than the picks-table (e.g. emphasise data-leg in picks, info-leg in discipline), they cannot add a consumer-side filter — the change MUST go inside `select_citations` (which would then need a per-surface mode parameter). Acknowledged: the invariant is the right default; per-surface modes are a future ADR if the need arises.
- Build-time collision raise can abort a memo run on a malformed `opportunity_report.json` that previously rendered (incorrectly) without complaint. The first run after item 007 lands may fail on legacy data with `name_cn` duplicates. Mitigation: the error message names both `instrument_id` values, and the operator's fix is a one-line edit in the source data.

## Related ADRs

- [ADR 0001 — citation data model](0001-citation-data-model.md): defines `citation_id` as 16 hex chars and the `select_citations` selector's determinism contract (§3). This ADR's SAME-3 invariant is the consumer-side companion: the selector is deterministic, so to keep the rendered outputs identical, the consumers must call it with identical input.
- [ADR 0002 — active-fund fetch engine](0002-active-fund-fetch-engine.md): defines `ConstituentAnalysis` shape and the flattened `OpportunityRow.thesis_evidence` for active-fund rows. The renderer's behaviour on multi-owner stocks (same constituent in two funds with different `one_line_view`) is governed by the per-fund subsection structure of the `## 持仓明细` appendix.
- [ADR 0003 — failure-mode + Policy B](0003-failure-mode-policy-b.md): the three-field failure taxonomy (`failure_reasons` / `evidence_gaps` / `audit_errors`) is what the appendix line-format precedence rules in CONTEXT.md ("Appendix line format precedence") render. The renderer never invents a sentinel; it dispatches on which field is non-empty.
