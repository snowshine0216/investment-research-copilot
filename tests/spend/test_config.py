from pathlib import Path
import pytest
from irc.spend.config import load_pricing, load_balances, load_consumption

REPO = Path(__file__).resolve().parents[2]


def test_load_pricing_has_margin_and_deepseek_models():
    pricing = load_pricing(REPO)
    assert pricing.margin == 1.2
    assert "deepseek-reasoner" in pricing.llm["deepseek"].models
    assert pricing.llm["deepseek"].currency == "CNY"
    assert pricing.seeds["memo_synthesis"].completion_tokens > 0


def test_load_balances_accepts_wallet_and_quota_entries():
    balances = load_balances(REPO)
    assert balances.entries["bocha"].balance is not None    # wallet
    assert balances.entries["brave"].quota is not None      # quota
    assert balances.entries["tavily"].quota is not None      # quota (PAYG)


def test_load_balances_rejects_entry_that_is_neither_wallet_nor_quota(tmp_path):
    bad = tmp_path / "spend_balances.yaml"
    bad.write_text("tavily: {foo: 1}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_balances(tmp_path, filename=bad.name)


def test_load_consumption_missing_file_returns_empty(tmp_path):
    assert load_consumption(tmp_path) == {}
