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
    out_dir: Path | None = None,
    write_estimate: bool = False,
) -> int:
    """Run the spend gate for a command. Returns 0 to proceed, 5 to stop. Set
    IRC_SKIP_SPEND_GATE=1 to bypass (e.g. offline dev)."""
    if os.environ.get("IRC_SKIP_SPEND_GATE", "").strip().lower() in _TRUE:
        return 0
    return run_preflight(
        repo_root, command, stages=stages,
        api_keys=collect_api_keys(), today=today or _china_today(),
        out_dir=out_dir, write_estimate=write_estimate,
    )


def run_spend_status(repo_root: str, *, today: date | None = None) -> int:
    """Read-only: print effective ledger balances for every configured provider.
    Triggers no paid calls and writes nothing."""
    from irc.spend.config import load_balances, load_consumption
    from irc.spend.ledger import effective_balance
    root = Path(repo_root)
    balances = load_balances(root)
    consumption = load_consumption(root)
    when = today or _china_today()
    print("── spend status (ledger; read-only) ──")
    for provider, entry in balances.entries.items():
        r = effective_balance(provider, entry, consumption, today=when)
        kind = "quota" if entry.quota is not None else "wallet"
        flag = "" if r.available else "  ⚠ insufficient"
        print(f"  {provider:11} [{kind}] effective={r.amount:.4g}{flag}")
    print("  (DeepSeek/OpenRouter balances are read live by the gate, not shown here.)")
    return 0
