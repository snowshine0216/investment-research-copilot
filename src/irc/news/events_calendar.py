from __future__ import annotations
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class KnownEvent:
    name: str
    date: date
    topic: str
    notes: str


_KNOWN_2026: tuple[KnownEvent, ...] = (
    KnownEvent("FOMC June meeting", date(2026, 6, 17), "us_monetary", "Rate decision + dot plot"),
    KnownEvent("FOMC July meeting", date(2026, 7, 29), "us_monetary", "Rate decision"),
    KnownEvent("FOMC September meeting", date(2026, 9, 16), "us_monetary", "Rate decision + SEP"),
    KnownEvent("PBoC LPR May", date(2026, 5, 20), "cn_monetary", "Loan prime rate"),
    KnownEvent("PBoC LPR June", date(2026, 6, 20), "cn_monetary", "Loan prime rate"),
    KnownEvent("WGC Q2 report", date(2026, 7, 31), "gold_specific", "Quarterly demand"),
    KnownEvent("CPI release (US)", date(2026, 5, 14), "us_monetary", "Monthly CPI"),
)


def upcoming_events(
    today: date, lookahead_days: int = 30, topics: tuple[str, ...] | None = None,
) -> list[KnownEvent]:
    horizon = (today, date.fromordinal(today.toordinal() + lookahead_days))
    out = [e for e in _KNOWN_2026 if horizon[0] <= e.date <= horizon[1]]
    if topics:
        out = [e for e in out if e.topic in topics]
    return sorted(out, key=lambda x: x.date)
