"""Gate #3 grounded-broad-fund count (Phase A).

Replaces the broken snippet `lookthrough_key in {'csi300','csi500',...}`: the
opportunity report stores `lookthrough_key` as the Chinese DISPLAY name
(沪深300, 中证500, …) because the universe config uses a Chinese `tracked_index`,
so a slug-membership test always returns 0 — a false negative even when funds
ARE grounded.

This script instead:
  1. resolves each broad row's Chinese name -> canonical slug via the production
     inversion map (`_INDEX_NAME_TO_SLUG`), and
  2. checks ACTUAL PE-TTM grounding by reading the cached
     `index_valuation_history` the same way the loader does
     (`_index_valuation_metrics` -> non-None PE percentile).

"mapped_to_allowlist" = the row's index is one of the 4 production broad slugs;
"grounded" = that index actually has mature cached PE-TTM data this run. The gap
between them is the diagnostic (e.g. csi500/sse50 referenced but legulegu didn't
land their series).

Run from repo root:
    uv run python docs/2026-06-05-phase-a-broad-grounding/count_grounded.py \
        outputs/<YYYY-MM-DD>/opportunity_report.json [data/local.duckdb]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import duckdb

from irc.opportunity.inputs_loader import _index_valuation_metrics
from irc.opportunity.lookthrough import _INDEX_NAME_TO_SLUG

_ALLOWLIST: tuple[str, ...] = ("csi300", "csi500", "csi1000", "sse50")


def _slug_for(lookthrough_key: str | None) -> str | None:
    """Chinese display name (or alias) -> canonical slug; None if unrecognised."""
    return _INDEX_NAME_TO_SLUG.get((lookthrough_key or "").strip().lower())


def classify_broad_rows(rows: list[dict], con: duckdb.DuckDBPyConnection) -> dict:
    """Per broad_index row: resolve slug + real PE-TTM grounding from the cache."""
    broad = [r for r in rows if r.get("lookthrough_kind") == "broad_index"]
    detail = []
    for r in broad:
        key = r.get("lookthrough_key")
        slug = _slug_for(key)
        # _index_valuation_metrics does its own name->slug inversion, so pass the
        # raw (Chinese) key; pe_pct is non-None only when the cached series exists
        # AND clears the min-history maturity gate.
        _, _, _, pe_pct, _ = _index_valuation_metrics(con, key)
        detail.append(
            {
                "instrument_id": r.get("instrument_id"),
                "lookthrough_key": key,
                "slug": slug,
                "on_allowlist": slug in _ALLOWLIST,
                "grounded": pe_pct is not None,
            }
        )
    return {
        "broad_total": len(broad),
        "mapped_to_allowlist": sum(d["on_allowlist"] for d in detail),
        "grounded": sum(d["grounded"] for d in detail),
        "grounded_by_slug": dict(
            Counter(d["slug"] for d in detail if d["grounded"])
        ),
        "detail": detail,
    }


def main() -> int:
    report_path = sys.argv[1]
    db_path = sys.argv[2] if len(sys.argv) > 2 else "data/local.duckdb"
    rows = json.loads(Path(report_path).read_text(encoding="utf-8"))["rows"]
    con = duckdb.connect(db_path, read_only=True)
    s = classify_broad_rows(rows, con)
    print(f"broad_index rows:        {s['broad_total']}")
    print(f"mapped to allowlist:     {s['mapped_to_allowlist']}  (slug in {_ALLOWLIST})")
    print(f"grounded (real PE-TTM):  {s['grounded']}  {s['grounded_by_slug']}")
    print()
    print("  id        lookthrough_key            slug         allowlist  grounded")
    for d in s["detail"]:
        print(
            f"  {str(d['instrument_id']):9s} {str(d['lookthrough_key']):24s} "
            f"{str(d['slug']):12s} {str(d['on_allowlist']):9s} {d['grounded']}"
        )
    print()
    ok = s["grounded"] >= 9
    print(f"gate #3 (grounded >= 9): {'PASS' if ok else 'NOT MET'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
