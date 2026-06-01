# ADR 0011 — Bull/bear debate is advisory-only; `thesis_debate.md` is exempt from the determinism contract

**Status:** Accepted (2026-05-31, funding-analysis item 005)
**Builds on:** [ADR 0001 — citation data model](0001-citation-data-model.md), [ADR 0003 — failure-mode + Policy B + H3](0003-failure-mode-policy-b.md), [ADR 0004 — renderer determinism + SAME-3](0004-renderer-determinism-and-alias-policy.md).
**Spec:** `docs/2026-05-31-funding-analysis/items/005-spec.md`

## Context

Item 005 borrows the TradingAgents bull-vs-bear pattern: a `thesis_defend` LLM half (steelman the bull case) paired with a `thesis_falsify` half (steelman the bear case), run behind an opt-in `--adversarial` flag on `irc opportunity`, producing a paired debate a human reads alongside the report.

`thesis_falsify` was a **registered-but-unwired** task slot before item 005 — `config/llm.yaml` declared it, but `src/` had zero production call-sites (the only definition, `research/falsification.py::generate_falsification`, is never called and is **theme-shaped**: it argues over a free-text theme summary, not a constituent thesis card). So item 005 wires **both** halves for the first time.

Three contracts are non-obvious, expensive to reverse, and the product of real trade-offs:

1. **The debate is advisory-only — it sets no state and is not a canonical artifact or memo input.**
2. **`thesis_debate.md` is exempt from the two-run byte-equality / deterministic-renderer contract** that binds the five canonical artifacts — even though it is written by `_write_opportunity_outputs`, the function whose entire design (H3 partition, SAME-3, the publishable-set lockdown) exists to enforce determinism and citation discipline.
3. **A fresh card-shaped defend+falsify runner** (`src/irc/opportunity/debate.py`) is built rather than reusing the theme-shaped `research/falsification.py`.

This ADR locks all three. A reviewer reading `opportunity/debate.py` or a new non-deterministic file inside `_write_opportunity_outputs` six months from now should land here.

## Decision

### 1. Advisory-only — no state, no gate, no canonical artifact, no memo input

The debate reads the **already-derived** `OpportunityRow` (post-`derive_thesis_from_evidence`) and emits prose. It produces no `ThesisEvidence`, no `[ref:...]` marker, no `evidence_gaps` / `advisory_gaps`, and changes no `thesis_state` / `valuation_state` / `opportunity_state` / `core_dca` / Policy-B verdict. `thesis_state` remains exclusively owned by `derive_thesis_from_evidence` (ADR 0003); Policy B still owns publishability and never sets state. `thesis_debate.md` is **NOT** one of the five canonical artifacts (`opportunity_report.json`, `thesis_cards.yaml`, `discipline_report.md`, `rejections.json`, `memo.md`) and is **NOT** read by `irc memo` — the deterministic memo pillars (§2/§3/§5/§7) and the `IRC_*_BEGIN/END` verbatim regions never consume it.

It is a separate, additive file written **only** when the flag is on, AFTER and independently of the canonical artifacts. The flag defaults OFF; absent, the stage makes zero thesis-LLM calls and its outputs are byte-identical to today. On, the cost is `2 × n_publishable_rows` thesis-LLM calls (defend + falsify per publishable row). Debate runs on **publishable rows only** (the H3 `evidence_gaps == ()` set) — gapped rows have not earned a thesis conclusion, so debating them is meaningless and risks leaking gapped-row context.

### 2. `thesis_debate.md` is exempt from the determinism contract

ADR 0004's two-run byte-equality contract is scoped to the deterministic renderers (`memo.md`, `discipline_report.md`); item 008's publishable-set lockdown covers the five canonical artifacts. An LLM-prose artifact is **structurally outside both**. The exemption is explicit so a future contributor does not "fix" the apparent violation of a non-deterministic file living inside the otherwise strictly-deterministic write boundary, and does not try to add `thesis_debate.md` to the lockdown's two-run byte-equality assertion.

The split that makes this safe: the **pure renderer** `compose_thesis_debate_markdown(debates) -> str` IS deterministic (same `ThesisDebate` tuple in → byte-identical Markdown out, unit-tested by calling twice); only the upstream LLM-produced `arguments` / `conditions` are non-deterministic. Determinism is therefore preserved everywhere it is contractually owed (the renderer) and explicitly waived only at the LLM edge.

`--adversarial` is permitted on canonical `outputs/<date>/` paths — unlike `--limit` (rejected on canonical paths because it caps the active-fund set and so **corrupts the publishable set**), `--adversarial` adds an advisory file and touches no row, so it cannot corrupt a canonical artifact.

### 3. Fresh card-shaped runner, not the theme-shaped `research/falsification.py`

`src/irc/opportunity/debate.py` holds `DefenseResult` + a card-shaped `ThesisDebate`, the prompt builders, the JSON parse/sanitise, the pairing, and `compose_thesis_debate_markdown` — all pure — plus a thin runner with the two `call_chat` effects orchestrated from `commands/opportunity_cmd.py`. The opportunity inputs are structured `OpportunityRow` fields (`name_cn`, `thesis_state`, `opportunity_reason`, top-N `thesis_evidence`), not free-text theme summaries.

**Considered options:**

- *Reuse `research/falsification.py`'s `generate_falsification(thesis_summary, route)` for the bear half.* Rejected. Its prompt is theme-shaped and its signature takes a flat `thesis_summary` string — feeding a row would force a lossy card→prose flattening at the call site and couple the opportunity stage to the research package (wrong dependency direction). Two falsifiers with different input shapes is the correct outcome, mirrored by `DefenseResult` vs `FalsificationResult` carrying the same single-tuple shape but living in different packages.
- *Make the debate a canonical artifact or a memo input.* Rejected. It would drag a non-deterministic LLM file into the two-run byte-equality contract and the publishable-set lockdown, breaking both.
- *Let the debate adjust `thesis_state` / Policy B (a real bull/bear judge).* Rejected. Violates ADR 0003's sole-owner invariant; the debate is a reasoning aid, not a classifier. No multi-round debate / no judge / no convergence loop in V1 (YAGNI for a reasoning aid).

## Consequences

**Positive:**
- Flag-off behaviour is byte-identical to today and trivially provable — there is no pre-existing default-path thesis-LLM call to preserve.
- The determinism/lockdown invariants (ADR 0004, item 008) stay green untouched: the new file is outside their scope by construction.
- One row's LLM failure degrades to an empty half (`（本行未能生成辩论）` placeholder) and never aborts the run or blocks the canonical artifacts.

**Negative (acknowledged):**
- A non-deterministic file now lives next to the deterministic canonical artifacts in `outputs/<date>/`. Mitigated by the CONTEXT.md `thesis_debate.md` entry and this ADR, which state the exemption explicitly so the next contributor does not add it to the lockdown.
- Two falsifiers (theme-shaped in `research/`, card-shaped in `opportunity/`) coexist. Mitigated by the CONTEXT.md `DefenseResult` entry distinguishing them; collapsing them would re-introduce the input-shape mismatch.
