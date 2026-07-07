from __future__ import annotations

from irc.rotation.seed import seed_boards, seed_holdings, seed_stock_board_map
from irc.rotation.types import BoardDay


def _tds(n: int = 25) -> tuple[str, ...]:
    return tuple(f"2026-06-{i:02d}" for i in range(1, n + 1))


def test_seed_boards_skips_already_present(tmp_path):
    from irc.rotation.series_store import append_snapshot

    p = tmp_path / "board_series.json"
    tds = _tds()
    append_snapshot(
        p,
        [BoardDay(d, "BK1", "半导体", 1.0, 1.0, 2.0, None, "backfill") for d in tds],
        keep_td=60,
        trading_days=tds,
    )
    calls = []

    def fake_hist(code, name):
        calls.append(code)
        return tuple(
            BoardDay(d, code, name, 1.0, None, 2.0, None, "backfill") for d in tds
        )

    summary = seed_boards(
        [("BK1", "半导体"), ("BK2", "白酒")],
        series_path=p,
        keep_td=60,
        trading_days=tds,
        fetch_hist=fake_hist,
    )
    assert calls == ["BK2"]  # BK1 skipped (already ≥ MIN_TD)
    assert summary["done"] == 1 and summary["skipped"] == 1
    assert summary["failed"] == ()


def test_seed_boards_partial_tolerant_on_fetch_error(tmp_path):
    p = tmp_path / "board_series.json"
    tds = _tds()

    def flaky(code, name):
        if code == "BK1":
            raise RuntimeError("transient block")
        return tuple(
            BoardDay(d, code, name, 1.0, None, 2.0, None, "backfill") for d in tds
        )

    summary = seed_boards(
        [("BK1", "半导体"), ("BK2", "白酒")],
        series_path=p,
        keep_td=60,
        trading_days=tds,
        fetch_hist=flaky,
    )
    assert summary["done"] == 1  # BK2 seeded despite BK1 blowing up
    assert summary["failed"] == ("BK1",)


def test_seed_holdings_skips_cached(tmp_path):
    cache = tmp_path / "narrative_holdings"
    cache.mkdir()
    (cache / "F1.json").write_text('{"holdings": []}', encoding="utf-8")
    fetched = []

    def fake_fetch(fund_id, *, cache_dir):
        fetched.append(fund_id)
        return ()

    summary = seed_holdings(["F1", "F2"], cache_dir=cache, fetch=fake_fetch)
    assert fetched == ["F2"]  # F1 already cached
    assert summary["done"] == 1 and summary["skipped"] == 1


def test_seed_stock_board_map_skips_fresh_and_chunks(tmp_path):
    map_path = tmp_path / "stock_industry_map.json"
    chunks = []

    def fake_batch(symbols):
        chunks.append(tuple(symbols))
        return {}, {s: "电子元件" for s in symbols}

    def fake_load(_path):
        return {"600001": {"industry": "半导体", "seen_at": "2026-07-06"}}

    recorded = []

    def fake_record(path, today, industry_by_symbol):
        recorded.append((today, dict(industry_by_symbol)))
        return {}

    summary = seed_stock_board_map(
        ["600001", "600002", "600003", "600004"],
        map_path=map_path,
        today="2026-07-06",
        batch_fetch=fake_batch,
        load_existing=fake_load,
        record=fake_record,
        chunk_size=2,
    )
    # 600001 is fresh → skipped; remaining 3 symbols in 2 chunks of ≤2.
    assert [len(c) for c in chunks] == [2, 1]
    assert "600001" not in [s for c in chunks for s in c]
    assert summary["skipped"] == 1 and summary["done"] == 3
    assert len(recorded) == 2


def test_seed_stock_board_map_chunk_failure_is_tolerated(tmp_path):
    map_path = tmp_path / "stock_industry_map.json"

    def boom(symbols):
        raise RuntimeError("chunk blocked")

    summary = seed_stock_board_map(
        ["600002", "600003"],
        map_path=map_path,
        today="2026-07-06",
        batch_fetch=boom,
        load_existing=lambda _p: {},
        record=lambda *a, **k: {},
        chunk_size=200,
    )
    assert summary["done"] == 0
    assert summary["failed"] == ("600002", "600003")


def test_seed_stock_board_map_refetches_stale_skips_fresh(tmp_path):
    # Production-shaped store: 行业 NAMES in the industry slot (NOT "BK1"). One
    # entry STALE (seen_at > 30 calendar days before today), one FRESH (≤ 30 days).
    map_path = tmp_path / "stock_industry_map.json"
    chunks = []

    def fake_batch(symbols):
        chunks.append(tuple(symbols))
        return {}, {s: "半导体" for s in symbols}

    def fake_load(_path):
        return {
            "600519": {"industry": "酿酒行业", "seen_at": "2026-05-01"},  # 66d → STALE
            "000651": {"industry": "家电行业", "seen_at": "2026-07-01"},  # 5d  → FRESH
        }

    summary = seed_stock_board_map(
        ["600519", "000651"],
        map_path=map_path,
        today="2026-07-06",
        batch_fetch=fake_batch,
        load_existing=fake_load,
        record=lambda *a, **k: {},
        chunk_size=200,
    )
    fetched = [s for c in chunks for s in c]
    assert "600519" in fetched       # STALE (>30d) re-fetched — the freshness fix
    assert "000651" not in fetched   # FRESH (≤30d) still skipped — resumability
    assert summary["skipped"] == 1   # only the fresh entry counts as skipped


def test_seed_stock_board_map_roundtrip_refreshes_stale_seen_at(tmp_path):
    # Integration: real store round-trip. Pre-seed a STALE + a FRESH entry, run
    # seed, assert stale seen_at bumped to today while fresh is untouched — the
    # heal loop end-to-end (stale → re-fetched → record_seen refresh-on-seen).
    from irc.monitor.industry_map_store import load_store, record_seen

    map_path = tmp_path / "stock_industry_map.json"
    record_seen(map_path, "2026-05-01", {"600519": "酿酒行业"})  # STALE (66d)
    record_seen(map_path, "2026-07-01", {"000651": "家电行业"})  # FRESH (5d)

    chunks = []

    def fake_batch(symbols):
        chunks.append(tuple(symbols))
        return {}, {s: "酿酒行业" for s in symbols}  # 2-tuple; only stale is pending

    summary = seed_stock_board_map(
        ["600519", "000651"],
        map_path=map_path,
        today="2026-07-06",
        batch_fetch=fake_batch,
        load_existing=load_store,
        record=record_seen,
        chunk_size=200,
    )
    store = load_store(map_path)
    assert store["600519"]["seen_at"] == "2026-07-06"   # STALE refreshed to today
    assert store["000651"]["seen_at"] == "2026-07-01"   # FRESH untouched
    assert "000651" not in [s for c in chunks for s in c]  # fresh never re-fetched
    assert summary["done"] == 1
