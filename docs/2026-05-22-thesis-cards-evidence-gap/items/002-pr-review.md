# Item 002 PR review — citation-data-model (Slice D0)

## PR
[#56](https://github.com/snowshine0216/investment-research-copilot/pull/56)

## Verdict
PASS-WITH-NITS

## High-confidence bugs
None.

## Latent bugs

**1. `fetch_types_attempted` is never serialized into `opportunity_report.json`, so the gapped-target failure section always renders `已尝试:` as empty.**

`fetch_types_attempted` was added only to `DisciplineRow`, not to `OpportunityRow`. `_row_to_dict` serializes `OpportunityRow` fields — it has no `fetch_types_attempted` key — so every row in `opportunity_report.json` lacks this field. When `render_failure_sections` calls `", ".join(op.get("fetch_types_attempted") or ())`, it always gets an empty string. The rendered line becomes `{iid} {name} | 原因: {gaps} | 已尝试:` with a trailing blank.

This is a spec-design gap: the spec adds the field to `DisciplineRow` (correct) and to `render_failure_sections`'s source dict (referencing the op row from JSON), but never adds it to `OpportunityRow` or to `_row_to_dict`. AC 27 tests that conclusion fields don't appear but does not assert that `已尝试:` is non-empty, so the test suite passes with the silent data loss.

Impact: the failure section of `memo.md` shows incomplete diagnostics for gapped targets. Item 006 (H3) is the downstream consumer that needs this field — it may trip on this when it wires the renderer to live data. Fix: add `fetch_types_attempted: tuple[str, ...] = ()` to `OpportunityRow` and serialize it in `_row_to_dict`, OR document explicitly that `已尝试:` will always be empty until item 006 populates it via a different path.

## Style / pattern observations

1. **`_strip_venue_suffix` leading-letter strip is over-broad** (confirmed from inline review). The check `stripped[0].isalpha() and stripped[1:].isdigit()` strips the leading alpha from any `X{digits}` pattern, including hypothetical non-A-share ids. The docstring acknowledges this but does not enumerate which leading letters are safe. Low risk for current universe but would silently break a canonical id like `H12345` if one were added. A more conservative fix would restrict to only `A` prefix (the only known A-share proxy).

2. **`_evidence_from_dict` silent skip when `citation_id` is falsy**: if an artifact was written with `citation_id=""` (pre-002 artifact or a bug), the round-trip check is skipped and no warning is emitted. The inline review also flagged this; it remains an observable gap. Adding a `raise ValueError` or at minimum a `warnings.warn` for the falsy case would catch artifact-version drift.

3. **`constituent_analyses` type annotation divergence**: `DisciplineRow.constituent_analyses` is typed `tuple[object, ...]` in the code but the spec and docstring say `tuple[Any, ...]`. `object` and `Any` have different mypy semantics — `object` is the stricter, more correct choice here (disallows arbitrary attribute access without cast), but the mismatch vs spec may confuse future readers. Either update the spec to say `tuple[object, ...]` or align the code to `tuple[Any, ...]` with a noqa comment.

4. **`CitationMeta.asset_class` has no `__post_init__` validation** (confirmed from inline review). Empty `asset_class` passes silently. The audit gates in item 009 depend on this field being a known non-empty string. A one-line `__post_init__` check would surface bad data at the producer rather than at audit time.

5. **`_slot_key` uses `getattr(e, "holding_weight_pct", 0.0) or 0.0`**: the `or 0.0` guard is correct for `None` but would silently coerce a legitimate `0.0` weight to `0.0` (no-op) and an accidentally-falsy `False` to `0.0` (correct). The double-0.0 pattern is slightly redundant — `float(getattr(e, "holding_weight_pct", 0.0) or 0.0)` is the safest spelling if `holding_weight_pct` could ever be `None` while the attribute exists on the object.

## Coverage gaps

1. **`_evidence_from_dict` mismatch path not tested** (confirmed from inline review). No test exercises the `ValueError` raise when JSON's `citation_id` doesn't match the recomputed value. This path is the tampering detector; its absence from tests means a regression could go unnoticed.

2. **`fetch_types_attempted` round-trip through `_row_to_dict`**: there is no test that asserts `_row_to_dict` emits `fetch_types_attempted`, because `OpportunityRow` does not have the field. If the latent bug above is addressed, a round-trip test should be added.

3. **Multi-instrument `build_cited_map` happy path**: the test exercises a single-row map. A test with two different `instrument_id` values (each with their own evidence) would validate the outer dict has two keys.

4. **`render_failure_sections` leading-newline contract not locked**: the function returns `"\n" + "\n".join(parts)` when non-empty, so the caller's `render_picks_table(...) + render_failure_sections(...)` gets one blank line between the table and the failure block. No test asserts this specific whitespace contract, meaning a refactor could silently remove the separator.

## Cross-check vs inline review (items/002-review.md)

**Inline reviewer's latent bug 1 — `is not` vs `not in` in `select_citations`:** REFUTED.

The inline reviewer's scenario requires `data_pick` and `info_pick` to be identity-different but equality-equal (`==`). This is impossible because:
- `data_candidates` filters to `citation_kind="data"` AND `scope in {"instrument","constituent"}`.
- `info_candidates` filters to `citation_kind="information"`.
- These sets are mutually exclusive on `citation_kind`, and `citation_kind` is a field in `ThesisEvidence.__eq__` (frozen dataclass). So `data_pick.citation_kind == "data"` and `info_pick.citation_kind == "information"` always, meaning `data_pick != info_pick` by `==` in every reachable state. The `is not` guard at line 63 and a hypothetical `!=` guard are logically equivalent.

The `not in selected` check in the fill-remaining loop (line 67) uses `__eq__`, which correctly deduplicates logically-identical entries. This is the desired behavior, not a bug.

**New issues found:**
- Latent bug 1 above (`fetch_types_attempted` not on `OpportunityRow`) is new and was not flagged by the inline reviewer.
- Nit 3 (`tuple[object, ...]` vs `tuple[Any, ...]` type annotation discrepancy) is new.
- Coverage gap 2 (`fetch_types_attempted` round-trip) is new and directly tied to the latent bug.
- Coverage gap 3 (multi-instrument `build_cited_map`) is new.

All of the inline reviewer's nits (items 1–5) are confirmed; nits 1 and 4 are repeated above with minor additional detail.

## Recommendation
Fix loop recommended for latent bug 1 before merge, or explicitly document that `已尝试:` in the failure section will be empty until item 006/`OpportunityRow` gains `fetch_types_attempted`. All other items are nits. The core schema (hash preimage, `__post_init__` validation, `select_citations` invariants, `build_cited_map` detectors) is correct and well-tested.

## Fix outcome

**Commit:** `c38afb9`

**Latent bug 1 (`fetch_types_attempted` schema gap) — RESOLVED.**

- `fetch_types_attempted: tuple[str, ...] = ()` added to `OpportunityRow` in `src/irc/opportunity/types.py`.
- `_row_to_dict` in `src/irc/opportunity/report.py` now serializes the field as `list(row.fetch_types_attempted)`.
- `render_failure_sections` in `src/irc/memo/picks_table.py` now renders `已尝试: —` when the list is empty (rather than leaving a trailing blank).
- `_discipline_row_from` in `src/irc/commands/opportunity_cmd.py` already used `getattr(row, "fetch_types_attempted", ())` — correct and no change needed.
- 6 new TDD tests added (red then green): 2 in `tests/opportunity/test_types.py`, 2 in `tests/opportunity/test_report.py`, 2 in `tests/memo/test_pick_rows.py`.
- `ruff check` clean on all touched files.
- Only the 4 known pre-existing failures remain (`test_only_stage_runs_single`, `test_thesis_coverage_meets_threshold`, `test_no_all_evidence_insufficient_valuation`, `test_eval_single_stage_data`).
