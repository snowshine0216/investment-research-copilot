"""Gold tilt combination: regime × drivers (item 006, 2026-05-19).

Adversarial review §B2: the gold engine advertises a 6-driver model in
the spec but the previous output was tilt=neutral with WGC drivers at
zero-fallback. _combine_tilts now produces a deterministic combined
verdict from regime + driver-score tilt + drivers_availability.
"""
from __future__ import annotations

import pytest

from irc.commands.gold_cmd import _combine_tilts


def test_complete_drivers_drives_tilt_when_regime_neutral() -> None:
    assert _combine_tilts("range_bound", "overweight", "complete") == "overweight"
    assert _combine_tilts("range_bound", "neutral_plus", "complete") == "neutral_plus"
    assert _combine_tilts("trending_up", "overweight", "complete") == "overweight"


def test_complete_drivers_clamps_overweight_into_downtrend() -> None:
    """Drivers say overweight + price trending down → clamp to neutral_plus."""
    assert _combine_tilts("trending_down", "overweight", "complete") == "neutral_plus"


def test_complete_drivers_passthrough_for_non_overweight() -> None:
    """The clamp only fires for the extreme overweight case."""
    assert _combine_tilts("trending_down", "neutral_plus", "complete") == "neutral_plus"
    assert _combine_tilts("trending_down", "underweight", "complete") == "underweight"


def test_partial_drivers_takes_cautious_path() -> None:
    """With partial data, never go above neutral_plus."""
    assert _combine_tilts("range_bound", "overweight", "partial") == "neutral_plus"
    assert _combine_tilts("range_bound", "neutral_plus", "partial") == "neutral_plus"
    # But conservative passes through when drivers already cautious:
    assert _combine_tilts("range_bound", "neutral", "partial") == "neutral"
    assert _combine_tilts("range_bound", "underweight", "partial") == "underweight"


def test_unavailable_drivers_fall_back_to_neutral() -> None:
    """No driver signal → honest neutral, regardless of regime."""
    assert _combine_tilts("range_bound", "overweight", "unavailable") == "neutral"
    assert _combine_tilts("trending_down", "overweight", "unavailable") == "neutral"
    assert _combine_tilts("trending_up", "overweight", "unavailable") == "neutral"
