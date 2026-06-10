from __future__ import annotations

from datetime import date

from irc.notify.calendar import should_skip_daily


def test_weekday_not_in_holidays_does_not_skip():
    # 2026-06-10 is a Wednesday.
    assert should_skip_daily(date(2026, 6, 10), set()) is False


def test_saturday_skips():
    # 2026-06-13 is a Saturday.
    assert should_skip_daily(date(2026, 6, 13), set()) is True


def test_sunday_skips():
    # 2026-06-14 is a Sunday.
    assert should_skip_daily(date(2026, 6, 14), set()) is True


def test_weekday_in_holidays_skips():
    holiday = date(2026, 10, 1)  # Thursday — CN National Day
    assert should_skip_daily(holiday, {holiday}) is True


def test_empty_holidays_only_skips_weekends():
    assert should_skip_daily(date(2026, 10, 1), set()) is False
