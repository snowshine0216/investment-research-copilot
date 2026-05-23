"""Item 008 — publishable-set-lockdown integration sweep.

Locks the publishable-set citation / scope / state / asset-class invariants
at the artifact-read level after a full `run_opportunity` (plus `run_memo`
for cross-stage ACs) execution. After this file's tests pass on the feature
branch, item 009 can flip IRC_CITATION_ENFORCE_MODE=block against a
known-clean baseline.

Key invariants:
- Publishable citation universe (Q5 resolution): opportunity_report.json
  ∪ gold_regime.json. rejections.json EXCLUDED — RejectionRecord has no
  thesis_evidence field (src/irc/opportunity/rejection_log.py:35–47).
- Memo route mock pair (Q1 resolution): patch synthesizer.call_chat +
  auditor.call_chat per tests/commands/test_memo_cmd_aliases.py:98–99.
- QDII variants (Q3): one per variant — qdii_us, qdii_hk, qdii_global.
- _GAP_TO_REASON precedence (Q7): assert observable rejection_reason
  string, NEVER import the private constant.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import pytest
import yaml

from irc.llm._types import ChatResponse


# ─── Helpers ────────────────────────────────────────────────────────────────

def _resp(text: str) -> ChatResponse:
    """Locked ChatResponse factory per tests/commands/test_memo_cmd_aliases.py:13."""
    return ChatResponse(
        text=text, prompt_tokens=10, completion_tokens=20,
        latency_ms=50, raw={},
    )


def _today_cn() -> str:
    """Asia/Shanghai date matching opportunity_cmd.py's output-dir convention."""
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _sha256_file(path: Path) -> str:
    """Return hex-digest sha256 of the on-disk bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect_publishable_citation_universe(out_dir: Path) -> set[str]:
    """Q5 resolution: opportunity_report.json ∪ gold_regime.json.
    rejections.json EXCLUDED — RejectionRecord has no thesis_evidence field.
    """
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    universe: set[str] = set()
    for row in opp.get("rows", []):
        for ev in row.get("thesis_evidence", []):
            cid = ev.get("citation_id")
            if cid:
                universe.add(cid)
    gold_path = out_dir / "gold_regime.json"
    if gold_path.exists():
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        for ev in gold.get("evidence", []):
            cid = ev.get("citation_id")
            if cid:
                universe.add(cid)
    return universe


@contextmanager
def _patch_memo_routes(synth_text: str) -> Iterator[None]:
    """Q1 resolution: locked patch pair per test_memo_cmd_aliases.py:98–99."""
    with patch("irc.memo.synthesizer.call_chat",
               return_value=_resp(synth_text)), \
         patch("irc.memo.auditor.call_chat",
               return_value=_resp("审核通过")):
        yield


def _install_ak_call_dispatch(monkeypatch, dispatch: dict) -> Counter:
    """Patch `_ak_call` with a dispatcher; return a call counter for
    cache-freshness assertions (ACs 15–17 inspect it after run_opportunity).
    """
    counter: Counter = Counter()

    def _side(fn_name: str, *args, **kwargs):
        symbol = args[0] if args else kwargs.get("symbol", "")
        key = (fn_name, str(symbol))
        counter[key] += 1
        frame = dispatch.get(key)
        if frame is None:
            import pandas as pd
            return pd.DataFrame()
        return frame

    monkeypatch.setattr(
        "irc.fundamentals.akshare_fundamentals._ak_call", _side,
    )
    return counter


def _seed_publishable_set_repo(
    tmp_path: Path,
    *,
    monkeypatch,
    include_qdii: bool = True,
    asset_classes: tuple[str, ...] = (
        "cn_equity_fund", "cn_bond_fund", "gold", "cn_etf",
    ),
    seed_date: str | None = None,
    override_env: dict[str, str] | None = None,
) -> dict[tuple[str, str], Any]:
    """Bootstrap a tmp_path repo for publishable-set integration tests.

    Returns the (fn_name, symbol) → frame dispatch dict; callers may mutate
    it before installing via _install_ak_call_dispatch(monkeypatch, dispatch).

    Env vars set via monkeypatch (Q2 resolution):
      IRC_OPPORTUNITY_AUTOBUILD=1
      IRC_CACHE_FRESHNESS_DAYS=7
      IRC_FETCH_BUDGET=2000
      IRC_ALLOW_STALE=1

    `override_env` lets per-test scenarios change individual values
    (e.g. AC12 sets IRC_FETCH_BUDGET=1 to force exhaustion).
    """
    import pandas as pd
    from irc.commands.init_cmd import run_init
    from irc.data.manifest import ManifestEntry, write_manifest

    # Env vars (Q2 resolution).
    env = {
        "IRC_OPPORTUNITY_AUTOBUILD": "1",
        "IRC_CACHE_FRESHNESS_DAYS": "7",
        "IRC_FETCH_BUDGET": "2000",
        "IRC_ALLOW_STALE": "1",
    }
    if override_env:
        env.update(override_env)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # Repo scaffold.
    run_init(str(tmp_path), force=False)

    # Manifest (so ingest staleness gate passes).
    write_manifest(
        tmp_path / "data",
        ManifestEntry(
            source="akshare",
            last_run_at=datetime.now(timezone.utc).isoformat(),
            schema_version="v1",
            record_counts={"prices": 100},
        ),
    )

    today = seed_date or _today_cn()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    # Per-asset-class seed instruments (Q3: one per variant for QDII).
    v1_instruments = {
        "cn_equity_fund": [("005827", "易方达蓝筹精选")],
        "cn_bond_fund":   [("000001", "华夏成长债")],
        "gold":           [("518880", "黄金ETF")],
        "cn_etf":         [("510300", "沪深300ETF")],
    }
    qdii_instruments = [
        ("004243", "qdii_us",     "易方达原油"),
        ("164906", "qdii_hk",     "交银中证海外"),
        ("100061", "qdii_global", "富国全球债"),
    ]

    scoring_rows = []
    for ac in asset_classes:
        for iid, name in v1_instruments.get(ac, []):
            scoring_rows.append({
                "instrument_id": iid, "name_cn": name,
                "asset_class": ac, "composite_score": 70.0,
            })
    if include_qdii:
        for iid, ac, name in qdii_instruments:
            scoring_rows.append({
                "instrument_id": iid, "name_cn": name,
                "asset_class": ac, "composite_score": 50.0,
            })

    (out_dir / "scoring.json").write_text(
        json.dumps({"scores": scoring_rows}, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "gold_regime.json").write_text(
        json.dumps({
            "regime": "range_bound", "zone": "pause",
            "tilt": "neutral_minus", "evidence": [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "proposed_allocation.yaml").write_text(
        yaml.safe_dump({"gold_tilt": "overweight", "selected_instruments": []}),
        encoding="utf-8",
    )

    # Synthetic AkShare dispatch — minimal frames that look like real responses
    # so _build_active_fund_snapshot / _build_fund_level_snapshot don't bail.
    dispatch: dict[tuple[str, str], Any] = {}

    return dispatch


# ─── Smoke test ─────────────────────────────────────────────────────────────

def test_seed_helper_builds_runnable_repo(tmp_path, monkeypatch) -> None:
    """Task 1 smoke — the seed helper builds a repo whose `run_opportunity`
    invocation reaches a write phase without crashing on missing inputs.
    Does NOT assert any AC; the per-AC tests below cover the invariants."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    assert (out_dir / "opportunity_report.json").exists()
    assert (out_dir / "thesis_cards.yaml").exists()
    assert (out_dir / "discipline_report.md").exists()
    assert (out_dir / "rejections.json").exists()
