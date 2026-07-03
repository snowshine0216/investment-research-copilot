# Item 001 — `attribution_strength` non-str hardening (narrative_macro)

Run: todos-critical-fixes · Date: 2026-07-03 · Source: TODOS.md line 15 via MASTER-SPEC §IN/001
Target: `src/irc/monitor/narrative_macro.py` (`_parse_theme_claims`, line ~123)
Tests: `tests/monitor/test_narrative_macro.py`

## Goal

`_VALID_STRENGTH` is a `set`, so the membership check `strength not in _VALID_STRENGTH`
in `_parse_theme_claims` hash-tests the LLM-supplied `attribution_strength` value; an
unhashable value (e.g. a list — a real LLM output shape) raises `TypeError`, which is not
in the retry loop's `except (json.JSONDecodeError, _MacroNarrErr)` tuple in
`gather_macro_narrative` and therefore escapes to the call-site blanket guard at
`src/irc/commands/monitor_cmd.py:1008-1013`, degrading the WHOLE 宏观面速览 macro block to
`gather_error: ...` — one malformed row costs every theme and skips the retry budget
entirely. This item makes any non-`str` `attribution_strength` behave exactly like every
other schema violation in this module: raise `_MacroNarrErr` (message keeping the
`schema_invalid:` prefix convention), which the existing loop consumes as a retry attempt
and, only on genuine exhaustion, degrades the doc through the normal
`(blocks=(), status=last_err)` path. The spec pins observable behavior, not the
implementation; the expected shape is a small `isinstance` guard in the pure helper.

## Acceptance criteria

Each criterion is independently verifiable with a unit test in
`tests/monitor/test_narrative_macro.py` (conventions: pure-helper tests via
`pytest.raises(_MacroNarrErr, match=...)`; gather-level tests via monkeypatched
`resolve_route`/`_resolve_model`, a fake `call` returning `_fake_resp(json.dumps(body))`,
and a `calls = {"n": 0}` counter — mirror the existing F1/F2 sections).

- **AC1 — list-valued strength, pure helper.**
  `_parse_theme_claims([{"claim": "<valid 中文 claim>", "attribution_strength":
  ["consistent_with"], "citation_ids": []}], (), hardened=False)` raises `_MacroNarrErr`
  with a message containing `bad attribution_strength` (and carrying the `schema_invalid:`
  prefix). It must NOT raise `TypeError`.
- **AC2 — dict-valued strength, pure helper.** Same call shape with
  `"attribution_strength": {"value": "consistent_with"}` also raises `_MacroNarrErr`,
  not `TypeError`.
- **AC3 — non-str hashable regression pin.** `attribution_strength` of `None` and of `3`
  each still raise `_MacroNarrErr` (this already works today; pin it so the new guard
  cannot regress it).
- **AC4 — retry consumption end-to-end.** Through `gather_macro_narrative`: a list-valued
  `attribution_strength` in the attempt-1 response, followed by a fully valid attempt-2
  response (Chinese claim, `"consistent_with"`, resolvable citation id from the built
  pool), yields `result.doc.status == "ok"`, one `MacroThemeBlock` parsed from the
  attempt-2 payload, exactly 2 `call` invocations, exactly 2 cost entries, and no
  exception propagates out of `gather_macro_narrative`.
- **AC5 — exhausted retries degrade, never raise.** Through `gather_macro_narrative`:
  a persistently list-valued `attribution_strength` on every attempt returns (does not
  raise) `result.doc.blocks == ()` with `result.doc.status` containing
  `bad attribution_strength`, after exactly `_MAX_SCHEMA_RETRIES + 1` (= 3) `call`
  invocations and 3 cost entries. This is the existing exhausted-retry degradation path,
  unchanged — the call-site `gather_error:` guard in `monitor_cmd.py` is never the
  mechanism for this shape.
- **AC6 — hardened-attempt parity with other schema violations.**
  `_parse_theme_claims(..., hardened=True)` with a list-valued strength raises
  `_MacroNarrErr` (it is NOT silently dropped the way the language guard drops claims on
  the hardened attempt — only the CJK guard has hardened-drop semantics).
- **AC7 — valid path unchanged.** All existing tests in
  `tests/monitor/test_narrative_macro.py` still pass; a valid `str` strength in
  `_VALID_STRENGTH` still produces a `Claim` whose `strength` is that exact string.
- **AC8 — no behavior change outside `_parse_theme_claims`.** The gather-level `except`
  tuple stays `(json.JSONDecodeError, _MacroNarrErr)` — `TypeError` is NOT added to it
  (a broad catch would launder future coding bugs into silent schema retries).

## Non-goals

- Changing macro-block degradation semantics for genuinely exhausted retries (the
  `(blocks=(), status=last_err)` path and the `monitor_cmd.py` blanket `gather_error:`
  guard both stay as-is).
- Changing the LLM prompt, the JSON schema asked of the model, `_VALID_STRENGTH`
  membership, or the hardened-retry ladder (`_MAX_SCHEMA_RETRIES`, hardened-on-last-only).
- Fixing the identical latent pattern in `src/irc/monitor/narrative.py:40`
  (`_parse_claims`) — that module has no production importers since report v3 replaced
  the per-fund narrative calls (`monitor_cmd.py` imports only `narrative_macro`); it is a
  candidate for deletion or the same one-line hardening in a separate cleanup, recorded
  here for the orchestrator, out of item 001 scope per MASTER-SPEC.
- Coercion or best-effort salvage of non-str strengths (e.g. unwrapping
  `["consistent_with"]` to its element): schema violations are rejected, not repaired,
  consistent with every other check in `_parse_theme_claims`.
- Splitting `narrative_macro.py` (already 225 lines) — the fix adds ~2 lines; module
  decomposition is unrelated refactoring.

## Constraints

- **TDD**: failing tests first (today they fail with `TypeError`), then the minimal
  guard, then refactor. Tests mirror source: `narrative_macro.py` →
  `tests/monitor/test_narrative_macro.py`; follow the existing section-header comment
  convention (`# ── F3: ... ──`).
- **Purity**: `_parse_theme_claims` stays pure — no I/O, no mutation of `rows`; the fix
  must be expressible as a validation branch, not a state change.
- **Size budget**: file < 200 lines is the ideal; the file already exceeds it at 225 —
  do not grow it beyond the ~2-line guard; functions < 20 lines ideal.
- **No VERSION bump**; add a `Fixed` line under CHANGELOG `[Unreleased]`.
- No trace `schema_version` change and no `_ENGINE_VERSION` change — this touches
  narrative parsing only, not factor math or trace shape.
- No signature changes are expected; if any occur, grep callers in `tests/` and run every
  test dir that exercises them (`tests/commands/` per-file — whole-dir hangs).

## Open questions resolved during brainstorming

1. **Guard any non-str, or only unhashables?** → Any non-str. Only unhashables crash
   today (hashable non-strs like `None`/`3` already reach `_MacroNarrErr`), but all valid
   values are `str`, so `isinstance(strength, str)` covers the crash class with zero
   valid-path change and pins one uniform rule; AC3 keeps the hashable case honest.
2. **Guard placement — pure helper vs. widening the gather-level `except`?** → Pure
   helper (`_parse_theme_claims`). Adding `TypeError` to the `except` tuple is a 1-line
   alternative but over-broad: any future coding-bug `TypeError` inside the parse block
   (e.g. in block assembly) would be silently converted into schema retries. Locked as AC8.
3. **Hardened-attempt behavior: raise or drop the claim?** → Raise. The task pin is
   "exactly like other schema violations"; a bad strength *string* (e.g. `"foo"`) raises
   on the hardened attempt too. Only the language guard deliberately has hardened-drop
   semantics. Locked as AC6.
4. **Error message format?** → Reuse the existing
   `schema_invalid: bad attribution_strength {strength!r}` format — `!r` renders lists
   and dicts fine, and the `schema_invalid:` prefix matches the typed-message convention
   documented in `impact_validate.py` and used for `last_err` classification. AC1/AC5 pin
   only the substring, not the full repr, to avoid over-constraining.
5. **Also fix `narrative.py`?** → No; out of scope (see Non-goals). Verified
   production-dead by grepping importers: only tests reference it.
6. **"Drop that one theme" vs. "consume a retry" — which does the loop actually do?** →
   Consume a whole-attempt retry: schema violations abort the attempt's parse and re-call
   the LLM; there is no per-theme drop for schema errors (per-claim drop exists only for
   the hardened language guard). The spec follows the as-built retry semantics — the
   invocation's "drop that one theme" phrasing maps to the exhausted-retry degradation,
   not a new per-theme mechanism.
