from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "src" / "irc" / "templates" / "config" / "universe" / "cn_funds.yaml"

# Five instrument IDs that appeared in 2026-05-18 outputs without a name_cn,
# producing "<id> <id>" lines in discipline_report.md. The user-side
# config/universe/cn_funds.yaml is gitignored, so the durable fix lives in
# the template that ships via `irc init`. See
# docs/2026-05-18-fix-memo-audit/items/003-spec.md.
_RECENTLY_UNNAMED_IDS: tuple[str, ...] = (
    "110022", "005827", "163417", "161005", "512960",
)


def test_recently_unnamed_ids_have_names_in_template() -> None:
    data = yaml.safe_load(TEMPLATE.read_text())
    by_id = {row["instrument_id"]: row for row in data["instruments"]}
    for iid in _RECENTLY_UNNAMED_IDS:
        assert iid in by_id, f"{iid} missing from template cn_funds.yaml"
        name = by_id[iid].get("name_cn", "")
        assert name, f"{iid} has empty name_cn in template"
        assert name != iid, f"{iid} name_cn is the id itself"
