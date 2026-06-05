from __future__ import annotations
from irc.spend.probes.base import BalanceProbe
from irc.spend.probes.deepseek import DeepSeekProbe
from irc.spend.probes.openrouter import OpenRouterProbe

PROBES: dict[str, BalanceProbe] = {
    "deepseek": DeepSeekProbe(),
    "openrouter": OpenRouterProbe(),
}
