from __future__ import annotations
import json
from datetime import date as _date
from pathlib import Path
from irc.config_loader import load_yaml
from irc.spend.config import (
    load_balances, load_consumption, load_pricing, load_usage_profile_raw,
)
from irc.spend.estimator import estimate
from irc.spend.gate import decide
from irc.spend.ledger import effective_balance
from irc.spend.probes import PROBES
from irc.spend.profile import effective_profile, seed_profile
from irc.spend.scope import resolve_scope
from irc.spend.types import BalanceReading, CostEstimate, GateDecision


def _balance_for(
    provider: str, api_keys: dict[str, str], probes, balances, consumption, pricing, today: _date,
) -> BalanceReading | None:
    if provider in probes and api_keys.get(provider):
        return probes[provider].probe(api_keys[provider])
    entry = balances.entries.get(provider)
    if entry is not None:
        reading = effective_balance(provider, entry, consumption, today=today)
        currency = pricing.search[provider].currency if provider in pricing.search else reading.currency
        return BalanceReading(provider, currency, reading.amount, reading.available, reading.source)
    return None   # no probe, no ledger (e.g. openbb/tiingo) → caller emits info/warn


def _print_table(command: str, decision: GateDecision, estimates: dict[str, CostEstimate]) -> None:
    print(f"\n── spend preflight ({command}) ──")
    for v in (*decision.blocked, *decision.warnings, *decision.ok):
        tag = {"blocked": "BLOCKED", "warning": "WARN", "ok": "ok", "info": "info"}[v.status]
        est = f"{v.estimate:.4g}" if v.estimate is not None else "—"
        bal = f"{v.balance:.4g}" if v.balance is not None else "—"
        print(f"  [{tag:7}] {v.provider:11} est={est:>10}  bal={bal:>10}  {v.detail}")
    if decision.blocked:
        print("  → STOP: insufficient balance. Top up, or edit config/spend_balances.yaml.")


def run_preflight(
    repo_root: Path | str,
    command: str,
    *,
    stages: tuple[str, ...] | None = None,
    api_keys: dict[str, str],
    probes: dict | None = None,
    today: _date,
    out_dir: Path | None = None,
    write_estimate: bool = False,
) -> int:
    """Edge: estimate scoped spend, read balances (probe or ledger), decide. Returns
    0 to proceed (possibly with warnings) or 5 to stop. Never raises on probe failure.
    When write_estimate=True, writes outputs/<today>/spend_estimate.json (irc run only)."""
    root = Path(repo_root)
    probes = PROBES if probes is None else probes
    pricing = load_pricing(root)
    balances = load_balances(root)
    consumption = load_consumption(root)
    llm = load_yaml(root / "config/llm.yaml", root)
    profile = effective_profile(seed_profile(pricing), load_usage_profile_raw(root))

    scope = resolve_scope(command, stages=stages)
    estimates = estimate(scope.tasks, scope.search_providers, llm, profile, pricing)

    readings: dict[str, BalanceReading] = {}
    for provider in estimates:
        reading = _balance_for(provider, api_keys, probes, balances, consumption, pricing, today)
        if reading is not None:
            readings[provider] = reading

    decision = decide(estimates, readings, margin=pricing.margin)
    _print_table(command, decision, estimates)

    if write_estimate:
        from irc.spend.estimate_io import estimate_to_dict
        from irc.io_utils import atomic_write_text
        dest = out_dir or root / "outputs" / today.isoformat()
        Path(dest).mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            Path(dest) / "spend_estimate.json",
            json.dumps(estimate_to_dict(estimates), indent=2, sort_keys=True),
        )

    return 5 if decision.blocked else 0
