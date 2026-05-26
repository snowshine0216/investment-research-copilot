# Ship blocked — item 002 (round 1)

Source: `/ship` steps 8 (code-reviewer + silent-failure-hunter) + 9 (adversarial). Fix before re-invoking `/ship`.

## P0 — must fix before landing

### P0-1 · Silent exception swallow in `fetch_qdii_premium_pct` with no logging

File: `src/irc/data/akshare_client.py`

The fetcher has a bare `except Exception:` that returns `None` with zero log output. AkShare schema changes, network failures, import errors, and unrelated bugs all manifest as `qdii_premium_unknown` downstream — but production debugging has no signal to distinguish them.

**Fix:**

1. Confirm the file already has a module-level `_log` logger (check imports — most adapters in this file use one). If not, add: `import logging; _log = logging.getLogger(__name__)` near the top.

2. Change the bare `except Exception:` blocks in **both** `fetch_qdii_premium_pct` and `_fetch_full_etf_spot_table` (if it has one) to:

```python
except Exception as exc:
    _log.warning(
        "fetch_qdii_premium_pct failed for %s: %s",
        symbol, exc, exc_info=True,
    )
    return None
```

Adjust the symbol kwarg to match the actual variable name in scope (e.g. `symbol` in `fetch_qdii_premium_pct`; "<bulk-table>" or similar string literal in `_fetch_full_etf_spot_table` since there's no per-symbol context there).

3. Add a unit test confirming the logger is called on a forced exception. Pattern: use `caplog` fixture in pytest and assert `"failed for"` substring in `caplog.text` after invoking with a mocked AkShare that raises.

### P0-2 · `qdii_premium_resolver` unhandled raise can silently drop subsequent rows in `run_scoring`

File: `src/irc/scoring/pipeline.py`

The resolver call inside the sequential `for r in rows:` loop has no try/except. If `qdii_premium_for_row` or the underlying fetcher raises (e.g. `SystemExit`, future regression that narrows the broad catch in P0-1's fixed fetcher), the whole `run_scoring` call aborts mid-loop and every row AFTER the failing QDII row is silently dropped from the scores output.

**Fix:**

Wrap the resolver call in a try/except that logs and treats as None. Mirror the pattern used for macro_fit futures (lines 80-86 in the same file have a logged warning + graceful fallback). The wrapped block:

```python
try:
    premium = qdii_premium_resolver(
        row_asset_class, row_market, str(r.instrument_id)
    )
except Exception as exc:
    _log.warning(
        "qdii_premium_resolver raised for %s: %s",
        r.instrument_id, exc, exc_info=True,
    )
    premium = None
if premium is not None:
    score_row["qdii_premium_pct"] = premium
```

Confirm `_log` is in scope at that point (same module). If not, import it. Add a test that simulates a resolver raising and verifies `run_scoring` still returns all expected rows with the affected row's `qdii_premium_pct` left unset (treated as unknown by the gate).

## P1 — should fix in this PR

### P1-1 · Magic `0.05` literals in `memo_cmd.py` function defaults

Files: `src/irc/commands/memo_cmd.py` lines 438 and 499

`_decision_status_for_pick` and `_build_pick_rows` both use `qdii_max_premium_pct: float = 0.05` as the default. The constant `QDII_MAX_PREMIUM_DEFAULT = 0.05` exists in `src/irc/schemas/discovery.py` precisely to avoid this duplication. If someone changes `QDII_MAX_PREMIUM_DEFAULT`, these two defaults will silently diverge.

**Fix:**

1. Move `from irc.schemas.discovery import QDII_MAX_PREMIUM_DEFAULT` from inside `run_memo` (around line 611) to the module-level import block.

2. Replace `qdii_max_premium_pct: float = 0.05` with `qdii_max_premium_pct: float = QDII_MAX_PREMIUM_DEFAULT` in both function signatures.

3. Run `uv run ruff check src/irc/commands/memo_cmd.py` to confirm no new violations.

### P1-2 · `qdii_max_premium_pct: 0` silently blocks all QDII buys (adversarial finding)

File: `src/irc/schemas/discovery.py`

Pydantic accepts `qdii_max_premium_pct: 0` (because constraint is `ge=0`). Every QDII fund with even 0.01% premium then trips `qdii_premium_too_high`, with no diagnostic explaining that the threshold itself is zero. Wrong-decision output.

**Fix:**

Change the constraint from `ge=0` to `gt=0` (strict greater-than). Zero is never a meaningful threshold value here — the user always wants at least some headroom. A negative or zero config value should be a validation error.

If this breaks a test that uses 0.0 as a sentinel, that test is asserting an invalid configuration; either delete it or update it to use a small positive (e.g. 0.001) and a comment explaining the boundary.

Also add a one-line CONTEXT.md note (or short ADR addendum) explaining the gt=0 invariant.

## P2 — defer to followup TODOs (do NOT fix here)

- No flag distinguishing synthetic `0.0` (off-exchange feeder) from measured `0.0` (on-exchange trading exactly at NAV). Future decision-report display work could surface this with a "synthetic" annotation. Note in TODOS.md.
- `lru_cache` test isolation requires `cache_clear()` in fixtures. Already addressed in current tests per code-reviewer; mention in TODOS for future test authors.

## Verification commands

```bash
uv run pytest tests/data/test_akshare_client.py tests/scoring/test_qdii_premium.py tests/scoring/test_pipeline_qdii_premium.py tests/commands/test_memo_cmd.py tests/schemas/test_discovery.py -q
uv run ruff check src tests
```

Then re-invoke `/ship`.
