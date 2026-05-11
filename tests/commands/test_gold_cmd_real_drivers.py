from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from irc.commands.init_cmd import run_init
from irc.commands.gold_cmd import run_gold


def test_gold_cmd_reads_cb_and_etf_from_wgc_csv(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    # Populate DuckDB with enough gold prices to satisfy run_gold
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
    con.close()
    wgc = Path(tmp_path) / "data" / "wgc"
    wgc.mkdir(parents=True, exist_ok=True)
    (wgc / "cb_purchases.csv").write_text("year,tons\n2026,950\n", encoding="utf-8")
    (wgc / "etf_holdings.csv").write_text(
        "date,total_tons\n2026-04-07,3220.5\n2026-05-07,3245.0\n", encoding="utf-8",
    )
    rc = run_gold(repo_root=str(tmp_path))
    assert rc == 0
