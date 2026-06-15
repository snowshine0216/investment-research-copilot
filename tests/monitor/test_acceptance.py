"""Acceptance/contract guards for the monitor vertical.

These tests enforce repo-wide invariants that protect architectural
contracts (ADR 0015, ADR 0017, sole-source policy, forbidden indicator).
They are deliberately strict — grep failures are loud and actionable.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_no_jijinkuang_indicator_in_production_fetch() -> None:
    """The forbidden 基金概况 indicator must not appear in monitor production code.

    The monitor fetches NAV via fetch_fund_nav_history (indicator 单位净值走势) only.
    A grep-acceptance test prevents silent regressions where the forbidden
    indicator is accidentally referenced (ADR 0017 / Conventions §20).
    """
    hits = subprocess.run(
        ["grep", "-rn", "基金概况", str(REPO / "src" / "irc" / "monitor")],
        capture_output=True,
        text=True,
    )
    assert hits.returncode != 0, (
        f"基金概况 found in monitor production code:\n{hits.stdout}"
    )


def test_monitor_cmd_does_not_call_load_repo_configs() -> None:
    """Sole-source contract: monitor_cmd reads ONLY config/monitor.yaml.

    It must use load_monitor_config and must never IMPORT or CALL load_repo_configs
    (which would pull in preferences.yaml, universe/*, etc.).
    We check that `from ... import load_repo_configs` or a bare call does not appear.
    References in the module docstring (which explicitly forbid the call) are allowed.
    """
    import ast

    src_text = (REPO / "src" / "irc" / "commands" / "monitor_cmd.py").read_text(
        encoding="utf-8"
    )
    # Check via AST: no import or call to load_repo_configs
    tree = ast.parse(src_text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = [alias.name for alias in node.names]
            assert "load_repo_configs" not in imported_names, (
                "monitor_cmd.py must not import load_repo_configs (sole-source contract)"
            )
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute)
                else ""
            )
            assert name != "load_repo_configs", (
                "monitor_cmd.py must not call load_repo_configs (sole-source contract)"
            )
    # Confirm the correct loader is present
    assert "load_monitor_config" in src_text, (
        "monitor_cmd.py must import and use load_monitor_config"
    )


def test_monitor_types_never_use_bare_action_field() -> None:
    """ADR 0015: monitor types must not carry an executable `action` field.

    The monitor produces research biases (ADD_BIAS/NEUTRAL/REDUCE_BIAS | NO_CALL),
    never executable actions. A bare `action` attribute on a type would violate
    this contract.
    """
    types_src = (REPO / "src" / "irc" / "monitor" / "types.py").read_text(
        encoding="utf-8"
    )
    assert "\n    action" not in types_src, (
        "monitor/types.py must not define a bare `action` field (ADR 0015)"
    )
