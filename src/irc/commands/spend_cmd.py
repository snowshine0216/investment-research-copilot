from __future__ import annotations
import os
from datetime import date, timezone, timedelta, datetime
from pathlib import Path
from irc.spend.preflight import run_preflight

# provider → env var holding its key (only paid providers the gate can probe/ledger)
_PROVIDER_ENV: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "brave": "BRAVE_API_KEY",
    "bocha": "BOCHA_API_KEY",
    "jina": "JINA_API_KEY",
}
_TRUE = {"1", "true", "yes", "on"}


def collect_api_keys() -> dict[str, str]:
    """Read provider keys from the environment; omit any that are unset/blank."""
    out = {}
    for provider, env_name in _PROVIDER_ENV.items():
        val = os.environ.get(env_name, "").strip()
        if val:
            out[provider] = val
    return out


def _china_today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def preflight_gate(
    repo_root: str,
    command: str,
    *,
    stages: tuple[str, ...] | None = None,
    today: date | None = None,
) -> int:
    """Run the spend gate for a command. Returns 0 to proceed, 5 to stop. Set
    IRC_SKIP_SPEND_GATE=1 to bypass (e.g. offline dev)."""
    if os.environ.get("IRC_SKIP_SPEND_GATE", "").strip().lower() in _TRUE:
        return 0
    return run_preflight(
        repo_root, command, stages=stages,
        api_keys=collect_api_keys(), today=today or _china_today(),
    )
