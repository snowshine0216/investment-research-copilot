"""Frozen data contracts for the sector rotation radar (spec §4/§5)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BoardDay:
    date: str
    board_code: str
    board_name: str
    chg_pct: float
    main_inflow_ratio: float | None
    turnover_pct: float | None
    board_pe: float | None  # f9 市盈率 from the snapshot; None when genuinely absent
    source: str  # "snapshot" | "backfill"


@dataclass(frozen=True)
class BoardState:
    board_code: str
    board_name: str
    state: str  # "emerging" | "hot" | "fading" | "quiet"
    days_in_state: int
    composite_pctl: float
    mom20: float
    flow5: float | None
    turn_delta: float
    pe_pctl: float | None
    chase_risk: bool


@dataclass(frozen=True)
class ExposureRow:
    fund_id: str
    name_cn: str
    board_code: str
    exposure_pct: float
    matched_symbols: tuple[str, ...]
    holdings_as_of: str | None


@dataclass(frozen=True)
class RotationCandidate:
    fund_id: str
    name_cn: str
    board_code: str
    board_name: str
    exposure_pct: float
    on_discovered_watchlist: bool
    in_monitor_set: bool
    held: bool
    holdings_as_of: str | None


@dataclass(frozen=True)
class RotationReport:
    schema_version: int
    radar_version: int
    data_status: str  # "ok" | "degraded_flow_dark" | "abstain"
    board_states: tuple[BoardState, ...]
    candidates: tuple[RotationCandidate, ...]
    diagnostics: dict = field(default_factory=dict)
