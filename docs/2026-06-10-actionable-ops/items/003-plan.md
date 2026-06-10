# Item 003 — Valuation axis ON (verify) + memo-routing docs fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regression-lock the already-shipped Phase D look-through axis (`active_fund_lookthrough.enabled: true`, `coverage_floor: 0.50`) and the memo→OpenRouter-Anthropic routing in the packaged config templates, and disambiguate the README so the packaged-template-vs-runtime-config relationship is explicit — with zero production code-path change.

**Architecture:** This is a verification-and-documentation slice. Two new offline unit tests read the **packaged config templates** (`src/irc/templates/config/*.yaml`) through the existing `irc.commands.init_cmd._read_template` seam and assert the shipped values. The README memo-routing note is sharpened (additive). A short verdict file records that the look-through axis is already ON (no flag flip). No `src/irc/**` production module is modified, so outputs stay byte-stable (AC5).

**Tech Stack:** Python 3.12+, pytest, PyYAML (already a dependency, used by `config_loader`), `importlib.resources` (via the existing `_read_template` seam), Markdown docs.

---

## Background facts (verified against the working tree — do not re-derive)

These were confirmed during the grill pass; the plan depends on them being true. They were re-verified at plan-authoring time:

- `src/irc/templates/config/valuation_buckets.yaml` has `active_fund_lookthrough.enabled: true` and `coverage_floor: 0.50` (committed `cb1642d`, Phase D PR2, PR #111).
- `src/irc/templates/config/llm.yaml` routes `memo_synthesis → {provider: openrouter, model: anthropic/claude-opus-4.7}` and `memo_audit → {provider: openrouter, model: anthropic/claude-sonnet-4.6}`.
- The read seam: `from irc.commands.init_cmd import _read_template` — `_read_template("config/llm.yaml")` returns the packaged template text; pass it through `yaml.safe_load`. Verified: `_read_template("config/valuation_buckets.yaml")` → `enabled: True, coverage_floor: 0.5`.
- `config/` is gitignored (`.gitignore:23`); the runtime `config/llm.yaml` on this machine routes memo to `deepseek-reasoner` — that is a machine-local override, NOT the shipped contract.
- `README.md:36` already describes the OpenRouter routing. CONTEXT.md already has the "Config: packaged template vs runtime" section (3 terms, committed `4edd5c1` during grill). **Do not re-add CONTEXT terms.**
- `_FILENAME_TO_SCHEMA` (`config_loader.py:19`) includes both `config/llm.yaml` and `config/valuation_buckets.yaml`, so both are members of `TEMPLATE_FILES` and resolvable by `_read_template`.

## Non-goals (do NOT do these — from spec §Non-goals)

- Do NOT change `active_fund_lookthrough.enabled` (already `true`) or `coverage_floor` (settled at `0.50`).
- Do NOT enable / stub / fabricate the consensus-upside axis (`consensus_upside_pct`, `target_price`) — forbidden by ADR 0009.
- Do NOT edit the runtime `config/llm.yaml` or `config/valuation_buckets.yaml` (gitignored, machine-local).
- Do NOT modify any `src/irc/**` production module (`classify_valuation`, `compose_opportunity_state`, `populate_inputs`, look-through aggregation, memo synth/audit, `derive_position_risk_level`, index/sector phases A/B/C).
- Do NOT create a new ADR (ADR 0012's 2026-06-05 addendum already records the axis-ON decision).
- Do NOT re-add CONTEXT.md terms (already present from the grill commit).
- Do NOT bump `VERSION`.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `tests/templates/__init__.py` | Create | Make `tests/templates/` a package (mirrors the new `src/irc/templates/config` surface under test). |
| `tests/templates/test_valuation_buckets_template.py` | Create | AC2 — assert packaged `valuation_buckets.yaml` has `enabled is True` and `coverage_floor == 0.50`. |
| `tests/templates/test_llm_template.py` | Create | AC3 — assert packaged `llm.yaml` routes `memo_synthesis`/`memo_audit` to `provider: openrouter` with `anthropic/...` model ids. |
| `README.md` | Modify | AC4/AC6 — sharpen the memo-routing note to name the packaged-template-vs-runtime distinction. |
| `CHANGELOG.md` | Modify | AC7-adjacent — `[Unreleased]` entry (user-visible doc/lock change). |
| `docs/2026-06-10-actionable-ops/items/003-verdict.md` | Create | AC1 — record that the axis is already ON (no flip) and the consensus-upside axis stays dormant per ADR 0009. |

All new tests are offline, pure-read, no network, no LLM, no mocks.

---

### Task 1: AC2 — lock the packaged `valuation_buckets.yaml` axis-ON state

**Files:**
- Create: `tests/templates/__init__.py`
- Create: `tests/templates/test_valuation_buckets_template.py`

- [ ] **Step 1: Create the test package marker**

Create `tests/templates/__init__.py` with empty content:

```python
```

(An empty file — zero bytes. This makes `tests/templates/` importable, mirroring the other test subpackages.)

- [ ] **Step 2: Write the failing test**

Create `tests/templates/test_valuation_buckets_template.py`:

```python
from __future__ import annotations

import yaml

from irc.commands.init_cmd import _read_template


def _packaged_valuation_buckets() -> dict:
    """Parse the shipped packaged template (the shipped contract, never the runtime copy)."""
    return yaml.safe_load(_read_template("config/valuation_buckets.yaml"))


def test_lookthrough_axis_is_enabled_in_packaged_template() -> None:
    # Phase D PR2 (commit cb1642d, PR #111): the active-fund look-through axis ships ON.
    cfg = _packaged_valuation_buckets()
    assert cfg["active_fund_lookthrough"]["enabled"] is True


def test_lookthrough_coverage_floor_is_half_in_packaged_template() -> None:
    # gate-#5 decision (ADR 0012 addendum 2026-06-05): coverage_floor settled at 0.50.
    cfg = _packaged_valuation_buckets()
    assert cfg["active_fund_lookthrough"]["coverage_floor"] == 0.50
```

- [ ] **Step 3: Run the test to confirm it passes for the right reason**

This test asserts an already-true shipped value, so it will PASS on first run. To prove it is actually exercising the contract (not vacuously passing), first confirm it is collected and green:

Run: `uv run pytest tests/templates/test_valuation_buckets_template.py -v`
Expected: `2 passed` — both `test_lookthrough_axis_is_enabled_in_packaged_template` and `test_lookthrough_coverage_floor_is_half_in_packaged_template` PASS.

- [ ] **Step 4: Prove the regression-lock bites (temporary mutation check — DO NOT COMMIT this mutation)**

Temporarily flip the packaged template to confirm the test would catch a regression. Edit `src/irc/templates/config/valuation_buckets.yaml` line 9 from `enabled: true` to `enabled: false`, then:

Run: `uv run pytest tests/templates/test_valuation_buckets_template.py -v`
Expected: `test_lookthrough_axis_is_enabled_in_packaged_template` FAILS with `assert False is True`.

Then **revert the mutation** (restore `enabled: true`):

Run: `git checkout -- src/irc/templates/config/valuation_buckets.yaml`
Run: `uv run pytest tests/templates/test_valuation_buckets_template.py -v`
Expected: `2 passed` again, and `git status` shows `src/irc/templates/config/valuation_buckets.yaml` is NOT modified.

- [ ] **Step 5: Commit**

```bash
git add tests/templates/__init__.py tests/templates/test_valuation_buckets_template.py
git commit -m "test(item-003): lock packaged valuation_buckets axis-ON (enabled+floor) against regression (AC2)"
```

---

### Task 2: AC3 — lock the packaged `llm.yaml` memo→OpenRouter routing

**Files:**
- Create: `tests/templates/test_llm_template.py`

- [ ] **Step 1: Write the failing test**

Create `tests/templates/test_llm_template.py`:

```python
from __future__ import annotations

import yaml

from irc.commands.init_cmd import _read_template


def _packaged_llm_tasks() -> dict:
    """Parse the shipped packaged llm.yaml task routing (the shipped contract)."""
    return yaml.safe_load(_read_template("config/llm.yaml"))["tasks"]


def test_memo_synthesis_routes_to_openrouter_anthropic() -> None:
    # Memo LLM routing (shipped default): memo_synthesis -> OpenRouter Anthropic.
    route = _packaged_llm_tasks()["memo_synthesis"]
    assert route["provider"] == "openrouter"
    assert route["model"].startswith("anthropic/")


def test_memo_audit_routes_to_openrouter_anthropic() -> None:
    # Memo LLM routing (shipped default): memo_audit -> OpenRouter Anthropic.
    route = _packaged_llm_tasks()["memo_audit"]
    assert route["provider"] == "openrouter"
    assert route["model"].startswith("anthropic/")
```

- [ ] **Step 2: Run the test to confirm it passes for the right reason**

Run: `uv run pytest tests/templates/test_llm_template.py -v`
Expected: `2 passed` — `test_memo_synthesis_routes_to_openrouter_anthropic` and `test_memo_audit_routes_to_openrouter_anthropic` PASS.

- [ ] **Step 3: Prove the regression-lock bites (temporary mutation check — DO NOT COMMIT this mutation)**

Temporarily edit `src/irc/templates/config/llm.yaml` line 19, changing `memo_synthesis` provider to `deepseek` and model to `deepseek-reasoner` (simulating the machine-local override leaking into the shipped contract), then:

Run: `uv run pytest tests/templates/test_llm_template.py -v`
Expected: `test_memo_synthesis_routes_to_openrouter_anthropic` FAILS with `assert 'deepseek' == 'openrouter'`.

Then **revert the mutation**:

Run: `git checkout -- src/irc/templates/config/llm.yaml`
Run: `uv run pytest tests/templates/test_llm_template.py -v`
Expected: `2 passed` again, and `git status` shows `src/irc/templates/config/llm.yaml` is NOT modified.

- [ ] **Step 4: Commit**

```bash
git add tests/templates/test_llm_template.py
git commit -m "test(item-003): lock packaged llm.yaml memo->OpenRouter-Anthropic routing (AC3)"
```

---

### Task 3: AC4 / AC6 — disambiguate the README memo-routing note

**Files:**
- Modify: `README.md:36` (the `OPENROUTER_API_KEY` table row)

The current line 36 reads:

```
| `OPENROUTER_API_KEY` | Required by default memo routes | `config/llm.yaml` routes `memo_synthesis` and `memo_audit` through OpenRouter Anthropic models. Re-route those tasks if you want a DeepSeek-only setup. |
```

It is already correct in direction (OpenRouter is the default), but it does not name the packaged-template-vs-runtime distinction, leaving room to re-derive the false "README says OpenRouter but config says DeepSeek" claim (AC6). The edit makes that distinction explicit and additive.

- [ ] **Step 1: Read the current README row to anchor the edit**

Run: `grep -n "OPENROUTER_API_KEY" README.md`
Expected: line `36` matches the row shown above.

- [ ] **Step 2: Replace the line 36 Notes cell with the disambiguated text**

Replace the exact existing line 36:

```
| `OPENROUTER_API_KEY` | Required by default memo routes | `config/llm.yaml` routes `memo_synthesis` and `memo_audit` through OpenRouter Anthropic models. Re-route those tasks if you want a DeepSeek-only setup. |
```

with:

```
| `OPENROUTER_API_KEY` | Required by default memo routes | Your `config/llm.yaml` is generated by `irc init` from the packaged template (`src/irc/templates/config/llm.yaml`) and is user-editable. The **shipped default** routes `memo_synthesis` (`anthropic/claude-opus-4.7`) and `memo_audit` (`anthropic/claude-sonnet-4.6`) through OpenRouter Anthropic models — so a fresh install needs this key. Re-routing both memo tasks to a DeepSeek-only setup (e.g. `deepseek-reasoner`) is a supported local edit to your `config/llm.yaml`; it does not change the shipped default. |
```

- [ ] **Step 3: Verify the edit landed and the table is still well-formed**

Run: `grep -n "shipped default" README.md`
Expected: one match on line `36` containing `The **shipped default** routes`.

Run: `grep -c "deepseek-reasoner" README.md`
Expected: count includes the new occurrence (the README already references `deepseek-reasoner`/Tushare on line 41 for `TUSHARE_TOKEN`; the new line adds one more, so the count increases by 1 vs the pre-edit count). Confirm the new line frames it as a "supported local edit", not the default.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(item-003): disambiguate README memo routing (packaged template vs runtime config) (AC4/AC6)"
```

---

### Task 4: AC1 — record the axis-already-ON verdict (no flag flip)

**Files:**
- Create: `docs/2026-06-10-actionable-ops/items/003-verdict.md`

- [ ] **Step 1: Write the verdict file**

Create `docs/2026-06-10-actionable-ops/items/003-verdict.md`:

```markdown
# Item 003 — Verdict: axis already ON, no flip performed

**Run:** `docs/2026-06-10-actionable-ops` · **Item:** 003 · **Date:** 2026-06-10
**Outcome:** verification + regression-lock + documentation. No production code-path change.

## Valuation axis state (AC1)

- **Phase D active-fund look-through axis is already `enabled: true`** in the packaged
  template `src/irc/templates/config/valuation_buckets.yaml`
  (`active_fund_lookthrough.enabled: true`, `coverage_floor: 0.50`), committed `cb1642d`
  (Phase D PR2, PR #111, 2026-06-05; gate #5 signed off, ADR 0012 addendum 2026-06-05).
  **No flag flip was performed — there is nothing to flip.** This item only adds a
  regression test (`tests/templates/test_valuation_buckets_template.py`) pinning the
  shipped value so it cannot silently regress.
- **The consensus-upside axis (`consensus_upside_pct` → `valuation_fundamental_signal`)
  stays `None` by the ADR 0009 contract.** Lighting it up requires an out-of-scope
  target-price source (Tushare) and would violate the recorded degrade-to-`None`
  decision. Left dormant by design; out of scope for this item.

## Memo routing (AC3/AC4)

- The packaged template `src/irc/templates/config/llm.yaml` routes `memo_synthesis` and
  `memo_audit` through OpenRouter Anthropic models (the **Memo LLM routing (shipped
  default)**, CONTEXT.md). README already described this; this item sharpened the note to
  name the packaged-template-vs-runtime-config distinction (CONTEXT.md "Config: packaged
  template vs runtime"). A `deepseek-reasoner` memo routing only ever arises from a
  machine-local **runtime config** override (`config/llm.yaml`, gitignored).

## Behavioural drift (AC5)

- No `src/irc/**` production module was modified. The new tests only *read* packaged
  templates and assert values; `OpportunityInput` is compute-only (never serialised).
  README / CHANGELOG / this verdict are docs. Therefore `valuation_state` and the
  opportunity-state distribution from `irc opportunity` / `irc decision` are unchanged.

## No new ADR

- The axis-ON decision (`enabled: true`, `coverage_floor: 0.50`, gate #5) is already
  durably recorded in ADR 0012's 2026-06-05 addendum. Per the grill (Q2), re-recording it
  fails the three-of-three ADR bar. This verdict is the verification record.
```

- [ ] **Step 2: Verify the file exists and is non-empty**

Run: `test -s docs/2026-06-10-actionable-ops/items/003-verdict.md && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add docs/2026-06-10-actionable-ops/items/003-verdict.md
git commit -m "docs(item-003): verdict — look-through axis already ON, no flip (AC1)"
```

---

### Task 5: CHANGELOG `[Unreleased]` entry

**Files:**
- Modify: `CHANGELOG.md` (insert a new `### Added` block immediately after the `## [Unreleased]` line, above the existing Phase A entry)

- [ ] **Step 1: Locate the `[Unreleased]` heading**

Run: `grep -n "## \[Unreleased\]" CHANGELOG.md`
Expected: one match (the section the new entry is inserted under).

- [ ] **Step 2: Insert the new entry**

Find this exact block in `CHANGELOG.md`:

```
## [Unreleased]

### Added — Phase A legulegu broad-leg rate-limit hardening (2026-06-08)
```

Replace it with:

```
## [Unreleased]

### Added — Valuation axis lock + memo-routing docs (2026-06-10)

- **Regression-locked the shipped valuation-axis and memo-routing contracts.** Two new
  offline unit tests (`tests/templates/test_valuation_buckets_template.py`,
  `tests/templates/test_llm_template.py`) pin the **packaged config templates**: the
  Phase D active-fund look-through axis ships `enabled: true` with `coverage_floor: 0.50`
  (PR #111 / gate #5), and `memo_synthesis`/`memo_audit` route through OpenRouter Anthropic
  models (the shipped default README documents). No production code path changed — the
  axis was already ON; nothing was flipped. The README memo-routing note now names the
  packaged-template-vs-runtime-config distinction so the shipped default cannot be misread
  as DeepSeek. The consensus-upside axis (`consensus_upside_pct`) stays dormant by the
  ADR 0009 degrade-to-`None` contract (out of scope to enable).

### Added — Phase A legulegu broad-leg rate-limit hardening (2026-06-08)
```

- [ ] **Step 3: Verify the entry landed and Phase A entry is preserved**

Run: `grep -n "Valuation axis lock\|Phase A legulegu broad-leg" CHANGELOG.md`
Expected: two matches — the new `Valuation axis lock + memo-routing docs (2026-06-10)` heading appears *before* the preserved `Phase A legulegu broad-leg rate-limit hardening (2026-06-08)` heading.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(item-003): CHANGELOG [Unreleased] — valuation axis lock + memo-routing docs"
```

---

### Task 6: AC7 — lint + targeted-suite verification + AC5 no-drift proof

**Files:** none (verification only).

- [ ] **Step 1: Lint the new tests (and src, unchanged)**

Run: `uv run ruff check src tests`
Expected: `All checks passed!` (or no output with exit 0). The new test files are line-length ≤100 and py312-clean.

- [ ] **Step 2: Run the full set of touched/new tests**

Run: `uv run pytest tests/templates/ -v`
Expected: `4 passed` — the two valuation-buckets tests and the two llm tests all PASS.

- [ ] **Step 3: AC5 — prove no production module was touched**

Run: `git diff --name-only main...HEAD -- 'src/irc/**'`
Expected: **empty output** (no `src/irc/**` production module modified — the look-through / memo / opportunity / decision code paths are untouched, so `valuation_state` and the opportunity-state distribution are byte-stable).

If output is non-empty, STOP — a production module was modified in violation of AC5/Non-goals; revert it before proceeding.

- [ ] **Step 4: Confirm gitignored runtime configs were NOT committed**

Run: `git diff --name-only main...HEAD -- 'config/'`
Expected: **empty output** (the gitignored runtime `config/*.yaml` must not appear in the branch diff).

- [ ] **Step 5: Confirm the full changed-file set matches the plan**

Run: `git diff --name-only main...HEAD`
Expected: exactly these six paths (order may vary):

```
CHANGELOG.md
README.md
docs/2026-06-10-actionable-ops/items/003-verdict.md
tests/templates/__init__.py
tests/templates/test_llm_template.py
tests/templates/test_valuation_buckets_template.py
```

If any other path appears, investigate before handing off.

---

## Self-Review (author checklist — completed)

**1. Spec coverage:**
- AC1 (axis-ON documented, not flipped) → Task 4 (verdict file).
- AC2 (template-flag regression test) → Task 1.
- AC3 (memo-routing regression test) → Task 2.
- AC4 (README disambiguation) → Task 3.
- AC5 (no behavioural drift) → Task 6 Step 3 (`git diff --name-only ... src/irc/**` empty).
- AC6 (doc consistency, README only; CONTEXT already done in grill) → Task 3 + the explicit "do not re-add CONTEXT terms" note.
- AC7 (suite green vs baseline; ruff clean) → Task 6 Steps 1–2.
- Non-goals (no flip, no axis B, no runtime-config edit, no src change, no new ADR, no VERSION bump) → enforced by the Non-goals block and Task 6 Steps 3–4.

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to" — every code and content block is literal.

**3. Type/name consistency:** Seam name `_read_template` and import path `irc.commands.init_cmd` match the verified source; YAML keys (`active_fund_lookthrough`, `enabled`, `coverage_floor`, `tasks`, `memo_synthesis`, `memo_audit`, `provider`, `model`) match the verified templates.

**Judgment calls made (cite section):**
- *AC3 model assertion strictness* — the spec (AC3) says "`anthropic/...` model ids" without pinning exact model strings. The test asserts `provider == "openrouter"` and `model.startswith("anthropic/")` rather than the literal `anthropic/claude-opus-4.7` / `anthropic/claude-sonnet-4.6`. Rationale: the load-bearing contract README documents is "OpenRouter Anthropic", and pinning exact patch model ids would make the lock brittle to a routine model bump (a separate, legitimate change) while still satisfying AC3's wording. The exact current model ids are recorded in the README (Task 3) and verdict (Task 4) for the human record.
- *TDD ordering for an already-true assertion (CLAUDE.md TDD rule)* — the project rule is "failing test first". For AC2/AC3 the asserted value already ships true, so a conventional red phase is impossible without mutating the shipped contract. The plan substitutes a **temporary-mutation regression-bite check** (Task 1 Step 4, Task 2 Step 3) that proves the test fails when the contract regresses, then reverts — satisfying the spirit of red→green (the test demonstrably distinguishes pass from fail) without committing a fake regression. This is the honest TDD shape for a regression-lock of an existing value.
- *CHANGELOG placement (spec §Constraints "CHANGELOG entry under [Unreleased] if user-visible")* — judged user-visible (README guidance + a shipped-contract lock), so an entry is added under `[Unreleased]` with no VERSION bump.
```
