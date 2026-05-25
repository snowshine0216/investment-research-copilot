"""Role-bucket failure banner (item 010, 2026-05-19)."""
from __future__ import annotations

from irc.memo.diagnostics import compose_role_bucket_banner


def _row(stage: str, status: str, role: str, count: int = 0, reason: str = "") -> dict:
    return {
        "stage": stage,
        "status": status,
        "asset_class": "",
        "theme": "",
        "role": role,
        "reason": reason,
        "count": count,
    }


def test_no_failures_returns_empty() -> None:
    rows = [
        _row("role_bucket", "bucketed", "core_us_equity", 4),
        _row("role_bucket", "bucketed", "defensive_us_bond", 2),
    ]
    assert compose_role_bucket_banner(rows) == ()


def test_failed_role_emits_banner_with_role_names() -> None:
    rows = [
        _row("role_bucket", "bucketed", "core_us_equity", 4),
        _row("role_bucket", "failed", "satellite_cn_tech", reason="below fail_below"),
        _row("role_bucket", "failed", "hedge_low_correlation", reason="below fail_below"),
    ]
    banner = compose_role_bucket_banner(rows)
    assert len(banner) == 2
    assert banner[0].startswith("数据覆盖不完整提示")
    assert "覆盖警告" not in banner[0]
    assert "2/3" in banner[0]
    assert "satellite_cn_tech" in banner[0]
    assert "hedge_low_correlation" in banner[0]
    assert "残缺集合中的最优选" in banner[1]


def test_banner_dedupes_role_names() -> None:
    """Defensive: if upstream emits duplicate failed rows for the same
    role, the banner still lists each role once."""
    rows = [
        _row("role_bucket", "bucketed", "core_us_equity", 4),
        _row("role_bucket", "failed", "X"),
        _row("role_bucket", "failed", "X"),
        _row("role_bucket", "failed", "Y"),
    ]
    banner = compose_role_bucket_banner(rows)
    assert banner[0].count("X") == 1
    assert "Y" in banner[0]


def test_empty_input_returns_empty() -> None:
    assert compose_role_bucket_banner([]) == ()
    assert compose_role_bucket_banner(None) == ()


def test_ignores_non_role_bucket_rows() -> None:
    rows = [
        _row("hard_filter", "rejected", "X", 100),  # not a role_bucket row
        _row("role_bucket", "bucketed", "core_us_equity", 4),
    ]
    assert compose_role_bucket_banner(rows) == ()
