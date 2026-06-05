import os
import pytest
from irc.spend.probes.deepseek import DeepSeekProbe

pytestmark = pytest.mark.live_balance


def _skip_unless_live():
    if os.environ.get("IRC_RUN_LIVE_BALANCE") != "1":
        pytest.skip("set IRC_RUN_LIVE_BALANCE=1 to run live balance probes")


def test_deepseek_live_balance_returns_amount():
    _skip_unless_live()
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        pytest.skip("DEEPSEEK_API_KEY not set")
    r = DeepSeekProbe().probe(key)
    assert r.source == "api"
    assert r.amount is not None
    assert r.currency  # non-empty
