# Item 002 spec — citation-data-model (Slice D0 a–f + D1b)

## Goal

Install the unified citation provenance schema that every downstream slice (items 003–009) depends on. After this lands, every `ThesisEvidence` instance is content-addressed (sha256 → `citation_id`), tagged with `scope`, `citation_kind`, `owner_instrument_id`, `parent_fund_id`, and `constituent_key`, and rejects construction if any required field is missing. `_row_to_dict` carries the new schema into `opportunity_report.json` (along with item 001's `contributing_dimensions`), `DisciplineRow` carries gap state and provenance through to renderers, a new `select_citations` pure function gives picks-table (D0e) and evidence-pool (D1a) a single deterministic citation source, and `_build_pick_rows` cross-references `opportunity_report.json` so gapped or absent trade targets fall to a failure section instead of becoming uncited memo picks. The slice bundles D0a–D0f with D1b because §4 step 1 of the source diagnosis lands them as one bundle — the `citation_id`/`CitationMeta` schema and the selector that consumes it must reach the tree together or item 003's first commit cannot construct `ThesisEvidence` at all.

## In scope

### Schema additions

1. **`ThesisEvidence` (`src/irc/opportunity/types.py`)** — gains six required fields with `__post_init__` validation; existing five fields (`type`, `source`, `url`, `date`, `summary`) keep their semantics.
2. **`CitationMeta`** — new frozen dataclass in `src/irc/opportunity/types.py` carrying `{scope, citation_kind, owner_instrument_id, asset_class, parent_fund_id, constituent_key}`. All required; `asset_class` is the asset class of the row whose `instrument_id == owner_instrument_id` at the time `build_cited_map` runs.
3. **Type aliases** — in `src/irc/opportunity/types.py`: `CitedMap = dict[str, dict[str, CitationMeta]]` (`instrument_id → {citation_id: CitationMeta}`) and `ConstituentCitedMap = dict[str, dict[str, dict[str, CitationMeta]]]` (`instrument_id → constituent_key → {citation_id: CitationMeta}`).
4. **`DisciplineRow` (`src/irc/opportunity/types.py:160-169`)** — gains four trailing defaulted fields: `thesis_evidence: tuple[ThesisEvidence, ...] = ()`, `constituent_analyses: tuple[Any, ...] = ()` (typed `tuple[ConstituentAnalysis, ...]` once item 003 lands; until then the trailing default is `()` and the field accepts any tuple), `evidence_gaps: tuple[str, ...] = ()`, `fetch_types_attempted: tuple[str, ...] = ()`.

### New module

5. **`src/irc/memo/citation_selector.py` (new)** — single pure function `select_citations(entries: tuple[ThesisEvidence, ...], cap: int = 3) -> tuple[ThesisEvidence, ...]` shared by D0e (picks_table) and D1a (evidence_pool). Spec in "Selector algorithm" below.

### Serializer / propagator changes

6. **`_row_to_dict` (`src/irc/opportunity/report.py:15-32`)** — emit two new keys:
   - `"thesis_evidence": [asdict(e) for e in row.thesis_evidence]`
   - `"contributing_dimensions": sorted(list(row.contributing_dimensions))` (item 001 field; serialize sorted for determinism)
   - `"constituent_analyses": [asdict(c) for c in row.constituent_analyses]` (empty list until item 003 populates the field).
7. **`_discipline_row_from` (`src/irc/commands/opportunity_cmd.py:148-163`)** — propagate `row.thesis_evidence`, `row.constituent_analyses`, `row.evidence_gaps`, `row.fetch_types_attempted` into the `DisciplineRow`.

### PickRow + citation rendering

8. **`PickRow` (`src/irc/memo/picks_table.py:31-46`)** — gains `citations: tuple[ThesisEvidence, ...] = ()` (trailing defaulted so existing constructors keep working in tests).
9. **`render_picks_table`** — add a `证据` column to the table. Render each citation as `[ref:{citation_id}] {type}·{source}·{date}`. Multiple citations are joined by `<br>` so they render as a multi-line cell in markdown. Empty `citations` → cell renders `—`.

### `_build_pick_rows` rewrite

10. **`_build_pick_rows` (`src/irc/commands/memo_cmd.py:236-278`)** — full rewrite per "Gap-aware pick-row construction" below. Returns `(pick_rows, absent_targets, gapped_targets)` so the caller can emit two new failure-section markdown blocks. Caller (`run_memo`) renders those blocks **after** the picks table inside the same `memo.md` (`## 未能纳入精选：机会数据缺失` and `## 未能纳入精选：证据不足`) and the function never silently drops a trade target.

### Citation map + duplicate detector

11. **`build_cited_map` (`src/irc/opportunity/types.py` or `src/irc/opportunity/citation_map.py` — see "Files touched")** — pure function `build_cited_map(rows: tuple[OpportunityRow, ...]) -> CitedMap`. Iterates each row's `thesis_evidence`, asserts `e.owner_instrument_id == row.instrument_id`, builds `CitationMeta` using `row.asset_class`, and inserts under `cited_map[row.instrument_id][e.citation_id]`. Raises `RuntimeError` if any `citation_id` appears under two different `(owner_instrument_id, citation_id)` pairs (duplicate-id detector).
12. **Duplicate-citation-id detector** — same `RuntimeError` is raised inside `build_cited_map`. **Timing:** item 002 lands the schema and function; it is NOT called from any write path in this slice. Item 009 (D2c) and the audit gates will call `build_cited_map` immediately before any `atomic_write_text` of `opportunity_report.json` / `memo.md`, so a duplicate-id collision aborts the run before a polluted artifact reaches disk. This is documented as part of the audit-gate consumer contract (ADR 0001).

### All existing `ThesisEvidence(...)` call sites updated

Threading detail in "Threading provenance through existing producers" below. Enumerated sites (grep for `ThesisEvidence(`):

- `src/irc/opportunity/thesis_evidence.py:80` (`_filing_evidence`)
- `src/irc/opportunity/thesis_evidence.py:95` (`_broker_evidence`)
- `src/irc/opportunity/thesis_evidence.py:110` (`_news_evidence`)
- `tests/opportunity/test_report.py:74`
- `tests/opportunity/test_report.py:80`
- `tests/opportunity/test_cards.py:84`
- `tests/opportunity/test_cards.py:90`
- `tests/opportunity/test_types.py:73`
- `tests/opportunity/test_types.py:88` (loop creating 5 instances by kind)

## Out of scope

- **D1a (memo evidence_pool citation markers)** — item 007.
- **D1c (alias-builder, `find_uncited_conclusions` empty-map check)** — item 007.
- **D2 (audit gates `find_uncited_opportunity_rows`, `find_missing_pick_citations`, `find_hallucinated_citations`, `find_uncited_conclusions`, `find_uncited_discipline_rows`)** — item 009.
- **D3 (discipline `_render_section` evidence-bullet rendering, `## 持仓明细` appendix)** — item 007.
- **Any constituent-evidence fetching** — item 003.
- **Universal gapped-row skip in `_write_opportunity_outputs`** — item 006 (H3).
- **`IRC_CITATION_ENFORCE_MODE` env var, citation_audit.json shadow log** — item 009.

## Detailed schema specifications

### `ThesisEvidence` after this slice

```python
@dataclass(frozen=True)
class ThesisEvidence:
    # Existing fields (unchanged)
    type: ThesisEvidenceKind            # "filing" | "broker" | "news" | "policy" | "snapshot"
    source: str
    url: str
    date: str                            # ISO YYYY-MM-DD
    summary: str
    # New required provenance fields (no defaults)
    scope: Literal["instrument", "constituent", "asset_class_macro", "policy"]
    citation_kind: Literal["data", "information"]
    owner_instrument_id: str
    parent_fund_id: str | None
    constituent_key: str | None
    # Computed in __post_init__ from the preimage below
    citation_id: str = ""  # populated by __post_init__; never accept caller-supplied value

    def __post_init__(self) -> None:
        # Validation: all required strings non-empty; literals respected.
        if not self.owner_instrument_id:
            raise ValueError("ThesisEvidence.owner_instrument_id must be non-empty")
        if self.citation_kind not in ("data", "information"):
            raise ValueError(f"invalid citation_kind: {self.citation_kind!r}")
        if self.scope not in ("instrument", "constituent", "asset_class_macro", "policy"):
            raise ValueError(f"invalid scope: {self.scope!r}")
        if not self.type or not self.source or not self.date:
            raise ValueError("ThesisEvidence.type/source/date must be non-empty")
        # parent_fund_id and constituent_key may be None (fund-level evidence)
        # but the kw-arg must be supplied explicitly (no default).
        # Fallback when URL is empty: include summary[:64] to disambiguate
        # two empty-URL filings for the same source+date with different content
        # (e.g., two Sina filing digests for different fiscal periods on the
        # same publish date, neither carrying a public URL).
        canonical_id = self.url or f"{self.source}:{self.date}:{self.summary[:64]}"
        preimage = (
            f"{self.owner_instrument_id}:{self.scope}:"
            f"{self.constituent_key or ''}:{self.type}:"
            f"{canonical_id}:{self.date}"
        ).encode("utf-8")
        object.__setattr__(self, "citation_id",
                           hashlib.sha256(preimage).hexdigest()[:16])
```

**Hash preimage rationale.** The hash binds the citation to the instrument it was fetched for (`owner_instrument_id` — explicitly that field, NOT any other "instrument" id), the scope (so a fund-level NAV citation and a constituent-level filing can't collide on the same `type:source:date` tuple), the constituent (for stock-level evidence), the type, the canonical URL (or fallback `source:date:summary[:64]` when URL is empty — e.g., two Sina filing digests for different fiscal periods of the same constituent on the same filing date), and the date. **Invariant:** 16 hex chars = 64 bits ⇒ birthday-paradox collision probability for ≤100k citations in a single run ≈ 2.7e-10. Acceptable, and the `build_cited_map` duplicate-id detector raises immediately if a collision ever fires. Documented as an explicit run-time invariant — not a probabilistic best-effort.

**Computed-field semantics.** `citation_id` is declared as a trailing field with default `""` so `dataclasses.asdict` includes it and YAML/JSON serializers emit it. `__post_init__` overwrites the empty default via `object.__setattr__` (required for frozen dataclasses). Callers MUST NOT pass `citation_id=` as a kwarg; if they do, it is silently overwritten — the producer is the construction-time hash, not the call site.

### `CitationMeta`

```python
@dataclass(frozen=True)
class CitationMeta:
    scope: Literal["instrument", "constituent", "asset_class_macro", "policy"]
    citation_kind: Literal["data", "information"]
    owner_instrument_id: str
    asset_class: str
    parent_fund_id: str | None
    constituent_key: str | None
```

All required. `asset_class` is required because D1b's portfolio-section audit (item 007/009) needs to reject "gold citation under `## CN权益基金`" from `CitationMeta.asset_class` alone, without alias lookup.

### Type aliases

```python
CitedMap = dict[str, dict[str, CitationMeta]]
ConstituentCitedMap = dict[str, dict[str, dict[str, CitationMeta]]]
```

### `DisciplineRow` after this slice

```python
@dataclass(frozen=True)
class DisciplineRow:
    instrument_id: str
    name_cn: str
    asset_class: str
    theme: str | None
    opportunity_state: OpportunityState
    dca_action: DcaAction
    risk_action: RiskAction
    note_cn: str
    # New trailing defaulted fields
    thesis_evidence: tuple[ThesisEvidence, ...] = ()
    constituent_analyses: tuple[Any, ...] = ()  # typed once item 003 lands
    evidence_gaps: tuple[str, ...] = ()
    fetch_types_attempted: tuple[str, ...] = ()
```

## Selector algorithm (D0f)

`select_citations(entries: tuple[ThesisEvidence, ...], cap: int = 3) -> tuple[ThesisEvidence, ...]`

**Sort key per entry** (descending priority on each tuple field):

```
(scope_rank, kind_rank, holding_weight_pct, iso_date_recency, citation_id_asc)
```

- `scope_rank`: `instrument` → 2, `constituent` → 2, `asset_class_macro` → 1, `policy` → 1.
- `kind_rank`: `data` → 2, `information` → 1 (used **only** to break ties when ranking inside a slot; cross-slot ranking ignores it — the two slots are filled separately).
- `holding_weight_pct`: `float`. For instrument-scoped entries → `0.0`. For constituent-scoped entries → the `weight_pct` from the `ConstituentAnalysis` that produced the evidence; for V1 (before item 003), constituent evidence does not exist yet, so this is always `0.0`.
- `iso_date_recency`: the `date` string; newer wins via direct lexicographic descending compare (`YYYY-MM-DD` strings are correctly ordered by string compare).
- `citation_id_asc`: the `citation_id` string; final tie-breaker, lexicographic ascending — guaranteed deterministic across runs because the id is content-addressed.

**Selection algorithm:**

```python
def select_citations(entries, cap=3):
    if not entries or cap <= 0:
        return ()

    def slot_key(e):
        # Cross-slot ranking ignores kind_rank.
        return (
            _scope_rank(e.scope),
            e.holding_weight_pct if hasattr(e, "holding_weight_pct") else 0.0,
            e.date,                  # used for desc compare via negation pattern
            e.citation_id,
        )

    # 1. Data slot: highest-ranked entry with citation_kind == "data" AND
    #    scope in {"instrument", "constituent"}.
    data_candidates = [e for e in entries
                       if e.citation_kind == "data"
                       and e.scope in ("instrument", "constituent")]
    data_pick = max(data_candidates, key=slot_key, default=None) \
        if data_candidates else None

    # 2. Info slot: highest-ranked entry with citation_kind == "information".
    info_candidates = [e for e in entries if e.citation_kind == "information"]
    info_pick = max(info_candidates, key=slot_key, default=None) \
        if info_candidates else None

    selected = []
    if data_pick is not None:
        selected.append(data_pick)
    if info_pick is not None and info_pick is not data_pick:
        selected.append(info_pick)

    # 3. Fill remaining slot(s) up to cap, by sort key, scope-precedence preserved.
    remaining = [e for e in entries if e not in selected]
    remaining.sort(key=slot_key, reverse=True)
    for e in remaining:
        if len(selected) >= cap:
            break
        selected.append(e)

    # 4. Stable rendering order: (scope_rank desc, date desc, citation_id asc).
    return tuple(sorted(selected,
                        key=lambda e: (-_scope_rank(e.scope), e.date, e.citation_id),
                        reverse=False))
```

Note on date sort: because the secondary key (`date`) should be descending but `citation_id` ascending in the final ordering, the implementation flips date by sorting on a tuple where date is wrapped as `("zzz", ...)` minus the date, OR by sorting in two passes. **Concrete impl detail (planner picks):** use `(-_scope_rank(e.scope), tuple(-ord(c) for c in e.date), e.citation_id)` is brittle — instead sort once by `(_scope_rank(e.scope), e.date)` descending then re-stable-sort by `citation_id` ascending. Either approach is acceptable as long as E13b regression locks the exact output ordering.

**Invariant.** If any entry satisfies the data-leg predicate (`citation_kind="data"` AND `scope in {"instrument","constituent"}`) AND any entry satisfies the info-leg predicate (`citation_kind="information"`), the returned tuple ALWAYS contains at least one of each before fill-remaining is run. Locked by `tests/memo/test_citation_selector.py::test_data_and_info_leg_invariant` — see acceptance criteria.

**Determinism.** Two input tuples that differ only in element order produce the same output tuple — locked by `tests/memo/test_citation_selector.py::test_shuffled_inputs_same_output` (paraphrases the future E13b spec).

## Gap-aware pick-row construction

`_build_pick_rows` rewrite (`src/irc/commands/memo_cmd.py:236-278`):

```python
def _build_pick_rows(
    trades: list[dict],
    opportunity: dict,
    scoring: dict,
    extra_names: dict[str, str] | None = None,
) -> tuple[list[PickRow], list[dict], list[dict]]:
    """Returns (pick_rows, absent_targets, gapped_targets).

    Each trade target is classified into exactly one of three buckets:
    - PickRow                       → trade target whose opportunity row has evidence_gaps == ()
    - absent_targets (dict trade)   → trade target whose iid is NOT in rows_by_id
                                      after venue-proxy resolution
    - gapped_targets (dict trade enriched with the matched op row)
                                    → trade target whose opportunity row has
                                      evidence_gaps != ()
    """
    rows_list = opportunity.get("rows") or []
    rows_by_id = {r["instrument_id"]: r for r in rows_list}      # explicit lookup
    score_by_id = {s["instrument_id"]: s for s in (scoring.get("scores") or [])}
    extra_names = extra_names or {}

    pick_rows: list[PickRow] = []
    absent: list[dict] = []
    gapped: list[dict] = []
    seen: set[str] = set()
    for t in trades:
        iid = t.get("target")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        # Resolution: direct hit, else venue-proxy strip (A1234.SH → 1234), else absent.
        op = rows_by_id.get(iid) or rows_by_id.get(_strip_venue_suffix(iid))
        if op is None:
            absent.append(t)
            continue
        if op.get("evidence_gaps"):                              # non-empty → gapped
            gapped.append({**t, "_matched_row": op})
            continue
        # Eligible: build PickRow with citations from select_citations(...).
        raw_evidence = tuple(
            _evidence_from_dict(d) for d in (op.get("thesis_evidence") or [])
        )
        citations = select_citations(raw_evidence, cap=3)
        # ... build PickRow as before, with citations=citations.
        pick_rows.append(PickRow(..., citations=citations))
    return pick_rows, absent, gapped
```

**`_strip_venue_suffix(iid)`** is a small pure helper: returns `iid` with a trailing `.SH`/`.SZ`/`.OF` stripped if present; otherwise returns `iid` unchanged. (`A1234.SH` is the stated example; `005827.OF` already deserves a direct hit because `005827` is the canonical id.)

**`_evidence_from_dict(d)`** is a small pure helper that rebuilds a `ThesisEvidence` from its JSON dict (because `opportunity_report.json` carries the asdict form, not the dataclass). It MUST pass every provenance kwarg through and let `__post_init__` recompute `citation_id` to verify the JSON round-trip is consistent (i.e., if the JSON's `citation_id` doesn't match the recomputed value, raise — detects tampering/drift).

**Caller change (`run_memo`).** After `pick_rows, absent, gapped = _build_pick_rows(...)`, the failure-section markdown must be appended to `picks_table_md` BEFORE it is passed into `MemoInputs(picks_table_md=...)`. `MemoInputs` is a fixed-shape dataclass (`src/irc/memo/template.py:5-21`) where §5 of the memo renders `picks_table_md` as the body of `## 5. 精选标的`; introducing top-level `## 未能纳入精选：…` headers would collide with the numbered section structure (`## 6. 风险提示` etc.). Therefore the failure subsections nest under §5 as `###` (h3) sub-blocks, NOT top-level `##` headers:

```markdown
### 未能纳入精选：机会数据缺失

- 510300 ...（trade plan 中存在，但 opportunity_report.json 中查无此 instrument_id）
- ...

### 未能纳入精选：证据不足

- 005827 易方达蓝筹精选 | 原因: missing_constituent_snapshot, news_search_empty | 已尝试: filing, broker, news
- ...
```

Concretely: `picks_table_md = render_picks_table(pick_rows) + render_failure_sections(absent, gapped, extra_names)` where `render_failure_sections` is a new pure function in `src/irc/memo/picks_table.py` that returns `""` when both buckets are empty, otherwise the joined `###`-headed sub-blocks separated by blank lines. The `_SCORING_FOOTNOTE` emitted by `render_picks_table` stays above the failure sections (footnote applies to the picks table proper). Acceptance criterion 26 is amended below to require `###` headers, not `##`.

For `absent`, render `{iid} {extra_names.get(iid, '?')}` (we don't have the op row to source name). For `gapped`, render `{iid} {op['name_cn']} | 原因: {comma-join(op['evidence_gaps'])} | 已尝试: {comma-join(op.get('fetch_types_attempted', []))}` — exactly the format mandated by source row H3 (item 006). **Renderer NEVER emits `opportunity_state`, `dca`, `risk`, or `note_cn` for gapped rows** — those carry conclusions; the failure section is conclusion-free.

**Missing `opportunity_report.json`.** If `opportunity = _load_json(out_today / "opportunity_report.json")` returns an empty dict (file absent), `rows_by_id` is empty and every trade target falls into `absent`. This is the explicit signal to the user that opportunity didn't run; we do NOT silently degrade to picks-without-citations. Caller (`run_memo`) keeps its existing fallback names logic for rendering the absent list — no behavior change there.

## Threading provenance through existing producers

Every existing `ThesisEvidence(...)` call site must pass the new required fields. Mapping:

| Site | `scope` | `citation_kind` | `owner_instrument_id` | `parent_fund_id` | `constituent_key` |
|---|---|---|---|---|---|
| `_filing_evidence` (thesis_evidence.py:80) | `"constituent"` if stock-level (V2/item 003), else **needs threading** (see below) | `"data"` | needs threading | needs threading | `f.symbol` (constituent_key) |
| `_broker_evidence` (thesis_evidence.py:95) | `"constituent"` (broker is per-stock) | `"information"` | needs threading | needs threading | `r.symbol` |
| `_news_evidence` (thesis_evidence.py:110) | `"asset_class_macro"` | `"information"` | needs threading | `None` | `None` |
| `tests/opportunity/test_report.py:74,80` | test inputs — pass `"constituent"`, `"data"`/`"information"`, `"510300"`, `None`, `"600519"` explicitly | | | | |
| `tests/opportunity/test_cards.py:84,90` | same as above | | | | |
| `tests/opportunity/test_types.py:73,88` | unit-test the dataclass — pass `"instrument"`, `"data"`, `"510300"`, `None`, `None` explicitly | | | | |

**Threading change for `derive_thesis_from_evidence`.** Today the function takes `snapshot, theme_report, *, asset_class`. It must also take `owner_instrument_id: str` (the instrument whose row is being built; the fund id when the asset class is a fund) so the three `_filing_evidence` / `_broker_evidence` / `_news_evidence` helpers can stamp `owner_instrument_id` and `parent_fund_id`. Update the call site in `src/irc/opportunity/states.py::build_opportunity_row` to pass `inp.instrument_id` as the new kwarg.

For `_filing_evidence` and `_broker_evidence`, the current V1 producer iterates `snapshot.filings`/`snapshot.broker_reports` which are aggregate per-fund. Until item 003 introduces per-constituent fetching, these evidence entries carry `scope="instrument"` (representing the fund's aggregate constituent picture, not a specific stock) — when item 003 lands it changes the producer to `scope="constituent"` and populates `constituent_key=f.symbol`. **Item 002 spec: use `scope="instrument"` and `constituent_key=None` for these helpers; item 003 will rewire to `scope="constituent"` and `constituent_key=f.symbol`.** This is the explicit pre-item-003 stance; D0 is unblocked even if the V1 evidence chain is aggregate-level.

For `_news_evidence`, the source is `ThemeReport.citations` — these are theme-report (macro/sector) citations, not instrument-specific. They carry `scope="asset_class_macro"`, `citation_kind="information"`, `owner_instrument_id=` the instrument-being-built (because `build_cited_map` requires `e.owner_instrument_id == row.instrument_id`), `parent_fund_id=None`, `constituent_key=None`. They will NOT satisfy the future audit gate's `scope in {"instrument","constituent"}` predicate, which is the intended behavior — macro citations are supplemental context only (per D2a's restriction rule).

**Test call sites** simply hardcode plausible values per the table above. Tests that exercise the round-trip through `opportunity_report.json` (test_report.py) MUST assert the new keys appear in the output.

## Acceptance criteria

1. `ThesisEvidence(...)` with empty `owner_instrument_id` raises `ValueError`.
2. `ThesisEvidence(...)` with `citation_kind="both"` (or anything not in `{"data","information"}`) raises `ValueError`.
3. `ThesisEvidence(...)` with `scope="random"` (not in the four-literal set) raises `ValueError`.
4. `ThesisEvidence(...)` with empty `type`, `source`, or `date` raises `ValueError`.
5. `ThesisEvidence(...)` with `parent_fund_id=None` and `constituent_key=None` constructs successfully (fund-level evidence).
6. `ThesisEvidence.citation_id` is deterministic: two constructions with identical preimage inputs produce the same `citation_id` (16 hex chars).
7. `ThesisEvidence.citation_id` differs across instruments: two evidence entries with same `type/source/date/url` but different `owner_instrument_id` produce different `citation_id`s.
8. `ThesisEvidence.citation_id` differs across constituents under the same fund: same `type/source/date/url`/`owner_instrument_id` but different `constituent_key` produces different `citation_id`s.
9. `select_citations((), cap=3) == ()`.
10. `select_citations(entries, cap=0) == ()`.
11. `select_citations(shuffled_a) == select_citations(shuffled_b)` when `set(shuffled_a) == set(shuffled_b)`.
12. `select_citations(entries, cap=3)` returns ≥1 entry with `citation_kind="data"` AND ≥1 with `citation_kind="information"` whenever the input contains at least one of each — locked by an explicit invariant test (6 data + 2 info input → output includes ≥1 info).
13. `select_citations` output is ordered by `(scope_rank desc, date desc, citation_id asc)` — locked by a fixed-input regression test with hand-computed expected order.
14. `_row_to_dict(row)` includes keys `"thesis_evidence"`, `"contributing_dimensions"` (sorted list), and `"constituent_analyses"` (empty list before item 003). JSON round-trip preserves all three.
15. `_discipline_row_from` propagates `row.thesis_evidence`, `row.constituent_analyses`, `row.evidence_gaps`, `row.fetch_types_attempted` into the returned `DisciplineRow`.
16. `PickRow` accepts `citations=()` as default (back-compat). With a non-empty `citations` tuple, `render_picks_table` emits a cell containing one `[ref:{citation_id}]` marker per citation, separated by `<br>`.
17. `_build_pick_rows` with a trade target whose `iid` is absent from `opportunity_report.json["rows"]` (and absent after venue-proxy strip) returns the trade in the `absent` list, NOT in `pick_rows`.
18. `_build_pick_rows` with a trade target whose op row has non-empty `evidence_gaps` returns the trade in the `gapped` list, NOT in `pick_rows`.
19. `_build_pick_rows` with a trade target whose op row has `evidence_gaps==()` returns a `PickRow` with `citations` set to `select_citations(rebuilt_evidence, cap=3)`.
20. `_build_pick_rows` raises `ValueError` if a rebuilt evidence dict's `citation_id` does not match the value recomputed by `__post_init__` (round-trip integrity check).
21. `build_cited_map(rows)` raises `RuntimeError("duplicate citation_id: ...")` if any `citation_id` appears under two different `(owner_instrument_id, citation_id)` keys.
22. `build_cited_map(rows)` returns `CitedMap` where `cited_map[row.instrument_id][e.citation_id] == CitationMeta(scope=e.scope, citation_kind=e.citation_kind, owner_instrument_id=e.owner_instrument_id, asset_class=row.asset_class, parent_fund_id=e.parent_fund_id, constituent_key=e.constituent_key)` for every evidence entry on every row.
23. `build_cited_map(rows)` raises `RuntimeError` if any evidence's `owner_instrument_id != row.instrument_id` (provenance integrity check; closes the "wrong instrument" path).
24. `_row_to_dict` round-trip: `json.loads(json.dumps(_row_to_dict(row)))["thesis_evidence"]` equals `[asdict(e) for e in row.thesis_evidence]` and includes `citation_id`.
25. `_row_to_dict` round-trip preserves `contributing_dimensions` as a sorted JSON list — `set(loaded["contributing_dimensions"]) == row.contributing_dimensions`.
26. Memo's failure-section markdown contains `### 未能纳入精选：机会数据缺失` and/or `### 未能纳入精选：证据不足` headers (h3, nested under `## 5. 精选标的`) when the corresponding bucket is non-empty; sections are omitted entirely (no header) when the bucket is empty. Acceptance test asserts the markdown appears between `_SCORING_FOOTNOTE` and `## 6. 风险提示`.
27. Failure-section bullets never render `opportunity_state`, `dca_action`, `risk_action`, or `note_cn` — only `instrument_id`, `name_cn`, `evidence_gaps`, `fetch_types_attempted`.

## Edge cases

- **`url` empty.** A Sina filing digest sometimes carries no URL. The hash preimage uses `canonical_id = self.url or f"{self.source}:{self.date}:{self.summary[:64]}"` so two distinct empty-URL filings from the same source on the same date for the same instrument+constituent but different content (e.g., FY24-Q3 vs FY24-Q4 digest published the same day) get distinct `citation_id`s via the summary prefix. The 64-char cap keeps the preimage bounded; if two summaries collide on the first 64 chars, they are functionally the same citation. If the producer ever needs richer disambiguation, add a `provider_id` field in a future slice; out of scope here.
- **`constituent_key` of fund-level evidence.** For a fund's NAV report or announcement, `parent_fund_id=None` (this is the fund itself, not a stock held by a fund) and `constituent_key=None`. The hash preimage uses `self.constituent_key or ""` so empty + None render to the same preimage segment — explicitly intended.
- **`owner_instrument_id` of constituent evidence.** A `600519` filing fetched for fund `005827` carries `owner_instrument_id="005827"` (the fund whose analysis is consuming this evidence), `parent_fund_id="005827"`, `constituent_key="600519"`. This means the SAME `600519` filing fetched independently for fund `163417` produces a DIFFERENT `citation_id` (different `owner_instrument_id` in the preimage) — intentional, because the citation is bound to the fund context.
- **`citation_id` collision risk.** 16 hex chars = 64 bits. Birthday-paradox collision probability for ≤100k citations in a run ≈ 2.7e-10. The duplicate-id detector in `build_cited_map` raises immediately if it ever fires, so a collision is loud, not silent.
- **`_build_pick_rows` with missing `opportunity_report.json`.** When the file doesn't exist, `_load_json` returns `{}`, `rows_by_id` is empty, every trade target falls into `absent`. The caller still writes memo.md; the failure section makes the missing-opportunity state explicit and observable. We do NOT raise here — that's a pipeline-orchestration concern handled by `require_fresh_ingest` and other upstream gates, not by `_build_pick_rows`.
- **Empty `entries` to `select_citations`.** Returns `()`. Caller's PickRow gets `citations=()` and renders `—` in the table cell.
- **`cap > len(entries)`.** `select_citations` returns all entries in stable order; no padding.
- **Item 003 not yet merged when item 002 lands.** `constituent_analyses` is typed as `tuple[Any, ...] = ()`; default empty tuple round-trips through JSON as `[]`. Item 003's spec then narrows the type to `tuple[ConstituentAnalysis, ...]` and populates it.

## Dependencies on other items

- **Depends on item 001 (merged).** `_row_to_dict` must serialize both new schemas in one pass — `thesis_evidence` AND `contributing_dimensions`. Item 001 added the field; item 002 emits it in JSON.
- **Blocks item 003 (A+G).** `ConstituentAnalysis` (item 003) carries `tuple[ThesisEvidence, ...]` — those `ThesisEvidence` instances depend on the new required-field schema. Item 003's first `ConstituentAnalysis(...)` constructor fails to compile until item 002's schema is in.
- **Blocks item 005 (F).** Fund NAV adapter constructs `ThesisEvidence` with `scope="instrument"`, `citation_kind="data"` — requires the new fields.
- **Blocks item 006 (H).** Failure renderer reads `DisciplineRow.evidence_gaps` and `fetch_types_attempted` — both added here.
- **Blocks item 007 (D1+D3).** Memo evidence-pool calls `select_citations` (added here); discipline renderer reads `DisciplineRow.thesis_evidence` (field added here).
- **Blocks item 009 (D2).** All audit gates consume `CitedMap`/`ConstituentCitedMap` + `CitationMeta` (added here) and call `build_cited_map` (added here).
- **Independent of item 010.** Holdings ingestor doesn't touch citations.

## Files touched (preview for planner)

| File | Change |
|---|---|
| `src/irc/opportunity/types.py` | Add `CitationMeta` dataclass; add `CitedMap`/`ConstituentCitedMap` type aliases; extend `ThesisEvidence` with 6 required fields + `__post_init__` validation + `citation_id` computation; extend `DisciplineRow` with 4 trailing defaulted fields. Add `import hashlib` at module top. |
| `src/irc/opportunity/citation_map.py` (new) | `build_cited_map(rows) -> CitedMap` with duplicate-id and wrong-owner detectors. Located in `opportunity/` rather than `memo/` because the producer is an opportunity-stage artifact (consumed by memo + opportunity audit gates). |
| `src/irc/opportunity/report.py` | `_row_to_dict` emits `thesis_evidence`, `contributing_dimensions`, `constituent_analyses`. |
| `src/irc/opportunity/thesis_evidence.py` | Add `owner_instrument_id: str` kwarg to `derive_thesis_from_evidence`; thread into `_filing_evidence` / `_broker_evidence` / `_news_evidence`; pass `scope`/`citation_kind`/`owner_instrument_id`/`parent_fund_id`/`constituent_key` into every `ThesisEvidence(...)` constructor. |
| `src/irc/opportunity/states.py` | `build_opportunity_row` passes `inp.instrument_id` as `owner_instrument_id=` to `derive_thesis_from_evidence`. |
| `src/irc/commands/opportunity_cmd.py` | `_discipline_row_from` propagates 4 new fields. |
| `src/irc/memo/citation_selector.py` (new) | `select_citations(entries, cap=3)` pure function. |
| `src/irc/memo/picks_table.py` | Add `citations` field to `PickRow`; add `证据` column to `render_picks_table`; render `[ref:{citation_id}] {type}·{source}·{date}` joined by `<br>`. |
| `src/irc/commands/memo_cmd.py` | Rewrite `_build_pick_rows` to return `(pick_rows, absent, gapped)`; add helper `_strip_venue_suffix`; add helper `_evidence_from_dict` (rebuilds `ThesisEvidence` from JSON dict). `run_memo` renders the two failure sections after the picks table. |
| `tests/opportunity/test_types.py` | Update existing `ThesisEvidence` constructions to pass new fields; add tests for `__post_init__` validation, `citation_id` determinism, cross-instrument hash divergence. |
| `tests/opportunity/test_report.py` | Update existing `ThesisEvidence` constructions; add test that `_row_to_dict` emits `thesis_evidence`/`contributing_dimensions`/`constituent_analyses` round-trip. |
| `tests/opportunity/test_cards.py` | Update existing `ThesisEvidence` constructions. |
| `tests/memo/test_citation_selector.py` (new) | Determinism (shuffled inputs same output), data+info leg invariant, stable rendering order, empty input, cap=0, cap > len. |
| `tests/memo/test_picks_table.py` | Add test that `[ref:{citation_id}]` markers render in the new column; empty `citations` renders `—`. |
| `tests/memo/test_pick_rows.py` (new) | Three regression cases: (a) absent trade target → in `absent` list; (b) gapped trade target → in `gapped` list; (c) clean trade target → in `pick_rows` with `citations` populated. |
| `tests/opportunity/test_citation_map.py` (new) | `build_cited_map` returns correct shape; raises on duplicate `citation_id`; raises on wrong-owner provenance mismatch. |

## Open questions for the planner

1. **YAML emission of `citation_id`.** `_card_to_dict` (`src/irc/opportunity/report.py:54-60`) uses `dataclasses.asdict(card)` which will include the new `citation_id` field. No code change needed for the YAML side — but a regression test should assert `thesis_cards.yaml` contains `citation_id: <16-hex>` per evidence entry. (Planner: confirm and add the assertion.)
2. **Picks table column count.** Adding a 9th column (`证据`) to the picks-table markdown means existing snapshot tests for the table (if any) will break. Planner: locate and update those snapshots, and confirm the header row's pipe count.
3. **`_evidence_from_dict` location.** Currently proposed inside `memo_cmd.py`. If a second consumer needs it (audit gates in item 009 might), promote to `src/irc/opportunity/types.py` as a `ThesisEvidence.from_dict` classmethod. Defer the decision unless a second consumer appears in this slice.
4. **Failure-section ordering inside `memo.md`.** ~~Spec says "after the picks table".~~ **Resolved (grill 002):** `MemoInputs` (`src/irc/memo/template.py:5-21`) is a fixed-shape dataclass; `_section(5, "精选标的", picks_section)` renders `picks_table_md` as the §5 body. Failure subsections are appended to `picks_table_md` as `###` (h3) blocks nested under §5, NOT new `##` top-level headers. The picks-table `_SCORING_FOOTNOTE` stays above the failure sections. See "Caller change" section above for the concrete seam.
5. **`_strip_venue_suffix`.** The diagnosis says `"A1234.SH" → "1234"` but does not say what other suffixes exist. Planner: enumerate suffixes from the universe configs (`bundle.universe_*`) before implementing the helper — at minimum `.SH`, `.SZ`, `.OF`, `.HK`. Conservative default: only strip suffixes that match `\.[A-Z]{2}$`.
