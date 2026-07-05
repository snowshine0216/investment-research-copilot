from __future__ import annotations

import json
import logging
from pathlib import Path

from irc.monitor.industry_map_store import fresh_slice, load_store, merge_seen, record_seen


def test_load_store_missing_file_is_empty(tmp_path: Path):
    assert load_store(tmp_path / "stock_industry_map.json") == {}


def test_load_store_corrupt_file_degrades_to_empty(tmp_path: Path, caplog):
    p = tmp_path / "stock_industry_map.json"
    p.write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert load_store(p) == {}
    assert any("unreadable" in r.message for r in caplog.records)


def test_load_store_malformed_rows_dropped_not_crash(tmp_path: Path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({
        "600519": {"industry": "酿酒行业", "seen_at": "2026-07-03"},
        "000651": {"industry": None, "seen_at": "2026-07-03"},
        "300750": "just-a-string",
    }, ensure_ascii=False), encoding="utf-8")
    assert load_store(p) == {"600519": {"industry": "酿酒行业", "seen_at": "2026-07-03"}}


def test_merge_seen_upserts_and_refreshes_seen_at_even_when_unchanged():
    store = {"600519": {"industry": "酿酒行业", "seen_at": "2026-06-01"}}
    merged = merge_seen(store, "2026-07-03", {"600519": "酿酒行业", "000651": "家电行业"})
    # refresh-on-seen: seen_at refreshed even though the industry string is unchanged
    assert merged["600519"] == {"industry": "酿酒行业", "seen_at": "2026-07-03"}
    assert merged["000651"] == {"industry": "家电行业", "seen_at": "2026-07-03"}


def test_merge_seen_skips_none_and_blank_and_never_mutates():
    store = {"600519": {"industry": "酿酒行业", "seen_at": "2026-06-01"}}
    before = {k: dict(v) for k, v in store.items()}
    merged = merge_seen(store, "2026-07-03", {"000651": None, "300750": "", "600690": "  "})
    assert set(merged) == {"600519"}         # absence ≠ evidence: nothing written
    assert store == before                   # pure: argument not mutated
    assert merged is not store


def test_fresh_slice_serves_within_30_calendar_days_only():
    store = {
        "600519": {"industry": "酿酒行业", "seen_at": "2026-06-03"},   # exactly 30 d → served
        "000651": {"industry": "家电行业", "seen_at": "2026-06-02"},   # 31 d → dropped
        "300750": {"industry": "电池", "seen_at": "2026-07-03"},       # today → served
    }
    assert fresh_slice(store, "2026-07-03") == {"600519": "酿酒行业", "300750": "电池"}


def test_fresh_slice_unparseable_seen_at_dropped_not_served():
    store = {"600519": {"industry": "酿酒行业", "seen_at": "not-a-date"}}
    assert fresh_slice(store, "2026-07-03") == {}


def test_fresh_slice_future_seen_at_is_not_fresh():
    """Round-1 P2 hardening: a future seen_at (e.g. clock skew / bad write) must
    NOT be served forever — only 0 <= delta <= max_age_days counts as fresh."""
    store = {"600519": {"industry": "酿酒行业", "seen_at": "2026-07-10"}}   # 7 d in the future
    assert fresh_slice(store, "2026-07-03") == {}


def test_record_seen_roundtrip_and_byte_stable(tmp_path: Path):
    p = tmp_path / "stock_industry_map.json"
    record_seen(p, "2026-07-02", {"600519": "酿酒行业"})
    record_seen(p, "2026-07-03", {"000651": "家电行业"})
    assert load_store(p) == {
        "600519": {"industry": "酿酒行业", "seen_at": "2026-07-02"},
        "000651": {"industry": "家电行业", "seen_at": "2026-07-03"},
    }
    a = p.read_bytes()
    record_seen(p, "2026-07-03", {"000651": "家电行业"})   # same-day no-op merge
    assert p.read_bytes() == a                              # byte-stable


def test_record_seen_all_none_input_writes_nothing(tmp_path: Path):
    p = tmp_path / "stock_industry_map.json"
    record_seen(p, "2026-07-03", {"600519": None})
    assert not p.exists()                    # RD-4: a no-op merge never creates the file


def test_merge_seen_stores_board_codes_as_industry():
    # ADR 0023 D7: the rotation radar reuses this store to persist stock→EM-board-code
    # mappings — board codes live in the `industry` slot (arbitrary strings already).
    store = merge_seen({}, "2026-07-06", {"600001": "BK0475", "000002": "BK0438"})
    served = fresh_slice(store, "2026-07-06")
    assert served == {"600001": "BK0475", "000002": "BK0438"}
