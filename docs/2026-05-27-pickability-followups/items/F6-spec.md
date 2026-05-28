# F6 — Filings evidence role: drop vs normalize

**Run**: `2026-05-27-pickability-followups`
**Origin**: `docs/2026-05-27-instrument-pickability/SKIPPED.md` F6
**Phase**: spec (Opus brainstorming-as-design)
**Locked dep-scan write surface** (from MASTER-PLAN):
`src/irc/opportunity/thesis_evidence.py`, `src/irc/memo/evidence_pool.py`,
**ADR amendment to `docs/adr/0001-citation-data-model.md` AND/OR
`docs/adr/0003-failure-mode-policy-b.md`**; tests under `tests/opportunity/` +
`tests/memo/`.

---

## Goal

Resolve the cognitive dissonance in today's memo — filing rows that carry the
"⚠️ 合规警示：…数值不得作为业绩依据引用，仅作原始数据存档" caveat in the
appendix **yet** are simultaneously selected by `select_citations` as the
data-leg citation in §5 picks evidence and the discipline-report nested bullets
— without (a) breaking the dual-coverage gate, (b) breaking Policy B rule 3,
or (c) silently converting an unverified raw scalar (`revenue_yoy=-0.0771…`)
into a confident percentage that the project has explicitly decided we cannot
defend. The chosen position, justified in detail below, is **keep filings as
the constituent-scope data-leg producer (no drop)** AND **reframe the role +
display** so the rendered surface matches the project's actual epistemic
stance: "the existence and date of this filing is reliable evidence of
disclosure; the raw `revenue_yoy` scalar is NOT a usable performance number."
The ADR amendment names this stance explicitly so a future contributor reading
either ADR 0001 §4 (audit-gate consumer list) or ADR 0003 §1 rule 3
(per-holding data leg) understands why the data-leg evidence is a
**disclosure-existence anchor**, not a number to read.

## Current state

In `outputs/2026-05-27/memo.md`, filing evidence appears in two distinct
surfaces with **different** rendering treatments:

1. **Inline picks evidence + discipline bullets** (the "load-bearing" surface
   read by `find_uncited_opportunity_rows`, the dual-coverage gate, and the
   SAME-3 selector): a single line like
   `**[27]** [stock:603927] filing · 603927.SH · 2026-03-31: 603927.SH 2026Q1 revenue_yoy=-0.07711453018869789 (...)`
   appears **without** the `⚠️ 合规警示` warning. 12 such inline filing rows
   in §5/§6/picks today. The synthesizer's system prompt (`memo/synthesizer.py:55-56`)
   forbids the LLM from converting `revenue_yoy` to a percentage, and
   `sanitize_unverified_revenue_yoy` (`tests/memo/test_pipeline_sanitization.py:86-109`)
   strips any LLM attempt to do so — so the reader sees the raw scalar
   verbatim with no in-context translation.
2. **Raw-evidence appendix (`## 附录·原始证据`)**: the same evidence line is
   prefixed by `⚠️ 合规警示：该字段含义及换算口径未经核实，数值不得作为业绩依据引用，仅作原始数据存档。 原始证据：…`
   triggered solely by the substring `revenue_yoy=` in
   `src/irc/memo/pipeline.py:176-177`. 12+ such appendix lines today.

In `outputs/2026-05-27/discipline_report.md`, filing rows render as bare marker
lines (`- [ref:7ed7f5d0b53e4ec5] filing · 600519.SH · 2026-03-31`) inside the
per-fund nested bullets — no warning, no numeric scalar shown (the
`per-fund 持仓` block shows the summary fragment; the citation bullet itself
is identifier-only).

**Downstream load-bearing consumers of filing rows** (each verified from the
code):

- **Policy B rule 3** (`opportunity/policy_b.py:316-333`): rejects any active
  fund where ANY ranked holding lacks `citation_kind="data"` evidence. The
  **only** producer of constituent-scope `citation_kind="data"` evidence in
  the codebase is `_evidence_for_constituent` (`fundamentals/snapshot.py:341-346
  and :392-397`) emitting `type="filing"`. Macro and fund-level paths produce
  `type="snapshot"` instead, but at `scope="asset_class_macro"` or
  `scope="instrument"` — not constituent. **Dropping `type="filing"` from
  constituent-scope evidence would cause Policy B rule 3 to fire for every
  active fund** that isn't already routed through rule 2.5 (foreign-heavy)
  or `_build_fund_level_snapshot` (QDII reform).
- **`select_citations`** (`opportunity/citation_selector.py:56-61`): the data
  slot picks `citation_kind="data" AND scope in {"instrument","constituent"}`.
  For active funds, that is the filing row. The SAME-3 invariant (ADR 0004)
  guarantees picks-table / evidence-pool / discipline-renderer all call this
  same selector with no pre-filter — so any change has to be expressed as a
  shape change to the evidence itself, not a per-surface filter.
- **`find_uncited_opportunity_rows`** (ADR 0001 §4): every publishable row
  must carry ≥1 data-leg with `scope in {"instrument","constituent"}`. For
  active funds: only filings satisfy this.
- **`_flatten_analyses` `_TYPE_RANK`** (`opportunity/thesis_evidence.py:285`):
  `{"filing": 0, "broker": 1, "news": 2}` — filings sort first per holding,
  making them the visually prominent citation row for each constituent.

**Conclusion from the current-state read**: filings are not orphan data; they
are the spine of constituent-scope data-leg coverage. The cognitive dissonance
is real but it is a **display + framing** problem, not a structural-role
problem. The fix has to keep the role and reframe the framing.

## The drop-vs-normalize decision

### Considered options

**A. Drop filings from picks evidence entirely.** Simplest at first glance —
shrink `_filing_evidence` (legacy path) and `_evidence_for_constituent`
(active-fund path) to never emit `type="filing"`; let broker reports + news
carry the load.
**Rejected**, because:
- Every active fund whose top-N holdings include CN-listed names would fail
  Policy B rule 3 (`incomplete_constituent_data` fires unless ALL ranked
  holdings carry `citation_kind="data"`). The only other data-leg producer
  for constituent scope is fund-level NAV via rule 2.5, which only fires for
  foreign-heavy funds. Net effect: ~all CN active funds would move from
  publishable → rejected. That is a regression of decision quality much
  larger than the cognitive-dissonance harm we are trying to fix.
- Re-routing all active funds through `_build_fund_level_snapshot`
  (QDII-style) would strip `constituent_analyses`, breaking the `## 持仓明细`
  appendix renderer (CONTEXT.md "持仓明细 appendix") — the same trade-off
  ADR 0003 §7 rejected for foreign-heavy funds.

**B. Normalize `revenue_yoy` to a comparable percentage at display time.**
Convert `-0.0771…` to `-7.7%` with explicit unit handling so the reader can
trust the rendered number.
**Rejected**, because the project has **already decided** (in
`memo/synthesizer.py:55-56` + `sanitize_unverified_revenue_yoy` +
`_REVENUE_YOY_APPENDIX_CAVEAT`) that the AkShare-sourced raw scalar's unit
and accounting convention are **not validated**. Some sources emit a fraction
(0.0771 → 7.71%), others may emit a percentage already (7.71 → 7.71% — or
771%, depending on issuer), and the CN/HK/edgar paths use different
normalization conventions inside `akshare_filing.py` / `hkex_client.py` /
`edgar_client.py`. Asserting `-0.0771 ⇒ -7.7%` everywhere is a confidence
claim we cannot back today. A full unit/normalization pass — per-provider
unit declarations, currency awareness, accounting-period alignment, scale
disambiguation — is the start of a fundamentals-data rewrite, which is
explicitly **out of scope** for this run.

**C. Keep filings + reframe role (chosen).** Filings continue to flow as
constituent-scope `citation_kind="data"` evidence (no role change → Policy B
rule 3, dual-coverage gate, SAME-3 invariant all unaffected). The
**displayed summary** changes from
`f"{symbol} {fiscal_period} revenue_yoy={raw_scalar}"` to a
disclosure-existence form that does not show the unverified scalar at all —
e.g. `f"{symbol} {fiscal_period} 财报已披露 (字段口径未核实)"`. The
appendix caveat key shifts from substring-`revenue_yoy=` to a
field-on-the-evidence flag (`disclosure_existence_only=True` style) so the
warning still attaches when applicable AND no longer false-negatives if the
summary template is later edited. The ADR amendment lands in **ADR 0001 §3
(citation-id hash preimage)** plus a new ADR 0001 §5 "Filing evidence
semantics" subsection, NOT in ADR 0003 — because the change is about what a
filing-typed citation *means* (citation data model), not about the audit
policy that consumes it.

### Recommendation: Option C — keep + reframe

One-sentence rationale: **filings are load-bearing as a disclosure-existence
anchor for the dual-coverage gate; dropping them breaks Policy B for every
CN active fund, and normalizing the scalar would be a confidence claim we
cannot back today — so the right move is to reframe the displayed summary
so it stops showing the unverified scalar inline, while leaving the
structural role (data-leg, constituent-scope, citation_kind="data") fully
intact.**

This is also the **smaller surface**: a localized edit to two summary-template
sites (`fundamentals/snapshot.py:344` and `:395`) plus the legacy path
(`opportunity/thesis_evidence.py:98`), the appendix caveat trigger in
`memo/pipeline.py:176`, the synthesizer prompt's `revenue_yoy=` quote in
`memo/synthesizer.py:55-56`, and the citation-id preimage in ADR 0001 §2
(which uses `summary[:64]` as the fallback when URL is empty — so the
summary text change CAN change citation_ids; this needs the ADR amendment to
acknowledge and accept the one-time hash re-roll for affected entries — same
shape as item 002's breaking-change absorption).

## Acceptance criteria

1. **No `revenue_yoy=<raw>` substring appears inline in any `ThesisEvidence.summary`
   field after this change.** `_evidence_for_constituent` (CN + HK paths) and
   `_filing_evidence` (legacy path) emit a `summary` of the form
   `f"{symbol} {fiscal_period} 财报已披露（口径未核实）"` (Chinese; exact wording
   per spec self-review). Verified by a unit test that builds an
   `ActiveFundSnapshot` with one CN holding and asserts the resulting
   `ThesisEvidence.summary` does not contain `"revenue_yoy="`.
2. **Policy B rule 3 keeps firing iff the underlying filing fetch failed
   (NOT because of the summary change).** Existing
   `tests/opportunity/test_policy_b.py` cases that build `type="filing"`
   evidence with `citation_kind="data"` continue to pass. A regression
   test asserts that an active-fund snapshot whose top-N all carry the new
   summary form is **publishable** under Policy B (no rule 3 fire).
3. **`select_citations` data-slot continues to select filing evidence for
   active funds** when broker/news rows are also present. A regression test
   builds a constituent analysis with `(filing, broker, news)` and asserts
   `select_citations(...).data_slot is the filing entry` (or, given the
   selector's tuple return shape, asserts the filing entry appears in the
   selected tuple and is the entry whose `citation_kind == "data"`).
4. **Dual-coverage gate (`find_uncited_opportunity_rows`) continues to pass
   for every publishable opportunity row in the existing test corpus.** No
   new uncited-row failures introduced.
5. **SAME-3 invariant holds**: the citation-id set rendered by
   picks-table, evidence-pool, and discipline-renderer remains pairwise
   equal for every fund row, both before and after the change. Verified by
   the existing SAME-3 acceptance test (ADR 0004) running green.
6. **Appendix caveat trigger no longer keys on `revenue_yoy=`.** The trigger
   moves to a structural condition — either (a) the evidence's
   `type == "filing"` AND it carries a new flag indicating
   disclosure-existence-only semantics, OR (b) a dedicated
   `_appendix_caveat_for_evidence_kind` lookup keyed on evidence type. Final
   wiring choice is locked in the grill. Either way, the appendix line in
   `outputs/<date>/memo.md` for a filing row still renders the
   `⚠️ 合规警示：…` prefix (so user-facing compliance posture is unchanged)
   AND no longer false-negatives if the summary template is edited.
7. **Citation-id hash re-roll is acknowledged in the ADR amendment.** Since
   the citation-id preimage uses `summary[:64]` as the URL-empty fallback
   (ADR 0001 §2), filing summaries that previously hashed `… revenue_yoy=…`
   now hash `… 财报已披露 …`. The ADR amendment states this is a one-time,
   intentional break (no migration); existing test fixtures that pin a
   specific hex citation_id for a filing row are updated in the same PR.
   This mirrors item 002's "single-slice absorbs the breaking-change cost"
   pattern.
8. **`memo/synthesizer.py` system-prompt clause about `revenue_yoy`
   (line 55-56) is updated** to reflect the new contract: "filing evidence
   does not expose `revenue_yoy` inline; do not invent a percentage from
   the filing date or symbol alone." `sanitize_unverified_revenue_yoy`
   stays in place as the belt-and-braces defense (it still strips any LLM
   hallucinated percentage).
9. **No regression on the 7 pre-existing test failures called out in the
   prior run's `run-final-verify.md`.**
10. **ADR amendment to ADR 0001 lands in the same PR.** New subsection or
    addendum titled "Filing evidence semantics" explicitly states (a) filings
    are constituent-scope `citation_kind="data"` and remain load-bearing for
    Policy B rule 3 + dual-coverage gate, (b) the displayed summary does
    NOT expose the unverified `revenue_yoy` scalar, (c) the appendix
    caveat is the user-facing compliance surface, (d) normalization of
    `revenue_yoy` to a percentage is deferred to a future, separately-scoped
    fundamentals-data effort. ADR 0003 receives a one-line cross-reference
    to ADR 0001's amendment so a reader landing in ADR 0003 §1 rule 3 sees
    the semantics pointer.

## Non-goals

- **No revenue_yoy unit-normalization layer.** No per-provider unit
  declarations, no currency awareness, no accounting-period alignment, no
  scale disambiguation. That is a fundamentals-data effort and explicitly
  out of scope.
- **No change to Policy B precedence, gap codes, or rule 2.5 semantics.**
  ADR 0003 is unchanged except for a one-line cross-reference pointer.
- **No change to the `## 持仓明细` appendix renderer's per-holding summary
  fragment shape.** The `one_line_view` field (`fundamentals/snapshot.py:542`)
  uses `summary[:24]` to compose the per-holding fragment; that fragment will
  now read `"600519.SH 2026Q1 财报已披"` instead of
  `"600519.SH 2026Q1 revenue"` — accepted as a side-effect of the summary
  change; no separate rework.
- **No change to fetch adapters** (`akshare_filing.py`, `hkex_client.py`,
  `edgar_client.py`). `FilingDigest.revenue_yoy` is still produced and still
  drives `_yoy_split` for the legacy thesis-state classifier. The change is
  in the *display layer* only.
- **No new ADR file.** Amendment-in-place to ADR 0001 mirrors the precedent
  ADR 0003 §7 set (amendment over sibling-ADR-that-overrides).
- **No change to the discipline-report nested-bullet shape.** Filing rows
  there are already identifier-only (`[ref:…] filing · symbol · date`);
  they have no scalar to remove.

## Constraints

- **TDD mandatory** — red-green-refactor. Every acceptance criterion above is
  expressed in tests-first form. No implementation lands without a failing
  test first.
- **Functional / immutable** — no mutation of `ThesisEvidence` instances;
  changes flow through `dataclasses.replace` or direct construction at the
  producer call sites.
- **H3 universal gapped-row invariant + SAME-3 invariant** preserved.
  Citation-set equality across picks-table / evidence-pool / discipline-renderer
  is verified by the SAME-3 acceptance test (ADR 0004); the test runs green
  pre- and post-change.
- **Citation-id format unchanged** — `\[ref:[0-9a-f]{16}\]` (ADR 0001).
  The hash preimage formula in ADR 0001 §2 is unchanged; what changes is
  the **input** to `summary[:64]` for filing rows. The ADR amendment
  acknowledges the one-time citation_id re-roll.
- **Policy B semantics preserved exactly** — `evaluate_policy_b` reads the
  evidence shape (`type`, `citation_kind`, `scope`), not the summary text;
  no Policy B test changes required beyond fixture-summary updates.
- **ADR amendment authoring required** — happens in the grill phase per the
  backlog-mode contract; this spec locks the target ADR (0001) and the
  pointer-only update to ADR 0003.
- **Cross-citation-universe integrity** — `build_cited_map` provenance check
  still raises on `owner_instrument_id != row.instrument_id`; the change
  does not touch ownership fields.
- **Live-test gate untouched** — no new live-test paths.
- **File-size budget**: target files are well under 200 lines; the change
  is line-level not structural.

## Open questions resolved during brainstorming

1. **Is the warning in memo.md§ appendix today doing real work?**
   *Resolved: yes — it is the user-facing compliance surface, and there's a
   matching belt-and-braces defense in `sanitize_unverified_revenue_yoy` plus
   a synthesizer-prompt clause forbidding LLM percentage conversion. Keep the
   user-visible warning; just stop keying it on the substring
   `revenue_yoy=` so the trigger survives the summary template change.*

2. **Could we change ONLY the appendix renderer to suppress the inline filing
   row OR change ONLY the summary template?**
   *Resolved: changing only the summary template is necessary AND sufficient.
   The summary text is what the SAME-3 invariant carries through to picks-
   table + evidence-pool + discipline; fixing it at the producer removes
   `revenue_yoy=<raw>` from every downstream surface in one shot. Changing
   only the appendix would leave the dissonance in picks evidence (where the
   reader actually decides) unfixed.*

3. **Why ADR 0001 instead of ADR 0003 for the amendment?**
   *Resolved: ADR 0001 governs the citation data model — what a citation
   IS, including what its summary should and should not contain. ADR 0003
   governs the audit policy — when a missing-data-leg causes a fund to be
   rejected. The change is purely about the meaning + display of a filing
   citation; Policy B rule 3 still reads `citation_kind="data"` and is
   semantically unchanged. Cross-reference pointer in ADR 0003 §1 rule 3
   gives reader navigability without splitting authority.*

4. **Does the citation_id hash re-roll count as a breaking change?**
   *Resolved: yes, technically — but the same way item 002 absorbed the
   `ThesisEvidence` field addition. No persistent consumer keys on a specific
   citation_id across the change boundary (citation_ids are recomputed on
   every run from the live evidence). The only call-sites that pin specific
   hex citation_ids are test fixtures; those get updated in the same PR.
   ADR amendment names this explicitly so a future reader doesn't trip.*

5. **Should `derive_thesis_from_evidence`'s `_TYPE_RANK` change?**
   *Resolved: no. `_TYPE_RANK = {"filing": 0, "broker": 1, "news": 2}`
   reflects display ordering (filing rendered first per holding). That
   ordering remains correct for the disclosure-existence form: a citation
   that anchors "this issuer disclosed on date X" is still the most
   foundational evidence row, and broker commentary + news still build on
   top of it.*

6. **Can the LLM still mention revenue_yoy as a directional cue (e.g. "营收
   同比为负")?**
   *Resolved: yes, but only via the LEGACY-path `_yoy_split` classifier
   which feeds the deterministic thesis-state ("falsified" / "intact" /
   "under_pressure") via `_classify_state`. The synthesizer never sees a
   percentage in the evidence pool, and the synthesizer-prompt clause still
   forbids it from inventing one. The thesis-state token (`intact` /
   `falsified` / etc.) IS still derived from `revenue_yoy` direction —
   that's a directional sign-of-the-fraction check, not a magnitude claim,
   and survives the "unit unverified" critique because direction is
   robust to scale errors as long as the sign convention is correct
   across providers. The grill phase confirms whether the sign convention
   IS correct across providers — if not, that's a separate, narrower
   follow-up.*

7. **What happens to the `_REVENUE_YOY_APPENDIX_CAVEAT` text itself —
   keep or reword?**
   *Resolved: keep the wording, change the trigger. The text
   "⚠️ 合规警示：该字段含义及换算口径未经核实，数值不得作为业绩依据引用，
   仅作原始数据存档。" is correct and compliance-aware; the only problem
   was that the trigger leaked an unverified scalar into the user's eye
   before the warning could fire. With the scalar removed from the
   summary, the trigger moves to a structural flag (evidence type / kind)
   and the same wording renders against the now-scalar-free body.*

---

**Spec self-review note**: pass — no placeholders, no contradictions, scope
is single-PR (target files all named, no fundamentals-data rewrite leaks in),
all 10 acceptance criteria are independently verifiable, ADR target (0001)
named, cross-reference target (0003) named. The exact final wording of the
new filing summary template (`财报已披露（口径未核实）` vs alternatives)
is intentionally left as a small grill-phase decision — the test in
criterion 1 keys on the absence of `"revenue_yoy="`, not on the presence of
a specific Chinese string, so wording iteration won't churn tests.
