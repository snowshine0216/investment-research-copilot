# Phase 2 Handoff — Preflight Spend / Balance Gate

**For a fresh session.** Phase 1 is shipped on `feat/spend-balance-gate`. This file is the
single entry point to continue with Phase 2 (learning + auto-decrement). Read the three
"Read first" docs, then follow "How to start".

---

## Status

- **Phase 1: DONE.** 23 atomic commits on `feat/spend-balance-gate` (started at `f0c7143`).
  A working gate using a **seeded** usage profile and a **read-only** ledger. Verified
  against spec §15.1 (all boxes green; live DeepSeek 99.61 CNY / OpenRouter 1.19 USD).
- **Phase 2: NOT STARTED.** Recorder + EWMA convergence + ledger auto-decrement +
  estimated-vs-actual artifacts + (expanded) README. Scope below.

## Read first (before touching code)

1. `docs/superpowers/specs/2026-06-05-spend-balance-gate-design.md` —
   **§3.2** (convergence data flow), **§5.4** (EWMA, pure `profile.py`),
   **§10** (Phase 2 scope), **§12** (artifacts + auto-convergence + trigger commands),
   **§13** (README deliverable), **§15.2** (Phase 2 exit gate — your Definition of Done),
   **§15.3** (final acceptance, both phases), **§16.1** (calibration; note item 5:
   *Phase 2 convergence is proven with SIMULATED actuals — no real spend required*).
2. `docs/superpowers/plans/2026-06-05-spend-balance-gate-phase1.md` — the Phase 1 plan
   (style + the "Deferred to Phase 2" list at the bottom).
3. `CONTEXT.md` + `CLAUDE.md` — conventions (TDD, pure cores / I/O at edges, <200-line
   files, ruff line-length 100, frozen dataclasses, secrets in `.env`).

## What exists now (Phase 1 — the seams you build on)

`src/irc/spend/` (pure cores + edges) and `src/irc/commands/spend_cmd.py`:

| File | Role | Phase 2 touch? |
|---|---|---|
| `schemas/spend.py` | `SpendPricingConfig`, `SpendBalancesConfig` (pydantic) | maybe (learned-profile schema) |
| `spend/config.py` | `load_pricing` / `load_balances` / `load_consumption` | add a learned-profile loader/writer |
| `spend/types.py` | `TaskUsage`, `UsageProfile`, `CostEstimate`, `BalanceReading`, … | reuse; `samples`/`alpha` already present for EWMA |
| `spend/profile.py` | `seed_profile()` only | **add EWMA overlay** (§5.4): blend learned over seed where `samples>0` |
| `spend/scope.py` | command/stages → tasks + search providers | reuse as-is |
| `spend/estimator.py` | pure per-provider estimate | reuse as-is |
| `spend/ledger.py` | pure `effective_balance` (wallet −consumed; quota auto-reset) — **read path only** | reuse the read path; the writer feeds its inputs |
| `spend/gate.py` | pure block/warn/ok decision | reuse as-is |
| `spend/probes/` | DeepSeek + OpenRouter live probes | reuse as-is |
| `spend/preflight.py` | edge: scope→estimate→balances→decide→print→exit | **add**: write `spend_estimate.json` at start |
| `commands/spend_cmd.py` | `preflight_gate`, `collect_api_keys`, `run_spend_status` | reuse |

**Config (committed, force-added — `config/` is gitignored):**
`config/spend_pricing.yaml`, `config/spend_balances.yaml`, and their `irc init` templates
under `src/irc/templates/config/`.

## Phase 2 scope (each item = one §15.2 exit-gate box)

1. **`spend/recorder.py` (pure) + a hookpoint.** Capture *actual* per-run usage:
   - per llm.yaml task: `calls`, `prompt_tokens`, `completion_tokens`
   - per search provider: `units` (queries or pages)
   - **Find the token-usage seam** in `src/irc/llm/` (the gateway / `http_client` —
     check whether `ChatResponse` carries token usage; if not, surface it) and the
     **search-call seam** in `src/irc/research/search*`. Keep counting pure; do the
     accumulation at the I/O edge.
2. **EWMA convergence in `profile.py` (pure, §5.4).** Load `data/spend/usage_profile.json`,
   overlay learned values where `samples>0`, blend with `alpha` (already on `UsageProfile`).
   `new = alpha*actual + (1-alpha)*old`; `samples += 1`.
3. **Ledger auto-decrement.** Recorder writes `data/spend/consumption.json` (wallet:
   `consumed_since` + `since`; quota: `consumed_this_period` + `period_start`). The existing
   `effective_balance` read path already consumes these — so `irc spend status` will then
   show the wallet reduced / quota counter advanced. (Atomic write: `.tmp.{pid} → os.replace`.)
4. **Artifacts (§12.1).** `outputs/<date>/spend_estimate.json` (at gate time) +
   `spend_actuals.json` (at run end); `data/spend/usage_profile.json` updated.
   `data/spend/` is gitignored already.
5. **Auto-convergence wiring (§12.2).** Hook the recorder so *every* gated run records
   actuals and updates the profile/ledger hands-off (likely a post-run step in
   `run_cmd` / the command runners, symmetric to the preflight call).
6. **README (§13).** Expand the existing "Spend / balance gate" section to document
   estimated-vs-actual artifact locations + auto-convergence behaviour, and add the
   **docs grep acceptance test** (mirrors the pattern used elsewhere).

## Phase 2 exit gate (§15.2) — your Definition of Done

- [ ] `uv run pytest tests/spend -k "recorder or convergence or ledger" -q` → all pass.
- [ ] **Convergence proven numerically:** a test (simulated actuals OK) shows a task's
      `samples` go `0 → ≥1` and its estimate move *toward the observed actual*; capture
      before/after for ≥1 provider.
- [ ] **Artifacts written:** a gated run writes `spend_estimate.json` + `spend_actuals.json`;
      `usage_profile.json` + `consumption.json` updated.
- [ ] **Auto-decrement proven:** after a run using a ledger provider, `irc spend status`
      shows reduced wallet / advanced quota counter.
- [ ] **README shipped** + docs grep test passes.
- [ ] **No regression + lint clean** (same commands as Phase 1).

> **Calibration decision (spec §16.1 item 5):** convergence is proven with **simulated /
> injected actuals — no real spend required**. The user triggers the first real `irc run`
> later. So Phase 2 can be fully TDD'd deterministically.

## Gotchas to preserve (learned the hard way in Phase 1)

- **Currency is never crossed.** Each provider's estimate stays in its own currency; the
  gate compares like-for-like. Don't sum across currencies.
- **DeepSeek `/user/balance` returns CNY *and* USD in unstable order** — `probes/deepseek.py`
  selects the **CNY** entry (pricing currency). Don't regress to `balance_infos[0]`.
- **Tests bypass the gate** via a global autouse `IRC_SKIP_SPEND_GATE` fixture in
  `tests/conftest.py` (keys are live in dev → would hit the network). `run_preflight` itself
  ignores the flag (only `preflight_gate` checks it), so unit-test `run_preflight`/recorder
  directly with injected probes/actuals + a fixed `today`.
- **`config/` is gitignored** → committed config + template files are `git add -f`'d.
- **Gate fires per gated command**, so during `irc run` it also fires inside
  memo/opportunity/decision (the static guard `test_gate_wiring.py` asserts all 6 runners
  call it — keep it green).
- **`irc init` must scaffold any new committed config** (Task 1's validate requires them;
  `test_init_creates_inputs_and_config` guards this).

## Still-open calibration flags (from §16.1 — confirm when convenient, not blocking)

- **Jina** per-page token unit (`10000` placeholder in `spend_pricing.yaml`).
- **Brave** monthly quota (`2000` placeholder in `spend_balances.yaml`).
- **Bocha** unit — assumed CNY wallet (¥0.036/call); confirm it's ¥ not a call-count package.
- DeepSeek (99.61 CNY) + OpenRouter (1.19 USD) are now **live-confirmed**.

## How to start (recommended order)

1. **(Optional but recommended) Sanity-check the seeds:** do 1–2 real `irc run`s and compare
   the printed estimates against actual provider usage, to confirm the seeds aren't wildly
   off before wiring convergence. (Phase 2 itself can be built without this — simulated
   actuals — but a real check de-risks the seed magnitudes.)
2. **Write the Phase 2 plan** with `superpowers:writing-plans` (Opus), mirroring the Phase 1
   plan's task-by-task TDD structure, into
   `docs/superpowers/plans/2026-06-05-spend-balance-gate-phase2.md`. Map one task per scope
   item above; each task ends in a commit.
3. **Execute** it task-by-task (TDD, commit per task) — e.g. re-invoke `/autodev` with the
   Phase 2 plan, same as Phase 1.
4. **Verify §15.2**, then **§15.3** final acceptance (two consecutive runs: run 2's estimate
   reflects run 1's recorded actuals — show the delta), and report.

## Resume pointers

- Branch: `feat/spend-balance-gate` (Phase 1 merged to `main` via PR; cut Phase 2 work from
  the latest `main` or continue on a `feat/spend-balance-gate-phase2` branch).
- Memory: `project_spend_balance_gate.md` (kept current — Phase 1 shipped + the 3 fixes).
- Phase 1 report: see the session that produced commits `fe8a508…` (this branch's log).
