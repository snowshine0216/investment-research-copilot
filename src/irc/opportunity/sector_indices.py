"""Single source-of-truth catalog for CN sector-index valuation onboarding
(Phase B). Pure, no I/O. Folds in the 3 existing metals slugs (no behavior
change) plus 14 new sector slugs — 17 total. The fetcher, the lookthrough
resolver, and the read-gate all import the derived maps from here so the
catalog cannot drift across files.

`display_cn` is the canonical universe `tracked_index` string (the resolution
key). `official_cn` is the `指数全称` from `index_csindex_all` — the live
identity-guard target. `aliases` carry malformed/colloquial universe spellings
(e.g. `中证机床ZZ`) so B1 needs NO `config/universe/*.yaml` edit.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SectorIndex:
    slug: str
    code: str  # csindex symbol for stock_zh_index_value_csindex
    display_cn: str  # canonical universe tracked_index string (resolution key)
    official_cn: str  # 指数全称 from index_csindex_all (identity-guard target)
    aliases: tuple[str, ...] = field(default=())


SECTOR_INDICES: tuple[SectorIndex, ...] = (
    SectorIndex("csi_robotics", "H30590", "中证机器人", "中证机器人指数"),
    SectorIndex("csi_smart_mfg", "930850", "中证智能制造", "中证智能制造主题指数"),
    SectorIndex("csi_machine_tool", "931866", "中证机床", "中证机床指数", ("中证机床ZZ",)),
    SectorIndex("csi_chip", "H30007", "中证芯片产业", "中证芯片产业指数"),
    SectorIndex(
        "csi_semiconductor", "H30184", "中证全指半导体",
        "中证全指半导体产品与设备指数",
    ),
    SectorIndex("csi_semi_equip", "931743", "中证半导体材料设备", "中证半导体材料设备主题指数"),
    SectorIndex("sse_star_chip", "000685", "上证科创板芯片", "上证科创板芯片指数"),
    SectorIndex("csi_ai_theme", "930713", "中证人工智能主题", "中证人工智能主题指数"),
    SectorIndex("csi_ai_industry", "931071", "中证人工智能产业", "中证人工智能产业指数"),
    SectorIndex("csi_telecom_equip", "931160", "中证全指通信设备", "中证全指通信设备指数"),
    SectorIndex("csi_digital_econ", "931582", "中证数字经济主题", "中证数字经济主题指数"),
    SectorIndex("csi_cloud", "930851", "中证云计算与大数据", "中证云计算与大数据主题指数"),
    SectorIndex("csi_compute_infra", "931688", "中证算力基础设施", "中证算力基础设施主题指数"),
    SectorIndex("csi_soe_tech", "932038", "中证国新央企科技引领", "中证国新央企科技引领指数"),
    SectorIndex("csi_nonferrous", "930708", "中证有色金属", "中证有色金属指数", ("中证有色",)),
    SectorIndex("csi_resource", "000819", "中证资源", "中证申万有色金属指数"),
    SectorIndex(
        "csi_nonferrous_mining", "931892", "中证有色金属矿业主题",
        "中证有色金属矿业主题指数",
    ),
)


def _build_name_to_slug(rows: tuple[SectorIndex, ...]) -> dict[str, str]:
    """Normalized (display_cn + aliases) -> slug. Raises on a collision so a
    malformed catalog fails loudly instead of silently overwriting."""
    out: dict[str, str] = {}
    for r in rows:
        for name in (r.display_cn, *r.aliases):
            key = name.strip().lower()
            if key in out and out[key] != r.slug:
                raise ValueError(f"alias collision: {key!r} -> {out[key]} and {r.slug}")
            out[key] = r.slug
    return out


SECTOR_INDEX_CODE: dict[str, str] = {r.slug: r.code for r in SECTOR_INDICES}
SECTOR_INDEX_DISPLAY: dict[str, str] = {r.slug: r.display_cn for r in SECTOR_INDICES}
SECTOR_INDEX_KEYS: frozenset[str] = frozenset(SECTOR_INDEX_DISPLAY)
SECTOR_NAME_TO_SLUG: dict[str, str] = _build_name_to_slug(SECTOR_INDICES)
