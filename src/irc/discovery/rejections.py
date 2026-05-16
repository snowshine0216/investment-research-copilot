from __future__ import annotations

import pandas as pd

from irc.discovery.hard_filter import HardFilterResult, Rejection
from irc.discovery.role_bucket import RoleBucketResult
from irc.discovery.universe import UniverseRow


REJECTION_COLUMNS = (
    "stage", "instrument_id", "ticker", "name_cn",
    "asset_class", "theme", "role", "reasons",
)


def _index_universe(rows: tuple[UniverseRow, ...]) -> dict[str, UniverseRow]:
    return {r.instrument_id: r for r in rows}


def _row_for_rejection(stage: str, rej: Rejection, universe_by_id: dict[str, UniverseRow]) -> dict[str, str]:
    row = universe_by_id.get(rej.instrument_id)
    return {
        "stage": stage,
        "instrument_id": rej.instrument_id,
        "ticker": row.ticker if row else rej.instrument_id,
        "name_cn": row.name_cn if row else "",
        "asset_class": row.asset_class if row else "",
        "theme": (row.theme if row and row.theme is not None else ""),
        "role": "",
        "reasons": "; ".join(rej.reasons),
    }


def _build_orphan_row(orphan_id: str, row: UniverseRow | None) -> dict[str, str]:
    return {
        "stage": "role_bucket",
        "instrument_id": orphan_id,
        "ticker": row.ticker if row else orphan_id,
        "name_cn": row.name_cn if row else "",
        "asset_class": row.asset_class if row else "",
        "theme": (row.theme if row and row.theme is not None else ""),
        "role": "",
        "reasons": "no_role_match",
    }


def _collect_orphan_rows(
    quality_passed: tuple[UniverseRow, ...],
    bucketed: RoleBucketResult,
    universe_by_id: dict[str, UniverseRow],
) -> list[dict[str, str]]:
    bucketed_ids: set[str] = {
        r.instrument_id for items in bucketed.buckets.values() for r in items
    }
    quality_passed_ids = {r.instrument_id for r in quality_passed}
    orphan_rows: list[dict[str, str]] = []
    for orphan_id in sorted(quality_passed_ids - bucketed_ids):
        row = universe_by_id.get(orphan_id)
        orphan_rows.append(_build_orphan_row(orphan_id, row))
    return orphan_rows


def build_discovery_rejections(
    universe: tuple[UniverseRow, ...],
    hard: HardFilterResult,
    quality: HardFilterResult,
    bucketed: RoleBucketResult,
) -> pd.DataFrame:
    universe_by_id = _index_universe(universe)
    rows: list[dict[str, str]] = []
    rows.extend(_row_for_rejection("hard_filter", rej, universe_by_id) for rej in hard.rejected)
    rows.extend(_row_for_rejection("quality_filter", rej, universe_by_id) for rej in quality.rejected)
    rows.extend(_collect_orphan_rows(quality.passed, bucketed, universe_by_id))
    return pd.DataFrame(rows, columns=list(REJECTION_COLUMNS))
