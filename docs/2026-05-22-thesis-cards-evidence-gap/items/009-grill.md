# Item 009 — Grill summary

Auto-accepted under autonomy override 2026-05-23 (autodev backlog-mode grill subagent for the 2026-05-22-thesis-cards-evidence-gap feature). No human in the loop; every recommended answer locked against existing project precedent (ADRs 0001–0004, CONTEXT.md, items 002/003/006/007/008 grill+ship cadence).

## Verdict

**PASS-WITH-NOTES.** Spec is plan-ready. All 7 open questions auto-resolved, 4 ACs sharpened, 2 ACs added (now 25 total), one minor factual correction landed (memo-stage `out_dir` derivation), one new `RejectionReasonCode` added, two CONTEXT.md terms appended. **No new ADR.** The "notes" tag flags two items the planner should expect to revisit: (a) Q5 dimension-conclusion-dropping renderer is explicitly deferred to v2 with an inline TODO at the gate-emission site, and (b) the lifted helper module `tests/integration/_publishable_set_helper.py` touches item 008's locked baseline file and must keep ACs 22–23 byte-equal-locked through the lift.

## Seven open questions resolved

| # | Question | Locked answer | Source of authority |
|---|---|---|---|
| Q1 | v2 dimension-binding handoff | **Defer to v2 via a CONTEXT.md breadcrumb under "Audit gates and enforcement modes".** New paragraph names the v1 structural binding, the v2 contract sketch (per-`type`-literal dimension tagging in `ThesisEvidence`), and points at the deferred D2a "drop the dimension's conclusion text" renderer behaviour (Q5). No ADR — the dimension-binding is a renderer/audit decision that doesn't satisfy the 3-of-3 ADR test (not hard to reverse; not surprising in context once CONTEXT.md names it). | D1 in spec §5; 3-of-3 ADR check from item 007 grill F2. |
| Q2 | Canonical-path detection edge cases | **Exact suffix-match against `outputs/{out_dir.name}` where the date component is read from `out_dir.name`, not from a wall-clock `_today()`.** Rule (precise): `out_dir` is canonical IFF `out_dir.resolve().parent.name == "outputs" AND re.fullmatch(r"\d{4}-\d{2}-\d{2}", out_dir.name)`. This handles (a) the off-by-one risk where a run launched at 23:59:30 CST has `_today() != out_dir.name`, (b) `--output-dir outputs/2026-05-22` cross-day invocations (still canonical — it's a real `outputs/<date>/` path), (c) tmp_path scratch dirs (not canonical — parent is not literally `outputs`). | Existing `_reject_limit_on_canonical` shape at `opportunity_cmd.py:387-399`; corrected for the wall-clock-skew failure mode. |
| Q3 | `_publishable_rows_present_upstream` naming | **Rename to `strict_empty_alias_check: bool = False` (Q3 alternative (c)).** Keyword-only. The leading-underscore-as-warning crutch is removed; the call site reads "with strict empty-alias check" which is loud and intent-disclosing. The bool stays — an enum is overengineered for a binary; a function split (alt (a)) duplicates 50 lines of body logic for no real safety win. Default `False` preserves item 007's all-gapped pipeline state semantics for every existing call site. Only the gate-wiring caller in `memo_cmd.py` flips it to `True` via `strict_empty_alias_check=bool(rebuilt_op_rows)`. | Q3 in spec §6; locked against the F1 / F3 sharpening pattern from item 008 grill. |
| Q4 | New `RejectionReasonCode = "citation_gate_blocked"` | **YES — add `citation_gate_blocked` to both the `RejectionReasonCode` literal set AND `_GAP_TO_REASON` in `src/irc/opportunity/rejection_log.py`.** Identity mapping (gap code IS the rejection reason — same shape as `qdii_information_unavailable` and `fund_announcements_unavailable`). The alternative (reuse `incomplete_constituent_data`) conflates two failure modes in `rejections.json` and breaks the rejection taxonomy's intent ("one code per root cause"). Insertion order in `_GAP_TO_REASON`: append at end so existing precedence is unchanged (citation_gate_blocked is the most-derived code, naturally lowest precedence; only fires when the row reached publishable via H3 but then failed the citation gate). | Q4 in spec §6; spec §4 "Files explicitly NOT touched" amended to remove `rejection_log.py`. |
| Q5 | Deferred dimension-conclusion-dropping renderer | **Confirmed: V1 scope is fail-the-row (Step 2a removes the row, stamps `evidence_gaps=("citation_gate_blocked",)`, routes to `rejections.json` + discipline failure section). Renderer follow-up is documented as a v2 TODO via an inline comment at the Step 2a emission site AND in CONTEXT.md "Audit gates and enforcement modes".** No spec-AC churn; AC6 already locks the v1 "row-blocking" interpretation. | D1 in spec §5; matches item 008 grill F1 deferral pattern. |
| Q6 | Item-008 baseline interaction when gate flips to default `block` | **Item 008's existing seed (`_seed_publishable_set_repo`) carries dual-leg dual-scope evidence on every publishable row by construction (lines 372-444 of `test_publishable_set_lockdown.py`: holdings frame for data leg via `_build_active_fund_snapshot`; announcement frame for information leg; filing frame for CN-constituent data leg; broker-report frame for CN-constituent info leg).** Therefore: when the gate flips to default `block` after item 009 lands, item 008's ACs 1–23 stay green WITHOUT seed augmentation. No `IRC_CITATION_ENFORCE_MODE=off` env-var override needed in the harness. Verified by tracing the dispatch dict at lines 386-444 against the gate predicate from AC1 (≥1 data + ≥1 information leg on `row.thesis_evidence`). Locked as a new AC24 ("item 008 baseline passes with citation gate live"). | Dry-run inspection of `_seed_publishable_set_repo` against the spec's AC1 predicate; matches item 008 grill's F1 mitigation pattern. |
| Q7 | Memo-stage `out_dir`-vs-`today` canonical mismatch | **Spec §6 Q7 had a factual error.** `memo_cmd.run_memo` at line 419 computes `out_today = scoring_path.parent` (which may differ from today if scoring fell back via `_latest_file`), but at line 534 it OVERWRITES with `out_dir = root / "outputs" / today` where `today = _today()` (line 409). The two locals are inconsistent — `out_today` is used for READING upstream artifacts (scoring/gold/alloc/plan/opportunity), `out_dir` is used for WRITING (memo.md, memo_audit.txt, memo_blocked.md). **Item 009's gate writes its shadow log to `out_dir` (the write path), NOT `out_today` (the read path).** `_resolve_enforce_mode(out_dir, today)` is the right signature; `today` is taken from `_today()` captured once at the top of `run_memo` and threaded through. AC11 amended to clarify this; new AC25 locks the read-vs-write directory invariant. | Direct read of `memo_cmd.py:409,419,534`; spec §6 Q7's claim "out_dir = scoring_path.parent" was wrong. |

## Additional findings during grilling

### F1 — `out_dir` write-path vs `out_today` read-path is a latent confusion

`memo_cmd.run_memo` uses two different locals for "today's output dir":
- `out_today = scoring_path.parent` (line 419) — READ path for upstream artifacts; can resolve to a stale-date dir when scoring fell back via `_latest_file`.
- `out_dir = root / "outputs" / today` (line 534) — WRITE path for memo.md and friends; always uses `_today()`.

This is a pre-existing design (item 010 / `WARNING: using stale scoring from ...` at opportunity_cmd.py:1202 acknowledges the cross-date scenario). Item 009's gate **must not** confuse the two — the shadow log lives next to the writes, not next to the reads. Locked in AC25.

### F2 — `citation_gate_blocked` gap code needs `_GAP_TO_REASON` registration before Step 2a stamps it

Without Q4's registration, Step 2a's synthesised `evidence_gaps=("citation_gate_blocked",)` would crash `_classify_rejection_reason` at `rejection_log.py:212` (`raise RuntimeError("unknown evidence_gap code: ...")`). The spec §4 "Files explicitly NOT touched" line excluding `rejection_log.py` was inconsistent with Step 2a's synthesis. **Resolved:** Q4 added the code; spec §4 amended; AC4-of-row-blocking now references the precedence-preserving append.

### F3 — `discipline_rows` are built from `publishable_rows` (post-Step-2 partition)

`_write_opportunity_outputs` at line 1113-1115 builds `discipline_rows` via `_discipline_row_from(r, ...) for r in publishable_rows`. So Step 2c's `find_uncited_discipline_rows(discipline_rows, ...)` operates on the SAME post-partition set as Step 2a's row gate (minus any row that Step 2a removed). The two gates' findings are not double-counted because Step 2a runs first; a row blocked at 2a is not in `publishable_rows` by the time Step 2c builds `discipline_rows`. **Locked as a clarifying note in the spec §3 AC9 sequence.** No AC change.

### F4 — Tests touching the gate that may break when default flips to `block`

Audit results — directly inspected each suspect file:

| File | Risk | Verdict |
|---|---|---|
| `tests/integration/test_publishable_set_lockdown.py` | Item 008 baseline — gate runs against its seeds | **GREEN** per Q6 (dual-leg seeding already in place). |
| `tests/commands/test_memo_cmd_aliases.py` | Tests `build_alias_maps` wiring; runs `run_memo` | **GREEN** — runs on a non-canonical `tmp_path` so the env-var-or-default `block` applies but the test seeds dual-leg; if any fail, the integration harness will surface them. |
| `tests/commands/test_opportunity_cmd_*.py` (multiple) | Existing opportunity_cmd integration tests | **Most likely GREEN — all use `tmp_path`**, so canonical-path detection from Q2 returns False (parent is not `outputs/`); the env var defaults to `block` but the seeds typically carry dual-leg. The planner audits each file in item 009 plan phase. |
| `tests/memo/test_*.py` | Pure unit tests of memo internals; don't call `run_memo` | **GREEN** — no `_write_opportunity_outputs` or `run_memo` invocation; gate not exercised. |
| `tests/opportunity/test_*.py` | Pure unit tests of opportunity internals; don't call `_write_opportunity_outputs` | **GREEN** — same as above. |

**Conclusion:** no pre-gate seed-augmentation tasks needed for v1. The planner SHOULD run `pytest -x` once locally with the gate live and surface any unexpected failures in `009-drift.md` (matches item 006/008 inline-fix precedent).

### F5 — Spec's Q5 vs item-008-grill's Q5 mismatch

**Item 008 grill Q5** = "citation universe excludes `rejections.json`" (the universe formula). **Item 009 spec §6 Q5** = "dimension-conclusion-dropping renderer behaviour" (a v2 deferral). **These are different Q5s.** Both are correctly scoped; both are resolved in their respective items. No conflict. Locked as a clarifying note in §9 of the rewritten spec.

## ADR review

3-of-3 ADR test applied to potential new ADRs for item 009:

| Candidate ADR | Hard to reverse? | Surprising without context? | Real trade-off? | Verdict |
|---|---|---|---|---|
| "Citation gate enforcement is fail-closed by default on canonical paths" | Yes (couples production runs to dual-leg seed quality) | Yes (counterintuitive: a gate that ignores env var) | Yes (D1+D4 in spec) | **Mitigation: CONTEXT.md term, not standalone ADR.** Already follows ADR 0003's fail-closed precedent; not a new architectural commitment, just a wiring of already-defined primitives. |
| "Structural-only dimension binding in v1" | No (additive in v2 via `type` literal expansion) | Yes (D2a diagnosis-doc text reads stricter) | Yes (D1 in spec) | **SKIP** — locked in CONTEXT.md "Audit gates and enforcement modes" + spec §5 D1. |
| "Shared citation_audit.json across opportunity + memo stages" | No (file is purely observational) | Marginal (RMW pattern is unusual but understood) | Yes (D5 in spec) | **SKIP** — internal artifact; not a contract surface for downstream tools. |

**No new ADRs created.** ADR 0001–0004 stand unmodified.

## CONTEXT.md additions

Two terms appended to a new section "Audit gates and enforcement modes":

1. **`IRC_CITATION_ENFORCE_MODE`** — the env var; default `block`; canonical-path override rule; shadow log location.
2. **Citation gate v1 dimension binding** — structural-only (≥1 data + ≥1 information leg anywhere on `row.thesis_evidence` per row); v2 contract sketch (per-`type` dimension tagging); Q5 dimension-conclusion-dropping renderer deferred.

## AC audit results

### Testability without live network: PASS (all 25)

Every AC seeds via the lifted `_publishable_set_helper.py` (no network); no `irc.fundamentals.akshare_*` indirection un-patched. ACs that exercise the shadow log assert on on-disk JSON after `atomic_write_text`.

### Sharpness — single binary pass/fail per AC: PASS (all 25)

Every AC has a `sha256` comparison, `set ⊆ set` membership, `regex match`, `== literal`, or `raises ExceptionClass` predicate. No "the test asserts reasonable behavior" hand-waving. Q2's canonical-path rule is now expressible as a one-line regex.

### Spec-vs-code alignment: AUDITED

Spec line-number references re-verified against the working tree as of commit `a57c4c4`:
- `opportunity_cmd.py:1089-1096` Step 1 raise: ✓ confirmed.
- `opportunity_cmd.py:1098-1100` Step 2 partition: ✓ confirmed (lines now 1099-1100).
- `opportunity_cmd.py:1117` serializer call: ✓ confirmed (now line 1117).
- `opportunity_cmd.py:387-399` `_reject_limit_on_canonical`: ✓ confirmed.
- `memo_cmd.py:474-486` `_instrument_aliases`, `_constituent_aliases`: ✓ confirmed.
- `memo_cmd.py:530-532` route resolution → `call_chat`: ✓ confirmed.
- `memo_cmd.py:539-567` `audit_blocks_publish` gate: ✓ confirmed.
- `memo_cmd.py:568` `atomic_write_text(memo.md)`: ✓ confirmed.
- **`memo_cmd.py:419` `out_today = scoring_path.parent` AND `memo_cmd.py:534` `out_dir = root / "outputs" / today`: NEW finding (F1) — spec §6 Q7 had this wrong.**

## File-touch map (revised)

### New files
- `src/irc/opportunity/auditor.py` (~120 LOC)
- `tests/opportunity/test_auditor.py` (~250 LOC)
- `tests/integration/test_citation_audit_gate.py` (~600 LOC)
- `tests/integration/_publishable_set_helper.py` (~250 LOC — extracted from item 008's test file)

### Modified files (production)
- `src/irc/memo/numeric_audit.py` — adds `find_missing_pick_citations`, `find_uncited_discipline_rows`; replaces `find_uncited_conclusions` body; adds `strict_empty_alias_check: bool = False` keyword.
- `src/irc/opportunity/citation_map.py` — adds `build_constituent_cited_map`.
- `src/irc/opportunity/rejection_log.py` — **NEW per Q4:** add `"citation_gate_blocked"` to `RejectionReasonCode` Literal + identity mapping in `_GAP_TO_REASON` (append at end to preserve precedence).
- `src/irc/commands/opportunity_cmd.py` — adds `_resolve_enforce_mode(out_dir, today)`, `_write_citation_audit_shadow_log(out_dir, payload)`; wires Steps 2a/2b/2c.
- `src/irc/commands/memo_cmd.py` — wires the memo-stage gate; passes `out_dir` (write-path, line 534), NOT `out_today` (read-path, line 419), to `_resolve_enforce_mode`.

### Modified files (tests)
- `tests/memo/test_numeric_audit.py` — adds AC2/3/4/8/17/18/19.
- `tests/integration/test_publishable_set_lockdown.py` — import shift only (no AC change) for the lifted helper.

### Files explicitly NOT touched
- `src/irc/opportunity/types.py` — no schema change.
- `src/irc/opportunity/thesis_evidence.py` — no producer change.
- `docs/adr/0001-0004` — unchanged.

## Spec file diff

`docs/2026-05-22-thesis-cards-evidence-gap/items/009-spec.md` updated with:
- §2 "What's already in place" — added line-number re-verification footnote.
- §3 AC11 — sharpened canonical-path rule per Q2 (regex-expressible, `out_dir.name`-based).
- §3 AC17 — parameter renamed from `_publishable_rows_present_upstream` to `strict_empty_alias_check` per Q3.
- §3 NEW AC24 — "item 008 baseline passes with citation gate live" per Q6.
- §3 NEW AC25 — "memo-stage `out_dir` is the write-path local, not the read-path local" per Q7+F1.
- §4 "Modified files (production)" — `rejection_log.py` added per Q4.
- §4 "Files explicitly NOT touched" — `rejection_log.py` removed.
- §5 D6 — NEW decision documenting `out_dir` vs `out_today` discipline.
- §6 "Resolved open questions" replaces the original "Open questions for grill phase" (Q1–Q7 all resolved).
- §7 "Non-goals" amended: no new ADR; existing `_GAP_TO_REASON` keys are unmodified (only one new key appended).
- §9 NEW "Cross-item references" — Q5-of-item-008 vs Q5-of-item-009 disambiguation.
- Spec line count: 273 → ~330 lines.

## Unresolved questions

None at grill level. The planner inherits a fully-locked spec with two documented deferrals (Q1 v2 dimension binding; Q5 v2 renderer drop behaviour), both with breadcrumb terms in CONTEXT.md.

## Most consequential clarification

**F1 + Q7. The `memo_cmd.run_memo` `out_dir` vs `out_today` distinction.** Without F1, item 009's planner would have followed spec §6 Q7's incorrect claim and threaded `out_today` (the read path) into `_resolve_enforce_mode`. On any run where scoring fell back via `_latest_file` (i.e., today's scoring.json does not exist but yesterday's does), `out_today.name` would be yesterday's date AND the shadow log would land in yesterday's `outputs/<yesterday>/` directory — silently splitting the audit trail across two day folders and breaking AC22's two-run byte equality. The grill caught this by direct read of `memo_cmd.py:409,419,534`.

**F2 + Q4. The missing `_GAP_TO_REASON` entry.** Without Q4's registration, Step 2a's `evidence_gaps=("citation_gate_blocked",)` synthesis would crash `_classify_rejection_reason` immediately on first use — and the crash would be a `RuntimeError` from inside `_write_opportunity_outputs`, AFTER `opportunity_report.json` had already been atomically written but BEFORE `rejections.json`. The crash would land between two write steps, leaving the on-disk state inconsistent (publishable artifacts visible, rejection log missing). The grill caught this by walking the call sequence from Step 2a → Step 4.
