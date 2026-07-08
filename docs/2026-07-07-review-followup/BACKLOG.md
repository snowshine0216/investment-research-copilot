# Review follow-up backlog — 2026-07-07

Source: `docs/2026-07-07-workflow-review.md` (the review) + user scoping 2026-07-07.
Status: **LOCKED 2026-07-07** — Q-A resolved by the grill (spec GRILLED + LOCKED, see its
§9/§10); Q-B agreed (README light-enhance as specced in 002-b, no full restructure);
Q-C agreed (R-1 + R-4 included as items 004/005; monitor code fixes M-3/M-4/M-7 stay
TODOS-registered for a dedicated session).

**Execution order: 004 → 005 → 001 → 002 → 003.** Rationale: 004 is the P0 that unblocks
the rotation vertical's purpose (S effort); 005 prevents the ~2026-08-05 silent collapse;
001 is the feature; 002 runs AFTER the code items so TODOS/docs record their *fixed* state;
003 depends on 002.

**Handoff — run in a fresh session:**

```
/autodev /Users/snow/Documents/Repository/investment-research-copilot/docs/2026-07-07-review-followup/BACKLOG.md
```

(Item 001's spec §10 carries the same worker constraints — they apply to every item here:
the literal "Calling the Agent tool is FORBIDDEN" line in every worker dispatch; per-file
pytest only, never whole `tests/commands/`; production-shaped fixtures; runtime proof
before "done"; no VERSION bump, CHANGELOG [Unreleased]; ⚠️ this repo's rotation vertical
has a documented autodev two-worker concurrent-build race — verify agentId + git state
before judging notifications, recover via reset-to-reviewed-base.)

Out of scope for this backlog (user-locked): CN proxy purchase / efinance source switch
(future decision); review Tier-2 engine fixes (M-1 flow freshness, M-4 evidence pinning,
M-2 real factor_freshness) — each needs its own spec+grill when picked up.

---

## Item 001 — Data-health notification (feature)

Spec: `docs/superpowers/specs/2026-07-07-data-health-notify-design.md` — **GRILLED +
LOCKED 2026-07-07** (all decisions in its §9; implementation constraints in its §10).
Effort S–M.

---

## Item 002 — Docs-sync + TODOS reconciliation (docs-only + 1 small test)

The review's §0 state-correction table and §1 drift tables ARE the work order — this item
executes them. No design needed; every edit below cites review IDs (D1–D15) whose exact
file:line + ground truth live in the review doc.

**002-a Drift fixes (mechanical):**

- CLAUDE.md: rewrite stage-flow diagram + commands from `run_cmd.py:17-20` `STAGE_NAMES`
  (D1); add `irc rotation`/`rotation seed`/`monitor flow-capture`/`fundamentals
  stock-valuation` + the `monitor`/`rotation` packages to Commands/Architecture (D2);
  add `monitor.json` to the monitor output list (D14).
- TODOS.md: flip F7 to built/merged `4d5af11d` (D3); rewrite the F8/seed entries to the
  superseded state (seed DONE 2026-07-06, 200×60 store, ledger 52 rows, direct egress
  intermittent — review §0); same corrections in `src/irc/rotation/README.md:187-189` +
  `CONTEXT.md:290-295`.
- docs/monitor/README.md: f127 → f100 batch field at :44, :62, :235 (D4); "engine-3" →
  engine-4 phrasing at :141-142 (D7).
- README.md: schema 6→7 at :224 (D5); "fixed 7 funds"→10 at :444 (D6); "Report v3"→v4 at
  :200 (D8); flow-capture row gains the chained `irc rotation` (D10); rotation row added to
  the output-inspection cheatsheet (D15).
- evals/README.md: 7→10 funds at :77 (D6); +`engine_population` 4th MetricReport row at
  :187-188 (D11); six→seven pure scorers at :146-148, :310 (D12).
- CONTEXT.md: retire the 17:30-schedule paragraph at :323-325 → point at
  ops/launchd/README schedule table (D9); four→six narrative metric fns at :43, five→six
  categories at :41 (D13).
- Uncommitted README hunk: "~200 boards" → "~200 (pagination cap — exact universe
  unverified, see review R-3)"; fix the flow-leg proxy wording ("routed through
  `IRC_CN_PROXY` when set; works direct when unset") to match docs/monitor/README:244.
  **Commit FACTS.md together with the CLAUDE.md FACTS-pointer hunk** (untracked-file
  dangling-link risk).
- FACTS.md: update the F8 TEMPORARY section to the intermittent-direct state (review §0).

**002-b README/doc-map enhance (light — see backlog note Q-B below):**

- Add a "Doc map" block to root README + CLAUDE.md References listing the five manuals
  (root README, docs/monitor/README, src/irc/rotation/README, evals/README,
  ops/launchd/README) + the diagrams.
- Declare single owners: launchd schedule table lives ONLY in ops/launchd/README (README /
  docs/monitor/README link to it); factor weights + schema/engine numbers live ONLY in
  docs/monitor/README (or "see code constant").
- Diagrams: refresh `monitor-workflow.html` labels (v3→v4 at :78, :438; engine-3→4 at
  :431) + add the 15:45 rotation-chain box at :350. `overall-workflow.html`: relabel the
  CLAUDE.md link as "thesis-cards evidence pipeline (2026-05-21; predates monitor/
  rotation)" — full regeneration DEFERRED (M effort, low urgency).

**002-c TODOS registration of the review's deferred findings** (per operating contract:
deferred = why-deferred + pickup trigger). Add entries for: R-2 (flow warm-up gate — pick
up with a radar_version decision), R-3 (pagination/`data.total` — verify on next good
egress day), R-5 (paced seed — before next opportunistic seed), R-6/R-7 (history hygiene —
with F1 analysis), R-8/R-9 (holdings quarter/empty-cache — at first quarterly roll),
R-10/R-11, M-5 (flow provenance), M-6 (agreement floor), M-8 (as_of note); plus Tier-2
pointers M-1/M-2/M-4 marked "needs own spec". Tier-1 code fixes (R-1 join, R-4 seed
skip-set, M-3 DARK marker, M-4 ledger stopgap, M-7 fund isolation) registered as DO-NOW
entries pointing at the review — unless promoted to backlog items here (note Q-C).

**002-d Version-grep guard test (the only code in this item, TDD):** a test that extracts
the schema/engine/radar version numbers stated in README.md / docs/monitor/README.md /
evals/README.md / monitor-workflow.html and asserts they match `trace.SCHEMA_VERSION`,
`monitor_cmd._ENGINE_VERSION`, rotation `radar_version` — kills the D5/D7/D8 drift class
permanently. (Review §1.4 suggestion 5 / §4 item 6.)

Effort: S (one session). Exit gate: every D-item re-verified fixed; `git diff` reviewed;
version-grep test red→green; FACTS.md committed.

---

## Item 003 — Opus-enablement pass (review §4; process/docs, S)

What of §4 is repo-encodable (the rest is session routing discipline — lives in the user's
global PLAYBOOK, out of repo scope):

- **CLAUDE.md Conventions additions** (3 bullets):
  1. *Production-shaped fixtures*: integration fixtures for store/cache/join code must be
     copied from real artifact shapes, never hand-crafted (R-1 was masked by a hand-crafted
     `"BK1"` fixture — review §2.1).
  2. *Assembly assertion per feature*: every factor/pipeline feature needs one end-to-end
     test proving the new leg moves the final output from the command layer
     (`_process_fund`-style), not only pure-function tests.
  3. *Contract sentences name their test*: any "contract"/"invariant" sentence added to
     CONTEXT.md or an ADR names the enforcing test; prose-only contracts are the M-1 root
     cause.
- **FACTS.md header rule**: entries describing a live incident carry a date and a
  verification command, and must be re-verified before being acted on (the F8 entry went
  stale in 2 days).
- Depends on: 002-a (fixing CLAUDE.md's wrong content first — accuracy is the biggest
  Opus lever), 002-d (version-grep removes a drift class from model responsibility).

---

## Item 004 — Rotation candidates join fix (review R-1, P0, effort S)

**Defect** (review §2.1 R-1, all file:line-cited there): `seed.py:73-99` stores f100 行业
**names** in `data/monitor/stock_industry_map.json`; `_cmd_helpers.py:101-105` feeds them
to `build_exposure` as `board_code`; `candidates.py:28-33` filters `r.board_code in
active` keyed by **BK codes** → `candidates` is always empty (07-06 real `ok` run: 21
active boards, warm 446-fund holdings cache, 0 candidates; offline name→code replay → 96
rows).

**Locked approach — translate at the rotation join, NOT in the store.** The store is
**monitor-owned and must keep names** (monitor joins 行业 names against the board-PE
table's 板块名称). `resolve_candidates`/`_cmd_helpers` builds `{board_name: board_code}`
from the day's `BoardState` list (carries both) and translates before the `active` filter.
Also in scope: fix the false docstring at `industry_map_store.py:16-18` ("board codes are
stored in the industry slot"); remove or use the dead `board_names` param in
`build_exposure` (`exposure.py:17-49`).

**Acceptance:** (1) integration test driving the **production-shaped** map (行业 names in
the industry slot — copy the real store shape; the current fixtures' `"BK1"`-in-industry
shape is exactly what masked this) through seed→exposure→candidates and asserting
non-empty candidate rows against active boards; (2) offline replay against the real
`data/rotation/board_series.json` + real map reproduces ~96 candidate rows (runtime
proof — EM egress NOT required); (3) no `radar_version` bump (L2 bug fix; board scoring
untouched — F7 availability-class precedent); (4) unmapped/HK symbols still degrade to
the existing diagnostics path.

## Item 005 — Rotation seed skip-set freshness (review R-4, effort S)

**Defect:** `seed.py:87-88` skip-set = ALL existing map keys regardless of `seen_at` age,
while the daily join reads `fresh_slice` (≤30 calendar days, `industry_map_store.py:31,
86-90`). Only the ~60 monitor symbols get daily refreshes → the other ~640 mappings expire
by ~2026-08-05, exposure coverage collapses, and re-seeding skips them all forever.

**Fix:** seed's skip-set = `fresh_slice(existing, today)` keys (one line + tests).
**Acceptance:** test that a stale (>30d `seen_at`) entry is re-fetched by seed while fresh
entries are still skipped (resumability preserved); test that a seed run refreshes
`seen_at` on re-fetched entries.

---

## Backlog decisions — RESOLVED 2026-07-07

- **Q-A → grilled** (spec §9). **Q-B → agreed**: light enhance per 002-b only; full README
  restructure rejected for now (revisit after the doc-map beds in). **Q-C → agreed**:
  R-1/R-4 in as items 004/005; M-3/M-4/M-7 stay TODOS-registered — they touch the locked
  report/ledger surfaces and get their own spec+review session.
