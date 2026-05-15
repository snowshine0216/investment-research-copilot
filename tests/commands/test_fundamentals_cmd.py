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
    mock_build.assert_called_once_with("沪深300", top_n=5)
    mock_write.assert_called_once()
    assert mock_write.call_args.args[1] == tmp_path / "data"


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
