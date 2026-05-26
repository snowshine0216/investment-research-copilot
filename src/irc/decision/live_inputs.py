"""Read-only I/O wrapper around `data/local.duckdb` for the decision +
memo renderers.

Exposes a single public function, `read_live_decision_inputs`, that returns
the latest macro snapshot + per-instrument weekly returns. Graceful degrade
(`({}, {})` on any failure) is preserved so callers can render placeholder
text rather than crash. Imported by both `commands/decision_cmd.py` and
`commands/memo_cmd.py` — single locus, no two-place drift.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def read_live_decision_inputs(
    repo_root: Path,
    instrument_ids: set[str],
) -> tuple[dict[str, float], dict[str, float]]:
    """Read latest macro snapshot + per-instrument weekly returns from the
    local DuckDB. Returns ``(macro_snapshot, weekly_return_by_id)``.

    Empty dicts on any failure — the renderer gracefully shows "未知" when
    a value is missing. Pure read; no caching, no mutation.
    """
    db_path = repo_root / "data" / "local.duckdb"
    if not db_path.exists():
        return {}, {}
    try:
        import duckdb  # local import — keep callers fast when db is absent
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        # Locked DBs (concurrent `irc run --only ingest`) and other I/O
        # failures should not block the decision report; render with
        # placeholders instead.
        print(
            f"WARNING: decision report could not read live macro/returns "
            f"({exc.__class__.__name__}); per-pick triggers will show "
            f"'未知 / unknown'."
        )
        return {}, {}
    macro: dict[str, float] = {}
    returns: dict[str, float] = {}
    try:
        macro_df = con.execute(
            "SELECT series_id, value FROM ("
            "  SELECT series_id, value, "
            "         ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY date DESC) AS rn"
            "  FROM macro_series"
            ") WHERE rn = 1"
        ).fetchdf()
        for _, r in macro_df.iterrows():
            try:
                macro[str(r["series_id"])] = float(r["value"])
            except (TypeError, ValueError):
                continue
        for iid in instrument_ids:
            navs = con.execute(
                "SELECT nav FROM nav_history WHERE instrument_id = ? "
                "ORDER BY date DESC LIMIT 8",
                [iid],
            ).fetchdf()
            if len(navs) < 5:
                if os.environ.get("DEBUG"):
                    print(
                        f"DEBUG: {iid} has {len(navs)} NAV rows (<5 threshold); "
                        "skipping weekly return.",
                        file=sys.stderr,
                    )
                continue
            latest = float(navs.iloc[0]["nav"])
            prior = float(navs.iloc[-1]["nav"])
            if prior > 0:
                returns[iid] = latest / prior - 1.0
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        print(
            f"WARNING: live_inputs query failed ({exc.__class__.__name__}: {exc}); "
            "macro snapshot and weekly returns will be empty — all triggers show ⚠.",
            file=sys.stderr,
        )
    finally:
        con.close()
    return macro, returns
