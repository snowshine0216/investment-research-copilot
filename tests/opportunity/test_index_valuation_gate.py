from __future__ import annotations

from datetime import date

import duckdb
import pytest

from irc.data.duckdb_helper import ensure_schema
from irc.opportunity.inputs_loader import _index_valuation_metrics


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "gate.duckdb"))
    ensure_schema(con)
    return con


def _seed(con, index_key, pe_pb_pairs, base_date=date(2025, 1, 1)):
    rows = []
    for i, (pe, pb) in enumerate(pe_pb_pairs):
        d = date.fromordinal(base_date.toordinal() + i)
        rows.append((index_key, d, pe, pb, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


# 200 rising PE points: > MIN_PE_POINTS (120) and span > MIN_PE_DAYS (180) -> mature.
_MATURE_PAIRS = [(10.0 + i * 0.1, None) for i in range(200)]


def test_sector_slug_off_allowlist_returns_full_none_tuple(tmp_path):
    """Mature sector series with empty allowlist -> full all-None short-circuit
    (raw pe/pb/div AND both percentiles withheld). Byte-identity invariant."""
    con = _con(tmp_path)
    _seed(con, "csi_robotics", _MATURE_PAIRS)
    result = _index_valuation_metrics(
        con, "中证机器人", activated_sector_slugs=frozenset()
    )
    assert result == (None, None, None, None, None)
    con.close()


def test_sector_slug_default_allowlist_returns_full_none_tuple(tmp_path):
    """Default (no kwarg passed) is frozenset() -> same short-circuit."""
    con = _con(tmp_path)
    _seed(con, "csi_robotics", _MATURE_PAIRS)
    assert _index_valuation_metrics(con, "中证机器人") == (None, None, None, None, None)
    con.close()


def test_sector_slug_on_allowlist_populates_percentile_pb_none(tmp_path):
    """Slug in allowlist + mature series -> PE percentile populated; PB None
    (csindex carries no PB)."""
    con = _con(tmp_path)
    _seed(con, "csi_robotics", _MATURE_PAIRS)
    pe, pb, div, pe_pct, pb_pct = _index_valuation_metrics(
        con, "中证机器人", activated_sector_slugs=frozenset({"csi_robotics"})
    )
    assert pe == pytest.approx(10.0 + 199 * 0.1)  # latest PE populated
    assert pb is None and div is None
    assert pe_pct == pytest.approx(1.0)  # latest is the max -> percentile 1.0
    assert pb_pct is None
    con.close()


def test_metals_slug_off_allowlist_short_circuits(tmp_path):
    """Folded-in metals slug is now allowlist-governed: empty allowlist ->
    full None (must NOT auto-activate on maturity)."""
    con = _con(tmp_path)
    _seed(con, "csi_nonferrous", _MATURE_PAIRS)
    assert _index_valuation_metrics(
        con, "中证有色金属", activated_sector_slugs=frozenset()
    ) == (None, None, None, None, None)
    con.close()


def test_broad_slug_unaffected_by_empty_allowlist(tmp_path):
    """Broad-index slug grounds regardless of the (empty) sector allowlist."""
    con = _con(tmp_path)
    _seed(con, "csi300", [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)])
    pe, pb, div, pe_pct, pb_pct = _index_valuation_metrics(
        con, "csi300", activated_sector_slugs=frozenset()
    )
    assert pe is not None and pe_pct == pytest.approx(1.0)
    con.close()


def test_broad_slug_unaffected_by_nonempty_allowlist(tmp_path):
    """A non-empty sector allowlist must not change broad behavior."""
    con = _con(tmp_path)
    _seed(con, "csi300", [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)])
    pe_a = _index_valuation_metrics(con, "csi300", activated_sector_slugs=frozenset())
    pe_b = _index_valuation_metrics(
        con, "csi300", activated_sector_slugs=frozenset({"csi_robotics"})
    )
    assert pe_a == pe_b
    con.close()
