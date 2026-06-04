# Commodity-Cyclical Valuation Guard + Sector PE Accumulate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop NAV price-momentum from producing a directional valuation verdict for commodity-cyclical funds with no fundamental PE anchor, and wire a csindex sector-PE accumulate-forward path so PE grounding switches on automatically once enough history accrues.

**Architecture:** Two independent slices. (A) A **symmetric classifier guard** in `classify_valuation` returns `evidence_insufficient` for `theme ∈ {"metals"}` when `valuation_percentile_fundamental is None` — withholding both cheap and expensive verdicts (lowest-risk, ship first). (B) An **accumulate-forward sector-PE pipeline**: a display-name→slug normalization layer makes the existing PE anchor reachable, a dedicated csindex fetcher reads the canonical `市盈率1` (PE-TTM) column, a second best-effort ingest leg grows the series weekly, and a stricter min-history gate prevents false precision on thin series. The generator emits 中文 index names for recognised CSI index funds so the mapping survives monthly universe regen. Narrative surfaces the withheld valuation as a non-blocking risk driver.

**Tech Stack:** Python 3.12, uv, DuckDB, pandas, AkShare (`stock_zh_index_value_csindex`), pytest, ruff. Frozen dataclasses + `dataclasses.replace`; pure stage cores, I/O at the edges.

---

## Background: invariants you must not break

Read these before touching code; they are enforced by existing tests:

- **TDD red→green→refactor.** Every logic change starts with a failing test. Test file mirrors source (`foo.py` → `tests/.../test_foo.py`).
- **Functional / immutable.** Pure stage cores; never mutate arguments; frozen dataclasses returned via `dataclasses.replace`.
- **No live AkShare in unit tests.** Live tests are double-gated (`pytest.mark.<name>` marker AND an `IRC_*=1` env var). All new unit tests use csindex-shaped **fixtures** and `unittest.mock.patch` on `_ak_call` — never the network.
- **`基金概况` is forbidden** in production fetch code. `tests/fundamentals/test_static_profile_invariant.py` greps for the literal. Never emit it. (The new fetcher does not consult fund-profile indicators at all.)
- **Symmetric guard invariant (the core lock).** For a commodity-cyclical theme with no fundamental anchor, the guard withholds **every** directional verdict — cheap *and* expensive/very_expensive — and returns `evidence_insufficient`. Narrowing it to "reject only expensive" is a **regression**, not a refinement (spec §"Core invariant").
- **H3 publishability is unaffected.** The narrative change in §4 must NOT add an `evidence_gap` — it only appends a risk **driver**. `publishable_rows = [r for r in kept_rows if not r.evidence_gaps]` must keep `evidence_insufficient`-valuation rows publishable.
- **Files <200 lines, functions <20 lines** ideal. Extract helpers rather than nest >3 levels.

## Ordering (dependency-respecting)

1. **Task 1 (§1 guard)** — independent; smallest, lowest-risk; locks the core invariant. Ships first.
2. **Task 2 (§2.1 lookthrough constants)** — defines `_SECTOR_INDEX_DISPLAY`, `_INDEX_NAME_TO_SLUG`, `_SECTOR_INDEX_KEYS`, `_INDEX_VALUATION_KEYS`. Must land before Tasks 3, 5, 6 (they import these).
3. **Task 3 (§2.1 + §2.2 + §3 inputs_loader)** — slug normalization, `_INDEX_VALUATION_KEYS` membership, min-history gate. Depends on Task 2.
4. **Task 4 (§2.3 csindex fetcher)** — `_SECTOR_INDEX_CODE`, `_CSINDEX_PE_TTM_COL`, `fetch_cn_sector_index_valuation_history`. Depends on Task 2 (imports `_SECTOR_INDEX_DISPLAY` slugs only conceptually; the CODE map is local).
5. **Task 5 (§2 ingest second leg)** — second `ingest_index_valuation_history` call with `_SECTOR_INDEX_KEYS` + the sector fetcher. Depends on Tasks 2 + 4.
6. **Task 6 (§2.1 generator branch)** — `_tracked_index_for` sector branch. Independent of Tasks 3–5 but logically pairs with Task 2's display names.
7. **Task 7 (§4 narrative driver)** — `_state_drivers` surfaces `evidence_insufficient`. Independent.
8. **Task 8 (CONTEXT.md invariant entry)** — documentation. Last.

## File-level map

| File | Responsibility | Task |
|---|---|---|
| `src/irc/opportunity/states.py` | `COMMODITY_CYCLICAL_THEMES` + symmetric guard in `classify_valuation` equity branch | 1 |
| `src/irc/opportunity/lookthrough.py` | `_SECTOR_INDEX_DISPLAY`, `_INDEX_NAME_TO_SLUG`, `_SECTOR_INDEX_KEYS`, `_INDEX_VALUATION_KEYS` | 2 |
| `src/irc/opportunity/inputs_loader.py` | slug normalization + `_INDEX_VALUATION_KEYS` membership; min-history gate over non-null PE; keep latest-null guard | 3 |
| `src/irc/fundamentals/akshare_index_valuation.py` | `_SECTOR_INDEX_CODE`, `_CSINDEX_PE_TTM_COL = "市盈率1"`, `fetch_cn_sector_index_valuation_history` | 4 |
| `src/irc/commands/ingest_cmd.py` | second `ingest_index_valuation_history` call (sector keys + sector fetcher) | 5 |
| `src/irc/discovery/cn_fund_universe.py` | `_tracked_index_for` sector branch | 6 |
| `src/irc/narrative/risk.py` | `_state_drivers` surfaces `evidence_insufficient` valuation (non-blocking) | 7 |
| `CONTEXT.md` | "Commodity-cyclical NAV-anchor exclusion" invariant entry | 8 |
| tests (mirrors of each) | per §4 of the spec | each task |

---

## Task 1: Symmetric commodity-cyclical valuation guard (§1)

**Files:**
- Modify: `src/irc/opportunity/states.py` (add `COMMODITY_CYCLICAL_THEMES` near `_EQUITY_ASSET_CLASSES` at line ~142–147; add guard in `classify_valuation` equity branch, after the `_BOND_ASSET_CLASSES` early-return at line 239, before the `fund_pct = inp.valuation_percentile_fundamental` block at line 244)
- Test: `tests/opportunity/test_states.py` (append after the existing valuation tests, e.g. after `test_pb_corroboration_note_appears_without_changing_state` at line ~146)

Reference (current code):
- `_EQUITY_ASSET_CLASSES` is defined at `states.py:142-144` and already includes `qdii_global`.
- `classify_valuation` starts at `states.py:229`; the bond early-return is at `:239-240`; the NAV-fallback block begins at `:244`.
- `inp.theme` is populated on `OpportunityInput` (`inputs_build.py:53`); `OpportunityInput.theme: str | None = None` (`opportunity/types.py:75`).

- [ ] **Step 1: Write the failing invariant-lock tests**

Append to `tests/opportunity/test_states.py`:

```python
# ---------------------------------------------------------------------------
# §1 commodity-cyclical NAV-anchor exclusion (symmetric guard)
# ---------------------------------------------------------------------------

from irc.opportunity.states import COMMODITY_CYCLICAL_THEMES


def test_commodity_cyclical_themes_is_metals_only():
    # Locked membership: the guard is bound to the theme set, not a shortlist.
    assert COMMODITY_CYCLICAL_THEMES == frozenset({"metals"})


def test_metals_no_fundamental_anchor_withholds_low_nav_would_be_cheap():
    # Low NAV percentile would read `cheap` — symmetric guard withholds it.
    inp = _make(
        asset_class="cn_equity_fund",
        theme="metals",
        valuation_percentile_fundamental=None,
        valuation_percentile_self=0.05,
    )
    state, reason = classify_valuation(inp)
    assert state == "evidence_insufficient"
    assert "锚" in reason or "动量" in reason


def test_metals_no_fundamental_anchor_withholds_high_nav_would_be_very_expensive():
    # High NAV percentile would read `very_expensive` — symmetric guard withholds it.
    inp = _make(
        asset_class="cn_equity_fund",
        theme="metals",
        valuation_percentile_fundamental=None,
        valuation_percentile_self=0.97,
    )
    state, _ = classify_valuation(inp)
    assert state == "evidence_insufficient"


def test_metals_guard_covers_qdii_global_cross_asset_class():
    # qdii_global is in _EQUITY_ASSET_CLASSES; a metals-themed QDII (378546) is guarded too.
    inp = _make(
        asset_class="qdii_global",
        theme="metals",
        valuation_percentile_fundamental=None,
        valuation_percentile_self=0.97,
    )
    state, _ = classify_valuation(inp)
    assert state == "evidence_insufficient"


def test_metals_with_pe_anchor_skips_guard_and_uses_pe_rule():
    # A metals fund that HAS a PE anchor uses the existing PE band rule.
    inp = _make(
        asset_class="cn_equity_fund",
        theme="metals",
        valuation_percentile_fundamental=0.05,  # PE cheap
        valuation_percentile_self=0.97,          # NAV high (ignored)
    )
    state, _ = classify_valuation(inp)
    assert state == "cheap"


def test_non_metals_equity_no_regression_keeps_nav_banding():
    # A non-metals equity fund with no fundamental anchor still bands off NAV.
    inp = _make(
        asset_class="cn_equity_fund",
        theme="semiconductor",
        valuation_percentile_fundamental=None,
        valuation_percentile_self=0.97,
    )
    state, _ = classify_valuation(inp)
    assert state == "very_expensive"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_states.py -q -k "metals or commodity_cyclical"`
Expected: FAIL — `ImportError: cannot import name 'COMMODITY_CYCLICAL_THEMES'` (and, once that name exists, the `evidence_insufficient` assertions fail because the guard is not yet wired).

- [ ] **Step 3: Add the `COMMODITY_CYCLICAL_THEMES` constant**

In `src/irc/opportunity/states.py`, immediately after `_EQUITY_ASSET_CLASSES` (ends at line 144) add:

```python
# NAV self-history percentile is price momentum, not valuation, for these
# themes. When no fundamental anchor exists the verdict is withheld
# SYMMETRICALLY (cheap AND expensive alike) — see CONTEXT.md
# "Commodity-cyclical NAV-anchor exclusion". Extensible without touching
# call sites.
COMMODITY_CYCLICAL_THEMES: frozenset[str] = frozenset({"metals"})
```

- [ ] **Step 4: Wire the symmetric guard into `classify_valuation`**

In `src/irc/opportunity/states.py`, inside `classify_valuation`, insert the guard **after** the bond early-return (`states.py:239-240`) and **before** the `fund_pct = inp.valuation_percentile_fundamental` line (`:244`):

```python
    if inp.asset_class in _BOND_ASSET_CLASSES:
        return classify_bond_valuation(inp)
    # §1 commodity-cyclical NAV-anchor exclusion. For a commodity-cyclical
    # theme with NO fundamental anchor, the NAV self-history percentile is
    # price momentum, not valuation. Withhold EVERY directional verdict —
    # cheap AND expensive alike (symmetric, see CONTEXT.md). A metals fund that
    # later gains a PE anchor (fund_pct is not None) skips this and uses the PE
    # rule below.
    if (
        inp.asset_class in _EQUITY_ASSET_CLASSES
        and inp.theme in COMMODITY_CYCLICAL_THEMES
        and inp.valuation_percentile_fundamental is None
    ):
        return (
            "evidence_insufficient",
            "NAV 价格百分位是动量而非估值；该周期性主题无基本面锚（PE 历史），"
            "方向性估值判断暂缺。",
        )
    # Phase 1 (item 001): the FUNDAMENTAL index PE-TTM percentile decides the
```

(The trailing comment line is the existing `:241` comment; leave it and the rest of the function unchanged.)

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_states.py -q -k "metals or commodity_cyclical"`
Expected: PASS (6 passed).

- [ ] **Step 6: Run the full states test file (no-regression check)**

Run: `uv run pytest tests/opportunity/test_states.py -q`
Expected: PASS (all existing tests still green — the guard only fires for metals-themed equity with `fund_pct is None`; the existing `_make()` default has `theme=None` so no test regresses).

- [ ] **Step 7: Lint**

Run: `uv run ruff check src/irc/opportunity/states.py tests/opportunity/test_states.py`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add src/irc/opportunity/states.py tests/opportunity/test_states.py
git commit -m "feat(opportunity): symmetric commodity-cyclical NAV-anchor valuation guard (§1)"
```

---

## Task 2: Sector-index slug constants in lookthrough (§2.1 + §2.2)

**Files:**
- Modify: `src/irc/opportunity/lookthrough.py` (add new constants after `_BROAD_INDEX_KEYS` at line 61; do NOT change `map_lookthrough`)
- Test: `tests/opportunity/test_lookthrough_sector_keys.py` (NEW — a small constants-only test file; `tests/opportunity/test_lookthrough.py` already exists and tests `map_lookthrough`, keep it untouched)

Reference (current code): `_BROAD_INDEX_DISPLAY` at `lookthrough.py:6-16`, `_BROAD_INDEX_KEYS = frozenset(_BROAD_INDEX_DISPLAY.keys())` at `:61`.

Slug ↔ 中文 mapping to wire (from spec Open items; CSI codes belong to Task 4):

| slug | 中文 display | keyword family |
|---|---|---|
| `csi_nonferrous` | `中证有色金属` | 有色 |
| `csi_resource` | `中证资源` | 资源 |
| `csi_nonferrous_mining` | `中证有色金属矿业主题` | 矿业 |

(`中证有色` is a colloquial short form of `中证有色金属` and resolves to `csi_nonferrous` via the inversion below. The funds 165520/161217/690008/018132 all map into one of these three slugs by keyword in Task 6.)

- [ ] **Step 1: Write the failing constants test**

Create `tests/opportunity/test_lookthrough_sector_keys.py`:

```python
from __future__ import annotations

from irc.opportunity.lookthrough import (
    _BROAD_INDEX_KEYS,
    _INDEX_NAME_TO_SLUG,
    _INDEX_VALUATION_KEYS,
    _SECTOR_INDEX_DISPLAY,
    _SECTOR_INDEX_KEYS,
)


def test_sector_index_display_has_expected_slugs():
    assert set(_SECTOR_INDEX_DISPLAY) == {
        "csi_nonferrous", "csi_resource", "csi_nonferrous_mining",
    }
    assert _SECTOR_INDEX_DISPLAY["csi_nonferrous"] == "中证有色金属"
    assert _SECTOR_INDEX_DISPLAY["csi_resource"] == "中证资源"
    assert _SECTOR_INDEX_DISPLAY["csi_nonferrous_mining"] == "中证有色金属矿业主题"


def test_sector_index_keys_mirror_display_keys():
    assert _SECTOR_INDEX_KEYS == frozenset(_SECTOR_INDEX_DISPLAY.keys())


def test_index_name_to_slug_inverts_display_names_lowercased():
    # 中文 display names resolve back to slugs (lowercasing is a no-op for CJK).
    assert _INDEX_NAME_TO_SLUG["中证有色金属"] == "csi_nonferrous"
    assert _INDEX_NAME_TO_SLUG["中证资源"] == "csi_resource"
    assert _INDEX_NAME_TO_SLUG["中证有色金属矿业主题"] == "csi_nonferrous_mining"
    # Colloquial short form also resolves.
    assert _INDEX_NAME_TO_SLUG["中证有色"] == "csi_nonferrous"


def test_index_name_to_slug_excludes_broad_names():
    # Broad display names are NOT added here — broad re-activation is a separate opt-in.
    assert "沪深300" not in _INDEX_NAME_TO_SLUG
    assert "中证1000" not in _INDEX_NAME_TO_SLUG


def test_index_valuation_keys_is_broad_union_sector():
    assert _INDEX_VALUATION_KEYS == _BROAD_INDEX_KEYS | _SECTOR_INDEX_KEYS
    # Broad keys still present (membership backward-compatible).
    assert "csi300" in _INDEX_VALUATION_KEYS
    assert "csi_nonferrous" in _INDEX_VALUATION_KEYS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/opportunity/test_lookthrough_sector_keys.py -q`
Expected: FAIL — `ImportError: cannot import name '_SECTOR_INDEX_DISPLAY'`.

- [ ] **Step 3: Add the constants**

In `src/irc/opportunity/lookthrough.py`, after line 61 (`_BROAD_INDEX_KEYS = frozenset(_BROAD_INDEX_DISPLAY.keys())`) add:

```python
# Sector-index slugs that gain a PE anchor via the csindex accumulate-forward
# path (§2). Populated with SECTOR indices only for this PR — broad display
# names are deliberately NOT inverted here so broad-fund behaviour is unchanged
# (broad #102 re-activation is a separate opt-in).
_SECTOR_INDEX_DISPLAY: dict[str, str] = {
    "csi_nonferrous": "中证有色金属",
    "csi_resource": "中证资源",
    "csi_nonferrous_mining": "中证有色金属矿业主题",
}

_SECTOR_INDEX_KEYS: frozenset[str] = frozenset(_SECTOR_INDEX_DISPLAY.keys())

# Inversion (中文/lowercased → slug). Includes a colloquial short-form alias so
# a generator-emitted "中证有色" resolves to the canonical slug.
_INDEX_NAME_TO_SLUG: dict[str, str] = {
    **{name.lower(): slug for slug, name in _SECTOR_INDEX_DISPLAY.items()},
    "中证有色": "csi_nonferrous",
}

# The full valuation key-set the inputs loader tests membership against — the
# union of broad (#102) and sector (this PR). Overloading "broad" is avoided.
_INDEX_VALUATION_KEYS: frozenset[str] = _BROAD_INDEX_KEYS | _SECTOR_INDEX_KEYS
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/opportunity/test_lookthrough_sector_keys.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the existing lookthrough test (no-regression)**

Run: `uv run pytest tests/opportunity/test_lookthrough.py -q`
Expected: PASS (`map_lookthrough` is untouched).

- [ ] **Step 6: Lint**

Run: `uv run ruff check src/irc/opportunity/lookthrough.py tests/opportunity/test_lookthrough_sector_keys.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/irc/opportunity/lookthrough.py tests/opportunity/test_lookthrough_sector_keys.py
git commit -m "feat(opportunity): sector-index slug/display constants + _INDEX_VALUATION_KEYS (§2.1/§2.2)"
```

---

## Task 3: Slug normalization + min-history gate in inputs_loader (§2.1 + §2.2 + §3)

**Files:**
- Modify: `src/irc/opportunity/inputs_loader.py`
  - import: change `from irc.opportunity.lookthrough import _BROAD_INDEX_KEYS` (line 17) to import `_INDEX_NAME_TO_SLUG` and `_INDEX_VALUATION_KEYS`
  - add module constants `MIN_PE_POINTS = 120`, `MIN_PE_DAYS = 180`
  - rewrite `_index_valuation_metrics` (lines 142-162): resolve slug, test `_INDEX_VALUATION_KEYS`, apply min-history gate over non-null PE while preserving the latest-null guard
- Test: `tests/opportunity/test_inputs_loader.py` (append after `test_populate_inputs_null_latest_pe_pb_yields_none_percentile` at line ~491)

Reference (current code), `inputs_loader.py:142-162`:

```python
def _index_valuation_metrics(
    con: duckdb.DuckDBPyConnection, tracked_index: str | None,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """..."""
    key = (tracked_index or "").strip().lower() or None
    if key is None or key not in _BROAD_INDEX_KEYS:
        return None, None, None, None, None
    df = _index_valuation_series(con, key)
    if df.empty:
        return None, None, None, None, None
    latest = df.iloc[-1]
    pe = _none_if_na(latest["pe_ttm"])
    pb = _none_if_na(latest["pb"])
    div = _none_if_na(latest["dividend_yield"])
    pe_series = pd.Series(df["pe_ttm"].to_numpy(), index=pd.to_datetime(df["date"]))
    pb_series = pd.Series(df["pb"].to_numpy(), index=pd.to_datetime(df["date"]))
    pe_pct = self_history_percentile(pe_series) if pe is not None else None
    pb_pct = self_history_percentile(pb_series) if pb is not None else None
    return pe, pb, div, pe_pct, pb_pct
```

Key design notes baked into the implementation:
- `key` resolution becomes `slug = _INDEX_NAME_TO_SLUG.get(norm) or norm` so an already-slug value still works AND a generator-emitted 中文 display name resolves. The DuckDB `index_valuation_series` query then uses `slug` (csindex ingest in Task 5 writes rows keyed by `slug`).
- The min-history gate counts **non-null pe_ttm** observations (`n_valid`) and the **calendar span** in days; below either floor → PE percentile `None`. csi300/csi1000 carry thousands of points so they pass unconditionally (gate is a no-op for broad indices).
- The latest-null guard (`pe_pct ... if pe is not None`) is preserved — `pe` is read from the latest row; when it is None the percentile is None regardless of the gate.
- The gate is applied to **PE** (the spec's §3 wording). PB percentile keeps its existing `pb is not None` guard (csindex sector rows carry `pb=None`, so sector PB percentile is naturally `None`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/opportunity/test_inputs_loader.py` (the `_seed_index_valuation_history`, `_seed_csi300_instrument_with_prices` helpers and `date` import already exist in this file):

```python
# ---------------------------------------------------------------------------
# §2.1 slug normalization + §3 min-history gate (sector PE accumulate)
# ---------------------------------------------------------------------------

from irc.opportunity.inputs_loader import MIN_PE_DAYS, MIN_PE_POINTS


def _seed_sector_instrument_with_prices(con, instrument_id="165520") -> None:
    con.execute(
        "INSERT INTO instruments VALUES "
        f"('{instrument_id}','{instrument_id}','cn_on_exchange','中证800有色ETF',NULL,"
        " 'metals','cny', DATE '2020-01-01', 0.005, 5.0e10, NULL, 6.0, "
        f" TIMESTAMP '2026-05-15', 'test', 'test:{instrument_id}')"
    )
    base = date(2025, 1, 1)
    rows = [
        (instrument_id, date.fromordinal(base.toordinal() + i),
         100.0, 100.0, 100.0, 100.0, 1.0)
        for i in range(300)
    ]
    con.executemany(
        "INSERT INTO prices VALUES (?,?,?,?,?,?,?, "
        f"TIMESTAMP '2026-05-15', 'test', 'test:{instrument_id}')",
        rows,
    )


def test_min_pe_gate_constants_are_120_and_180():
    assert MIN_PE_POINTS == 120
    assert MIN_PE_DAYS == 180


def test_sector_display_name_resolves_and_grounds_pe_when_mature(tmp_path):
    # A display-name tracked_index ("中证有色金属") resolves to slug csi_nonferrous;
    # 130 daily non-null PE points (>120, span >180d) ground a PE percentile.
    con = duckdb.connect(str(tmp_path / "sector_mature.duckdb"))
    ensure_schema(con)
    _seed_sector_instrument_with_prices(con)
    pairs = [(10.0 + i * 0.05, None) for i in range(130)]  # pb None like csindex
    _seed_index_valuation_history(con, "csi_nonferrous", pairs)
    skeleton = OpportunityInput(
        instrument_id="165520", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="中证有色金属", name_cn="中证800有色ETF",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm == pytest.approx(10.0 + 129 * 0.05)
    assert inp.valuation_percentile_fundamental is not None
    # csindex carries no PB → pb percentile stays None.
    assert inp.valuation_percentile_fundamental_pb is None
    con.close()


def test_sector_thin_series_below_min_points_yields_none(tmp_path):
    # 50 non-null PE points (<120) — percentile withheld even though span could pass.
    con = duckdb.connect(str(tmp_path / "sector_thin.duckdb"))
    ensure_schema(con)
    _seed_sector_instrument_with_prices(con)
    pairs = [(20.0 + i * 0.1, None) for i in range(50)]
    _seed_index_valuation_history(con, "csi_nonferrous", pairs)
    skeleton = OpportunityInput(
        instrument_id="165520", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="中证有色金属",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm == pytest.approx(20.0 + 49 * 0.1)  # latest pe still surfaced
    assert inp.valuation_percentile_fundamental is None
    con.close()


def test_sector_short_span_below_min_days_yields_none(tmp_path):
    # 130 points but compressed into < MIN_PE_DAYS calendar span → withheld.
    con = duckdb.connect(str(tmp_path / "sector_shortspan.duckdb"))
    ensure_schema(con)
    _seed_sector_instrument_with_prices(con)
    # Reuse the same date for every row so the span is 0 days (< 180).
    rows = [("csi_nonferrous", date(2026, 1, 1), 10.0 + i * 0.01, None, None)
            for i in range(130)]
    con.executemany(
        "INSERT OR REPLACE INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )
    skeleton = OpportunityInput(
        instrument_id="165520", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="中证有色金属",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.valuation_percentile_fundamental is None
    con.close()


def test_sector_latest_null_pe_yields_none_percentile(tmp_path):
    # 130 valid points + final null PE row → latest-null guard wins, percentile None.
    con = duckdb.connect(str(tmp_path / "sector_nulllatest.duckdb"))
    ensure_schema(con)
    _seed_sector_instrument_with_prices(con)
    valid = [(10.0 + i * 0.05, None) for i in range(130)]
    _seed_index_valuation_history(con, "csi_nonferrous", [*valid, (None, None)])
    skeleton = OpportunityInput(
        instrument_id="165520", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="中证有色金属",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.pe_ttm is None
    assert inp.valuation_percentile_fundamental is None
    con.close()


def test_csi300_scale_unaffected_by_min_history_gate(tmp_path):
    # csi300 with 300 rising daily points still grounds a percentile (gate no-op).
    con = duckdb.connect(str(tmp_path / "csi300_scale.duckdb"))
    ensure_schema(con)
    _seed_csi300_instrument_with_prices(con)
    pairs = [(10.0 + i * 0.02, 1.0 + i * 0.001) for i in range(300)]
    _seed_index_valuation_history(con, "csi300", pairs)
    skeleton = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf",
        market="cn_on_exchange", tracked_index="csi300",
    )
    inp = populate_inputs(con, skeleton, holding_entry_date=None)
    assert inp.valuation_percentile_fundamental == pytest.approx(1.0)
    con.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -q -k "sector or min_pe_gate or csi300_scale"`
Expected: FAIL — `ImportError: cannot import name 'MIN_PE_POINTS'` first; after constants exist, the sector-display-name tests fail because `中证有色金属` does not resolve (still tests `_BROAD_INDEX_KEYS`).

- [ ] **Step 3: Update the lookthrough import**

In `src/irc/opportunity/inputs_loader.py`, replace line 17:

```python
from irc.opportunity.lookthrough import _BROAD_INDEX_KEYS
```

with:

```python
from irc.opportunity.lookthrough import _INDEX_NAME_TO_SLUG, _INDEX_VALUATION_KEYS
```

- [ ] **Step 4: Add the gate constants**

In `src/irc/opportunity/inputs_loader.py`, add near the other module constants (e.g. after `_CPI_YOY_SERIES_ID` at line 76):

```python
# §3 min-history gate for thin accumulating sector-PE series. Return a non-None
# PE percentile ONLY when the series has >= MIN_PE_POINTS non-null PE
# observations AND spans >= MIN_PE_DAYS calendar days. csi300/csi1000 carry
# thousands of points so the gate is a no-op for broad indices.
MIN_PE_POINTS: int = 120
MIN_PE_DAYS: int = 180
```

- [ ] **Step 5: Rewrite `_index_valuation_metrics`**

Replace the body of `_index_valuation_metrics` (`inputs_loader.py:142-162`) with:

```python
def _pe_series_is_mature(pe_series: pd.Series) -> bool:
    """§3 gate: >= MIN_PE_POINTS non-null PE points AND >= MIN_PE_DAYS span."""
    valid = pe_series.dropna()
    if len(valid) < MIN_PE_POINTS:
        return False
    idx = pd.to_datetime(valid.index)
    span_days = (idx.max() - idx.min()).days
    return span_days >= MIN_PE_DAYS


def _index_valuation_metrics(
    con: duckdb.DuckDBPyConnection, tracked_index: str | None,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """Return (pe_ttm, pb, dividend_yield, pe_percentile, pb_percentile) from the
    CACHED index_valuation_history table (R3 — no live fetch). (None,)*5 when the
    index is not a recognised valuation index or has no cached rows.

    The `tracked_index` value may be a display name (e.g. "中证有色金属"); it is
    normalised to a canonical slug via `_INDEX_NAME_TO_SLUG` before membership
    in `_INDEX_VALUATION_KEYS` is tested (§2.1). The PE percentile honours the
    §3 min-history gate AND the latest-null guard.
    """
    norm = (tracked_index or "").strip().lower() or None
    if norm is None:
        return None, None, None, None, None
    slug = _INDEX_NAME_TO_SLUG.get(norm) or norm
    if slug not in _INDEX_VALUATION_KEYS:
        return None, None, None, None, None
    df = _index_valuation_series(con, slug)
    if df.empty:
        return None, None, None, None, None
    latest = df.iloc[-1]
    pe = _none_if_na(latest["pe_ttm"])
    pb = _none_if_na(latest["pb"])
    div = _none_if_na(latest["dividend_yield"])
    pe_series = pd.Series(df["pe_ttm"].to_numpy(), index=pd.to_datetime(df["date"]))
    pb_series = pd.Series(df["pb"].to_numpy(), index=pd.to_datetime(df["date"]))
    pe_pct = (
        self_history_percentile(pe_series)
        if pe is not None and _pe_series_is_mature(pe_series)
        else None
    )
    pb_pct = self_history_percentile(pb_series) if pb is not None else None
    return pe, pb, div, pe_pct, pb_pct
```

Note: `self_history_percentile` already requires ≥30 valid points; `_pe_series_is_mature` is the stricter explicit floor. The `slug` (not `norm`) is passed to `_index_valuation_series` so the DuckDB query reads csindex rows written under the slug key in Task 5.

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -q -k "sector or min_pe_gate or csi300_scale"`
Expected: PASS.

- [ ] **Step 7: Run the full inputs_loader test file (regression check on broad-index path)**

Run: `uv run pytest tests/opportunity/test_inputs_loader.py -q`
Expected: PASS **with one expected fix** — `test_populate_inputs_reads_cached_index_valuation_percentile` (line 208) seeds only **40** csi300 rows and asserts `valuation_percentile_fundamental == 1.0`. 40 < `MIN_PE_POINTS` (120), so the new gate would now return `None` and this test would FAIL. This is a deliberate tightening: bump that fixture to satisfy the gate.

  Edit `test_populate_inputs_reads_cached_index_valuation_percentile` (line 213): change
  `pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(40)]`
  to
  `pairs = [(10.0 + i * 0.1, 1.0 + i * 0.01) for i in range(130)]`
  and update the two latest-value asserts on lines 220-222 from `13.9`/`1.39` to the new latest:
  `assert inp.pe_ttm == pytest.approx(10.0 + 129 * 0.1)` (== 22.9) and
  `assert inp.pb == pytest.approx(1.0 + 129 * 0.01)` (== 2.29).
  The `valuation_percentile_fundamental == 1.0` / `_pb == 1.0` and `earnings_yield == 1/<latest pe>` asserts stay (update the earnings_yield divisor to `22.9`).

  Also audit these fixtures that seed `[(...)] * 30` or `* 30`-scale rows and assert a non-None `valuation_percentile_fundamental` — they must be bumped to ≥120 points spanning ≥180 days, OR their assertion relaxed to `is None`. Inspect each and adjust to keep intent:
  - `test_populate_inputs_real_yield_in_ratio_units` (line 248): seeds `[(14.0, 1.3)] * 30`; it asserts `real_yield`/`earnings_yield`, NOT the fundamental percentile, so it stays green (latest pe still surfaced). No change needed.
  - `test_populate_inputs_no_live_index_fetch` (line 268): seeds `[(12.0, 1.3)] * 30`; asserts only `pe_ttm == 12.0`. No change needed.
  - `test_consensus_upside_notch_fires_on_genuinely_cheap_percentile` (line 494) and `test_population_consumes_consensus_upside_per_item_002` (line 404): these set `valuation_percentile_fundamental` directly on the input or seed single rows — read each and confirm they do not depend on the loader deriving a non-None percentile from a <120-point series. If one does, bump its seed to 130 points. (Run the file and let failures pinpoint the exact fixtures rather than guessing.)

  After edits, re-run: `uv run pytest tests/opportunity/test_inputs_loader.py -q` → Expected: PASS.

- [ ] **Step 8: Lint**

Run: `uv run ruff check src/irc/opportunity/inputs_loader.py tests/opportunity/test_inputs_loader.py`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add src/irc/opportunity/inputs_loader.py tests/opportunity/test_inputs_loader.py
git commit -m "feat(opportunity): slug-normalize tracked_index + min-history PE gate (§2.1/§2.2/§3)"
```

---

## Task 4: csindex sector PE-TTM fetcher (§2.3)

**Files:**
- Modify: `src/irc/fundamentals/akshare_index_valuation.py` (add `_SECTOR_INDEX_CODE`, `_CSINDEX_PE_TTM_COL`, `_csindex_pe_ttm_map`, `fetch_cn_sector_index_valuation_history`)
- Test: `tests/fundamentals/test_akshare_index_valuation.py` (append after the existing history tests at line ~154)

Reference (current code): `_PE_COLS` at `akshare_index_valuation.py:33` (legulegu names — must NOT be reused for csindex). `_DATE_COLS` at `:36`. `_ak_call` indirection at `:39-42`. `_fetch_frame` at `:80-86`. `_series_map` at `:89-113`. `IndexValuationHistory` / `IndexValuationPoint` from `index_valuation_types`.

CSI codes to wire (from spec Open items; verified live during implementation — see live-test step):

| slug | CSI code | 中证 index |
|---|---|---|
| `csi_nonferrous` | `930708` | 中证有色金属 (中证有色) |
| `csi_resource` | `000819` | 中证资源 |
| `csi_nonferrous_mining` | `931892` | 中证有色金属矿业主题 |

(`930708` is confirmed in the spec for 中证有色金属. `csi_resource`/`csi_nonferrous_mining` CSI codes above are best-effort placeholders to be confirmed by the gated live test in Step 8; the unit tests do not depend on the literal codes — they mock `_ak_call`. If a live probe shows a different code, update `_SECTOR_INDEX_CODE` only.)

Canonical PE column: `市盈率1` (PE-TTM/trailing). The fetcher must NOT reuse `_series_map(..., _PE_COLS)` — it uses a dedicated `_CSINDEX_PE_TTM_COL` constant and a dedicated date-column resolution. csindex frames expose 中文 date columns; resolve via the existing `_DATE_COLS` precedence (`日期/date/trade_date`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/fundamentals/test_akshare_index_valuation.py`:

```python
from irc.fundamentals.akshare_index_valuation import (
    _CSINDEX_PE_TTM_COL,
    fetch_cn_sector_index_valuation_history,
)

# csindex-shaped frame: 市盈率1 (PE-TTM) + 市盈率2 (LYR) + 股息率 cols, NO pb col.
_CSINDEX_FRAME = pd.DataFrame({
    "日期": ["2026-05-26", "2026-05-27", "2026-05-28"],
    "市盈率1": [26.50, 26.80, 26.97],
    "市盈率2": [29.10, 29.20, 29.28],
    "股息率1": [1.10, 1.10, 1.12],
    "股息率2": [1.20, 1.20, 1.22],
})


def test_csindex_pe_ttm_col_is_市盈率1():
    assert _CSINDEX_PE_TTM_COL == "市盈率1"


def test_sector_fetch_unknown_slug_returns_none_without_calling_ak():
    with patch("irc.fundamentals.akshare_index_valuation._ak_call") as mocked:
        out = fetch_cn_sector_index_valuation_history("not_a_sector")
    assert out is None
    mocked.assert_not_called()


def test_sector_fetch_reads_市盈率1_and_sets_pb_none():
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        return_value=_CSINDEX_FRAME,
    ):
        out = fetch_cn_sector_index_valuation_history("csi_nonferrous")
    assert isinstance(out, IndexValuationHistory)
    assert out.index_key == "csi_nonferrous"
    assert len(out.rows) == 3
    assert [r.date_iso for r in out.rows] == ["2026-05-26", "2026-05-27", "2026-05-28"]
    # PE comes from 市盈率1 (TTM), NOT 市盈率2.
    assert out.rows[-1].pe_ttm == pytest.approx(26.97)
    # csindex has NO PB column.
    assert all(r.pb is None for r in out.rows)


def test_sector_fetch_fails_if_only_legulegu_pe_names_present():
    # A frame carrying ONLY legulegu PE names (平均市盈率) must NOT yield PE —
    # proves the fetcher does not fall back to _PE_COLS.
    legulegu_frame = pd.DataFrame({
        "日期": ["2026-05-28"],
        "平均市盈率": [12.1],
    })
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        return_value=legulegu_frame,
    ):
        out = fetch_cn_sector_index_valuation_history("csi_nonferrous")
    # No 市盈率1 column → no usable PE rows → degrade to None.
    assert out is None


def test_sector_fetch_passes_csi_code_to_ak_call():
    calls: list[dict] = []

    def _fake(fn_name, **kwargs):
        calls.append({"fn": fn_name, **kwargs})
        return _CSINDEX_FRAME

    with patch("irc.fundamentals.akshare_index_valuation._ak_call", side_effect=_fake):
        fetch_cn_sector_index_valuation_history("csi_nonferrous")
    assert calls and calls[0]["fn"] == "stock_zh_index_value_csindex"
    # csi_nonferrous -> 930708
    assert calls[0].get("symbol") == "930708"


def test_sector_fetch_degrades_to_none_on_adapter_exception():
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        side_effect=RuntimeError("network down"),
    ):
        assert fetch_cn_sector_index_valuation_history("csi_nonferrous") is None


def test_sector_fetch_returns_none_on_empty_frame():
    with patch(
        "irc.fundamentals.akshare_index_valuation._ak_call",
        return_value=pd.DataFrame(),
    ):
        assert fetch_cn_sector_index_valuation_history("csi_nonferrous") is None
```

(`pytest` is already importable in this file? It currently uses bare `assert`; add `import pytest` at the top of the test module if `pytest.approx` is used and not yet imported.)

- [ ] **Step 2: Add `import pytest` if missing**

Check the top of `tests/fundamentals/test_akshare_index_valuation.py`. If `import pytest` is absent, add it under `from unittest.mock import patch`. (`pytest.approx` is used in the new tests.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -q -k "sector or csindex"`
Expected: FAIL — `ImportError: cannot import name '_CSINDEX_PE_TTM_COL'`.

- [ ] **Step 4: Add the csindex constants + fetcher**

In `src/irc/fundamentals/akshare_index_valuation.py`, after `_DIV_COLS`/`_DATE_COLS` (line 35-36) add:

```python
# §2.3 csindex canonical PE column. CSI publishes 市盈率1 = total mkt-cap ÷ TTM
# attributable net profit (PE-TTM/trailing); 市盈率2 is static/LYR. This is a
# DEDICATED constant — csindex column names are NOT in the legulegu _PE_COLS set,
# so this fetcher must not reuse _series_map(..., _PE_COLS).
_CSINDEX_PE_TTM_COL: str = "市盈率1"

# Sector slug -> CSI index code (csindex `stock_zh_index_value_csindex` symbol).
# 930708 confirmed live for 中证有色金属; the other two are best-effort,
# confirmed by the gated live test (degrade-to-None on miss).
_SECTOR_INDEX_CODE: dict[str, str] = {
    "csi_nonferrous": "930708",
    "csi_resource": "000819",
    "csi_nonferrous_mining": "931892",
}
```

Then add the fetcher near the bottom of the file (after `fetch_cn_index_valuation_history`):

```python
def _csindex_pe_ttm_map(df: pd.DataFrame) -> dict[str, float | None]:
    """Pure: map each parseable date to its 市盈率1 (PE-TTM) value. Empty map when
    the frame lacks 市盈率1 or a date column. Does NOT consult legulegu _PE_COLS."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    if _CSINDEX_PE_TTM_COL not in df.columns:
        return {}
    date_col = next((c for c in _DATE_COLS if c in df.columns), None)
    if date_col is None:
        return {}
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    out: dict[str, float | None] = {}
    for d, raw in zip(parsed, df[_CSINDEX_PE_TTM_COL], strict=True):
        if pd.isna(d):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = None
        if value is not None and pd.isna(value):
            value = None
        out[d.date().isoformat()] = value
    return out


def fetch_cn_sector_index_valuation_history(
    index_key: str,
) -> IndexValuationHistory | None:
    """Full PE-TTM series (from csindex 市盈率1) for a recognised sector index;
    None for unknown slugs / adapter failure / no usable PE rows. pb is always
    None (csindex carries no PB column). AkShare-only ingest infra (R4)."""
    code = _SECTOR_INDEX_CODE.get(index_key)
    if code is None:
        return None
    df = _fetch_frame("stock_zh_index_value_csindex", code)
    if df is None:
        return None
    pe_map = _csindex_pe_ttm_map(df)
    dates = sorted(pe_map)
    if not dates:
        return None
    rows = tuple(
        IndexValuationPoint(
            date_iso=d,
            pe_ttm=pe_map.get(d),
            pb=None,
            dividend_yield=None,
        )
        for d in dates
    )
    return IndexValuationHistory(index_key=index_key, rows=rows)
```

Note: `_fetch_frame(fn_name, cn_name)` passes its second arg as `symbol=`. The csindex symbol is the numeric CSI code, so `_fetch_frame("stock_zh_index_value_csindex", code)` calls `_ak_call("stock_zh_index_value_csindex", symbol=code)` — matching `test_sector_fetch_passes_csi_code_to_ak_call`.

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -q -k "sector or csindex"`
Expected: PASS.

- [ ] **Step 6: Run the full fetcher test file (no-regression)**

Run: `uv run pytest tests/fundamentals/test_akshare_index_valuation.py -q`
Expected: PASS (legulegu fetchers untouched).

- [ ] **Step 7: Run the `基金概况` acceptance test (forbidden-string lock)**

Run: `uv run pytest tests/fundamentals/test_static_profile_invariant.py -q`
Expected: PASS. (The new fetcher consults no fund-profile indicator; it operates only on csindex index codes. This test does not currently grep `akshare_index_valuation.py`, but run it to confirm no regression in the production modules it does grep.)

- [ ] **Step 8 (OPTIONAL — live verification, gated): confirm CSI codes + that 市盈率1 is TTM**

This step requires network and is double-gated; default `pytest` skips it. Run it once during implementation to confirm the three CSI codes return a numeric PE and that 市盈率1 ≤ 市盈率2 (TTM ≤ static in an upcycle, per spec). Add a live test mirroring `tests/fundamentals/test_index_valuation_live.py`:

```python
# tests/fundamentals/test_sector_index_valuation_live.py
from __future__ import annotations
import os
import pytest
from irc.fundamentals.akshare_index_valuation import (
    _SECTOR_INDEX_CODE,
    fetch_cn_sector_index_valuation_history,
)

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(not _RUN, reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests"),
]


@pytest.mark.parametrize("slug", sorted(_SECTOR_INDEX_CODE))
def test_sector_index_pe_ttm_live(slug):
    out = fetch_cn_sector_index_valuation_history(slug)
    assert out is not None, f"{slug} ({_SECTOR_INDEX_CODE[slug]}) returned no history"
    pes = [r.pe_ttm for r in out.rows if r.pe_ttm is not None]
    assert pes, f"{slug}: no numeric 市盈率1 PE — confirm the CSI code/column"
    assert all(p > 0 for p in pes)
    print(f"\n  ✓ {slug} ({_SECTOR_INDEX_CODE[slug]}) live: latest PE-TTM={pes[-1]}")
```

Run: `IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare tests/fundamentals/test_sector_index_valuation_live.py -v -s`
Expected: each slug prints a positive latest PE-TTM. If a slug returns `None`, fix its code in `_SECTOR_INDEX_CODE` and re-run. (If skipped due to no network, proceed — the offline tests fully cover the code path; record in the task notes that codes are unverified.)

- [ ] **Step 9: Lint**

Run: `uv run ruff check src/irc/fundamentals/akshare_index_valuation.py tests/fundamentals/test_akshare_index_valuation.py`
Expected: `All checks passed!`

- [ ] **Step 10: Commit**

```bash
git add src/irc/fundamentals/akshare_index_valuation.py tests/fundamentals/test_akshare_index_valuation.py
git commit -m "feat(fundamentals): csindex sector PE-TTM fetcher reading canonical 市盈率1 (§2.3)"
```

---

## Task 5: Second ingest leg for sector index valuation (§2)

**Files:**
- Modify: `src/irc/commands/ingest_cmd.py`
  - import `_SECTOR_INDEX_KEYS` alongside `_BROAD_INDEX_KEYS` (line 25)
  - import `fetch_cn_sector_index_valuation_history` from `irc.fundamentals.akshare_index_valuation`
  - add a SECOND `ingest_index_valuation_history` call (sector keys + sector fetcher) right after the existing broad-index leg (`ingest_cmd.py:569-576`), best-effort/non-fatal
- Test: `tests/commands/test_ingest_index_valuation_wiring.py` (extend the existing source-grep test)

Reference (current code), `ingest_cmd.py:565-576`:

```python
        # Item 001 Phase 1a — index PE/PB history (best-effort, non-fatal).
        ...
        try:
            iv_rows = ingest_index_valuation_history(
                con, tuple(sorted(_BROAD_INDEX_KEYS)), now_iso=_now_iso(),
            )
            ak_counts["index_valuation_history"] = iv_rows
        except Exception as exc:  # noqa: BLE001 — best-effort enrichment
            _log.warning("index_valuation_history ingest failed: %s", exc, exc_info=True)
            ak_counts["index_valuation_history"] = 0
```

The existing wiring test (`test_ingest_index_valuation_wiring.py`) is a **source-grep** test over `inspect.getsource(ingest_cmd.run_ingest)`. Extend it; no runtime DuckDB harness needed.

- [ ] **Step 1: Write the failing wiring tests**

Append to `tests/commands/test_ingest_index_valuation_wiring.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_ingest_index_valuation_wiring.py -q`
Expected: FAIL — `_SECTOR_INDEX_KEYS` / `fetch_cn_sector_index_valuation_history` not present in `ingest_cmd` source.

- [ ] **Step 3: Add the imports**

In `src/irc/commands/ingest_cmd.py`, change line 25:

```python
from irc.opportunity.lookthrough import _BROAD_INDEX_KEYS
```

to:

```python
from irc.opportunity.lookthrough import _BROAD_INDEX_KEYS, _SECTOR_INDEX_KEYS
```

and add (near line 16, beside the other `irc.fundamentals` import or just below the ingestor import at line 24):

```python
from irc.fundamentals.akshare_index_valuation import (
    fetch_cn_sector_index_valuation_history,
)
```

- [ ] **Step 4: Add the second ingest leg**

In `src/irc/commands/ingest_cmd.py`, immediately after the existing broad-index `try/except` block (ends at line 576, the `ak_counts["index_valuation_history"] = 0` line), insert:

```python
        # §2 — sector index PE history (csindex accumulate-forward, best-effort).
        # INSERT OR REPLACE on (index_key, date) dedups overlapping weekly windows;
        # the thin series grows over time until the §3 min-history gate switches
        # PE grounding on. Non-fatal — a miss degrades to NAV-fallback + the §1
        # guard, not a halt. Mirrors the broad-index leg above.
        try:
            sector_rows = ingest_index_valuation_history(
                con,
                tuple(sorted(_SECTOR_INDEX_KEYS)),
                fetch=fetch_cn_sector_index_valuation_history,
                now_iso=_now_iso(),
            )
            ak_counts["index_valuation_history"] += sector_rows
        except Exception as exc:  # noqa: BLE001 — best-effort enrichment
            _log.warning(
                "sector index_valuation_history ingest failed: %s", exc, exc_info=True
            )
```

Note: `ak_counts["index_valuation_history"]` is already set by the broad-index leg above (to `iv_rows` or `0`), so `+=` is safe. `ingest_index_valuation_history` already accepts a `fetch` keyword param (`index_valuation_ingestor.py:26`).

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `uv run pytest tests/commands/test_ingest_index_valuation_wiring.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Run the ingestor unit tests + ingest_cmd import smoke (regression)**

Run: `uv run pytest tests/data/test_index_valuation_ingestor.py tests/commands/test_ingest_index_valuation_wiring.py -q`
Expected: PASS. (The ingestor signature is unchanged; only a second call is added.)

- [ ] **Step 7: Verify the module imports cleanly (catch import cycles)**

Run: `uv run python -c "import irc.commands.ingest_cmd"`
Expected: no output, exit 0. (Confirms the new `irc.fundamentals.akshare_index_valuation` import does not introduce a cycle — it already imports `irc.opportunity.lookthrough`, which `ingest_cmd` also imports, so this is acyclic.)

- [ ] **Step 8: Lint**

Run: `uv run ruff check src/irc/commands/ingest_cmd.py tests/commands/test_ingest_index_valuation_wiring.py`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add src/irc/commands/ingest_cmd.py tests/commands/test_ingest_index_valuation_wiring.py
git commit -m "feat(ingest): second best-effort sector-index valuation leg via csindex (§2)"
```

---

## Task 6: Generator sector-index branch (§2.1)

**Files:**
- Modify: `src/irc/discovery/cn_fund_universe.py` (`_tracked_index_for`, lines 108-156 — add a sector branch that emits the 中文 index name for recognised CSI **index** funds; active resource funds emit `None`)
- Test: `tests/discovery/test_cn_fund_universe.py` (append after the existing classification tests)

Reference (current code): `_tracked_index_for(fund_name, asset_class, theme)` at `cn_fund_universe.py:108`. The `cn_etf` themed branch at `:154-155` currently returns `fund_name` verbatim for any themed `cn_etf`. The new sector branch must fire BEFORE that fallback so 有色/资源/矿业 ETFs get a canonical 中文 index name instead of their raw fund name. Active funds (`cn_equity_fund`, off-exchange) hit none of these branches and return `None` (stay guarded).

Behaviour to implement:
- For `asset_class == "cn_etf"` whose name matches a sector keyword, emit the matching display name:
  - `矿业` (most specific) → `中证有色金属矿业主题`
  - `有色` → `中证有色金属`
  - `资源` → `中证资源`
- Non-matching themed `cn_etf` keeps the existing `fund_name` fallback.
- `cn_equity_fund` (active resource funds) returns `None` (no branch matches).

The display strings MUST match `_SECTOR_INDEX_DISPLAY` (Task 2) so `_INDEX_NAME_TO_SLUG` resolves them. Order checks most-specific-first so a "有色金属矿业" fund maps to `csi_nonferrous_mining`, not `csi_nonferrous`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/discovery/test_cn_fund_universe.py` (`CatalogFund` / `classify_catalog_fund` are imported in this file; confirm and add `_tracked_index_for` to the import if testing it directly):

```python
from irc.discovery.cn_fund_universe import _tracked_index_for


def test_tracked_index_for_nonferrous_etf_emits_中证有色金属():
    assert _tracked_index_for("华夏中证有色金属ETF", "cn_etf", "metals") == "中证有色金属"


def test_tracked_index_for_resource_etf_emits_中证资源():
    assert _tracked_index_for("招商中证资源ETF", "cn_etf", "metals") == "中证资源"


def test_tracked_index_for_mining_etf_emits_矿业主题_most_specific():
    # 有色金属矿业 contains 有色 AND 矿业 — most-specific (矿业) wins.
    assert (
        _tracked_index_for("国泰中证有色金属矿业主题ETF", "cn_etf", "metals")
        == "中证有色金属矿业主题"
    )


def test_tracked_index_for_active_resource_fund_emits_none():
    # Active cn_equity_fund (no single index) stays guarded → None.
    assert _tracked_index_for("某某资源精选混合A", "cn_equity_fund", "metals") is None


def test_tracked_index_for_non_sector_cn_etf_keeps_fund_name_fallback():
    # A themed cn_etf NOT matching 有色/资源/矿业 keeps the existing fallback.
    assert _tracked_index_for("半导体ETF", "cn_etf", "semiconductor") == "半导体ETF"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/discovery/test_cn_fund_universe.py -q -k "tracked_index_for"`
Expected: FAIL — the nonferrous/resource/mining ETFs currently return their raw `fund_name` (e.g. `"华夏中证有色金属ETF"`), not the canonical display name.

- [ ] **Step 3: Add the sector branch**

In `src/irc/discovery/cn_fund_universe.py`, inside `_tracked_index_for`, insert the sector branch immediately **before** the `if asset_class == "cn_etf" and theme is not None:` fallback (currently at line 154):

```python
    if asset_class == "cn_etf":
        # §2.1 — recognised CSI sector-index ETFs emit a canonical 中文 index
        # name (matching _SECTOR_INDEX_DISPLAY) so _INDEX_NAME_TO_SLUG resolves
        # them and the accumulate-forward PE anchor becomes reachable. Most
        # specific keyword first (矿业 before 有色).
        if "矿业" in fund_name and "有色" in fund_name:
            return "中证有色金属矿业主题"
        if "有色" in fund_name:
            return "中证有色金属"
        if "资源" in fund_name:
            return "中证资源"
    if asset_class == "cn_etf" and theme is not None:
        return fund_name
    return None
```

(Leave the trailing `cn_bond_fund` branch and the final `return None` as they are — insert above the existing `if asset_class == "cn_etf" and theme is not None:` line, NOT after the final return.)

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest tests/discovery/test_cn_fund_universe.py -q -k "tracked_index_for"`
Expected: PASS.

- [ ] **Step 5: Run the full generator test file (no-regression)**

Run: `uv run pytest tests/discovery/test_cn_fund_universe.py -q`
Expected: PASS. (`test_classifies_domestic_etf_only_with_exchange_traded_evidence` at line 94 asserts a `沪深300` ETF → `沪深300`; the broad-keyword loop at `:132-144` runs before the new sector branch, so broad ETFs are unaffected.)

- [ ] **Step 6: Lint**

Run: `uv run ruff check src/irc/discovery/cn_fund_universe.py tests/discovery/test_cn_fund_universe.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/irc/discovery/cn_fund_universe.py tests/discovery/test_cn_fund_universe.py
git commit -m "feat(discovery): emit canonical CSI sector-index name for 有色/资源/矿业 ETFs (§2.1)"
```

---

## Task 7: Narrative surfaces withheld valuation as a non-blocking driver (§4)

**Files:**
- Modify: `src/irc/narrative/risk.py` (`_state_drivers`, lines 26-49 — append a driver when `view.valuation_state == "evidence_insufficient"`)
- Test: `tests/narrative/test_risk.py` (append after `test_multiple_drivers_escalate_to_high` at line ~100)

Reference (current code): `_state_drivers` at `risk.py:26-49`. It returns `tuple[tuple[str, str, int], ...]`. `derive_position_risk_level` (`:52-70`) short-circuits to `("insufficient", ...)` when `view.evidence_gaps` is non-empty (line 60) — BEFORE `_state_drivers` runs. So a withheld valuation on a publishable row (empty `evidence_gaps`) reaches `_state_drivers`.

Design decision (spec §4): weight `w = 1` (mild caveat; a tuning knob). The driver tuple is `("valuation_state", "valuation withheld — no fundamental anchor", 1)`. Do NOT add an evidence_gap — H3 publishability stays untouched.

- [ ] **Step 1: Write the failing tests**

Append to `tests/narrative/test_risk.py`:

```python
def test_evidence_insufficient_valuation_surfaces_driver_non_blocking():
    # A withheld valuation (no fundamental anchor) on a publishable row surfaces a
    # mild driver — NOT silently dropped, NOT forced to 'insufficient'.
    level, rationale, drivers = derive_position_risk_level(
        _view(valuation_state="evidence_insufficient"), _overlap(), {}
    )
    assert "valuation_state" in drivers
    assert "valuation withheld" in rationale
    # weight 1 alone → 'moderate' (not insufficient, not high).
    assert level == "moderate"


def test_evidence_insufficient_valuation_does_not_force_insufficient_level():
    # evidence_gaps drives 'insufficient'; a withheld VALUATION state must not.
    level, _r, _d = derive_position_risk_level(
        _view(valuation_state="evidence_insufficient"), _overlap(), {}
    )
    assert level != "insufficient"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/narrative/test_risk.py -q -k "evidence_insufficient_valuation"`
Expected: FAIL — no `valuation_state` driver is emitted for `evidence_insufficient` today, so `drivers == ()` and `level == "low"`.

- [ ] **Step 3: Add the driver**

In `src/irc/narrative/risk.py`, inside `_state_drivers`, add after the existing `valuation_state` expensive check (lines 32-33):

```python
    if view.valuation_state in ("expensive", "very_expensive"):
        out.append(("valuation_state", f"{view.valuation_state} valuation", 2))
    if view.valuation_state == "evidence_insufficient":
        # §4 — surface a WITHHELD valuation (commodity-cyclical NAV-anchor
        # exclusion) so it appears in the risk rationale rather than being
        # silently benign. Non-blocking: weight 1 (mild caveat, a tuning knob);
        # no evidence_gap is added, so H3 publishability is unaffected.
        out.append(
            ("valuation_state", "valuation withheld — no fundamental anchor", 1)
        )
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest tests/narrative/test_risk.py -q -k "evidence_insufficient_valuation"`
Expected: PASS.

- [ ] **Step 5: Run the full risk test file (no-regression)**

Run: `uv run pytest tests/narrative/test_risk.py -q`
Expected: PASS. (`test_clean_row_is_low` uses `valuation_state="fair"`, untouched; the new branch only fires for `evidence_insufficient`.)

- [ ] **Step 6: Lint**

Run: `uv run ruff check src/irc/narrative/risk.py tests/narrative/test_risk.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/irc/narrative/risk.py tests/narrative/test_risk.py
git commit -m "feat(narrative): surface withheld valuation as a non-blocking risk driver (§4)"
```

---

## Task 8: CONTEXT.md invariant entry

**Files:**
- Modify: `CONTEXT.md` (add the "Commodity-cyclical NAV-anchor exclusion" bullet in the "Failure-mode + audit policy" section, immediately after the existing `valuation_price_fundamental_divergence` bullet at line 48 — they are conceptually adjacent valuation-grounding invariants)

No test (documentation). The bullet records the symmetric-guard invariant and the accumulate-forward path so future edits do not narrow the guard.

- [ ] **Step 1: Add the invariant bullet**

In `CONTEXT.md`, after the `valuation_price_fundamental_divergence` bullet (line 48, in the `## Failure-mode + audit policy` section), insert:

```markdown
- **Commodity-cyclical NAV-anchor exclusion** — for a commodity-cyclical theme (`COMMODITY_CYCLICAL_THEMES = frozenset({"metals"})`, `src/irc/opportunity/states.py`), when **no fundamental anchor exists** (`valuation_percentile_fundamental is None`), the NAV self-history percentile is **not** a valuation anchor — it is price momentum. `classify_valuation` withholds **every** directional verdict — `cheap` *and* `expensive`/`very_expensive` alike — and returns the existing `evidence_insufficient` `ValuationState` **before** any band assignment. The exclusion is **symmetric on purpose**: a metals fund reading `cheap` off a post-crash NAV trough is exactly as much a momentum artifact as one reading `very_expensive` at the peak. A future change narrowing the guard to "reject only the expensive end" re-admits momentum-as-valuation on the cheap side and is a **regression**, not a refinement. Scope: bound to `theme == "metals"`, and `_EQUITY_ASSET_CLASSES` includes `qdii_global`, so the guard covers all metals-themed equity rows (20 `cn_equity_fund` + 1 `qdii_global`, e.g. 378546). A metals fund that later gains a PE anchor (`valuation_percentile_fundamental is not None`) skips the guard and uses the PE rule. The PE anchor accumulates forward via the csindex sector leg (`fetch_cn_sector_index_valuation_history` reading the canonical `市盈率1` PE-TTM column; second best-effort `ingest_index_valuation_history` leg over `_SECTOR_INDEX_KEYS`) and the §3 min-history gate (`MIN_PE_POINTS=120` non-null PE points AND `MIN_PE_DAYS=180` span in `_index_valuation_metrics`). Narrative `_state_drivers` surfaces a withheld valuation as a **non-blocking** mild risk driver (`("valuation_state", "valuation withheld — no fundamental anchor", 1)`) — no `evidence_gap` is added, so H3 publishability is unaffected. Locked by `tests/opportunity/test_states.py` (the symmetric low-NAV + high-NAV + `qdii_global` cross-asset-class invariant tests).
```

- [ ] **Step 2: Verify the entry reads correctly**

Run: `uv run python -c "import pathlib,re; b=pathlib.Path('CONTEXT.md').read_text(); assert 'Commodity-cyclical NAV-anchor exclusion' in b and 'symmetric on purpose' in b; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add CONTEXT.md
git commit -m "docs(context): record commodity-cyclical NAV-anchor exclusion invariant"
```

---

## Final verification (after all tasks)

Run the full set of touched test files together to confirm cross-task coherence (scoped — NOT the full ~18-min suite):

```bash
uv run pytest \
  tests/opportunity/test_states.py \
  tests/opportunity/test_lookthrough_sector_keys.py \
  tests/opportunity/test_lookthrough.py \
  tests/opportunity/test_inputs_loader.py \
  tests/fundamentals/test_akshare_index_valuation.py \
  tests/fundamentals/test_static_profile_invariant.py \
  tests/commands/test_ingest_index_valuation_wiring.py \
  tests/data/test_index_valuation_ingestor.py \
  tests/discovery/test_cn_fund_universe.py \
  tests/narrative/test_risk.py \
  -q
```
Expected: all PASS.

Lint everything touched:

```bash
uv run ruff check src tests
```
Expected: `All checks passed!`

Import smoke (no cycles):

```bash
uv run python -c "import irc.commands.ingest_cmd; import irc.opportunity.inputs_loader; import irc.fundamentals.akshare_index_valuation; print('imports ok')"
```
Expected: `imports ok`.

---

## Self-review notes (judgment calls surfaced for the executor)

- **§3 gate tightens existing csi300 fixtures.** The new `MIN_PE_POINTS=120` floor breaks `test_populate_inputs_reads_cached_index_valuation_percentile` (40-row fixture) and may break other ≥30-but-<120 fixtures that assert a non-None fundamental percentile. Task 3 Step 7 enumerates the fix; let test failures pinpoint the exact fixtures rather than pre-editing blind. This is intended behaviour, not a workaround — broad indices in production carry thousands of points.
- **CSI codes for `csi_resource` / `csi_nonferrous_mining` are best-effort** (only `930708` is spec-confirmed). The offline unit tests mock `_ak_call` and never depend on the literal code; the gated live test (Task 4 Step 8) is the verification point. If a code is wrong, only `_SECTOR_INDEX_CODE` changes.
- **Fund→slug mapping is by ETF-name keyword** (有色/资源/矿业), emitted by the generator (Task 6). The spec lists funds 165520/161217/690008/018132 as CSI-index metals funds; each maps via keyword. 160221 (国证/CNI) and 378546 (qdii_global) are deliberately NOT mapped (no `有色/资源/矿业` ETF branch reaches them — 378546 is `qdii_global`, not `cn_etf`; 160221's name routes through the broad/fallback path) and stay guarded by §1.
- **Narrative driver weight `w=1`** is the spec's default (mild). A single weight-1 driver yields `moderate` via the `_LADDER` severity sum; the test locks this. If the user later wants it weaker/stronger, only the literal `1` changes.
- **Broad-index #102 re-activation is OUT of scope** (spec Open items): `_INDEX_NAME_TO_SLUG` deliberately excludes broad display names, so production broad-fund behaviour is unchanged by this PR. Task 2's `test_index_name_to_slug_excludes_broad_names` locks that boundary.
