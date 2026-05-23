# Item 006 spec — failure-mode + Policy B weight-aware quorum + H3 universal gapped-row invariant (Slice H h1–h4 + H2.v2)

## Goal

Item 006 is the **failure-mode and audit-policy layer** that sits between items 003 + 005 (which populate `ActiveFundSnapshot.constituent_analyses`, `FundLevelSnapshot.evidence_gaps`, and `ConstituentAnalysis.failure_reasons`) and item 007 (which renders memo + discipline outputs). It transforms the raw per-fund data the fetch engines produced into three deterministic outputs: (a) gap-stamped `OpportunityRow.evidence_gaps`, (b) the partitioned `publishable_rows` vs `gapped_rows` sets, and (c) `outputs/{date}/rejections.json` — the canonical audit trail naming every excluded fund and why.

Three sub-slices ship in this item, each load-bearing for downstream:

- **H1 (rejection_log)** — new `src/irc/opportunity/rejection_log.py` module with frozen-dataclass `RejectionRecord` + `ConstituentCoverageEntry` + a pure `record_fund_rejection(...)` builder + I/O-isolated `write_rejections_json(records, out_dir)`. One entry per excluded fund.
- **H2.v2 (Policy B weight-aware quorum)** — NOT the simpler v1 quorum from the original diagnosis; the post-grill amendment that requires (1) data leg for ALL top-N, (2) info leg for `ceil(top_N/2)` material holdings by weight, (3) tail-holding data-only-permitted, (4) `audit_error="missing_constituent_record"` for constituents with both `evidence==() AND failure_reasons==()`, (5) per-mention strict rule deferred to memo-stage `find_uncited_conclusions` in items 007/009, (6) `thesis_state` never a synthetic partial value.
- **H3 (universal gapped-row invariant)** — `_write_opportunity_outputs` skips thesis_card + pick_row emission for ANY row where `evidence_gaps != ()`; failure renderer emits ONLY `{instrument_id} {name_cn} | 原因: {evidence_gaps} | 已尝试: {fetch_types_attempted}` and never reads `opportunity_state`/`dca`/`risk`/`note_cn` (those carry conclusions, which gapped rows do not earn).
- **H4 (V1 systematic exclusions)** — once-per-run summary line `## V1 systematic exclusions: N funds excluded...` in `discipline_report.md` + §1.2 footnote in the diagnosis doc (the footnote text was already shipped with Slice H2.v2; item 006 verifies it is present and adds the once-per-run runtime summary line).

Item 006 reads `evidence_gaps` populated by items 003 (active-fund) + 005 (fund-level QDII sentinel + dispatch). It writes new gap codes for Policy B failures (`incomplete_constituent_record`, `incomplete_constituent_data`, `insufficient_info_coverage_top_half`, `incomplete_constituent_coverage`, `holdings_fetch_failed`). It also adds the new field `ConstituentAnalysis.audit_errors: tuple[str, ...] = ()` so the audit-error class is structurally distinguishable from regular `evidence_gaps` and from adapter-level `failure_reasons`.

Item 006 ships ZERO new renderers for `memo.md` or for the discipline action sections — those land in item 007. Item 006 ships ONLY: (a) the failure-section renderer for `discipline_report.md`, (b) the once-per-run V1 systematic-exclusion summary line, (c) the `rejections.json` writer. The citation gate flips to canonical-path-block mode in item 009.

## In scope

### H1 — `rejection_log.py` module

New file `src/irc/opportunity/rejection_log.py`. All functions pure; I/O is isolated to `write_rejections_json(records, out_dir)`.

**Frozen dataclasses (the schema):**

```python
RejectionReasonCode = Literal[
    "holdings_fetch_failed",
    "incomplete_constituent_record",
    "incomplete_constituent_data",
    "insufficient_info_coverage_top_half",
    "incomplete_constituent_coverage",
    "qdii_information_unavailable",
    "fund_nav_unavailable",
    "missing_us_news_adapter",          # H4 systematic-exclusion sub-class
]

@dataclass(frozen=True)
class ConstituentCoverageEntry:
    symbol: str
    name_cn: str
    weight_pct: float                        # 0.0–100.0
    weight_rank: int                         # 1-based; rank-1 = highest weight
    in_material_top_half: bool               # True iff weight_rank <= ceil(top_N/2)
                                             # (or tied at the cutoff weight)
    exchange: str                            # "SH"|"SZ"|"BJ"|"HK"|"US"|"UNKNOWN"
    has_data_leg: bool                       # >=1 evidence with citation_kind="data"
    has_info_leg: bool                       # >=1 evidence with citation_kind="information"
    data_kind_count: int
    information_kind_count: int
    failure_reasons: tuple[str, ...]
    audit_errors: tuple[str, ...]

@dataclass(frozen=True)
class RejectionRecord:
    instrument_id: str
    name_cn: str
    asset_class: str
    rejection_reason: RejectionReasonCode
    decision_rule: str                       # stable human-readable string
                                             # e.g. "info-leg quorum 5 of 10; 3 of material top-half satisfied"
    rejection_at_stage: Literal["opportunity_build", "opportunity_write"]
    constituent_coverage: tuple[ConstituentCoverageEntry, ...]
    fund_level_failure_reasons: tuple[str, ...]
    fetch_types_attempted: tuple[str, ...]
    evidence_gaps: tuple[str, ...]           # mirror of OpportunityRow.evidence_gaps
                                             # for cross-reference with H3 failure renderer

@dataclass(frozen=True)
class RejectionsDocument:
    run_date: str                            # ISO YYYY-MM-DD
    plan_hash: str                           # propagated from FetchPlan when available;
                                             # "" outside autobuild mode
    entries: tuple[RejectionRecord, ...]     # sorted by (asset_class, instrument_id)
```

**Public functions:**

```python
MATERIAL_HOLDING_QUORUM: Callable[[int], int]  # = lambda n: math.ceil(n / 2)

def evaluate_policy_b(
    snapshot: ActiveFundSnapshot,
    *,
    top_n: int,
) -> "PolicyBVerdict":
    """Pure function. Reads constituent_analyses + failure_reasons_by_symbol + fund_level_failure_reasons.
    Returns a verdict carrying gap_codes, audit_errors, decision_rule, material_symbols,
    constituent_coverage (in weight_rank order)."""
    ...

def record_fund_rejection(
    *,
    row: OpportunityRow,
    snapshot: ActiveFundSnapshot | FundLevelSnapshot | None,
    verdict: "PolicyBVerdict | None",
    rejection_reason: RejectionReasonCode,
    decision_rule: str,
    rejection_at_stage: Literal["opportunity_build", "opportunity_write"] = "opportunity_write",
) -> RejectionRecord:
    """Pure builder. NO I/O. Composes a RejectionRecord from row + snapshot + verdict."""
    ...

def write_rejections_json(
    document: RejectionsDocument,
    out_dir: Path,
) -> None:
    """Atomic write to outputs/{date}/rejections.json via the existing .tmp.{pid} → os.replace pattern."""
    ...
```

`PolicyBVerdict` (frozen dataclass, also exported):

```python
@dataclass(frozen=True)
class PolicyBVerdict:
    gap_codes: tuple[str, ...]               # () iff fund is publishable under Policy B
    audit_errors: tuple[str, ...]            # ("missing_constituent_record:{symbol}", ...)
    decision_rule: str                       # e.g. "info-leg quorum 5 of 10; 5 satisfied (publishable)"
                                             # or "info-leg quorum 5 of 10; 3 satisfied"
    material_symbols: tuple[str, ...]        # constituent_keys in the material top-half
    constituent_coverage: tuple[ConstituentCoverageEntry, ...]
                                             # ordered by weight_rank ascending
                                             # (rank 1 = highest weight)
```

### H2.v2 — Policy B weight-aware quorum (the evaluator)

`evaluate_policy_b(snapshot, *, top_n)` implements the following rules in order. Each rule short-circuits when it fires (returns a verdict with the corresponding `gap_codes` and `decision_rule`):

1. **Fund-level holdings fetch failed.** If `snapshot.constituent_analyses == ()` AND `snapshot.fund_level_failure_reasons` non-empty (`holdings_fetch_failed:{fund_id}:{reason}` present) → `gap_codes=("holdings_fetch_failed",)`, `decision_rule="holdings adapter empty/failed"`, `constituent_coverage=()`.

2. **Missing constituent record (audit error).** For each `ConstituentAnalysis` where `evidence == () AND failure_reasons == ()` (the constituent was emitted but carries no evidence AND no diagnostics — Item 003's adapter contract was violated): append `f"missing_constituent_record:{c.symbol}"` to `audit_errors`. If any such constituent exists → `gap_codes=("incomplete_constituent_record",)`, `decision_rule="missing constituent records: {n} of {top_n}"`. Note: this is an **audit error**, not a normal evidence gap. The downstream `find_incomplete_constituent_analyses` (item 009 D2c step-2b) ALSO raises `RuntimeError` on this predicate — defence in depth.

3. **Per-holding data leg required for ALL top-N.** For each `ConstituentAnalysis`, check `has_data_leg = any(e.citation_kind == "data" for e in c.evidence)`. If any top-N holding has `has_data_leg == False` → `gap_codes=("incomplete_constituent_data",)`, `decision_rule="data leg missing for {n} of {top_n} holdings: {symbols}"`. Tail holdings ARE NOT exempt from the data leg — disclosure listed them, so the gap is real.

4. **Per-holding info leg required for material top-half (ceil(top_N/2) by weight).** Rank `constituent_analyses` by `weight_pct` descending (ties broken by `symbol` ascending for determinism, BUT the material set ignores the symbol tiebreaker — see §"Material-set tie rule" below). The material set = the top `ceil(top_N/2)` holdings by weight, EXTENDED to include any holding whose `weight_pct` equals the cutoff weight (tied at the boundary). For each holding in the material set, check `has_info_leg = any(e.citation_kind == "information" for e in c.evidence)`. Count `satisfied = sum(has_info_leg for c in material)`. If `satisfied < len(material)` → `gap_codes=("insufficient_info_coverage_top_half",)`, `decision_rule=f"info-leg quorum {len(material)} of {top_n}; {satisfied} of material top-half satisfied"`. Tail holdings (`weight_rank > len(material)`) may be data-only without blocking.

5. **Some top-N holdings have only `failure_reasons`, no evidence at all.** If any `ConstituentAnalysis` has `evidence == () AND failure_reasons != ()` → `gap_codes=("incomplete_constituent_coverage",)`, `decision_rule=f"holdings with no evidence: {n} of {top_n}"`. Note: rules 3 + 4 fire first on the symbols that DO have evidence; rule 5 catches the "evidence==()" subset that survived rules 1+2 (i.e. constituents with `failure_reasons != ()`).

6. **Publishable.** If none of rules 1–5 fired → `gap_codes=()`, `decision_rule=f"info-leg quorum {len(material)} of {top_n}; {satisfied} satisfied (publishable)"`.

**Rule precedence:** Rules 1 → 2 → 3 → 5 → 4. (Rule 4 is the "info-leg quorum" gate; it must fire LAST so that data-leg failures and missing-record audit errors surface as their own gap codes — otherwise a fund with 3 holdings missing data + 0 info-leg coverage would be stamped `insufficient_info_coverage_top_half`, hiding the data failure.) **Locked test:** spec criterion 14 — "a fund with both a data-leg miss and an info-leg miss reports `incomplete_constituent_data` (not `insufficient_info_coverage_top_half`)".

**Material-set tie rule (the boundary case):** suppose `top_n=10` and the sorted weights are `[8.2, 7.1, 6.5, 5.0, 4.2, 4.2, 3.8, ...]`. `ceil(10/2)=5`, so the initial cutoff is rank-5 (weight=4.2). Position 6 has weight=4.2 (tied at the cutoff) → include both positions 5 AND 6 in the material set (size 6). Tiebreaker between equal-weight symbols at non-boundary positions is `symbol` ascending (deterministic ordering for `constituent_coverage` output), but it does NOT shrink the material set.

**`thesis_state` invariant.** Policy B never sets a synthetic `thesis_state`. The four `ThesisState` literals (`intact`, `under_pressure`, `falsified`, `evidence_insufficient`) are exclusively set by item 003's `derive_thesis_from_evidence`. When Policy B stamps `evidence_gaps != ()`, the row's `thesis_state` retains whatever value `derive_thesis_from_evidence` already assigned — item 006 does NOT modify it. The row is filtered from publishable output by H3 (next sub-slice); the `thesis_state` value is irrelevant downstream once `evidence_gaps != ()`.

**Per-mention strict rule deferred.** Item 006 does NOT inspect memo prose; that gate lives in item 007/009 (`find_uncited_conclusions` + `find_missing_constituent_info_citation`). Item 006 only does the quorum check on the structured `ConstituentAnalysis.evidence` tuple.

### H2.v2 — schema additions

Add a new field to `ConstituentAnalysis` in `src/irc/fundamentals/types.py`:

```python
@dataclass(frozen=True)
class ConstituentAnalysis:
    symbol: str
    name_cn: str
    weight_pct: float
    evidence: tuple[ThesisEvidence, ...]
    failure_reasons: tuple[str, ...]
    one_line_view: str
    audit_errors: tuple[str, ...] = ()       # NEW — Slice H2.v2
```

`audit_errors` is **populated by `evaluate_policy_b`**, NOT by item 003's snapshot builder. Item 003's `ConstituentAnalysis` instances are constructed with `audit_errors=()`. Policy B reads them and (in the "missing_constituent_record" case) emits a NEW `ConstituentAnalysis` instance via `dataclasses.replace(c, audit_errors=("missing_constituent_record:"+c.symbol,))` when building the `ConstituentCoverageEntry`. The original `snapshot.constituent_analyses` tuple is NOT mutated (item 003's snapshot is frozen and its disk cache must not see new audit_errors — those are derived-on-evaluation).

Add the new field at the END of the dataclass with a default `()` so all existing call sites continue to compile without change. Item 003's tests + cache JSON serialisation tolerate the trailing field.

### H2.v2 — wiring into `_build_rows` (gap stamping)

In `src/irc/commands/opportunity_cmd.py::_build_rows`, after `build_opportunity_row` produces a row whose `lookthrough_target.kind == "active_fund"`, item 006 inserts a Policy B evaluation:

```python
if isinstance(snap_obj, ActiveFundSnapshot):
    verdict = evaluate_policy_b(snap_obj, top_n=TOP_N_DEFAULT)
    if verdict.gap_codes:
        row = replace(row, evidence_gaps=row.evidence_gaps + verdict.gap_codes)
    pending_verdicts[row.instrument_id] = verdict   # stashed for _write_opportunity_outputs
```

The verdict is stashed in a `pending_verdicts: dict[str, PolicyBVerdict]` keyed by `instrument_id` and passed through to `_write_opportunity_outputs` so the rejection record can be emitted with the full verdict context. (Alternative: re-evaluate Policy B inside `_write_opportunity_outputs` — rejected because re-evaluation duplicates compute and risks the verdict diverging if any field on the snapshot changes between calls.)

For `FundLevelSnapshot` (item 005's fund-level + QDII sentinel) and the legacy `ConstituentSnapshot` (display-only), no Policy B evaluation runs — those rows acquire `evidence_gaps` from item 005's sentinel writer or stay gap-free, and the rejection_log records them in `_write_opportunity_outputs` based on `row.evidence_gaps != ()` alone.

### H3 — universal gapped-row invariant in `_write_opportunity_outputs`

The function partitions `kept_rows` (item 003/005-stamped + item 006-Policy-B-stamped rows) into two sets ONCE at the top:

```python
def _write_opportunity_outputs(
    kept_rows: list[OpportunityRow],
    positions: dict[str, PositionContext],
    qualities: dict[str, SelectionQuality],
    roles: dict[str, str],
    holdings: dict[str, Holding],
    out_dir: Path,
    today: str,
    *,
    pending_verdicts: dict[str, PolicyBVerdict] | None = None,
) -> None:
    # Step 1 — H3 FATAL pre-gate: fetch_budget_exhausted is run-level only.
    for r in kept_rows:
        if "fetch_budget_exhausted" in r.evidence_gaps:
            raise RuntimeError(
                f"fetch_budget_exhausted appeared on row {r.instrument_id} — "
                "this gap is run-level fatal and must be caught at preflight; "
                "row-level emission is a programming error"
            )

    # Step 2 — H3 partition.
    publishable_rows = [r for r in kept_rows if not r.evidence_gaps]
    gapped_rows = [r for r in kept_rows if r.evidence_gaps]

    # Step 3 — emit thesis_cards + opportunity_report.json from publishable_rows only.
    cards = [
        build_thesis_card(...) for r in publishable_rows
        if r.instrument_id in holdings or r.opportunity_state in ("core_dca", "small_watch")
    ]
    discipline_rows = [_discipline_row_from(r, positions[r.instrument_id]) for r in publishable_rows]
    # ... atomic_write_text(out_dir / "opportunity_report.json",
    #     json.dumps(compose_opportunity_report(publishable_rows, today), ...))
    # ... atomic_write_text(out_dir / "thesis_cards.yaml", compose_thesis_cards_yaml(cards))

    # Step 4 — build rejections.json from gapped_rows.
    rejection_records = tuple(
        record_fund_rejection(
            row=r,
            snapshot=snapshot_cache.get(r.instrument_id),
            verdict=(pending_verdicts or {}).get(r.instrument_id),
            rejection_reason=_classify_rejection_reason(r),
            decision_rule=(pending_verdicts or {}).get(r.instrument_id, _SENTINEL).decision_rule,
        )
        for r in gapped_rows
    )
    write_rejections_json(
        RejectionsDocument(run_date=today, plan_hash=plan_hash, entries=rejection_records),
        out_dir,
    )

    # Step 5 — compose discipline_report.md = (publishable bucket sections)
    # + failure_section + V1_systematic_exclusion_summary.
    failure_section = render_failure_section(gapped_rows)
    v1_summary = render_v1_systematic_exclusion_summary(rejection_records)
    atomic_write_text(
        out_dir / "discipline_report.md",
        compose_discipline_markdown(discipline_rows, today)
        + "\n\n" + v1_summary
        + "\n\n## 证据不足 / Failed fetch\n\n" + failure_section,
    )
```

**H3 invariants (locked by tests):**

1. `thesis_cards.yaml` contains ZERO entries whose `instrument_id ∈ {r.instrument_id for r in gapped_rows}`.
2. `opportunity_report.json` `rows` list contains ZERO entries with non-empty `evidence_gaps` (the JSON-serialised rows are the partitioned publishable set).
3. `discipline_report.md`'s **publishable bucket sections** (`今日可定投`, `减速定投`, `暂停加仓`, `风险复核`, `调仓复核`, `退出复核`) contain ZERO gapped rows (those are routed to the failure section).
4. `discipline_report.md`'s **failure section** emits each gapped row as exactly: `- **{instrument_id} {name_cn}** ｜ 原因: {evidence_gaps_joined} ｜ 已尝试: {fetch_types_attempted_joined}`. NO `opportunity_state` / `dca` / `risk` / `note_cn` text appears for gapped rows.
5. `fetch_budget_exhausted` in any row's `evidence_gaps` → `RuntimeError` raised IMMEDIATELY at Step 1 (before any `.tmp` file is created). Unconditional `raise`, NOT `assert` (because `-O` disables assertions).

### H3 — failure section renderer

New file `src/irc/opportunity/failure_renderer.py`:

```python
def render_failure_section(rows: Sequence[OpportunityRow]) -> str:
    """Render the failure section of discipline_report.md.

    Reads ONLY: instrument_id, name_cn, evidence_gaps, fetch_types_attempted.
    NEVER reads: opportunity_state, dca_action, risk_action, note_cn,
    opportunity_reason, valuation_state, heat_state, thesis_state,
    product_quality_state, contributing_dimensions, thesis_evidence,
    constituent_analyses.

    Output one line per row:
      - **{instrument_id} {name_cn}** ｜ 原因: {gaps_joined} ｜ 已尝试: {fetch_types_joined}
    """
    if not rows:
        return "（无）"
    lines: list[str] = []
    for r in sorted(rows, key=lambda r: (r.asset_class, r.instrument_id)):
        gaps = ", ".join(r.evidence_gaps) or "(none)"
        attempted = ", ".join(r.fetch_types_attempted) or "(none)"
        lines.append(
            f"- **{r.instrument_id} {r.name_cn}** ｜ 原因: {gaps} ｜ 已尝试: {attempted}"
        )
    return "\n".join(lines)


def render_v1_systematic_exclusion_summary(
    records: Sequence[RejectionRecord],
) -> str:
    """Once-per-run summary line for H4. Counts US-heavy material-holding funds.

    A US-heavy fund is one where the rejection_reason is
    insufficient_info_coverage_top_half AND the material_top_half constituents
    are predominantly (majority by count) exchange="US".
    """
    us_heavy = [
        r for r in records
        if r.rejection_reason == "insufficient_info_coverage_top_half"
        and _is_us_heavy(r.constituent_coverage)
    ]
    if not us_heavy:
        return "## V1 systematic exclusions: 0 funds excluded due to US-heavy material holdings"
    names = ", ".join(f"{r.instrument_id} {r.name_cn}" for r in us_heavy)
    return (
        f"## V1 systematic exclusions: {len(us_heavy)} funds excluded due to "
        f"US-heavy material holdings (V2 prerequisite: US information adapter). "
        f"Excluded: {names}"
    )


def _is_us_heavy(coverage: Sequence[ConstituentCoverageEntry]) -> bool:
    material = [c for c in coverage if c.in_material_top_half]
    if not material:
        return False
    us = sum(1 for c in material if c.exchange == "US")
    return us > len(material) // 2  # strict majority
```

The renderer's signature is the **enforcement mechanism**. `render_failure_section` accepts `Sequence[OpportunityRow]` and reads only the 4 allowed fields; a future contributor cannot accidentally add `r.opportunity_state` because the failure-section line format is locked by a regression test that greps the rendered output for forbidden tokens (see acceptance criterion 17).

### H4 — V1 systematic exclusion footnote + once-per-run summary line

Two surfaces:

1. **§1.2 footnote in `docs/diagnosis-thesis-cards-evidence-gap.md`.** Already shipped at line 32 of the diagnosis doc (verified via grep in the directive context). Item 006's acceptance criterion checks that the footnote still exists with the canonical text "documents the systematic exclusion of US-heavy active CN funds...". No new text written by item 006 — the criterion is a regression check.

2. **Once-per-run `## V1 systematic exclusions: N funds...` line in `discipline_report.md`.** Emitted via `render_v1_systematic_exclusion_summary(records)` (see §H3). Placement: between the publishable bucket sections and the failure section. The count N is derived from `rejections.json` entries with `rejection_reason="insufficient_info_coverage_top_half"` where the material top-half constituents are predominantly US (strict-majority by count). The summary line is emitted UNCONDITIONALLY (even when N=0) so the section header is stable across runs and greppable for monitoring.

### H3 — `_classify_rejection_reason` helper

Given a `gapped_row`, derive the `RejectionReasonCode` for the rejection record. Precedence (first match wins):

```python
_GAP_TO_REASON = {
    "qdii_information_unavailable":         "qdii_information_unavailable",
    "holdings_fetch_failed":                "holdings_fetch_failed",
    "incomplete_constituent_record":        "incomplete_constituent_record",
    "incomplete_constituent_data":          "incomplete_constituent_data",
    "insufficient_info_coverage_top_half":  "insufficient_info_coverage_top_half",
    "incomplete_constituent_coverage":      "incomplete_constituent_coverage",
    "fund_nav_unavailable":                 "fund_nav_unavailable",
}

def _classify_rejection_reason(row: OpportunityRow) -> RejectionReasonCode:
    for gap in row.evidence_gaps:
        if gap in _GAP_TO_REASON:
            return _GAP_TO_REASON[gap]
    raise RuntimeError(
        f"row {row.instrument_id} carries unrecognised evidence_gaps: {row.evidence_gaps}"
    )
```

Unknown gap codes raise — defence against silent acceptance of new gap codes that bypass the rejection log. Adding a new gap code therefore REQUIRES adding it to `_GAP_TO_REASON` (locked by criterion 19).

## Out of scope

- **Item 007 territory** — memo `evidence_pool` rendering with `[ref:{citation_id}]` markers, the `## 持仓明细` appendix, per-fund constituent inline bullets, `build_alias_maps`. Item 006 does NOT touch `memo_cmd.py` or `auditor.py`.
- **Item 009 territory** — `find_uncited_opportunity_rows` (per-driver gate), `find_missing_pick_citations`, `find_hallucinated_citations`, `find_uncited_conclusions`, `find_uncited_discipline_rows`, `find_incomplete_constituent_analyses` (the runtime aborter; item 006's Policy B is the gap-stamper, item 009 is the post-write blocker). The canonical-path `IRC_CITATION_ENFORCE_MODE=block` flip is item 009.
- **Per-mention strict citation enforcement.** Memo-stage `find_uncited_conclusions` reads memo prose `[ref:...]` markers and enforces "every mentioned stock owes a dual-leg citation". Item 006 does NOT inspect memo prose.
- **`derive_thesis_from_evidence` modifications.** Item 003 owns the `ThesisState`-literal-only contract; item 006 verifies it via criterion 13 but does not modify `derive_thesis_from_evidence`.
- **New AkShare adapters.** Item 005's NAV + announcement adapters cover the fund-level surface; item 003's per-constituent adapters cover the active-fund surface. No new I/O modules in item 006.
- **DuckDB persistence of rejections.** `rejections.json` is the single source of truth; no DuckDB ingest. Item 010's `fund_holdings` ingest is independent.
- **Backfilling `audit_errors` on cached `ConstituentAnalysis` JSON.** Existing on-disk caches predate the new field; cache reader tolerates the absence via dataclass default. Item 006 does NOT trigger a cache rebuild.
- **Failure-section rendering changes to the existing bucket sections** (`今日可定投`, `减速定投`, `暂停加仓`, `风险复核`, `调仓复核`, `退出复核`). Those continue to render via item 003's existing `_render_section` from `report.py`. Item 006 only adds the NEW failure section + V1 summary line at the end of `discipline_report.md`.

## Constraints

- **Functional programming.** Every new function in `rejection_log.py`, `policy_b.py`, and `failure_renderer.py` is pure. Mutation is restricted to (a) `write_rejections_json` (the I/O boundary, identical pattern to `atomic_write_text`), and (b) the `pending_verdicts: dict` constructed in `_build_rows` (a local accumulator passed by argument to `_write_opportunity_outputs`, never global). Frozen dataclasses + `dataclasses.replace` for `ConstituentAnalysis.audit_errors` mutation.
- **Public API stability.** New public files (`rejection_log.py`, `failure_renderer.py`) are additive. `_write_opportunity_outputs` adds a new `pending_verdicts` keyword argument (default `None` for backward compat with any test caller) but the function's behaviour for gap-free rows is **byte-identical** to before item 006: the `publishable_rows` partition matches what `kept_rows` was when no row carries `evidence_gaps`. The shape of `thesis_cards.yaml` + `opportunity_report.json` for non-gapped rows is unchanged.
- **Backward compat with item 003's cache JSON.** `ConstituentAnalysis.audit_errors` default-empty tuple → JSON cache files written by item 003 load via the existing `_active_fund_snapshot_from_dict` without changes (the missing key falls through to the dataclass default). No cache migration required.
- **No new third-party deps.** `math.ceil` and `dataclasses.replace` are stdlib.
- **Security / I/O surface.** All I/O confined to `outputs/{date}/rejections.json` + `outputs/{date}/discipline_report.md`. Atomic write via the existing `atomic_write_text` for both files. No reads outside the repo root.
- **Performance.** Policy B is O(top_N · |evidence|) per fund — typically O(10 · 5) = O(50) per fund × ~52 active funds = O(2600) ops per run. Negligible. The partition + sort step in `_write_opportunity_outputs` is O(n log n) on ~80 rows. No new hot paths.
- **Determinism.** `RejectionRecord` ordering = `(asset_class, instrument_id)` ascending. `ConstituentCoverageEntry` ordering inside each record = `weight_rank` ascending (rank 1 first). `material_symbols` ordering = `weight_rank` ascending. `decision_rule` strings are template-format-locked (criterion 11) so they diff cleanly across runs.
- **Test isolation.** Every Policy B test passes a fixture `ActiveFundSnapshot` directly to `evaluate_policy_b` — no AkShare mocking, no cache fixtures. Failure-renderer tests pass fixture `OpportunityRow` tuples. Rejection-log writer tests use `tmp_path` from pytest.

## Acceptance criteria

Each criterion is independently verifiable.

### H1 — `rejection_log.py` schema + writer

1. **`record_fund_rejection` builder.** `RejectionRecord` constructed by `record_fund_rejection(row=..., snapshot=ActiveFundSnapshot(...), verdict=PolicyBVerdict(gap_codes=("insufficient_info_coverage_top_half",), ...), rejection_reason="insufficient_info_coverage_top_half", decision_rule="info-leg quorum 5 of 10; 3 of material top-half satisfied")` carries: `instrument_id`, `name_cn`, `asset_class`, `rejection_reason`, `decision_rule`, `rejection_at_stage`, `constituent_coverage` length == `len(snapshot.constituent_analyses)`, `fund_level_failure_reasons`, `fetch_types_attempted`, `evidence_gaps`. All fields present.

2. **`ConstituentCoverageEntry.weight_rank` is 1-based.** For a 10-holding snapshot sorted descending by weight, ranks are `1..10`. Ties in weight resolve by `symbol` ascending; tied positions both receive the same `weight_rank` ONLY if they share the cutoff-boundary weight (otherwise consecutive ranks).

3. **`ConstituentCoverageEntry.in_material_top_half` matches `ceil(top_N/2)` semantics.** For `top_n=10` with no ties, ranks 1–5 → `in_material_top_half=True`, ranks 6–10 → `False`. With a tie at rank-5/rank-6 (both weight 4.2%), BOTH have `in_material_top_half=True` (material set extends to include all positions tied at the cutoff).

4. **`write_rejections_json` atomic write.** Writes `outputs/{date}/rejections.json` via `.tmp.{pid} → os.replace`. Concurrent writers (simulated via `tmp_path` + two processes) never observe a truncated file. Parent dir auto-created. JSON has `run_date`, `plan_hash`, `entries: [...]` keys.

5. **`RejectionsDocument.entries` ordering is `(asset_class, instrument_id)` ascending.** Two runs over the same fixture universe produce byte-identical `rejections.json`.

6. **Empty rejections case.** When `gapped_rows == []`, `rejections.json` is written with `entries: []` (NOT skipped — the empty file is the signal of "no rejections this run").

7. **`MATERIAL_HOLDING_QUORUM(n)` matches `math.ceil(n/2)`.** `MATERIAL_HOLDING_QUORUM(10) == 5`, `MATERIAL_HOLDING_QUORUM(3) == 2`, `MATERIAL_HOLDING_QUORUM(1) == 1`, `MATERIAL_HOLDING_QUORUM(0) == 0`.

### H2.v2 — Policy B verdict + gap stamping

8. **All 10 holdings with full data + ≥1 info each → publishable.** `evaluate_policy_b(snapshot, top_n=10)` returns `PolicyBVerdict(gap_codes=(), audit_errors=(), decision_rule="info-leg quorum 5 of 10; 5 satisfied (publishable)", material_symbols=<5 keys>, constituent_coverage=<10 entries>)`. NO rejection log entry written for this fund.

9. **5 of top-5 info-satisfied, positions 6–10 data-only → publishable.** Material set has 5 entries, 5 of 5 satisfy info-leg → publishable. Tail holdings data-only do NOT block.

10. **3 of material top-5 info-satisfied → blocked.** `gap_codes=("insufficient_info_coverage_top_half",)`, `decision_rule="info-leg quorum 5 of 10; 3 of material top-half satisfied"`. Rejection log entry includes the weight breakdown and material flag.

11. **Position 7 has no data leg → blocked.** `gap_codes=("incomplete_constituent_data",)`, `decision_rule="data leg missing for 1 of 10 holdings: ['{symbol_7}']"`. Rule 3 fires before rule 4 → reason is `incomplete_constituent_data`, NOT `insufficient_info_coverage_top_half` (criterion 14).

12. **All 10 with only `failure_reasons`, no evidence at all → blocked.** Rule 5 fires: `gap_codes=("incomplete_constituent_coverage",)`, `decision_rule="holdings with no evidence: 10 of 10"`. (Rule 3 also matches but rule 5 has higher precedence than rule 4 — see precedence list. Actually rule 3 fires FIRST because data-leg missing is detected before "no evidence at all". Resolution: rule 3 detects "any holding lacks data leg", which is true when `evidence==()`. Final precedence: 1 → 2 → 3 → 4 → 5. ADJUSTED: when `evidence==() AND failure_reasons != ()`, rule 3 catches it as data-leg missing → `incomplete_constituent_data`. **Locked**: the canonical "all 10 with only failure_reasons" case produces `incomplete_constituent_data` because every holding lacks a data leg. The `incomplete_constituent_coverage` gap fires when SOME holdings have no evidence AND OTHERS have partial evidence — i.e., the mixed case. Test must construct the mixed case to exercise rule 5.)

13. **Constituent with `evidence==() AND failure_reasons==()` → audit error.** `evaluate_policy_b` returns `gap_codes=("incomplete_constituent_record",)`, `audit_errors=("missing_constituent_record:<symbol>",)`. Rejection log entry's `constituent_coverage` includes the symbol with `audit_errors` populated. The `ConstituentCoverageEntry.audit_errors` field is non-empty for that row.

14. **Rule precedence — data-leg miss + info-leg miss → `incomplete_constituent_data`.** Constructed fixture: 10 holdings, 5 material, but position 3 (material) has no data leg AND positions 6–10 have no info leg (tail data-only). Rule 3 fires first → `gap_codes=("incomplete_constituent_data",)`. Rule 4 does NOT fire (short-circuit).

15. **`thesis_state` invariant under Policy B.** Construct a row where `derive_thesis_from_evidence` returned `thesis_state="evidence_insufficient"` AND Policy B stamps `gap_codes=("insufficient_info_coverage_top_half",)`. The resulting `OpportunityRow.thesis_state == "evidence_insufficient"` (one of the 4 literals — NOT a synthetic value). E10's locked test (item 008) re-asserts this; item 006's test asserts that `evaluate_policy_b` does NOT touch `thesis_state`.

16. **`ConstituentAnalysis.audit_errors` field default.** Construct `ConstituentAnalysis(symbol="600519", name_cn="贵州茅台", weight_pct=6.2, evidence=(...), failure_reasons=(), one_line_view="...")` (no `audit_errors` kwarg) → `audit_errors == ()`. Field is at the END of the dataclass; existing call sites compile unchanged.

### H3 — universal gapped-row invariant

17. **`_write_opportunity_outputs` skips thesis_cards for gapped rows.** Given `kept_rows = [r1 (gap-free), r2 (evidence_gaps=("qdii_information_unavailable",))]`, the resulting `thesis_cards.yaml` contains exactly 1 card (`r1`); `opportunity_report.json` `rows` list has 1 entry; `r2` does NOT appear.

18. **Failure renderer emits ONLY the 4 allowed fields.** Render output for a gapped row is matched against the regex `^- \\*\\*{instrument_id} {name_cn}\\*\\* ｜ 原因: .+ ｜ 已尝试: .+$`. Negative assertion: the output does NOT contain any of the strings: `opportunity_state`, `dca`, `risk`, `note_cn`, `valuation_state`, `heat_state`, `thesis_state`, `product_quality_state`, `opportunity_reason`. Additionally, a row with `opportunity_state="pause_wait"` AND `note_cn="暂停加仓"` (built BEFORE the gap was stamped — fixture construction injects these conclusion fields) renders in the failure section WITHOUT the `暂停加仓` token or any `pause_wait` token.

19. **All gap codes are recognised by `_classify_rejection_reason`.** Iterate over `_GAP_TO_REASON.keys()` and assert each maps to a valid `RejectionReasonCode`. Adding a new gap code to the codebase WITHOUT updating `_GAP_TO_REASON` causes the rejection_log writer to raise `RuntimeError` on that row — locked by a regression test that injects a synthetic gap code `evidence_gaps=("unknown_synthetic_gap",)` and asserts the raise.

20. **`fetch_budget_exhausted` is run-level fatal.** Construct a row with `evidence_gaps=("fetch_budget_exhausted",)` and call `_write_opportunity_outputs([row], ...)` → raises `RuntimeError` with message containing `"fetch_budget_exhausted"` and `"row-level emission is a programming error"`. NO `.tmp` files exist on disk after the raise (Step 1 fires BEFORE any `atomic_write_text` call). Locked invariant: `raise`, not `assert` (verified via running the test with `python -O`).

21. **Discipline report bucket sections exclude gapped rows.** `discipline_report.md`'s `今日可定投`, `减速定投`, `暂停加仓`, `风险复核`, `调仓复核`, `退出复核` sections contain ZERO mentions of any `gapped_row.instrument_id`. Gapped rows appear ONLY in the new `## 证据不足 / Failed fetch` section.

22. **`rejections.json` records all gapped funds.** Fixture universe: 3 publishable funds + 2 QDII-sentinel-gapped funds + 1 Policy-B-blocked active fund (info-leg quorum) + 1 fund with `holdings_fetch_failed` → `rejections.json` `entries` length == 4 (the gapped subset); publishable funds are absent.

### H4 — V1 systematic exclusions

23. **§1.2 footnote regression.** `grep -F "documents the systematic exclusion of US-heavy" docs/diagnosis-thesis-cards-evidence-gap.md` returns exactly 1 match (or matches the canonical phrase already shipped with Slice H2.v2). If the footnote is missing → test fails with a clear "H4 §1.2 footnote regressed" message.

24. **Once-per-run V1 systematic exclusion summary line.** `discipline_report.md` contains exactly one line matching `^## V1 systematic exclusions: \d+ funds excluded` — emitted UNCONDITIONALLY (zero-count case still renders `## V1 systematic exclusions: 0 funds excluded due to US-heavy material holdings`).

25. **N counts US-heavy funds correctly.** Fixture universe with 2 funds blocked by `insufficient_info_coverage_top_half`: fund A has 3 of 5 material holdings on US exchange (US-heavy); fund B has 1 of 5 (not US-heavy). Summary line counts exactly 1 fund. Fund A's `instrument_id` and `name_cn` appear in the "Excluded:" enumeration.

### MASTER-SPEC top-level acceptance items 7 + 8

26. **Item 7 (rejection trace) verify-against-output.** `outputs/<date>/rejections.json` exists after a non-empty rejection run. Each entry has all required fields: `instrument_id`, `name_cn`, `asset_class`, `rejection_reason`, `decision_rule`, `constituent_coverage` (with weight ranks + adapter-level `failure_reasons`). Schema validated against `RejectionsDocument` dataclass shape.

27. **Item 8 (V1 systematic exclusions) verify-against-output.** `discipline_report.md` contains the once-per-run summary line near the failure section naming the count of US-heavy material-holding funds excluded. The number matches `len([r for r in rejections.entries if _is_us_heavy(r.constituent_coverage)])`.

## Edge cases (locked by spec; tested in plan phase)

- **Fund with `top_n=10` but `len(constituent_analyses)==7` (provider returned 7 holdings).** `evaluate_policy_b(snapshot, top_n=10)` ranks the 7 holdings; `material = ceil(10/2) = 5`. The material set is the top-5 of the 7. If all 5 satisfy info-leg → publishable (even though `len(snapshot.constituent_analyses) < top_n`). The shortfall is NOT a Policy B blocker — that's an `incomplete_constituent_coverage` case only if some holdings have `failure_reasons != ()` AND `evidence == ()`.

- **Fund with `len(constituent_analyses) == 0` BUT `fund_level_failure_reasons == ()`.** Rule 1 does NOT fire (no fund-level failure). Rules 2–5 iterate an empty list and find nothing to gap-stamp. Verdict: `gap_codes=()`, `decision_rule="info-leg quorum 0 of {top_n}; 0 satisfied (publishable)"`. THIS IS A BUG SHAPE — the fund should never have empty constituent_analyses without a failure reason. Add a defensive guard: if `len(snapshot.constituent_analyses) == 0` AND `fund_level_failure_reasons == ()` → emit `audit_errors=("empty_constituent_analyses_without_failure_reason",)` and `gap_codes=("incomplete_constituent_record",)`. Locked by criterion: a fixture with empty `constituent_analyses` and empty `fund_level_failure_reasons` produces the audit-error path.

- **`top_n=0`.** Trivial; verdict is `gap_codes=()`, material set is empty. Should never occur in production (TOP_N_DEFAULT=10) but guarded for safety.

- **`top_n=1`.** `MATERIAL_HOLDING_QUORUM(1) == 1`. The single holding must satisfy BOTH data AND info legs to publish.

- **All weights equal (degenerate `weight_pct=10.0` × 10).** All holdings tie at rank 1; the material set extends to include ALL holdings (since every position is tied at the cutoff weight). Effectively becomes a full-quorum gate. Sort tiebreaker = `symbol` ascending for deterministic output ordering.

- **`evidence_gaps` contains a code from item 005's sentinel (`qdii_information_unavailable`) AND a Policy B code.** Should be impossible (item 005 sentinels are emitted only for `qdii_us`/`qdii_hk`/`qdii_global`, none of which run through Policy B because they are `FundLevelSnapshot` not `ActiveFundSnapshot`). But defensively, `_classify_rejection_reason` returns the FIRST matching gap in `_GAP_TO_REASON` precedence order (QDII first because it precedes Policy B codes in the dict literal). Locked test: fixture with both codes → reason = `"qdii_information_unavailable"`.

- **`replace(c, audit_errors=...)` does NOT modify the cached snapshot.** The snapshot loaded from `data/fundamentals/{quarter}/active_fund/fund_{iid}.json` is frozen; `evaluate_policy_b` constructs a NEW `ConstituentCoverageEntry` carrying the audit_errors. The cached JSON on disk is byte-identical before and after `evaluate_policy_b`. Locked test: assert sha256 of cache file unchanged after evaluate.

- **Multiple gap codes on a single row.** E.g., a row could acquire `incomplete_constituent_data` AND `insufficient_info_coverage_top_half` from a hypothetical future rule that doesn't short-circuit. Item 006 enforces short-circuit precedence (each rule returns immediately when it fires), so the verdict's `gap_codes` always has length ≤ 1 from Policy B's contribution. Items 003 + 005 may add additional gap codes (e.g. QDII sentinel) that combine with Policy B output via `row.evidence_gaps + verdict.gap_codes`. The rejection_log records all of them in the `evidence_gaps` mirror field.

## Open questions resolved during brainstorming

### Q1 — Placement of `record_fund_rejection` calls

**Question:** Should `_write_opportunity_outputs` invoke `record_fund_rejection` at the end (after partitioning rows into publishable vs gapped), OR should `_build_rows` invoke it as rows are computed?

**Recommendation:** `_write_opportunity_outputs` invokes it at the end. Three reasons:

1. `_build_rows` may be called multiple times in some test harnesses or future re-execution paths; emitting rejection records inside the row construction would risk duplicates.
2. The rejection_log needs the FULL `evidence_gaps` tuple including any post-stamping additions (e.g., a future slice could add late-stage gap stamping). Doing the partition + rejection-log build at the same place ensures a single source of truth.
3. The `pending_verdicts: dict[str, PolicyBVerdict]` accumulator stashed in `_build_rows` and consumed in `_write_opportunity_outputs` cleanly threads the verdict context (with `decision_rule` + `material_symbols` + `constituent_coverage`) without re-running Policy B.

**Adopted.** Spec §H3 wires `record_fund_rejection` into Step 4 of `_write_opportunity_outputs`, AFTER the partition.

### Q2 — Quorum formula constant placement

**Question:** Lock `ceil(top_N/2)` as an explicit module-level constant?

**Recommendation:** Yes — `MATERIAL_HOLDING_QUORUM = lambda n: math.ceil(n / 2)` exported from `rejection_log.py`. Reasons:

1. The formula is referenced in three places: `evaluate_policy_b`, the `ConstituentCoverageEntry.in_material_top_half` derivation, and the `decision_rule` string template. Centralising prevents drift.
2. Future asset classes (e.g. cn_bond_fund holdings, if V2 adds per-bond evidence) may want a different quorum — having the formula as a module constant makes the alternative call site `MATERIAL_HOLDING_QUORUM_BONDS = lambda n: math.ceil(n / 3)` trivial to add.
3. Tests directly assert `MATERIAL_HOLDING_QUORUM(n)` for `n ∈ {0, 1, 3, 10}` — locked by criterion 7.

**Adopted.** Defined in `rejection_log.py`.

### Q3 — "Material holdings by weight" semantic

**Question:** Top `ceil(top_N/2)` by `holding_weight_pct` (per-constituent weight), or by weight-sum threshold?

**Recommendation:** Top `ceil(top_N/2)` by `holding_weight_pct`, extended to include tied positions at the cutoff weight. The H2.v2 source language ("ceil(top_N/2) material holdings by weight, ties resolved by including both") commits to count-based, not threshold-based.

**Adopted.** §H2.v2 rule 4 + the "Material-set tie rule" lock the semantic. Threshold-based interpretation is explicitly rejected — it would introduce a free parameter (the threshold) and complicate determinism.

### Q4 — Gapped rows in rejection_log output

**Question:** Should gapped rows still appear in `rejection_log.py`'s output?

**Recommendation:** YES. `rejections.json` is the full audit trail; every gapped row gets one entry. Publishable rows (gap-free) get NO entry. The failure section in `discipline_report.md` is the human-readable view; `rejections.json` is the machine-readable view; both come from the same `gapped_rows` partition.

**Adopted.** Criterion 22 locks this.

### Q5 — `fetch_budget_exhausted` collision with item 003's preflight gate

**Question:** Does item 006's H3 invariant conflict with item 003's `FetchBudgetExceeded` exception?

**Recommendation:** No conflict — both gates fire, both must hold. Item 003's preflight check raises BEFORE `_build_rows` returns (so no row ever carries `fetch_budget_exhausted` in production). Item 006's H3 Step 1 is a defence-in-depth assertion: if a row somehow carries the gap (e.g., a future hand-stamped gap, a fuzz test, or a bug in `_build_rows`), the write step raises immediately. The two together guarantee no `.tmp` artefacts are ever written when the budget gate trips.

**Adopted.** Criterion 20 locks the row-level emission as fatal.

### Q6 — `rejections.json` schema

**Question:** Propose a frozen-dataclass-backed JSON shape.

**Recommendation:** As specified in §H1. `RejectionsDocument` is the top-level container; `entries: tuple[RejectionRecord, ...]` carries per-fund records; each record has `constituent_coverage: tuple[ConstituentCoverageEntry, ...]` for the weight-ranked per-stock breakdown. Reason codes are a `Literal` for type safety. `decision_rule` is a free-form human-readable string with locked template formats (criterion 11).

**Adopted.** §H1 spec dataclasses + the JSON serialisation via `dataclasses.asdict`.

### Q7 — `audit_error="missing_constituent_record"` field placement

**Question:** Does the audit error land on a different field than `evidence_gaps`?

**Recommendation:** YES — add `audit_errors: tuple[str, ...] = ()` to `ConstituentAnalysis`. The semantic distinction:

- **`failure_reasons` (item 003)** — adapter-level catastrophes ("filing_fetch_failed:600519:ConnectionError"). The adapter ran but couldn't produce evidence.
- **`evidence_gaps` (`OpportunityRow.evidence_gaps`)** — fund-row-level gap codes derived from the constituent set ("incomplete_constituent_data", "insufficient_info_coverage_top_half"). The fund as a whole cannot publish.
- **`audit_errors` (item 006 NEW)** — invariant violations at the data-shape level ("missing_constituent_record:600519" = the constituent was emitted but carries neither evidence nor failure_reasons, which item 003's contract forbids). The shape is corrupt.

Item 009's `find_incomplete_constituent_analyses` reads BOTH `failure_reasons` and `audit_errors` (when it lands) — different predicate, different raise message.

**Adopted.** §H2.v2 schema additions add the field. Criterion 16 locks the default. Item 003's existing tests are unaffected (trailing default field).

## Files touched (preview for planner)

| File | Action |
|---|---|
| `src/irc/opportunity/rejection_log.py` (NEW) | Define `RejectionReasonCode`, `ConstituentCoverageEntry`, `RejectionRecord`, `RejectionsDocument`, `PolicyBVerdict`, `MATERIAL_HOLDING_QUORUM`, `evaluate_policy_b`, `record_fund_rejection`, `write_rejections_json`. |
| `src/irc/opportunity/failure_renderer.py` (NEW) | Define `render_failure_section`, `render_v1_systematic_exclusion_summary`, `_is_us_heavy`. |
| `src/irc/fundamentals/types.py` | Add `audit_errors: tuple[str, ...] = ()` to `ConstituentAnalysis` (END of dataclass, after `one_line_view`). |
| `src/irc/commands/opportunity_cmd.py` | Wire Policy B into `_build_rows` (after `build_opportunity_row`); thread `pending_verdicts: dict[str, PolicyBVerdict]` into `_write_opportunity_outputs`. In `_write_opportunity_outputs`: add Step 1 (`fetch_budget_exhausted` raise), Step 2 (partition), Step 3 (publishable-only emit), Step 4 (`write_rejections_json`), Step 5 (compose discipline markdown with failure section + V1 summary). |
| `tests/opportunity/test_rejection_log.py` (NEW) | Unit tests for criteria 1–7, 19, 22. |
| `tests/opportunity/test_policy_b.py` (NEW) | Unit tests for criteria 8–16. |
| `tests/opportunity/test_failure_renderer.py` (NEW) | Unit tests for criteria 17, 18, 21, 24, 25. |
| `tests/commands/test_opportunity_cmd.py` | Add integration tests for criteria 17, 20, 21, 22, 26, 27. |
| `docs/diagnosis-thesis-cards-evidence-gap.md` | Verify §1.2 footnote intact (criterion 23) — no edit unless regressed. |
| `CONTEXT.md` | Append "Failure-mode + Policy B" glossary section (grill phase decides) with `Policy B`, `Material top-half quorum`, `audit_errors vs evidence_gaps vs failure_reasons`, `Rejection log`, `V1 systematic exclusion`. |
| `docs/adr/0002-active-fund-fetch-engine.md` (optional) | §6 amendment OR new ADR 0003 — grill phase decides whether the failure-mode policy warrants a co-located decision or a standalone ADR. Lean toward §6 amendment ("Failure-mode evaluation policy") since Policy B operates on engine outputs. |

## Dependencies on other items

**Hard requires (must merge before item 006):**

- Item 001 (`contributing_dimensions` + `fetch_types_attempted`) — already merged.
- Item 002 (citation data model + `evidence_gaps` field semantics) — already merged.
- Item 003 (`ActiveFundSnapshot`, `ConstituentAnalysis`, `failure_reasons_by_symbol`, `fund_level_failure_reasons`) — already merged.
- Item 005 (`FundLevelSnapshot`, QDII sentinel emitting `evidence_gaps=("qdii_information_unavailable",)`, `_classify_fund_level_scores`) — already merged.

**Required-by (items that read item 006's outputs):**

- Item 007 (memo + discipline renderers) — reads `rejections.json` for the discipline failure expansion and for the §2 audit narrative; reads `OpportunityRow.evidence_gaps` + `fetch_types_attempted` (which item 006 stamps for active funds) for the failure section in `discipline_report.md`.
- Item 008 (integration sweep) — E10 coverage smoke asserts `publishable_rows` (the H3 partition) all have `evidence_gaps == ()` + dual-coverage citations + `thesis_state ∈ {4 literals}`. E11 manual checklist references `rejections.json`.
- Item 009 (citation gate block mode) — `find_uncited_opportunity_rows` runs on the `publishable_rows` subset (item 006's partition); `find_incomplete_constituent_analyses` reads `ConstituentAnalysis.audit_errors` (item 006's new field) AND `ConstituentAnalysis.failure_reasons`.

## Notes for the grill phase

1. **ADR amendment vs. ADR 0003?** Policy B is a downstream consumer of the fetch engine's `ActiveFundSnapshot`, not a contract of the engine itself. Co-locating in ADR 0002 §6 ("Failure-mode evaluation policy") keeps the "fetch + evaluate" decision surface in one document. New ADR 0003 would be appropriate if the audit-policy layer grows beyond Policy B (e.g., adds memo-stage strict-mention enforcement). Lean toward §6 amendment for V1.

2. **CONTEXT.md additions auto-accepted under autonomy override 2026-05-23.** New glossary entries (grill phase commits these): `Policy B (weight-aware quorum)`, `Material top-half quorum`, `Rejection log`, `Audit error vs evidence gap vs failure reason`, `V1 systematic exclusion (US-heavy)`.

3. **`evaluate_policy_b` is a pure function on `ActiveFundSnapshot`** — does NOT call adapters, does NOT touch caches. Tests inject `ActiveFundSnapshot` directly. Item 003's snapshot construction is the upstream producer; item 006 is the consumer.

4. **Why is Policy B applied ONLY to `ActiveFundSnapshot`?** Because passive `FundLevelSnapshot` (item 005) does not have per-constituent evidence — its citations are fund-level NAV + announcements, evaluated by the dual-coverage gate in item 009 (`find_uncited_opportunity_rows`). Policy B is the per-constituent quorum layer; it has no meaning for passive funds. The QDII sentinel emits `evidence_gaps=("qdii_information_unavailable",)` directly from item 005 — item 006 only records the rejection via `_classify_rejection_reason` and `record_fund_rejection`.

5. **Why is `pending_verdicts` necessary?** Without it, `_write_opportunity_outputs` would need to either (a) re-evaluate Policy B from scratch (re-loading snapshots from `snapshot_cache`, doubling compute) or (b) recover `decision_rule` and `material_symbols` from the row's `evidence_gaps` (which doesn't carry them — `evidence_gaps` is a flat tuple of code strings). The verdict object is the clean carrier for the cross-function context. Locked.

6. **The "missing_constituent_record" audit error overlaps with item 009's `find_incomplete_constituent_analyses`.** Item 006 STAMPS the audit-error on the `ConstituentCoverageEntry` (read-only — derived from snapshot inspection). Item 009 RAISES on the same predicate (write-time blocking). The two are layered: item 006 documents the audit error in `rejections.json` so it's visible WITHOUT triggering item 009's block (because item 009 only runs on `publishable_rows`, and a fund with the audit error is gap-stamped → routed to `gapped_rows` → never seen by item 009). The item 009 raise is a defence-in-depth check for the case where Policy B failed to stamp the gap (programming error).
