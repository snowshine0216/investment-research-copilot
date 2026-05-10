from __future__ import annotations

from typing import Any


def requires_manager_tenure(instrument: Any) -> bool:
    if instrument.market == "cn_on_exchange":
        return False
    return instrument.asset_class.endswith(("equity_fund", "bond_fund"))