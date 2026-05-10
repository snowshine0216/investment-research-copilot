from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pandas as pd

from irc.discovery.hard_filter import HardFilterResult
from irc.discovery.role_bucket import RoleBucketResult
from irc.discovery.universe import UniverseRow


DIAGNOSTIC_COLUMNS = ("stage", "status", "asset_class", "theme", "role", "reason", "count")


@dataclass(frozen=True)
class DiagnosticRow:
    stage: str
    status: str
    asset_class: str
    theme: str
    role: str
    reason: str
    count: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "stage": self.stage,
            "status": self.status,
            "asset_class": self.asset_class,
            "theme": self.theme,
            "role": self.role,
            "reason": self.reason,
            "count": self.count,
        }


def _theme_label(value: str | None) -> str:
    return value if value is not None else "none"


def _index_universe(rows: tuple[UniverseRow, ...]) -> dict[str, UniverseRow]:
    return {row.instrument_id: row for row in rows}


def _count_rows(stage: str, status: str, rows: tuple[UniverseRow, ...]) -> list[DiagnosticRow]:
    counts = Counter((row.asset_class, _theme_label(row.theme)) for row in rows)
    return [
        DiagnosticRow(stage, status, asset_class, theme, "", "", count)
        for (asset_class, theme), count in sorted(counts.items())
    ]


def _count_rejections(
    stage: str,
    result: HardFilterResult,
    universe_by_id: dict[str, UniverseRow],
) -> list[DiagnosticRow]:
    counts: Counter[tuple[str, str, str]] = Counter()
    for rejection in result.rejected:
        row = universe_by_id.get(rejection.instrument_id)
        asset_class = row.asset_class if row is not None else "unknown"
        theme = _theme_label(row.theme) if row is not None else "unknown"
        for reason in rejection.reasons:
            counts[(asset_class, theme, reason)] += 1
    return [
        DiagnosticRow(stage, "rejected", asset_class, theme, "", reason, count)
        for (asset_class, theme, reason), count in sorted(counts.items())
    ]


def _count_roles(bucketed: RoleBucketResult) -> list[DiagnosticRow]:
    rows = [
        DiagnosticRow("role_bucket", "bucketed", "", "", role, "", len(items))
        for role, items in sorted(bucketed.buckets.items())
    ]
    rows.extend(
        DiagnosticRow("role_bucket", "relaxed", "", "", role, "below min_candidates_per_role", len(bucketed.buckets.get(role, ())))
        for role in sorted(bucketed.relaxed_roles)
    )
    rows.extend(
        DiagnosticRow("role_bucket", "failed", "", "", role, "below fail_below", 0)
        for role in sorted(bucketed.failed_roles)
    )
    return rows


def build_discovery_diagnostics(
    universe: tuple[UniverseRow, ...],
    hard: HardFilterResult,
    quality: HardFilterResult,
    bucketed: RoleBucketResult,
) -> pd.DataFrame:
    universe_by_id = _index_universe(universe)
    rows: list[DiagnosticRow] = []
    rows.extend(_count_rows("universe", "input", universe))
    rows.extend(_count_rows("hard_filter", "passed", hard.passed))
    rows.extend(_count_rejections("hard_filter", hard, universe_by_id))
    rows.extend(_count_rows("quality_filter", "passed", quality.passed))
    rows.extend(_count_rejections("quality_filter", quality, universe_by_id))
    rows.extend(_count_roles(bucketed))
    return pd.DataFrame([row.as_dict() for row in rows], columns=list(DIAGNOSTIC_COLUMNS))
