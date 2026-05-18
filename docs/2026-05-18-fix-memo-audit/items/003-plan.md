# Item 003 — Plan

## Goal
Stop `discipline_report.md` from rendering `110022 110022` / `512960 512960` / etc. by ensuring the 5 affected IDs resolve to a real instrument record with a non-empty `name_cn`.

## Root cause confirmed

`config/universe/cn_funds.yaml` (user-side) is a heavily trimmed copy of `src/irc/templates/config/universe/cn_funds.yaml` (template) and does NOT contain the 5 IDs. `cn_funds.generated.yaml` doesn't either. Result: in `opportunity_cmd.py:92` the `instr` lookup returns `None`, so `name_cn` falls back to `instrument_id`.

The 5 IDs flow into scoring/opportunity because they came from an earlier discovery run that's still cached in DuckDB or scoring.json — they're not in the latest watchlist either.

## Approach

Two-part fix:

1. **Data:** add the 5 entries to `config/universe/cn_funds.yaml`. Use the names already present in `src/irc/templates/config/universe/cn_funds.yaml` so we stay consistent with the project's curated naming.
2. **Defensive code:** when `instr is None` in `_build_input`, emit `f"未登记({iid})"` instead of the raw ID. Makes future unknown IDs visually distinct so we don't have to chase the same bug per fund.

## Steps

### 1. Add the 5 entries to `config/universe/cn_funds.yaml`

Append after the existing block:

```yaml
  # === 主动权益基金 (consumer/blue-chip/balanced) ===
  - { instrument_id: "110022", ticker: "110022", market: cn_off_exchange,
      name_cn: "易方达消费行业", asset_class: cn_equity_fund, currency: cny,
      theme: consumer, venue_required: [cmb_fund] }
  - { instrument_id: "005827", ticker: "005827", market: cn_off_exchange,
      name_cn: "易方达蓝筹精选", asset_class: cn_equity_fund, currency: cny,
      venue_required: [cmb_fund] }
  - { instrument_id: "163417", ticker: "163417", market: cn_off_exchange,
      name_cn: "兴全合宜A", asset_class: cn_equity_fund, currency: cny,
      venue_required: [cmb_fund] }
  - { instrument_id: "161005", ticker: "161005", market: cn_off_exchange,
      name_cn: "富国天惠成长LOF", asset_class: cn_equity_fund, currency: cny,
      venue_required: [cmb_fund] }
  # === 主题ETF (央企创新) ===
  - { instrument_id: "512960", ticker: "512960", market: cn_on_exchange,
      name_cn: "央企创新ETF博时", asset_class: cn_etf, currency: cny,
      theme: soe, tracked_index: "中证国新央企科技引领",
      venue_required: [cn_brokerage] }
```

### 2. Defensive fallback in `opportunity_cmd._build_input`

`src/irc/commands/opportunity_cmd.py:92`:

```python
name_cn = (
    instr.name_cn if instr is not None
    else f"未登记({score_row.get('instrument_id', '')})"
)
```

### 3. Tests

Add a new test file: `tests/discovery/test_universe_completeness.py`

```python
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[2]

REQUIRED_IDS = ("110022", "005827", "163417", "161005", "512960")


def test_recently_scored_ids_have_names_in_cn_funds_yaml() -> None:
    """Five IDs that appeared in 2026-05-18 outputs without a name_cn are now
    registered in config/universe/cn_funds.yaml. Discovered via the discipline
    report rendering '110022 110022' (id-twice) — root cause was these IDs
    missing from the universe entirely. See docs/2026-05-18-fix-memo-audit/items/003-spec.md."""
    data = yaml.safe_load((REPO / "config" / "universe" / "cn_funds.yaml").read_text())
    by_id = {row["instrument_id"]: row for row in data["instruments"]}
    for iid in REQUIRED_IDS:
        assert iid in by_id, f"{iid} missing from cn_funds.yaml"
        name = by_id[iid].get("name_cn", "")
        assert name, f"{iid} has empty name_cn"
        assert name != iid, f"{iid} name_cn is the id itself"
```

Existing tests in `tests/decision/test_completeness.py` already cover the asset-class logic, so no further test surface change needed.

Also add a small test for the defensive fallback. File: `tests/opportunity/test_build_input_fallback.py` (new).

```python
# Targeted test: when instr is None in _build_input, the fallback name_cn
# should be the deterministic "未登记(<id>)" placeholder, not the id itself.
# This protects against future unknown IDs flowing through and producing
# misleading "<id> <id>" lines in the discipline report.
from unittest.mock import MagicMock

from irc.commands.opportunity_cmd import _build_input


def test_build_input_unknown_instrument_uses_placeholder_name():
    score_row = {"instrument_id": "999999", "asset_class": "cn_equity_fund", "role": ""}
    con = MagicMock()
    con.execute.return_value.fetchdf.return_value.empty = True
    inp = _build_input(
        score_row=score_row, instr=None, holding=None, target_band=None,
        portfolio_total_cny=0.0, available_venues=set(), con=con,
    )
    assert inp.name_cn == "未登记(999999)"
```

### 4. Verify

```
uv run pytest tests/discovery/test_universe_completeness.py tests/opportunity/test_build_input_fallback.py -v
uv run pytest tests/scoring tests/decision tests/trades tests/memo tests/opportunity tests/allocation tests/discovery -q
```

### 5. Commit + push + PR
