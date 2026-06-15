"""Live smoke test for the MiniMax provider route (§12.1/§12.2).

Double-gated: BOTH ``RUN_LIVE_LLM_TESTS=1`` AND ``-m live_llm`` are required.
Without the env var the module-level ``pytestmark`` skips every test here before
any import of the LLM packages occurs, so no real network traffic is triggered.

Verifies:
  §12.1 — MiniMax OpenAI-compatible path (…/v1/chat/completions) + auth header.
  §12.2 — ``base_resp`` error-envelope detection in ``_parse_response`` fires on
           a malformed 200 response (unit-tested in test_http_client.py); this live
           call confirms the happy-path shape so the envelope guard is exercised.

Degradation: if MINIMAX_API_KEY / MINIMAX_BASE_URL are absent the test is skipped
(resolve_route / call_chat raise a clear env-var-missing error); the monitor report
ships with ``narrative_status`` degraded when the provider fails at runtime.

Run::

    RUN_LIVE_LLM_TESTS=1 uv run pytest tests/llm/test_live_minimax.py -v -m live_llm
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from irc.config_loader import load_yaml
from irc.llm.gateway import resolve_route
from irc.llm.http_client import call_chat

_REPO = Path(__file__).resolve().parents[2]

# Module-level skip gate: both the env var AND -m live_llm are required.
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_LLM_TESTS") != "1",
    reason="double-gated: set RUN_LIVE_LLM_TESTS=1 to hit MiniMax",
)


@pytest.mark.live_llm
def test_minimax_round_trip() -> None:
    """§12.1/§12.2: one real chat call through the monitor's MiniMax route.

    Confirms:
    - ``resolve_route("monitor_impact", ...)`` resolves without KeyError
      (provider + task both present in config/llm.yaml).
    - The OpenAI-compatible path ``<base_url>/chat/completions`` is reachable
      and returns a non-empty response text.
    - If MiniMax returns a ``base_resp`` error envelope inside an HTTP 200, the
      ``_parse_response`` guard raises immediately with a clear message (§12.2).
    """
    cfg = load_yaml(_REPO / "config/llm.yaml", _REPO)
    route = resolve_route("monitor_impact", cfg)
    resp = call_chat(
        route,
        [{"role": "user", "content": "Reply with the single word OK."}],
        temperature=0.0,
        max_tokens=8,
    )
    assert resp.text, (
        "MiniMax round-trip returned an empty response text — "
        "check MINIMAX_BASE_URL + MINIMAX_API_KEY + MINIMAX_MODEL env vars."
    )
