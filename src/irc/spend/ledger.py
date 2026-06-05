from __future__ import annotations
from datetime import date
from typing import Any
from irc.schemas.spend import SpendBalanceEntry
from irc.spend.types import BalanceReading


def _period_start(today: date, reset_day: int) -> date:
    """First day of the current quota period (reset_day this month, or last month
    if we haven't reached reset_day yet)."""
    if today.day >= reset_day:
        return date(today.year, today.month, reset_day)
    month, year = (12, today.year - 1) if today.month == 1 else (today.month - 1, today.year)
    return date(year, month, reset_day)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _wallet_reading(provider: str, entry: SpendBalanceEntry, row: dict[str, Any]) -> BalanceReading:
    consumed = float(row.get("consumed_since", 0.0))
    since = _parse_date(row.get("since"))
    if since is None or (entry.as_of is not None and entry.as_of > since):
        consumed = 0.0   # user re-anchored; ignore pre-anchor consumption
    amount = float(entry.balance) - consumed
    return BalanceReading(provider, currency="", amount=amount, available=amount > 0, source="ledger")


def _quota_reading(
    provider: str, entry: SpendBalanceEntry, row: dict[str, Any], today: date,
) -> BalanceReading:
    period_start = _period_start(today, entry.reset_day)
    stored_start = _parse_date(row.get("period_start"))
    consumed = float(row.get("consumed_this_period", 0.0))
    if stored_start is None or stored_start < period_start:
        consumed = 0.0   # period rolled over → auto-reset
    amount = float(entry.quota) - consumed
    return BalanceReading(provider, currency="", amount=amount, available=amount > 0, source="ledger")


def effective_balance(
    provider: str,
    entry: SpendBalanceEntry,
    consumption: dict[str, Any],
    *,
    today: date,
) -> BalanceReading:
    """Pure: anchor + machine consumption + clock → effective balance reading.
    Wallet = balance − consumed-since-anchor; quota = quota − consumed-this-period
    (auto-reset on period rollover)."""
    row = consumption.get(provider, {})
    if entry.quota is not None:
        return _quota_reading(provider, entry, row, today)
    return _wallet_reading(provider, entry, row)
