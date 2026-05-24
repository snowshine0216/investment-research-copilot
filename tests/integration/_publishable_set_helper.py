"""Lifted from tests/integration/test_publishable_set_lockdown.py per item 009 D3.

Shared seed scaffold for the publishable-set lockdown (item 008) and the
citation-audit-gate (item 009) integration suites. Both files import from
this module; no other module should import here.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

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
