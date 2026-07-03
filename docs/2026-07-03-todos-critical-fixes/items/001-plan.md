# Item 001 — `attribution_strength` Non-str Hardening: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A non-`str` `attribution_strength` from the macro-narrative LLM (list/dict — real output shapes) raises `_MacroNarrErr` inside `_parse_theme_claims` like every other schema violation, so it consumes the normal schema-retry budget in `gather_macro_narrative` instead of escaping as `TypeError` to the `monitor_cmd.py` blanket guard and degrading the whole 宏观面速览 block to `gather_error:`.

**Architecture:** One condition change in the pure helper `_parse_theme_claims` (`src/irc/monitor/narrative_macro.py:123`): prepend `not isinstance(strength, str)` to the existing `_VALID_STRENGTH` membership check, routing all non-str shapes to the existing `schema_invalid: bad attribution_strength {strength!r}` raise. No new functions, no signature changes, no exception-tuple changes.

**Tech Stack:** Python 3.12+, uv, pytest, ruff. All commands run from the repo root `/Users/snow/Documents/Repository/investment-research-copilot`.

## Global Constraints

- Branch is already `claude/todos-critical-fixes-001` (created by the orchestrator). Do NOT create branches, do NOT push, do NOT open a PR — the orchestrator ships.
- TDD mandatory: failing tests FIRST (they fail with `TypeError` today), then the minimal guard, then verification. Test file mirrors source: `src/irc/monitor/narrative_macro.py` → `tests/monitor/test_narrative_macro.py`.
- `_parse_theme_claims` stays PURE: no I/O, no mutation of `rows`; the fix is a validation branch only.
- Do NOT touch: `VERSION`, `_ENGINE_VERSION`, trace `schema_version`, `_VALID_STRENGTH` membership, `_MAX_SCHEMA_RETRIES`, the LLM prompt (`_build_macro_messages`), `src/irc/monitor/narrative.py` (production-dead twin — out of scope), and the gather-level `except (json.JSONDecodeError, _MacroNarrErr)` tuple (AC8: adding `TypeError` there would launder future coding bugs into silent retries).
- `src/irc/monitor/narrative_macro.py` is 225 lines today and must stay 225 lines (the guard modifies one line in place; zero growth).
- Ruff: line-length 100, target py312 — `uv run ruff check src tests` must stay clean.
- CHANGELOG: add a `### Fixed` subsection under `[Unreleased]`; NO version bump.
- TODOS.md: mark line 15 (`attribution_strength` unhashable shape) `[x]` with a `**Resolved 2026-07-03:**` annotation naming the fix + test names, matching the file's existing resolved-entry style.
- NEVER run `tests/commands/` as a whole directory (known suite-ordering hang) — per-file only.

---

### Task 1: F3 tests + isinstance guard in `_parse_theme_claims`

**Files:**
- Modify: `tests/monitor/test_narrative_macro.py` (append new F3 section at end of file, after the F2 section ending at line 328)
- Modify: `src/irc/monitor/narrative_macro.py:123` (one condition)

**Interfaces:**
- Consumes: existing test scaffolds in `tests/monitor/test_narrative_macro.py` — module-level `_fake_resp(text)` helper (line 100), the `monkeypatch.setattr(nm, "resolve_route", ...)` / `_resolve_model` pattern, `build_macro_pool` + `SearchHit` pool construction, `calls = {"n": 0}` counter convention. `Claim` fields are `claim` / `attribution_strength` / `citation_ids` (`src/irc/monitor/types.py:71-74`).
- Produces: hardened `_parse_theme_claims(rows, pool, *, hardened)` — unchanged signature; any non-`str` `attribution_strength` now raises `_MacroNarrErr("schema_invalid: bad attribution_strength {strength!r}")`. Task 2 depends on the test names defined here.

- [ ] **Step 1: Confirm you are on the implementation branch**

Run: `git branch --show-current`
Expected output: `claude/todos-critical-fixes-001`
If it prints anything else: STOP and report — do not create a branch yourself.

- [ ] **Step 2: Append the F3 test section (7 tests) to `tests/monitor/test_narrative_macro.py`**

Append the following verbatim at the very end of `tests/monitor/test_narrative_macro.py` (after `test_parse_theme_claims_rejects_bare_string_citation_ids`, currently the last test at line 328). Keep two blank lines before the section-header comment, matching the F1/F2 style:

```python
# ── F3: non-str attribution_strength hardening (todos-critical-fixes 001) ──────


def test_parse_theme_claims_rejects_list_valued_attribution_strength():
    """AC1: an unhashable list strength (real LLM output shape) must raise
    _MacroNarrErr like every other schema violation — never TypeError from
    the _VALID_STRENGTH set-membership hash test."""
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    rows = [{"claim": "央行本周维持利率不变，符合市场预期。",
             "attribution_strength": ["consistent_with"], "citation_ids": []}]
    with pytest.raises(_MacroNarrErr, match="schema_invalid: bad attribution_strength"):
        _parse_theme_claims(rows, (), hardened=False)


def test_parse_theme_claims_rejects_dict_valued_attribution_strength():
    """AC2: a dict-wrapped strength is also unhashable — same _MacroNarrErr path."""
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    rows = [{"claim": "央行本周维持利率不变，符合市场预期。",
             "attribution_strength": {"value": "consistent_with"}, "citation_ids": []}]
    with pytest.raises(_MacroNarrErr, match="schema_invalid: bad attribution_strength"):
        _parse_theme_claims(rows, (), hardened=False)


def test_parse_theme_claims_rejects_hashable_non_str_attribution_strength():
    """AC3 regression pin: hashable non-strs (None, int) already reach
    _MacroNarrErr today via failed set membership; the new isinstance guard
    must not change that."""
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    for bad in (None, 3):
        rows = [{"claim": "央行本周维持利率不变，符合市场预期。",
                 "attribution_strength": bad, "citation_ids": []}]
        with pytest.raises(_MacroNarrErr, match="schema_invalid: bad attribution_strength"):
            _parse_theme_claims(rows, (), hardened=False)


def test_parse_theme_claims_list_strength_raises_even_when_hardened():
    """AC6: the hardened attempt raises like any schema violation — only the
    CJK language guard has hardened-drop semantics."""
    from irc.monitor.narrative_macro import _parse_theme_claims, _MacroNarrErr

    rows = [{"claim": "央行本周维持利率不变，符合市场预期。",
             "attribution_strength": ["consistent_with"], "citation_ids": []}]
    with pytest.raises(_MacroNarrErr, match="schema_invalid: bad attribution_strength"):
        _parse_theme_claims(rows, (), hardened=True)


def test_gather_macro_narrative_list_strength_consumes_retry_then_ok(monkeypatch):
    """AC4 (+AC7 exact-str pin): a list-valued strength on attempt 1 consumes
    ONE schema retry; the valid attempt-2 payload then parses normally. No
    exception escapes gather_macro_narrative."""
    from irc.monitor.narrative_macro import gather_macro_narrative, build_macro_pool
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    cid = pool["us_monetary"][0].citation_id

    bad_body = {"us_monetary": [
        {"claim": "美联储本周维持利率不变，符合市场预期。",
         "attribution_strength": ["consistent_with"], "citation_ids": [cid]},
    ]}
    good_body = {"us_monetary": [
        {"claim": "美联储本周维持利率不变，符合市场预期。",
         "attribution_strength": "consistent_with", "citation_ids": [cid]},
    ]}

    calls = {"n": 0}

    def _call(task, messages, route, **kw):
        calls["n"] += 1
        return _fake_resp(_json.dumps(bad_body if calls["n"] == 1 else good_body))

    result = gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
    assert result.doc.status == "ok"
    assert len(result.doc.blocks) == 1
    assert result.doc.blocks[0].theme == "us_monetary"
    assert result.doc.blocks[0].claims[0].attribution_strength == "consistent_with"
    assert calls["n"] == 2
    assert len(result.cost_entries) == 2


def test_gather_macro_narrative_persistent_list_strength_degrades_after_full_budget(
    monkeypatch,
):
    """AC5: a persistently bad strength exhausts the WHOLE retry budget
    (_MAX_SCHEMA_RETRIES + 1 = 3 calls, 3 cost entries) then degrades via the
    normal (blocks=(), status=last_err) path — it never raises out of
    gather_macro_narrative, so the monitor_cmd gather_error guard is never
    the mechanism for this shape."""
    from irc.monitor.narrative_macro import (
        _MAX_SCHEMA_RETRIES, build_macro_pool, gather_macro_narrative,
    )
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    cid = pool["us_monetary"][0].citation_id

    bad_body = {"us_monetary": [
        {"claim": "美联储本周维持利率不变，符合市场预期。",
         "attribution_strength": ["consistent_with"], "citation_ids": [cid]},
    ]}

    calls = {"n": 0}

    def _call(task, messages, route, **kw):
        calls["n"] += 1
        return _fake_resp(_json.dumps(bad_body))

    result = gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
    assert result.doc.blocks == ()
    assert "bad attribution_strength" in result.doc.status
    assert calls["n"] == _MAX_SCHEMA_RETRIES + 1   # 3 today; pinned to the constant
    assert len(result.cost_entries) == _MAX_SCHEMA_RETRIES + 1


def test_gather_macro_narrative_does_not_launder_parse_type_errors(monkeypatch):
    """AC8 pin: the gather except tuple stays (json.JSONDecodeError,
    _MacroNarrErr). A coding-bug TypeError raised inside the parse block must
    propagate, NOT be consumed as a silent schema retry."""
    from irc.monitor.narrative_macro import gather_macro_narrative, build_macro_pool
    from irc.research.search.types import SearchHit
    import irc.monitor.narrative_macro as nm
    import json as _json

    monkeypatch.setattr(nm, "resolve_route", lambda task, route: type(
        "RR", (), {"provider": "testprovider"})())
    monkeypatch.setattr(nm, "_resolve_model", lambda rr: "test-model")

    def _boom(*a, **k):
        raise TypeError("coding bug")

    monkeypatch.setattr(nm, "_parse_theme_claims", _boom)

    hit = SearchHit(title="Fed holds", url="https://reuters.com/fed", snippet="x",
                    published_iso="2026-06-15", source_domain="reuters.com")
    pool = build_macro_pool({"us_monetary": (hit,)})
    cid = pool["us_monetary"][0].citation_id

    body = {"us_monetary": [
        {"claim": "美联储本周维持利率不变。", "attribution_strength": "consistent_with",
         "citation_ids": [cid]},
    ]}

    def _call(task, messages, route, **kw):
        return _fake_resp(_json.dumps(body))

    with pytest.raises(TypeError, match="coding bug"):
        gather_macro_narrative(theme_pool=pool, route=object(), call=_call)
```

- [ ] **Step 3: Run the F3 selection to verify RED**

Run: `uv run pytest tests/monitor/test_narrative_macro.py -q -k "attribution_strength or list_strength or launder"`

Expected: `5 failed, 2 passed, 22 deselected`
- FAILED (all with `TypeError` mentioning `unhashable type: 'list'` or `unhashable type: 'dict'`):
  `test_parse_theme_claims_rejects_list_valued_attribution_strength`,
  `test_parse_theme_claims_rejects_dict_valued_attribution_strength`,
  `test_parse_theme_claims_list_strength_raises_even_when_hardened`,
  `test_gather_macro_narrative_list_strength_consumes_retry_then_ok`,
  `test_gather_macro_narrative_persistent_list_strength_degrades_after_full_budget`
- PASSED (deliberate regression pins of today's behavior):
  `test_parse_theme_claims_rejects_hashable_non_str_attribution_strength` (AC3),
  `test_gather_macro_narrative_does_not_launder_parse_type_errors` (AC8)

If the failure counts differ, STOP: the two pins passing and the five TypeError failures ARE the red state this plan requires.

- [ ] **Step 4: Implement the guard (GREEN — minimal change)**

In `src/irc/monitor/narrative_macro.py`, change exactly one line inside `_parse_theme_claims` (line 123).

Old (lines 122–124 for context; edit only the middle line):

```python
        strength = r.get("attribution_strength")
        if strength not in _VALID_STRENGTH:
            raise _MacroNarrErr(f"schema_invalid: bad attribution_strength {strength!r}")
```

New:

```python
        strength = r.get("attribution_strength")
        if not isinstance(strength, str) or strength not in _VALID_STRENGTH:
            raise _MacroNarrErr(f"schema_invalid: bad attribution_strength {strength!r}")
```

Rationale (do not deviate): `not isinstance(strength, str)` short-circuits BEFORE the set-membership hash test, so unhashable shapes never reach it; valid `str` values take the identical path as before; the raise (message included) is reused verbatim. Do NOT add a separate raise with a different message, do NOT coerce/unwrap list values, do NOT touch any other check.

- [ ] **Step 5: Re-run the F3 selection to verify GREEN**

Run: `uv run pytest tests/monitor/test_narrative_macro.py -q -k "attribution_strength or list_strength or launder"`
Expected: `7 passed, 22 deselected`

- [ ] **Step 6: Run the full mirror test file (AC7 — valid path unchanged)**

Run: `uv run pytest tests/monitor/test_narrative_macro.py -q`
Expected: `29 passed` (22 pre-existing + 7 new; zero failures)

- [ ] **Step 7: Verify zero file growth and the untouched except tuple (AC8 static check)**

Run: `wc -l src/irc/monitor/narrative_macro.py`
Expected output: `     225 src/irc/monitor/narrative_macro.py`

Run: `grep -c "except (json.JSONDecodeError, _MacroNarrErr)" src/irc/monitor/narrative_macro.py && grep -c "except TypeError" src/irc/monitor/narrative_macro.py; true`
Expected output: `1` then `0` (grep -c prints 0 and exits non-zero for the second pattern — that is the pass condition).

- [ ] **Step 8: Lint**

Run: `uv run ruff check src tests`
Expected output: `All checks passed!`

- [ ] **Step 9: Cross-file verification sweep (per-file — NEVER the whole `tests/commands/` dir, it hangs)**

These five files also import/exercise `narrative_macro` or `gather_macro_narrative`. No signature changed, so all must pass unmodified. Run each separately:

```bash
uv run pytest tests/monitor/test_render_html.py -q
uv run pytest tests/monitor/test_acceptance_eval.py -q
uv run pytest tests/commands/test_monitor_cmd.py -q
uv run pytest tests/commands/test_monitor_cmd_eval_wiring.py -q
uv run pytest tests/commands/test_monitor_cmd_trace.py -q
```

Expected: every command ends `N passed` with 0 failed (N varies per file). Any failure: STOP and re-check Step 4 — you must not have touched anything beyond the single condition.

- [ ] **Step 10: Commit the test + implementation**

```bash
git add tests/monitor/test_narrative_macro.py src/irc/monitor/narrative_macro.py
git commit -m "fix(monitor): non-str attribution_strength raises _MacroNarrErr, consuming the macro schema-retry budget"
```

Expected: commit created on `claude/todos-critical-fixes-001` with exactly those 2 files. Do NOT push.

---

### Task 2: CHANGELOG + TODOS.md bookkeeping

**Files:**
- Modify: `CHANGELOG.md` (insert a `### Fixed` subsection directly under `## [Unreleased]`, line 8)
- Modify: `TODOS.md:15` (mark resolved)

**Interfaces:**
- Consumes: the test names defined in Task 1 Step 2 (cited verbatim in the TODOS annotation).
- Produces: documentation only — no code.

- [ ] **Step 1: Add the CHANGELOG entry**

In `CHANGELOG.md`, replace this exact text (top of the file body, lines 8–10):

```markdown
## [Unreleased]

### Changed — constituent/macro news factor normalized by Σweight; `_ENGINE_VERSION` 3 → 4 (2026-07-03)
```

with:

```markdown
## [Unreleased]

### Fixed — macro narrative: non-str `attribution_strength` consumes the schema-retry budget instead of degrading the whole block (2026-07-03)

- **`_parse_theme_claims` (`src/irc/monitor/narrative_macro.py`) now type-guards
  `attribution_strength` before the `_VALID_STRENGTH` set-membership test.** An
  unhashable LLM value (e.g. `["consistent_with"]` — a real output shape) previously
  raised `TypeError`, escaping `gather_macro_narrative`'s
  `(json.JSONDecodeError, _MacroNarrErr)` retry loop into the `monitor_cmd.py` blanket
  guard: the WHOLE 宏观面速览 block degraded to `gather_error:` with the retry budget
  skipped. Any non-`str` value now raises the existing
  `schema_invalid: bad attribution_strength ...` `_MacroNarrErr`, consuming a normal
  schema retry and, only on exhaustion, degrading via the standard
  `(blocks=(), status=last_err)` path. The gather `except` tuple is deliberately
  unchanged (catching `TypeError` there would launder future coding bugs into silent
  retries). No `_ENGINE_VERSION` or trace `schema_version` change. No VERSION bump.

### Changed — constituent/macro news factor normalized by Σweight; `_ENGINE_VERSION` 3 → 4 (2026-07-03)
```

- [ ] **Step 2: Mark the TODOS.md item resolved**

In `TODOS.md`, replace the exact line 15:

```markdown
- [ ] **`attribution_strength` unhashable shape skips macro retry budget** — if the macro LLM emits a non-hashable `attribution_strength` (e.g. a list), the `strength not in _VALID_STRENGTH` check (`narrative_macro.py:120`) raises TypeError, escaping the inner schema-retry loop; the call-site guard degrades the WHOLE macro block (honest absence, logged) instead of retrying/dropping that one theme. No crash/data loss. One-line isinstance hardening. (report-v3-001 ship adversarial review 2026-07-02, P2)
```

with (single line — same text, `[x]`, resolution appended):

```markdown
- [x] **`attribution_strength` unhashable shape skips macro retry budget** — if the macro LLM emits a non-hashable `attribution_strength` (e.g. a list), the `strength not in _VALID_STRENGTH` check (`narrative_macro.py:120`) raises TypeError, escaping the inner schema-retry loop; the call-site guard degrades the WHOLE macro block (honest absence, logged) instead of retrying/dropping that one theme. No crash/data loss. One-line isinstance hardening. (report-v3-001 ship adversarial review 2026-07-02, P2) **Resolved 2026-07-03:** `_parse_theme_claims` now requires `isinstance(strength, str)` before the `_VALID_STRENGTH` membership test, so any non-str shape (list/dict/None/int) raises the existing `schema_invalid: bad attribution_strength ...` `_MacroNarrErr` — consumed by the normal schema-retry loop (retry, then degrade to `(blocks=(), status=last_err)` on exhaustion); the gather-level `except` tuple deliberately unchanged (no `TypeError` laundering). Tests `test_parse_theme_claims_rejects_list_valued_attribution_strength` / `_rejects_dict_valued_attribution_strength` / `_rejects_hashable_non_str_attribution_strength` / `_list_strength_raises_even_when_hardened` + `test_gather_macro_narrative_list_strength_consumes_retry_then_ok` / `_persistent_list_strength_degrades_after_full_budget` / `_does_not_launder_parse_type_errors`.
```

- [ ] **Step 3: Verify the doc edits landed where expected**

Run: `grep -n "Resolved 2026-07-03" TODOS.md`
Expected: 2 matches — line 15 (this item) and line 70 (the pre-existing venue-filtering entry).

Run: `grep -n "bad attribution_strength" CHANGELOG.md`
Expected: at least 1 match inside the new `### Fixed` block under `[Unreleased]`.

Run: `git diff --stat`
Expected: exactly `CHANGELOG.md` and `TODOS.md` modified (VERSION untouched).

- [ ] **Step 4: Final sanity re-run (tests + lint unchanged by docs)**

Run: `uv run pytest tests/monitor/test_narrative_macro.py -q`
Expected: `29 passed`

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 5: Commit the bookkeeping**

```bash
git add CHANGELOG.md TODOS.md
git commit -m "docs(monitor): CHANGELOG + TODOS resolved entry for attribution_strength hardening"
```

Expected: commit created with exactly those 2 files. Do NOT push, do NOT open a PR — the orchestrator ships.

---

## Acceptance-criteria → step map (self-review record)

| Spec AC | Where satisfied |
| --- | --- |
| AC1 list, pure helper | Task 1 Step 2 `test_parse_theme_claims_rejects_list_valued_attribution_strength`; red Step 3, green Step 5 |
| AC2 dict, pure helper | Task 1 Step 2 `test_parse_theme_claims_rejects_dict_valued_attribution_strength` |
| AC3 hashable non-str pin | Task 1 Step 2 `test_parse_theme_claims_rejects_hashable_non_str_attribution_strength` (passes at red — deliberate pin) |
| AC4 retry consumption e2e | Task 1 Step 2 `test_gather_macro_narrative_list_strength_consumes_retry_then_ok` (status ok, 1 block, 2 calls, 2 cost entries) |
| AC5 exhausted retries degrade | Task 1 Step 2 `test_gather_macro_narrative_persistent_list_strength_degrades_after_full_budget` (counts pinned to `_MAX_SCHEMA_RETRIES + 1`) |
| AC6 hardened parity | Task 1 Step 2 `test_parse_theme_claims_list_strength_raises_even_when_hardened` |
| AC7 valid path unchanged | Task 1 Step 6 full-file run (29 passed) + exact-str assertion in the AC4 test |
| AC8 except tuple untouched | Task 1 Step 2 `test_gather_macro_narrative_does_not_launder_parse_type_errors` (behavioral pin) + Step 7 grep (static) |
| CHANGELOG Fixed line, no VERSION bump | Task 2 Steps 1, 3 |
| TODOS.md line 15 resolved | Task 2 Steps 2, 3 |
| Size budget / purity | Task 1 Steps 4 (validation branch only), 7 (`wc -l` = 225) |
