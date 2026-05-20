from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "src" / "irc" / "templates" / "config" / "universe" / "cn_funds.yaml"
QDII_US_TEMPLATE = REPO / "src" / "irc" / "templates" / "config" / "universe" / "qdii_us.yaml"

# Five instrument IDs that appeared in 2026-05-18 outputs without a name_cn,
# producing "<id> <id>" lines in discipline_report.md. The user-side
# config/universe/cn_funds.yaml is gitignored, so the durable fix lives in
# the template that ships via `irc init`. See
# docs/2026-05-18-fix-memo-audit/items/003-spec.md.
_RECENTLY_UNNAMED_IDS: tuple[str, ...] = (
    "110022", "005827", "163417", "161005", "512960",
)

# US-bond QDII feeders required by the defensive_us_bond role bucket.
# Without these, the bucket returns 0 candidates (E5 universe gap).
# See docs/2026-05-20-e5-role-bucket-fixes/items/002-plan.md.
_US_BOND_QDII_IDS: tuple[str, ...] = ("161716", "003719", "006308")


def test_recently_unnamed_ids_have_names_in_template() -> None:
    data = yaml.safe_load(TEMPLATE.read_text())
    by_id = {row["instrument_id"]: row for row in data["instruments"]}
    for iid in _RECENTLY_UNNAMED_IDS:
        assert iid in by_id, f"{iid} missing from template cn_funds.yaml"
        name = by_id[iid].get("name_cn", "")
        assert name, f"{iid} has empty name_cn in template"
        assert name != iid, f"{iid} name_cn is the id itself"


def test_us_bond_qdii_feeders_present_in_template() -> None:
    """defensive_us_bond bucket needs us_etf rows with 'bond' in tracked_index.
    Template must ship at least three so a fresh `irc init` clears the gap."""
    data = yaml.safe_load(QDII_US_TEMPLATE.read_text())
    by_id = {row["instrument_id"]: row for row in data["instruments"]}
    for iid in _US_BOND_QDII_IDS:
        row = by_id.get(iid)
        assert row is not None, f"{iid} missing from template qdii_us.yaml"
        assert row["asset_class"] == "us_etf", f"{iid} must be us_etf for predicate match"
        assert "bond" in row["tracked_index"].lower(), (
            f"{iid} tracked_index must contain 'bond' (case-insensitive) — got {row['tracked_index']!r}"
        )
