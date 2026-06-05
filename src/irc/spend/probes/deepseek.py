from __future__ import annotations
import httpx
from irc.spend.probes.base import ProbeError, get_json_with_retry
from irc.spend.types import BalanceReading

_URL = "https://api.deepseek.com/user/balance"


class DeepSeekProbe:
    provider = "deepseek"

    def probe(self, api_key: str, *, client: httpx.Client | None = None) -> BalanceReading:
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        try:
            body = get_json_with_retry(_URL, headers=headers, client=client)
        except ProbeError:
            return BalanceReading(self.provider, currency="CNY", amount=None,
                                  available=False, source="probe_failed")
        infos = body.get("balance_infos") or [{}]
        info = infos[0]
        currency = info.get("currency", "CNY")
        try:
            amount = float(info.get("total_balance"))
        except (TypeError, ValueError):
            amount = None
        return BalanceReading(self.provider, currency=currency, amount=amount,
                              available=bool(body.get("is_available", False)), source="api")
