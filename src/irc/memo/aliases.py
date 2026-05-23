"""Item 007 D1c — alias-builder.

Pure function `build_alias_maps` constructs `InstrumentAliases` +
`ConstituentAliases` from a tuple of publishable `OpportunityRow`s. Consumed
by item 009's `find_uncited_conclusions` to map memo prose mentions back to
rows.

Determinism rule (ADR 0004 §1): consumers MUST `sorted(fs)` before iterating
a `ConstituentAliases` frozenset whose iteration order would affect rendered
output or audit-finding emission.

See [ADR 0004 §1 + §2](../../../docs/adr/0004-renderer-determinism-and-alias-policy.md).
"""
from __future__ import annotations

from irc.opportunity.types import OpportunityRow


InstrumentAliases = dict[str, str]
"""alias-string → instrument_id"""

ConstituentAliases = dict[str, frozenset[tuple[str, str]]]
"""stock identifier (symbol OR name_cn) → frozenset of (instrument_id, constituent_key)"""


class InstrumentAliasCollisionError(RuntimeError):
    """Raised by build_alias_maps when an alias-string resolves to two
    different instrument_id values (e.g. two unrelated funds sharing
    name_cn due to malformed opportunity_report.json).

    Loud, fail-fast, deterministic — see ADR 0004 §2. Raise happens AT
    BUILD time, never at lookup time.
    """


def build_alias_maps(
    publishable_rows: tuple[OpportunityRow, ...],
) -> tuple[InstrumentAliases, ConstituentAliases]:
    """Pure function. Build alias maps from publishable rows.

    Raises `InstrumentAliasCollisionError` if any alias key maps to two
    different `instrument_id` values. Multi-owner constituents (same stock
    held by ≥2 funds) accumulate into a frozenset — this is the NORMAL case
    for blue-chip names and never raises.
    """
    # Instrument-level: working dict[alias_key, set[instrument_id]] for collision detection.
    inst_working: dict[str, set[str]] = {}
    for r in publishable_rows:
        for alias in _instrument_alias_keys(r):
            if not alias:
                continue
            inst_working.setdefault(alias, set()).add(r.instrument_id)

    # Final pass: collapse + collision check.
    instrument_aliases: InstrumentAliases = {}
    for alias, iids in inst_working.items():
        if len(iids) > 1:
            raise InstrumentAliasCollisionError(
                f"alias {alias!r} resolves to multiple instrument_ids: "
                f"{sorted(iids)}"
            )
        instrument_aliases[alias] = next(iter(iids))

    # Constituent-level: accumulate frozensets directly (multi-owner is normal).
    cons_working: dict[str, set[tuple[str, str]]] = {}
    for r in publishable_rows:
        for c in r.constituent_analyses:
            tup = (r.instrument_id, c.symbol)
            if c.symbol:
                cons_working.setdefault(c.symbol, set()).add(tup)
            if c.name_cn:
                cons_working.setdefault(c.name_cn, set()).add(tup)

    constituent_aliases: ConstituentAliases = {
        key: frozenset(tups) for key, tups in cons_working.items()
    }

    return instrument_aliases, constituent_aliases


def _instrument_alias_keys(row: OpportunityRow) -> tuple[str, ...]:
    """Return the alias-string set for one OpportunityRow.

    Sources: (a) bare instrument_id, (b) canonical name_cn, (c) the
    lookthrough_target.key WHEN it textually contains `instrument_id` and is
    therefore guaranteed-unique (e.g. `fund_005827` for active funds, or
    `510300.SH` for hypothetical venue-suffixed forms).

    NEVER include `lookthrough_target.key` when it's a SHARED descriptor like
    `"csi300"`, `"gold"`, `"cn_bond"`, `"qdii_us"`, or `"global_equity"` —
    those collide with every other ETF tracking the same index, and the
    `InstrumentAliasCollisionError` is raised on every normal production run
    where more than one such ETF is publishable (per the post-ship review
    finding that ANY two CSI 300 ETFs or two gold ETFs trigger the collision).
    """
    keys: list[str] = [row.instrument_id]
    if row.name_cn:
        keys.append(row.name_cn)
    lt_key = getattr(row.lookthrough_target, "key", "")
    # Only include lt_key as an alias if it embeds the instrument_id (and
    # is therefore unique). Shared cross-instrument keys are excluded.
    if lt_key and lt_key != row.instrument_id and row.instrument_id in lt_key:
        keys.append(lt_key)
    return tuple(keys)
