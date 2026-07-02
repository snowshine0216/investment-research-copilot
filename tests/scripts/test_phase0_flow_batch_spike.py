from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

from scripts.phase0_flow_batch_spike import (
    _normalize_proxy,
    _parse_ulist,
    _resolve_cn_proxy_for_spike,
    equiv,
)


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


# ── _resolve_cn_proxy_for_spike ──────────────────────────────────────────────
def test_resolve_cn_proxy_env_var_set_returns_normalized(tmp_path, monkeypatch):
    monkeypatch.setenv("IRC_CN_PROXY", "42.51.40.10:16816")
    assert _resolve_cn_proxy_for_spike(tmp_path) == "http://42.51.40.10:16816"


def test_resolve_cn_proxy_env_unset_falls_back_to_root_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("IRC_CN_PROXY", raising=False)
    (tmp_path / ".env").write_text("SOME_OTHER=1\nIRC_CN_PROXY=9.9.9.9:8080\n", encoding="utf-8")
    assert _resolve_cn_proxy_for_spike(tmp_path) == "http://9.9.9.9:8080"


def test_resolve_cn_proxy_neither_env_nor_env_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.delenv("IRC_CN_PROXY", raising=False)
    # no .env written under tmp_path
    assert _resolve_cn_proxy_for_spike(tmp_path) is None


def test_resolve_cn_proxy_is_root_relative_not_cwd_relative(tmp_path, monkeypatch):
    """A .env in the real CWD must NOT leak into a root-relative resolve call."""
    monkeypatch.delenv("IRC_CN_PROXY", raising=False)
    other_root = tmp_path / "root_without_env"
    other_root.mkdir()
    # Simulate a decoy .env sitting in the process CWD (not under other_root).
    decoy_cwd = tmp_path / "decoy_cwd"
    decoy_cwd.mkdir()
    (decoy_cwd / ".env").write_text("IRC_CN_PROXY=1.2.3.4:9\n", encoding="utf-8")
    monkeypatch.chdir(decoy_cwd)
    assert _resolve_cn_proxy_for_spike(other_root) is None


# ── equiv() loop-restructuring regression guard ─────────────────────────────
class _RecordingCtx:
    """Stub context manager that records how many times it is entered/exited,
    to guard against per-iteration re-entry of a single instance (the bug the
    proxy_env-around-the-loop fix addresses)."""

    def __init__(self):
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return None

    def __exit__(self, *exc_info):
        self.exit_count += 1
        return False


def test_equiv_enters_proxy_context_exactly_once_for_multiple_symbols(tmp_path, monkeypatch):
    prior = tmp_path / "prior.json"
    prior.write_text(
        '{"run_date": "2026-07-01", "by_symbol": '
        '{"600519": 1.23, "000651": 2.34, "600690": 3.45}}',
        encoding="utf-8",
    )

    recording_ctx = _RecordingCtx()

    fake_http_proxy = types.ModuleType("irc.http_proxy")
    fake_http_proxy.proxy_env = lambda proxy: recording_ctx
    monkeypatch.setitem(sys.modules, "irc.http_proxy", fake_http_proxy)

    fake_ak = MagicMock()
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    # Force ABSENT-match branch (not the exception path) for each symbol so the
    # loop runs to completion across all 3 candidates without hitting the
    # (deliberately network-forbidding) fund-flow mock's exception.
    import pandas as pd

    empty_df = pd.DataFrame(columns=["日期", "主力净流入-净占比"])
    fake_ak.stock_individual_fund_flow.return_value = empty_df

    rc = equiv(prior, n=3, proxy="http://1.2.3.4:80")

    assert rc == 1  # INCONCLUSIVE: no overlapping completed-day rows in the stub data
    assert fake_ak.stock_individual_fund_flow.call_count == 3
    assert recording_ctx.enter_count == 1
    assert recording_ctx.exit_count == 1
