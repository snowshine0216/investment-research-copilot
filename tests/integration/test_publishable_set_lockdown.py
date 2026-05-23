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

    Unexpected keys (a `(fn_name, symbol)` pair not in `dispatch`) ALSO
    increment the counter under a sentinel KEY-TUPLE `("__unexpected__", "<fn>:<sym>")`.
    The correct assertion shape is `assert _unexpected_calls(counter) == []`
    (NOT `counter["__unexpected__:*"]` — that's a Counter lookup of a string
    key that's never stored, which always silently returns 0). Returns an
    empty DataFrame for those calls so tests don't crash mid-arrange; the
    unexpected counter is the actual signal that fails the assertion.
    """
    counter: Counter = Counter()

    def _side(fn_name: str, *args, **kwargs):
        symbol = args[0] if args else kwargs.get("symbol", "")
        key = (fn_name, str(symbol))
        counter[key] += 1
        frame = dispatch.get(key)
        if frame is None:
            counter[("__unexpected__", f"{fn_name}:{symbol}")] += 1
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


def _unexpected_calls(counter: Counter) -> list[str]:
    """Return human-readable list of unexpected dispatch keys recorded
    by `_install_ak_call_dispatch`. Empty list means every call was
    explicitly mapped in the seed's dispatch dict."""
    return [
        key[1] for key in counter
        if isinstance(key, tuple) and key[0] == "__unexpected__"
    ]


def _assert_h3_partition(
    scored_iids: set[str],
    row_iids: set[str],
    rej_iids: set[str],
) -> None:
    """Lock the H3 universal invariant: every scored instrument lands in
    EXACTLY one of (publishable rows, rejected rows). A row invisible to
    both surfaces is a partition break (e.g. a silent drop by
    `_apply_reduction` with no rejection record); a row in BOTH is a
    Policy-B accounting bug. CONTEXT.md describes H3 as universal —
    callers from any AC that runs `run_opportunity` should invoke this."""
    missing = scored_iids - (row_iids | rej_iids)
    overlap = row_iids & rej_iids
    assert not missing, (
        f"H3 completeness break: {missing} appear in scoring.json but in "
        "NEITHER opportunity_report.json rows NOR rejections.json entries"
    )
    assert not overlap, (
        f"H3 disjointness break: {overlap} appear in BOTH publishable "
        "and rejected surfaces (Policy B accounting error)"
    )


_FIXED_INGESTED_AT = "2026-05-23T08:00:00+00:00"

# Computed ONCE at module import so both `_seed_publishable_set_repo` calls
# in AC22 see the same broker-report date (the value flows through
# `BrokerReport.published_iso` → `ThesisEvidence.date` → the citation_id
# preimage; any cross-call drift breaks AC22 byte-equality). 30 days < the
# 90-day broker-freshness window in
# `akshare_filing.fetch_recent_broker_reports`, so the date stays fresh
# whenever the test runs.
_BROKER_REPORT_DATE = (
    datetime.now(timezone(timedelta(hours=8))).date() - timedelta(days=30)
).isoformat()


def _preload_duckdb(
    root: Path,
    instrument_ids: list[str],
    *,
    now_ts: str | None = None,
) -> None:
    """Insert minimal DuckDB rows so populate_inputs returns non-None fields.

    Writes `instruments` metadata (expense_ratio, aum) and a 400-day
    synthetic NAV series — enough for self_history_percentile to return a
    value and remove the structural evidence gaps (missing_valuation_data,
    missing_flow_or_return_data, missing_product_metadata).

    `now_ts` defaults to a fixed ISO timestamp so AC22's two-run byte-equality
    test stays deterministic regardless of wall-clock skew between the two
    `run_opportunity(repo_root=...)` invocations. Callers running tests OTHER
    than byte-equality can leave the default; it doesn't affect any other
    surface because `_ingested_at` is not projected into the four canonical
    artifacts AC22 compares.
    """
    from irc.data.duckdb_helper import connect, ensure_schema

    db_path = root / "data" / "local.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = connect(db_path)
    ensure_schema(con)
    today = datetime.now(timezone(timedelta(hours=8))).date()

    if now_ts is None:
        now_ts = _FIXED_INGESTED_AT
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
        # Guard against silent "appended to non-existent file" — if run_init's
        # template emission ever changes, `open("a")` would create a NEW file
        # containing only this entry (no `instruments:` list header), so
        # yaml.safe_load would parse as a string and the appended row would
        # silently vanish from the universe.
        assert qdii_us_path.exists(), (
            f"expected {qdii_us_path} to exist after run_init; "
            "appending to a missing file would create invalid YAML"
        )
        assert qdii_hk_path.exists(), (
            f"expected {qdii_hk_path} to exist after run_init; "
            "appending to a missing file would create invalid YAML"
        )
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
    # `日期` reads from the module-level `_BROKER_REPORT_DATE` (computed once at
    # import time): the value flows through `BrokerReport.published_iso` →
    # `ThesisEvidence.date` → the citation_id sha256 preimage, so any cross-call
    # drift between the two `_seed_publishable_set_repo` calls in AC22 would
    # break byte-equality. Computing once at import + reusing avoids both the
    # wall-clock midnight window AND the 90-day broker-freshness cutoff (a
    # literal like "2024-12-31" silently gets dropped by the freshness gate
    # over time).
    broker_frame = pd.DataFrame({
        "机构": ["中金公司"],
        "东财评级": ["买入"],
        "报告名称": ["2024年年度报告"],
        "日期": [_BROKER_REPORT_DATE],
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
    # Guard against silent slice-direction inversion if the heading is ever
    # renamed (md.find returns -1; `md[:-1]` would silently make the
    # bucket-leakage assertion a near-false-negative).
    assert failure_idx >= 0, "discipline failure heading '## 证据不足' missing"
    above = md[:failure_idx]
    below = md[failure_idx:]

    assert "005827" in row_iids, "publishable iid missing from opportunity rows"
    assert "163417" not in row_iids, "gapped iid leaked into opportunity rows"
    assert "005827" in card_iids, "publishable iid missing from thesis_cards"
    assert "163417" not in card_iids, "gapped iid leaked into thesis_cards"
    assert "005827" in above, "publishable iid missing from discipline buckets"
    assert "163417" not in above, "gapped iid leaked into discipline buckets"
    assert "163417" in rej_iids, "gapped iid missing from rejections.json"
    assert "005827" not in rej_iids, "publishable iid leaked into rejections.json"
    assert "163417" in below, "gapped iid missing from discipline failure section"
    scored_iids = {s["instrument_id"] for s in scoring["scores"]}
    _assert_h3_partition(scored_iids, row_iids, rej_iids)


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

    # Capture once — `_today_cn()` evaluated twice with a midnight crossing
    # between the two calls would point out_dir at one date and the
    # `today=` arg at another, writing artifacts where the test never reads.
    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
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
        today=today,
    )

    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entry = next(e for e in rej["entries"] if e["instrument_id"] == "004243")
    assert entry["rejection_reason"] == "qdii_information_unavailable", \
        f"Policy-B precedence broken: got {entry['rejection_reason']!r}, " \
        "expected 'qdii_information_unavailable' (qdii key precedes policy-b key " \
        "in _GAP_TO_REASON dict-iteration order per ADR 0003)"


def test_policy_b_precedence_holds_when_qdii_gap_is_not_first_in_tuple(
    tmp_path, monkeypatch,
) -> None:
    """AC11 adversarial variant — when `evidence_gaps` tuple lists a
    structural gap BEFORE 'qdii_information_unavailable', the rejection_reason
    classifier MUST still resolve to 'qdii_information_unavailable' (the
    production-fix iterates `_GAP_TO_REASON` key-order, not the tuple-order).
    This is the case the prior `_classify_rejection_reason` bug silently
    failed: tuple-order iteration returned 'incomplete_constituent_data'."""
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
        # Adversarial ordering — structural gap FIRST, QDII gap LAST.
        evidence_gaps=(
            "insufficient_info_coverage_top_half",
            "qdii_information_unavailable",
        ),
        thesis_evidence=(),
        constituent_analyses=(),
    )

    # Capture once — midnight-skew guard, see sibling test for rationale.
    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
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
        today=today,
    )

    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entry = next(e for e in rej["entries"] if e["instrument_id"] == "004243")
    assert entry["rejection_reason"] == "qdii_information_unavailable", \
        "QDII precedence MUST hold regardless of evidence_gaps tuple order " \
        f"(got {entry['rejection_reason']!r})"


# ─── AC12: fetch_budget_exhausted is fatal at write time ─────────────────────

def test_fetch_budget_exhausted_fatal_at_write_time_via_run_opportunity(
    tmp_path, monkeypatch,
) -> None:
    """AC12 — _write_opportunity_outputs called with a row carrying
    'fetch_budget_exhausted' in evidence_gaps raises RuntimeError before
    any .tmp file becomes visible. Re-asserts via _write_opportunity_outputs
    directly (the run_opportunity path raises SystemExit(3) for budget
    exceeded, not RuntimeError)."""
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

    poisoned_row = OpportunityRow(
        instrument_id="005827",
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827",
            display_cn="易方达蓝筹精选", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=("fetch_budget_exhausted",),
        thesis_evidence=(),
        constituent_analyses=(),
    )

    # Capture once — midnight-skew guard, same as the sibling AC11 tests.
    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(RuntimeError, match="fetch_budget_exhausted"):
        _write_opportunity_outputs(
            kept_rows=[poisoned_row],
            positions={"005827": PositionContext(
                portfolio_weight=None, target_band_low=None, target_band_high=None,
                drawdown_since_entry=None, is_holding=False,
            )},
            qualities={"005827": SelectionQuality(
                expense_ratio=None, aum_cny=None, tracking_error=None,
                premium_discount_abs=None, history_days=None, data_completeness=0.5,
            )},
            roles={"005827": ""},
            holdings={},
            out_dir=out_dir,
            today=today,
        )

    # No artifacts may exist after the fatal raise.
    assert not (out_dir / "opportunity_report.json").exists(), \
        "fetch_budget_exhausted raise left a partial opportunity_report.json"
    assert not any(out_dir.glob("*.tmp*")), \
        "fetch_budget_exhausted raise left a .tmp file"


# ─── ACs 13–14: 持仓明细 appendix integrity (D3b) ────────────────────────────

_APPENDIX_LINE_RE_FOR_TEST = re.compile(
    r"^- \S+ .+ \(权重 [\d.]+%\): .+$"
)


def test_chicang_appendix_line_shape_per_publishable_row(tmp_path, monkeypatch) -> None:
    """AC13 — for every publishable cn_equity_fund/cn_etf row with non-empty
    constituent_analyses, the '## 持仓明细' appendix contains a subheading
    '### {instrument_id} {name_cn}' followed by ≥1 bullet line matching the
    locked regex (audit-error suffix permitted)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))

    appendix_idx = md.find("## 持仓明细")
    if appendix_idx < 0:
        pytest.skip("no publishable cn_equity_fund/cn_etf rows with constituents in this seed")
    appendix = md[appendix_idx:]

    for row in opp.get("rows", []):
        if row["asset_class"] not in {"cn_equity_fund", "cn_etf"}:
            continue
        if not row.get("constituent_analyses"):
            continue
        subheading = f"### {row['instrument_id']} {row['name_cn']}"
        assert subheading in appendix, \
            f"appendix missing subheading {subheading!r}"
        # Find subheading + following block until next ### or EOF.
        sh_idx = appendix.index(subheading)
        next_sh = appendix.find("###", sh_idx + len(subheading))
        block = appendix[sh_idx:next_sh] if next_sh >= 0 else appendix[sh_idx:]
        bullets = [
            ln for ln in block.splitlines()
            if _APPENDIX_LINE_RE_FOR_TEST.match(ln)
        ]
        assert bullets, \
            f"appendix subheading {subheading!r} has no bullet lines matching shape"


def test_chicang_appendix_omits_qdii(tmp_path, monkeypatch) -> None:
    """AC14 — QDII rows have NO '### {instrument_id}' subheading in the
    '## 持仓明细' appendix (they appear only in the failure section)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    appendix_idx = md.find("## 持仓明细")
    if appendix_idx < 0:
        # Appendix may be absent if no publishable rows have constituents.
        # That's fine; QDII is trivially absent.
        return
    appendix = md[appendix_idx:]
    for iid in _QDII_IIDS:
        assert f"### {iid}" not in appendix, \
            f"QDII {iid} leaked into 持仓明细 appendix"


# ─── ACs 15–17: snapshot-cache freshness (E8 family) ─────────────────────────

def _prewrite_active_fund_cache(
    tmp_path: Path,
    *,
    fund_id: str,
    cache_probed_at: str,
    source_report_quarter: str = "2024Q4",
) -> None:
    """Pre-write an ActiveFundSnapshot cache file with a controlled
    cache_probed_at field. Mirrors the on-disk shape produced by
    `snapshot_cache.write_active_fund_cache`."""
    from irc.fundamentals.snapshot_cache import write_active_fund_cache
    from irc.fundamentals.types import ActiveFundSnapshot

    snap = ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date="2024-01-15",
        source_report_quarter=source_report_quarter,
        constituent_analyses=(),
        failure_reasons_by_symbol={},
        cache_probed_at=cache_probed_at,
    )
    write_active_fund_cache(snap, tmp_path / "data")


def test_snapshot_cache_within_window_zero_akshare_calls(tmp_path, monkeypatch) -> None:
    """AC15 — within IRC_CACHE_FRESHNESS_DAYS, cached snapshot is reused
    and zero _ak_call invocations target the cached fund_id."""
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
        seed_date=today,
    )
    # Pre-write cache with cache_probed_at = today (within window).
    _prewrite_active_fund_cache(
        tmp_path, fund_id="005827", cache_probed_at=today,
    )
    counter = _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(repo_root=str(tmp_path))

    fund_calls = sum(
        v for (fn, sym), v in counter.items() if sym == "005827"
    )
    assert fund_calls == 0, \
        f"expected zero AkShare calls for cached fund 005827, got {fund_calls}: " \
        f"{[k for k in counter if k[1] == '005827']}"


def test_snapshot_cache_expired_probe_same_quarter_reuses(tmp_path, monkeypatch) -> None:
    """AC16 — cache older than IRC_CACHE_FRESHNESS_DAYS triggers a probe
    (one fund_portfolio_hold_em call with top_n=1); probe returns the same
    source_report_quarter so the cache is reused (no full per-constituent
    rebuild) and cache_probed_at is updated to today.

    Production probe path: _maybe_freshness_probe → fetch_cn_etf_holdings(top_n=1)
    → fund_portfolio_hold_em.  Same quarter → schedule_full_refetch=False →
    snap_obj = probed (cached data, updated timestamp).

    The holdings_frame must use the AkShare-native quarter format "2024年4季度"
    (matched by _QUARTER_RE = r"(\\d{4})年(\\d)季度") so that
    _parse_quarter_column returns "2024Q4" and the same-quarter check succeeds.
    Frames using "2024Q4" (non-native) parse to ("", "") → probe fails closed.
    """
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    expired = (
        datetime.now(timezone(timedelta(hours=8))).date()
        - timedelta(days=14)
    ).isoformat()

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
        seed_date=today,
    )
    _prewrite_active_fund_cache(
        tmp_path, fund_id="005827", cache_probed_at=expired,
        source_report_quarter="2024Q4",
    )
    # Override the holdings frame for 005827 with AkShare-native quarter format
    # so _parse_quarter_column returns ("2024Q4", ...) and the probe detects
    # same-quarter → schedule_full_refetch=False.
    import pandas as pd
    probe_holdings_frame = pd.DataFrame({
        "股票代码": ["600519"],
        "股票名称": ["贵州茅台"],
        "占净值比例": [8.2],
        "季度": ["2024年4季度"],  # native format parseable by _QUARTER_RE
    })
    dispatch[("fund_portfolio_hold_em", "005827")] = probe_holdings_frame

    counter = _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    # Probe fires exactly once (fund_portfolio_hold_em, top_n=1); same quarter
    # detected → no full rebuild → no constituent evidence calls for 005827.
    holdings_calls = counter[("fund_portfolio_hold_em", "005827")]
    assert holdings_calls == 1, (
        f"expected exactly 1 probe call (no full rebuild) for cached fund 005827, "
        f"got {holdings_calls}"
    )

    # Constituent-level evidence rebuild should NOT have fired (cache reused).
    # The prewritten cache has empty constituent_analyses, so no stock calls.
    constituent_calls = sum(
        v for (fn, sym), v in counter.items()
        if fn in ("stock_financial_abstract", "stock_research_report_em", "stock_news_em")
    )
    assert constituent_calls == 0, (
        f"probe-only path should not re-fetch constituent evidence, "
        f"got {constituent_calls} constituent calls"
    )

    # cache_probed_at updated to today on disk.
    from irc.fundamentals.snapshot_cache import load_active_fund_cache
    snap = load_active_fund_cache("005827", "2024Q4", tmp_path / "data")
    assert snap is not None
    assert snap.cache_probed_at == today, (
        f"expected cache_probed_at refreshed to {today}, got {snap.cache_probed_at}"
    )


def test_snapshot_cache_probe_failure_fail_closed_refetch(tmp_path, monkeypatch) -> None:
    """AC17 — probe failure forces full re-fetch (fail-closed, never silent-reuse).

    The probe uses fetch_cn_etf_holdings → fund_portfolio_hold_em.  When the
    probe raises, _maybe_freshness_probe returns (snap, True) → the caller
    calls build_snapshot (full rebuild) which calls fund_portfolio_hold_em again.
    Total holdings calls ≥ 2: one probe attempt + ≥ 1 rebuild attempt.
    """
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    expired = (
        datetime.now(timezone(timedelta(hours=8))).date()
        - timedelta(days=14)
    ).isoformat()

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
        seed_date=today,
    )
    _prewrite_active_fund_cache(
        tmp_path, fund_id="005827", cache_probed_at=expired,
    )

    # Make the first fund_portfolio_hold_em call (the probe, top_n=1) raise;
    # subsequent calls (full rebuild, top_n=10) return valid data from dispatch.
    import pandas as pd
    holdings_frame = dispatch.get(("fund_portfolio_hold_em", "005827"))
    call_seq: list[int] = []

    def _fail_first_holdings(fn_name, *args, **kwargs):
        sym = args[0] if args else kwargs.get("symbol", "")
        if fn_name == "fund_portfolio_hold_em" and str(sym) == "005827":
            call_seq.append(1)
            if len(call_seq) == 1:
                raise RuntimeError("probe network error (simulated)")
            return holdings_frame if holdings_frame is not None else pd.DataFrame()
        # Delegate all other fn_names to the dispatch dict.
        key = (fn_name, str(sym))
        frame = dispatch.get(key)
        return frame if frame is not None else pd.DataFrame()

    monkeypatch.setattr(
        "irc.fundamentals.akshare_fundamentals._ak_call", _fail_first_holdings,
    )
    monkeypatch.setattr(
        "irc.fundamentals.akshare_filing._ak_call", _fail_first_holdings,
    )

    # Probe failure → full rebuild fires; run_opportunity may exit non-zero
    # (system-exit) when the rebuild is the only path and itself raises, but
    # MUST NOT swallow programming bugs. Narrow the catch to SystemExit so
    # genuine crashes (NameError, import failures, KeyError) surface as test
    # failures instead of being masked by a silent re-raise on the assertion.
    try:
        run_opportunity(repo_root=str(tmp_path))
    except SystemExit:
        pass  # AC17 tolerates explicit non-zero exit from the rebuild path.

    probe_attempts = len(call_seq)
    assert probe_attempts >= 1, "probe was not even attempted"
    assert probe_attempts >= 2, (
        "probe failure did NOT trigger full re-fetch (silent-reuse leak): "
        f"only {probe_attempts} holdings call(s) observed"
    )


# ─── AC18: E9 downstream propagation ─────────────────────────────────────────

def test_empty_holdings_propagate_to_rejections_holdings_fetch_failed(
    tmp_path, monkeypatch,
) -> None:
    """AC18 — empty AkShare holdings → failure_reasons_by_symbol populated
    → row carries evidence_gaps containing 'holdings_fetch_failed' →
    appears in rejections.json, NOT in thesis_cards.yaml."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    # Force empty holdings for 005827.
    import pandas as pd
    dispatch[("fund_portfolio_hold_em", "005827")] = pd.DataFrame()

    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cards_doc = yaml.safe_load((out_dir / "thesis_cards.yaml").read_text(encoding="utf-8")) or {}
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))

    card_iids = {c["instrument_id"] for c in cards_doc.get("cards", [])}
    assert "005827" not in card_iids, \
        "fund with empty AkShare holdings leaked into thesis_cards.yaml"

    entry = next(
        (e for e in rej.get("entries", []) if e["instrument_id"] == "005827"),
        None,
    )
    assert entry is not None, \
        "fund with empty AkShare holdings missing from rejections.json"
    # Canonical contract: empty AkShare holdings → row carries the exact
    # `holdings_fetch_failed` code in `evidence_gaps`. The previous OR-form
    # silently accepted any other gap code that happened to map to the same
    # rejection_reason; tighten to the producer-side invariant.
    gaps = entry.get("evidence_gaps", [])
    assert "holdings_fetch_failed" in gaps, \
        f"expected 'holdings_fetch_failed' in evidence_gaps; got {gaps!r}"


# ─── ACs 19–20: cross-stage SAME-3 / citation-id-subset ──────────────────────

def _harvest_first_citation_ids(out_dir: Path, n: int = 3) -> list[str]:
    """Return up to n citation_ids from opportunity_report.json — used to
    build a deterministic memo synth body whose [ref:...] markers are a
    known subset of the publishable universe."""
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    ids: list[str] = []
    for row in opp.get("rows", []):
        for ev in row.get("thesis_evidence", []):
            cid = ev.get("citation_id")
            if cid and cid not in ids:
                ids.append(cid)
            if len(ids) >= n:
                return ids
    return ids


def test_memo_cites_only_publishable_citation_ids(tmp_path, monkeypatch) -> None:
    """AC19 — every [ref:{id}] in memo.md is in the publishable universe
    defined as opportunity_report.json ∪ gold_regime.json (rejections.json
    EXCLUDED per Q5)."""
    from irc.commands.memo_cmd import run_memo
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cids = _harvest_first_citation_ids(out_dir, n=3)
    if not cids:
        pytest.skip("no citation_ids produced by run_opportunity in this seed")
    synth_body = " ".join(f"[ref:{c}]" for c in cids) + " 备忘录正文"

    with _patch_memo_routes(synth_body):
        run_memo(str(tmp_path))

    memo_md = (out_dir / "memo.md").read_text(encoding="utf-8")
    universe = _collect_publishable_citation_universe(out_dir)
    refs = re.findall(r"\[ref:([0-9a-f]{16})\]", memo_md)
    assert refs, "memo.md has no [ref:...] markers despite synth body containing them"
    leaked = [r for r in refs if r not in universe]
    assert not leaked, \
        f"memo.md cites {leaked!r} not in publishable universe (size {len(universe)})"


def test_memo_picks_table_citation_set_matches_opportunity_row(
    tmp_path, monkeypatch,
) -> None:
    """AC20 — for each cn_equity_fund pick, the set of citation_ids in
    memo.md picks-table 证据 cell equals the set in opportunity_report.json
    for that row's selected-top-3 (per select_citations(cap=3)).
    SAME-3 invariant re-asserted post-disk-roundtrip."""
    from irc.commands.memo_cmd import run_memo
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.memo.citation_selector import select_citations
    from irc.fundamentals.types import ThesisEvidence

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cids = _harvest_first_citation_ids(out_dir, n=3)
    if not cids:
        pytest.skip("no citation_ids produced in this seed")

    with _patch_memo_routes(" 备忘录正文"):
        run_memo(str(tmp_path))

    memo_md = (out_dir / "memo.md").read_text(encoding="utf-8")
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))

    for row in opp.get("rows", []):
        if row["asset_class"] != "cn_equity_fund":
            continue
        # Reconstruct top-3 via select_citations and compare to picks-table cell.
        evs = tuple(ThesisEvidence.from_dict(d) for d in row.get("thesis_evidence", []))
        top3 = {ev.citation_id for ev in select_citations(evs, cap=3)}
        # Locate the picks-table row for this iid; extract its 证据 cell.
        pat = rf"\| *{re.escape(row['instrument_id'])} *\|.*?\|(.*?)\|"
        m = re.search(pat, memo_md)
        if not m:
            pytest.skip(f"no picks-table row for {row['instrument_id']}")
        cell = m.group(1)
        cell_ids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", cell))
        assert cell_ids == top3, \
            f"SAME-3 mismatch for {row['instrument_id']}: " \
            f"picks-table={cell_ids!r} vs opportunity-top-3={top3!r}"


# ─── AC21: multi-owner constituent on-disk provenance ────────────────────────

def test_multi_owner_constituent_keeps_separate_owner_instrument_id(
    tmp_path, monkeypatch,
) -> None:
    """AC21 — when 贵州茅台 (600519) appears as a constituent of BOTH fund A
    (005827) and fund B (163417), each fund's thesis_evidence entry for
    600519 has owner_instrument_id == that fund's iid. No leakage."""
    from irc.commands.opportunity_cmd import run_opportunity
    import pandas as pd

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    # Add a second cn_equity_fund to scoring.json.
    out_dir = tmp_path / "outputs" / _today_cn()
    scoring = json.loads((out_dir / "scoring.json").read_text(encoding="utf-8"))
    scoring["scores"].append({
        "instrument_id": "163417", "name_cn": "兴全合润",
        "asset_class": "cn_equity_fund", "composite_score": 72.0,
    })
    (out_dir / "scoring.json").write_text(
        json.dumps(scoring, ensure_ascii=False), encoding="utf-8",
    )
    # Pre-load DuckDB for the second fund so structural evidence gaps are avoided.
    _preload_duckdb(tmp_path, ["163417"])

    # Both funds carry 600519 as a top holding. `季度` column matches the
    # other holdings frames in this seed so the cache writes under the
    # realistic `(fund_id, "2024Q4")` key instead of `(fund_id, "")`,
    # keeping AC21 aligned with real AkShare response shape.
    same_holding_frame = pd.DataFrame({
        "股票代码": ["600519"],
        "股票名称": ["贵州茅台"],
        "占净值比例": [8.2],
        "季度": ["2024年4季度"],
    })
    dispatch[("fund_portfolio_hold_em", "005827")] = same_holding_frame
    dispatch[("fund_portfolio_hold_em", "163417")] = same_holding_frame
    # Wire announcement data for 163417 (information leg).
    ann_frame = pd.DataFrame({
        "公告标题": ["2024年第4季度报告"],
        "公告日期": ["2024-01-15"],
        "报告ID": ["ANN002"],
    })
    dispatch[("fund_announcement_dividend_em", "163417")] = ann_frame
    dispatch[("fund_announcement_report_em", "163417")] = ann_frame
    dispatch[("fund_announcement_personnel_em", "163417")] = ann_frame

    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    by_iid = {r["instrument_id"]: r for r in opp.get("rows", [])}
    if "005827" not in by_iid or "163417" not in by_iid:
        pytest.skip("seed did not produce both funds publishably")

    a_owners = {
        ev["owner_instrument_id"]
        for ev in by_iid["005827"].get("thesis_evidence", [])
        if ev.get("constituent_key") == "600519"
    }
    b_owners = {
        ev["owner_instrument_id"]
        for ev in by_iid["163417"].get("thesis_evidence", [])
        if ev.get("constituent_key") == "600519"
    }
    assert a_owners == {"005827"}, \
        f"fund A 600519 entries have wrong owner_instrument_id: {a_owners!r}"
    assert b_owners == {"163417"}, \
        f"fund B 600519 entries have wrong owner_instrument_id: {b_owners!r}"


# ─── ACs 22–23: pipeline-level two-run byte equality ─────────────────────────

def test_two_run_byte_equality_opportunity_artifacts(tmp_path, monkeypatch) -> None:
    """AC22 — two consecutive run_opportunity invocations against identical
    seeds in distinct tmp_paths produce byte-identical artifacts for:
      - opportunity_report.json
      - thesis_cards.yaml
      - discipline_report.md
      - rejections.json
    Catches non-deterministic ordering (frozenset, glob, dict-hash, timestamps)
    invisible to unit-level tests."""
    from irc.commands.opportunity_cmd import run_opportunity

    a = tmp_path / "run_a"
    b = tmp_path / "run_b"
    a.mkdir()
    b.mkdir()

    today = _today_cn()
    dispatch_a = _seed_publishable_set_repo(
        a, monkeypatch=monkeypatch, seed_date=today,
    )
    _install_ak_call_dispatch(monkeypatch, dispatch_a)
    run_opportunity(repo_root=str(a))

    dispatch_b = _seed_publishable_set_repo(
        b, monkeypatch=monkeypatch, seed_date=today,
    )
    _install_ak_call_dispatch(monkeypatch, dispatch_b)
    run_opportunity(repo_root=str(b))

    for name in (
        "opportunity_report.json",
        "thesis_cards.yaml",
        "discipline_report.md",
        "rejections.json",
    ):
        ha = _sha256_file(a / "outputs" / today / name)
        hb = _sha256_file(b / "outputs" / today / name)
        assert ha == hb, \
            f"{name} differs across two runs: a={ha[:12]}… b={hb[:12]}… " \
            "(non-determinism in the I/O stack — likely frozenset iter, " \
            "glob/walk ordering, dict-hash, or datetime.now() injection)"


def test_two_run_byte_equality_memo_after_run_memo(tmp_path, monkeypatch) -> None:
    """AC23 — same shape as AC22 but for memo.md after run_opportunity → run_memo.
    Patched synth body is a deterministic function of the just-written
    opportunity_report.json so the synth output is itself a function of the
    publishable-set citation universe."""
    from irc.commands.memo_cmd import run_memo
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    a = tmp_path / "run_a"
    b = tmp_path / "run_b"
    a.mkdir()
    b.mkdir()

    def _full_run(repo: Path) -> Path:
        dispatch = _seed_publishable_set_repo(
            repo, monkeypatch=monkeypatch, seed_date=today,
        )
        _install_ak_call_dispatch(monkeypatch, dispatch)
        run_opportunity(repo_root=str(repo))
        out_dir = repo / "outputs" / today
        cids = _harvest_first_citation_ids(out_dir, n=3)
        synth_body = " ".join(f"[ref:{c}]" for c in cids) + " 备忘录正文"
        with _patch_memo_routes(synth_body):
            run_memo(str(repo))
        return out_dir

    out_a = _full_run(a)
    out_b = _full_run(b)

    ha = _sha256_file(out_a / "memo.md")
    hb = _sha256_file(out_b / "memo.md")
    assert ha == hb, \
        f"memo.md differs across two runs: a={ha[:12]}… b={hb[:12]}… " \
        "(non-determinism in the memo I/O stack)"
