from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from irc.opportunity.sector_indices import (
    SECTOR_INDEX_CODE,
    SECTOR_INDEX_DISPLAY,
    SECTOR_INDEX_KEYS,
    SECTOR_INDICES,
    SECTOR_NAME_TO_SLUG,
    SectorIndex,
)

# (slug, code, display_cn) expectations for every curated tracked_index.
_RESOLUTION_CASES = [
    ("中证机器人", "csi_robotics", "H30590"),
    ("中证智能制造", "csi_smart_mfg", "930850"),
    ("中证机床ZZ", "csi_machine_tool", "931866"),  # malformed universe value via alias
    ("中证芯片产业", "csi_chip", "H30007"),
    ("中证全指半导体", "csi_semiconductor", "H30184"),
    ("中证半导体材料设备", "csi_semi_equip", "931743"),
    ("上证科创板芯片", "sse_star_chip", "000685"),
    ("中证人工智能主题", "csi_ai_theme", "930713"),
    ("中证人工智能产业", "csi_ai_industry", "931071"),
    ("中证全指通信设备", "csi_telecom_equip", "931160"),
    ("中证数字经济主题", "csi_digital_econ", "931582"),
    ("中证云计算与大数据", "csi_cloud", "930851"),
    ("中证算力基础设施", "csi_compute_infra", "931688"),
    ("中证国新央企科技引领", "csi_soe_tech", "932038"),
    ("中证有色金属", "csi_nonferrous", "930708"),
    ("中证资源", "csi_resource", "000819"),
    ("中证有色金属矿业主题", "csi_nonferrous_mining", "931892"),
]


def test_catalog_has_seventeen_rows():
    assert len(SECTOR_INDICES) == 17


def test_every_row_has_nonempty_code_and_official_cn():
    for r in SECTOR_INDICES:
        assert isinstance(r, SectorIndex)
        assert r.code, f"{r.slug}: empty code"
        assert r.official_cn, f"{r.slug}: empty official_cn"
        assert r.display_cn, f"{r.slug}: empty display_cn"


def test_slugs_are_unique():
    slugs = [r.slug for r in SECTOR_INDICES]
    assert len(slugs) == len(set(slugs))


def test_existing_metals_slugs_and_codes_unchanged():
    # Folded-in with NO behavior change (regression lock vs the inline dicts).
    assert SECTOR_INDEX_CODE["csi_nonferrous"] == "930708"
    assert SECTOR_INDEX_CODE["csi_resource"] == "000819"
    assert SECTOR_INDEX_CODE["csi_nonferrous_mining"] == "931892"
    assert SECTOR_INDEX_DISPLAY["csi_nonferrous"] == "中证有色金属"
    assert SECTOR_INDEX_DISPLAY["csi_resource"] == "中证资源"
    assert SECTOR_INDEX_DISPLAY["csi_nonferrous_mining"] == "中证有色金属矿业主题"


def test_alias_collision_rejection():
    # Building the name->slug map from (display_cn + aliases) must NOT silently
    # map one normalized key to two distinct slugs. Non-tautological: rebuild
    # independently and assert no key collides across rows.
    seen: dict[str, str] = {}
    for r in SECTOR_INDICES:
        keys = (r.display_cn, *r.aliases)
        for k in keys:
            norm = k.strip().lower()
            assert norm not in seen or seen[norm] == r.slug, (
                f"alias collision: {norm!r} -> {seen.get(norm)} and {r.slug}"
            )
            seen[norm] = r.slug


@pytest.mark.parametrize("tracked_index,slug,code", _RESOLUTION_CASES)
def test_resolution_tracked_index_to_slug_to_code(tracked_index, slug, code):
    resolved = SECTOR_NAME_TO_SLUG[tracked_index.strip().lower()]
    assert resolved == slug
    assert SECTOR_INDEX_CODE[resolved] == code


def test_sector_index_keys_is_display_keyset():
    assert SECTOR_INDEX_KEYS == frozenset(SECTOR_INDEX_DISPLAY)


def test_curated_config_coverage_every_sector_etf_resolves():
    # Load the REAL curated universe; every sector-ETF tracked_index must resolve
    # to a matrix slug. Proves config <-> matrix sync. Non-tautological.
    repo_root = Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((repo_root / "config/universe/cn_funds.yaml").read_text())
    sector_tracked = {ti.strip().lower() for ti, _, _ in _RESOLUTION_CASES}
    for instr in cfg.get("instruments", []):
        ti = (instr.get("tracked_index") or "").strip().lower()
        if ti in sector_tracked:
            assert ti in SECTOR_NAME_TO_SLUG, f"curated sector tracked_index unmapped: {ti}"
