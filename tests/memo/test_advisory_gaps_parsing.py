"""JSON deserialization validation for opportunity_report.json `advisory_gaps`.

P1.SF.1 fix: silent coalescing of JSON null + missing type validation can
turn a malformed advisory_gaps field into `()` without any signal, silently
dropping a pickability advisory. Validate at the boundary.
"""
from __future__ import annotations

import pytest


def test_parse_advisory_gaps_none_returns_empty():
    from irc.commands.memo_cmd import _parse_advisory_gaps
    assert _parse_advisory_gaps(None, instrument_id="005827") == ()


def test_parse_advisory_gaps_empty_list_returns_empty():
    from irc.commands.memo_cmd import _parse_advisory_gaps
    assert _parse_advisory_gaps([], instrument_id="005827") == ()


def test_parse_advisory_gaps_single_code_round_trips():
    from irc.commands.memo_cmd import _parse_advisory_gaps
    assert _parse_advisory_gaps(
        ["top_holdings_broker_thin"], instrument_id="005827",
    ) == ("top_holdings_broker_thin",)


def test_parse_advisory_gaps_string_value_raises_with_instrument_id():
    from irc.commands.memo_cmd import _parse_advisory_gaps
    with pytest.raises(ValueError, match="005827"):
        _parse_advisory_gaps("top_holdings_broker_thin", instrument_id="005827")


def test_parse_advisory_gaps_dict_value_raises():
    from irc.commands.memo_cmd import _parse_advisory_gaps
    with pytest.raises(ValueError, match="advisory_gaps"):
        _parse_advisory_gaps({"foo": "bar"}, instrument_id="005827")


def test_parse_advisory_gaps_int_value_raises():
    from irc.commands.memo_cmd import _parse_advisory_gaps
    with pytest.raises(ValueError, match="005827"):
        _parse_advisory_gaps(42, instrument_id="005827")


def test_parse_advisory_gaps_list_with_non_string_raises():
    from irc.commands.memo_cmd import _parse_advisory_gaps
    with pytest.raises(ValueError, match="005827"):
        _parse_advisory_gaps([42, "top_holdings_broker_thin"], instrument_id="005827")
