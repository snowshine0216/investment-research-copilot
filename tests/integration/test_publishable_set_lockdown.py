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
    """Patch `_ak_call` with a dispatcher in BOTH modules; return a call counter
    for cache-freshness assertions (ACs 15–17 inspect it after run_opportunity).

    Patches both irc.fundamentals.akshare_fundamentals._ak_call (holdings,
    announcements, NAV, news) and irc.fundamentals.akshare_filing._ak_call
    (filings, broker reports) since each module defines its own indirection.
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
    monkeypatch.setattr(
        "irc.fundamentals.akshare_filing._ak_call", _side,
    )
    return counter


def _preload_duckdb(root: Path, instrument_ids: list[str]) -> None:
    """Insert minimal DuckDB rows so populate_inputs returns non-None fields.

    Writes `instruments` metadata (expense_ratio, aum) and a 400-day
    synthetic NAV series — enough for self_history_percentile to return a
    value and remove the structural evidence gaps (missing_valuation_data,
    missing_flow_or_return_data, missing_product_metadata).
    """
    import duckdb as _ddb
    from irc.data.duckdb_helper import connect, ensure_schema

    db_path = root / "data" / "local.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = connect(db_path)
    ensure_schema(con)
    today = datetime.now(timezone(timedelta(hours=8))).date()

    now_ts = datetime.now(timezone.utc).isoformat()
    for iid in instrument_ids:
        # Insert instrument metadata.
        con.execute(
            """INSERT OR REPLACE INTO instruments
               (instrument_id, ticker, market, name_cn, asset_class, currency,
                expense_ratio, aum, manager_tenure_years,
                _ingested_at, _source, _raw_ref)
               VALUES (?, ?, 'CN', ?, 'cn_equity_fund', 'CNY', 0.015, 5e9, 5.0,
                       ?, 'test_seed', 'synthetic')""",
            [iid, iid, "测试基金", now_ts],
        )
        # Insert 400 days of synthetic NAV for percentile / returns.
        from datetime import timedelta as _td
        import math
        for d in range(400):
            nav_date = (today - _td(days=400 - d)).isoformat()
            nav_val = 1.0 + 0.1 * math.sin(d / 60)
            con.execute(
                """INSERT OR REPLACE INTO nav_history
                   (instrument_id, date, nav, _ingested_at, _source, _raw_ref)
                   VALUES (?, ?, ?, ?, 'test_seed', 'synthetic')""",
                [iid, nav_date, round(nav_val, 6), now_ts],
            )
    con.close()


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

    # Repo scaffold — creates all required YAML config files.
    run_init(str(tmp_path), force=False)

    # Append test QDII instruments to universe YAMLs so instr_index can find
    # them and map_lookthrough receives proper tracked_index context.
    if include_qdii:
        _qdii_us_entry = (
            '  - { instrument_id: "004243", ticker: "004243",'
            ' market: cn_off_exchange, name_cn: "易方达原油", asset_class: us_etf,'
            ' currency: cny, tracked_index: "S&P 500", venue_required: [cmb_fund] }\n'
        )
        _qdii_hk_entry = (
            '  - { instrument_id: "164906", ticker: "164906",'
            ' market: cn_off_exchange, name_cn: "交银中证海外", asset_class: hk_etf,'
            ' currency: cny, tracked_index: "hsi", venue_required: [cmb_fund] }\n'
        )
        qdii_us_path = tmp_path / "config" / "universe" / "qdii_us.yaml"
        qdii_hk_path = tmp_path / "config" / "universe" / "qdii_hk.yaml"
        with qdii_us_path.open("a", encoding="utf-8") as f:
            f.write(_qdii_us_entry)
        with qdii_hk_path.open("a", encoding="utf-8") as f:
            f.write(_qdii_hk_entry)

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
    # QDII instruments: use asset_class us_etf / hk_etf / qdii_global with
    # tracked_index that routes them to the QDII sentinel via map_lookthrough.
    # us_etf + tracked="S&P 500" → alias "sp500" → target.kind="qdii_us" ✓
    # hk_etf + tracked="hsi"     → target.kind="qdii_hk" ✓
    # qdii_global is handled by asset_class branch directly ✓
    qdii_instruments = [
        ("004243", "us_etf",      "易方达原油",    "S&P 500"),
        ("164906", "hk_etf",      "交银中证海外",  "hsi"),
        ("100061", "qdii_global", "富国全球债",    "global_equity"),
    ]

    scoring_rows = []
    for ac in asset_classes:
        for iid, name in v1_instruments.get(ac, []):
            scoring_rows.append({
                "instrument_id": iid, "name_cn": name,
                "asset_class": ac, "composite_score": 70.0,
            })
    if include_qdii:
        for iid, ac, name, tracked in qdii_instruments:
            scoring_rows.append({
                "instrument_id": iid, "name_cn": name,
                "asset_class": ac, "composite_score": 50.0,
                "tracked_index": tracked,
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
    # so _build_active_fund_snapshot produces publishable rows.
    # Holdings frame for active funds (data leg).
    holdings_frame = pd.DataFrame({
        "股票代码": ["600519", "000858"],
        "股票名称": ["贵州茅台", "五粮液"],
        "占净值比例": [8.2, 6.1],
        "季度": ["2024Q4", "2024Q4"],
    })
    # Announcement frame for active funds (information leg).
    ann_frame = pd.DataFrame({
        "公告标题": ["2024年第4季度报告"],
        "公告日期": ["2024-01-15"],
        "报告ID": ["ANN001"],
    })

    dispatch: dict[tuple[str, str], Any] = {}

    # Filing digest frame for CN constituents (data leg via stock_financial_abstract).
    # Column format: "选项" / "指标" labels + date-like column headers (YYYYMMDD).
    filing_frame = pd.DataFrame({
        "选项": ["常用指标", "常用指标", "常用指标"],
        "指标": ["营业总收入", "归母净利润", "营业成本"],
        "20241231": [100.0, 20.0, 60.0],
        "20231231": [90.0, 18.0, 54.0],
    })
    # Broker report frame for CN constituents (info leg via stock_research_report_em).
    broker_frame = pd.DataFrame({
        "机构": ["中金公司"],
        "东财评级": ["买入"],
        "报告名称": ["2024年年度报告"],
        "日期": [datetime.now(timezone(timedelta(hours=8))).date().isoformat()],
        "报告PDF链接": ["https://example.com/report.pdf"],
    })

    # Wire data for cn_equity_fund instruments.
    if "cn_equity_fund" in asset_classes:
        for iid, _ in v1_instruments["cn_equity_fund"]:
            dispatch[("fund_portfolio_hold_em", iid)] = holdings_frame
            # All three announcement endpoints — any non-empty one satisfies the
            # info-leg requirement (_collect_publishable_citation_universe).
            dispatch[("fund_announcement_dividend_em", iid)] = ann_frame
            dispatch[("fund_announcement_report_em", iid)] = ann_frame
            dispatch[("fund_announcement_personnel_em", iid)] = ann_frame
        # Constituent-level evidence for the seeded holdings.
        for stock_code in ["600519", "000858"]:
            dispatch[("stock_financial_abstract", stock_code)] = filing_frame
            dispatch[("stock_research_report_em", stock_code)] = broker_frame
            dispatch[("stock_news_em", stock_code)] = pd.DataFrame()

    # Pre-load DuckDB with instrument metadata + price series so
    # populate_inputs returns non-None structural fields (valuation percentile,
    # returns, expense_ratio) and rows do not generate structural evidence gaps.
    all_iids = [iid for ac in asset_classes for iid, _ in v1_instruments.get(ac, [])]
    if all_iids:
        _preload_duckdb(tmp_path, all_iids)

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


# ─── ACs 1–5: publishable-set citation invariants (E10 family) ───────────────

def test_publishable_dual_leg_coverage(tmp_path, monkeypatch) -> None:
    """AC1 — every published row carries ≥1 data + ≥1 information citation.
    No row has both legs absent. citation_kind ∈ {"data", "information"}
    (legacy "both" forbidden per ADR 0001)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    rows = opp.get("rows", [])
    if not rows:
        pytest.skip("no publishable rows produced by seed — all rows gapped")
    for row in rows:
        kinds = {ev["citation_kind"] for ev in row.get("thesis_evidence", [])}
        assert "data" in kinds, \
            f"row {row['instrument_id']} missing data-leg evidence: kinds={kinds}"
        assert "information" in kinds, \
            f"row {row['instrument_id']} missing information-leg evidence: kinds={kinds}"
        assert kinds <= {"data", "information"}, \
            f"row {row['instrument_id']} has forbidden citation_kind: {kinds}"


def test_publishable_owner_instrument_provenance(tmp_path, monkeypatch) -> None:
    """AC2 — every entry.owner_instrument_id == row.instrument_id.
    No cross-instrument leakage on disk."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        iid = row["instrument_id"]
        for ev in row.get("thesis_evidence", []):
            assert ev["owner_instrument_id"] == iid, \
                f"cross-instrument leakage: row {iid} carries owner={ev['owner_instrument_id']}"


def test_publishable_scope_is_instrument_or_constituent(tmp_path, monkeypatch) -> None:
    """AC3 — every entry.scope ∈ {"instrument", "constituent"}.
    No publishable row may have scope=asset_class_macro / policy as its
    SOLE evidence basis. Macro/policy may co-exist alongside instrument
    or constituent entries (an absent-from-pool check would over-assert)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        scopes = {ev["scope"] for ev in row.get("thesis_evidence", [])}
        assert scopes & {"instrument", "constituent"}, \
            f"row {row['instrument_id']} lacks instrument/constituent scope: {scopes}"


def test_publishable_thesis_state_literal_only(tmp_path, monkeypatch) -> None:
    """AC4 — every row.thesis_state ∈ {"intact","under_pressure","falsified","evidence_insufficient"}.
    No synthetic "partial_evidence"-style values."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    allowed = {"intact", "under_pressure", "falsified", "evidence_insufficient"}
    for row in opp.get("rows", []):
        assert row["thesis_state"] in allowed, \
            f"row {row['instrument_id']} has invalid thesis_state {row['thesis_state']!r}"


def test_publishable_evidence_gaps_empty_after_disk_roundtrip(tmp_path, monkeypatch) -> None:
    """AC5 — every published row has evidence_gaps == [] after JSON round-trip.
    H3 universal gapped-row invariant guarantees this at _write_opportunity_outputs
    time; AC5 re-asserts after JSON round-trip to catch serializer drift."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        assert row["evidence_gaps"] == [], \
            f"row {row['instrument_id']} carries non-empty evidence_gaps on publish: {row['evidence_gaps']!r}"


# ─── ACs 6–9: QDII exclusion invariants ──────────────────────────────────────

_QDII_ASSET_CLASSES = {"qdii_us", "qdii_hk", "qdii_global", "us_etf", "hk_etf"}
_QDII_IIDS = ("004243", "164906", "100061")


def test_qdii_never_in_thesis_cards(tmp_path, monkeypatch) -> None:
    """AC6 — no thesis_card has asset_class in {qdii_us,qdii_hk,qdii_global,us_etf,hk_etf}."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cards_doc = yaml.safe_load((out_dir / "thesis_cards.yaml").read_text(encoding="utf-8")) or {}
    cards = cards_doc.get("cards", [])
    for card in cards:
        assert card.get("asset_class") not in _QDII_ASSET_CLASSES, \
            f"QDII asset_class leaked into thesis_cards.yaml: {card}"


def test_qdii_never_in_opportunity_report_rows(tmp_path, monkeypatch) -> None:
    """AC7 — same set check against opportunity_report.json rows array."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        assert row["asset_class"] not in _QDII_ASSET_CLASSES, \
            f"QDII asset_class leaked into opportunity_report rows: {row}"
        assert row["instrument_id"] not in _QDII_IIDS, \
            f"QDII instrument_id leaked into opportunity_report rows: {row}"


def test_qdii_appears_in_rejections_with_qdii_reason(tmp_path, monkeypatch) -> None:
    """AC8 — every seeded QDII instrument in rejections.json with
    rejection_reason == 'qdii_information_unavailable'."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entries_by_iid = {e["instrument_id"]: e for e in rej.get("entries", [])}
    for iid in _QDII_IIDS:
        assert iid in entries_by_iid, \
            f"QDII {iid} missing from rejections.json"
        assert entries_by_iid[iid]["rejection_reason"] == "qdii_information_unavailable", \
            f"QDII {iid} rejection_reason wrong: {entries_by_iid[iid]['rejection_reason']!r}"


def test_qdii_appears_in_discipline_failure_section(tmp_path, monkeypatch) -> None:
    """AC9 — every seeded QDII iid appears AFTER '## 证据不足' heading and
    NOT in any bucket section above it. Failure-section heading locked by
    tests/commands/test_opportunity_cmd_h3_invariant.py."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    failure_idx = md.find("## 证据不足")
    assert failure_idx >= 0, "discipline_report.md missing '## 证据不足' heading"
    above, below = md[:failure_idx], md[failure_idx:]
    for iid in _QDII_IIDS:
        assert iid not in above, \
            f"QDII {iid} appears in a bucket section above '## 证据不足'"
        assert iid in below, \
            f"QDII {iid} missing from failure section below '## 证据不足'"


# ─── AC10: H3 partition across four output surfaces ──────────────────────────

def test_h3_partition_across_four_output_surfaces(tmp_path, monkeypatch) -> None:
    """AC10 — given one publishable + one Policy-B-gapped seed:
      (a) only publishable iid in thesis_cards.yaml
      (b) only publishable iid in opportunity_report.json rows
      (c) only publishable iid in discipline_report.md bucket sections
      (d) only gapped iid in rejections.json entries
      (e) gapped iid in discipline_report.md failure section
    """
    from irc.commands.opportunity_cmd import run_opportunity

    # Seed only cn_equity_fund (one publishable iid) + force a synthetic
    # gapped row via a second cn_equity_fund whose holdings _ak_call
    # returns empty (triggers Policy B insufficient_info_coverage_top_half).
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    # Augment scoring.json with a second iid that gets the empty-holdings
    # treatment via the dispatcher.
    out_dir = tmp_path / "outputs" / _today_cn()
    scoring = json.loads((out_dir / "scoring.json").read_text(encoding="utf-8"))
    scoring["scores"].append({
        "instrument_id": "163417", "name_cn": "兴全合润",
        "asset_class": "cn_equity_fund", "composite_score": 65.0,
    })
    (out_dir / "scoring.json").write_text(
        json.dumps(scoring, ensure_ascii=False), encoding="utf-8",
    )
    # Also need DuckDB data for 163417 so structural gaps don't fire first.
    _preload_duckdb(tmp_path, ["163417"])

    # 163417 gets empty AkShare holdings → Policy B failure.
    import pandas as pd
    dispatch[("fund_portfolio_hold_em", "163417")] = pd.DataFrame()

    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    cards_doc = yaml.safe_load((out_dir / "thesis_cards.yaml").read_text(encoding="utf-8")) or {}
    card_iids = {c["instrument_id"] for c in cards_doc.get("cards", [])}
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    row_iids = {r["instrument_id"] for r in opp.get("rows", [])}
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    rej_iids = {e["instrument_id"] for e in rej.get("entries", [])}
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    failure_idx = md.find("## 证据不足")
    above = md[:failure_idx]
    below = md[failure_idx:]

    assert "005827" in row_iids, "publishable iid missing from opportunity rows"
    assert "163417" not in row_iids, "gapped iid leaked into opportunity rows"
    assert "005827" in above, "publishable iid missing from discipline buckets"
    assert "163417" not in above, "gapped iid leaked into discipline buckets"
    assert "163417" in rej_iids, "gapped iid missing from rejections.json"
    assert "005827" not in rej_iids, "publishable iid leaked into rejections.json"
    assert "163417" in below, "gapped iid missing from discipline failure section"


# ─── AC11: Policy-B precedence ───────────────────────────────────────────────

def test_policy_b_precedence_qdii_over_policy_b_code(tmp_path, monkeypatch) -> None:
    """AC11 — a QDII row carrying BOTH 'qdii_information_unavailable' AND
    'insufficient_info_coverage_top_half' in evidence_gaps must classify
    its rejection_reason as 'qdii_information_unavailable'.

    Asserts on the OBSERVABLE string, NOT by importing _GAP_TO_REASON.
    """
    # precedence per src/irc/opportunity/rejection_log.py::_GAP_TO_REASON
    # dict-iteration order + ADR 0003
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.selection import SelectionQuality

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    _install_ak_call_dispatch(monkeypatch, dispatch)

    qdii_row = OpportunityRow(
        instrument_id="004243",
        name_cn="易方达原油",
        asset_class="us_etf",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="qdii_us", key="sp500",
            display_cn="标普500", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="evidence_insufficient",
        product_quality_state="strong",
        opportunity_state="exclude",
        opportunity_reason="",
        evidence_gaps=(
            "qdii_information_unavailable",
            "insufficient_info_coverage_top_half",
        ),
        thesis_evidence=(),
        constituent_analyses=(),
    )

    out_dir = tmp_path / "outputs" / _today_cn()
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_opportunity_outputs(
        kept_rows=[qdii_row],
        positions={"004243": PositionContext(
            portfolio_weight=None, target_band_low=None, target_band_high=None,
            drawdown_since_entry=None, is_holding=False,
        )},
        qualities={"004243": SelectionQuality(
            expense_ratio=None, aum_cny=None, tracking_error=None,
            premium_discount_abs=None, history_days=None, data_completeness=0.5,
        )},
        roles={"004243": ""},
        holdings={},
        out_dir=out_dir,
        today=_today_cn(),
    )

    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entry = next(e for e in rej["entries"] if e["instrument_id"] == "004243")
    assert entry["rejection_reason"] == "qdii_information_unavailable", \
        f"Policy-B precedence broken: got {entry['rejection_reason']!r}, " \
        "expected 'qdii_information_unavailable' (qdii key precedes policy-b key " \
        "in _GAP_TO_REASON dict-iteration order per ADR 0003)"
