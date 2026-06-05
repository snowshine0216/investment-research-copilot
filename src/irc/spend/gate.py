from __future__ import annotations
from irc.spend.types import BalanceReading, CostEstimate, GateDecision, ProviderVerdict


def _verdict(provider: str, est: CostEstimate | None, bal: BalanceReading | None, margin: float) -> ProviderVerdict:
    est_amt = est.amount if est else None
    bal_amt = bal.amount if bal else None
    if est is not None and bal is not None and bal.amount is not None:
        need = est.amount * margin
        if not bal.available or bal.amount < need:
            return ProviderVerdict(provider, est_amt, bal_amt, "blocked",
                                   f"need ≥ {need:.4g} {est.currency}, have {bal.amount:.4g}")
        return ProviderVerdict(provider, est_amt, bal_amt, "ok",
                               f"{bal.amount:.4g} ≥ {need:.4g} {est.currency}")
    if bal is not None and bal.amount is None:
        return ProviderVerdict(provider, est_amt, None, "warning",
                               f"balance unreadable ({bal.source}); proceeding")
    if est is not None and bal is None:
        return ProviderVerdict(provider, est_amt, None, "warning",
                               "no balance source; proceeding")
    return ProviderVerdict(provider, est_amt, bal_amt, "info", "no estimate / no balance")


def decide(
    estimates: dict[str, CostEstimate],
    balances: dict[str, BalanceReading],
    *,
    margin: float,
) -> GateDecision:
    """Pure: estimates + balances + margin → grouped verdicts. Hard-stops only on a
    confirmed-insufficient reading (balance known AND below estimate×margin, or the
    provider's own flag is unavailable)."""
    providers = sorted(set(estimates) | set(balances))
    verdicts = [_verdict(p, estimates.get(p), balances.get(p), margin) for p in providers]
    return GateDecision(
        blocked=tuple(v for v in verdicts if v.status == "blocked"),
        warnings=tuple(v for v in verdicts if v.status == "warning"),
        ok=tuple(v for v in verdicts if v.status in ("ok", "info")),
    )
