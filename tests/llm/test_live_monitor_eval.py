"""Live double-gated test for the M1 LLM eval suites (§6, OQ-A).

Double-gated: BOTH the registered ``live_llm`` marker AND
``IRC_RUN_LIVE_LLM_EVAL=1`` are required. ``IRC_RUN_LIVE_LLM_EVAL`` is the SAME
switch that ungates the runner (eval_cmd._run_live_gated), so "this test runs"
⟺ "the runner would run" — one switch, zero drift (OQ-A).

Requires a FAST non-reasoning MINIMAX_MODEL (MiniMax-Text-01, NOT M3) — a
reasoning model both over-spends and risks JSON-mode drift (project memory).

Run::

    IRC_RUN_LIVE_LLM_EVAL=1 uv run pytest tests/llm/test_live_monitor_eval.py -m live_llm -v
"""
from __future__ import annotations
import os
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    os.environ.get("IRC_RUN_LIVE_LLM_EVAL") != "1",
    reason="double-gated: set IRC_RUN_LIVE_LLM_EVAL=1 to drive the corpora through MiniMax",
)


@pytest.mark.live_llm
def test_impact_suite_passes_on_current_prompts():
    from evals.monitor_impact.runner import run
    rc = run(_REPO)
    assert rc == 0, "impact suite did not PASS — check prompts / MINIMAX_MODEL"


@pytest.mark.live_llm
def test_narrative_suite_passes_on_current_prompts():
    from evals.monitor_narrative.runner import run
    rc = run(_REPO)
    assert rc == 0, "narrative suite did not PASS — check prompts / MINIMAX_MODEL"
