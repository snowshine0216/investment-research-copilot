Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct entry-point exercise (Skill(skill="verify") was tried first; its own
doctrine — "Don't import-and-call", "Don't run tests" — does not fit this change: the fix is a
pure-parse guard inside an LLM-response parser with no CLI/HTTP/GUI surface of its own, and the
only realistic end-to-end entry point (`irc monitor`) is explicitly forbidden here because it
hits real network + paid LLM APIs. No `.claude/skills/verifier-*` matches this surface. Per the
dispatch's explicit override, fell back to (b) a standalone script driving the real production
code path (`gather_macro_narrative` / `_parse_theme_claims`, unmodified, only the transport-edge
`call`/`resolve_route`/`_resolve_model` faked — same convention the module's own test file uses)
plus (a) CLI boot and (c) the mirror pytest file.)

Entry point exercised:
- `uv run irc --help`
- `uv run python /private/tmp/.../scratchpad/smoke_001.py` — standalone script (not the test
  file) importing `gather_macro_narrative`, `build_macro_pool`, `_parse_theme_claims`,
  `_MacroNarrErr`, `_MAX_SCHEMA_RETRIES` from `irc.monitor.narrative_macro` and exercising:
  Case A (fake `call` returns list-valued `attribution_strength` JSON on attempt 1, valid JSON
  on attempt 2), Case B (fake `call` always returns list-valued strength — exhaustion), plus
  direct pure-helper calls for AC1/AC2/AC3/AC6/AC7.
- `uv run pytest tests/monitor/test_narrative_macro.py -q`
- Static grep of `src/irc/monitor/narrative_macro.py` for the except-tuple (AC8) and of
  `CHANGELOG.md`/`VERSION` for the required Fixed entry / no-bump constraint.

Observed behavior:
- AC1 (list-valued strength, pure helper) — observed `_parse_theme_claims([...list...], (),
  hardened=False)` raised `_MacroNarrErr: schema_invalid: bad attribution_strength
  ['consistent_with']`; no `TypeError`.
- AC2 (dict-valued strength, pure helper) — observed same call with a dict strength raised
  `_MacroNarrErr: schema_invalid: bad attribution_strength {'value': 'consistent_with'}`; no
  `TypeError`.
- AC3 (non-str hashable regression pin) — observed `None` and `3` each still raise
  `_MacroNarrErr: schema_invalid: bad attribution_strength None` / `... 3`.
- AC4 (retry consumption end-to-end) — observed through `gather_macro_narrative`: attempt-1
  fake `call` returned list-valued strength, attempt-2 returned a valid payload;
  `result.doc.status == "ok"`, `len(result.doc.blocks) == 1`, block theme `us_monetary`,
  `claims[0].attribution_strength == "consistent_with"`, `calls["n"] == 2`,
  `len(result.cost_entries) == 2`. No exception escaped.
- AC5 (exhausted retries degrade, never raise) — observed through `gather_macro_narrative` with
  an always-bad fake `call`: returned (did not raise)
  `(result.doc.blocks, result.doc.status) == ((), "schema_invalid: bad attribution_strength
  ['consistent_with']")`; `calls["n"] == 3 == _MAX_SCHEMA_RETRIES + 1`;
  `len(result.cost_entries) == 3`.
- AC6 (hardened-attempt parity) — observed `_parse_theme_claims(..., hardened=True)` with a
  list-valued strength still raised `_MacroNarrErr: schema_invalid: bad attribution_strength
  ['consistent_with']` (not silently dropped).
- AC7 (valid path unchanged) — observed a valid `"consistent_with"` string produced a `Claim`
  with `attribution_strength == "consistent_with"`; `uv run pytest
  tests/monitor/test_narrative_macro.py -q` → `29 passed in 0.05s`.
- AC8 (no except-tuple widening, static) — observed
  `grep -n "except.*Error" src/irc/monitor/narrative_macro.py` → single hit:
  `except (json.JSONDecodeError, _MacroNarrErr) as exc:` (line 220); no `TypeError` anywhere in
  the file. `git diff main...HEAD -- src/irc/monitor/narrative_macro.py` shows exactly a
  1-line production change:
  `- if strength not in _VALID_STRENGTH:` / `+ if not isinstance(strength, str) or strength not
  in _VALID_STRENGTH:`.
- CLI still boots — observed `uv run irc --help` exit 0, full command list printed.
- Housekeeping constraints — observed `CHANGELOG.md` has a dated `### Fixed` entry under
  `[Unreleased]` describing this exact fix; no `VERSION` file diff on the branch
  (`git diff main...HEAD -- VERSION` empty); `narrative_macro.py` is 225 lines (unchanged from
  the spec's stated baseline — the fix widens one existing line, net 0 line delta).

Failures: none.
