from __future__ import annotations

import inspect

from irc.commands import ingest_cmd


def test_run_ingest_calls_index_valuation_ingestor() -> None:
    """run_ingest must invoke the index-valuation ingestor over the broad-index
    keys so the cached table is refreshed on `irc run --from ingest`."""
    src = inspect.getsource(ingest_cmd.run_ingest)
    assert "ingest_index_valuation_history" in src
    assert "_BROAD_INDEX_KEYS" in src


def test_ingest_cmd_imports_broad_index_keys_and_ingestor() -> None:
    body = inspect.getsource(ingest_cmd)
    assert "from irc.data.index_valuation_ingestor import" in body
    assert "_BROAD_INDEX_KEYS" in body
