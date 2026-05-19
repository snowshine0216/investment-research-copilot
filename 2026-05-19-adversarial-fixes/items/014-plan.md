# 014 — Plan

## Steps

1. `src/irc/memo/diagnostics.py`:
   - `compose_fx_qdii_lines(allocation, usd_tolerance)` returns a 3-line
     diagnostic when QDII weight (us_etf + hk_etf) ≥ 0.20. Lines:
     header with weight + tolerance check, premium/discount
     placeholder (data layer to fill later), hedge-cost placeholder.
2. `src/irc/commands/memo_cmd.py`:
   - Read `bundle.preferences.currency_tolerance.usd` as the tolerance.
   - Prepend FX/QDII lines to risk_notes when above floor.
3. Tests at `tests/memo/test_diagnostics_fx_qdii.py`:
   - below floor → empty
   - above floor → 3 lines
   - within tolerance → "落在" copy
   - above tolerance → "超出" copy
   - tolerance None → still emits header
   - hk_etf counts; cn classes don't
