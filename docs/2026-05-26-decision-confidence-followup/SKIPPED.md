# SKIPPED — Decision Confidence Followup

Items from the input that autodev did NOT take through the per-item loop.

## Source item #1 — Refresh trade plan to clear stale venue flags

**Reason:** Operational refresh — no code change. Handoff itself flags this as "5 minutes, do first" and says "No code change". The remediation is `uv run irc run --from plan && uv run irc decision`, which only mutates the gitignored `outputs/` partition.

**Recommended unblock path:** User runs the two commands locally whenever convenient; verifies the blocked count drops from 8.3% → ~6.8%. Not autodev's surface — autodev is for PR-shaped code changes, not for re-running a stage of the pipeline on already-merged code.

**Note:** Item 001 (Foreign-fund Policy B relaxation) is the structural fix for the 006809 row that remains on the blocked list even after refreshing. Item 002 (QDII premium fetcher) is the structural fix for the 8 QDII rows. After both ship, this refresh becomes the canonical way to *observe* the reduction in blocked count.
