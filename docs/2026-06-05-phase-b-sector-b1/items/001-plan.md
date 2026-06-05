# Phase B Sector Expansion — B1 Data Onboarding (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Onboard 17 CN sector-index PE-TTM series (14 new + 3 existing metals) into the proven csindex valuation seam via a single source-of-truth catalog module, with activation gated OFF (empty allowlist) so production output is byte-identical until series mature and a human reviews B2.

**Architecture:** New pure module `src/irc/opportunity/sector_indices.py` holds the `SectorIndex` table + derived maps; `lookthrough.py` and `akshare_index_valuation.py` import those maps (dropping their inline 3-entry sector dicts); a new config allowlist `sector_index_grounding.activated_slugs` is threaded explicitly (keyword-only, no global read) from `run_opportunity` down to a new short-circuit gate in `_index_valuation_metrics`. Accumulation (ingest) is unchanged — it auto-iterates `_SECTOR_INDEX_KEYS`, which now contains all 17 slugs.

**Tech Stack:** Python 3.12, uv, pytest, ruff, DuckDB, pandas, frozen dataclasses, pydantic-settings (FrozenModel).

---

## Scope (read before starting)

- **IN (this plan):** SoT catalog module, fetcher import swap, `activated_slugs` config + read-gate, explicit threading, all structural + activation-gate + threading tests, the strengthened live identity guard (authored only — NOT executed against the network), per-slug ingest audit helper, docs (CONTEXT.md / CHANGELOG / ROADMAP).
- **OUT (do NOT touch):** B2 activation (no slug ever added to the allowlist here — it stays `[]`); any `config/universe/*.yaml` value edit (the `中证机床ZZ` malformed value is resolved purely by an alias); a sector PB source; the `中证机床ZZ` universe rename.
- **Load-bearing invariant:** with the allowlist empty, `irc opportunity` output is **byte-identical** to `main`. The non-activated sector short-circuit MUST return the full `(None, None, None, None, None)` tuple (withholds raw `pe_ttm/pb/dividend_yield` AND both percentiles), because the raw metrics also feed `OpportunityInput`. A withheld-percentile-only short-circuit is WRONG.
- **Gate posture (do not mis-judge in verify/review):** Gate #3 (grounded > 0) is **NOT claimed** at B1 — grounded count = 0 by design; the ingest audit showing all 17 slugs accumulating / 0 mature / 0 grounded is the EXPECTED state. Gate #5 is **N/A** (no recommendation change; empty diff expected). The live identity guard's *execution* (real AkShare) is a human hard-stop — author the test, do NOT run it in the autonomous flow.

---

## Verified facts (confirmed by reading the real code — do not re-derive)

These are the REAL symbol names and line anchors. The impl agent should trust these over any line numbers in the spec.

- **Threading chain (real):** `run_opportunity` (`src/irc/commands/opportunity_cmd.py:1434`, calls `_build_rows` at line 1497 with `lookthrough_cfg=bundle.valuation_buckets.active_fund_lookthrough` at 1506) → `_build_rows` (`opportunity_cmd.py:699`, keyword-only `lookthrough_cfg` at 715; calls `_build_input` at 833) → `_build_input` (`src/irc/opportunity/inputs_build.py:15`, keyword-only `lookthrough_cfg` at 25; calls `populate_inputs` at 65) → `populate_inputs` (`src/irc/opportunity/inputs_loader.py:253`, keyword-only `lookthrough_cfg` at 260; calls `_index_valuation_metrics` at 302) → `_index_valuation_metrics` (`inputs_loader.py:154`).
- **`ValuationBucketsConfig`** lives in `src/irc/schemas/valuation.py:33`; it already has `active_fund_lookthrough: ActiveFundLookthroughConfig`. `ActiveFundLookthroughConfig` is at line 21. Both subclass `FrozenModel` (from `irc.schemas._types`).
- **Config is loaded** via `src/irc/config_loader.py:26` (`"config/valuation_buckets.yaml": ValuationBucketsConfig`) and exposed as `bundle.valuation_buckets` (`config_loader.py:92`). There is **NO committed `config/valuation_buckets.yaml`** — the template at `src/irc/templates/config/valuation_buckets.yaml` is scaffolded into `config/` by `irc init`.
- **`lookthrough.py` current sector dicts:** `_SECTOR_INDEX_DISPLAY` (lines 67-71, 3 entries), `_SECTOR_INDEX_KEYS` (line 73), `_INDEX_NAME_TO_SLUG` (lines 77-80, sector names + `"中证有色" → csi_nonferrous` alias), `_INDEX_VALUATION_KEYS` (line 84 = `_BROAD_INDEX_KEYS | _SECTOR_INDEX_KEYS`). `_BROAD_INDEX_KEYS` (line 61) is untouched.
- **`akshare_index_valuation.py`** has inline `_SECTOR_INDEX_CODE` (lines 47-51, 3 entries) consumed by `fetch_cn_sector_index_valuation_history` (line 184, `code = _SECTOR_INDEX_CODE.get(index_key)` at 190). It already imports `_BROAD_INDEX_DISPLAY` from `lookthrough` (line 27) — same dependency direction.
- **`_index_valuation_metrics`** (`inputs_loader.py:154-187`): signature `(con, tracked_index)`; normalizes `norm = (tracked_index or "").strip().lower() or None`, resolves `slug = _INDEX_NAME_TO_SLUG.get(norm) or norm` (line 169), tests `slug not in _INDEX_VALUATION_KEYS` (line 170). Returns 5-tuple `(pe, pb, div, pe_pct, pb_pct)`.
- **Ingest leg (unchanged):** `src/irc/commands/ingest_cmd.py:587` already calls `ingest_index_valuation_history(con, tuple(sorted(_SECTOR_INDEX_KEYS)), fetch=fetch_cn_sector_index_valuation_history, ...)`. New slugs are picked up automatically because `_SECTOR_INDEX_KEYS` grows. The aggregate count is at `index_valuation_ingestor.py:57` (`return len(params)`).
- **Curated universe (confirmed present in `config/universe/cn_funds.yaml`):** all 14 sector `tracked_index` strings exist (lines 94, 118-167), including the malformed `中证机床ZZ` at line 133. The 3 metals slugs (`中证有色金属`, `中证资源`, `中证有色金属矿业主题`) are **NOT** in `cn_funds.yaml` — they arise from the `theme: metals` narrative path. So the curated-config coverage test must only assert the 14 sector-ETF tracked indices resolve.
- **Test seed helper:** `tests/opportunity/test_inputs_loader.py:196` defines `_seed_index_valuation_history(con, index_key, pe_pb_pairs, base_date=date(2025,1,1))` (one row per consecutive day). Reuse this pattern for the gate tests. `ensure_schema` from `irc.data.duckdb_helper` creates `index_valuation_history`.
- **Live marker:** `pytest.mark.live_akshare` is registered in `pyproject.toml:52`. Double-gate pattern: `pytestmark = [pytest.mark.live_akshare, pytest.mark.skipif(os.environ.get("IRC_RUN_LIVE_AKSHARE") != "1", ...)]` (see existing `tests/fundamentals/test_sector_index_valuation_live.py`).

---

## The 17-row catalog matrix (spec §4 — copy verbatim into Task 1)

| slug | code | display_cn (`tracked_index`) | official_cn (`指数全称`) | aliases |
|---|---|---|---|---|
| `csi_robotics` | `H30590` | 中证机器人 | 中证机器人指数 | — |
| `csi_smart_mfg` | `930850` | 中证智能制造 | 中证智能制造主题指数 | — |
| `csi_machine_tool` | `931866` | 中证机床 | 中证机床指数 | `中证机床ZZ` |
| `csi_chip` | `H30007` | 中证芯片产业 | 中证芯片产业指数 | — |
| `csi_semiconductor` | `H30184` | 中证全指半导体 | 中证全指半导体产品与设备指数 | — |
| `csi_semi_equip` | `931743` | 中证半导体材料设备 | 中证半导体材料设备主题指数 | — |
| `sse_star_chip` | `000685` | 上证科创板芯片 | 上证科创板芯片指数 | — |
| `csi_ai_theme` | `930713` | 中证人工智能主题 | 中证人工智能主题指数 | — |
| `csi_ai_industry` | `931071` | 中证人工智能产业 | 中证人工智能产业指数 | — |
| `csi_telecom_equip` | `931160` | 中证全指通信设备 | 中证全指通信设备指数 | — |
| `csi_digital_econ` | `931582` | 中证数字经济主题 | 中证数字经济主题指数 | — |
| `csi_cloud` | `930851` | 中证云计算与大数据 | 中证云计算与大数据主题指数 | — |
| `csi_compute_infra` | `931688` | 中证算力基础设施 | 中证算力基础设施主题指数 | — |
| `csi_soe_tech` | `932038` | 中证国新央企科技引领 | 中证国新央企科技引领指数 | — |
| `csi_nonferrous` | `930708` | 中证有色金属 | 中证有色金属指数 | `中证有色` |
| `csi_resource` | `000819` | 中证资源 | 中证申万有色金属指数 | — |
| `csi_nonferrous_mining` | `931892` | 中证有色金属矿业主题 | 中证有色金属矿业主题指数 | — |

> **Alias note:** the `中证机床ZZ` alias on `csi_machine_tool` is what resolves the malformed universe value — `display_cn` stays the clean `中证机床` (NOT `中证机床ZZ`). The `中证有色` alias on `csi_nonferrous` preserves the existing colloquial-short-form behavior from `lookthrough.py:79`.

---

## File structure (decomposition)

- **Create** `src/irc/opportunity/sector_indices.py` — pure SoT catalog (< 200 lines, no I/O).
- **Create** `tests/opportunity/test_sector_indices.py` — SoT structural + alias-collision + resolution + curated-config coverage tests.
- **Modify** `src/irc/opportunity/lookthrough.py` — drop inline 3-entry sector dicts; import derived maps; recompose `_SECTOR_INDEX_KEYS` / `_SECTOR_INDEX_DISPLAY` / `_INDEX_NAME_TO_SLUG` / `_INDEX_VALUATION_KEYS` from the SoT.
- **Modify** `src/irc/fundamentals/akshare_index_valuation.py` — drop inline `_SECTOR_INDEX_CODE`; import `SECTOR_INDEX_CODE` from the SoT.
- **Modify** `src/irc/schemas/valuation.py` — add `SectorIndexGroundingConfig` nested model + `sector_index_grounding` field on `ValuationBucketsConfig`.
- **Modify** `src/irc/templates/config/valuation_buckets.yaml` — add `sector_index_grounding: { activated_slugs: [] }`.
- **Modify** `src/irc/opportunity/inputs_loader.py` — add keyword-only `activated_sector_slugs` to `_index_valuation_metrics` (short-circuit gate) and to `populate_inputs` (forwarding).
- **Modify** `src/irc/opportunity/inputs_build.py` — forward `activated_sector_slugs` through `_build_input`.
- **Modify** `src/irc/commands/opportunity_cmd.py` — forward `activated_sector_slugs` through `_build_rows`; source it from `bundle.valuation_buckets.sector_index_grounding.activated_slugs` in `run_opportunity`.
- **Modify** `src/irc/data/index_valuation_ingestor.py` — add `audit_sector_ingest(con) -> tuple[...]` per-slug audit helper.
- **Modify** tests: `tests/opportunity/test_lookthrough_sector_keys.py` (update to 17-slug SoT-backed expectations), `tests/fundamentals/test_sector_index_valuation_live.py` (strengthen identity guard), and add `tests/data/test_sector_ingest_audit.py`, plus gate/threading tests in `tests/opportunity/test_inputs_loader.py` (or a new `tests/opportunity/test_index_valuation_gate.py`).
- **Modify** docs: `CONTEXT.md` ("Valuation inputs"), `CHANGELOG.md` (`[Unreleased]`), `docs/ROADMAP.md` (Phase B → B1 done).

---

## Task 1: SoT catalog module `sector_indices.py`

**Files:**
- Create: `src/irc/opportunity/sector_indices.py`
- Test: `tests/opportunity/test_sector_indices.py`

- [ ] **Step 1: Write the failing SoT-contract + alias-collision + resolution test**

Create `tests/opportunity/test_sector_indices.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/opportunity/test_sector_indices.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'irc.opportunity.sector_indices'`.

- [ ] **Step 3: Write the SoT module**

Create `src/irc/opportunity/sector_indices.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/opportunity/test_sector_indices.py -q`
Expected: PASS (all tests green, 17-row catalog).

- [ ] **Step 5: Lint the new module**

Run: `uv run ruff check src/irc/opportunity/sector_indices.py tests/opportunity/test_sector_indices.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/sector_indices.py tests/opportunity/test_sector_indices.py
git commit -m "feat(sector-b1): SoT sector-index catalog (17 slugs, derived maps)"
```

---

## Task 2: `lookthrough.py` imports the derived maps

**Files:**
- Modify: `src/irc/opportunity/lookthrough.py` (lines 63-84)
- Test: `tests/opportunity/test_lookthrough_sector_keys.py` (update existing)

- [ ] **Step 1: Update the existing key tests to the SoT-backed 17-slug reality**

The current `tests/opportunity/test_lookthrough_sector_keys.py` asserts only 3 slugs and imports `_SECTOR_INDEX_DISPLAY` from `lookthrough`. Replace its body with:

```python
from __future__ import annotations

from irc.opportunity.lookthrough import (
    _BROAD_INDEX_KEYS,
    _INDEX_NAME_TO_SLUG,
    _INDEX_VALUATION_KEYS,
    _SECTOR_INDEX_DISPLAY,
    _SECTOR_INDEX_KEYS,
)
from irc.opportunity.sector_indices import (
    SECTOR_INDEX_DISPLAY,
    SECTOR_INDEX_KEYS,
)


def test_sector_display_is_sot_backed():
    # lookthrough re-exports the SoT map verbatim (no inline copy).
    assert _SECTOR_INDEX_DISPLAY == SECTOR_INDEX_DISPLAY
    assert len(_SECTOR_INDEX_DISPLAY) == 17
    # Existing metals slugs preserved (regression lock).
    assert _SECTOR_INDEX_DISPLAY["csi_nonferrous"] == "中证有色金属"


def test_sector_keys_mirror_sot_keys():
    assert _SECTOR_INDEX_KEYS == SECTOR_INDEX_KEYS == frozenset(SECTOR_INDEX_DISPLAY)


def test_index_name_to_slug_resolves_sector_names_and_aliases():
    assert _INDEX_NAME_TO_SLUG["中证有色金属"] == "csi_nonferrous"
    assert _INDEX_NAME_TO_SLUG["中证有色"] == "csi_nonferrous"  # colloquial alias preserved
    assert _INDEX_NAME_TO_SLUG["中证机床zz"] == "csi_machine_tool"  # malformed alias (lowercased)
    assert _INDEX_NAME_TO_SLUG["中证机器人"] == "csi_robotics"  # new slug


def test_index_name_to_slug_excludes_broad_names():
    # Broad display names are NOT inverted here — broad re-activation is separate.
    assert "沪深300" not in _INDEX_NAME_TO_SLUG
    assert "中证1000" not in _INDEX_NAME_TO_SLUG


def test_index_valuation_keys_is_broad_union_sector():
    assert _INDEX_VALUATION_KEYS == _BROAD_INDEX_KEYS | _SECTOR_INDEX_KEYS
    assert "csi300" in _INDEX_VALUATION_KEYS  # broad membership backward-compatible
    assert "csi_nonferrous" in _INDEX_VALUATION_KEYS  # sector
    assert "csi_robotics" in _INDEX_VALUATION_KEYS  # new sector
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/opportunity/test_lookthrough_sector_keys.py -q`
Expected: FAIL — `_SECTOR_INDEX_DISPLAY` still has 3 entries / `中证机床zz` not in `_INDEX_NAME_TO_SLUG`.

- [ ] **Step 3: Replace the inline sector dicts in `lookthrough.py` with SoT imports**

In `src/irc/opportunity/lookthrough.py`, change the import at the top (line 3 region) to add the SoT import:

```python
from irc.opportunity.sector_indices import (
    SECTOR_INDEX_DISPLAY,
    SECTOR_INDEX_KEYS,
    SECTOR_NAME_TO_SLUG,
)
from irc.opportunity.types import LookthroughTarget, OpportunityInput
```

Then replace the entire block currently at lines 63-84 (the `_SECTOR_INDEX_DISPLAY` comment + dict, `_SECTOR_INDEX_KEYS`, `_INDEX_NAME_TO_SLUG`, and `_INDEX_VALUATION_KEYS` definitions) with:

```python
# Sector-index maps come from the single source-of-truth catalog
# (opportunity/sector_indices.py) — 17 slugs (14 new + 3 folded-in metals).
# Re-bound here under the legacy private names so existing importers
# (inputs_loader, akshare_index_valuation, ingest_cmd, tests) stay valid.
_SECTOR_INDEX_DISPLAY: dict[str, str] = SECTOR_INDEX_DISPLAY
_SECTOR_INDEX_KEYS: frozenset[str] = SECTOR_INDEX_KEYS

# Inversion (中文/lowercased name or alias -> slug). Broad display names are
# deliberately NOT inverted here (broad re-activation is a separate opt-in).
_INDEX_NAME_TO_SLUG: dict[str, str] = dict(SECTOR_NAME_TO_SLUG)

# The full valuation key-set the inputs loader tests membership against — the
# union of broad (#102) and sector. Overloading "broad" is avoided.
_INDEX_VALUATION_KEYS: frozenset[str] = _BROAD_INDEX_KEYS | _SECTOR_INDEX_KEYS
```

> **Note:** `SECTOR_NAME_TO_SLUG` already includes the `中证有色` and `中证机床zz` aliases (lowercased), so the previous hand-written `"中证有色": "csi_nonferrous"` line is now covered by the catalog. Keep `_BROAD_INDEX_KEYS` (line 61) and all other dicts untouched.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/opportunity/test_lookthrough_sector_keys.py -q`
Expected: PASS.

- [ ] **Step 5: Run the broader lookthrough + inputs-loader suites for regressions**

Run: `uv run pytest tests/opportunity/ -q`
Expected: PASS (no regression — `map_lookthrough` and `_index_valuation_metrics` still resolve metals slugs as before).

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/lookthrough.py tests/opportunity/test_lookthrough_sector_keys.py
git commit -m "refactor(sector-b1): lookthrough imports SoT sector maps (drops inline dicts)"
```

---

## Task 3: `akshare_index_valuation.py` imports `SECTOR_INDEX_CODE`

**Files:**
- Modify: `src/irc/fundamentals/akshare_index_valuation.py` (lines 44-51, 190)
- Test: `tests/fundamentals/test_akshare_index_valuation.py` (add one assertion)

- [ ] **Step 1: Write a failing test that the fetcher uses the SoT code map**

Append to `tests/fundamentals/test_akshare_index_valuation.py`:

```python
def test_sector_code_map_is_sot_backed():
    from irc.fundamentals.akshare_index_valuation import _SECTOR_INDEX_CODE
    from irc.opportunity.sector_indices import SECTOR_INDEX_CODE

    assert _SECTOR_INDEX_CODE is SECTOR_INDEX_CODE
    assert _SECTOR_INDEX_CODE["csi_robotics"] == "H30590"  # new slug resolvable


def test_sector_fetch_resolves_new_slug_code(monkeypatch):
    import pandas as pd

    from irc.fundamentals import akshare_index_valuation as m

    captured = {}

    def fake_ak(fn_name, **kwargs):
        captured["symbol"] = kwargs.get("symbol")
        return pd.DataFrame({"日期": ["2026-06-04"], "市盈率1": [28.5]})

    monkeypatch.setattr(m, "_ak_call", fake_ak)
    out = m.fetch_cn_sector_index_valuation_history("csi_robotics")
    assert out is not None
    assert captured["symbol"] == "H30590"
```

> **Backward-compat:** keep the alias name `_SECTOR_INDEX_CODE` bound to the imported `SECTOR_INDEX_CODE` so the existing live test (`test_sector_index_valuation_live.py`) and any other importer continue to work without edits in this task.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py::test_sector_code_map_is_sot_backed -q`
Expected: FAIL — `_SECTOR_INDEX_CODE` is still the inline 3-entry dict (`is` check fails / `csi_robotics` KeyError).

- [ ] **Step 3: Replace the inline `_SECTOR_INDEX_CODE` with the SoT import**

In `src/irc/fundamentals/akshare_index_valuation.py`, add to the imports near line 27:

```python
from irc.opportunity.lookthrough import _BROAD_INDEX_DISPLAY
from irc.opportunity.sector_indices import SECTOR_INDEX_CODE
```

Then delete the inline dict at lines 44-51 (the `# Sector slug -> CSI index code...` comment block and the 3-entry `_SECTOR_INDEX_CODE` literal) and replace with:

```python
# Sector slug -> CSI index code, from the single source-of-truth catalog
# (opportunity/sector_indices.py). Aliased to the legacy private name so the
# live test and fetcher keep their existing references.
_SECTOR_INDEX_CODE: dict[str, str] = SECTOR_INDEX_CODE
```

> The fetcher body (`code = _SECTOR_INDEX_CODE.get(index_key)` at line 190) is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -q`
Expected: PASS (all existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/irc/fundamentals/akshare_index_valuation.py tests/fundamentals/test_akshare_index_valuation.py
git commit -m "refactor(sector-b1): fetcher imports SoT SECTOR_INDEX_CODE (drops inline dict)"
```

---

## Task 4: Config schema + template — `sector_index_grounding.activated_slugs`

**Files:**
- Modify: `src/irc/schemas/valuation.py` (after line 31, and the `ValuationBucketsConfig` body at 33-38)
- Modify: `src/irc/templates/config/valuation_buckets.yaml` (append)
- Test: new `tests/schemas/test_valuation_sector_grounding.py`

- [ ] **Step 1: Write the failing schema test**

Create `tests/schemas/test_valuation_sector_grounding.py`:

```python
from __future__ import annotations

from irc.schemas.valuation import (
    SectorIndexGroundingConfig,
    ValuationBucketsConfig,
)

_BUCKETS = [
    {"max_percentile": 0.30, "buy_method": "lump_sum", "granularity": "x"},
    {"max_percentile": 1.00, "buy_method": "suspend", "granularity": "n/a"},
]


def test_sector_grounding_defaults_to_empty_list():
    cfg = ValuationBucketsConfig(buckets=_BUCKETS)
    assert cfg.sector_index_grounding.activated_slugs == []


def test_sector_grounding_accepts_slugs():
    cfg = ValuationBucketsConfig(
        buckets=_BUCKETS,
        sector_index_grounding={"activated_slugs": ["csi_robotics"]},
    )
    assert cfg.sector_index_grounding.activated_slugs == ["csi_robotics"]


def test_sector_grounding_standalone_default():
    assert SectorIndexGroundingConfig().activated_slugs == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/schemas/test_valuation_sector_grounding.py -q`
Expected: FAIL — `ImportError: cannot import name 'SectorIndexGroundingConfig'`.

- [ ] **Step 3: Add the nested schema + field**

In `src/irc/schemas/valuation.py`, after the `ActiveFundLookthroughConfig` class (ends line 31), add:

```python
class SectorIndexGroundingConfig(FrozenModel):
    """Phase B sector-index PE grounding allowlist (B1).

    `activated_slugs` is the reviewed set of sector slugs (from
    opportunity/sector_indices.py) permitted to ground a fund's valuation off
    the csindex PE percentile. B1 default = empty (accumulate only; output
    byte-identical). B2 adds reviewed mature slugs after gate #5."""
    activated_slugs: list[str] = Field(default_factory=list)
```

Then in `ValuationBucketsConfig` (line 33), add the field after `active_fund_lookthrough`:

```python
class ValuationBucketsConfig(FrozenModel):
    buckets: list[Bucket] = Field(min_length=1)
    active_fund_lookthrough: ActiveFundLookthroughConfig = Field(
        default_factory=ActiveFundLookthroughConfig
    )
    sector_index_grounding: SectorIndexGroundingConfig = Field(
        default_factory=SectorIndexGroundingConfig
    )
```

- [ ] **Step 4: Run the schema test to verify it passes**

Run: `uv run pytest tests/schemas/test_valuation_sector_grounding.py -q`
Expected: PASS.

- [ ] **Step 5: Add the block to the template YAML**

Append to `src/irc/templates/config/valuation_buckets.yaml`:

```yaml

sector_index_grounding:
  activated_slugs: []   # B1: empty (accumulate only; output byte-identical).
                        # B2: reviewed mature slugs added after gate #5.
```

- [ ] **Step 6: Verify the template still loads under the schema**

Run: `uv run python -c "import yaml; from irc.schemas.valuation import ValuationBucketsConfig; d=yaml.safe_load(open('src/irc/templates/config/valuation_buckets.yaml')); c=ValuationBucketsConfig(**d); print('activated_slugs=', c.sector_index_grounding.activated_slugs)"`
Expected: `activated_slugs= []`

- [ ] **Step 7: Commit**

```bash
git add src/irc/schemas/valuation.py src/irc/templates/config/valuation_buckets.yaml tests/schemas/test_valuation_sector_grounding.py
git commit -m "feat(sector-b1): sector_index_grounding.activated_slugs config (B1 empty)"
```

---

## Task 5: Read-gate in `_index_valuation_metrics`

**Files:**
- Modify: `src/irc/opportunity/inputs_loader.py` (lines 154-187, plus import at line 17)
- Test: new `tests/opportunity/test_index_valuation_gate.py`

- [ ] **Step 1: Write the failing gate tests (flag-OFF byte-identity + flag-ON populated + broad unaffected)**

Create `tests/opportunity/test_index_valuation_gate.py`:

```python
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from irc.data.duckdb_helper import ensure_schema
from irc.opportunity.inputs_loader import _index_valuation_metrics


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "gate.duckdb"))
    ensure_schema(con)
    return con


def _seed(con, index_key, pe_pb_pairs, base_date=date(2025, 1, 1)):
    rows = []
    for i, (pe, pb) in enumerate(pe_pb_pairs):
        d = date.fromordinal(base_date.toordinal() + i)
        rows.append((index_key, d, pe, pb, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


# 200 rising PE points: > MIN_PE_POINTS (120) and span > MIN_PE_DAYS (180) -> mature.
_MATURE_PAIRS = [(10.0 + i * 0.1, None) for i in range(200)]


def test_sector_slug_off_allowlist_returns_full_none_tuple(tmp_path):
    """Mature sector series with empty allowlist -> full all-None short-circuit
    (raw pe/pb/div AND both percentiles withheld). Byte-identity invariant."""
    con = _con(tmp_path)
    _seed(con, "csi_robotics", _MATURE_PAIRS)
    result = _index_valuation_metrics(
        con, "中证机器人", activated_sector_slugs=frozenset()
    )
    assert result == (None, None, None, None, None)
    con.close()


def test_sector_slug_default_allowlist_returns_full_none_tuple(tmp_path):
    """Default (no kwarg passed) is frozenset() -> same short-circuit."""
    con = _con(tmp_path)
    _seed(con, "csi_robotics", _MATURE_PAIRS)
    assert _index_valuation_metrics(con, "中证机器人") == (None, None, None, None, None)
    con.close()


def test_sector_slug_on_allowlist_populates_percentile_pb_none(tmp_path):
    """Slug in allowlist + mature series -> PE percentile populated; PB None
    (csindex carries no PB)."""
    con = _con(tmp_path)
    _seed(con, "csi_robotics", _MATURE_PAIRS)
    pe, pb, div, pe_pct, pb_pct = _index_valuation_metrics(
        con, "中证机器人", activated_sector_slugs=frozenset({"csi_robotics"})
    )
    assert pe == pytest.approx(10.0 + 199 * 0.1)  # latest PE populated
    assert pb is None and div is None
    assert pe_pct == pytest.approx(1.0)  # latest is the max -> percentile 1.0
    assert pb_pct is None
    con.close()


def test_metals_slug_off_allowlist_short_circuits(tmp_path):
    """Folded-in metals slug is now allowlist-governed: empty allowlist ->
    full None (must NOT auto-activate on maturity)."""
    con = _con(tmp_path)
    _seed(con, "csi_nonferrous", _MATURE_PAIRS)
    assert _index_valuation_metrics(
        con, "中证有色金属", activated_sector_slugs=frozenset()
    ) == (None, None, None, None, None)
    con.close()


def test_broad_slug_unaffected_by_empty_allowlist(tmp_path):
    """Broad-index slug grounds regardless of the (empty) sector allowlist."""
    con = _con(tmp_path)
    _seed(con, "csi300", [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)])
    pe, pb, div, pe_pct, pb_pct = _index_valuation_metrics(
        con, "csi300", activated_sector_slugs=frozenset()
    )
    assert pe is not None and pe_pct == pytest.approx(1.0)
    con.close()


def test_broad_slug_unaffected_by_nonempty_allowlist(tmp_path):
    """A non-empty sector allowlist must not change broad behavior."""
    con = _con(tmp_path)
    _seed(con, "csi300", [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(200)])
    pe_a = _index_valuation_metrics(con, "csi300", activated_sector_slugs=frozenset())
    pe_b = _index_valuation_metrics(
        con, "csi300", activated_sector_slugs=frozenset({"csi_robotics"})
    )
    assert pe_a == pe_b
    con.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/opportunity/test_index_valuation_gate.py -q`
Expected: FAIL — `_index_valuation_metrics() got an unexpected keyword argument 'activated_sector_slugs'`.

- [ ] **Step 3: Add the import and the gate**

In `src/irc/opportunity/inputs_loader.py`, extend the lookthrough import (line 17) and add the SoT import:

```python
from irc.opportunity.lookthrough import _INDEX_NAME_TO_SLUG, _INDEX_VALUATION_KEYS
from irc.opportunity.sector_indices import SECTOR_INDEX_KEYS
```

Change the `_index_valuation_metrics` signature and insert the short-circuit immediately after the slug is resolved. Replace lines 154-171 (signature, docstring, and the up-to `_INDEX_VALUATION_KEYS` membership block) with:

```python
def _index_valuation_metrics(
    con: duckdb.DuckDBPyConnection,
    tracked_index: str | None,
    *,
    activated_sector_slugs: frozenset[str] = frozenset(),
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """Return (pe_ttm, pb, dividend_yield, pe_percentile, pb_percentile) from the
    CACHED index_valuation_history table (R3 — no live fetch). (None,)*5 when the
    index is not a recognised valuation index or has no cached rows.

    The `tracked_index` value may be a display name (e.g. "中证有色金属"); it is
    normalised to a canonical slug via `_INDEX_NAME_TO_SLUG` before membership
    in `_INDEX_VALUATION_KEYS` is tested. The PE percentile honours the §3
    min-history gate AND the latest-null guard.

    Phase B activation gate: a SECTOR slug (`slug in SECTOR_INDEX_KEYS`) that is
    NOT on the reviewed `activated_sector_slugs` allowlist short-circuits to the
    FULL all-None tuple — withholding raw pe/pb/div AND the percentile (the raw
    metrics also feed OpportunityInput), so B1 output is byte-identical. Broad
    slugs are unaffected.
    """
    norm = (tracked_index or "").strip().lower() or None
    if norm is None:
        return None, None, None, None, None
    slug = _INDEX_NAME_TO_SLUG.get(norm) or norm
    if slug not in _INDEX_VALUATION_KEYS:
        return None, None, None, None, None
    if slug in SECTOR_INDEX_KEYS and slug not in activated_sector_slugs:
        return None, None, None, None, None
```

> Everything from `df = _index_valuation_series(con, slug)` (line 172) onward is unchanged.

- [ ] **Step 4: Run the gate tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_index_valuation_gate.py -q`
Expected: PASS (all 6).

- [ ] **Step 5: Run the existing inputs-loader suite for regressions**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -q`
Expected: PASS — broad-index tests still ground (the default `frozenset()` is inert for broad slugs).

- [ ] **Step 6: Commit**

```bash
git add src/irc/opportunity/inputs_loader.py tests/opportunity/test_index_valuation_gate.py
git commit -m "feat(sector-b1): activation gate in _index_valuation_metrics (allowlist short-circuit)"
```

---

## Task 6: Thread the allowlist `populate_inputs → _build_input → _build_rows → run_opportunity`

**Files:**
- Modify: `src/irc/opportunity/inputs_loader.py` (`populate_inputs`, line 253; call at 302)
- Modify: `src/irc/opportunity/inputs_build.py` (`_build_input`, line 15; call at 65)
- Modify: `src/irc/commands/opportunity_cmd.py` (`_build_rows` line 699; call at 833; `run_opportunity` call at 1497)
- Test: new `tests/opportunity/test_sector_allowlist_threading.py`

- [ ] **Step 1: Write the failing threading test**

Create `tests/opportunity/test_sector_allowlist_threading.py`:

```python
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from irc.data.duckdb_helper import ensure_schema
from irc.opportunity import inputs_loader
from irc.opportunity.types import OpportunityInput


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "thread.duckdb"))
    ensure_schema(con)
    return con


def _seed_mature(con, index_key):
    rows = []
    base = date(2025, 1, 1)
    for i in range(200):
        d = date.fromordinal(base.toordinal() + i)
        rows.append((index_key, d, 10.0 + i * 0.1, None, None))
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


def test_populate_inputs_forwards_allowlist_to_metrics(tmp_path, monkeypatch):
    """The allowlist must REACH _index_valuation_metrics (no global lookup)."""
    captured = {}
    real = inputs_loader._index_valuation_metrics

    def spy(con, tracked_index, *, activated_sector_slugs=frozenset()):
        captured["slugs"] = activated_sector_slugs
        return real(con, tracked_index, activated_sector_slugs=activated_sector_slugs)

    monkeypatch.setattr(inputs_loader, "_index_valuation_metrics", spy)
    con = _con(tmp_path)
    skeleton = OpportunityInput(
        instrument_id="562500", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="中证机器人", name_cn="机器人ETF",
    )
    inputs_loader.populate_inputs(
        con, skeleton, holding_entry_date=None,
        activated_sector_slugs=frozenset({"csi_robotics"}),
    )
    assert captured["slugs"] == frozenset({"csi_robotics"})
    con.close()


def test_populate_inputs_on_allowlist_grounds_sector(tmp_path):
    """End-to-end through populate_inputs: allowlisted mature sector grounds PE."""
    con = _con(tmp_path)
    _seed_mature(con, "csi_robotics")
    skeleton = OpportunityInput(
        instrument_id="562500", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="中证机器人",
    )
    inp = inputs_loader.populate_inputs(
        con, skeleton, holding_entry_date=None,
        activated_sector_slugs=frozenset({"csi_robotics"}),
    )
    assert inp.valuation_percentile_fundamental == pytest.approx(1.0)
    assert inp.valuation_percentile_fundamental_pb is None
    con.close()


def test_populate_inputs_empty_allowlist_withholds_sector(tmp_path):
    """Default empty allowlist -> sector ungrounded (byte-identity)."""
    con = _con(tmp_path)
    _seed_mature(con, "csi_robotics")
    skeleton = OpportunityInput(
        instrument_id="562500", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="中证机器人",
    )
    inp = inputs_loader.populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.valuation_percentile_fundamental is None
    assert inp.pe_ttm is None
    con.close()
```

Also add a source-inspection threading guard for the command layer (so the chain can't silently break). Append to the same file:

```python
def test_build_rows_and_run_opportunity_thread_the_allowlist():
    import inspect

    from irc.commands import opportunity_cmd
    from irc.opportunity import inputs_build

    build_input_src = inspect.getsource(inputs_build._build_input)
    assert "activated_sector_slugs" in build_input_src

    build_rows_src = inspect.getsource(opportunity_cmd._build_rows)
    assert "activated_sector_slugs" in build_rows_src

    run_src = inspect.getsource(opportunity_cmd.run_opportunity)
    assert "sector_index_grounding" in run_src
    assert "activated_slugs" in run_src
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/opportunity/test_sector_allowlist_threading.py -q`
Expected: FAIL — `populate_inputs()` rejects `activated_sector_slugs` / source guards fail.

- [ ] **Step 3: Add `activated_sector_slugs` to `populate_inputs`**

In `src/irc/opportunity/inputs_loader.py`, change the `populate_inputs` signature (line 253-261) to add the keyword-only param after `lookthrough_cfg`:

```python
def populate_inputs(
    con: duckdb.DuckDBPyConnection,
    skeleton: OpportunityInput,
    *,
    holding_entry_date: date | None,
    broker_reports: tuple[BrokerReport, ...] = (),
    provider: CnFundamentalsProvider | None = None,
    lookthrough_cfg: ActiveFundLookthroughConfig = ActiveFundLookthroughConfig(),
    activated_sector_slugs: frozenset[str] = frozenset(),
) -> OpportunityInput:
```

And change the call (line 302-304) to pass it:

```python
    pe_ttm, pb, dividend_yield, fund_pct, fund_pct_pb = _index_valuation_metrics(
        con, skeleton.tracked_index,
        activated_sector_slugs=activated_sector_slugs,
    )
```

- [ ] **Step 4: Thread through `_build_input`**

In `src/irc/opportunity/inputs_build.py`, add the keyword-only param to `_build_input` (line 15-26) after `lookthrough_cfg`:

```python
    provider: CnFundamentalsProvider,
    lookthrough_cfg: ActiveFundLookthroughConfig = ActiveFundLookthroughConfig(),
    activated_sector_slugs: frozenset[str] = frozenset(),
) -> OpportunityInput:
```

And forward it in the `populate_inputs` call (line 65-70):

```python
    return populate_inputs(
        con, skeleton,
        holding_entry_date=entry_date,
        provider=provider,
        lookthrough_cfg=lookthrough_cfg,
        activated_sector_slugs=activated_sector_slugs,
    )
```

- [ ] **Step 5: Thread through `_build_rows`**

In `src/irc/commands/opportunity_cmd.py`, add the keyword-only param to `_build_rows` (line 715) after `lookthrough_cfg`:

```python
    lookthrough_cfg: ActiveFundLookthroughConfig = ActiveFundLookthroughConfig(),
    activated_sector_slugs: frozenset[str] = frozenset(),
) -> tuple[list[OpportunityRow], dict, dict, dict, dict, str, dict]:
```

And forward it in the `_build_input` call (line 833-840):

```python
            inp = _build_input(
                score, instr, holding,
                target_band,
                portfolio_total_cny, available_venues,
                con,
                provider=provider,
                lookthrough_cfg=lookthrough_cfg,
                activated_sector_slugs=activated_sector_slugs,
            )
```

- [ ] **Step 6: Source the allowlist in `run_opportunity`**

In `src/irc/commands/opportunity_cmd.py`, in the `_build_rows` call inside `run_opportunity` (line 1497-1507), add the new keyword right after `lookthrough_cfg`:

```python
            lookthrough_cfg=bundle.valuation_buckets.active_fund_lookthrough,
            activated_sector_slugs=frozenset(
                bundle.valuation_buckets.sector_index_grounding.activated_slugs
            ),
```

- [ ] **Step 7: Run the threading test to verify it passes**

Run: `uv run pytest tests/opportunity/test_sector_allowlist_threading.py -q`
Expected: PASS (all 5).

- [ ] **Step 8: Run the opportunity command + opportunity package suites for regressions**

Run: `uv run pytest tests/opportunity/ tests/commands/test_ingest_index_valuation_wiring.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/irc/opportunity/inputs_loader.py src/irc/opportunity/inputs_build.py src/irc/commands/opportunity_cmd.py tests/opportunity/test_sector_allowlist_threading.py
git commit -m "feat(sector-b1): thread activated_sector_slugs run_opportunity->_index_valuation_metrics (no global read)"
```

---

## Task 7: Per-slug ingest audit helper `audit_sector_ingest`

**Files:**
- Modify: `src/irc/data/index_valuation_ingestor.py` (add helper; keep file < 200 lines)
- Test: new `tests/data/test_sector_ingest_audit.py`

- [ ] **Step 1: Write the failing audit test**

Create `tests/data/test_sector_ingest_audit.py`:

```python
from __future__ import annotations

from datetime import date

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.data.index_valuation_ingestor import audit_sector_ingest


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "audit.duckdb"))
    ensure_schema(con)
    return con


def _seed(con, index_key, n, *, base=date(2025, 1, 1), pe=12.0):
    rows = [
        (index_key, date.fromordinal(base.toordinal() + i), pe, None, None)
        for i in range(n)
    ]
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


def test_audit_covers_all_17_slugs_even_when_empty(tmp_path):
    con = _con(tmp_path)
    rows = audit_sector_ingest(con)
    assert len(rows) == 17  # every sector slug reported, even with 0 rows
    by_slug = {r.slug: r for r in rows}
    r = by_slug["csi_robotics"]
    assert r.row_count == 0
    assert r.has_numeric_pe is False
    assert r.latest_date is None
    assert r.mature is False
    con.close()


def test_audit_reports_accumulating_not_mature(tmp_path):
    con = _con(tmp_path)
    _seed(con, "csi_robotics", 20)  # < 120 points, < 180 day span
    rows = {r.slug: r for r in audit_sector_ingest(con)}
    r = rows["csi_robotics"]
    assert r.row_count == 20
    assert r.has_numeric_pe is True
    assert r.points == 20
    assert r.mature is False  # 20 < MIN_PE_POINTS (120) -> B1 expected state


def test_audit_reports_mature_when_thresholds_cleared(tmp_path):
    con = _con(tmp_path)
    _seed(con, "csi_robotics", 200)  # 200 points, 199-day span
    rows = {r.slug: r for r in audit_sector_ingest(con)}
    r = rows["csi_robotics"]
    assert r.points >= 120
    assert r.span_days >= 180
    assert r.mature is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/data/test_sector_ingest_audit.py -q`
Expected: FAIL — `ImportError: cannot import name 'audit_sector_ingest'`.

- [ ] **Step 3: Add the audit helper + result type**

In `src/irc/data/index_valuation_ingestor.py`, extend the imports at the top:

```python
from dataclasses import dataclass
from datetime import date as _date

from irc.opportunity.lookthrough_valuation import MIN_PE_DAYS, MIN_PE_POINTS
from irc.opportunity.sector_indices import SECTOR_INDEX_KEYS
```

Then append at the end of the module:

```python
@dataclass(frozen=True)
class SectorIngestAudit:
    """Per-slug accumulation status for the B1 ingest-audit artifact."""
    slug: str
    row_count: int
    has_numeric_pe: bool
    points: int           # non-null PE points (the MIN_PE_POINTS axis)
    latest_date: str | None
    freshness_days: int | None
    span_days: int        # latest - earliest non-null PE date (MIN_PE_DAYS axis)
    mature: bool          # points >= MIN_PE_POINTS AND span_days >= MIN_PE_DAYS


def _audit_one_slug(
    con: duckdb.DuckDBPyConnection, slug: str, *, today: _date
) -> SectorIngestAudit:
    df = con.execute(
        "SELECT CAST(date AS VARCHAR) AS d, pe_ttm FROM index_valuation_history "
        "WHERE index_key = ? ORDER BY date",
        [slug],
    ).fetchdf()
    row_count = int(len(df))
    pe_dates = [
        r["d"] for _, r in df.iterrows() if r["pe_ttm"] is not None and r["pe_ttm"] == r["pe_ttm"]
    ]
    points = len(pe_dates)
    latest_date = pe_dates[-1] if pe_dates else None
    freshness_days = (
        (today - _date.fromisoformat(latest_date)).days if latest_date else None
    )
    span_days = (
        (_date.fromisoformat(pe_dates[-1]) - _date.fromisoformat(pe_dates[0])).days
        if points >= 2 else 0
    )
    mature = points >= MIN_PE_POINTS and span_days >= MIN_PE_DAYS
    return SectorIngestAudit(
        slug=slug, row_count=row_count, has_numeric_pe=points > 0, points=points,
        latest_date=latest_date, freshness_days=freshness_days, span_days=span_days,
        mature=mature,
    )


def audit_sector_ingest(
    con: duckdb.DuckDBPyConnection, *, today: _date | None = None
) -> tuple[SectorIngestAudit, ...]:
    """Per-slug accumulation audit over ALL sector slugs (replaces the
    ingestor's silent aggregate count). Returns one row per slug, sorted by
    slug. B1 expected state: every slug present, 0 mature -> 0 grounded."""
    ref = today or _date.today()
    return tuple(
        _audit_one_slug(con, slug, today=ref) for slug in sorted(SECTOR_INDEX_KEYS)
    )
```

> **Size budget:** if this pushes `index_valuation_ingestor.py` over 200 lines, extract `SectorIngestAudit` + the two helpers into a sibling `src/irc/data/sector_ingest_audit.py` and re-export `audit_sector_ingest` from `index_valuation_ingestor.py`. Re-check with `wc -l` in Step 5.

- [ ] **Step 4: Run the audit test to verify it passes**

Run: `uv run pytest tests/data/test_sector_ingest_audit.py -q`
Expected: PASS (all 3).

- [ ] **Step 5: Verify the size budget**

Run: `uv run python -c "print(sum(1 for _ in open('src/irc/data/index_valuation_ingestor.py')))"`
Expected: a number < 200 (if ≥ 200, apply the extraction note from Step 3 and re-run the audit test).

- [ ] **Step 6: Commit**

```bash
git add src/irc/data/index_valuation_ingestor.py tests/data/test_sector_ingest_audit.py
git commit -m "feat(sector-b1): per-slug audit_sector_ingest helper (replaces silent aggregate count)"
```

---

## Task 8: Strengthen the live identity guard (author only — do NOT execute against network)

**Files:**
- Modify: `tests/fundamentals/test_sector_index_valuation_live.py`

> **Hard stop:** this test is double-gated (`pytest.mark.live_akshare` + `IRC_RUN_LIVE_AKSHARE=1`). It is NOT collected by default `uv run pytest` and MUST NOT be run against live AkShare in the autonomous flow. Authoring it is the deliverable; execution is a human gate (#4). The two flagged codes (`sse_star_chip` 000685 — absent from `index_csindex_all`; `csi_resource` 000819 — display≠official) are documented for human confirmation before B2, NOT blockers here.

- [ ] **Step 1: Replace the live test file with the strengthened identity + PE guard**

Overwrite `tests/fundamentals/test_sector_index_valuation_live.py`:

```python
from __future__ import annotations

import os

import pytest

from irc.fundamentals.akshare_index_valuation import (
    _ak_call,
    _SECTOR_INDEX_CODE,
    fetch_cn_sector_index_valuation_history,
)
from irc.opportunity.sector_indices import SECTOR_INDICES

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        not _RUN, reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests"
    ),
]

# index_csindex_all has no entry for SSE-listed codes (科创板). Cross-check that
# one via the SSE source / manual confirmation, not the CSI catalog identity.
_CSI_CATALOG_ABSENT = {"000685"}


@pytest.mark.parametrize("slug", sorted(_SECTOR_INDEX_CODE))
def test_sector_index_pe_ttm_numeric_live(slug):
    """Every sector code returns a numeric 市盈率1 PE-TTM series."""
    out = fetch_cn_sector_index_valuation_history(slug)
    assert out is not None, f"{slug} ({_SECTOR_INDEX_CODE[slug]}) returned no history"
    pes = [r.pe_ttm for r in out.rows if r.pe_ttm is not None]
    assert pes, f"{slug}: no numeric 市盈率1 PE — confirm the CSI code/column"
    assert all(p > 0 for p in pes)


def test_sector_codes_identity_in_csindex_all_live():
    """Load index_csindex_all ONCE; assert each committed code resolves to its
    committed official_cn (catches valid-but-WRONG codes). SSE-only codes are
    cross-checked separately (flagged for gate #4)."""
    catalog = _ak_call("index_csindex_all")
    # index_csindex_all columns: 指数代码 / 指数全称 (verify live; adjust if AkShare renames).
    code_col = next(c for c in ("指数代码", "code", "指数编号") if c in catalog.columns)
    name_col = next(c for c in ("指数全称", "指数简称", "name") if c in catalog.columns)
    by_code = {str(r[code_col]).strip(): str(r[name_col]).strip() for _, r in catalog.iterrows()}
    mismatches = []
    for row in SECTOR_INDICES:
        if row.code in _CSI_CATALOG_ABSENT:
            continue
        official = by_code.get(row.code)
        if official != row.official_cn:
            mismatches.append((row.slug, row.code, row.official_cn, official))
    assert not mismatches, f"code<->official-name identity mismatches: {mismatches}"
```

- [ ] **Step 2: Verify the strengthened test is NOT collected by the default run (the gate works)**

Run: `uv run pytest tests/fundamentals/test_sector_index_valuation_live.py -q`
Expected: `2 skipped` (or `17 deselected/skipped`) — the `IRC_RUN_LIVE_AKSHARE=1` skipif fires; nothing hits the network.

- [ ] **Step 3: Lint the live test file**

Run: `uv run ruff check tests/fundamentals/test_sector_index_valuation_live.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add tests/fundamentals/test_sector_index_valuation_live.py
git commit -m "test(sector-b1): strengthen live identity guard (numeric PE + code<->official-name over all codes)"
```

---

## Task 9: Docs (Gate #6) — CONTEXT.md, CHANGELOG, ROADMAP

**Files:**
- Modify: `CONTEXT.md` ("Valuation inputs" section, the `valuation_percentile_fundamental` entry ~line 141)
- Modify: `CHANGELOG.md` (`[Unreleased]`, ~line 8)
- Modify: `docs/ROADMAP.md` (Phase B table row ~line 25 + Phase B section ~line 105-116)

- [ ] **Step 1: Add a sector-grounding note to CONTEXT.md "Valuation inputs"**

In `CONTEXT.md`, immediately after the `valuation_percentile_fundamental` entry (the line beginning `- **\`valuation_percentile_fundamental\` (+ \`_pb\`)** —`), add a new bullet:

```markdown
- **`sector_index_grounding.activated_slugs` (Phase B B1 sector onboarding, 2026-06-05)** — the reviewed allowlist (in `valuation_buckets.yaml`, schema `SectorIndexGroundingConfig`) of CN **sector** slugs permitted to ground a fund's `valuation_percentile_fundamental` off the csindex PE-TTM percentile. Sector slugs and their CSI codes live in the single source of truth `src/irc/opportunity/sector_indices.py` (`SECTOR_INDICES` — 17 slugs: 14 new + the 3 folded-in metals slugs `csi_nonferrous`/`csi_resource`/`csi_nonferrous_mining`). **PE-only** — csindex carries no PB, so sector `valuation_percentile_fundamental_pb` stays `None` (intentional documented gap; ADR 0012 §5 corroborate-only). Accumulation runs for ALL sector slugs via the ingest leg (`ingest_cmd` over `_SECTOR_INDEX_KEYS`, csindex accumulate-forward ~20 rows/call). **Activation is allowlist-gated:** `_index_valuation_metrics` short-circuits to the FULL all-`None` tuple `(None, None, None, None, None)` for any sector slug not on `activated_slugs` (withholds raw pe/pb/div AND the percentile — the raw metrics also feed `OpportunityInput`), so the **B1 default (empty allowlist) is byte-identical** to the NAV-only path through maturation. The allowlist is threaded explicitly `run_opportunity → _build_rows → _build_input → populate_inputs → _index_valuation_metrics(..., activated_sector_slugs=...)` (keyword-only, default `frozenset()`; no global read — FP rule). The 3 metals slugs are now ALSO allowlist-governed (deliberate fix: they must not auto-activate unreviewed when they mature ~Nov 2026). Per-slug accumulation status is auditable via `data/index_valuation_ingestor.py::audit_sector_ingest`. B2 (separate, post-maturation, gate-#5) adds reviewed mature slugs.
```

- [ ] **Step 2: Add a CHANGELOG `[Unreleased]` entry**

In `CHANGELOG.md`, under `## [Unreleased]` (before the existing Phase D PR2 block), add:

```markdown
### Added — Phase B sector-index PE onboarding (B1, activation OFF, 2026-06-05)

- New single-source-of-truth catalog `src/irc/opportunity/sector_indices.py`:
  `SectorIndex` frozen dataclass + `SECTOR_INDICES` (17 slugs = 14 new sector
  indices + the 3 folded-in metals slugs) and derived maps `SECTOR_INDEX_CODE`
  / `SECTOR_INDEX_DISPLAY` / `SECTOR_INDEX_KEYS` / `SECTOR_NAME_TO_SLUG`.
  `lookthrough.py` and `fundamentals/akshare_index_valuation.py` now import the
  derived maps (inline 3-entry sector dicts removed).
- Config allowlist `sector_index_grounding.activated_slugs` (schema
  `SectorIndexGroundingConfig`, template `valuation_buckets.yaml`), threaded
  explicitly to a new gate in `_index_valuation_metrics`: a sector slug not on
  the allowlist short-circuits to the full all-`None` tuple. **B1 default =
  empty → production output byte-identical** (accumulate-only). The csindex
  series take ~6 months to clear the 120/180 maturity gate; **grounded count =
  0 by design at B1** (gate #3 not claimed). Activation (B2) is a separate,
  post-maturation, gate-#5-reviewed change.
- The malformed universe value `中证机床ZZ` is resolved via an alias in
  `SECTOR_INDICES` — **no `config/universe/*.yaml` edit** (preserves byte-identity).
- Per-slug ingest audit `data/index_valuation_ingestor.py::audit_sector_ingest`
  (row count / has-numeric-PE / latest date / freshness / maturity per slug)
  replaces the ingestor's silent aggregate count.
- Strengthened live identity guard `test_sector_index_valuation_live.py`
  (double-gated `IRC_RUN_LIVE_AKSHARE=1`): asserts numeric `市盈率1` AND
  code↔official-name identity in `index_csindex_all` over all codes. Flags
  `sse_star_chip` (000685, absent from `index_csindex_all`) and `csi_resource`
  (000819, display≠official) for human confirmation before B2 activation.
```

- [ ] **Step 3: Mark Phase B → B1 done in ROADMAP**

In `docs/ROADMAP.md`, update the Phase B table row (line ~25) from:

```markdown
| B — sector ETFs | ☐ open | +21 funds (3%) — PE-only (csindex) |
```

to:

```markdown
| B — sector ETFs | ◑ B1 done (onboarding; activation OFF) | +17 sector slugs onboarded, PE-only (csindex); B2 activation pending maturation + gate #5 |
```

And in the `### Phase B — Sector expansion` section (line ~105), add a status line right after the heading:

```markdown
- **Status (2026-06-05):** **B1 done** — SoT catalog `opportunity/sector_indices.py` (17 slugs), config-gated activation (`sector_index_grounding.activated_slugs`, default empty), per-slug ingest audit, strengthened live identity guard. Output byte-identical (allowlist empty); grounded = 0 by design. Run record: `docs/2026-06-05-phase-b-sector-b1/`. **B2 (activation)** pending ~6-month maturation + the real NAV-vs-PE diff + gate #5 sign-off (resolve flags `sse_star_chip` 000685 / `csi_resource` 000819 first). Committed scope is **17 sector slugs / 14 new** (the "21 funds" estimate also counted generated-catalog ETFs that never resolve).
```

- [ ] **Step 4: Commit**

```bash
git add CONTEXT.md CHANGELOG.md docs/ROADMAP.md
git commit -m "docs(sector-b1): CONTEXT valuation-inputs + CHANGELOG + ROADMAP Phase B B1 done"
```

---

## Task 10: Final verification — full suite, lint, byte-identity check

**Files:** none (verification only)

- [ ] **Step 1: Run the full sector-B1 test slice**

Run:
```bash
uv run pytest tests/opportunity/test_sector_indices.py tests/opportunity/test_lookthrough_sector_keys.py tests/opportunity/test_index_valuation_gate.py tests/opportunity/test_sector_allowlist_threading.py tests/fundamentals/test_akshare_index_valuation.py tests/schemas/test_valuation_sector_grounding.py tests/data/test_sector_ingest_audit.py tests/data/test_index_valuation_ingestor.py tests/commands/test_ingest_index_valuation_wiring.py -q
```
Expected: all PASS (live test slice not included — it is gated).

- [ ] **Step 2: Lint everything touched**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 3: Confirm no `config/valuation_buckets.yaml` value was edited and no `config/universe/*.yaml` value changed**

Run: `git diff --name-only main...HEAD -- config/`
Expected: **no output** (B1 touches only the *template* under `src/irc/templates/`, never `config/`).

- [ ] **Step 4: Byte-identity check (the load-bearing B1 invariant)**

This proves an empty allowlist leaves `irc opportunity` output unchanged vs `main`. Run against a checkout with cached data present (the autodev env has `data/local.duckdb` + a prior `outputs/<date>/`). If no cached data exists in the autodev sandbox, record this step as **deferred to verify/human** (the gate posture allows this — see note below) and rely on the unit-level byte-identity locks (Tasks 5/6: empty-allowlist returns the full `None` tuple, sector ungrounded).

```bash
# A) capture main's opportunity outputs
git stash --include-untracked 2>/dev/null || true
git checkout main -- src/irc 2>/dev/null
uv run irc opportunity --output-dir /tmp/b1_main 2>/dev/null || echo "no cached data — defer to verify"
git checkout HEAD -- src/irc
git stash pop 2>/dev/null || true
# B) capture this branch's outputs and diff
uv run irc opportunity --output-dir /tmp/b1_branch 2>/dev/null || echo "no cached data — defer to verify"
diff -r /tmp/b1_main /tmp/b1_branch && echo "BYTE-IDENTICAL ✓" || echo "DIFF FOUND — investigate (B1 MUST be byte-identical)"
```

Expected: `BYTE-IDENTICAL ✓` when cached data is present; otherwise the explicit "defer to verify" message (the unit-level locks in Tasks 5/6 are the primary guarantee, and the post-ship `/verify` step re-checks this).

> **Gate posture reminder for the verifier/reviewer:** with the allowlist empty, byte-identity is the success criterion. Gate #3 (grounded > 0) is **NOT claimed** — the ingest audit showing all 17 slugs accumulating / 0 mature / 0 grounded is the EXPECTED B1 state, not a failure. Gate #5 is **N/A** (no recommendation change; empty diff expected). The live identity guard's execution is a human hard stop.

- [ ] **Step 5: Final commit (only if Step 1-3 surfaced any fix)**

```bash
git add -A
git commit -m "chore(sector-b1): final lint + verification fixes" || echo "nothing to commit"
```

---

## Self-Review (author's checklist — completed)

**Spec coverage (spec §3-§8):**
- §3.4 SoT module + derived maps → Task 1. ✓
- §3.4 lookthrough imports maps; §5 fetcher imports `SECTOR_INDEX_CODE` → Tasks 2, 3. ✓
- §3.2 config allowlist + schema → Task 4. ✓
- §3.2 short-circuit gate (full `None` tuple) → Task 5. ✓
- §3.3 explicit threading (no global read) + threading test → Task 6. ✓
- §3.5 no universe edit; `中证机床ZZ` via alias → Task 1 catalog (`中证机床ZZ` alias) + Task 10 Step 3 guard. ✓
- §7 tests: alias-collision, curated-config coverage, resolution, SoT contract → Task 1; flag-OFF/ON gate, threading, broad-unchanged → Tasks 5, 6; live identity+PE → Task 8; per-slug audit → Task 7. ✓
- §8 Gate #6 docs → Task 9. ✓
- §9 byte-identity invariant → Task 10 Step 4 + unit locks. ✓

**Placeholder scan:** no TBD/TODO; every code step shows full code; every command shows expected output. ✓

**Type consistency:** `SectorIndex(slug, code, display_cn, official_cn, aliases)`, `SECTOR_INDEX_CODE`/`SECTOR_INDEX_DISPLAY`/`SECTOR_INDEX_KEYS`/`SECTOR_NAME_TO_SLUG`, `SectorIndexGroundingConfig.activated_slugs`, `activated_sector_slugs: frozenset[str]`, `audit_sector_ingest(con, *, today) -> tuple[SectorIngestAudit, ...]` — used identically across all tasks. ✓

**Judgment calls made (stale-spec / code-reality reconciliations):**
1. Spec §6 pseudocode shows `_INDEX_NAME_TO_SLUG.get(norm) or norm`; the real `inputs_loader.py:169` matches exactly — gate inserted right after that line (Task 5). ✓
2. Spec §4 lists `csi_machine_tool` display as `中证机床ZZ *(alias→中证机床)*`. Resolved to: `display_cn = "中证机床"` (clean canonical) with `aliases=("中证机床ZZ",)` — so the malformed universe value resolves AND `display_cn` is the clean form, satisfying §3.5 (no universe edit). The curated-config coverage test (Task 1) feeds the raw `中证机床ZZ` and asserts it resolves via the alias. ✓
3. Spec §7 "curated-config coverage: every sector-ETF tracked_index resolves" — confirmed the 3 metals tracked indices are NOT in `cn_funds.yaml` (they ride the `theme: metals` path), so the coverage test asserts only the 14 sector-ETF indices (the 3 metals slugs are covered by the resolution + SoT-contract tests instead). ✓
4. `_SECTOR_INDEX_CODE` / `_SECTOR_INDEX_DISPLAY` legacy private names are **kept as aliases** to the SoT objects (not deleted) so the existing live test and any other importer keep working without churn — matches the spec's "import the derived maps (replacing inline dicts)" intent while minimizing blast radius. ✓
5. `audit_sector_ingest` is added to the existing `index_valuation_ingestor.py` (spec §7 says it "replaces the ingestor's silent aggregate count") with a size-budget extraction fallback to a sibling module if the file would exceed 200 lines. ✓
