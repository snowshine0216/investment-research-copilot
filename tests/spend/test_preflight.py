import json
from datetime import date
from pathlib import Path
import yaml
from irc.spend.types import BalanceReading
from irc.spend.preflight import run_preflight

REPO = Path(__file__).resolve().parents[2]


def _seed_repo(repo: Path) -> None:
    """Write minimal config files so run_preflight can load pricing/balances/llm."""
    (repo / "config").mkdir(parents=True, exist_ok=True)
    (repo / "config/spend_pricing.yaml").write_text(yaml.safe_dump({
        "margin": 1.2,
        "llm": {"deepseek": {"currency": "CNY", "models": {
            "deepseek-chat": {"input_per_mtok": 0.9515, "output_per_mtok": 1.9029},
        }}},
        "search": {"tavily": {"currency": "credits", "per_query": 2.0}},
        "seeds": {
            "memo_synthesis": {"calls": 1, "prompt_tokens": 12000, "completion_tokens": 6000},
            "memo_audit": {"calls": 1, "prompt_tokens": 12000, "completion_tokens": 6000},
        },
        "search_seeds": {"tavily": {"units": 40}},
    }), encoding="utf-8")
    (repo / "config/spend_balances.yaml").write_text(yaml.safe_dump({
        "deepseek": {"balance": 999.0, "as_of": "2026-06-01"},
    }), encoding="utf-8")
    (repo / "config/llm.yaml").write_text(yaml.safe_dump({
        "providers": {
            "deepseek": {
                "base_url": "https://api.deepseek.com",
                "api_key_env": "DEEPSEEK_API_KEY",
            },
        },
        "tasks": {
            "memo_synthesis": {"provider": "deepseek", "model": "deepseek-chat"},
            "memo_audit": {"provider": "deepseek", "model": "deepseek-chat"},
        },
    }), encoding="utf-8")


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


def test_run_preflight_writes_estimate_only_when_write_estimate(tmp_path):
    _seed_repo(tmp_path)                       # pricing + llm.yaml + balances (existing helper)
    today = date(2026, 6, 6)
    run_preflight(tmp_path, "memo", api_keys={}, today=today)            # default: no opt-in
    assert not (tmp_path / "outputs/2026-06-06/spend_estimate.json").exists()
    run_preflight(tmp_path, "run", api_keys={}, today=today,
                  stages=("memo",), write_estimate=True)  # opt-in
    art = json.loads((tmp_path / "outputs/2026-06-06/spend_estimate.json").read_text())
    assert "deepseek" in art and "currency" in art["deepseek"]   # per-provider, currency kept
