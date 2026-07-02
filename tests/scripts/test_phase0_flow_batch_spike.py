from __future__ import annotations

from scripts.phase0_flow_batch_spike import _normalize_proxy, _parse_ulist


def test_normalize_bare_host_port_gets_http_scheme():
    assert _normalize_proxy("42.51.40.10:16816") == "http://42.51.40.10:16816"


def test_normalize_already_schemed_is_unchanged():
    assert _normalize_proxy("http://h:1") == "http://h:1"


def test_normalize_blank_is_none():
    assert _normalize_proxy("") is None
    assert _normalize_proxy("   ") is None
    assert _normalize_proxy(None) is None


def test_parse_ulist_still_extracts_f12_to_f184():
    payload = {"data": {"diff": [{"f12": "600519", "f184": 4.86}]}}
    assert _parse_ulist(payload) == {"600519": 4.86}
