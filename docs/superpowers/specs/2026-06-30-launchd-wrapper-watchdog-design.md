# launchd Wrapper Watchdog + Single-Instance Lock — Design

**Status:** Draft for review — rev 2 (2026-06-30, grill-with-docs resolutions folded in)
**Owner:** Xue Yin
**Related:** ADR 0016 (launchd notify architecture); the monitor-completion-sentinel fix
([PR #179](https://github.com/snowshine0216/investment-research-copilot/pull/179), branch
`fix/monitor-completion-sentinel`) that surfaced this gap during its `/ship` review.

> **Rev-2 changelog (grill-with-docs, 2026-06-30).** Seven decisions sharpened: (Q1) kill the
> **process group**, not the PID — `uv run` spawns a Python child, so a single-PID `kill` risks
> orphaning the worker (continued paid spend + a late `monitor.json` write); (Q2) the lock
> prevents **duplicate paid LLM spend + wasted concurrent work** — the forward ledger is *bloat,
> not contamination* (the reader dedups by `(run_date, fund_id)`); (Q3) keep 1800/3600 + state the
> **threat model** (no-timeout network stalls; LLM + `cached_fetch` are self-bounded); (Q4) a kill
> leaves a **benign orphaned `.tmp`** (atomic `os.replace` → never read), no SIGTERM handler added;
> (Q5) **`$SECONDS` wall-clock accounting** + `IRC_WATCHDOG_POLL` as an internal check-cadence
> knob; (Q6) snapshot is **protective-only** (no completion sentinel exists); (Q7) lock-contention
> is a **silent `exit 0`**. No standalone ADR — rationale lives here + in `lib-run.sh` comments,
> with a one-line pointer added to ADR 0016.

> **Why now.** The single-daily-12:15 schedule rework (#178) removed the long-running
> `run-daily.sh` / `run-weekly-full.sh` wrappers, and with them the **portable background
> watchdog** (`IRC_RUN_TIMEOUT` → `kill -TERM`/`kill -KILL` → `rc=124`) and the
> **single-instance lock** (`outputs/_logs/.run.lock`). The two surviving wrappers
> (`run-monitor.sh`, `run-fundamentals.sh`) have **neither**. Two independent `/ship`
> reviewers (silent-failure + adversarial) flagged that a hung `irc monitor` now runs
> unbounded with no same-day retry, and `ops/launchd/README.md:27` still *claims* a lock
> that does not exist — a live doc/impl mismatch.

---

## 1. Scope

Restore two robustness primitives to the surviving launchd wrappers, extracted once into a
shared, unit-testable bash library:

- **Watchdog (wall-clock kill):** bound each wrapper's run with a configurable timeout;
  on overrun, escalate `TERM`→`KILL` **on the child's process group** and report `rc=124`.
- **Single-instance lock:** prevent a manual run and the scheduled fire (or any two fires)
  from overlapping — chiefly to avoid **duplicate paid LLM spend** and wasted concurrent work
  (see §4.3 for the corrected justification).
- **Docs:** correct the false lock claim and document both timeouts + the notify asymmetry.

### Threat model (what the watchdog is actually for)

The watchdog targets a **non-LLM, non-`cached_fetch` network call with no timeout** — e.g. AkShare
goes through `requests`, whose default timeout is `None` (blocks forever) for NAV / constituent
fetches; a half-open socket there hangs the whole run indefinitely. LLM calls are already
self-bounded (30 s per call + an aggregate `deadline_s` → `AggregateTimeoutError`) and
`cached_fetch` has the stop-after-5 transient breaker, so **neither can hang for 30 min** and
neither is the watchdog's target. This is why the ceilings (§4) are generous, not tight: a healthy
run is minutes, and the watchdog only fires on a genuine stall.

**Non-goals:**

- No `notify-status` run-kind for the snapshot job (snapshot timeouts are logged, not paged —
  see §4.2). The snapshot has **no single completion-sentinel artifact**, so success detection
  isn't a quick add; a separate change.
- **No SIGTERM handler added to `irc`.** A kill therefore leaves a benign orphaned `.tmp`
  (see §8) — acceptable, because the atomic `os.replace` means a stray `.tmp` is never read.
  Adding signal handling to `irc`'s core is out of scope for a bash-wrapper feature.
- No GNU `timeout`/`gtimeout` (not present on stock macOS — see §2).
- **No change** to the just-shipped `monitor.json` completion sentinel / once-per-day
  idempotency logic (#179). The lock is *concurrency* control; the sentinel is *completion*
  detection. They are orthogonal and both retained.
- No change to the trading-day gate, the provenance-`/dev/null` logging, or the plists.
- The root `CLAUDE.md` claims atomic writes use `.tmp.{pid}` — actually `mkstemp` (random suffix).
  A stale doc nit, flagged here as a separate trivial follow-up (not fixed by this feature).

---

## 2. Mechanism — reuse the proven portable pattern

The deleted `run-daily.sh` already shipped a portable, macOS-native watchdog: background the
command, poll the child with `kill -0` on a fixed interval, and on timeout escalate
`kill -TERM` → (grace) → `kill -KILL`, returning `rc=124`. This is the chosen mechanism — with
one correction over the old code.

**Correction: kill the process group, not the PID.** The old code did `kill -TERM "$_PID"`, but
`"$UV_BIN" run irc monitor` does **not** exec into Python — `uv run` spawns the `irc`
(`irc.cli:main`) console script as a **child** and supervises it. So `$!` is the *uv* PID with a
Python worker underneath. A single-PID kill that uv doesn't forward would **orphan the Python
worker** (reparented, still running): it keeps burning paid MiniMax spend and can finish and write
`monitor.json` *after* the watchdog set `rc=124` and `notify-status` paged "timeout" — the exact
silent inconsistency #179 fixed. We instead launch under bash job control (`set -m`, so the
backgrounded job is a process-group leader with `PGID == $!`) and signal the **whole group**:
`kill -TERM -"$pid"` → grace → `kill -KILL -"$pid"` (negative PID = process group). This is
robust whether or not uv forwards signals, and takes down uv + Python + any grandchildren in one
shot. macOS-compatible without `setsid`.

**Rejected alternatives:**

- **GNU `timeout` / `gtimeout`** — stock macOS ships no `timeout`; it requires
  `brew install coreutils`. The original code's "portable background watchdog" comment was a
  deliberate choice to avoid this dependency. Rejected.
- **launchd `ExitTimeOut`** — governs the SIGKILL grace period when a job is *unloaded*, not a
  per-invocation wall-clock ceiling, and does not track a backgrounded child of the wrapper.
  Does not fit. Rejected.

---

## 3. Shared library: `ops/launchd/lib-run.sh`

Rather than inline ~25 lines of lock + watchdog into each of the two wrappers — the duplication
that bred the stale-test drift cleaned up in #179 — extract two small functions sourced by both
wrappers **after** `cd "$REPO_ROOT"` (so the relative `source ops/launchd/lib-run.sh` resolves;
`REPO_ROOT` is the install-time-substituted absolute path). The library has no `__UV_BIN__` /
`__REPO_ROOT__` placeholders — it is pure logic and is checked in verbatim.

### 3.1 `acquire_lock <lock_dir>`

mkdir-atomic acquire with stale-reclaim, identical in spirit to the old `run-daily.sh` block.

- `mkdir "$lock_dir"` succeeds → write `$$` to `"$lock_dir/pid"`, install an `EXIT` trap that
  `rm -rf "$lock_dir"`, return `0`.
- `mkdir` fails (held) → read the holder pid; if `kill -0 "$holder"` (alive) → return non-zero
  ("skip"). If the holder is gone → reclaim (`rm -rf` + retry `mkdir`); on retry failure return
  non-zero.
- Caller convention: `acquire_lock "$LOCK" || { echo "[$TODAY] another run in progress — skipping."; exit 0; }`

Note: the `EXIT` trap is set inside the function but applies to the whole script (bash traps are
global). Only `acquire_lock` installs an EXIT trap, so there is no trap-stacking ambiguity.

### 3.2 `run_with_watchdog <timeout_secs> <cmd> [args...]`

- Enable bash job control (`set -m`) so the next backgrounded job becomes its own process-group
  leader, then run `"$@"` (after shifting off `<timeout_secs>`) in the background; capture
  `pid=$!` (== the group's PGID).
- Reset `SECONDS=0` (bash wall-clock builtin) and poll: while `kill -0 "$pid"`, check
  `[ "$SECONDS" -ge "$timeout" ]`; if so, log a loud timestamped watchdog line to stderr,
  `kill -TERM -"$pid"`, `sleep 5`, `kill -KILL -"$pid"` (negative PID = whole group), mark killed,
  break; otherwise `sleep "${IRC_WATCHDOG_POLL:-10}"` and loop.
  - **`$SECONDS`, not accumulated sleeps** — wall-clock accurate regardless of system load.
  - **`IRC_WATCHDOG_POLL`** (default 10 s) is the `kill -0` *check cadence* only, decoupled from
    the timeout accounting. Production stays at 10 s (fine for 30/60-min ceilings); tests set it
    to `0.2` with a 1 s timeout so the kill→124 path runs in ~1 s. Internal knob — documented only
    in `lib-run.sh` comments, never in the README.
- Killed → `return 124`. Otherwise `wait "$pid"` and `return` the child's real exit status.
- Caller convention under `set -e`: `rc=0; run_with_watchdog "$T" "$UV_BIN" run irc monitor || rc=$?`
  (the `|| rc=$?` keeps a non-zero child rc — including 124 — from aborting the script before
  `notify-status` runs).

These two functions are the entire public interface. Each is independently testable by sourcing
the library and calling it with stub commands (§6).

---

## 4. Per-wrapper wiring

### 4.1 `run-monitor.sh`

Final order (existing gates unchanged; **bold** = new):

1. trading-day gate (weekend + CN holiday skip)
2. `monitor.json` once-per-day idempotency skip (#179)
3. **`acquire_lock "outputs/_logs/.monitor.lock"`** — skip-on-contention (`exit 0`)
4. **`rc=0; run_with_watchdog "${IRC_MONITOR_TIMEOUT:-1800}" "$UV_BIN" run irc monitor || rc=$?`**
5. `"$UV_BIN" run irc notify-status --run-kind monitor --last-exit-code "$rc" || true`
6. `exit "$rc"`

A timeout yields `rc=124`; `notify-status` pages it (`classify.py:15` already maps
`124 → "timeout"`). The lock sits **after** the idempotency skip — no point locking a day we are
skipping — and releases via the `EXIT` trap.

**Lock-contention skip is silent.** If the lock is held (a manual run colliding with the scheduled
fire), step 3 logs "another run in progress — skipping" and `exit 0` — **no notify**, consistent
with the weekend / holiday / idempotency skips (a skip is not a failure). No failure is masked: a
*hung* prior holder is killed by its **own** watchdog (which frees the lock and pages its own
`timeout`), and under the single daily fire there is no second scheduled fire to skip.

**Default `IRC_MONITOR_TIMEOUT` = 1800s (30 min).** A healthy brief is a few minutes; 30 min never
false-kills a slow-but-progressing run (EastMoney backoff, slow LLM) yet catches a genuine hang
well before the next 24h fire.

### 4.2 `run-fundamentals.sh`

Final order (**bold** = new):

1. **`acquire_lock "outputs/_logs/.snapshot.lock"`** — skip-on-contention (`exit 0`)
2. **`rc=0; run_with_watchdog "${IRC_SNAPSHOT_TIMEOUT:-3600}" "$UV_BIN" run irc monitor snapshot || rc=$?`**
3. log the final `rc` (the per-run log already captures stdout+stderr); **no `notify-status` call**
4. `exit "$rc"`

**Default `IRC_SNAPSHOT_TIMEOUT` = 3600s (60 min).** The snapshot is sequential 5–15 min over
constituents; 60 min is a generous ceiling that still kills a stuck constituent fetch so the next
quarter is not blocked and the lock is released.

**Asymmetry (intentional, protective-only).** The snapshot job has **no notification path**, and
adding one is not a quick change: `notify-status` only special-cases the `monitor` run-kind, and —
the binding reason — the snapshot has **no single completion-sentinel artifact** (it refreshes
constituent caches under `data/...`, not one `monitor.json`-style file), so there is nothing for a
new run-kind to test for success. A snapshot timeout is therefore *logged loudly* (the `rc=124`
watchdog line in `outputs/_logs/run-fundamentals.<ts>.log`) but does **not** page. This is
acceptable because a failed/killed snapshot is *already surfaced indirectly*: the next daily
monitor brief degrades the affected factors to N/A (README: "surfaced, not silent") within ~a day.
The watchdog's value here is purely **protective** — kill the stuck constituent socket so the
process does not linger for three months and the `.snapshot.lock` is freed. Wiring a snapshot
notification (which would first require designing a snapshot completion sentinel) is an explicit
non-goal/follow-up for a job that runs 4×/year and whose failure is already visible.

### 4.3 Per-wrapper locks, not one shared lock

The monitor (daily 12:15) and snapshot (quarterly 06:00) jobs run at different cadences over
atomically-written caches, so cross-job mutual exclusion is unnecessary and would be harmful: a
single shared `.run.lock` would make the 12:15 monitor **false-skip an entire day** if a 06:00
snapshot overran. Separate `.monitor.lock` / `.snapshot.lock` give each wrapper self-protection
(manual run vs scheduled fire) without coupling.

**What the monitor lock actually buys (corrected).** The concrete payoff is preventing two
concurrent `irc monitor` runs from each calling the LLM for all ~10 funds — i.e. **duplicate paid
MiniMax spend** (the preflight spend gate is per-run, so it will not catch the doubling) plus
wasted duplicate work and pointless races on the same atomic output files. It is **not** about
eval integrity: `append_ledger` (`forward_log.py:40`) blind-appends, but the reader
(`latest_per_key`, `forward_score`) **dedups by `(run_date, fund_id)` keeping max `written_at`**,
so a double-run produces ledger **bloat that the reader silently collapses**, not contamination.
Collision odds are low under a single daily fire, but the lock is ~10 lines and prevents a real
2× paid-spend event.

---

## 5. Docs

`ops/launchd/README.md`:

- **Fix the false claim** at line 27: replace the single `outputs/_logs/.run.lock` reference with
  the two per-wrapper locks (`.monitor.lock`, `.snapshot.lock`) and what each guards.
- Document `IRC_MONITOR_TIMEOUT` (1800) and `IRC_SNAPSHOT_TIMEOUT` (3600), the `rc=124` →
  "timeout" notification for monitor, and the snapshot-logs-but-does-not-page asymmetry.

`docs/adr/0016-*.md` (launchd notify architecture): add a **one-line pointer** to this spec for
the restored watchdog + per-wrapper lock (process-group kill, per-wrapper locks, snapshot
protective-only) — no standalone ADR, since the decision is reversible (~30 lines of bash) and the
rationale lives here + in `lib-run.sh` comments.

---

## 6. Testing

This feature exists because a real protection had only a content-assertion test, which was
deleted when the wrappers it named disappeared. The new implementation gets **behavioral** tests.

### 6.1 `tests/ops/test_run_lib.py` (new — library unit tests)

Source `ops/launchd/lib-run.sh` in a subprocess and exercise the functions directly:

- `run_with_watchdog`: a fast command (`true`) returns `0`; a command returning `7` propagates
  `7`; with `IRC_WATCHDOG_POLL=0.2`, a `sleep 5` under `run_with_watchdog 1` is killed and returns
  **124** in ~1 s. **Process-group kill test:** the backgrounded command spawns a grandchild
  (e.g. `bash -c 'sleep 30 & wait'`); after the timeout fires, assert the grandchild PID is gone
  (`kill -0` fails) — proving the group kill, not just a single-PID kill, took down the subtree.
- `acquire_lock`: first acquire returns `0` and creates the dir + pid file; a second acquire while
  held returns non-zero (skip); a lock dir holding a **dead** pid is reclaimed (returns `0`).

### 6.2 `tests/ops/test_launchd_monitor.py` (extend — wrapper integration)

Using the existing `_template_wrapper` + stub-`uv` harness:

- A stub `uv` whose `irc monitor` sleeps longer than a tiny injected `IRC_MONITOR_TIMEOUT` →
  the watchdog kills it → the wrapper calls `notify-status … --last-exit-code 124`.
- A second monitor invocation while a `.monitor.lock` is held (pre-create the lock dir with a live
  pid) → the wrapper skips (`uv` never called for `monitor`).
- **Restore a watchdog-presence assertion** pointed at the surviving wrappers (replacing the one
  deleted in #179), now backed by a real implementation: assert both wrappers source `lib-run.sh`
  and pass an `IRC_*_TIMEOUT`-defaulted ceiling into `run_with_watchdog`.

### 6.3 `tests/commands/test_notify_cmd.py` (extend)

`bash -n` already globs `*.sh`, so it will lint the new `lib-run.sh` automatically; add a focused
assertion that `lib-run.sh` defines both `acquire_lock` and `run_with_watchdog`.

All new bash is TDD'd: write the failing behavioral test first (e.g. the `sleep`-is-killed-→-124
test fails against an absent `run_with_watchdog`), then implement the library function.

---

## 7. Files touched

| File | Change |
|---|---|
| `ops/launchd/lib-run.sh` | **new** — `acquire_lock` + `run_with_watchdog` |
| `ops/launchd/run-monitor.sh` | source lib; lock + watchdog around `irc monitor`; `IRC_MONITOR_TIMEOUT` |
| `ops/launchd/run-fundamentals.sh` | source lib; lock + watchdog around `irc monitor snapshot`; `IRC_SNAPSHOT_TIMEOUT` |
| `ops/launchd/README.md` | fix lock claim; document timeouts + notify asymmetry |
| `docs/adr/0016-*.md` | one-line pointer to this spec (no standalone ADR) |
| `tests/ops/test_run_lib.py` | **new** — library unit tests (incl. process-group kill, `IRC_WATCHDOG_POLL`) |
| `tests/ops/test_launchd_monitor.py` | wrapper integration (timeout-kill, lock-skip) + restored watchdog-presence test |
| `tests/commands/test_notify_cmd.py` | assert `lib-run.sh` defines both functions |
| `CHANGELOG.md` / `TODOS.md` | `[Unreleased]` entry; close the watchdog follow-up item |

---

## 8. Risks & edge cases

- **Trap interaction:** only `acquire_lock` installs an `EXIT` trap; `run_with_watchdog` does not,
  so there is no trap clobbering. If the *wrapper itself* is killed (launchd unload) the trap may
  not fire → stale lock dir → reclaimed by the next run's `kill -0` check.
- **`set -m` scope:** job control is enabled to make the backgrounded job a process-group leader so
  the negative-PID kill targets only the child's group (not the wrapper or launchd). It does not
  affect the later foreground `notify-status` call. The kill uses negative PID
  (`kill -TERM -"$pid"`); since `pid == $!` is the group leader under `set -m`, this signals the
  whole subtree (uv + Python + grandchildren).
- **`set -euo pipefail`:** backgrounding + `wait` + the `|| rc=$?` calling convention preserves the
  child rc without `-e` aborting early (proven in the old `run-daily.sh`).
- **Double-kill / fast exit:** if the child exits between the `kill -0` check and the `kill`,
  the `kill` is a harmless no-op (`2>/dev/null || true`).
- **Kill leaves a benign orphaned `.tmp`:** with no SIGTERM handler, a kill mid-`_write_outputs`
  skips `atomic_write_text`'s `except` cleanup, leaving a `<name>.XXXXXX.tmp` (mkstemp) in the
  date-partitioned, gitignored output dir. **Harmless** — the atomic `os.replace` means a stray
  `.tmp` is never read by any consumer and can never be mistaken for a completed `monitor.json`.
  Documented, not handled (see §1 non-goals).
- **Timeout too tight:** mitigated by generous defaults (30 min / 60 min) and env overrides; a
  false-kill surfaces as `rc=124` "timeout" (monitor) rather than silent data loss.
