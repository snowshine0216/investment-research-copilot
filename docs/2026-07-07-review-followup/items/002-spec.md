# Item 002 spec — Docs-sync + TODOS reconciliation (user-authored work order)

*(autodev run note: spec + grill are ⏭️ pre-completed by user instruction — BACKLOG.md: "The review's §0 state-correction table and §1 drift tables ARE the work order — this item executes them. No design needed; every edit below cites review IDs (D1–D15) whose exact file:line + ground truth live in the review doc." The work order below is copied verbatim from BACKLOG.md Item 002; ground truth = docs/2026-07-07-workflow-review.md §0/§1.)*

**IMPORTANT execution context:** items 004, 005 and 001 merged BEFORE this item (user-locked order, so docs record their FIXED state). Several target files/lines have already moved: 001's Task 6 amended ADR 0016 + docs/monitor/README + ops/launchd/README + root README; 004/005 added CHANGELOG/TODOS entries. Every D-item must be executed against CURRENT file state — re-locate targets, don't trust the review's line numbers blindly; where the fixed state supersedes the review's correction (e.g. F7/F8 TODOS entries must now ALSO note R-1/R-4 fixed), record the current truth.

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

