# SKIPPED — Instrument Pickability Fixes

Three findings from the review were deferred per the user's P0-only scoping decision at intake. Listed here so the audit trail is complete and a follow-up run can pick them up.

## F4 — `thesis_news=50` constant; scores too narrow to differentiate picks

**Blocker**: Real differentiation requires news-content scoring against thesis keywords, not just citation presence. That's an LLM-scoring task that interacts with `src/irc/llm/` task routing, `src/irc/scoring/`, and the existing thesis-state machine. Doing it without the broader scoring redesign produces marginal gains.

**Recommended unblock path**: Spec a `thesis_news_scoring` ADR first. Define inputs (news headlines + thesis cards), outputs (0–100 alignment score), grading rubric, and how it interacts with the existing `derive_thesis_from_evidence` invariant. Then a separate autodev run can implement it.

## F5 — §2 macro research excerpts truncated to heading / first line

**Blocker**: The research summaries are LLM-generated and stored as opaque blobs under `data/research/`. The truncation appears to happen at the LLM prompt layer (`memo_synthesis` task) or at the research-summarizer step that feeds `gold_regime.json["evidence"]`. Fixing it well needs an LLM prompt change + ground-truth test fixtures + manual eval that the new summaries don't drift.

**Recommended unblock path**: Bench the current research prompt against a 5-week historical corpus, write a paragraph-level summary prompt variant, eval on the same corpus, commit only if quality improves on ≥4 of 5 weeks. Separate run.

## F6 — Filing data orphan; rows carry "数值不得作为业绩依据引用" warning yet still appear

**Blocker**: Design call, not implementation. ADR 0001/0003 explicitly preserve filing rows as "raw evidence archive". Removing them changes ADR semantics. Restating them so they ARE usable evidence requires either a normalization layer (revenue_yoy is currently raw with mixed units) or a deletion + ADR amendment.

**Recommended unblock path**: A design conversation, not an autodev run. Decide between (a) drop filing rows from picks evidence entirely and let broker reports + news carry the load, or (b) build a thin normalization wrapper that converts revenue_yoy to a comparable scalar with explicit unit handling. Write an ADR amendment first.
