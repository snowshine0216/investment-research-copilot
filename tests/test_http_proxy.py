from __future__ import annotations

import os

import pytest

from irc.http_proxy import proxy_env, resolve_cn_proxy

_URL = "IRC_CN_PROXY"
_MODE = "IRC_CN_PROXY_MODE"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(_URL, raising=False)
    monkeypatch.delenv(_MODE, raising=False)


def test_unset_is_none():
    assert resolve_cn_proxy() is None


def test_bare_host_port_gets_http_scheme(monkeypatch):
    monkeypatch.setenv(_URL, "42.51.40.10:16816")
    assert resolve_cn_proxy() == "http://42.51.40.10:16816"


def test_already_schemed_url_unchanged(monkeypatch):
    monkeypatch.setenv(_URL, "http://h:1")
    assert resolve_cn_proxy() == "http://h:1"


def test_blank_is_none(monkeypatch):
    monkeypatch.setenv(_URL, "   ")
    assert resolve_cn_proxy() is None


def test_mode_off_disables_even_when_url_present(monkeypatch):
    monkeypatch.setenv(_URL, "h:1")
    monkeypatch.setenv(_MODE, "off")
    assert resolve_cn_proxy() is None


def test_mode_on_is_default(monkeypatch):
    monkeypatch.setenv(_URL, "h:1")
    assert resolve_cn_proxy() == "http://h:1"


def test_mode_garbage_value_fails_open_to_on(monkeypatch):
    monkeypatch.setenv(_URL, "h:1")
    monkeypatch.setenv(_MODE, "garbage")
    assert resolve_cn_proxy() == "http://h:1"


def test_proxy_env_none_is_noop(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "orig")
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    with proxy_env(None):
        assert os.environ["HTTPS_PROXY"] == "orig"
        assert "HTTP_PROXY" not in os.environ
    assert os.environ["HTTPS_PROXY"] == "orig"
    assert "HTTP_PROXY" not in os.environ


def test_proxy_env_sets_and_restores(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "orig")
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    with proxy_env("http://p:9"):
        assert os.environ["HTTP_PROXY"] == "http://p:9"
        assert os.environ["HTTPS_PROXY"] == "http://p:9"
        assert os.environ["http_proxy"] == "http://p:9"
    assert os.environ["HTTPS_PROXY"] == "orig"       # restored
    assert "HTTP_PROXY" not in os.environ            # restored to absent
