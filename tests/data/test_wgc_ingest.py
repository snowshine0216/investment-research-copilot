from __future__ import annotations
from pathlib import Path
from irc.data.wgc_ingest import (
    cb_purchases_yearly_tons, etf_holdings_30d_change_tons,
)


def test_cb_purchases_from_csv(tmp_path: Path):
    csv = tmp_path / "wgc_cb.csv"
    csv.write_text("year,tons\n2024,1037\n2025,950\n", encoding="utf-8")
    out = cb_purchases_yearly_tons(csv_path=csv, as_of_year=2025)
    assert out == 950.0


def test_cb_purchases_falls_back_to_zero_when_missing(tmp_path: Path):
    out = cb_purchases_yearly_tons(csv_path=tmp_path / "nope.csv", as_of_year=2025)
    assert out == 0.0


def test_etf_holdings_30d_change_from_csv(tmp_path: Path):
    csv = tmp_path / "wgc_etf.csv"
    csv.write_text(
        "date,total_tons\n2026-04-07,3220.5\n2026-05-07,3245.0\n",
        encoding="utf-8",
    )
    out = etf_holdings_30d_change_tons(csv_path=csv, as_of="2026-05-07")
    assert abs(out - 24.5) < 1e-6
