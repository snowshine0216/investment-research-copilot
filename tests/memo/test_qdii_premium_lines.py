"""Pure-logic tests for src/irc/memo/qdii_premium_lines.py (item 003).

Covers AC1–AC18 of docs/2026-05-27-instrument-pickability/items/003-spec.md
and the four decisions locked in docs/adr/0006-qdii-premium-memo-surface.md.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

from irc.schemas.discovery import QDII_MAX_PREMIUM_DEFAULT


def test_threshold_is_alias_of_decision_gate_default() -> None:
    """AC5: QDII_PREMIUM_THRESHOLD_PCT must be the SAME object/value as
    QDII_MAX_PREMIUM_DEFAULT so the memo display value can never drift from
    the decision-gate value."""
    from irc.memo.qdii_premium_lines import QDII_PREMIUM_THRESHOLD_PCT

    assert QDII_PREMIUM_THRESHOLD_PCT == QDII_MAX_PREMIUM_DEFAULT
    assert QDII_PREMIUM_THRESHOLD_PCT == 0.05


def test_marker_constants_match_existing_convention() -> None:
    """Mirror IRC_CONCENTRATION_BEGIN/END and the rest of the
    `<!-- IRC_*_BEGIN -->` / `<!-- IRC_*_END -->` family."""
    from irc.memo.qdii_premium_lines import (
        QDII_PREMIUM_MARKER_BEGIN,
        QDII_PREMIUM_MARKER_END,
    )

    assert QDII_PREMIUM_MARKER_BEGIN == "<!-- IRC_QDII_PREMIUM_BEGIN -->"
    assert QDII_PREMIUM_MARKER_END == "<!-- IRC_QDII_PREMIUM_END -->"


def test_format_cell_none_returns_em_dash() -> None:
    """AC2 branch 1: non-QDII rows (premium is None) render `—`."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    assert _format_qdii_premium_cell(qdii_premium_pct=None,
                                     asset_class="cn_etf") == "—"


def test_format_cell_off_exchange_zero_renders_with_suffix() -> None:
    """AC2 branch 2 (G-Q4): synthetic-zero from off-exchange feeders
    renders `0.00%（场外申赎）` so it's not confused with a same-day
    on-exchange NAV coincidence."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    for asset_class in ("us_etf", "hk_etf", "qdii_global"):
        cell = _format_qdii_premium_cell(qdii_premium_pct=0.0,
                                         asset_class=asset_class)
        assert cell == "0.00%（场外申赎）"


def test_format_cell_positive_premium_renders_signed_two_decimals() -> None:
    """AC2 branch 3: on-exchange premium — always-signed, 2 decimals."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    cell = _format_qdii_premium_cell(qdii_premium_pct=0.0648,
                                     asset_class="us_etf")
    assert cell == "+6.48%"


def test_format_cell_negative_discount_renders_signed_two_decimals() -> None:
    """AC2 branch 3 (discount path): -0.34% on 513690."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    cell = _format_qdii_premium_cell(qdii_premium_pct=-0.0034,
                                     asset_class="hk_etf")
    assert cell == "-0.34%"


def test_format_cell_defensive_non_qdii_zero_returns_em_dash() -> None:
    """AC2 branch 4 (defensive): structurally impossible per
    qdii_premium_for_row routing, but rendered as `—` if it ever occurs."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    assert _format_qdii_premium_cell(qdii_premium_pct=0.0,
                                     asset_class="cn_etf") == "—"


def test_format_cell_never_contains_pipe_or_br() -> None:
    """AC3: every render path must keep the markdown row single-line."""
    from irc.memo.qdii_premium_lines import _format_qdii_premium_cell

    samples = (
        _format_qdii_premium_cell(None, "cn_etf"),
        _format_qdii_premium_cell(0.0, "us_etf"),
        _format_qdii_premium_cell(0.0648, "us_etf"),
        _format_qdii_premium_cell(-0.0034, "hk_etf"),
    )
    for s in samples:
        assert "|" not in s
        assert "<br>" not in s


def _fixed_clock() -> datetime:
    return datetime(2026, 5, 27, 15, 30, 0, tzinfo=timezone(timedelta(hours=8)))


def test_build_projection_sorts_rows_by_instrument_id() -> None:
    """AC6 + AC14(a): rows sorted by instrument_id ASC for two-run byte
    equality."""
    from irc.memo.qdii_premium_lines import build_qdii_premium_projection

    score_rows = [
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
        {"instrument_id": "017641", "name_cn": "国泰纳指联接",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0},
    ]
    proj = build_qdii_premium_projection(
        score_rows,
        evidence_cutoff="2026-05-26",
        now_fn=_fixed_clock,
    )
    iids = [r["instrument_id"] for r in proj["rows"]]
    assert iids == ["017641", "159501", "513690"]


def test_build_projection_blocking_flag_marks_above_threshold() -> None:
    """AC6: blocking = (pct is not None) AND (pct > threshold_pct)."""
    from irc.memo.qdii_premium_lines import build_qdii_premium_projection

    score_rows = [
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    by_iid = {r["instrument_id"]: r for r in proj["rows"]}
    assert by_iid["159501"]["blocking"] is True
    assert by_iid["513690"]["blocking"] is False


def test_build_projection_renders_cell_per_row() -> None:
    """AC6: each row carries `render_cell` (the picks-table cell value)
    so downstream consumers can echo the memo text verbatim."""
    from irc.memo.qdii_premium_lines import build_qdii_premium_projection

    score_rows = [
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    assert proj["rows"][0]["render_cell"] == "-0.34%"


def test_build_projection_threshold_and_metadata() -> None:
    """AC6: top-level fields generated_at, threshold_pct, evidence_cutoff."""
    from irc.memo.qdii_premium_lines import (
        QDII_PREMIUM_THRESHOLD_PCT,
        build_qdii_premium_projection,
    )

    proj = build_qdii_premium_projection(
        score_rows=[], evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    assert proj["threshold_pct"] == QDII_PREMIUM_THRESHOLD_PCT
    assert proj["evidence_cutoff"] == "2026-05-26"
    assert proj["generated_at"] == "2026-05-27T15:30:00+08:00"
    assert proj["rows"] == []


def test_build_projection_skips_rows_without_premium() -> None:
    """AC6: only rows whose qdii_premium_pct is not None are included.
    NG10 + G-Q11: a None value means data is unknown — excluded from §6
    and the artefact."""
    from irc.memo.qdii_premium_lines import build_qdii_premium_projection

    score_rows = [
        {"instrument_id": "513690", "name_cn": "港股红利",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
        {"instrument_id": "159949", "name_cn": "未知溢价",
         "asset_class": "us_etf", "qdii_premium_pct": None},
        {"instrument_id": "510300", "name_cn": "沪深300",
         "asset_class": "cn_etf", "qdii_premium_pct": None},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    iids = [r["instrument_id"] for r in proj["rows"]]
    assert iids == ["513690"]


def test_build_projection_is_deterministic_across_two_calls() -> None:
    """AC14: same inputs → byte-identical outputs."""
    import json
    from irc.memo.qdii_premium_lines import build_qdii_premium_projection

    score_rows = [
        {"instrument_id": "159501", "name_cn": "X", "asset_class": "us_etf",
         "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "Y", "asset_class": "hk_etf",
         "qdii_premium_pct": -0.0034},
    ]
    a = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock)
    b = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock)
    assert json.dumps(a, ensure_ascii=False, sort_keys=True) == \
        json.dumps(b, ensure_ascii=False, sort_keys=True)


def test_render_block_wraps_in_markers_and_lists_rows() -> None:
    """AC7: full block — marker BEGIN + header + per-row bullets +
    marker END. Above-threshold rows get （超阈值，已暂缓执行）."""
    from irc.memo.qdii_premium_lines import (
        QDII_PREMIUM_MARKER_BEGIN,
        QDII_PREMIUM_MARKER_END,
        build_qdii_premium_projection,
        render_qdii_premium_block,
    )

    score_rows = [
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0692},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    block = render_qdii_premium_block(proj)
    lines = block.splitlines()
    assert lines[0] == QDII_PREMIUM_MARKER_BEGIN
    assert lines[-1] == QDII_PREMIUM_MARKER_END
    assert "数据截止 2026-05-26" in lines[1]
    assert "阈值 5%" in lines[1]
    # Sorted by iid → 159501 before 513690.
    assert "159501 标普消费ETF：+6.92%（超阈值，已暂缓执行）" in block
    assert "513690 港股红利ETF博时：-0.34%" in block
    # The discount row is NOT marked as blocking.
    discount_line = next(
        l for l in lines if "513690" in l
    )
    assert "超阈值" not in discount_line


def test_render_block_empty_projection_returns_empty_string() -> None:
    """AC7: empty projection → empty string (caller falls back to legacy
    placeholder)."""
    from irc.memo.qdii_premium_lines import (
        build_qdii_premium_projection,
        render_qdii_premium_block,
    )

    proj = build_qdii_premium_projection(
        score_rows=[], evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    assert render_qdii_premium_block(proj) == ""


def test_format_prefix_for_blocking_row() -> None:
    """AC9 / G-Q3: ⛔ qdii_premium_too_high（{cell} > 5%，已暂缓）｜ — note
    the full-width ｜ (U+FF5C) separator."""
    from irc.memo.qdii_premium_lines import format_qdii_premium_prefix

    row = {
        "instrument_id": "159501", "blocking": True,
        "render_cell": "+6.92%",
    }
    prefix = format_qdii_premium_prefix(row)
    assert prefix == "⛔ qdii_premium_too_high（+6.92% > 5%，已暂缓）｜"
    # Separator is full-width (U+FF5C), distinct from half-width `|`.
    assert "｜" in prefix
    assert "|" not in prefix


def test_format_prefix_for_non_blocking_row_returns_empty_string() -> None:
    """AC9: rows whose `blocking` is False receive no prefix."""
    from irc.memo.qdii_premium_lines import format_qdii_premium_prefix

    row = {
        "instrument_id": "513690", "blocking": False,
        "render_cell": "-0.34%",
    }
    assert format_qdii_premium_prefix(row) == ""


def test_write_snapshot_always_writes_even_when_rows_empty(tmp_path: Path) -> None:
    """G-Q5: always-written invariant — empty rows list still produces
    a file with the four schema fields populated."""
    import json
    from irc.memo.qdii_premium_lines import (
        build_qdii_premium_projection,
        write_qdii_premium_snapshot,
    )

    proj = build_qdii_premium_projection(
        score_rows=[], evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    write_qdii_premium_snapshot(proj, out_dir=tmp_path)
    artefact = tmp_path / "qdii_premium.json"
    assert artefact.exists()
    payload = json.loads(artefact.read_text(encoding="utf-8"))
    assert payload["rows"] == []
    assert payload["threshold_pct"] == 0.05
    assert payload["evidence_cutoff"] == "2026-05-26"
    assert payload["generated_at"] == "2026-05-27T15:30:00+08:00"


def test_write_snapshot_two_runs_produce_byte_identical_file(tmp_path: Path) -> None:
    """AC14: stub clock + identical scoring → byte-identical files."""
    from irc.memo.qdii_premium_lines import (
        build_qdii_premium_projection,
        write_qdii_premium_snapshot,
    )

    score_rows = [
        {"instrument_id": "159501", "name_cn": "X", "asset_class": "us_etf",
         "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "Y", "asset_class": "hk_etf",
         "qdii_premium_pct": -0.0034},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock)

    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    write_qdii_premium_snapshot(proj, out_dir=a_dir)
    write_qdii_premium_snapshot(proj, out_dir=b_dir)
    a_bytes = (a_dir / "qdii_premium.json").read_bytes()
    b_bytes = (b_dir / "qdii_premium.json").read_bytes()
    assert a_bytes == b_bytes


def test_write_snapshot_emits_above_threshold_row_with_blocking_flag(
    tmp_path: Path,
) -> None:
    """AC6: 159501 at 6.92% renders blocking=True; 513690 at -0.34%
    renders blocking=False."""
    import json
    from irc.memo.qdii_premium_lines import (
        build_qdii_premium_projection,
        write_qdii_premium_snapshot,
    )

    score_rows = [
        {"instrument_id": "159501", "name_cn": "标普消费ETF",
         "asset_class": "us_etf", "qdii_premium_pct": 0.0692},
        {"instrument_id": "513690", "name_cn": "港股红利ETF博时",
         "asset_class": "hk_etf", "qdii_premium_pct": -0.0034},
    ]
    proj = build_qdii_premium_projection(
        score_rows, evidence_cutoff="2026-05-26", now_fn=_fixed_clock,
    )
    write_qdii_premium_snapshot(proj, out_dir=tmp_path)
    payload = json.loads(
        (tmp_path / "qdii_premium.json").read_text(encoding="utf-8")
    )
    by_iid = {r["instrument_id"]: r for r in payload["rows"]}
    assert by_iid["159501"]["blocking"] is True
    assert by_iid["159501"]["render_cell"] == "+6.92%"
    assert by_iid["513690"]["blocking"] is False
    assert by_iid["513690"]["render_cell"] == "-0.34%"
