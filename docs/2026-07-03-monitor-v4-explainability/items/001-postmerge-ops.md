# Item 001 — post-merge ops (manual, after roll-up merge to main)

1. **Reinstall the launchd agents** so the templated `run-weekly.sh` picks up
   the eval-refresh step: `bash ops/launchd/install.sh`. Verify the installed
   wrapper contains `IRC_WEEKLY_EVAL_TIMEOUT` and `launchctl list | grep
   com.irc` shows all agents loaded.
2. **One manual live eval run at rollout** to clear the current stale caveats
   immediately (the next Saturday fire would otherwise be the first refresh):
   `IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact` then
   `IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_narrative` (eval-live spend
   gate applies).
3. Next `uv run irc monitor` brief: suite-caused chips should flip to
   ✓ validated; any remaining 为何有保留 lines are genuinely fund-specific.
