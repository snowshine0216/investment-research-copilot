from __future__ import annotations

import ssl

import pytest
import requests

from irc.data.akshare_client import FundNotFound
from irc.observability.errors import classify_exception


@pytest.mark.parametrize(
    "exc,expected_category",
    [
        (ssl.SSLError("UNEXPECTED_EOF"), "ssl"),
        (requests.exceptions.SSLError("wrap_socket failed"), "ssl"),
        (requests.exceptions.ProxyError("proxy down"), "proxy"),
        (requests.exceptions.Timeout("read timed out"), "timeout"),
        (TimeoutError("op took too long"), "timeout"),
        (KeyError("data"), "data-key"),
        (KeyError("['最新规模'] not in index"), "schema"),
        (FundNotFound("002601"), "not-found"),
        (ValueError("empty NAV history"), "empty"),
        (ValueError("empty price history"), "empty"),
        (AttributeError("unrelated"), "other"),
        (RuntimeError("something else"), "other"),
    ],
)
def test_classify_exception_returns_expected_category(exc, expected_category):
    category, description = classify_exception(exc)
    assert category == expected_category
    assert isinstance(description, str)
    assert description  # non-empty


def test_classify_exception_falls_back_to_other_with_repr():
    class _MyError(Exception):
        pass

    category, description = classify_exception(_MyError("boom"))
    assert category == "other"
    assert "_MyError" in description
    assert "boom" in description


def test_classify_exception_data_key_takes_precedence_over_generic_keyerror():
    # KeyError('data') must classify as data-key, not other, even though the
    # 'other' fallback could match any exception.
    category, _ = classify_exception(KeyError("data"))
    assert category == "data-key"
