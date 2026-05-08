from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import yaml
from irc.config_loader import load_repo_configs
from irc.io_utils import atomic_write_text
from irc.allocation.mode_selector import select_mode
from irc.trades.pipeline import build_trade_plan


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def run_plan(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()
    alloc_path = root / "outputs" / today / "proposed_allocation.yaml"
    if not alloc_path.exists():
        candidates = sorted((root / "outputs").glob("*/proposed_allocation.yaml"))
        if not candidates:
            print("ERROR: no proposed_allocation.yaml; run `irc allocate` first.")
            return 2
        alloc_path = candidates[-1]
    alloc = yaml.safe_load(alloc_path.read_text(encoding="utf-8"))
    selected = alloc["selected_instruments"]
    universe_combined_items: list[dict] = []
    for u in (bundle.universe_qdii_us, bundle.universe_qdii_hk,
              bundle.universe_cn_funds, bundle.universe_gold):
        universe_combined_items.extend(i.model_dump() for i in u.instruments)
    from irc.schemas.universe import UniverseConfig
    universe = UniverseConfig.model_validate({"instruments": universe_combined_items})
    available_venues: list[str] = []
    for acc in bundle.account.accounts:
        available_venues.extend(acc.available_venues)
    current_total = sum(h.cost_basis_cny for acc in bundle.account.accounts for h in acc.holdings)
    mode = select_mode(
        current_total_cny=current_total,
        monthly_new_capital_cny=bundle.preferences.investment_plan.monthly_new_capital_cny,
    )
    rows = build_trade_plan(
        selected_instruments=selected, mode=mode,
        valuation_percentiles={},  # Plan 4 will populate; default to mode-based
        available_venues=list(set(available_venues)),
        universe=universe, valuation=bundle.valuation_buckets,
        triggers=bundle.triggers,
    )
    out_path = root / "outputs" / today / "trade_plan.yaml"
    atomic_write_text(out_path, yaml.safe_dump(
        {"mode": mode, "trades": rows}, sort_keys=False, allow_unicode=True))
    print(f"plan OK: mode={mode}, {len(rows)} trades → {out_path}")
    return 0
