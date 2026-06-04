"""Item 009 D2a — opportunity-stage structural auditor.

Pure functions consumed by the opportunity-stage gate in
`src/irc/commands/opportunity_cmd.py::_write_opportunity_outputs`. No I/O.

`find_uncited_opportunity_rows` implements the v1 STRUCTURAL dual-leg binding:
for each publishable OpportunityRow, require ≥1 entry in `row.thesis_evidence`
with `citation_kind == "data"` AND ≥1 with `citation_kind == "information"`,
both with `owner_instrument_id == row.instrument_id` and scope in
{"instrument","constituent"}. The v2 `(type → dimension)` map is a deliberate
deferral — see Q1 in `docs/2026-05-22-thesis-cards-evidence-gap/items/009-grill.md`.

`find_incomplete_constituent_analyses` catches pure-failure constituents
(`evidence == () AND failure_reasons != ()`) that escaped H2's gap stamp; a
finding here is fatal at the gate-wiring caller (raises RuntimeError).
"""
from __future__ import annotations

from irc.memo.numeric_audit import NumericFinding
from irc.opportunity.types import OpportunityRow


_PUBLISHABLE_SCOPES: frozenset[str] = frozenset({"instrument", "constituent"})


def find_uncited_opportunity_rows(
    publishable_rows: tuple[OpportunityRow, ...] | list[OpportunityRow],
    cited_map: dict,
) -> list[NumericFinding]:
    """Return a list of NumericFinding for rows that fail the v1 structural
    dual-leg dual-scope check.

    Per AC6 row-level restriction rule: emits at most ONE finding per missing
    leg per row (not per-dimension). `prose_excerpt` carries
    `"dimension:<first dim sorted>"` for log-reader context; v2 will expand
    to per-dimension findings once the `(type → dimension)` map exists.
    """
    findings: list[NumericFinding] = []
    for row in publishable_rows:
        owned_data = [
            ev for ev in row.thesis_evidence
            if ev.citation_kind == "data"
            and ev.scope in _PUBLISHABLE_SCOPES
            and ev.owner_instrument_id == row.instrument_id
        ]
        owned_info = [
            ev for ev in row.thesis_evidence
            if ev.citation_kind == "information"
            and ev.scope in _PUBLISHABLE_SCOPES
            and ev.owner_instrument_id == row.instrument_id
        ]
        dims_sorted = sorted(row.contributing_dimensions) or ["<none>"]
        dim_excerpt = f"dimension:{dims_sorted[0]}"
        if not owned_data:
            findings.append(NumericFinding(
                instrument_id=row.instrument_id,
                kind="missing_data_citation",
                prose_excerpt=dim_excerpt,
                evidence_excerpt=row.opportunity_state,
            ))
        if not owned_info:
            findings.append(NumericFinding(
                instrument_id=row.instrument_id,
                kind="missing_information_citation",
                prose_excerpt=dim_excerpt,
                evidence_excerpt=row.opportunity_state,
            ))
    return findings


def find_incomplete_constituent_analyses(
    publishable_rows: tuple[OpportunityRow, ...] | list[OpportunityRow],
    *,
    foreign_heavy_exempt_ids: frozenset[str] = frozenset(),
) -> list[NumericFinding]:
    """Return a NumericFinding per ConstituentAnalysis with `evidence == ()`
    AND `failure_reasons != ()` on a publishable row.

    Per Q9 grill correction: a finding from this function is FATAL at the
    opportunity-stage gate caller (it raises RuntimeError, ignoring
    `IRC_CITATION_ENFORCE_MODE` — same shape as `fetch_budget_exhausted`).
    Kept as a structured NumericFinding rather than an in-function raise so
    the auditor module stays pure and uniformly testable.

    Partial-success constituents (`evidence != () AND failure_reasons != ()`)
    are NOT violations — Policy B's per-holding data leg + top-half info
    quorum is the correct disposition.

    `foreign_heavy_exempt_ids` are the instrument_ids whose Policy B verdict
    published via rule 2.5 (foreign-heavy short-circuit; `fired_rule == "2.5"`,
    `gap_codes == ()`). Rule 2.5 publishes the fund on fund-level NAV +
    announcement evidence and bypasses ALL per-holding checks (ADR 0003 §7),
    so a pure-failure foreign constituent on such a row is EXPECTED — the CN
    filings pipeline is structurally unreachable for HK/US tickers — and is
    NOT the gap-stamp escape this gate exists to catch. The fund's whole row
    is therefore skipped, mirroring rule 2.5's short-circuit. The failed
    constituent still surfaces as `❌` in the `## 持仓明细` appendix.
    """
    findings: list[NumericFinding] = []
    for row in publishable_rows:
        if row.instrument_id in foreign_heavy_exempt_ids:
            continue
        for c in row.constituent_analyses:
            if c.evidence == () and c.failure_reasons != ():
                findings.append(NumericFinding(
                    instrument_id=row.instrument_id,
                    kind="constituent_pure_failure",
                    prose_excerpt=f"symbol={c.symbol}",
                    evidence_excerpt=(
                        f"evidence=() failure_reasons={c.failure_reasons!r}"
                    ),
                ))
    return findings
