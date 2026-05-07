from __future__ import annotations
from irc.schemas.overrides import OverridesConfig


def test_overrides_lists_default_empty():
    cfg = OverridesConfig.model_validate({"boost_list": [], "ban_list": []})
    assert cfg.boost_list == []
