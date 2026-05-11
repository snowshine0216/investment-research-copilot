from __future__ import annotations
from datetime import date
from irc.news.events_calendar import upcoming_events, KnownEvent


def test_upcoming_events_within_window():
    today = date(2026, 5, 7)
    events = upcoming_events(today=today, lookahead_days=30)
    assert isinstance(events, list)
    if events:
        assert all(isinstance(e, KnownEvent) for e in events)
        assert all(e.date >= today for e in events)


def test_upcoming_events_filtered_by_topic():
    today = date(2026, 5, 7)
    fed_events = upcoming_events(today=today, lookahead_days=120, topics=("us_monetary",))
    for e in fed_events:
        assert e.topic == "us_monetary"
