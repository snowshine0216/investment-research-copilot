# Item 003 — Opus-enablement pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encode the repo-actionable half of the 2026-07-07 workflow-review §4 ("what Opus needs to reach ~90% of Fable") as durable guardrail text — three testing-discipline bullets in CLAUDE.md's **Conventions (enforced)** section and one live-incident rule in FACTS.md's preamble — each citing the concrete failure it prevents.

**Architecture:** Docs-only. Two files, two independent edits, two commits. No `src/` change, no test file (justification below). Each new bullet is written in the file's existing voice and, like CLAUDE.md's "Things you'll trip over" entries, names the review finding it exists to prevent (R-1 for fixtures, the M3/dark-factor lesson for assembly, M-1 for prose contracts). Every edit is re-anchored against the **current** file (items 001/002 already merged on this branch and moved several targets) — the review's `file:line` are stale anchors, not ground truth.

**Tech Stack:** Markdown. `grep` for verification. No Python, no pytest.

## Global Constraints

- **Stay on branch `autodev/review-followup-feature`.** Do NOT switch branches, do NOT push.
- **Verify current state before every edit.** Read the target region first. Item 002 (merged) already added the "Doc map" block to References and left the **Conventions (enforced)** section (7 bullets, TDD → … → Skill routing) and the FACTS.md preamble blockquote **unchanged** — those are this item's two edit sites. Do not trust the review's line numbers; re-locate by the content anchors quoted in each task.
- **Scope is exactly the item 003 spec:** 3 CLAUDE.md Conventions bullets + 1 FACTS.md header rule. The rest of review §4 (session routing, model-selection discipline) lives in the user's global PLAYBOOK and is **out of repo scope** — do not add it here.
- **Voice:** match each file's register. CLAUDE.md bullets use a **bold lead phrase** then prose; the trip-over entries cite the specific bug/mechanism (e.g. "f127-on-`ulist.np`", "over-estimated ~35×"). Carry that citation habit into the new bullets. FACTS.md preamble is a `>` blockquote in plain English.
- **No line budget** on Markdown docs; keep bullets to one logical line each to match the surrounding Conventions list.

## Testing decision — NO test file (justified)

The item 003 spec's own bullet 3 ("contract sentences name their test") applies to **runtime contracts/invariants** — sentences asserting a behaviour that code must uphold. The three new Conventions bullets and the FACTS.md rule are **process discipline for the author/agent**, not runtime contracts: they have **no code source of truth to grep against** (unlike item 002-d's version-grep guard, which pins doc strings to `SCHEMA_VERSION`/`_ENGINE_VERSION` constants). A "self-enforcing" test could only assert the bullet strings are *present* in the doc — a circular presence-check that guards against nothing but accidental deletion, at real maintenance cost, and would tempt future editors to keep dead literal strings alive to satisfy it. The one plausible candidate — a test that greps CONTEXT.md/ADRs for "contract"/"invariant" and asserts each names a test — is brittle by construction (false-positives on every prose use of "invariant", no reliable way to segment a "contract sentence") and is explicitly **not** built here. **Decision: docs-only, no test.** Verification is the one-time `grep` sweep in each task, not CI.

---

## Task 1: CLAUDE.md — three testing-discipline bullets in Conventions (enforced)

**Files:**
- Modify: `CLAUDE.md` — the **Conventions (enforced)** section (currently ~lines 108–118); insert immediately **after** the TDD bullet and **before** the `- **Functional, immutable.**` bullet.

**Interfaces:**
- Consumes: nothing (standalone doc edit).
- Produces: three new top-level bullets grouped with TDD as the section's testing cluster. Downstream: none — Task 2 is independent.

- [ ] **Step 1: Re-anchor against the current file**

Read `CLAUDE.md` lines 108–120 and confirm the current text is exactly:

```
## Conventions (enforced)

These rules come from the project's `.cursor`/AGENTS guidance, ADRs, and global FP guidance. Apply them when writing or modifying code.

- **TDD.** Red → green → refactor. Never write implementation without a failing test first. Test file mirrors source (`foo.py` → `tests/.../test_foo.py`).
- **Functional, immutable.** Pure functions, `const`-style by default. …
```

If item 002 or a later edit moved this, re-locate by the literal string `- **TDD.** Red → green → refactor.` — that bullet is the insertion anchor. The three new bullets go on the lines **directly after** it (keeping all test-discipline rules adjacent to TDD), pushing `- **Functional, immutable.**` down.

- [ ] **Step 2: Insert the three bullets**

Edit `CLAUDE.md`. Anchor `old_string` on the TDD bullet line; `new_string` = the TDD bullet followed by the three new bullets. Insert **verbatim**:

```markdown
- **Production-shaped fixtures.** Integration fixtures for store / cache / join code must be **copied from a real on-disk artifact** (a real `data/**` store or cache file), never hand-crafted. R-1 — the rotation candidates join was dead (the stock→board map stores 行业 *names*, the join filters on `BK*` *codes* → **always 0 candidates**) — shipped green for weeks because `tests/rotation/test_seed.py` put a hand-crafted `"BK1"` in the industry slot, so the fixture never exercised the real name/code shape (review §2.1 / R-1).
- **Assembly assertion per feature.** Every factor / pipeline feature carries one end-to-end test proving the new leg moves the **final** output from the command layer (the `_process_fund`-style wiring tests under `tests/commands/`), not pure-function tests alone. Wiring — not logic — is the recurring failure here: the repo's own M3 lesson ("plan under-wired runner/metrics ASSEMBLY — caught by ship steps 8+9, not drift") and the dark-factor traps (a factor computed but never passed into `FactorInputs`, so it moves nothing) both pass every pure-unit test (review §4.4).
- **Contract sentences name their test.** Any "contract" / "invariant" sentence added to CONTEXT.md or an ADR names the test that enforces it; prose-only contracts are the M-1 root cause — the flow freshness contract (FRESH / STALE-N / DARK) lived only in CONTEXT.md + ADR 0019 text, was never implemented, and served stale flow rows indefinitely labeled "fresh" (review §4.3 / M-1).
```

The resulting order in the section is: TDD → **Production-shaped fixtures → Assembly assertion per feature → Contract sentences name their test** → Functional, immutable → Effects at edges → … → Skill routing.

- [ ] **Step 3: Verify the edit — presence, count, and section placement**

Run:

```bash
grep -n "Production-shaped fixtures\|Assembly assertion per feature\|Contract sentences name their test" CLAUDE.md
awk '/^## Conventions \(enforced\)/{f=1} /^## Things you.ll trip over/{f=0} f' CLAUDE.md | grep -c '^- \*\*'
```

Expected: first grep prints exactly **3** lines, all with line numbers **between** the `## Conventions (enforced)` header and the `## Things you'll trip over…` header (i.e. the three bullets landed inside Conventions, not in the trip-over section). Second command prints **10** (7 original bullets + 3 new). If either fails, the insertion missed the section — re-do Step 2.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(003): production-shaped-fixtures + assembly + contract-names-test conventions"
```

---

## Task 2: FACTS.md — live-incident rule in the preamble

**Files:**
- Modify: `FACTS.md` — the preamble blockquote (currently lines 3–6), between the existing blockquote and the `## Services & endpoints` heading.

**Interfaces:**
- Consumes: nothing.
- Produces: one new `>` paragraph continuing the preamble blockquote. Independent of Task 1.

- [ ] **Step 1: Re-anchor against the current file**

Read `FACTS.md` lines 1–8 and confirm the preamble ends with this exact line:

```
> live in `.env` — this file references the key name only, never a secret/proxy value.
```

followed by a blank line and `## Services & endpoints`. The F8 live-incident entry this rule generalises is in the **Services & endpoints** section (the `AkShare / EastMoney (board plane)` bullet, which already carries its "As of 2026-07-07 …" date and a "Re-verify with the CN egress board-plane one-liners below" instruction — that bullet is the exemplar the rule points at, and is **not edited here**).

- [ ] **Step 2: Append the live-incident rule to the preamble blockquote**

Edit `FACTS.md`. Anchor `old_string` on the final preamble line above; `new_string` = that line followed by a `>` separator and the new paragraph. Insert **verbatim**:

```markdown
> live in `.env` — this file references the key name only, never a secret/proxy value.
>
> **Live-incident entries carry a date and a verification command, and must be re-verified
> before being acted on.** A line describing a *transient* condition — a geo-block, an
> outage, a "currently unset / currently set" env var, a "currently blocked" egress plane —
> rots fast: the F8 board-plane entry below went stale **within 2 days** (written
> "hard-blocked", already superseded by a 2026-07-06 seed success at review time). Treat any
> dated live-incident line as a hypothesis, not a fact — run its cited one-liner (the
> `uv run python -c …` / CN-egress probes already in this file are the pattern) and trust the
> result, not the prose.
```

- [ ] **Step 3: Verify the edit — presence and placement before the first section**

Run:

```bash
grep -n "Live-incident entries carry a date" FACTS.md
awk 'NR>1 && /^## /{print NR": "$0; exit}' FACTS.md
```

Expected: the grep prints **1** line whose line number is **less than** the line number printed by the second command (i.e. the rule sits in the preamble, above the first `## ` section header, `## Services & endpoints`). If the grep line number is greater, the paragraph landed inside a section — re-do Step 2.

- [ ] **Step 4: Commit**

```bash
git add FACTS.md
git commit -m "docs(003): FACTS preamble — live-incident entries carry date + verify-before-acting rule"
```

---

## Self-Review

**1. Spec coverage** (item 003 spec, verbatim enumerated content):
- CLAUDE.md Conventions bullet 1 (production-shaped fixtures, R-1) → Task 1, bullet 1. ✔
- CLAUDE.md Conventions bullet 2 (assembly assertion per feature, `_process_fund`-style) → Task 1, bullet 2. ✔
- CLAUDE.md Conventions bullet 3 (contract sentences name their test, M-1) → Task 1, bullet 3. ✔
- FACTS.md header rule (live-incident date + verification command, re-verify before acting, F8 went stale in 2 days) → Task 2. ✔
- Out-of-scope §4 items (session routing) deliberately excluded per Global Constraints. ✔

**2. Placeholder scan:** no "TBD"/"handle edge cases"/"similar to Task N" — every bullet is written verbatim in the plan; no code steps. ✔

**3. Type/name consistency:** N/A (no code). Cross-file: Task 1 and Task 2 touch disjoint files; the two commits are independent and can land in either order. ✔

**4. Anchor freshness:** both tasks Step 1 re-read the current file and re-locate by literal content string, not by the review's stale line numbers (001/002 already merged on this branch). ✔
