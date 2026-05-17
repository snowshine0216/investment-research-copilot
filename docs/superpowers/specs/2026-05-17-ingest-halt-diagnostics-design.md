# P0: Fail-Loud Ingest with Actionable Halt File

**Status:** approved (design)
**Date:** 2026-05-17
**Scope:** P0 — the first three items of the 2026-05-17 enhance/fix plan, restricted to ingest-stage behavior and the halt artifact.

## Problem

When `irc ingest` cannot fetch fresh data (akshare unreachable, network outage, schema drift), the pipeline halts with the generic message `stage exit code 1` in `outputs/<date>/PIPELINE_HALTED.md`. Two failure modes recently observed (2026-05-16, 2026-05-17) produced identical halt files, leaving the operator no way to distinguish "network down" from "every fetch returned empty" without re-running interactively.

The current behavior also wastes 5–10 minutes per failed run on the akshare retry loop (`src/irc/data/akshare_client.py:54-73` — 3 attempts with exponential backoff per fetch, across ~200 instruments) before exiting with the same uninformative message.

## Goal

Halt the pipeline immediately when ingest cannot produce fresh data, and write a halt file that says *what* failed and *why* in one read.

## Non-goals

- Stale-data fallback mode (rejected; would let downstream stages produce misleading artifacts).
- HTTP proxy configuration for akshare (rejected; assumes infrastructure the user does not have).
- Lowering the existing "halt only if 0/N successes" threshold.
- Changes to any stage other than ingest.
- Changes to downstream artifact formats (decision report, memo, opportunity report).

## Design

### Components

**1. Preflight canary.** New private function `_ingest_preflight()` in `src/irc/commands/ingest_cmd.py`, called as the first action in `run_ingest`. Performs one cheap akshare call (a single-row index quote known to be stable). Three outcomes:

- success → continue with full ingest.
- transient/network error (classified by the existing helper at `src/irc/data/akshare_client.py:76-101`) → write `.halt_reason.json` with `kind="akshare_unreachable"`, exit code 1. No retry loop runs.
- any other exception → write `.halt_reason.json` with `kind="akshare_error"` (parse/auth/schema), exit code 1.

**2. Structured halt payload.** New frozen dataclass in `src/irc/pipeline_halt.py`:

```python
@dataclass(frozen=True)
class HaltReason:
    kind: str                          # akshare_unreachable | akshare_empty | akshare_error | preflight_unexpected | stage_exit
    stage: str
    detail: str                        # one-line human summary
    stats: Mapping[str, int] = ()      # e.g. {"price_attempts": 198, "price_successes": 0}
    first_error: str | None = None     # truncated (max 500 char) exception/stderr line
```

`write_halted()` is extended (not replaced) to accept either:
- `(stage: str, reason: str)` — unchanged, for back-compat with stages that have not migrated.
- `(halt_reason: HaltReason)` — new path, renders a richer markdown file.

The structured path renders a "Diagnostics" section with: kind, a small stats table, the `first_error` code block (if present), and a `kind`-specific remediation hint (looked up from a small dict).

**3. Subprocess → orchestrator hand-off.** Ingest is run by `run_pipeline` in `src/irc/commands/run_cmd.py` as a subprocess; it cannot pass a dataclass back directly. On a structured failure, ingest writes `outputs/<date>/.halt_reason.json` immediately before exiting with code 1. The orchestrator, after detecting `rc != 0`, checks for that file:
- if present → load it into a `HaltReason`, pass to `write_halted()`, then delete the JSON.
- if absent → fall back to the old `write_halted(stage, "stage exit code N")` path. This preserves behavior for every other stage and for ingest failures that crash before they can write the file.

On entry, `run_ingest` deletes any pre-existing `.halt_reason.json` for that date as a stale guard.

**4. Post-ingest halt.** The existing 0-success guard at `src/irc/commands/ingest_cmd.py:524-536` is extended to write `.halt_reason.json` with `kind="akshare_empty"`, the per-source attempt/success counts in `stats`, and the most recent fetch exception line in `first_error`, before its existing `exit(1)`.

### Data flow

```
run_pipeline
  └─ subprocess: irc ingest
       ├─ delete stale .halt_reason.json if present
       ├─ _ingest_preflight()
       │     ├─ success         → continue
       │     ├─ transient error → write .halt_reason.json(kind=akshare_unreachable); exit 1
       │     └─ other exception → write .halt_reason.json(kind=akshare_error);      exit 1
       ├─ full akshare price/nav fetch loop (existing)
       ├─ if (price_attempts > 0 AND price_successes == 0)
       │   OR (nav_attempts > 0 AND nav_successes == 0):
       │     → write .halt_reason.json(kind=akshare_empty, stats={...}); exit 1
       └─ exit 0
  ←
  if rc != 0:
       if .halt_reason.json exists → HaltReason.from_file(); write_halted(reason); unlink
       else                        → write_halted("ingest", f"stage exit code {rc}")
```

### Error handling

- Preflight is wrapped in a broad `try/except`. An unexpected exception type still produces a halt file with `kind="preflight_unexpected"` and the exception class name in `detail`; the CLI never exits without a halt file when preflight runs.
- `HaltReason.from_file()` validates required keys; on corrupt JSON, the orchestrator falls back to the legacy generic message rather than raising.
- `first_error` is truncated to 500 characters and stripped of newlines before being written.

### Back-compat

- `write_halted(stage: str, reason: str)` keeps its current signature. The new path is opt-in via `write_halted(halt_reason: HaltReason)`.
- The rendered markdown gains a "Diagnostics" section but keeps the existing "Stopped at stage", "Reason", "Remediation", and "Generated at" lines so anything parsing those continues to work.
- The `.halt_reason.json` file name starts with a dot (hidden) and is deleted after read; it is not part of the public artifact surface.

## Testing

Unit-only; no network access required.

1. `test_preflight_transient_writes_halt_reason` — monkeypatch the canary call to raise a connection error of the kind the existing classifier flags as transient; assert `.halt_reason.json` is written with `kind="akshare_unreachable"` and the process exit code is 1.
2. `test_preflight_unexpected_writes_halt_reason` — monkeypatch the canary to raise an unrelated exception; assert `kind="preflight_unexpected"` and a halt file still exists.
3. `test_post_ingest_zero_success_writes_halt_reason` — monkeypatch the fetch loop so every attempt fails; assert `kind="akshare_empty"` with the correct attempt/success counts in `stats`.
4. `test_write_halted_renders_structured_reason` — construct a `HaltReason`, call `write_halted(reason)`, read the markdown back, assert it contains the kind, the stats table, the `first_error` block, and the matching remediation line.
5. `test_orchestrator_consumes_halt_reason_file` — write a `.halt_reason.json` to a temp outputs dir, run the orchestrator's post-stage handler with `rc=1`, assert the rendered markdown is the structured form and the JSON file is deleted afterward.
6. `test_orchestrator_falls_back_when_no_halt_reason_file` — same setup without the JSON; assert the legacy `"stage exit code 1"` markdown is rendered.

## Files touched

- `src/irc/pipeline_halt.py` — add `HaltReason`, extend `write_halted` with the structured path.
- `src/irc/commands/ingest_cmd.py` — add `_ingest_preflight`, add `.halt_reason.json` writes at the preflight and post-ingest failure points, add the stale-file delete on entry.
- `src/irc/commands/run_cmd.py` — after `rc != 0`, check for `.halt_reason.json`, route to the appropriate `write_halted` call.
- `tests/test_pipeline_halt.py` — new tests for the structured rendering and orchestrator hand-off.
- `tests/commands/test_ingest_cmd.py` — new tests for the preflight and 0-success halt paths.

## Open questions

None at design time. Default values for `kind` strings and the remediation hint dict are chosen during implementation.
