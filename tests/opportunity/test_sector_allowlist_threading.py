from __future__ import annotations

from datetime import date

import duckdb
import pytest

from irc.data.duckdb_helper import ensure_schema
from irc.opportunity import inputs_loader
from irc.opportunity.types import OpportunityInput


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "thread.duckdb"))
    ensure_schema(con)
    return con


def _seed_mature(con, index_key):
    rows = []
    base = date(2025, 1, 1)
    for i in range(200):
        d = date.fromordinal(base.toordinal() + i)
        rows.append((index_key, d, 10.0 + i * 0.1, None, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


def test_populate_inputs_forwards_allowlist_to_metrics(tmp_path, monkeypatch):
    """The allowlist must REACH _index_valuation_metrics (no global lookup)."""
    captured = {}
    real = inputs_loader._index_valuation_metrics

    def spy(con, tracked_index, *, activated_sector_slugs=frozenset()):
        captured["slugs"] = activated_sector_slugs
        return real(con, tracked_index, activated_sector_slugs=activated_sector_slugs)

    monkeypatch.setattr(inputs_loader, "_index_valuation_metrics", spy)
    con = _con(tmp_path)
    skeleton = OpportunityInput(
        instrument_id="562500", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="中证机器人", name_cn="机器人ETF",
    )
    inputs_loader.populate_inputs(
        con, skeleton, holding_entry_date=None,
        activated_sector_slugs=frozenset({"csi_robotics"}),
    )
    assert captured["slugs"] == frozenset({"csi_robotics"})
    con.close()


def test_populate_inputs_on_allowlist_grounds_sector(tmp_path):
    """End-to-end through populate_inputs: allowlisted mature sector grounds PE."""
    con = _con(tmp_path)
    _seed_mature(con, "csi_robotics")
    skeleton = OpportunityInput(
        instrument_id="562500", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="中证机器人",
    )
    inp = inputs_loader.populate_inputs(
        con, skeleton, holding_entry_date=None,
        activated_sector_slugs=frozenset({"csi_robotics"}),
    )
    assert inp.valuation_percentile_fundamental == pytest.approx(1.0)
    assert inp.valuation_percentile_fundamental_pb is None
    con.close()


def test_populate_inputs_empty_allowlist_withholds_sector(tmp_path):
    """Default empty allowlist -> sector ungrounded (byte-identity)."""
    con = _con(tmp_path)
    _seed_mature(con, "csi_robotics")
    skeleton = OpportunityInput(
        instrument_id="562500", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="中证机器人",
    )
    inp = inputs_loader.populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.valuation_percentile_fundamental is None
    assert inp.pe_ttm is None
    con.close()


def test_build_rows_and_run_opportunity_thread_the_allowlist():
    import inspect

    from irc.commands import opportunity_cmd
    from irc.opportunity import inputs_build

    build_input_src = inspect.getsource(inputs_build._build_input)
    assert "activated_sector_slugs" in build_input_src

    build_rows_src = inspect.getsource(opportunity_cmd._build_rows)
    assert "activated_sector_slugs" in build_rows_src

    run_src = inspect.getsource(opportunity_cmd.run_opportunity)
    assert "sector_index_grounding" in run_src
    assert "activated_slugs" in run_src
