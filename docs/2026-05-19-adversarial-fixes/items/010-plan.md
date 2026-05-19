# 010 — Plan

## Steps

1. `src/irc/memo/diagnostics.py`:
   - `compose_role_bucket_banner(diagnostics_rows)`: returns
     `(header, caveat)` when any rows have stage=role_bucket,
     status=failed. Header names the failed roles and shows N/total.
2. `src/irc/commands/memo_cmd.py`:
   - Add `_load_discovery_diagnostics(out_dir)` helper that reads
     discovery_diagnostics.csv via stdlib csv.DictReader.
   - Prepend role-bucket lines to risk_notes (highest priority, so they
     appear first in the memo's risk section).
3. Tests:
   - empty diagnostics → ()
   - 2 failed of 3 roles → banner with "2/3" and both role names
   - dedupe duplicate failed rows
   - empty/None input → ()
   - ignores non-role_bucket rows
