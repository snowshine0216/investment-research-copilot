from datetime import date
from irc.schemas.spend import SpendBalanceEntry
from irc.spend.ledger import apply_usage, effective_balance


def _wallet(balance, as_of):
    return SpendBalanceEntry(balance=balance, as_of=as_of)


def _quota(quota, reset_day=1):
    return SpendBalanceEntry(quota=quota, reset="monthly", reset_day=reset_day)


def test_wallet_subtracts_consumption_since_anchor():
    entry = _wallet(100.0, date(2026, 6, 1))
    consumption = {"tavily": {"consumed_since": 30.0, "since": "2026-06-01"}}
    r = effective_balance("tavily", entry, consumption, today=date(2026, 6, 5))
    assert r.amount == 70.0
    assert r.source == "ledger"
    assert r.available is True


def test_wallet_resets_consumption_when_anchor_moved_forward():
    entry = _wallet(100.0, date(2026, 6, 10))   # user topped up on the 10th
    consumption = {"tavily": {"consumed_since": 30.0, "since": "2026-06-01"}}
    r = effective_balance("tavily", entry, consumption, today=date(2026, 6, 11))
    assert r.amount == 100.0   # consumption before the new anchor is ignored


def test_wallet_missing_consumption_returns_full_balance():
    r = effective_balance("jina", _wallet(500.0, date(2026, 6, 1)), {}, today=date(2026, 6, 5))
    assert r.amount == 500.0


def test_negative_balance_marks_unavailable():
    entry = _wallet(10.0, date(2026, 6, 1))
    consumption = {"bocha": {"consumed_since": 25.0, "since": "2026-06-01"}}
    r = effective_balance("bocha", entry, consumption, today=date(2026, 6, 5))
    assert r.amount == -15.0
    assert r.available is False


def test_quota_within_period_subtracts_period_consumption():
    consumption = {"brave": {"consumed_this_period": 380.0, "period_start": "2026-06-01"}}
    r = effective_balance("brave", _quota(2000.0), consumption, today=date(2026, 6, 20))
    assert r.amount == 1620.0


def test_quota_auto_resets_when_month_rolls_over():
    consumption = {"brave": {"consumed_this_period": 380.0, "period_start": "2026-06-01"}}
    # today is in July → period_start is stale → consumed resets to 0
    r = effective_balance("brave", _quota(2000.0), consumption, today=date(2026, 7, 2))
    assert r.amount == 2000.0


def test_wallet_accumulates_consumed_since_and_sets_since_when_absent():
    out = apply_usage({}, "tavily", units=4, kind="wallet", today=date(2026, 6, 6))
    assert out["tavily"]["consumed_since"] == 4.0
    assert out["tavily"]["since"] == "2026-06-06"
    out2 = apply_usage(out, "tavily", units=3, kind="wallet", today=date(2026, 6, 7))
    assert out2["tavily"]["consumed_since"] == 7.0          # accumulates
    assert out2["tavily"]["since"] == "2026-06-06"          # anchor date preserved


def test_quota_accumulates_consumed_this_period_and_stamps_period_start():
    out = apply_usage({}, "brave", units=10, kind="quota", today=date(2026, 6, 6))
    assert out["brave"]["consumed_this_period"] == 10.0
    assert out["brave"]["period_start"] == "2026-06-06"


def test_apply_usage_does_not_mutate_input():
    src = {"tavily": {"consumed_since": 1.0, "since": "2026-06-01"}}
    apply_usage(src, "tavily", units=2, kind="wallet", today=date(2026, 6, 6))
    assert src["tavily"]["consumed_since"] == 1.0           # original untouched
