from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class MetricReport:
    name: str
    value: float
    status: str
    n_observations: int = 0
    threshold: dict[str, float] = field(default_factory=dict)
    details_ref: str | None = None


@dataclass(frozen=True)
class StageReport:
    stage: str
    ran_at: str
    based_on: list[str]
    metrics: list[MetricReport]
    overall: str
    notes: str = ""
    config_versions: dict[str, str] = field(default_factory=dict)


def report_to_dict(r: StageReport) -> dict[str, Any]:
    return asdict(r)
