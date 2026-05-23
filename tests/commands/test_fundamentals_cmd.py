from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from irc.commands.fundamentals_cmd import run_snapshot_rebuild
from irc.fundamentals.types import ConstituentSnapshot


def _snapshot(target: str = "沪深300") -> ConstituentSnapshot:
    return ConstituentSnapshot(
        lookthrough_target=target,
        as_of_iso="2026-05-15",
        constituents=(),
        filings=(),
        broker_reports=(),
        failure_reasons=(),
    )


def test_snapshot_rebuild_requires_at_least_one_target(tmp_path: Path) -> None:
    rc = run_snapshot_rebuild(repo_root=str(tmp_path), targets=(), top_n=10)

    assert rc == 2


def test_snapshot_rebuild_builds_and_writes_each_target(tmp_path: Path) -> None:
    output_path = tmp_path / "data" / "fundamentals" / "2026Q1" / "沪深300.json"
    with patch(
        "irc.commands.fundamentals_cmd.build_snapshot",
        return_value=_snapshot(),
    ) as mock_build, patch(
        "irc.commands.fundamentals_cmd.write_snapshot",
        return_value=output_path,
    ) as mock_write:
        rc = run_snapshot_rebuild(
            repo_root=str(tmp_path),
            targets=("沪深300",),
            top_n=5,
        )

    assert rc == 0
    call_args = mock_build.call_args
    assert call_args.args[0].display_cn == "沪深300"
    assert call_args.args[0].kind in ("broad_index", "sector_theme", "qdii_us", "qdii_hk")
    assert call_args.kwargs == {"top_n": 5}
    mock_write.assert_called_once()
    assert mock_write.call_args.args[1] == tmp_path / "data"


def test_snapshot_rebuild_target_all_expands_registered_targets(tmp_path: Path) -> None:
    output_path = tmp_path / "data" / "fundamentals" / "2026Q1" / "沪深300.json"
    with patch(
        "irc.commands.fundamentals_cmd.registered_snapshot_targets",
        return_value=("沪深300", "中证500"),
    ), patch(
        "irc.commands.fundamentals_cmd.build_snapshot",
        side_effect=lambda lt, *, top_n: _snapshot(lt.display_cn),
    ) as mock_build, patch(
        "irc.commands.fundamentals_cmd.write_snapshot",
        return_value=output_path,
    ) as mock_write:
        rc = run_snapshot_rebuild(
            repo_root=str(tmp_path),
            targets=("all",),
            top_n=5,
        )

    assert rc == 0
    assert [call.args[0].display_cn for call in mock_build.call_args_list] == ["沪深300", "中证500"]
    assert [call.kwargs for call in mock_build.call_args_list] == [{"top_n": 5}, {"top_n": 5}]
    assert mock_write.call_count == 2


def test_snapshot_rebuild_target_all_deduplicates_explicit_targets(tmp_path: Path) -> None:
    output_path = tmp_path / "data" / "fundamentals" / "2026Q1" / "沪深300.json"
    with patch(
        "irc.commands.fundamentals_cmd.registered_snapshot_targets",
        return_value=("沪深300", "中证500"),
    ), patch(
        "irc.commands.fundamentals_cmd.build_snapshot",
        side_effect=lambda lt, *, top_n: _snapshot(lt.display_cn),
    ) as mock_build, patch(
        "irc.commands.fundamentals_cmd.write_snapshot",
        return_value=output_path,
    ):
        rc = run_snapshot_rebuild(
            repo_root=str(tmp_path),
            targets=("沪深300", "all", "中证500"),
            top_n=3,
        )

    assert rc == 0
    assert [call.args[0].display_cn for call in mock_build.call_args_list] == ["沪深300", "中证500"]


def test_snapshot_rebuild_warns_but_completes_when_snapshot_has_failures(tmp_path: Path) -> None:
    failed_snapshot = ConstituentSnapshot(
        lookthrough_target="未知指数",
        as_of_iso="2026-05-15",
        constituents=(),
        filings=(),
        broker_reports=(),
        failure_reasons=("unknown lookthrough_target: 未知指数",),
    )
    with patch(
        "irc.commands.fundamentals_cmd.build_snapshot",
        return_value=failed_snapshot,
    ), patch(
        "irc.commands.fundamentals_cmd.write_snapshot",
        return_value=tmp_path / "data" / "fundamentals" / "2026Q1" / "未知指数.json",
    ):
        rc = run_snapshot_rebuild(
            repo_root=str(tmp_path),
            targets=("未知指数",),
            top_n=10,
        )

    assert rc == 0
