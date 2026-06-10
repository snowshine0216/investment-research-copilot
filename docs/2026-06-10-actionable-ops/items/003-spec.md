# Item 003 — Valuation axis ON (verify) + memo-routing docs fix

**Run:** `docs/2026-06-10-actionable-ops` · **Backlog item:** 003 · **Classification:** IN
**Status:** spec (brainstormed 2026-06-10, autonomy-override — no user in loop; recommended answers auto-accepted)

## Background correction (verified in code, not assumed)

The MASTER-SPEC item-003 row rests on two observations that **the code contradicts as of `autodev/actionable-ops-feature`**. Brainstorming reframed the item around the verified state rather than the stale premise.

1. **"Enable the valuation fundamental axis (ADR 0012, shadow→on)."** There are **two** distinct fundamental valuation axes; the spec conflated them:
   - **(A) Phase D active-fund look-through** — `active_fund_lookthrough.enabled` → `valuation_percentile_fundamental[_pb]` → `classify_valuation`. The **shipped template** `src/irc/templates/config/valuation_buckets.yaml` already has `enabled: true` (committed `cb1642d`, "Phase D PR2 — flip active-fund look-through ON (floor 0.50)", PR #111, 2026-06-05). Gate #4 and gate #5 are signed off (ADR 0012 addendum 2026-06-05; `docs/2026-06-04-phase-d-lookthrough-pr1/gate5-review-note.md`). **This axis is already ON in the shipped product.** There is no flag to flip.
   - **(B) Consensus-upside** — `consensus_upside_pct` → `valuation_fundamental_signal` (`src/irc/opportunity/valuation_fundamental.py`) → `compose_opportunity_state` (the `valuation_fundamental` param, `states.py:515`). This axis is wired end-to-end but evaluates to `None` in production because no wired broker feed carries a `target_price` (EastMoney drops 目标价 upstream). **This dormancy is a load-bearing ADR 0009 decision** ("the `None` is the contract... a future reader may helpfully stub a `target_price`. **Do not.**"). Lighting it up requires a target-price source (Tushare), which is **out of scope** for this item and would violate a recorded ADR.

2. **"README contradicts `config/llm.yaml` on memo routing."** The runtime `config/` directory is **gitignored** (`.gitignore:23 config/`). The shipped truth is the packaged template `src/irc/templates/config/llm.yaml`, which `irc init` copies into `config/` (`init_cmd.py` → `TEMPLATE_FILES`). The **template** routes `memo_synthesis → openrouter / anthropic/claude-opus-4.7` and `memo_audit → openrouter / anthropic/claude-sonnet-4.6` — and `README.md:36` correctly describes exactly that. The `deepseek-reasoner` routing the MASTER-SPEC saw exists **only in this machine's gitignored runtime `config/llm.yaml`** (a hand edit / local override), not in the shipped contract. So **README is already correct vs the shipped default**; rewriting it to claim `deepseek-reasoner` would make it wrong for every fresh `irc init` and contradict the template.

## Goal

Honestly close out item 003 against the verified code state rather than the stale premise: (1) **lock** the already-shipped valuation-axis state so it cannot silently regress — add a regression test that pins the packaged template's `active_fund_lookthrough.enabled: true` (Phase D PR2) and the memo→OpenRouter routing, plus a one-line decision record noting the axis is already ON (no flag flip is performed, because none is needed and the consensus-upside axis must stay dormant per ADR 0009); and (2) **disambiguate** the README so the template-vs-runtime config relationship is explicit — `config/llm.yaml` is user-generated from the packaged template, the shipped default routes memo to OpenRouter Anthropic, and re-routing to a DeepSeek-only setup is a supported local edit. No production behaviour changes; this item is a verification-and-documentation slice, not a code-path change.

## Acceptance criteria

Each is independently verifiable.

- **AC1 — Axis-ON state documented, not flipped.** A short decision note (in the item dir or appended to the run `PROGRESS.md` / a `003-verdict`) records that the Phase D look-through axis is already `enabled: true` in `src/irc/templates/config/valuation_buckets.yaml` (commit `cb1642d`, PR #111), so no flag flip is performed; and that the consensus-upside axis (`consensus_upside_pct`) stays `None` by the ADR 0009 contract (out of scope to enable). No change is made to the `enabled` value.
- **AC2 — Template-flag regression test.** A new test asserts the **packaged template** `src/irc/templates/config/valuation_buckets.yaml` parses with `active_fund_lookthrough.enabled is True` and `coverage_floor == 0.50` (locking the Phase D PR2 / gate-#5 decision against silent regression). Test mirrors source layout (e.g. `tests/templates/test_valuation_buckets_template.py` or alongside existing template/config tests).
- **AC3 — Memo-routing regression test.** A new test asserts the **packaged template** `src/irc/templates/config/llm.yaml` routes `memo_synthesis` and `memo_audit` to `provider: openrouter` with `anthropic/...` model ids (locking the shipped contract README documents).
- **AC4 — README disambiguation.** `README.md` is updated so the `config/llm.yaml` memo-routing statement explicitly notes that (a) `config/llm.yaml` is generated by `irc init` from the packaged template and is user-editable, (b) the **shipped default** routes `memo_synthesis`/`memo_audit` through OpenRouter Anthropic models, and (c) re-routing both tasks to DeepSeek (e.g. `deepseek-reasoner`) is a supported local change. No claim that the shipped default is DeepSeek.
- **AC5 — No behavioural drift.** A real `irc opportunity` (cached) and `irc decision` run on current outputs produce the same `valuation_state` / opportunity-state distribution as before this item (the item changes no runtime code path). Verified by diff against the pre-change outputs or by confirming no `src/irc/**` production module under the opportunity/memo paths is modified.
- **AC6 — Doc consistency.** Any wording in `README.md` and the MASTER-SPEC-referenced docs that would let a future reader re-derive the false "axis is OFF" or "README says OpenRouter but config says DeepSeek" claims is corrected or footnoted (at minimum README; CONTEXT.md/ADR only if a concrete inaccuracy is found there — do not gratuitously edit ADRs).
- **AC7 — Suite green vs baseline.** `uv run pytest` on the touched/new test paths passes; `uv run ruff check src tests` clean. Full-suite regressions, if any, are diff-scoped against the known-failing baseline (8 pre-existing failures + flaky e2e research gate) before being treated as regressions.

## Non-goals

- **Flipping `active_fund_lookthrough.enabled`** — already `true`; nothing to flip.
- **Lighting up the consensus-upside axis** (`consensus_upside_pct`) — requires a target-price source (Tushare `daily_basic`/research target) and would contravene ADR 0009's degrade-to-None contract. Out of scope; left dormant by design.
- **Stubbing or fabricating a `target_price`** — explicitly forbidden by ADR 0009.
- **Re-running or re-deciding gate #5 / the `coverage_floor` value** — settled at 0.50 (ADR 0012 addendum); this item only locks it against regression.
- **Editing the runtime `config/llm.yaml` or `config/valuation_buckets.yaml`** — gitignored, machine-local; not part of the shipped contract. (If a fresh-machine memo run is desired with the shipped default, that is an operator action, not a code change.)
- **Any change to `classify_valuation`, `compose_opportunity_state`, `populate_inputs`, the look-through aggregation, or the memo synthesis/audit pipeline.**
- **Touching the index/sector phases (A/B/C)** or `derive_position_risk_level`.

## Constraints

**Project rules (binding — from CLAUDE.md, MASTER-PLAN, ADRs):**

- **TDD mandatory.** Failing test first, then make it pass. New tests (AC2, AC3) are written red→green. Test file mirrors source (`src/irc/templates/...` → `tests/templates/...` or the existing config-test home).
- **No `VERSION` bump.** Accumulate any user-facing note under `CHANGELOG [Unreleased]` at the static VERSION (project convention; overrides the generic `/ship` VERSION step).
- **Files < 200 lines, functions < 20 lines** (ideal); extract helpers rather than nest > 3 levels.
- **Functional / immutable; effects at edges.** New test helpers are pure where possible; the only I/O is reading the packaged template (a thin wrapper, already provided by `init_cmd._read_template` / `config_loader`). No new module-level mutable state, no globals.
- **Secrets in `.env` only;** YAML references env-var names (`OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`) — unchanged.

**Performance:** none material — adds two fast offline unit tests and a doc edit; no new runtime path, no network, no LLM call.

**Public-API stability:** zero change to any Python signature, CLI command, or output schema. `compose_opportunity_state`'s `valuation_fundamental` param and `populate_inputs`'s `broker_reports`/`lookthrough_cfg` params are untouched. Outputs are byte-stable (AC5).

**Dependencies:** no new dependencies. Tests read existing packaged templates via the existing template-read seam.

**Security:** no secret handling changes; README edit must not inline any key (references env-var names only).

**Locked invariants (must remain intact, asserted by existing tests — this item touches none of their inputs):** H3 universal gapped-row, SAME-3 citation-set equality, 16-hex citation id (ADR 0001), `OpportunityRow.thesis_state` set only by `derive_thesis_from_evidence`, opportunity-before-memo `STAGE_NAMES` ordering, Policy B / `thesis_state` ownership (ADR 0003). `valuation_state` stays a separate axis from `thesis_state`.

## Open questions resolved during brainstorming (auto-accepted; rationale recorded)

- **OQ1 — "Enable the axis": which axis, and is a flip needed?** *Resolved:* The Phase D look-through axis is **already `enabled: true`** in the shipped template (commit `cb1642d`, PR #111, gate #5 signed off). The consensus-upside axis is dormant **by ADR 0009 design**. *Decision:* perform **no flag flip**; instead **verify + lock** the ON state and document it. *Rationale:* flipping an already-true flag is a no-op; enabling the consensus-upside axis would require an out-of-scope data source and violate a recorded ADR. The honest deliverable is regression-locking + documentation.
- **OQ2 — README vs config/llm.yaml: which is the truth, and which way does the fix go?** *Resolved:* The shipped **template** routes memo to OpenRouter Anthropic and **README already matches it**; the `deepseek-reasoner` routing lives only in this machine's **gitignored runtime** `config/llm.yaml`. *Decision:* **keep README's OpenRouter description** and add a clarifying note that `config/llm.yaml` is a user-editable copy of the template (DeepSeek-only is a supported local override). *Rationale:* the prompt's instruction "update README to match config, since config is what executes" assumes the executing config is the shipped contract — it is not; it is a per-machine, gitignored file. Describing the shipped default (the template) is the only stable, correct documentation; rewriting README to `deepseek-reasoner` would mislead every fresh `irc init`.
- **OQ3 — Should this item add a runtime mechanism to reconcile template vs runtime config (e.g. warn on drift)?** *Resolved:* **No.** *Rationale:* YAGNI — the gitignored-user-config pattern is intentional and established across all 12 config files; a drift-warning subsystem is a separate, larger concern and out of scope for a docs/verification item.
- **OQ4 — Where to record the "axis already ON" decision (AC1)?** *Resolved:* a concise note in the item/run dir (verdict file or `PROGRESS.md` line), **not** a new ADR. *Rationale:* ADR 0012's addendum already records the PR2 ON decision durably; a fresh ADR would duplicate it. This item only needs a verification record, not a new decision-of-record.
- **OQ5 — Scope of the doc fix (README only, or CONTEXT/ADR too)?** *Resolved:* **README only**, unless a concrete inaccuracy is found in CONTEXT.md/ADR during implementation. *Rationale:* the inaccuracy was in the MASTER-SPEC's reading, not in the shipped docs; gratuitous ADR edits violate the "don't propose unrelated changes" principle and risk churning load-bearing decision records.
- **OQ6 — Could not be resolved from MASTER-SPEC + code alone?** *None.* All ambiguities were resolvable from the code, the template files, git history (`cb1642d`, `5b0a22c`), and the ADRs. The only genuine judgement call (OQ2's fix direction) is recorded with rationale and is defensible from the gitignore + template-copy mechanism alone.
