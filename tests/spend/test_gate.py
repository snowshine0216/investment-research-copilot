from irc.spend.types import CostEstimate, BalanceReading
from irc.spend.gate import decide


def _est(provider, amount, currency="CNY"):
    return CostEstimate(provider, currency, amount, {provider: amount})


def _bal(provider, amount, available=True, source="api", currency="CNY"):
    return BalanceReading(provider, currency, amount, available, source)


def test_blocks_when_balance_below_estimate_times_margin():
    d = decide({"deepseek": _est("deepseek", 10.0)},
               {"deepseek": _bal("deepseek", 11.0)}, margin=1.2)  # need 12.0
    assert [v.provider for v in d.blocked] == ["deepseek"]


def test_ok_when_balance_covers_estimate_with_margin():
    d = decide({"deepseek": _est("deepseek", 10.0)},
               {"deepseek": _bal("deepseek", 15.0)}, margin=1.2)
    assert [v.provider for v in d.ok] == ["deepseek"]


def test_blocks_when_provider_flag_unavailable_even_if_amount_high():
    d = decide({"deepseek": _est("deepseek", 1.0)},
               {"deepseek": _bal("deepseek", 999.0, available=False)}, margin=1.2)
    assert [v.provider for v in d.blocked] == ["deepseek"]


def test_warns_when_balance_unreadable():
    d = decide({"jina": _est("jina", 1.0, currency="tokens")},
               {"jina": _bal("jina", None, available=False, source="probe_failed", currency="tokens")},
               margin=1.2)
    assert [v.provider for v in d.warnings] == ["jina"]
    assert d.blocked == ()


def test_negative_ledger_balance_blocks():
    d = decide({"bocha": _est("bocha", 0.5)},
               {"bocha": _bal("bocha", -3.0, available=False, source="ledger")}, margin=1.2)
    assert [v.provider for v in d.blocked] == ["bocha"]
