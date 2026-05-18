# Item 008 — Derive `venue_status` when no trade exists; drop `unknown` default for in-universe instruments

## What

`src/irc/decision/gates.py:37-44`:

```python
def venue_status_for_trade(trade: dict[str, Any] | None) -> VenueStatus:
    if trade is None:
        return "unknown"
    ...
```

When the allocation didn't produce a trade row for an instrument, venue is reported as `unknown` — even when we already know the instrument's `venue_required` and the user's `available_venues`. Result: 85 of 103 rows in `outputs/2026-05-18/decision_report.md` show `venue=unknown` unnecessarily.

## Files to touch

- `src/irc/decision/gates.py` — change the signature of `venue_status_for_trade` to accept either a trade dict OR an instrument lookup (`instrument: Instrument | None`, `available_venues: set[str] | None`). When trade is None but instrument + available_venues are provided, derive status via the same logic as `trades/venue_check.py:check_venue`.
- `src/irc/decision/report.py` (or wherever `decide_row` is called) — pass instrument + available_venues alongside the trade.
- `src/irc/commands/decision_cmd.py` (or equivalent) — thread `available_venues` and the universe into `decide_row`.
- `tests/decision/test_gates.py` — add tests for the new derivation paths.

## Acceptance criteria

- `venue_status_for_trade` becomes `venue_status(trade, instrument, available_venues)`. When `trade is not None`, return today's logic exactly. When `trade is None` AND `instrument is not None` AND `available_venues`: derive by intersecting `instrument.venue_required` with `available_venues`. If overlap → `direct`. No overlap and a proxy exists in the universe → `proxy_available`. No overlap and no proxy → `blocked_no_proxy`. Otherwise → `unknown`.
- `available_venues` empty or `None` keeps today's behavior (`unknown`) — this preserves the case where the user has not configured their account yet.
- Existing callers that pass only `trade` keep working via a default `instrument=None, available_venues=None`.
- New test: instrument in universe + matching available_venues + trade=None → `direct`.
- New test: instrument in universe + no matching venue + cn_etf with a same-index `cn_equity_fund` proxy → `proxy_available`.
- New test: empty available_venues → still `unknown`.
- The full suite is green.

## Coordination

- Item 007 introduced `watch_reason`. The `venue_unknown` sub-case will become rare after this lands; that's expected.
- Avoid duplicating proxy logic — reuse `check_venue` from `trades/venue_check.py`. Move shared helpers into `trades/venue_check.py` if needed and import from `decision/gates.py`.

## Out of scope

- Renaming the `VenueStatus` literals.
- Changing the proxy-finding rules. Item 010 covers the one rule change we want.
