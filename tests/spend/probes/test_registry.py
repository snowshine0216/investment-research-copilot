from irc.spend.probes import PROBES


def test_registry_exposes_api_probes():
    assert set(PROBES) == {"deepseek", "openrouter"}
    assert PROBES["deepseek"].provider == "deepseek"
