"""Pure: monitor fund + analysis_profile → typed LookthroughTarget.

Maps each of the 7 monitor funds to the LookthroughTarget variant that
`build_snapshot` expects — `active_fund` for active CN equity, or a fund-level
kind (gold / qdii_global) for commodity and QDII profiles. The `provider_symbol`
is always the fund id, so look-through fetches NAV + announcements via the CN
endpoints and never touches the us_etf alias path.

Never produces `broad_index` — that kind refreshes the wrong domain (§9 spec).
"""
from __future__ import annotations

from irc.fundamentals.types import LookthroughTarget
from irc.monitor.types import MonitorFund

# analysis_profile → LookthroughKind.
# active_fund: full active-fund snapshot (filings + broker + NAV + announcements).
# gold: fund-level snapshot (NAV + announcements, commodity — no equity anchor).
# qdii_global: fund-level QDII snapshot (NAV + announcements, never us_etf alias).
_PROFILE_TO_KIND: dict[str, str] = {
    "active_cn_equity": "active_fund",
    "gold": "gold",
    "qdii_global": "qdii_global",
    "qdii_china_us_internet": "qdii_global",  # CN-registered index QDII → qdii_global path
}


def target_for_fund(fund: MonitorFund) -> LookthroughTarget:
    """Pure: monitor fund → typed LookthroughTarget (provider_symbol = fund_id)."""
    kind = _PROFILE_TO_KIND[fund.analysis_profile]
    return LookthroughTarget(
        kind=kind,
        key=f"fund_{fund.id}",
        display_cn=fund.name_cn,
        provider_symbol=fund.id,
    )
