# 002 — Eval registry with lifecycle classification

## Problem

`src/irc/commands/eval_cmd.py:_get_runner` hardcodes a `dict[str, str]` of stage → module mappings and `run_eval` hardcodes a parallel tuple of stages for `--all`. The two lists drift naturally. More importantly, every stage is treated identically: `news` (no live producer) and `queries` (no persisted artifact) participate in `--all` and produce misleading missing-input FAILs that look identical to a real broken stage.

## Required behavior

- A single source of truth for which evals exist, where their runner module lives, their lifecycle state, and whether they belong in the default `--all` suite.
- Direct invocation of an inactive stage (`irc eval news`, `irc eval queries`) prints a clear "this stage is inactive" message and does not run the runner or write a misleading missing-input report.
- `irc eval --all` runs only stages marked `in_all_suite=True`.
- `triggers` remains in the active suite as a deliberate FAIL until Phase 2 (its `unimplemented_active` lifecycle records why).

## Lifecycle classification (from spec §Phase-1-target-contracts and §Stages-that-should-not-remain-in-the-default-active-suite-unchanged)

| Stage | Lifecycle | `in_all_suite` |
|---|---|---|
| data | active | true |
| research | active | true |
| discovery | active | true |
| scoring | active | true |
| gold_score | active | true |
| allocation | active | true |
| trade_plan | active | true |
| memo | active | true |
| architecture | active | true |
| opportunity | active | true |
| triggers | unimplemented_active | true |
| news | inactive_legacy | false |
| queries | inactive_uninstrumented | false |

## Acceptance criteria

- `evals/_shared/registry.py` exists with:
  - frozen `EvalStageSpec` dataclass (`stage`, `runner_module`, `lifecycle`, `in_all_suite`)
  - `Lifecycle` Literal of exactly the four values above
  - module-level `REGISTRY: dict[str, EvalStageSpec]` covering all 13 stages
  - `get_spec(stage) -> EvalStageSpec` raising `KeyError` on unknown
  - `active_suite_stages() -> tuple[str, ...]` excluding inactive stages, preserving the spec's stage order
  - `is_inactive(spec) -> bool` for the two `inactive_*` lifecycles
- `src/irc/commands/eval_cmd.py` is rewritten to use the registry as its single source of truth (no inline stage list, no inline runner-module dict).
- Direct invocation of `news` or `queries` returns rc=2, prints a message naming the lifecycle, and does NOT call into the runner module.
- `--all` summary lists 11 stages (10 active + triggers); does NOT list news or queries.
- All existing tests pass (`tests/commands/test_eval_cmd.py`, `tests/test_cli_smoke.py`, every runner test).
- A new `tests/evals/test_registry.py` covers registry contents and helpers.
- A new section in `tests/commands/test_eval_cmd.py` (or a new test file) covers the inactive-stage CLI behavior and the active-suite filter.

## Non-goals

- Do not move runner modules.
- Do not change runner internals.
- Do not change report-writing behavior for active stages (that's items 003/004).
- Do not change the rc encoding (0=PASS, 1=WARN, 2=FAIL stays).

## Files touched

- `evals/_shared/registry.py` (new)
- `src/irc/commands/eval_cmd.py` (rewrite using registry)
- `tests/evals/test_registry.py` (new)
- `tests/commands/test_eval_cmd.py` (add inactive-stage + active-suite tests)
