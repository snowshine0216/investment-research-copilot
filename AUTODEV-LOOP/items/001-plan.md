# 001 — Plan

## Step 1 — failing test (Red)

Create `tests/evals/test_packaging.py`:

```python
"""Regression test for the installed CLI being able to import `evals`.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/001-spec.md

The bug: pyproject.toml originally packaged only src/irc into the wheel,
so `irc eval <stage>` raised ModuleNotFoundError before any metric ran.
This test guards against regression by exercising the importability of
every `evals.<stage>.runner` module the registry knows about,
using a fresh subprocess so the test doesn't benefit from pytest's
pythonpath = ["src", "."] override.
"""
from __future__ import annotations
import subprocess
import sys


_STAGES = (
    "data", "news", "research", "discovery", "scoring",
    "gold_score", "allocation", "trade_plan",
    "memo", "queries", "triggers", "architecture", "opportunity",
)


def test_evals_runners_importable_from_clean_subprocess() -> None:
    """Each evals.<stage>.runner must import in a Python process that
    does NOT inherit pytest's sys.path tweaks.

    We launch python with an empty PYTHONPATH and rely solely on the
    installed package layout. If the wheel does not ship `evals/`,
    the import fails — which is exactly the production bug we're fixing.
    """
    script = "\n".join(
        f"import importlib; importlib.import_module('evals.{s}.runner')"
        for s in _STAGES
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={"PYTHONPATH": "", "PATH": ""},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"evals runners failed to import from a clean subprocess.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
```

Run: `uv run pytest tests/evals/test_packaging.py -x` — expect FAIL with `ModuleNotFoundError: No module named 'evals'`.

## Step 2 — minimum fix (Green)

Edit `pyproject.toml` `[tool.hatch.build.targets.wheel]`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/irc", "evals"]
```

Re-install the package so the wheel layout reflects the new manifest:

```
uv sync
```

Re-run: `uv run pytest tests/evals/test_packaging.py -x` — expect PASS.

## Step 3 — verify nothing else broke

```
uv run pytest -x
```

Must exit 0.

## Step 4 — sanity check the actual CLI bug

```
uv run irc eval research
```

Must NOT raise `ModuleNotFoundError`. It may still report PASS/WARN/FAIL based on whether `data/research/research_status.json` exists — that's expected for this item.

## Step 5 — commit

Stage `pyproject.toml` + `tests/evals/test_packaging.py` + AUTODEV-LOOP updates. Single commit:

```
fix(evals): ship `evals/` package in wheel so installed CLI can import it (001)
```

Body lists the bug + the regression test as the fix evidence.

## Notes / pitfalls

- `env={"PYTHONPATH": ""}` is the key isolation: pytest's pythonpath option doesn't reach a subprocess we launch ourselves.
- Setting `PATH=""` ensures the subprocess can't accidentally re-discover the package via some other shim.
- Do NOT add `force-include` for evals templates / non-Python files unless one is required — none exists today.
- Hatch will treat `evals` as a regular package because it has `__init__.py`.
