from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import pytest
from irc.commands.init_cmd import run_init
from irc.commands.gold_cmd import run_gold


@pytest.fixture
def repo_with_gold_data(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "data" / "local.duckdb")
    ensure_schema(con)
    base = date(2026, 5, 7)
    for i in range(180):
        d = base - timedelta(days=180 - i)
        con.execute(
            "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["518880", d.isoformat(), 4.20, 4.25, 4.18, 4.20 + i * 0.005, 1e7,
             "2026-05-07T10:00:00+08:00", "openbb",
             f"openbb:prices:518880:{d.isoformat()}"],
        )
    # Macro series
    for s, v in (("DGS10", 4.0), ("DTWEXBGS", 104.0)):
        con.execute(
            "INSERT INTO macro_series VALUES (?, ?, ?, ?, ?, ?)",
            [s, base.isoformat(), v, "2026-05-07T10:00:00+08:00", "openbb",
             f"openbb:macro_series:{s}:{base.isoformat()}"],
        )
    con.close()
    return tmp_path


def test_gold_writes_regime_and_band(repo_with_gold_data: Path):
    rc = run_gold(repo_root=str(repo_with_gold_data))
    assert rc == 0
    out_dir = next(p for p in (repo_with_gold_data / "outputs").iterdir())
    assert (out_dir / "gold_regime.json").exists()
    assert (out_dir / "gold_band.yaml").exists()
