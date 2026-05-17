# Item 008 — Implementation Plan

> Reference: `docs/AUTODEV-LOOP/items/008-spec.md`. Base: `feat/evidence-wiring-and-memo-enrichment`. Sub-branch: `claude/p1p2-008-venue-registry-backfill`.

## Diagnosis (what's actually wrong)

The user's `inputs/account.yaml` lists `available_venues: [cmb_fund, cmb_gold]` (CMB bank only — no brokerage). Every on-exchange A-share ETF, US ETF, HK ETF in `config/universe/` has `venue_required: [cn_brokerage]` / `[us_brokerage]` / `[hk_brokerage]`. There is no overlap → `venue_compatible=False` for all of them.

`_proxy_for` at `src/irc/trades/venue_check.py:21-33` then tries to find a substitute, but enforces a STRICT `i.asset_class == target.asset_class` match. Off-exchange CSI300 / Nasdaq100 / etc. index funds exist in `config/universe/cn_funds.generated.yaml` with `tracked_index` set, but they have `asset_class: cn_equity_fund` (not `cn_etf`). So the proxy search finds nothing → `proxy_id=None` → status falls to `blocked_no_proxy`.

The fix is one targeted relaxation: when the target is an equity-style ETF (`cn_etf` / `us_etf` / `hk_etf`) AND has a non-empty `tracked_index`, allow an off-exchange `cn_equity_fund` proxy if its `tracked_index` matches. Bonds and active funds without `tracked_index` are unaffected.

## Goal

After this change, instruments like 510300 / 510050 / 159919 (cn_etf, tracked_index=沪深300/上证50) get a non-null `proxy_id` pointing to a same-index off-exchange fund when one exists in the universe. Other instruments (bonds, gold, unique trackers) stay as before.

## Files

| File | Change |
|---|---|
| `src/irc/trades/venue_check.py` | Add `_PROXY_ASSET_CLASS_SUBSTITUTIONS` + relax `_proxy_for` |
| `tests/trades/test_venue_check.py` | Three new tests covering the cross-class proxy paths |
| `src/irc/decision/gates.py` (read-only verification) | Confirm no downstream consumer breaks |

No data/yaml changes. The universe registry already has the right `tracked_index` metadata; only the proxy-matching logic needs to be permissive enough to use it.

---

## Task 1: Add cross-asset-class proxy substitution

### Step 1.1: Write the failing tests

- [ ] Add to `tests/trades/test_venue_check.py`:

```python
def test_cn_etf_proxied_by_cn_equity_fund_with_same_tracked_index():
    """A-share index ETFs can be proxied via off-exchange index funds tracking
    the same benchmark — this is the canonical CMB-bank-only setup."""
    universe = _u([
        {"instrument_id": "510300", "ticker": "510300", "market": "cn_on_exchange",
         "name_cn": "华泰柏瑞沪深300ETF", "asset_class": "cn_etf", "currency": "cny",
         "tracked_index": "沪深300", "venue_required": ["cn_brokerage"]},
        {"instrument_id": "OFF300", "ticker": "OFF300", "market": "cn_off_exchange",
         "name_cn": "嘉实沪深300指数研究增强A", "asset_class": "cn_equity_fund",
         "currency": "cny", "tracked_index": "沪深300", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="510300",
                      available_venues=["cmb_fund", "cmb_gold"], universe=universe)
    assert out.compatible is False
    assert out.proxy_id == "OFF300"


def test_us_etf_proxied_by_cn_equity_fund_qdii_with_same_index():
    universe = _u([
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "S&P 500", "venue_required": ["us_brokerage"]},
        {"instrument_id": "QDII500", "ticker": "006075", "market": "cn_off_exchange",
         "name_cn": "易方达标普500", "asset_class": "cn_equity_fund", "currency": "cny",
         "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="VTI",
                      available_venues=["cmb_fund"], universe=universe)
    assert out.proxy_id == "QDII500"


def test_bond_fund_does_not_get_cross_class_proxy():
    """Active bond funds are NOT substitutable across asset_classes —
    the cross-class relaxation only applies to index-tracked equity ETFs."""
    universe = _u([
        {"instrument_id": "111111", "ticker": "111111", "market": "cn_off_exchange",
         "name_cn": "纯债基金A", "asset_class": "cn_bond_fund", "currency": "cny",
         "venue_required": ["cn_brokerage"]},
        # A cn_equity_fund exists, but it's a different asset_class and has no
        # matching tracked_index, so it must NOT be offered as a proxy.
        {"instrument_id": "OTHEREQ", "ticker": "OTHEREQ", "market": "cn_off_exchange",
         "name_cn": "其他基金", "asset_class": "cn_equity_fund", "currency": "cny",
         "tracked_index": "沪深300", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="111111",
                      available_venues=["cmb_fund"], universe=universe)
    assert out.proxy_id is None


def test_cross_class_proxy_requires_matching_tracked_index():
    """Even within the allow-list, the tracked_index MUST match — we don't
    silently substitute a CSI300 fund for an SSE50 ETF."""
    universe = _u([
        {"instrument_id": "510050", "ticker": "510050", "market": "cn_on_exchange",
         "name_cn": "上证50ETF", "asset_class": "cn_etf", "currency": "cny",
         "tracked_index": "上证50", "venue_required": ["cn_brokerage"]},
        {"instrument_id": "OFF300", "ticker": "OFF300", "market": "cn_off_exchange",
         "name_cn": "沪深300指数基金", "asset_class": "cn_equity_fund",
         "currency": "cny", "tracked_index": "沪深300", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="510050",
                      available_venues=["cmb_fund"], universe=universe)
    assert out.proxy_id is None


def test_cross_class_proxy_requires_target_to_be_index_tracked():
    """An equity ETF with no tracked_index (rare, but possible) must NOT
    silently substitute a tracked fund — same-class match still applies."""
    universe = _u([
        {"instrument_id": "WEIRD", "ticker": "WEIRD", "market": "cn_on_exchange",
         "name_cn": "未定指数ETF", "asset_class": "cn_etf", "currency": "cny",
         "tracked_index": "", "venue_required": ["cn_brokerage"]},
        {"instrument_id": "OFF300", "ticker": "OFF300", "market": "cn_off_exchange",
         "name_cn": "沪深300指数基金", "asset_class": "cn_equity_fund",
         "currency": "cny", "tracked_index": "沪深300", "venue_required": ["cmb_fund"]},
    ])
    out = check_venue(instrument_id="WEIRD",
                      available_venues=["cmb_fund"], universe=universe)
    assert out.proxy_id is None
```

### Step 1.2: Run tests, confirm they fail
- [ ] Run: `uv run pytest tests/trades/test_venue_check.py -v`
- [ ] Expected: 5 new tests FAIL (the cross-class allow-list doesn't exist yet), existing 3 PASS.

### Step 1.3: Add the allow-list + relax `_proxy_for`

- [ ] Replace the contents of `src/irc/trades/venue_check.py` with:

```python
from __future__ import annotations
from dataclasses import dataclass
from irc.schemas.universe import UniverseConfig, Instrument


@dataclass(frozen=True)
class VenueCheckResult:
    compatible: bool
    proxy_id: str | None
    note: str


# Cross-asset-class substitution for proxy lookup. The target's asset_class
# maps to the set of asset_classes whose instruments may serve as proxies.
# Equity-style ETFs (cn_etf, us_etf, hk_etf) can be proxied by off-exchange
# index funds (cn_equity_fund) when the tracked_index matches. Bonds, gold,
# and active funds proxy only within their own class.
_PROXY_ASSET_CLASS_SUBSTITUTIONS: dict[str, frozenset[str]] = {
    "cn_etf": frozenset({"cn_etf", "cn_equity_fund"}),
    "us_etf": frozenset({"us_etf", "cn_equity_fund"}),
    "hk_etf": frozenset({"hk_etf", "cn_equity_fund"}),
}


def _allowed_proxy_classes(target_class: str) -> frozenset[str]:
    return _PROXY_ASSET_CLASS_SUBSTITUTIONS.get(target_class, frozenset({target_class}))


def _find(universe: UniverseConfig, iid: str) -> Instrument | None:
    for i in universe.instruments:
        if i.instrument_id == iid:
            return i
    return None


def _proxy_for(
    target: Instrument, universe: UniverseConfig, available_venues: set[str],
) -> Instrument | None:
    """Find a proxy: same tracked_index, venue compatible with user, asset_class
    in the documented substitution set for the target's class.

    Cross-asset-class substitution is gated on a non-empty target tracked_index:
    we never silently substitute an active/unindexed fund.
    """
    target_index = (target.tracked_index or "").strip()
    allowed_classes = _allowed_proxy_classes(target.asset_class)
    cross_class = len(allowed_classes) > 1
    # When the rule allows cross-class substitution, the target itself MUST
    # be index-tracked — otherwise we have no benchmark to match on.
    if cross_class and not target_index:
        allowed_classes = frozenset({target.asset_class})
    for i in universe.instruments:
        if i.instrument_id == target.instrument_id:
            continue
        if i.asset_class not in allowed_classes:
            continue
        if (i.tracked_index or "").strip() != target_index:
            continue
        if not i.venue_required or set(i.venue_required) & available_venues:
            return i
    return None


def check_venue(
    instrument_id: str, available_venues: list[str], universe: UniverseConfig,
) -> VenueCheckResult:
    target = _find(universe, instrument_id)
    if target is None:
        return VenueCheckResult(compatible=False, proxy_id=None,
                                note=f"instrument {instrument_id} not in universe")
    if set(target.venue_required) & set(available_venues):
        return VenueCheckResult(compatible=True, proxy_id=None, note="direct match")
    proxy = _proxy_for(target, universe, set(available_venues))
    if proxy is not None:
        return VenueCheckResult(
            compatible=False, proxy_id=proxy.instrument_id,
            note=f"venue mismatch; proxy via {proxy.instrument_id} ({proxy.name_cn})",
        )
    return VenueCheckResult(compatible=False, proxy_id=None,
                            note="venue mismatch and no proxy available; consider opening new account")
```

### Step 1.4: Run tests
- [ ] Run: `uv run pytest tests/trades/test_venue_check.py -v`
- [ ] Expected: all 8 PASS.

### Step 1.5: Sanity-check the trades pipeline still works end-to-end
- [ ] Run: `uv run pytest tests/trades/ -v`
- [ ] Expected: all PASS, no regression in `test_pipeline.py`.

### Step 1.6: Commit
- [ ] Run:

```bash
git add src/irc/trades/venue_check.py tests/trades/test_venue_check.py
git commit -m "feat(trades): cross-class proxy substitution for index-tracked equity ETFs"
```

---

## Task 2: Full-suite verification

### Step 2.1: Run all tests
- [ ] Run: `uv run pytest -q -x`
- [ ] Expected: all PASS. If any test in `tests/opportunity/` or `tests/commands/` relied on a specific instrument having `proxy_id=None`, it may now find a proxy — update the assertion if it's outdated.

### Step 2.2: Ruff
- [ ] Run: `uv run ruff check src/irc/trades/ tests/trades/`
- [ ] Expected: no new findings.
