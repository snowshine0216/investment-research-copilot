# ADR 0013 — Spend recorder: actual usage rides home as return data, never via a global or a threaded sink

**Status:** Accepted (2026-06-06, spend-balance-gate Phase 2)
**Spec:** `docs/superpowers/specs/2026-06-05-spend-balance-gate-design.md` (§3.2 convergence flow, §10 Phase 2)
**Plan:** `docs/superpowers/plans/2026-06-05-spend-balance-gate-phase2.md`
**Glossary:** CONTEXT.md "Spend / balance gate" (`CostEntry`, `RunActuals`, Recorder, effective profile).

## Context

Phase 2 must capture each run's **actual** paid-API usage — per-`llm.yaml`-task token counts and per-provider search units — and, at run end, EWMA-fold it into the learned profile (`data/spend/usage_profile.json`) and decrement the ledger (`data/spend/consumption.json`).

The token counts are already on `ChatResponse` (`prompt_tokens`/`completion_tokens`), parsed at the single LLM I/O choke point `llm/http_client.py::call_chat(route, …) -> ChatResponse`, where `route.task/.provider/.model` are known. `call_chat` is invoked from ~8 modules. A pure `CostEntry` + `append_cost(history, entry) -> [*history, entry]` already exist in `llm/cost_tracker.py` (unwired before Phase 2).

The repo's hard rules collide on the obvious implementations: **no shared mutable module state / no globals**; **pure cores stay pure (effects at edges)**; **never mutate function arguments**; **return transformed data rather than mutate in place**. Any accumulator that spans a whole run's many `call_chat` calls has to thread usage somehow without breaking these.

The call_chat wrappers come in two shapes, which is the non-obvious part a future reader will hit:

- **Shape A** — the wrapper returns the `ChatResponse` to its caller: `memo/synthesizer.py::synthesize_memo`, `memo/auditor.py::audit_memo`, `queries/responder.py::respond_to_query`.
- **Shape B** — the wrapper consumes `resp` internally and returns a **domain object**, so the caller never sees the tokens: `scoring/factors/macro_fit.py::score_macro_fit -> FactorScore`, `discovery/reason_writer.py::write_reason`, `research/synthesize.py::synthesize_report -> ResearchReport`, `research/falsification.py::generate_falsification`, `opportunity/debate.py::run_defend`/`run_falsify`.

## Decision

**Actual usage rides home as ordinary return data, up to the command edge, which calls `spend/record_run.py::record_command_run`.** One principle, two seams:

- **Shape A** — the command edge (`run_memo`, `run_ask`) appends a `CostEntry` (via the pure `append_cost`) from the `ChatResponse` it already receives. No wrapper change.
- **Shape B** — the `call_chat` wrapper is itself the I/O edge (it performs the network call, so it is **not** a pure core); it **returns its usage alongside its domain result** (e.g. `score_macro_fit(ctx, route) -> tuple[FactorScore, ChatResponse]`). The orchestration layer (`scoring/pipeline.py`, `discovery/pipeline.py`, `research/theme_research.py`, `opportunity/debate.py::run_debates`) gathers them into a **local** list and returns it up; the command edge feeds the collected `history` (+ search-unit counts) to `record_command_run`.

The **pure math cores** (scoring formulas, thesis derivation, report assembly) never see a `CostEntry`. No `recorder` parameter is threaded *down*; no module-level or `contextvars` sink exists.

Two related recorder semantics are locked here because a reader of `record_run.py` will want them:

- **Fires on success *and* failure**, guarded by a "made paid calls" early-return. `call_chat` raises on failure, so `history` only ever holds **completed, billed** calls — recording them keeps the ledger honest (under-counting spend is the dangerous direction for a "do I have enough?" gate; over/accurate-counting is safe). Resume re-runs are new billed calls, correctly counted again.
- **Trigger is "spends money," not "is gated."** The recorder is wired into `research`/`discover`/`score`/`opportunity`/`memo` + standalone `ask`/`eval-funds`/`narrative --analyze` — **not** `decision` (gated but zero paid calls). Wallet-vs-quota is derived from `config/spend_balances.yaml` (the reader's own `entry.quota is not None` predicate), never passed by the command.

## Considered options

- **Module-global or `contextvars` usage sink, set at the command edge, read inside `call_chat`.** Rejected: it is precisely the "shared mutable module state / global" the project's `CLAUDE.md` forbids. Cheapest to wire (one hook, zero signature churn) but it makes the data flow invisible and untestable without process-scoped fixtures.
- **A mutable `list[CostEntry]` (or a `Recorder` object) threaded *down* as a parameter to the wrappers/orchestration.** Rejected: it **mutates a passed-in argument** (forbidden) and leaks an effectful sink parameter into the orchestration layer. Less return-type churn than the chosen option, but it trades a banned mutation for that convenience.
- **Usage rides home as return data (chosen).** The only option honoring all of: no globals, pure cores untouched, never mutate arguments, effects at edges. Cost: return-type churn on the four Shape-B wrappers + their one orchestration layer each (each a per-stage commit). This mirrors the Shape-A path (memo) exactly — usage is just data, one or two layers deeper.

## Consequences

**Positive:**
- Convergence is fully unit-testable with **simulated/injected actuals** (no network, no spend) — `fold_actuals`, `record_command_run`, and the per-stage edges all take plain data.
- Default-path behaviour is unchanged where a stage isn't yet wired: usage is additive return data, so an unwired edge simply doesn't record.
- Writer/reader can't drift on wallet-vs-quota (single predicate, single config source).

**Negative (acknowledged):**
- Shape-B wrappers now return tuples like `(FactorScore, ChatResponse)`, which reads oddly until you know this ADR — a *scoring* function appears to return LLM usage. Mitigated by the CONTEXT.md `CostEntry` entry and this ADR, which exist so the next contributor does **not** "tidy" the tuples into a global sink.
- Two falsification call paths already exist (theme-shaped `research/falsification.py`, card-shaped `opportunity/debate.py`, per ADR 0011); both now return usage, so the rule applies uniformly rather than special-casing either.
