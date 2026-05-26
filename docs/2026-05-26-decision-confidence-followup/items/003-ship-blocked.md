# Ship blocked — item 003 (round 1)

Source: `/ship` steps 8 (code-reviewer + silent-failure-hunter) + 9 (adversarial — verdict CLEAN). Fix before re-invoking `/ship`.

## P0 — must fix before landing

### P0-1 · Silent exception swallow in `read_live_decision_inputs`

File: `src/irc/decision/live_inputs.py:68` (bare `except Exception: pass`)

The outer try-block at line 43 wraps both the `macro_series` query and the entire `nav_history` loop. The current except clause is `except Exception: pass` — no log, no print, no reraise. If `macro_series` table is absent, DuckDB schema mismatches, or a column type coerces unexpectedly, the function returns `({}, {})` with no signal to the operator. Every memo trigger then renders `⚠` with no diagnostic.

The connect-failure path at line 31 already emits `print("WARNING: ...", file=sys.stderr)`. Apply the same pattern at line 68:

```python
except Exception as exc:   # was: bare "except Exception: pass"
    print(
        f"WARNING: live_inputs query failed ({exc.__class__.__name__}: {exc}); "
        "macro snapshot and weekly returns will be empty — all triggers show ⚠.",
        file=sys.stderr,
    )
```

(Add `import sys` to the module's imports if it's not already there.)

Add a test in `tests/decision/test_live_inputs.py`:

```python
def test_read_live_decision_inputs_logs_on_query_failure(tmp_path, capsys, monkeypatch):
    """P0-1 fix: catastrophic query failures emit a WARNING, not silent empty dicts."""
    # Set up a DB whose macro_series table is intentionally missing/corrupted,
    # OR monkeypatch the cursor to raise mid-query.
    # Assert capsys.readouterr().err contains "WARNING: live_inputs query failed"
    # AND that the returned tuple is ({}, {}).
```
Adjust to whatever pattern the existing `test_live_inputs.py` uses for DB-missing cases.

## P1 — should fix in this PR

### P1-1 · `or 0.0` corrupts explicit zero / integer threshold

File: `src/irc/memo/picks_table.py:135`

```python
threshold=float(trig.get("threshold") or 0.0),
```

`trig.get("threshold")` returning integer `0` (a valid threshold like `weekly_return > 0`) is falsy → `or 0.0` fires and substitutes. Coincidentally no observable bug TODAY (current thresholds are all non-zero floats), but pattern is latent.

**Fix:** Replace with explicit None check:

```python
_raw_threshold = trig.get("threshold")
threshold=float(0.0 if _raw_threshold is None else _raw_threshold),
```

OR inline:

```python
threshold=float(trig["threshold"]) if trig.get("threshold") is not None else 0.0,
```

Add a unit test:

```python
def test_format_trigger_status_compact_handles_zero_threshold(...):
    """P1-1 fix: integer/explicit 0 thresholds are preserved (not silently substituted)."""
```

### P1-2 · Silent NAV `< 5` skip in `read_live_decision_inputs`

File: `src/irc/decision/live_inputs.py:62-63`

When `len(navs) < 5`, the instrument is silently omitted from `returns`. User sees `⚠` glyph but has no path to debug.

**Fix:** Emit a DEBUG-level log when `DEBUG` env var is set (the project's existing debug pattern):

```python
if len(navs) < 5:
    if os.environ.get("DEBUG"):
        print(
            f"DEBUG: {iid} has {len(navs)} NAV rows (<5 threshold); skipping weekly return.",
            file=sys.stderr,
        )
    continue
```

Add `import os` to the module if not already present. No test required for the DEBUG branch since it's optional diagnostic plumbing (matches the project's `DEBUG=true` pattern from CLAUDE.md).

## P2 — defer to TODOs (do NOT fix here)

- Pipe-injection in trigger `name` (and other table cells) — pre-existing, not a regression from this PR. The adversarial review noted it as latent but explicitly out of scope here.
- `field.startswith("macro.")` case-sensitivity in `sizing.py:149` — pre-existing in the extracted helper; tolerable since YAML is human-authored and `irc config validate` could catch this elsewhere. Add to TODOs if not already there.
- The fragile `cells[-3]/[-2]` test isolation pattern in `test_picks_table_new_columns_carry_no_citation_markers` — pre-existing test design choice; works for the current 12-column layout.

## Verification

```bash
uv run pytest tests/decision/test_live_inputs.py tests/memo/test_picks_table.py tests/memo/test_trigger_status_compact.py -q
uv run ruff check src tests
```

Then re-invoke `/ship`.
