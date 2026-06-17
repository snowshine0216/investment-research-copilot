from __future__ import annotations

from datetime import date

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.monitor.types import MonitorFund


def _fund(fund_id, profile):
    return MonitorFund(
        id=fund_id, name_cn="x", market="cn_off_exchange",
        analysis_profile=profile, themes=(), constituent_news=False,
        weights={}, bands={}, minimum_confidence=0.5,
    )


def _seed_instrument(con, fund_id, tracked_index):
    # provenance cols are NOT NULL → name + supply them.
    con.execute(
        "INSERT INTO instruments (instrument_id, ticker, market, name_cn, "
        "asset_class, currency, tracked_index, _ingested_at, _source, _raw_ref) "
        "VALUES (?,?,?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:i')",
        [fund_id, fund_id, "cn_off_exchange", "x", "cn_etf", "cny", tracked_index],
    )


def _seed_iv(con, index_key, pairs):
    rows = []
    for i, (pe, pb) in enumerate(pairs):
        d = date.fromordinal(date(2025, 1, 1).toordinal() + i)
        rows.append((index_key, d, pe, pb, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


def test_index_fund_gets_real_valuation_state(tmp_path):
    # Use csi300 — a working index anchor (china_internet is NOT a valuation key;
    # see the SPEC GAP note in the plan header). Profile active_cn_equity makes
    # valuation eligible, so the mapped state surfaces as an eligible FactorScore.
    con = duckdb.connect(str(tmp_path / "local.duckdb"))
    ensure_schema(con)
    _seed_instrument(con, "510300", "csi300")
    _seed_iv(con, "csi300", [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)])

    from irc.monitor.valuation import resolve_valuation_state
    res = resolve_valuation_state(_fund("510300", "active_cn_equity"),
                                  con=con, root=tmp_path)
    assert res.state == "very_expensive" and res.cached is True
    # The state is consumed by _valuation → an eligible FactorScore (vocab maps it).
    from irc.monitor.factors import FactorInputs, build_factor_scores
    inp = FactorInputs(
        acc_nav=(), minimum_observations=251,
        valuation_state=res.state, valuation_cached=res.cached,
        restricted=None, aum_delta_pct=None, macro_rows=(), constituent_rows=(),
    )
    scores = {s.name: s for s in build_factor_scores("active_cn_equity", inp)}
    assert scores["valuation"].eligible is True
    assert scores["valuation"].value == -1.0   # very_expensive → _VALUATION_MAP -1.0
    con.close()


def test_gold_and_qdii_global_valuation_stay_profile_ineligible(tmp_path):
    con = duckdb.connect(str(tmp_path / "local.duckdb"))
    ensure_schema(con)
    from irc.monitor.valuation import resolve_valuation_state
    from irc.monitor.factors import FactorInputs, build_factor_scores
    for profile in ("gold", "qdii_global"):
        res = resolve_valuation_state(_fund("0", profile), con=con, root=tmp_path)
        inp = FactorInputs(
            acc_nav=(), minimum_observations=251,
            valuation_state=res.state, valuation_cached=res.cached,
            restricted=None, aum_delta_pct=None, macro_rows=(), constituent_rows=(),
        )
        scores = {s.name: s for s in build_factor_scores(profile, inp)}
        assert scores["valuation"].eligible is False
        assert scores["valuation"].reason == "profile_ineligible"
    con.close()
