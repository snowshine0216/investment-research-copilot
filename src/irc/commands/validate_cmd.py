from __future__ import annotations
from pathlib import Path
import sys
from irc.config_loader import load_repo_configs


def run_validate(repo_root: str) -> int:
    root = Path(repo_root)
    try:
        bundle = load_repo_configs(root)
    except Exception as exc:  # noqa: BLE001 — surface every config error to user
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    n_inst = (
        len(bundle.universe_qdii_us.instruments)
        + len(bundle.universe_qdii_hk.instruments)
        + len(bundle.universe_cn_funds.instruments)
        + len(bundle.universe_gold.instruments)
    )
    print(
        "OK: all 14 YAML files validated.\n"
        f"  scoring weights version: {bundle.scoring.weights_version}\n"
        f"  universe size: {n_inst} instruments\n"
        f"  llm tasks configured: {len(bundle.llm.tasks)}"
    )
    return 0
