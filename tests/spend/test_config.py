from pathlib import Path
import pytest
from irc.spend.config import (load_consumption, load_pricing, load_balances,
                              load_usage_profile_raw, write_consumption, write_usage_profile)
from irc.spend.types import TaskUsage, UsageProfile

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


def test_usage_profile_roundtrips_atomically(tmp_path):
    assert load_usage_profile_raw(tmp_path) == {}        # absent → empty
    profile = UsageProfile(tasks={
        "memo_synthesis": TaskUsage("memo_synthesis", 1.0, 1100.0, 520.0, samples=3)}, alpha=0.3)
    write_usage_profile(tmp_path, profile)
    raw = load_usage_profile_raw(tmp_path)
    assert raw["memo_synthesis"]["samples"] == 3
    assert raw["memo_synthesis"]["avg_prompt_tokens"] == 1100.0
    # file lives at the documented path
    assert (tmp_path / "data/spend/usage_profile.json").exists()


def test_write_consumption_roundtrips(tmp_path):
    write_consumption(tmp_path, {"tavily": {"consumed_since": 4.0, "since": "2026-06-06"}})
    assert load_consumption(tmp_path)["tavily"]["consumed_since"] == 4.0


# --- FIX 2: corrupt-JSON must surface the file path ---------------------------

def test_load_consumption_corrupt_json_raises_runtime_error_with_path(tmp_path):
    """A truncated consumption.json must raise RuntimeError naming the file path."""
    path = tmp_path / "data/spend/consumption.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad json", encoding="utf-8")
    with pytest.raises(RuntimeError, match=str(path)):
        load_consumption(tmp_path)


def test_load_usage_profile_raw_corrupt_json_raises_runtime_error_with_path(tmp_path):
    """A truncated usage_profile.json must raise RuntimeError naming the file path."""
    path = tmp_path / "data/spend/usage_profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad json", encoding="utf-8")
    with pytest.raises(RuntimeError, match=str(path)):
        load_usage_profile_raw(tmp_path)
