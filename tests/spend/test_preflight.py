from datetime import date
from pathlib import Path
from irc.spend.types import BalanceReading
from irc.spend.preflight import run_preflight

REPO = Path(__file__).resolve().parents[2]


class _FakeProbe:
    def __init__(self, provider, amount, available=True):
        self.provider = provider
        self._amount, self._available = amount, available

    def probe(self, api_key, *, client=None):
        return BalanceReading(self.provider, "CNY", self._amount, self._available, "api")


def _keys():
    return {"deepseek": "sk-x"}   # only deepseek key present → only deepseek probed


def test_returns_0_when_balance_covers_estimate(capsys):
    probes = {"deepseek": _FakeProbe("deepseek", 9999.0)}
    rc = run_preflight(REPO, "run", stages=("score", "memo"),
                       api_keys=_keys(), probes=probes, today=date(2026, 6, 5))
    assert rc == 0
    assert "spend preflight" in capsys.readouterr().out.lower()


def test_returns_5_and_prints_block_when_insufficient(capsys):
    probes = {"deepseek": _FakeProbe("deepseek", 0.01)}
    rc = run_preflight(REPO, "run", stages=("score", "memo"),
                       api_keys=_keys(), probes=probes, today=date(2026, 6, 5))
    assert rc == 5
    out = capsys.readouterr().out
    assert "BLOCKED" in out and "deepseek" in out


def test_probe_failure_warns_and_proceeds(capsys):
    class _Boom:
        provider = "deepseek"
        def probe(self, api_key, *, client=None):
            return BalanceReading("deepseek", "CNY", None, False, "probe_failed")
    rc = run_preflight(REPO, "run", stages=("score", "memo"),
                       api_keys=_keys(), probes={"deepseek": _Boom()}, today=date(2026, 6, 5))
    assert rc == 0
    assert "unreadable" in capsys.readouterr().out.lower()
