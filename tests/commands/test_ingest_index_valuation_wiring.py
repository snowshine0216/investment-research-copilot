from __future__ import annotations

import inspect

from irc.commands import ingest_cmd


def test_run_ingest_calls_index_valuation_ingestor() -> None:
    """run_ingest must invoke the index-valuation ingestor over the production
    legulegu allowlist with replace_keys=True so the cached table self-migrates
    on `irc run --from ingest`."""
    src = inspect.getsource(ingest_cmd.run_ingest)
    assert "ingest_index_valuation_history" in src
    assert "_LEGULEGU_INDEX_SYMBOL" in src
    assert "replace_keys=True" in src


def test_ingest_cmd_imports_broad_index_keys_and_ingestor() -> None:
    body = inspect.getsource(ingest_cmd)
    assert "from irc.data.index_valuation_ingestor import" in body
    assert "_LEGULEGU_INDEX_SYMBOL" in body


def test_run_ingest_calls_sector_index_valuation_leg() -> None:
    """run_ingest must invoke a SECOND ingest leg over the sector-index keys with
    the csindex sector fetcher, so the accumulate-forward table grows weekly."""
    src = inspect.getsource(ingest_cmd.run_ingest)
    assert "_SECTOR_INDEX_KEYS" in src
    assert "fetch_cn_sector_index_valuation_history" in src


def test_ingest_cmd_imports_sector_keys_and_sector_fetcher() -> None:
    body = inspect.getsource(ingest_cmd)
    assert "_SECTOR_INDEX_KEYS" in body
    assert "fetch_cn_sector_index_valuation_history" in body
