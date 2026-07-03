"""PURE promotion diff between two opportunity_report row sets (no I/O).

A *promotion* is an instrument NEWLY reaching the actionable end of a track
today, relative to the most recent prior run:

- ``state`` track: ``opportunity_state == "core_dca"`` where the prior state
  was anything else (or the instrument was absent from the prior report).
- ``dca`` track: ``dca_action == "accelerate_dca"`` where the prior action
  was anything else (or absent).

No prior report at all (``prior_date=None``) yields an EMPTY diff — a
first-ever run must not page every core_dca fund as newly promoted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

PROMOTED_STATE = "core_dca"
PROMOTED_DCA = "accelerate_dca"


@dataclass(frozen=True)
class Promotion:
    instrument_id: str
    name_cn: str
    kind: str            # "state" | "dca"
    prior: str | None    # None = absent from the prior report
    current: str


@dataclass(frozen=True)
class PromotionDiff:
    prior_date: str | None
    promotions: tuple[Promotion, ...]

    @property
    def instrument_ids(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for p in self.promotions:
            seen.setdefault(p.instrument_id, None)
        return tuple(seen)


def _track_promotion(
    iid: str, name: str, kind: str,
    current: str | None, prior: str | None, promoted_value: str,
) -> Promotion | None:
    if current != promoted_value or prior == promoted_value:
        return None
    return Promotion(iid, name, kind, prior, promoted_value)


def _row_promotions(
    row: Mapping[str, Any], prior_row: Mapping[str, Any] | None,
) -> tuple[Promotion, ...]:
    iid = str(row.get("instrument_id") or "")
    name = str(row.get("name_cn") or "")
    prior_state = str(prior_row.get("opportunity_state") or "") if prior_row else None
    prior_dca = str(prior_row.get("dca_action") or "") if prior_row else None
    out = (
        _track_promotion(iid, name, "state", str(row.get("opportunity_state") or ""),
                         prior_state, PROMOTED_STATE),
        _track_promotion(iid, name, "dca", str(row.get("dca_action") or ""),
                         prior_dca, PROMOTED_DCA),
    )
    return tuple(p for p in out if p is not None)


def diff_promotions(
    today_rows: Sequence[Mapping[str, Any]],
    prior_rows: Sequence[Mapping[str, Any]],
    *, prior_date: str | None,
) -> PromotionDiff:
    if prior_date is None:
        return PromotionDiff(prior_date=None, promotions=())
    prior_by_id = {
        str(r.get("instrument_id")): r
        for r in prior_rows if r.get("instrument_id")
    }
    promotions: list[Promotion] = []
    for row in today_rows:
        iid = str(row.get("instrument_id") or "")
        if not iid:
            continue
        promotions.extend(_row_promotions(row, prior_by_id.get(iid)))
    return PromotionDiff(prior_date=prior_date, promotions=tuple(promotions))


def promotions_block(diff: PromotionDiff) -> dict[str, Any]:
    """JSON-serializable block for decision_report.json embedding."""
    return {
        "prior_date": diff.prior_date,
        "rows": [
            {
                "instrument_id": p.instrument_id, "name_cn": p.name_cn,
                "kind": p.kind, "prior": p.prior, "current": p.current,
            }
            for p in diff.promotions
        ],
    }
