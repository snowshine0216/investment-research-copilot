from __future__ import annotations
import httpx
from irc.spend.probes.base import ProbeError, get_json_with_retry
from irc.spend.types import BalanceReading

_URL = "https://openrouter.ai/api/v1/credits"


class OpenRouterProbe:
    provider = "openrouter"

    def probe(self, api_key: str, *, client: httpx.Client | None = None) -> BalanceReading:
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        try:
            body = get_json_with_retry(_URL, headers=headers, client=client)
        except ProbeError:
            return BalanceReading(self.provider, currency="USD", amount=None,
                                  available=False, source="probe_failed")
        data = body.get("data", {})
        try:
            amount = float(data.get("total_credits", 0)) - float(data.get("total_usage", 0))
        except (TypeError, ValueError):
            amount = None
        return BalanceReading(self.provider, currency="USD", amount=amount,
                              available=amount is not None and amount > 0, source="api")
