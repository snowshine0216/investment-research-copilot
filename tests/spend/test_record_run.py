import json
from datetime import date
from pathlib import Path
import yaml
from irc.llm.cost_tracker import CostEntry
from irc.spend.record_run import record_command_run


def _seed_configs(repo: Path):
    (repo / "config").mkdir(parents=True, exist_ok=True)
    (repo / "config/spend_pricing.yaml").write_text(yaml.safe_dump({
        "margin": 1.2,
        "llm": {"deepseek": {"currency": "CNY",
                             "models": {"deepseek-chat": {"input_per_mtok": 1.0, "output_per_mtok": 2.0}}}},
        "search": {"tavily": {"currency": "credits", "per_query": 2.0}},
        "seeds": {"memo_synthesis": {"calls": 4, "prompt_tokens": 4000, "completion_tokens": 2000}},
        "search_seeds": {"tavily": {"units": 10}},
    }), encoding="utf-8")
    (repo / "config/spend_balances.yaml").write_text(yaml.safe_dump({
        "bocha": {"balance": 2870, "as_of": "2026-06-01"},          # wallet
        "brave": {"quota": 2000, "reset": "monthly", "reset_day": 1},  # quota
    }), encoding="utf-8")


def test_record_run_writes_actuals_folds_profile_and_decrements_ledger(tmp_path):
    _seed_configs(tmp_path)   # also writes spend_balances.yaml: bocha=wallet, brave=quota
    out_dir = tmp_path / "outputs/2026-06-06"
    history = [CostEntry("memo_synthesis", "deepseek", "deepseek-chat", 1000, 500, 10,
                         "2026-06-06T01:00:00+08:00")]
    record_command_run(
        repo_root=tmp_path, out_dir=out_dir,
        history=history, search_units={"bocha": 4, "brave": 6}, today=date(2026, 6, 6),
    )
    # 1. actuals artifact
    actuals = json.loads((out_dir / "spend_actuals.json").read_text())
    assert actuals["tasks"]["memo_synthesis"]["avg_prompt_tokens"] == 1000.0
    assert actuals["search_units"] == {"bocha": 4, "brave": 6}
    # 2. profile folded (samples 0→1, moved off seed toward actual)
    prof = json.loads((tmp_path / "data/spend/usage_profile.json").read_text())
    assert prof["memo_synthesis"]["samples"] == 1
    assert prof["memo_synthesis"]["avg_prompt_tokens"] == 0.3 * 1000.0 + 0.7 * 4000.0
    # 3. ledger decremented — KIND DERIVED FROM spend_balances.yaml, not passed in (Q2)
    cons = json.loads((tmp_path / "data/spend/consumption.json").read_text())
    assert cons["bocha"]["consumed_since"] == 4.0          # wallet → consumed_since
    assert cons["brave"]["consumed_this_period"] == 6.0    # quota  → consumed_this_period


def test_record_run_accumulates_units_across_commands(tmp_path):
    _seed_configs(tmp_path)
    out_dir = tmp_path / "outputs/2026-06-06"
    for _ in range(2):
        record_command_run(repo_root=tmp_path, out_dir=out_dir, history=[],
                           search_units={"bocha": 5}, today=date(2026, 6, 6))
    cons = json.loads((tmp_path / "data/spend/consumption.json").read_text())
    assert cons["bocha"]["consumed_since"] == 10.0       # 5 + 5 across two commands


def test_record_run_skips_providers_with_no_balance_entry(tmp_path):
    _seed_configs(tmp_path)
    record_command_run(repo_root=tmp_path, out_dir=tmp_path / "outputs/2026-06-06",
                       history=[], search_units={"unknown_provider": 9}, today=date(2026, 6, 6))
    cpath = tmp_path / "data/spend/consumption.json"
    cons = json.loads(cpath.read_text()) if cpath.exists() else {}
    assert "unknown_provider" not in cons                # no entry → no orphan row


def test_record_run_no_paid_calls_writes_nothing(tmp_path):
    # Q4 guard: a command that made no paid calls (e.g. `decision`) records nothing.
    _seed_configs(tmp_path)
    out_dir = tmp_path / "outputs/2026-06-06"
    record_command_run(repo_root=tmp_path, out_dir=out_dir, history=[],
                       search_units={}, today=date(2026, 6, 6))
    assert not (out_dir / "spend_actuals.json").exists()
    assert not (tmp_path / "data/spend/usage_profile.json").exists()
