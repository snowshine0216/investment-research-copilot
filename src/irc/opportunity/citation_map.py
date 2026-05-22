"""Build a `CitedMap` from a sequence of `OpportunityRow`s.

Pure function. Consumed by audit gates (item 009) immediately before
`atomic_write_text` of `opportunity_report.json` and `memo.md`; a duplicate
citation_id or a wrong-owner mismatch aborts the run before a polluted
artifact reaches disk.

This slice (item 002) lands the function but does NOT call it from any write
path — that wire-up is item 009's responsibility per ADR 0001 §4.
"""
from __future__ import annotations

from irc.opportunity.types import CitationMeta, CitedMap, OpportunityRow


def build_cited_map(rows: tuple[OpportunityRow, ...]) -> CitedMap:
    """Walk every row's `thesis_evidence`, validate provenance, and build the map.

    Raises:
      RuntimeError: if any evidence's `owner_instrument_id != row.instrument_id`.
      RuntimeError: if any `citation_id` appears under two DIFFERENT owners
        (genuine hash collision; 64-bit birthday risk ≈ 2.7e-10 per 100k
        citations).
    """
    cited: dict[str, dict[str, CitationMeta]] = {}
    # Owner-of-id tracking for cross-owner duplicate-id detection.
    owner_of_id: dict[str, str] = {}

    for row in rows:
        for ev in row.thesis_evidence:
            if ev.owner_instrument_id != row.instrument_id:
                raise RuntimeError(
                    f"provenance mismatch: evidence owner_instrument_id="
                    f"{ev.owner_instrument_id!r} but row.instrument_id="
                    f"{row.instrument_id!r} (citation_id={ev.citation_id!r})"
                )
            prior_owner = owner_of_id.get(ev.citation_id)
            if prior_owner is not None and prior_owner != row.instrument_id:
                raise RuntimeError(
                    f"duplicate citation_id {ev.citation_id!r} appears under "
                    f"two different owners: {prior_owner!r} and "
                    f"{row.instrument_id!r}"
                )
            owner_of_id[ev.citation_id] = row.instrument_id
            cited.setdefault(row.instrument_id, {})[ev.citation_id] = CitationMeta(
                scope=ev.scope,
                citation_kind=ev.citation_kind,
                owner_instrument_id=ev.owner_instrument_id,
                asset_class=row.asset_class,
                parent_fund_id=ev.parent_fund_id,
                constituent_key=ev.constituent_key,
            )
    return cited
