from __future__ import annotations

from irc.notify.health import HealthDigest, HealthItem, health_unknown


def test_digest_empty_has_no_warnings():
    assert HealthDigest().has_warnings is False
    assert HealthDigest().items == ()


def test_digest_has_warnings_true_when_any_warn():
    dg = HealthDigest((HealthItem("a", "info", "x"), HealthItem("b", "warn", "y")))
    assert dg.has_warnings is True


def test_digest_info_only_has_no_warnings():
    dg = HealthDigest((HealthItem("a", "info", "x"),))
    assert dg.has_warnings is False


def test_health_unknown_is_a_single_warn():
    dg = health_unknown()
    assert dg.has_warnings is True
    assert dg.items[0].code == "health_unknown"
    assert "health unknown" in dg.items[0].text


def test_items_are_frozen():
    import dataclasses
    import pytest

    item = HealthItem("a", "info", "x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.code = "b"  # type: ignore[misc]
