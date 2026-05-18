# 001 — Package `evals/` for installed CLI + regression test

## Problem

`uv run irc eval research` (and every other `irc eval <stage>` invocation) fails with:

```
ModuleNotFoundError: No module named 'evals'
```

Root cause: `pyproject.toml` declares only `src/irc` as a wheel package, so the installed console script `irc` has no `evals/` on its import path. Tests pass because `pyproject.toml` sets `pythonpath = ["src", "."]` for pytest, but the installed entrypoint does not see the repo root.

## Required behavior

- Installed `irc` console script can import `evals.*` modules.
- Every existing test still passes.
- A new regression test fails today and passes after the fix.

## Acceptance criteria

- `pyproject.toml` includes the top-level `evals` package in the wheel build.
- A new test `tests/evals/test_packaging.py` proves the `evals` package is importable from a fresh subprocess that runs the installed CLI entrypoint. The test must fail on the current `main` build and pass after the fix.
- `uv run pytest -x` exits 0 after the change.
- No changes to runner contracts, registry, or runner code — packaging only.

## Non-goals

- Do NOT move `evals/` under `src/irc/evals/`. Spec §Recommended-architecture-1 explicitly defers that as a separate refactor.
- Do NOT rename the `evals` package.
- Do NOT add CI changes.

## Files touched

- `pyproject.toml` (add `evals` to the wheel's packaged trees)
- `tests/evals/test_packaging.py` (new)
