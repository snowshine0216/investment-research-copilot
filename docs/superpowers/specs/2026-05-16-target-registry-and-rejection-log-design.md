# Design: per-instrument rejection log + `_TARGET_REGISTRY` expansion

**Date:** 2026-05-16
**Status:** ready for implementation planning
**Scope:** two independent PRs landing in this order — (1) `discovery_rejections.csv` so dropped instruments are traceable; (2) `_TARGET_REGISTRY` expansion so HK QDII, sector themes, and US extras resolve to real constituents.

## Background

Two TODO items from `TODOS.md`:

> 3. Expand `_TARGET_REGISTRY` (HK + sectors + US extras) — add 恒生指数/恒生科技/港股红利/中概互联, add 道琼斯/美国50, map sector themes to dedicated CSI sector indices.
>
> 4. Fix orphaned 科创50 — investigate why 588000/588080 don't reach `scoring.json`.

Investigation showed Item 4 is *not* a snapshot-wiring problem: `_TARGET_REGISTRY["科创50"]` already resolves to `cn_index 000688`. The actual cause is in `discovery/quality_filter.py`: 588000/588080 have ~38.8% three-year drawdown, which exceeds the risk-band cap (`max_drawdown[1]=0.20 × cn_etf buffer 1.4 = 0.28`). They are filtered out before reaching scoring.

The filter behaviour is correct given the user's risk band. The product gap is **visibility**: today's `discovery_diagnostics.csv` aggregates rejections by `(stage, asset_class, theme, reason)` and discards `instrument_id`, so the operator cannot answer "why was 588000 dropped?" from the output files.

Items 3 and 4 are therefore reframed as:
- **PR 1** — surface per-instrument rejection reasons (Item 4 follow-up).
- **PR 2** — close the lookthrough → snapshot coverage gap (Item 3).

## PR 1 — `discovery_rejections.csv`

### Goal

Every instrument that enters the discovery universe but does not reach the watchlist appears in `outputs/<date>/discovery_rejections.csv` with its rejection reasons.

### Output

`outputs/<date>/discovery_rejections.csv`

```csv
stage,instrument_id,ticker,name_cn,asset_class,theme,role,reasons
hard_filter,159352,159352,A500ETF南方,cn_etf,broad,,inception 1.6y < 3.0y
quality_filter,588000,588000,科创50ETF华夏,cn_etf,broad,,drawdown_3y 0.388 > 0.28
quality_filter,588080,588080,科创50ETF易方达,cn_etf,broad,,drawdown_3y 0.388 > 0.28
role_bucket,005051,005051,广发军工指数A,cn_equity_fund,defense,,no_role_match
```

- One row per dropped instrument, attributed to the first stage that drops it. An instrument rejected by `hard_filter` does not appear again under `quality_filter` or `role_bucket`.
- `reasons` joined with `; ` when the stage records multiple.
- `role` populated only on `role_bucket` stage; empty otherwise.

### Architecture

```
run_discovery_with_diagnostics(...)
  ├─ apply_hard_filter      → HardFilterResult(passed, rejected)
  ├─ apply_quality_filter   → HardFilterResult(passed, rejected)
  ├─ bucket_by_role         → RoleBucketResult(buckets, relaxed, failed)
  ├─ build_discovery_diagnostics(...)  (existing, aggregated CSV)
  └─ build_discovery_rejections(...)   (NEW, per-instrument CSV)
```

New module `src/irc/discovery/rejections.py`:

```python
def build_discovery_rejections(
    universe: tuple[UniverseRow, ...],
    hard: HardFilterResult,
    quality: HardFilterResult,
    bucketed: RoleBucketResult,
) -> pd.DataFrame
```

Pure function. Joins each `Rejection` to its `UniverseRow` for human-readable columns (`name_cn`, `asset_class`, `theme`). `role_bucket` doesn't currently track "no rule matched" instruments — they're implicit (no `pred` returned true). The new module derives that set as `{r.instrument_id for r in quality.passed} − union(r.instrument_id for r in bucketed.buckets.values())`.

### Wiring

- `DiscoveryRunResult` gains a `rejections: pd.DataFrame` field.
- `run_discovery_with_diagnostics` populates it.
- `discover_cmd.run_discover` writes `out_dir / "discovery_rejections.csv"` via `atomic_write_text` (same pattern as `discovery_diagnostics.csv`).

### Out of scope

- The filter thresholds themselves. `config/discovery.yaml` stays as-is.
- The aggregated `discovery_diagnostics.csv` schema. Untouched.

### Tests

- `tests/discovery/test_rejections.py` — pure-function coverage:
  - hard-filter rejection only,
  - quality-filter rejection only,
  - role-bucket "no rule matched" case,
  - multi-reason joining.
- Extend `tests/commands/test_discover_cmd.py` to assert the new file is written and parses as CSV.

## PR 2 — `_TARGET_REGISTRY` expansion

### Goal

`map_lookthrough(input).display_cn` always resolves to a `_TARGET_REGISTRY` entry that fetches real constituents. No display name silently falls into the `evidence_insufficient` path because of a missing registry entry.

### Coverage matrix

| Bucket | Display names | Spec kind |
|---|---|---|
| Broad CN (existing) | 沪深300 中证500 中证1000 中证A500 上证50 科创50 创业板 中证红利 红利低波 | `cn_index` |
| **Sector themes (new)** | 半导体 医药 新能源 消费 金融 军工 有色金属 房地产 国企改革 科技 | `cn_index` |
| US QDII (existing + new) | 标普500 纳斯达克100 **道琼斯 美国50 美股大盘** | `us_symbols` |
| **HK QDII (new)** | 恒生指数 恒生科技 港股红利 中概互联 | `hk_index` |

### New spec kind: `hk_index`

Today's `hk_symbols` path takes a hardcoded `symbols` tuple. HK *indices* need the same shape as `cn_index` — a code, a top-N fetch, then per-symbol filing digests.

```python
@dataclass(frozen=True)
class _TargetSpec:
    kind: str               # 'cn_index' | 'us_symbols' | 'hk_symbols' | 'hk_index'
    code: str = ""
    symbols: tuple[str, ...] = ()
```

Dispatch in `build_snapshot`:

```python
if spec.kind == "hk_index":
    return _build_hk_index_snapshot(target, spec, top_n, timestamp)
```

`_build_hk_index_snapshot` mirrors `_build_cn_snapshot`: fetch top-N constituents → call `fetch_hk_filing_digest` for each.

### New adapter: `fetch_hk_index_constituents`

Lives in `src/irc/fundamentals/akshare_fundamentals.py` next to `fetch_cn_index_constituents`.

```python
def fetch_hk_index_constituents(code: str, top_n: int) -> tuple[Constituent, ...]
```

Contract:
- Returns `Constituent` instances with `market="hk"`.
- Returns `()` on any failure (no raise).
- Uses akshare's HK-index constituent endpoint via the existing `_ak_call` indirection. Exact akshare function name is an implementation-time decision; candidates: `stock_hk_index_constituent_em` or `index_stock_hk_em`. Whichever ships, it lives behind this contract.

### Sector-index resolution — deprecate `sector_proxy.py`

Today `src/irc/opportunity/sector_proxy.py` maps a theme to a *broad* index name (e.g. `semiconductor → 沪深300`). Sector evidence from 沪深300 constituents is useless for a 半导体 thesis.

The new design routes each sector theme display name **directly** through `_TARGET_REGISTRY`. Because `map_lookthrough(...).display_cn` already produces `"半导体"`, `"医药"`, … they land in the registry the same way `"沪深300"` does.

`sector_proxy.proxy_target_for_theme` and its caller in `thesis_evidence` are deleted.

### Sector index code mapping

Tentative codes (to verify against AkShare before implementation locks them in):

| Theme | Index name | Code |
|---|---|---|
| 半导体 | 中证全指半导体 | `H30184` |
| 医药 | 中证医药卫生 | `000933` |
| 新能源 | 中证新能源 | `399808` |
| 消费 | 中证主要消费 | `000932` |
| 金融 | 中证金融 | `000934` |
| 军工 | 中证军工 | `399967` |
| 有色金属 | 中证有色金属 | `H30202` |
| 房地产 | 中证全指房地产 | `000952` |
| 国企改革 | 央企创新驱动 | `000861` |
| 科技 | 中证科技龙头 | `931087` |

Verification step is part of the implementation plan: run `fetch_cn_index_constituents(code, top_n=10)` once per code; any code that returns `()` gets swapped for a working AkShare-supported equivalent before the PR lands.

### US extras

Plain additions to the existing `us_symbols` path:
- `"道琼斯"` → top-10 DJIA names by weight.
- `"美国50"` → top-10 of FTSE Russell US Large Cap 50.
- `"美股大盘"` → reuse the 标普500 list.

### Error handling

Existing pattern, no new convention:
- Adapter returns `None` / `()` on any exception (no raise).
- `_build_*_snapshot` collects per-symbol failures into `failure_reasons` and continues.
- `build_snapshot` never raises. Downstream code already handles partial snapshots.

### Coupling test (drift guard)

`tests/opportunity/test_lookthrough.py` already pins that every `map_lookthrough` output's `display_cn` exists as a key in `_TARGET_REGISTRY`. Extend the parametrised list to cover every new display name. This is the spec's primary safety net against drift between `lookthrough.py` and `snapshot.py`.

### Test plan

| File | Tests |
|---|---|
| `tests/fundamentals/test_snapshot.py` | New `kind="hk_index"` dispatch; sector-index target (`半导体`) routes to `cn_index` fetcher with the expected code; unknown target still returns empty snapshot with `failure_reason`. |
| `tests/fundamentals/test_akshare_fundamentals.py` | `fetch_hk_index_constituents` happy path + failure-returns-`()` (mock akshare via `_ak_call`). |
| `tests/opportunity/test_lookthrough.py` | Parametrise the drift check across the full new display-name set. |
| `tests/opportunity/test_thesis_evidence.py` | `sector_proxy` removal: themes formerly proxied to 沪深300 now flow through the real sector snapshot path. Update or delete proxy-specific assertions. |

### Out of scope for PR 2

- No change to `fetch_hk_filing_digest` itself — it already handles single HK symbols.
- No change to the snapshot cache layer — keyed on `(lookthrough_target, as_of_iso)`, agnostic to spec kind.
- No change to discovery / scoring / opportunity downstream — they consume `ConstituentSnapshot`, not registry entries.
- No backfill of `data/fundamentals/2026Q1/*.json` — produced by the existing all-target workflow on next run.

## Sequencing

PR 1 ships first because:
- It's smaller and self-contained (one new module, one new output file).
- It immediately answers the original investigative question for 588000/588080.
- PR 2 will produce *new* rejection patterns once sector themes resolve to real constituent fetches; having the rejection log in place first makes that diff easier to read.

PR 2 ships second.

## Risks and follow-ups

- **AkShare HK-index endpoint stability:** the new `fetch_hk_index_constituents` depends on an akshare function whose exact name and schema must be verified at implementation time. If no clean endpoint exists, the fallback is the `hk_symbols` path with a hardcoded top-10 tuple per HK index — same approach as today's US QDII targets. Spec accepts this fallback without re-design.
- **Sector index code drift:** the code mapping above is tentative. The implementation plan's first step is a verification pass against AkShare's actual offerings. Any code that fails gets replaced before the PR opens.
- **Filter policy still hidden in CSV:** PR 1 makes rejections visible but doesn't surface "should this filter be relaxed for high-vol indices?" as a UI question. Out of scope here; a future change could add per-asset-class overrides in `config/overrides.yaml`.
