from __future__ import annotations

from dataclasses import dataclass

from irc.schemas.universe import Instrument, UniverseConfig


@dataclass(frozen=True)
class UniverseRow:
    instrument_id: str
    ticker: str
    market: str
    name_cn: str
    asset_class: str
    currency: str
    tracked_index: str | None
    theme: str | None
    venue_required: tuple[str, ...]


def _to_row(i: Instrument) -> UniverseRow:
    return UniverseRow(
        instrument_id=i.instrument_id,
        ticker=i.ticker,
        market=i.market,
        name_cn=i.name_cn,
        asset_class=i.asset_class,
        currency=i.currency,
        tracked_index=i.tracked_index,
        theme=i.theme,
        venue_required=tuple(i.venue_required),
    )


def enumerate_universe(
    qdii_us: UniverseConfig,
    qdii_hk: UniverseConfig,
    cn_funds: UniverseConfig,
    gold: UniverseConfig,
) -> tuple[UniverseRow, ...]:
    """Step 1 of Discovery: combine all universe files, dedup by instrument_id."""
    seen: set[str] = set()
    out: list[UniverseRow] = []
    for cfg in (qdii_us, qdii_hk, cn_funds, gold):
        for instr in cfg.instruments:
            if instr.instrument_id in seen:
                continue
            seen.add(instr.instrument_id)
            out.append(_to_row(instr))
    return tuple(out)
