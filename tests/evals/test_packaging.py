"""Regression test for the installed CLI being able to import `evals`.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/001-spec.md

The bug: pyproject.toml originally packaged only src/irc into the wheel,
so `irc eval <stage>` raised ModuleNotFoundError before any metric ran.
This test guards against regression by exercising the importability of
every `evals.<stage>.runner` module the CLI dispatches to, using a fresh
subprocess launched in isolated mode from a working directory that does
NOT contain the repo's top-level `evals/`. That isolation reproduces the
production console-script context where the only `evals` Python can find
must come from the installed package layout (the wheel), not from pytest's
pythonpath = ["src", "."] override or from Python's default
add-current-directory-to-sys.path behavior for `python -c`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


_STAGES: tuple[str, ...] = (
    "data", "news", "research", "discovery", "scoring",
    "gold_score", "allocation", "trade_plan",
    "memo", "queries", "triggers", "architecture", "opportunity",
)


def test_evals_runners_importable_from_installed_layout(tmp_path: Path) -> None:
    """Every evals.<stage>.runner imports in an isolated subprocess run from
    a clean cwd. If the wheel does not ship `evals/`, the import fails — the
    production bug we are fixing.
    """
    script = "\n".join(
        f"import importlib; importlib.import_module('evals.{s}.runner')"
        for s in _STAGES
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"evals runners failed to import from the installed layout.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
