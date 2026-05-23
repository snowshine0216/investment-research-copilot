# Item 007 inline review verdict (from `/ship` steps 8+9)

**Verdict:** PASS-WITH-NITS (after fix commit)
**Captured by:** `/ship` workflow steps 8 + 9 — pre-landing review (two parallel subagents) + adversarial review (one subagent)
**Date:** 2026-05-23
**Branch:** `autodev/thesis-evidence-007-memo-and-discipline-renderers`
**Base:** `autodev/thesis-cards-evidence-gap`

## Subagents dispatched

1. `pr-review-toolkit:code-reviewer` (Sonnet) — general code-quality pass
2. `pr-review-toolkit:silent-failure-hunter` (Sonnet) — exception swallowing + fallback misuse
3. `general-purpose` adversarial (Sonnet) — race conditions, edge inputs, failure modes, SAME-3 invariant attempts, marker grammar abuse, appendix regex shapes, cycle-fix shim limitations

## Findings — closed before opening PR

### P0 — silent YAML-parse swallow (closed in fix commit)

**File:** `src/irc/commands/opportunity_cmd.py:1054`
**Surfaced by:** silent-failure-hunter (P0) + code-reviewer (P1).
**Issue:** `except (OSError, Exception)` is equivalent to bare `except Exception` (Exception is a supertype of OSError). It silently swallowed `yaml.YAMLError` AND any future `KeyError` / `TypeError` raised inside the comprehension over `doc.get("trades")`. Result: a corrupted `trade_plan.yaml` would silently default to empty `pick_order_iids`, causing the discipline appendix to render in fallback instrument-id order with no warning to the user.
**Fix:** Narrowed to `except (OSError, yaml.YAMLError)`. Non-IO exceptions now propagate.
**Regression test:** `tests/commands/test_opportunity_cmd.py::test_load_pick_order_iids_propagates_non_yaml_exceptions` (passes `trades:\n  - just_a_string\n` to trigger an AttributeError that the old `except` would have swallowed). Plus the complementary `test_load_pick_order_iids_tolerates_malformed_yaml` to lock the still-tolerated parse-failure path.

### P1 — `_APPENDIX_LINE_RE` silently rejected real CN fund names with parens (closed in fix commit)

**File:** `src/irc/opportunity/report.py:230`
**Surfaced by:** adversarial reviewer (P1, called out as the blocking issue).
**Issue:** The plan's "Locked appendix line regex contract" specified `[^()\n]+?` for the `nm` capture group. Real Chinese fund names routinely embed parentheses (`大成纳斯达克100ETF联接(QDII)A`, `易方达标普信息科技指数(QDII-LOF)A`, `广发道琼斯石油指数(QDII-LOF)人民币E`). The regex silently returned `None` for every such line, so item 009's `find_uncited_discipline_rows` (which inherits this regex contract) would have under-counted coverage with no warning.
**Fix:** Relaxed `nm` to `[^\n]+?` (the plan's textual description was "NM = greedy non-newline" — the impl was stricter than the documented intent). The trailing literal ` \(权重 ` keeps the non-greedy match unambiguous (fund names do not contain the substring `(权重`).
**Regression test:** `tests/opportunity/test_report_appendix.py::test_appendix_line_re_accepts_parens_in_cn_fund_names` with four realistic samples spanning all four non-defensive shapes (Shape 1, Shape 4 with refs, Shape 2 failure-only `❌`, Shape 3 audit-error `⚠️`).

### P1 — `ThesisEvidence.from_dict` mismatch guard truthiness bug (closed in fix commit)

**File:** `src/irc/fundamentals/types.py` (the OQ1 classmethod added by Task 1).
**Surfaced by:** silent-failure-hunter.
**Issue:** `if expected_id and expected_id != ev.citation_id` is falsy for `expected_id == ""` (and for `None`). The first case was an unreachable claim — an older pipeline version writing `citation_id=""` to JSON would silently bypass the integrity check.
**Fix:** Tightened to `if expected_id is not None and ...`. Empty string now triggers the mismatch raise.
**Regression tests:** `test_thesis_evidence_from_dict_empty_string_citation_id_raises` (explicit empty → raises) + `test_thesis_evidence_from_dict_no_citation_id_key_does_not_raise` (key absent → silent reconstruction is intended).

## Findings — deferred (P2 / Notes / design choices)

These were noted but not blocking:

- **Adversarial F2 (P2)** — `format_combined_marker('abcdef1234567890', 'ABC]D')` produces `[stock:ABC]D]` which parses partially. Theoretical: `constituent_key` is populated from AkShare symbols which never contain `]`. Defer.
- **Adversarial F3 (P2)** — NaN `weight_pct` would render as `(权重 nan%)` and fail the regex. `ConstituentAnalysis` has no `__post_init__` validation. Theoretical: snapshot construction never emits NaN. Defer (covered by a `math.isfinite` filter that lives in item 005's deferred-hygiene list).
- **Adversarial F4 (P2)** — `_load_pick_order_iids` race with mid-flight `trade_plan.yaml` write. Mitigation: `plan.py` already uses atomic-write (`.tmp.pid → os.replace`). Window is the `os.replace` instant; production runs serial pipelines, not concurrent. Defer.
- **Adversarial F5 (Note)** — cycle-fix shim only re-exports `select_citations`. Future symbol additions to `irc.opportunity.citation_selector` won't appear in the memo shim. Behavior is "loud ImportError at runtime, not at type-check time" — acceptable. Documented in the shim docstring.
- **Code-reviewer P1.1 (Note)** — alias maps built and immediately discarded in `memo_cmd.py:471–474`. By design (item 009 consumes them); the throwaway `_`-prefixed locals signal intent. Code-reviewer suggested an explicit comment; the existing inline comment is sufficient.
- **Code-reviewer P1.4 (Note)** — `_reconstruct_opportunity_rows` lacks a focused unit test. Covered end-to-end by `test_memo_cmd_aliases.py`. Defer.
- **Silent-failure P1.3 (Note)** — `find_uncited_conclusions`'s empty-map RuntimeError is unreachable until item 009 wires the consumer. The guard is "load-bearing" only after item 009 ships; item 007's stub correctness is verified by `test_find_uncited_conclusions_empty_instrument_aliases_raises`.

## Post-fix verification

- `tests/memo/ tests/opportunity/ tests/fundamentals/ tests/commands/test_memo_cmd*.py tests/commands/test_opportunity_cmd.py tests/evals/test_architecture.py`: **743 passed / 12 skipped / 0 failed** (was 738 before; +5 new regression tests).
- `tests/evals/test_architecture.py::test_dag_acyclic_check_*`: PASS.
- Ruff on item 007 touched files: clean.

## Recommendation

**PASS-WITH-NITS.** Three actionable findings closed pre-PR with regression tests. Deferred items are P2 / theoretical / by-design. Ready for ship + post-ship verify + `/code-review`.
