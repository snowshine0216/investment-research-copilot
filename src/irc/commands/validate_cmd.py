from __future__ import annotations
from pathlib import Path
import sys
from irc.config_loader import load_repo_configs, TEMPLATE_FILES


def run_validate(repo_root: str) -> int:
    root = Path(repo_root)
    try:
        bundle = load_repo_configs(root)
    except Exception as exc:  # noqa: BLE001 — surface every config error to user
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    from irc.spend.config import load_pricing, load_balances
    try:
        pricing = load_pricing(root)
        load_balances(root)
    except Exception as exc:  # noqa: BLE001 — surface spend-config errors too
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    n_inst = (
        len(bundle.universe_qdii_us.instruments)
        + len(bundle.universe_qdii_hk.instruments)
        + len(bundle.universe_cn_funds.instruments)
        + len(bundle.universe_gold.instruments)
    )
    print(
        f"OK: all {len(TEMPLATE_FILES)} YAML files validated.\n"
        f"  scoring weights version: {bundle.scoring.weights_version}\n"
        f"  universe size: {n_inst} instruments\n"
        f"  llm tasks configured: {len(bundle.llm.tasks)}\n"
        f"  spend: margin {pricing.margin}, {len(pricing.seeds)} task seeds"
    )
    return 0
