Verdict: PASS

Subagent: sonnet

Source: `docs/2026-07-07-review-followup/items/003-spec.md` (user-authored, verbatim from
BACKLOG.md). Item 003 is a docs-only change (CLAUDE.md Conventions bullets + FACTS.md
preamble) landed across 3 commits: `c8f6b43b` (initial bullets), `e0ecc4a3` (FACTS
preamble), `dc22d0f5` (review-driven rewording that closed three wording loopholes:
fixture scope vs. `-m integration`, adversarial-fixture exemption, `tests/commands/`
per-file caveat, and the `.env` grep recipe).

Entry point exercised (cold-read protocol): read ONLY the final committed text —
`CLAUDE.md:113-115` (Conventions bullets) and `FACTS.md:1-17` (preamble) — as a fresh
session would, with no other conversational context. `Skill(skill="verify")` was
considered and not invoked: the skill's own scope note excludes diffs that "only touch
tests, docs, or other code with no runtime surface to drive," which this item is: the
cold-read actionability test specified by the dispatch is the applicable verification
method here, not the runtime-proof skill.

Observed per check:

- **(a) Fixture rule.** `CLAUDE.md:113`: "Scope is by purpose, not test tier — this is
  not the `-m integration` pytest marker... at any test tier" → text alone confirms it
  covers plain unit tests, not just `-m integration` (i). Text also defines an explicit
  exemption: "Deliberately-adversarial fixtures (a mismatch, a duplicate, a malformed
  shape — built on purpose to exercise an edge case) are exempt from this and should
  look visibly synthetic" (ii). Applied to real cases: `tests/rotation/test_seed.py`'s
  hand-crafted `"BK1"` (cited in-rule as the R-1 violation — a *normal-shape* fixture
  masquerading as real input, correctly NOT exempt) vs. `tests/notify/test_health.py:152-201`
  (`funds: "x"`, `board_pe_freshness: 12345`, `funds: {"f1": "not-a-dict"}`,
  `signal: None`, `macro_snapshots: None` — each docstring-labeled "proven live crash",
  visibly synthetic wrong-typed values built on purpose) → correctly EXEMPT under the
  rule as written. Confirmed against fixture files on disk (`tests/notify/fixtures/*.json`,
  9–2737 lines each, sized like real captures, not literals) and against
  `003-notes.md:5-10`, which independently names this same file as a rule beneficiary.
- **(b) Assembly rule.** `CLAUDE.md:114`: "invoke the new test by its single file
  (e.g. `uv run pytest tests/commands/test_<name>_cmd.py -q`), never the whole
  directory" — text alone explicitly forbids bare `pytest tests/commands/`. PASS.
- **(c) Contract rule.** `CLAUDE.md:115` uses "sentence **added** to CONTEXT.md or an
  ADR" — forward-tense wording, read cold as: applies to new contract sentences, not a
  mandate to retrofit existing prose-only contracts (e.g. H3) already in CONTEXT.md.
  Independently corroborated by `003-review.md:11`: "'contract sentences name their
  test' is forward-only by wording ('added') — the pre-existing uncited CONTEXT.md
  contracts (H3 etc.) are intentionally not swept." PASS.
- **(d) FACTS rule.** `FACTS.md:11`: "re-verify any such claim with `grep -oE '^NAME=' .env`,
  substituting the real var name — names only, never values." Applied verbatim to the
  IRC_HTTPS_PROXY "currently set" claim at `FACTS.md:89`:
  `grep -oE '^IRC_HTTPS_PROXY=' .env` → returned `IRC_HTTPS_PROXY=` (match found, value
  never printed since the regex captures only up to `=`). Confirms the claim using only
  the preamble's own recipe, no value read. PASS.
- **Spec-bullet fidelity (step 3).** Diffed `003-spec.md` against final CLAUDE.md/FACTS.md
  text via `git show c8f6b43b/e0ecc4a3/dc22d0f5`: all 4 user-authored bullets
  (production-shaped fixtures, assembly assertion, contract sentences name their test,
  FACTS.md live-incident header rule) survive in the final text; the `dc22d0f5` rewording
  narrows/clarifies wording (scope-by-purpose, adversarial exemption, per-file caveat,
  grep recipe) without changing locked meaning, per `003-notes.md:3-17`.
- **Step 4.** `uv run pytest tests/docs/ -q` → `9 passed`.

Failures: 0.
