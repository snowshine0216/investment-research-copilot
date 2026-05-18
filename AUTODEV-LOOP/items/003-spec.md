# 003 — Shared artifact locator

## Problem

Each runner re-implements (or fails to re-implement) the "find today's outputs, fall back to the latest valid dated outputs" logic. The `architecture` runner hardcodes today; `discovery`, `gold_score`, `allocation`, `trade_plan`, and `memo` read from retired non-dated paths entirely. Without a shared locator the runner modernizations in items 005–010 would each invent their own version of this logic.

## Required behavior

A pure function `locate(repo_root, required_filenames, *, today_iso=None) -> LocatedArtifacts | None` that:

1. Selects `outputs/<today_iso>/` if ALL `required_filenames` are present there.
2. Otherwise scans `outputs/<YYYY-MM-DD>/` directories and returns the latest one where ALL `required_filenames` are present.
3. Returns `None` only when no valid dated artifact set exists.
4. Returns a `LocatedArtifacts(paths, artifact_date)` where `paths` preserves the order of `required_filenames`.
5. Treats partial multi-file sets as non-matches (a date counts only if EVERY required filename exists).
6. Ignores non-date subdirectories under `outputs/` (`logs/`, `tmp/`, etc.).
7. Is pure: same inputs → same output. The `today_iso` parameter is the only "today" knob; production callers default to `None` which uses the project's Asia/Shanghai timezone.

## Acceptance criteria

- `evals/_shared/locator.py` exists with:
  - frozen `LocatedArtifacts` dataclass holding `paths: tuple[Path, ...]` and `artifact_date: str`
  - `locate(repo_root, required_filenames, *, today_iso=None)` returning `LocatedArtifacts | None`
  - module-private `_today_iso()` helper used as the default for `today_iso`
- `tests/evals/test_locator.py` covers:
  - no `outputs/` dir → None
  - no dated dir satisfies contract → None
  - today exists with full contract → today selected
  - today exists with partial contract → falls back to latest complete date
  - today absent → latest valid date selected
  - non-date subdirs ignored (`logs/`, `tmp/`)
  - empty `required_filenames` → `ValueError`
  - returned `paths` preserve caller order
- Locator does NOT depend on any runner module — strictly bottom-up.
- All existing tests still pass.

## Non-goals

- Do not wire any runner to use the locator yet (items 005–010 do that).
- Do not handle nested subdirectories under `outputs/<date>/`.
- Do not read or parse file contents — locator only checks existence.
- Do not invent a multi-stage "contract" abstraction — runners can pass their own filename tuples.

## Files touched

- `evals/_shared/locator.py` (new)
- `tests/evals/test_locator.py` (new)
