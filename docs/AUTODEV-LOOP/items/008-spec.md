# Item 008 — Backfill venue/proxy registry

## Problem

`outputs/2026-05-17/decision_report.md` shows ~80% of rows at `venue=unknown` and another ~10% at `venue=blocked_no_proxy`. Per `src/irc/decision/gates.py:27-34` and `src/irc/trades/venue_check.py`, these statuses mean:
- `unknown` — no `trade` object for the instrument; the trade plan couldn't decide.
- `blocked_no_proxy` — trade exists but `venue_compatible=False` AND `proxy_id=None`.

For a small known list of instruments, this is a registry-coverage problem, not a per-run logic problem. Today's report has the same instrument codes (`017641`, `096001`, `050025`, etc.) appearing across multiple dates — these are stable mappings.

## Approach

1. From `outputs/2026-05-17/decision_report.md`, extract the unique instrument IDs at `unknown` or `blocked_no_proxy`.
2. For each, determine the correct mapping by reading instrument metadata (asset_class, market, ticker) from `config/` or DuckDB. Classify as:
   - **direct** — venue can trade it directly (most A-share ETFs from a CN brokerage).
   - **proxy** — needs a proxy instrument; add `proxy_id` mapping.
   - **genuinely unreachable** — document with a code comment, leave as-is.
3. Add the mappings to whatever config/registry file `venue_check.py` reads from.
4. Re-run `irc plan` (or the equivalent) against the existing DuckDB data and verify the new `decision_report.md` shows the expected venue status.

## Acceptance criteria

- The set of `unknown`/`blocked_no_proxy` rows in the regenerated `decision_report.md` is strictly smaller than today's.
- Every remaining unreachable instrument has a code comment explaining why (e.g. "QDII quota suspended", "delisted").
- A test pins the expected mapping for at least 5 representative instruments (one per asset_class).

## Files (expected)

- `config/` — venue/proxy mapping file (find the actual location; may be inline in `src/irc/trades/venue_check.py`).
- `src/irc/trades/venue_check.py` — read from the new mappings.
- `tests/trades/test_venue_check.py` (or similar) — pin the mappings.

## Non-goals

- Changing the venue_check decision logic.
- Adding new venue types.
- Wiring proxy instruments into the actual trade execution flow (already exists per `trades/pipeline.py:40-44`).
