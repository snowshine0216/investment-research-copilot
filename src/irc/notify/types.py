"""Frozen value types for the outcome notifier.

`RunOutcome` carries every input the pure classifier needs — the command edge
reads the clock, filesystem, and exit code and packs them here so
`classify_run_outcome` stays deterministic and mock-free.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from irc.notify.health import HealthDigest

Severity = Literal["failed", "halted", "stale", "degraded", "action", "clean"]
RunKind = Literal["daily", "weekly", "monitor", "flow-capture"]


@dataclass(frozen=True)
class RunOutcome:
    """Everything the classifier needs, gathered at the command edge.

    Sell-side counts are `int | None`: `None` (JSON null) means signals were
    never derived (pre-001 / stale artifact) — unknown, NOT zero (ADR 0015).

    `decision_report_unreadable` is True when the JSON file exists but cannot
    be parsed (P1-1). The classifier maps this to severity `failed`.
    """

    run_kind: RunKind
    last_exit_code: int
    today_dir_exists: bool
    pipeline_halted: bool
    stale_ingest: bool
    actionable_buy_count: int
    trim_count: int | None
    exit_count: int | None
    review_count: int | None
    decision_report_unreadable: bool = False
    # Funds newly promoted (opportunity_state → core_dca / dca_action →
    # accelerate_dca vs. the prior run) — from decision_report.json summary.
    promotion_count: int = 0
    promotion_ids: tuple[str, ...] = ()
    # Data-health digest (ADR 0016 amendment) — pure derivation of on-disk
    # artifacts, gathered best-effort at the edge. None keeps every pre-001
    # callsite valid.
    health: HealthDigest | None = None
    # One-time abstain→ok recovery notice body (flow-capture only). When set on
    # an otherwise-clean run it forces should_notify (G-Q3→C).
    recovery_notice: str | None = None


@dataclass(frozen=True)
class NotificationDecision:
    """The pure classifier's verdict; the dispatcher renders + sends it."""

    should_notify: bool
    severity: Severity
    title: str
    body: str
