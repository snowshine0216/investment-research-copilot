from __future__ import annotations

import json
import logging

import pandas as pd
import pytest
import requests

from irc.fundamentals.legulegu_fetch import (
    LeguleguCooldownExhausted,
    _LEGULEGU_BACKOFF_S,
    _LEGULEGU_COOLDOWN_RETRIES,
    _LEGULEGU_COOLDOWN_S,
    _LEGULEGU_GAP_S,
    _LEGULEGU_NETWORK_ATTEMPTS,
    _is_network_transient,
    _is_throttle_signature,
    fetch_legulegu_frame,
)


# ---- constants are the locked judgment values ----

def test_constants_are_locked_judgment_values() -> None:
    assert _LEGULEGU_GAP_S == 4.0
    assert _LEGULEGU_NETWORK_ATTEMPTS == 3
    assert _LEGULEGU_BACKOFF_S == 3.0
    assert _LEGULEGU_COOLDOWN_S == 30.0
    assert _LEGULEGU_COOLDOWN_RETRIES == 1


# ---- throttle classifier ----

def test_missing_csrf_attribute_error_is_throttle() -> None:
    exc = AttributeError("'NoneType' object has no attribute 'attrs'")
    assert _is_throttle_signature(exc) is True


def test_stdlib_json_decode_error_is_throttle() -> None:
    exc = json.JSONDecodeError("Expecting value", "<html>", 0)
    assert _is_throttle_signature(exc) is True


def test_requests_json_decode_error_is_throttle() -> None:
    # requests 2.33.1 builds against simplejson, so requests.JSONDecodeError is
    # NOT a json.JSONDecodeError subclass — the classifier must match it explicitly.
    exc = requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0)
    assert _is_throttle_signature(exc) is True


def test_attribute_error_without_nonetype_is_fatal() -> None:
    # A genuine parser/schema change can also trip an AttributeError on .attrs,
    # but only the missing-CSRF surface carries BOTH 'NoneType' and 'attrs'.
    exc = AttributeError("widget has no attribute 'attrs'")
    assert _is_throttle_signature(exc) is False


def test_plain_value_error_is_fatal() -> None:
    assert _is_throttle_signature(ValueError("boom")) is False


def test_key_error_data_envelope_is_fatal() -> None:
    # documented blind spot (ADR 0014 D2/Q2b): a JSON error envelope raises
    # KeyError('data') and is deliberately FATAL, not throttle.
    assert _is_throttle_signature(KeyError("data")) is False


# ---- network classifier ----

def test_requests_connection_error_is_network() -> None:
    assert _is_network_transient(requests.exceptions.ConnectionError("reset")) is True


def test_requests_timeout_is_network() -> None:
    assert _is_network_transient(requests.exceptions.Timeout("slow")) is True


def test_builtin_connection_error_is_network() -> None:
    assert _is_network_transient(ConnectionError("reset")) is True


def test_value_error_is_not_network() -> None:
    assert _is_network_transient(ValueError("nope")) is False


# ---- fetch_legulegu_frame sleep sequences (the heart of the spec) ----

class _Recorder:
    """Records the args fed to the injected fake _sleep."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _patch_sleep(monkeypatch, recorder: _Recorder) -> None:
    monkeypatch.setattr("irc.fundamentals.legulegu_fetch._sleep", recorder)


_FRAME = pd.DataFrame({"日期": ["2026-06-08"], "滚动市盈率": [12.1]})


def test_network_success_on_third_attempt(monkeypatch) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)
    calls = {"n": 0}

    def ak_call(fn_name, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.exceptions.ConnectionError("reset")
        return _FRAME

    out = fetch_legulegu_frame(ak_call, "stock_index_pe_lg", "沪深300")
    assert out is _FRAME
    # GAP before each attempt; backoff 3 then 6 between the 3 attempts.
    assert rec.sleeps == [4.0, 3.0, 4.0, 6.0, 4.0]


def test_network_exhausts_returns_none(monkeypatch, caplog) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)

    def ak_call(fn_name, **kwargs):
        raise requests.exceptions.ConnectionError("reset")

    with caplog.at_level(logging.WARNING):
        out = fetch_legulegu_frame(ak_call, "stock_index_pe_lg", "沪深300")
    assert out is None
    assert rec.sleeps == [4.0, 3.0, 4.0, 6.0, 4.0]  # 3 attempts, 2 backoffs
    assert sum(1 for r in caplog.records if r.levelno == logging.WARNING) == 1


def test_throttle_success_on_retry(monkeypatch) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)
    calls = {"n": 0}

    def ak_call(fn_name, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise AttributeError("'NoneType' object has no attribute 'attrs'")
        return _FRAME

    out = fetch_legulegu_frame(ak_call, "stock_index_pe_lg", "沪深300")
    assert out is _FRAME
    assert rec.sleeps == [4.0, 30.0, 4.0]  # GAP, cooldown, GAP-before-retry


def test_throttle_exhausts_raises(monkeypatch) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)
    calls = {"n": 0}

    def ak_call(fn_name, **kwargs):
        calls["n"] += 1
        raise AttributeError("'NoneType' object has no attribute 'attrs'")

    with pytest.raises(LeguleguCooldownExhausted):
        fetch_legulegu_frame(ak_call, "stock_index_pe_lg", "沪深300")
    assert calls["n"] == 2  # initial + one cooldown retry, then suspend
    assert rec.sleeps == [4.0, 30.0, 4.0]  # no second cooldown wait


def test_success_non_dataframe_returns_empty_frame(monkeypatch) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)

    out = fetch_legulegu_frame(lambda fn, **kw: "not a frame", "stock_index_pe_lg", "沪深300")
    assert isinstance(out, pd.DataFrame)
    assert out.empty
    assert rec.sleeps == [4.0]  # one GAP, one attempt


def test_fatal_error_returns_none_no_retry(monkeypatch, caplog) -> None:
    rec = _Recorder()
    _patch_sleep(monkeypatch, rec)

    def ak_call(fn_name, **kwargs):
        raise KeyError("data")  # documented blind spot → fatal

    with caplog.at_level(logging.WARNING):
        out = fetch_legulegu_frame(ak_call, "stock_index_pe_lg", "沪深300")
    assert out is None
    assert rec.sleeps == [4.0]  # one GAP, one attempt, no retry
    assert sum(1 for r in caplog.records if r.levelno == logging.WARNING) == 1
