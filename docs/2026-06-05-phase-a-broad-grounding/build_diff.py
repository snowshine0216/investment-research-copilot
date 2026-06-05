"""Phase A before/after diff (gate #5). Reads two opportunity_report.json files
(baseline vs Phase A) on the broad-index subset and writes before-after.md.

Run from repo root:
    uv run python docs/2026-06-05-phase-a-broad-grounding/build_diff.py \
        outputs/_phase_a_baseline/opportunity_report.json \
        outputs/_phase_a_after/opportunity_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_DIVERGENCE = "valuation_price_fundamental_divergence"


def _broad_rows(report_path: str) -> dict[str, dict]:
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for row in data["rows"]:
        if row.get("lookthrough_kind") != "broad_index":
            continue
        out[row["instrument_id"]] = {
            "name_cn": row["name_cn"],
            "valuation_state": row["valuation_state"],
            "divergence": _DIVERGENCE in row.get("advisory_gaps", []),
            "lookthrough_key": row.get("lookthrough_key"),
        }
    return out


def main() -> int:
    baseline_path, after_path = sys.argv[1], sys.argv[2]
    before = _broad_rows(baseline_path)
    after = _broad_rows(after_path)
    ids = sorted(set(before) | set(after))
    lines = [
        "# Phase A — broad-index grounding: before/after",
        "",
        "Broad-index funds only. `valuation_state` is the headline axis; "
        "`divergence` = the price/fundamental advisory (`证据缺口：价格与基本面估值背离`).",
        "",
        "| id | name | state (before) | state (after) | divergence (after) | flipped |",
        "|---|---|---|---|---|---|",
    ]
    flips = 0
    for iid in ids:
        b = before.get(iid, {})
        a = after.get(iid, {})
        bs = b.get("valuation_state", "—")
        as_ = a.get("valuation_state", "—")
        flipped = "✅" if (bs != as_ and as_ != "—") else ""
        if flipped:
            flips += 1
        div = "⚠️" if a.get("divergence") else ""
        name = a.get("name_cn") or b.get("name_cn") or ""
        lines.append(f"| {iid} | {name} | {bs} | {as_} | {div} | {flipped} |")
    lines += [
        "",
        f"Broad funds compared: {len(ids)}. valuation_state flips: {flips}.",
        "",
        "Manual eyeball (gate #5): confirm state flips on the grounded funds, the "
        "newly-firing divergence advisory, and that 161721 / 003318 / 标普红利低波50 "
        "do NOT appear here (they stayed on NAV / Phase-D, not the broad path).",
    ]
    out_path = Path(__file__).parent / "before-after.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
