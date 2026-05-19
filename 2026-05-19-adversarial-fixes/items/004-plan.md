# 004 — Plan

## Steps

1. Add new module `src/irc/research/source_tier.py`:
   - `class SourceTier(IntEnum)` — PRIMARY=1 … UNKNOWN=5
   - `_PRIMARY_HOSTS`, `_WIRE_HOSTS`, `_PAPER_HOSTS`,
     `_REPUBLISHER_HOSTS` (frozensets)
   - `classify(url) -> SourceTier`, `is_trusted(tier) -> bool`
   - Matching: exact host or strict subdomain.
2. Add `tests/research/test_source_tier.py`.
3. (Downstream wiring: items 002 + 010 + 014 will consume `classify()`
   when they fire — keeping this item to a self-contained new module.)
