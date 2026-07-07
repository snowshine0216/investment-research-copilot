# Item 004 — Rotation candidates join fix (review R-1, P0)

Spec for autodev run `review-followup`. Ground truth: `docs/2026-07-07-workflow-review.md`
§2.1 R-1 + §5. Locked scope: `BACKLOG.md` "Item 004". Effort: S. Kind: code (bug fix).

## Goal

The sector-rotation radar's L2 candidates join is dead code: the stock→board store
(`data/monitor/stock_industry_map.json`) holds f100 **行业 names** in its `industry`
slot (verified real shape: `{"000001": {"industry": "银行Ⅱ", "seen_at": "2026-07-06"}}`),
but `candidates.rank_candidates` filters `r.board_code in active` against **BK board
codes** (`candidates.py:28-33`). Because `_cmd_helpers.resolve_candidates` feeds the
name-valued map straight into `build_exposure` as if it were codes (`_cmd_helpers.py:101-103`,
`exposure.py:30-35`), every `ExposureRow.board_code` is actually a name, so the active
filter matches nothing and `candidates` is **always empty** — even on the successful
2026-07-06 `ok` run (21 active boards, 446-fund warm holdings cache, `candidates: 0`).
This item translates 行业 name → BK code **at the rotation join** (in
`resolve_candidates`, building `{board_name: board_code}` from the day's `BoardState`
list — which carries both), so the code-keyed active filter matches and the radar
produces its candidate rows from data already on disk. The store stays monitor-owned and
name-based (monitor joins names against the board-PE 板块名称 table). No board scoring,
no store shape, and no version numbers change.

## Acceptance criteria

- **AC1 — translation at the join.** `resolve_candidates` (`src/irc/rotation/_cmd_helpers.py`)
  builds a `{board_name: board_code}` map from the passed `states: tuple[BoardState, ...]`
  and translates the fresh stock→industry-name slice into a stock→**board-code** map
  *before* calling `build_exposure`. After the fix, `ExposureRow.board_code` carries a BK
  code, matching `rank_candidates`'s code-keyed `active` set.
- **AC2 — dead param removed.** `build_exposure` (`src/irc/rotation/exposure.py:17-21`)
  drops the never-used `board_names` parameter; its signature becomes
  `build_exposure(funds, stock_to_board)`. Grep confirms no remaining caller passes a third
  positional arg. `build_exposure` keeps its single job: `{symbol: board_code}` →
  fund×board exposure rows + coverage diagnostics (no taxonomy knowledge).
- **AC3 — false docstring corrected.** `src/irc/monitor/industry_map_store.py:16-19` no
  longer claims "board codes are stored in the `industry` slot". Rewritten to state the
  store holds 行业 **names** (f100) for both monitor and radar consumers, and that the
  radar translates name → board code at *its* join (`resolve_candidates`), never in the
  store.
- **AC4 — production-shaped integration test (committed, TDD red-first).** A new test drives
  a map whose `industry` slot holds **行业 names** (shape copied from the real store —
  `{sym: {"industry": "<name>", "seen_at": "<date>"}}`, e.g. `"银行Ⅱ"`, NOT the
  `"BK1"`-in-industry shape at `tests/rotation/test_seed.py:88` that masked this) through
  `record_seen`/`load_store` → `fresh_slice` → `resolve_candidates` (with a `BoardState`
  list carrying matching `board_name`+`board_code`, an active board, and a held fund whose
  holdings sit in that board) → asserts **non-empty** candidates whose `board_code` is a BK
  code in the active set. The same test asserts the pre-fix behavior (names passed through
  as codes) yields **zero** candidates — locking the name-vs-code distinction as a
  regression guard.
- **AC5 — build_exposure unit tests updated.** `tests/rotation/test_exposure.py` calls
  become 2-arg (`build_exposure(funds, s2b)`); their existing `s2b` (values already BK
  codes) is the correct post-refactor contract and needs no shape change — only the dead
  third arg is dropped.
- **AC6 — offline replay runtime proof (documented, not a committed fixture test).** Against
  the real on-disk `data/rotation/board_series.json` + real
  `data/monitor/stock_industry_map.json` (dated 2026-07-06; EM egress NOT required), a
  documented, re-runnable replay through the real `_build_states` → translate →
  `build_exposure` → `rank_candidates` path reproduces: **96** raw exposure rows on active
  boards ≥10% pre-cap (`BK1036` 58, `BK0465` 19, `BK0727` 15, `BK0474` 2, `BK0473` 1,
  `BK1259` 1 — exactly the review's figure), and **34** end-to-end `candidates` after the
  intentional `CAND_TOP_N=10` per-board cap (`candidates.py:14,36`). The spec records both
  numbers so `len(candidates) == 34 ≠ 96` is expected, not a defect. Pre-fix replay yields
  0 (confirmed).
- **AC7 — unmapped/HK degrade unchanged.** Holdings symbols absent from the translated
  code map (HK + un-seeded A-shares) still land in `build_exposure`'s existing
  `unmapped_syms` / `coverage_pct` diagnostics (replay: coverage 62.16%, 389 unmapped),
  which flow to `resolve_candidates`'s diag and the report. No new degradation code; the
  existing diagnostics path is preserved.
- **AC8 — no version bump.** `RotationReport.radar_version` and `schema_version`
  (`src/irc/rotation/types.py:57-58`) are unchanged. Board scoring / `states` computation
  untouched (F7 availability-class precedent).
- **AC9 — TDD + budgets.** Red → green → refactor; new/changed tests fail before the fix
  and pass after. Touched files stay < 200 lines and changed functions ≤ ~20 lines
  (`resolve_candidates` gains ~2 lines for the translation; `build_exposure` loses a param).
  Tests run per-file (`uv run pytest tests/rotation/test_exposure.py`,
  `.../test_candidates.py`, and the new integration test file), **never** the whole
  `tests/commands/` directory (documented hang, FACTS.md).

## Non-goals

- **No store-side translation.** The store (`data/monitor/stock_industry_map.json`) is
  monitor-owned and MUST keep 行业 names; `seed.py` (which already writes names via f100,
  `seed.py:83-99`) is unchanged.
- **R-4 seed skip-set freshness** (`seed.py:87-88`) is **item 005**, not this item — even
  though it sits in the same file. Do not touch the seed skip-set here.
- **No `radar_version`/`schema_version` bump**; no change to board scoring, hysteresis
  states, composite, or the flow/turn/PE legs.
- **No pagination / universe fix** (R-3), **no flow warm-up gate** (R-2), **no report
  layout change**. Diagnostics semantics stay as they are.
- **No new fetch, LLM, or network path.** Pure-logic + edge-glue change only.
- **No committing the real 2.9 MB `board_series.json` as a test fixture** — the replay is a
  manual runtime proof against live on-disk artifacts (they drift; committing them is
  heavy and pointless). The committed test uses a small production-*shaped* synthetic map.

## Constraints (incl. locked decisions)

- **LOCKED — translate at the join, not in the store.** The `{board_name: board_code}` map
  is built in `resolve_candidates` from the day's `BoardState` list and applied before the
  `active` filter. The store keeps names.
- **LOCKED — in scope:** fix the false docstring at `industry_map_store.py:16-19`; remove
  the dead `board_names` param in `build_exposure` (`exposure.py:17-49`).
- **LOCKED — no `radar_version` bump** (L2 bug fix; board scoring untouched — F7
  availability-class precedent).
- **LOCKED — unmapped/HK symbols still degrade to the existing diagnostics path.**
- **LOCKED — acceptance must include:** (1) integration test through the production-shaped
  (行业-names-in-industry-slot) map, seed→exposure→candidates, asserting non-empty
  candidates against active boards; (2) offline replay against the real
  `board_series.json` + real map reproducing ~96 candidate rows (runtime proof, EM egress
  not required); (3) per-file pytest only, never whole `tests/commands/`.
- **Board names are unique** (verified: 200 board names → 200 codes, 0 collisions) so
  `{board_name: board_code}` is lossless; **all 103 distinct industry names in the real map
  resolve to a board** (100% name coverage) — the join is sound.
- **Functional / immutable / effects-at-edges** per CLAUDE.md; translation is a pure dict
  comprehension. Worker dispatches carry the literal line **"Calling the Agent tool is
  FORBIDDEN"**. No VERSION bump; CHANGELOG `[Unreleased]` accumulation.

## Open questions resolved during brainstorming (auto-accepted; rationale recorded)

- **Q1 — translate upstream in `resolve_candidates`, or repurpose `board_names` inside
  `build_exposure`?** → **Upstream, drop the param.** The locked approach explicitly places
  the `{board_name: board_code}` construction in `resolve_candidates` and translation
  "before the active filter"; keeping `build_exposure` a pure symbol→code aggregator with
  no taxonomy knowledge is the cleaner boundary, and removing the never-used param beats
  reviving it as a second in-signature map.
- **Q2 — is the runtime-proof target 96 or 34?** → **Both, explicitly.** Empirically
  reproduced from on-disk 07-06 data: **96** = raw exposure rows on active boards ≥10%
  *before* the `CAND_TOP_N=10` per-board cap (matches the review's `BK1036 58 / BK0465 19 /
  BK0727 15…` verbatim); **34** = the actual `candidates` output *after* the cap. The
  review's "~96 candidate rows" measured the pre-cap signal. Recording both prevents an
  implementer from treating `len(candidates)==34≠96` as a failure.
- **Q3 — what makes the integration test "production-shaped"?** → 行业 **names** in the
  `industry` slot (copied from the real store shape), not the `"BK1"`-in-industry shape
  that masked R-1 (`tests/rotation/test_seed.py:88`). Small synthetic map + a `BoardState`
  list carrying both `board_name` and `board_code`, plus a held fund whose holdings map to
  an active board. Include the pre-fix `== 0` regression assertion.
- **Q4 — fate of existing `test_exposure.py` fixtures?** → Keep; just drop the dead third
  arg. Their `s2b` values (BK codes) are the correct post-refactor contract for
  `build_exposure`, since translation now happens upstream. The shape fix lives in the new
  `resolve_candidates`-layer test, which is where the name→code boundary actually is.
- **Q5 — does anything change for monitor / seed / store?** → No. The only code touched:
  `_cmd_helpers.resolve_candidates` (add translation), `exposure.build_exposure` (drop
  param), `industry_map_store.py` docstring, and the rotation tests. `seed.py`,
  `series_store.py`, monitor code, and the store file format are untouched.
- **Q6 — is the replay a committed test or a manual proof?** → Manual, documented,
  re-runnable proof against live artifacts (per AC6). Committing the real 2.9 MB
  `board_series.json` as a fixture is heavy and drifts; the committed regression coverage is
  the small production-shaped integration test.
