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
   documented in `impact_validate.py` ~~and used for `last_err` classification~~ —
   corrected by grill: nothing machine-parses the prefix today (the only status consumer
   logic is `doc.status != "ok"` at `render_html.py:402`; `trace.py:_macro_narrative` and
   `monitor_cmd._narrative_dump` serialize the status verbatim) — the prefix is a
   human-readable convention kept for consistency, not a consumed contract. AC1/AC5 pin
   only the substring, not the full repr, to avoid over-constraining.
5. **Also fix `narrative.py`?** → No; out of scope (see Non-goals). Verified
   production-dead by grepping importers: only tests reference it.
6. **"Drop that one theme" vs. "consume a retry" — which does the loop actually do?** →
   Consume a whole-attempt retry: schema violations abort the attempt's parse and re-call
   the LLM; there is no per-theme drop for schema errors (per-claim drop exists only for
   the hardened language guard). The spec follows the as-built retry semantics — the
   invocation's "drop that one theme" phrasing maps to the exhausted-retry degradation,
   not a new per-theme mechanism.

## Resolved decisions

Grill session 2026-07-03 (autonomous, grill-with-docs; recommendations auto-accepted).
Every claim below was verified against the working tree on
`autodev/todos-critical-fixes-feature`.

- Q: Does the `schema_invalid:` message-prefix convention actually exist in this module,
  and does the spec's proposed error message match it?
  A: Yes. `narrative_macro.py:124` already emits
  `schema_invalid: bad attribution_strength {strength!r}`; the guard only routes non-`str`
  values to that same raise (identical message). The prefix family
  (`schema_invalid|unresolved_citation|empty_pool`) is documented in
  `impact_validate.py:8`, and `narrative_macro` imitates it (`banned_verb:`,
  `language_guard:`, `provider_error:` follow the same shape).
  Rationale: reusing the existing raise keeps the fix to a pure validation-branch widening.
  Doc impact: none.
- Q: The spec claimed the prefix is "used for `last_err` classification" — true?
  A: No — overstated; clause struck. Nothing machine-parses status prefixes: the sole
  status-consuming branch is `doc.status != "ok"` (`render_html.py:402`, degrades to `""`);
  `trace.py:176 _macro_narrative` and `monitor_cmd._narrative_dump` (line ~435) serialize
  the status verbatim; no `startswith`/prefix match exists in `src/` or `evals/`.
  Rationale: keep the spec honest — the prefix is convention, not a consumed contract.
  Doc impact: none (spec strike-through only).
- Q: Does AC5's "exactly `_MAX_SCHEMA_RETRIES + 1` (= 3) call invocations" match the
  actual retry budget?
  A: Yes. `_MAX_SCHEMA_RETRIES = 2` (`narrative_macro.py:20`); the loop is
  `range(_MAX_SCHEMA_RETRIES + 1)` (line 193) → 3 attempts, one `CostEntry` appended per
  successful `call` before parsing → AC4's 2-entries and AC5's 3-entries counts are exact.
  Rationale: pin the counts to the constant, not a literal, so a future budget change
  doesn't silently invalidate the ACs.
  Doc impact: none.
- Q: Can the new degraded status string (`schema_invalid: bad attribution_strength [...]`)
  break the eval layer or any other consumer?
  A: No. `metrics_narrative.py` consumes theme-keyed claim dicts, never status strings
  (and copies `_BANNED_VERBS` verbatim rather than importing `narrative.py`);
  `eval/trace.py` stores `doc.status` additively; render degrades any non-`"ok"` status
  to an omitted section. The status value is new only in *when* it appears (schema-exhaust
  path instead of `gather_error:`), and both were already free-form strings.
  Rationale: verified by grep — no prefix parsing anywhere downstream.
  Doc impact: none.
- Q: Does the non-goal "narrative.py:40 is production-dead" hold?
  A: Yes. Importers of `irc.monitor.narrative` are only
  `tests/monitor/test_narrative.py` and
  `tests/commands/test_monitor_cmd_theme_consolidation.py:150` (both tests);
  `monitor_cmd.py` imports `narrative_macro` only; `evals/monitor_narrative/runner.py`
  imports `metrics_narrative`, which does NOT import `narrative.py`.
  Rationale: non-goal stands; deletion/hardening of the twin stays with the orchestrator.
  Doc impact: none.
- Q: Hardened-attempt semantics — does the spec's "raise, don't drop" (AC6) match the code?
  A: Yes. Only the language guard has hardened-`continue` semantics
  (`narrative_macro.py:137-140`); the strength check (line 123) precedes it and is
  hardened-agnostic, as are all other schema checks.
  Rationale: AC6 pins existing asymmetry, no new mechanism.
  Doc impact: none.
- Q: Is the cited blanket guard (`monitor_cmd.py:1008-1013`) accurate?
  A: Yes — `except Exception → gather_error: {exc}` at exactly those lines; a `TypeError`
  escaping `gather_macro_narrative` lands there today, confirming the failure narrative.
  Doc impact: none.
- Q: Do the test-scaffold conventions the ACs reference exist?
  A: Yes — `_fake_resp` (test file line 100), `calls = {"n": 0}` counter (line 205),
  section headers `# ── F1 ──` (line 247) / `# ── F2 ──` (line 316) in
  `tests/monitor/test_narrative_macro.py`; the new section is `F3`.
  Doc impact: none.
- Q: Does CHANGELOG have an `[Unreleased]` section for the required `Fixed` line?
  A: Yes — `[Unreleased]` with dated `### Changed` / `### Added` subsections; the item
  adds a `### Fixed` entry there. No VERSION bump (project convention).
  Doc impact: none.
- Q: CONTEXT.md marks 宏观面速览 (the very block this spec hardens) "not yet built" —
  contradiction?
  A: Stale glossary, synced. Report v3 shipped to main 2026-07-03 (squash `221a34e4`
  lineage; readability merge `b04bc6d1`): `narrative_macro.py`, `render_overview.py`
  (今日速览), `source_tiers.py`, ADR 0022, and the ADR 0017 report-v3 addendum all exist.
  Updated the four report-v3 "not yet built" annotations, "(ADR 0022 when written.)",
  "(ADR 0017 addendum when built)", and the dual-track "**not yet built**" flag (built
  2026-06-21, `_dual_track.py` wired via `holding_metrics` → `monitor_cmd`).
  Rationale: the plan phase reads spec + glossary together; a glossary that denies the
  target code exists is a real hazard.
  Doc impact: CONTEXT.md (annotation sync only, no term changes).
- Q: Does the same unhashable-crash class exist in the sibling impacts leg?
  A: Yes, latent: `impact_validate.py:33` (`tuple(r.get("citation_ids", ()))`) raises
  `TypeError` on a non-iterable value (and `extract_json(...).get("impacts", [])` at
  `impacts.py:80` raises `AttributeError` on a list-shaped top level), both escaping
  `except (json.JSONDecodeError, ImpactValidationError)` at `impacts.py:83`. OUT of
  item-001 scope (different module, per-fund guard topology differs) — recorded here for
  the orchestrator, same treatment as the `narrative.py:40` non-goal.
  Doc impact: none.
- Q: Does this fix warrant an ADR?
  A: No — fails all three of the three-of-three rule: trivially reversible (one guard
  line), unsurprising (uniform "reject non-str like any schema violation"), and the only
  real alternative (widening the gather `except` tuple to `TypeError`) is rejected and
  recorded as AC8 inside the spec itself.
  Doc impact: none.
