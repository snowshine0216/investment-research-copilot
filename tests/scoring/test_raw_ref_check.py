from __future__ import annotations

from irc.scoring.raw_ref_check import reachability_rate


def test_reachability_all_present() -> None:
    refs = ("a", "b", "c")
    index = {"a", "b", "c"}
    assert reachability_rate(refs, index) == 1.0


def test_reachability_partial() -> None:
    assert reachability_rate(("a", "b", "c", "d"), {"a", "b"}) == 0.5


def test_reachability_empty_returns_one() -> None:
    assert reachability_rate((), set()) == 1.0
