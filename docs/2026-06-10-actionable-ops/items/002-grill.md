Verdict: PASS

Subagent: opus
Questions resolved: 7

Item 002 (`irc notify-status` + launchd scheduling) was grilled against the live
codebase and the documented domain model (ADR 0015 null-counts contract, the spend-gate
seam, `_china_today`/`STAGE_NAMES`, `decision_cmd` artifact requirements). One
load-bearing correction (Q1) and six confirmations/sharpenings were applied in place.
The spec is now consistent with how `irc run` / `irc decision` / the spend gate actually
behave; no further blocking ambiguity remains before the plan phase.

## Docs touched

- `CONTEXT.md` — new `## Scheduling & notification (irc notify-status, launchd)` section
  (8 terms: `RunOutcome`, `NotificationDecision`, `Severity` precedence, Missing-today-dir
  outcome, `notify-status` spend-gate exemption, Daily-light run chain, Trading-day skip
  predicate, launchd local-time assumption).
- `docs/adr/0016-local-scheduling-and-notification.md` — NEW ADR (six locked decisions:
  launchd-not-cron, daily=full-`irc run`, exit-code-via-wrapper + pure classifier,
  null⇒action, missing-today-dir⇒failed + UTC8-no-fallback, weekend+static-YAML gating).
- `docs/2026-06-10-actionable-ops/items/002-spec.md` — refined in place: `## Resolved
  decisions` (Q1–Q7), strike-throughs in Goal / Approach / Components / Data flow /
  Classification (new branch 0) / RunOutcome field / AC9 / AC11 / OQ1 / OQ6 / closing note,
  `Codifies: ADR 0016` header line.
- `docs/2026-06-10-actionable-ops/items/002-grill.md` — this file.

## Resolved decisions

### Q1 — Daily chain `ingest → opportunity → decision` vs. the full `irc run`?
- **A:** BOTH cadences run the full `irc run`. The daily/weekly distinction is schedule +
  trading-day skip, NOT a different command chain.
- **Rationale:** `decision_cmd.run_decision` hard-requires `_REQUIRED_ARTIFACTS =
  {scoring.json, proposed_allocation.yaml, trade_plan.yaml, memo_traceability.json}`,
  produced by the `score`/`allocate`/`plan`/`memo` stages the short chain SKIPS. On a
  fresh weekday `outputs/<today>/` those are absent ⇒ `irc decision` exits 2 (config) every
  day ⇒ the daily notification is a permanent false "config error". `STAGE_NAMES`
  (`run_cmd.py:17`) already ends `…→ opportunity → memo → decision`, so the full `irc run`
  produces everything the notifier reads.
- **Doc impact:** ADR 0016 §2; CONTEXT "Daily-light run chain"; spec Goal/Approach/
  Components/wrapper-name/OQ1/OQ6 strike-throughs.

### Q2 — Does `irc notify-status` trip the paid-API spend gate (exit 5)?
- **A:** No. It never calls `preflight_gate`, so it cannot exit 5.
- **Rationale:** The spend gate is opt-in per command — `preflight_gate(repo_root,
  "<cmd>")` is invoked explicitly only inside `ask`/`decision`/`eval-funds`/`narrative`/
  `run` (`spend_cmd.py`); free commands (`freshness`/`allocate`/`plan`/`gold`) opt out by
  simply not calling it. `notify-status` makes zero paid calls and follows the same pattern.
- **Doc impact:** ADR 0016 Consequences; CONTEXT "`notify-status` spend-gate exemption".

### Q3 — How does the notifier resolve TODAY's dir, and what if it's absent?
- **A:** Resolve via UTC+8 `_china_today()` (same rule the pipeline writes with); a missing
  `outputs/<today>/` classifies as `failed`, never `clean`. Do NOT reuse
  `decision_cmd._resolve_output_dir`'s latest-dir fallback.
- **Rationale:** `_resolve_output_dir` returns `candidates[-1]` (most recent prior dir) when
  today's is missing — a reader convenience for `irc decision`, but in the notifier it would
  report a stale prior run as today's outcome (false "clean"). The quiet-clean default (OQ4)
  only works if a *missing* notification means the schedule broke ⇒ missing today-dir must
  surface as `failed`. Added classifier branch 0 + a `today_dir_exists: bool` `RunOutcome`
  field.
- **Doc impact:** ADR 0016 §5; CONTEXT "Missing-today-dir outcome"; spec Classification
  branch 0, RunOutcome field, Data flow, AC11.

### Q4 — Wrapper idempotency/spam: how many notifications fire on failure?
- **A:** Exactly one. The wrapper is fail-fast (`set -euo pipefail`), runs ONE command
  (`irc run`), captures `$?` once, calls `notify-status` once.
- **Rationale:** Collapsing the daily chain to a single `irc run` (Q1) removes the
  `ingest && opportunity && decision` sequence that could have emitted three notifications;
  the orchestrator already halts the whole run on the first failing stage and writes resume
  state (CLAUDE.md "`run_pipeline` writes resume state for SystemExit/exception halts").
- **Doc impact:** ADR 0016 Consequences; spec Approach (fail-fast note).

### Q5 — Does adding `IRC_FEISHU_WEBHOOK_URL` break `irc init` / `config validate` without secrets?
- **A:** No. Read directly from `os.environ` at the command edge (NOT a new required
  `Settings` field), exactly like `IRC_NOTIFY_ON_CLEAN` / `IRC_SKIP_SPEND_GATE`.
- **Rationale:** `Settings` (`settings.py`) sets `extra="ignore"` so an unrelated env var
  never errors; keeping the optional webhook out of the pydantic schema entirely means a
  `deepseek_api_key`-less `irc init`/`config validate` is wholly unaffected. URL referenced
  by env-var name only, never a CLI arg, never logged in full (AC7).
- **Doc impact:** ADR 0016 Consequences (spec Constraints already correct — no change).

### Q6 — launchd runs in machine-local time; how is "17:30 China time" expressed?
- **A:** The plist `StartCalendarInterval` targets the operator's machine-local wall-clock
  (documented assumption: ~17:30 China time holds on a UTC+8 machine; a non-UTC+8 operator
  adjusts `Hour`/`Minute` per the ops README). The pipeline's internal date resolution stays
  UTC+8 (`_china_today`).
- **Rationale:** `StartCalendarInterval` has no timezone field and fires in the local zone;
  converting at install time would require the installer to know the target zone. Documenting
  the assumption + the one-line manual adjustment is dependency-free and honest.
- **Doc impact:** ADR 0016 §1/Consequences; CONTEXT "launchd local-time assumption"; spec
  Goal, Components/plist comments, AC9.

### Q7 — Failure modes: `osascript` perms fail / Feishu POST fails — crash the wrapper?
- **A:** No. `notify-status` logs the transport failure and exits non-zero WITHOUT raising;
  one channel failing does not block the other (AC8). The wrapper does not gate on
  `notify-status`'s own exit code — the pipeline result already reached the operator via the
  artifacts/log.
- **Rationale:** Mirrors the project's degrade-never-crash recorder pattern (the spend
  recorder logs `"spend recorder failed", exc_info=True` and continues). A broken notifier
  must never mask the underlying run result.
- **Doc impact:** None (AC8 + the §Approach "never raises" clause already cover it; recorded
  for completeness).
