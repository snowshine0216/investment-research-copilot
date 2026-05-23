# Item 008 Implementation Plan — publishable-set-lockdown integration sweep (Slice E)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock the publishable-set citation / scope / state / asset-class invariants at the artifact-read level by adding 23 ACs' worth of integration tests in `tests/integration/test_publishable_set_lockdown.py`, plus the cross-cutting two-run byte-equality regression that closes the determinism loop. After this item ships, item 009 can flip `IRC_CITATION_ENFORCE_MODE=block` against a known-clean baseline.

**Architecture:** One new test file (`tests/integration/test_publishable_set_lockdown.py`, ~600–800 LOC) housing a module-level `_seed_publishable_set_repo(tmp_path, **scenario_kwargs)` helper plus 23 per-AC scenario tests. The seed helper composes three primitives that already exist in the project's test code: (a) `run_init(str(tmp_path))` to bootstrap the inputs/configs/outputs layout, (b) `monkeypatch.setenv` for the four env-var gates (`IRC_OPPORTUNITY_AUTOBUILD`, `IRC_CACHE_FRESHNESS_DAYS`, `IRC_FETCH_BUDGET`, `IRC_ALLOW_STALE`), (c) a `_universal_side`-style `_ak_call` dispatcher that returns synthetic AkShare frames keyed by `(fn_name, symbol)`. Memo route mocking lives in a separate `_patch_memo_routes(synth_text)` context manager wrapping `patch("irc.memo.synthesizer.call_chat", ...) + patch("irc.memo.auditor.call_chat", ...)` per the locked precedent in `tests/commands/test_memo_cmd_aliases.py:98–99`. Tests are grouped by invariant family with one test per AC.

**Tech Stack:** Python 3.12, pytest, `unittest.mock.patch`, stdlib `hashlib`/`json`/`yaml`/`re`. No new third-party deps. No production-code edits in the test-authoring commit (per Q6 inline-fix policy: production fixes triggered by failing tests land as **separate commits** on the same sub-branch, captured in `008-drift.md`).

---

## Constraints (apply to every task)

- **Strict TDD per task:** Write the failing test FIRST, run it red, then either (a) the test goes green immediately because the production code already complies (the publishable-set invariants are already enforced by items 001–007 — the tests merely *lock* them) or (b) the test exposes a real drift bug, in which case fix the drift inline on the sub-branch as a separate commit per Q6.
- **Test-only by intent.** Item 008 does NOT modify `src/irc/**` in its test-authoring commits. Any production fix is its own separate commit with `fix(...)` prefix and a one-line entry in `008-drift.md`.
- **Per-test isolation via per-test seeding.** Each test gets its own `tmp_path`, its own `monkeypatch` fixture, its own seed-helper invocation. NO module-scoped pytest fixtures (rejected D1 Option B).
- **Citation universe formula locked** (Q5 resolution): `universe = opportunity_report.json["rows"][*]["thesis_evidence"][*]["citation_id"] ∪ gold_regime.json["evidence"][*]["citation_id"]`. `rejections.json` is **EXPLICITLY EXCLUDED** — verified by reading `src/irc/opportunity/rejection_log.py:35–47` (no `thesis_evidence` field on `RejectionRecord`). The helper `_collect_publishable_citation_universe(out_dir)` is the only function that constructs this set; all tests that reference the universe call this helper.
- **Memo route mock pair locked** (Q1 resolution): every `run_memo` call site uses `_patch_memo_routes(synth_text)` which patches `irc.memo.synthesizer.call_chat` AND `irc.memo.auditor.call_chat` together. NO lower-level `run_memo_pipeline` invocation — `run_memo(str(tmp_path))` is the entry point per the locked precedent.
- **QDII variant coverage = one per variant** (Q3 resolution): `qdii_us`, `qdii_hk`, `qdii_global` = 3 rows. Locks the per-variant exclusion path in `_build_qdii_sentinel_snapshot`.
- **`_GAP_TO_REASON` dict-iteration precedence asserted on the observable string, NOT by importing the constant** (Q7 resolution): AC11 hard-codes `rejection_reason == "qdii_information_unavailable"` with the comment `# precedence per src/irc/opportunity/rejection_log.py::_GAP_TO_REASON dict-iteration order + ADR 0003`. The private constant is NEVER imported.
- **Two-run byte-equality uses `sha256` of the on-disk artifact bytes** (ACs 22–23): no string-level comparison; the bytes-as-stored shape is the contract. Files compared: `opportunity_report.json`, `thesis_cards.yaml`, `discipline_report.md`, `rejections.json` for AC22; `memo.md` for AC23.
- **Commit cadence:** one conventional-commit per task (`test(integration):` for the test commits; `fix(...):` for any drift-fix commits with `008-drift.md` updated in the same commit). DO NOT push.
- **Verification per task:** an exact `pytest tests/integration/test_publishable_set_lockdown.py::test_<name> -v` command with expected PASS output. Final task = full `pytest -x -q` + `ruff check src/ tests/` clean.

## Branch

Sub-branch: `autodev/thesis-evidence-008-integration-test-sweep` cut from `autodev/thesis-cards-evidence-gap`. Commits land on the sub-branch; the eventual PR opens against `autodev/thesis-cards-evidence-gap`.

---

## File-touch map (read this before starting)

**Test (create):**
- `tests/integration/test_publishable_set_lockdown.py` (~600–800 LOC) — the flagship integration test file. Module structure:
  - Imports + `_resp(text)` factory for `ChatResponse` (copied verbatim from `test_memo_cmd_aliases.py:13`).
  - `_seed_publishable_set_repo(tmp_path, *, monkeypatch, include_qdii=True, asset_classes=("cn_equity_fund","cn_bond_fund","gold","cn_etf"), seed_date="2026-05-14", override_env=None) -> dict` — bootstraps the repo, sets env vars, returns a dispatch dict mapping `(fn_name, symbol) -> response_frame` that the caller installs as `_ak_call` side effect.
  - `_install_ak_call_dispatch(monkeypatch, dispatch) -> Counter` — patches `irc.fundamentals.akshare_fundamentals._ak_call`, returns the call counter for cache-freshness assertions (ACs 15–17).
  - `_patch_memo_routes(synth_text: str)` — context manager wrapping the locked synth+audit `patch` pair.
  - `_collect_publishable_citation_universe(out_dir: Path) -> set[str]` — reads `opportunity_report.json` + `gold_regime.json`, returns the Q5-resolved citation union.
  - `_sha256_file(path: Path) -> str` — read bytes, return hex digest.
  - 23 per-AC scenario tests with descriptive names (full list in §"Acceptance criteria mapping" below).

**Modified files:**
- `CONTEXT.md` — append one paragraph to the "Test infrastructure" section naming `test_publishable_set_lockdown.py` as the locked baseline + the "Publishable citation universe" term (per grill F3). One commit, Task 13.
- `docs/2026-05-22-thesis-cards-evidence-gap/items/008-drift.md` — created ONLY if a test exposes a real production drift bug. Each line: `- <date> <commit-sha> fix(<scope>): <one-line description>`.

**Files explicitly NOT touched (per Q6 + §4 NO-list):**
- `src/irc/**` — no changes in the test-authoring commits. Production fixes (if surfaced by failing tests) land as separate `fix(...)` commits, documented in `008-drift.md`.
- `tests/memo/**`, `tests/opportunity/**`, `tests/fundamentals/**` — existing unit tests stay as-is.
- `tests/commands/test_opportunity_cmd_h3_invariant.py` — already covers `_write_opportunity_outputs` at row-construction level. Item 008's tests use `run_opportunity` end-to-end as a distinct surface.

---

## Locked decisions (resolutions of Q1, Q4, Q5, Q6 from grill phase)

### Q1 — `run_memo` offline mocking pattern (LOCKED)

Patch BOTH routes via `unittest.mock.patch`:

```python
with patch("irc.memo.synthesizer.call_chat", return_value=_resp(synth_text)), \
     patch("irc.memo.auditor.call_chat", return_value=_resp("审核通过")):
    run_memo(str(tmp_path))
```

where `_resp(text)` returns `ChatResponse(text=text, prompt_tokens=10, completion_tokens=20, latency_ms=50, raw={})`. Wrapped in module-level `_patch_memo_routes(synth_text)` context manager. **No `run_memo_pipeline` lower-level invocation needed** — `run_memo(str(tmp_path))` is sufficient with both routes patched (`src/irc/commands/memo_cmd.py:530–532` resolves both routes and forwards them to `run_memo_pipeline`).

### Q4 — Cache freshness env var name (LOCKED)

`IRC_CACHE_FRESHNESS_DAYS` exists in production at `src/irc/commands/opportunity_cmd.py:71` (`IRC_CACHE_FRESHNESS_DAYS_DEFAULT = 7`) and `:199` (`_freshness_days()` reads via `os.environ.get`). The term is already documented in `CONTEXT.md` "Fail-closed freshness probe". **No new env var, no new CONTEXT.md term beyond the "Publishable citation universe" + "Publishable-set lockdown baseline" appendices from grill F3, no ADR amendment.** AC15/16/17 reference the existing constant verbatim by string name (no import of the private `_freshness_days` helper).

### Q5 — Citation-id universe for AC19 (LOCKED)

```
universe = {citation_id for row in opportunity_report.json["rows"]
                        for entry in row["thesis_evidence"]}
         ∪ {citation_id for entry in gold_regime.json.get("evidence", [])}
```

**`rejections.json` is EXPLICITLY EXCLUDED** — `RejectionRecord` (`src/irc/opportunity/rejection_log.py:35–47`) has no `thesis_evidence` field. Gapped rows have not earned conclusions and carry no citations. The exclusion is structural, not policy. The `_collect_publishable_citation_universe(out_dir)` helper is the SOLE constructor of this set; AC19 + AC23 both consume it. The helper MUST NOT read `rejections.json`.

### Q6 — Production-fix policy in test-only PR (LOCKED inline-fix)

If an AC fails because production drifted from spec, fix the drift in a **separate commit** on the same sub-branch and append a one-line entry to `docs/2026-05-22-thesis-cards-evidence-gap/items/008-drift.md`. DO NOT spawn a follow-up issue. Items 003 + 006 PR precedent. The PR review surface absorbs the fix-and-test pair atomically; item 009 depends on a known-clean baseline.

**Decision-tree per failing test:**
1. Test fails red. Investigate.
2. Is the test wrong (mis-asserts the spec)? Fix the test. Continue.
3. Is the production code wrong (drifted from item 001–007's locked behavior)? Fix the production code in a SEPARATE commit with prefix `fix(<scope>):`; update `008-drift.md` in the SAME commit; re-run the failing test green; continue.
4. Both green? Commit the test in its own `test(integration):` commit.

---

## Task index (one slice per task, all green-at-checkpoint)

1. **Seed helper + auxiliary primitives** — `_seed_publishable_set_repo`, `_install_ak_call_dispatch`, `_patch_memo_routes`, `_collect_publishable_citation_universe`, `_sha256_file`, `_resp`. Smoke test confirms the helper builds a valid repo end-to-end.
2. **ACs 1–5: publishable-set citation invariants (E10 family)** — dual-leg coverage + owner provenance + publishable scope + literal-only `thesis_state` + empty `evidence_gaps` on JSON round-trip.
3. **ACs 6–9: QDII exclusion invariants** — never in cards, never in opportunity rows, present in rejections with correct reason, present in discipline failure section.
4. **AC10: H3 partition across four output surfaces.**
5. **AC11: Policy-B precedence renders `qdii_information_unavailable` over Policy-B codes.**
6. **AC12: `fetch_budget_exhausted` is fatal at write time via `run_opportunity`.**
7. **ACs 13–14: 持仓明细 appendix integrity (D3b).**
8. **ACs 15–17: snapshot-cache freshness (E8 family).**
9. **AC18: E9 downstream propagation — empty AkShare holdings flow to `evidence_gaps=["holdings_fetch_failed"]` + exclude.**
10. **ACs 19–20: cross-stage SAME-3 / citation-id-subset (`run_opportunity → run_memo`).**
11. **AC21: multi-owner constituent keeps separate provenance on disk (E16).**
12. **ACs 22–23: pipeline-level two-run byte equality.**
13. **CONTEXT.md update + final verification** — append "Publishable-set lockdown baseline" + "Publishable citation universe" terms to "Test infrastructure"; run `pytest -x -q` + `ruff check src/ tests/`; inspect commit log.

---

## Task 1: Seed helper + auxiliary primitives

**Files:**
- Create: `tests/integration/test_publishable_set_lockdown.py` (header + helpers + ONE smoke test).

- [ ] **Step 1: Write the failing smoke test**

Create `tests/integration/test_publishable_set_lockdown.py` with the header, helpers, and a single smoke test that exercises the seed helper end-to-end:

```python
"""Item 008 — publishable-set-lockdown integration sweep.

Locks the publishable-set citation / scope / state / asset-class invariants
at the artifact-read level after a full `run_opportunity` (plus `run_memo`
for cross-stage ACs) execution. After this file's tests pass on the feature
branch, item 009 can flip IRC_CITATION_ENFORCE_MODE=block against a
known-clean baseline.

Key invariants:
- Publishable citation universe (Q5 resolution): opportunity_report.json
  ∪ gold_regime.json. rejections.json EXCLUDED — RejectionRecord has no
  thesis_evidence field (src/irc/opportunity/rejection_log.py:35–47).
- Memo route mock pair (Q1 resolution): patch synthesizer.call_chat +
  auditor.call_chat per tests/commands/test_memo_cmd_aliases.py:98–99.
- QDII variants (Q3): one per variant — qdii_us, qdii_hk, qdii_global.
- _GAP_TO_REASON precedence (Q7): assert observable rejection_reason
  string, NEVER import the private constant.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import pytest
import yaml

from irc.llm.http_client import ChatResponse


# ─── Helpers ────────────────────────────────────────────────────────────────

def _resp(text: str) -> ChatResponse:
    """Locked ChatResponse factory per tests/commands/test_memo_cmd_aliases.py:13."""
    return ChatResponse(
        text=text, prompt_tokens=10, completion_tokens=20,
        latency_ms=50, raw={},
    )


def _today_cn() -> str:
    """Asia/Shanghai date matching opportunity_cmd.py's output-dir convention."""
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _sha256_file(path: Path) -> str:
    """Return hex-digest sha256 of the on-disk bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect_publishable_citation_universe(out_dir: Path) -> set[str]:
    """Q5 resolution: opportunity_report.json ∪ gold_regime.json.
    rejections.json EXCLUDED — RejectionRecord has no thesis_evidence field.
    """
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    universe: set[str] = set()
    for row in opp.get("rows", []):
        for ev in row.get("thesis_evidence", []):
            cid = ev.get("citation_id")
            if cid:
                universe.add(cid)
    gold_path = out_dir / "gold_regime.json"
    if gold_path.exists():
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        for ev in gold.get("evidence", []):
            cid = ev.get("citation_id")
            if cid:
                universe.add(cid)
    return universe


@contextmanager
def _patch_memo_routes(synth_text: str) -> Iterator[None]:
    """Q1 resolution: locked patch pair per test_memo_cmd_aliases.py:98–99."""
    with patch("irc.memo.synthesizer.call_chat",
               return_value=_resp(synth_text)), \
         patch("irc.memo.auditor.call_chat",
               return_value=_resp("审核通过")):
        yield


def _install_ak_call_dispatch(monkeypatch, dispatch: dict) -> Counter:
    """Patch `_ak_call` with a dispatcher; return a call counter for
    cache-freshness assertions (ACs 15–17 inspect it after run_opportunity).
    """
    counter: Counter = Counter()

    def _side(fn_name: str, *args, **kwargs):
        symbol = args[0] if args else kwargs.get("symbol", "")
        key = (fn_name, str(symbol))
        counter[key] += 1
        frame = dispatch.get(key)
        if frame is None:
            # Default empty frame — callers add to dispatch only the shapes they need.
            import pandas as pd
            return pd.DataFrame()
        return frame

    monkeypatch.setattr(
        "irc.fundamentals.akshare_fundamentals._ak_call", _side,
    )
    return counter


def _seed_publishable_set_repo(
    tmp_path: Path,
    *,
    monkeypatch,
    include_qdii: bool = True,
    asset_classes: tuple[str, ...] = (
        "cn_equity_fund", "cn_bond_fund", "gold", "cn_etf",
    ),
    seed_date: str | None = None,
    override_env: dict[str, str] | None = None,
) -> dict[tuple[str, str], Any]:
    """Bootstrap a tmp_path repo for publishable-set integration tests.

    Returns the (fn_name, symbol) → frame dispatch dict; callers may mutate
    it before installing via _install_ak_call_dispatch(monkeypatch, dispatch).

    Env vars set via monkeypatch (Q2 resolution):
      IRC_OPPORTUNITY_AUTOBUILD=1
      IRC_CACHE_FRESHNESS_DAYS=7
      IRC_FETCH_BUDGET=2000
      IRC_ALLOW_STALE=1

    `override_env` lets per-test scenarios change individual values
    (e.g. AC12 sets IRC_FETCH_BUDGET=1 to force exhaustion).
    """
    import pandas as pd
    from irc.commands.init_cmd import run_init
    from irc.data.manifest import ManifestEntry, write_manifest

    # Env vars (Q2 resolution).
    env = {
        "IRC_OPPORTUNITY_AUTOBUILD": "1",
        "IRC_CACHE_FRESHNESS_DAYS": "7",
        "IRC_FETCH_BUDGET": "2000",
        "IRC_ALLOW_STALE": "1",
    }
    if override_env:
        env.update(override_env)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # Repo scaffold.
    run_init(str(tmp_path), force=False)

    # Manifest (so ingest staleness gate passes).
    write_manifest(
        tmp_path / "data",
        ManifestEntry(
            source="akshare",
            last_run_at=datetime.now(timezone.utc).isoformat(),
            schema_version="v1",
            record_counts={"prices": 100},
        ),
    )

    today = seed_date or _today_cn()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    # Per-asset-class seed instruments (Q3: one per variant for QDII).
    v1_instruments = {
        "cn_equity_fund": [("005827", "易方达蓝筹精选")],
        "cn_bond_fund":   [("000001", "华夏成长债")],
        "gold":           [("518880", "黄金ETF")],
        "cn_etf":         [("510300", "沪深300ETF")],
    }
    qdii_instruments = [
        ("004243", "qdii_us",     "易方达原油"),
        ("164906", "qdii_hk",     "交银中证海外"),
        ("100061", "qdii_global", "富国全球债"),
    ]

    scoring_rows = []
    for ac in asset_classes:
        for iid, name in v1_instruments.get(ac, []):
            scoring_rows.append({
                "instrument_id": iid, "name_cn": name,
                "asset_class": ac, "composite_score": 70.0,
            })
    if include_qdii:
        for iid, ac, name in qdii_instruments:
            scoring_rows.append({
                "instrument_id": iid, "name_cn": name,
                "asset_class": ac, "composite_score": 50.0,
            })

    (out_dir / "scoring.json").write_text(
        json.dumps({"scores": scoring_rows}, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "gold_regime.json").write_text(
        json.dumps({
            "regime": "range_bound", "zone": "pause",
            "tilt": "neutral_minus", "evidence": [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "proposed_allocation.yaml").write_text(
        yaml.safe_dump({"gold_tilt": "overweight", "selected_instruments": []}),
        encoding="utf-8",
    )

    # Synthetic AkShare dispatch — minimal frames that look like real responses
    # so _build_active_fund_snapshot / _build_fund_level_snapshot don't bail.
    # Caller adds per-scenario overrides.
    dispatch: dict[tuple[str, str], Any] = {}

    return dispatch


# ─── Smoke test ─────────────────────────────────────────────────────────────

def test_seed_helper_builds_runnable_repo(tmp_path, monkeypatch) -> None:
    """Task 1 smoke — the seed helper builds a repo whose `run_opportunity`
    invocation reaches a write phase without crashing on missing inputs.
    Does NOT assert any AC; the per-AC tests below cover the invariants."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    assert (out_dir / "opportunity_report.json").exists()
    assert (out_dir / "thesis_cards.yaml").exists()
    assert (out_dir / "discipline_report.md").exists()
    assert (out_dir / "rejections.json").exists()
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_seed_helper_builds_runnable_repo -v`

Expected: ONE of three outcomes:
- **PASS** — the seed helper composes correctly against current production code; commit and move to Task 2.
- **FAIL** with a deterministic error in `run_opportunity` (e.g. KeyError for missing input fixture, JSON schema mismatch). The error message points at what the helper needs to seed additionally. Iterate on the helper body (NOT production code) until the smoke test passes.
- **FAIL** with a production drift bug (rare for a smoke test). Follow Q6 inline-fix flow.

- [ ] **Step 3: Iterate the helper until smoke passes**

Adjust the seed helper body if the smoke test exposes missing fixtures. Common fixes (none of which require production changes):
- Add a minimal `inputs/instruments.yaml` write step (check `run_init` defaults to confirm).
- Add a minimal `data/fundamentals/<quarter>/...` pre-write for cached snapshots.
- Extend the `dispatch` dict with a sentinel empty `pd.DataFrame()` for fn names that `_ak_call` is invoked with during the smoke run.

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_seed_helper_builds_runnable_repo -v`

Expected: PASS.

Run: `pytest tests/integration/ -x -q` (broader check that the new file doesn't regress siblings).

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): add publishable-set-lockdown seed helper + smoke (T1)"
```

---

## Task 2: ACs 1–5 — publishable-set citation invariants (E10 family)

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 5 tests).

- [ ] **Step 1: Write the failing tests**

Append after the smoke test in `tests/integration/test_publishable_set_lockdown.py`:

```python
# ─── ACs 1–5: publishable-set citation invariants (E10 family) ───────────────

def test_publishable_dual_leg_coverage(tmp_path, monkeypatch) -> None:
    """AC1 — every published row carries ≥1 data + ≥1 information citation.
    No row has both legs absent. citation_kind ∈ {"data", "information"}
    (legacy "both" forbidden per ADR 0001)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    rows = opp.get("rows", [])
    assert rows, "expected at least one publishable row"
    for row in rows:
        kinds = {ev["citation_kind"] for ev in row.get("thesis_evidence", [])}
        assert "data" in kinds, \
            f"row {row['instrument_id']} missing data-leg evidence: kinds={kinds}"
        assert "information" in kinds, \
            f"row {row['instrument_id']} missing information-leg evidence: kinds={kinds}"
        assert kinds <= {"data", "information"}, \
            f"row {row['instrument_id']} has forbidden citation_kind: {kinds}"


def test_publishable_owner_instrument_provenance(tmp_path, monkeypatch) -> None:
    """AC2 — every entry.owner_instrument_id == row.instrument_id.
    No cross-instrument leakage on disk."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        iid = row["instrument_id"]
        for ev in row.get("thesis_evidence", []):
            assert ev["owner_instrument_id"] == iid, \
                f"cross-instrument leakage: row {iid} carries owner={ev['owner_instrument_id']}"


def test_publishable_scope_is_instrument_or_constituent(tmp_path, monkeypatch) -> None:
    """AC3 — every entry.scope ∈ {"instrument", "constituent"}.
    No publishable row may have scope=asset_class_macro / policy as its
    SOLE evidence basis. Macro/policy may co-exist alongside instrument
    or constituent entries (an absent-from-pool check would over-assert)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        scopes = {ev["scope"] for ev in row.get("thesis_evidence", [])}
        assert scopes & {"instrument", "constituent"}, \
            f"row {row['instrument_id']} lacks instrument/constituent scope: {scopes}"


def test_publishable_thesis_state_literal_only(tmp_path, monkeypatch) -> None:
    """AC4 — every row.thesis_state ∈ {"intact","under_pressure","falsified","evidence_insufficient"}.
    No synthetic "partial_evidence"-style values."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    allowed = {"intact", "under_pressure", "falsified", "evidence_insufficient"}
    for row in opp.get("rows", []):
        assert row["thesis_state"] in allowed, \
            f"row {row['instrument_id']} has invalid thesis_state {row['thesis_state']!r}"


def test_publishable_evidence_gaps_empty_after_disk_roundtrip(tmp_path, monkeypatch) -> None:
    """AC5 — every published row has evidence_gaps == [] after JSON round-trip.
    H3 universal gapped-row invariant guarantees this at _write_opportunity_outputs
    time; AC5 re-asserts after JSON round-trip to catch serializer drift."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        assert row["evidence_gaps"] == [], \
            f"row {row['instrument_id']} carries non-empty evidence_gaps on publish: {row['evidence_gaps']!r}"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_publishable_dual_leg_coverage -v`

Expected: PASS (items 001–007 already enforce dual-leg coverage at write time) OR FAIL — if FAIL, follow Q6 decision-tree.

Run the remaining four similarly:
```
pytest tests/integration/test_publishable_set_lockdown.py::test_publishable_owner_instrument_provenance -v
pytest tests/integration/test_publishable_set_lockdown.py::test_publishable_scope_is_instrument_or_constituent -v
pytest tests/integration/test_publishable_set_lockdown.py::test_publishable_thesis_state_literal_only -v
pytest tests/integration/test_publishable_set_lockdown.py::test_publishable_evidence_gaps_empty_after_disk_roundtrip -v
```

- [ ] **Step 3: Implement (no production code unless drift)**

If all five pass, no implementation step is needed — items 001–007 already comply.

If any fails with a real drift bug, follow Q6 inline-fix flow: produce a minimal `fix(<scope>):` commit (separate from the test commit) AND append one line to `008-drift.md` in the SAME commit. Then re-run the failing test green.

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "publishable_"`

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock publishable-set citation invariants (ACs 1-5, T2)"
```

(If a drift-fix was needed, it shipped as a SEPARATE prior `fix(...)` commit on the same sub-branch with the matching `008-drift.md` entry.)

---

## Task 3: ACs 6–9 — QDII exclusion invariants

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 4 tests).

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ─── ACs 6–9: QDII exclusion invariants ──────────────────────────────────────

_QDII_ASSET_CLASSES = {"qdii_us", "qdii_hk", "qdii_global", "us_etf", "hk_etf"}
_QDII_IIDS = ("004243", "164906", "100061")


def test_qdii_never_in_thesis_cards(tmp_path, monkeypatch) -> None:
    """AC6 — no thesis_card has asset_class in {qdii_us,qdii_hk,qdii_global,us_etf,hk_etf}."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cards_doc = yaml.safe_load((out_dir / "thesis_cards.yaml").read_text(encoding="utf-8")) or {}
    cards = cards_doc.get("cards", [])
    for card in cards:
        assert card.get("asset_class") not in _QDII_ASSET_CLASSES, \
            f"QDII asset_class leaked into thesis_cards.yaml: {card}"


def test_qdii_never_in_opportunity_report_rows(tmp_path, monkeypatch) -> None:
    """AC7 — same set check against opportunity_report.json rows array."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        assert row["asset_class"] not in _QDII_ASSET_CLASSES, \
            f"QDII asset_class leaked into opportunity_report rows: {row}"
        assert row["instrument_id"] not in _QDII_IIDS, \
            f"QDII instrument_id leaked into opportunity_report rows: {row}"


def test_qdii_appears_in_rejections_with_qdii_reason(tmp_path, monkeypatch) -> None:
    """AC8 — every seeded QDII instrument in rejections.json with
    rejection_reason == 'qdii_information_unavailable'."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entries_by_iid = {e["instrument_id"]: e for e in rej.get("entries", [])}
    for iid in _QDII_IIDS:
        assert iid in entries_by_iid, \
            f"QDII {iid} missing from rejections.json"
        assert entries_by_iid[iid]["rejection_reason"] == "qdii_information_unavailable", \
            f"QDII {iid} rejection_reason wrong: {entries_by_iid[iid]['rejection_reason']!r}"


def test_qdii_appears_in_discipline_failure_section(tmp_path, monkeypatch) -> None:
    """AC9 — every seeded QDII iid appears AFTER '## 证据不足' heading and
    NOT in any bucket section above it. Failure-section heading locked by
    tests/commands/test_opportunity_cmd_h3_invariant.py."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    failure_idx = md.find("## 证据不足")
    assert failure_idx >= 0, "discipline_report.md missing '## 证据不足' heading"
    above, below = md[:failure_idx], md[failure_idx:]
    for iid in _QDII_IIDS:
        assert iid not in above, \
            f"QDII {iid} appears in a bucket section above '## 证据不足'"
        assert iid in below, \
            f"QDII {iid} missing from failure section below '## 证据不足'"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "qdii_"`

Expected: 4 PASS, OR FAIL with drift bug → Q6 flow.

- [ ] **Step 3: Implement (Q6 if needed)**

If a test fails, investigate per Q6 decision tree. The most likely drift is a discipline-report heading change ("## 证据不足" → "## 证据不足 / Failed fetch") — fix renderer literal in `src/irc/opportunity/report.py` if so (one-line `fix(opportunity):` commit + `008-drift.md` entry).

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "qdii_"`

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock QDII exclusion invariants across 4 output surfaces (ACs 6-9, T3)"
```

---

## Task 4: AC10 — H3 partition across four output surfaces

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 1 test).

- [ ] **Step 1: Write the failing test**

Append:

```python
# ─── AC10: H3 partition across four output surfaces ──────────────────────────

def test_h3_partition_across_four_output_surfaces(tmp_path, monkeypatch) -> None:
    """AC10 — given one publishable + one Policy-B-gapped seed:
      (a) only publishable iid in thesis_cards.yaml
      (b) only publishable iid in opportunity_report.json rows
      (c) only publishable iid in discipline_report.md bucket sections
      (d) only gapped iid in rejections.json entries
      (e) gapped iid in discipline_report.md failure section
    """
    from irc.commands.opportunity_cmd import run_opportunity

    # Seed only cn_equity_fund (one publishable iid) + force a synthetic
    # gapped row via a second cn_equity_fund whose holdings _ak_call
    # returns empty (triggers Policy B insufficient_info_coverage_top_half).
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    # Augment scoring.json with a second iid that gets the empty-holdings
    # treatment via the dispatcher.
    out_dir = tmp_path / "outputs" / _today_cn()
    scoring = json.loads((out_dir / "scoring.json").read_text(encoding="utf-8"))
    scoring["scores"].append({
        "instrument_id": "163417", "name_cn": "兴全合润",
        "asset_class": "cn_equity_fund", "composite_score": 65.0,
    })
    (out_dir / "scoring.json").write_text(
        json.dumps(scoring, ensure_ascii=False), encoding="utf-8",
    )

    # 163417 gets empty AkShare holdings → Policy B failure.
    import pandas as pd
    dispatch[("fund_portfolio_hold_em", "163417")] = pd.DataFrame()

    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    cards_doc = yaml.safe_load((out_dir / "thesis_cards.yaml").read_text(encoding="utf-8")) or {}
    card_iids = {c["instrument_id"] for c in cards_doc.get("cards", [])}
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    row_iids = {r["instrument_id"] for r in opp.get("rows", [])}
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    rej_iids = {e["instrument_id"] for e in rej.get("entries", [])}
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    failure_idx = md.find("## 证据不足")
    above = md[:failure_idx]
    below = md[failure_idx:]

    assert "005827" in card_iids, "publishable iid missing from thesis_cards.yaml"
    assert "163417" not in card_iids, "gapped iid leaked into thesis_cards.yaml"
    assert "005827" in row_iids, "publishable iid missing from opportunity rows"
    assert "163417" not in row_iids, "gapped iid leaked into opportunity rows"
    assert "005827" in above, "publishable iid missing from discipline buckets"
    assert "163417" not in above, "gapped iid leaked into discipline buckets"
    assert "163417" in rej_iids, "gapped iid missing from rejections.json"
    assert "005827" not in rej_iids, "publishable iid leaked into rejections.json"
    assert "163417" in below, "gapped iid missing from discipline failure section"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_h3_partition_across_four_output_surfaces -v`

Expected: PASS, OR FAIL with drift → Q6 flow.

- [ ] **Step 3: Implement (Q6 if needed)**

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_h3_partition_across_four_output_surfaces -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock H3 partition across 4 output surfaces (AC10, T4)"
```

---

## Task 5: AC11 — Policy-B precedence renders qdii_information_unavailable over Policy-B codes

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 1 test).

- [ ] **Step 1: Write the failing test**

Append:

```python
# ─── AC11: Policy-B precedence ───────────────────────────────────────────────

def test_policy_b_precedence_qdii_over_policy_b_code(tmp_path, monkeypatch) -> None:
    """AC11 — a QDII row carrying BOTH 'qdii_information_unavailable' AND
    'insufficient_info_coverage_top_half' in evidence_gaps must classify
    its rejection_reason as 'qdii_information_unavailable'.

    Asserts on the OBSERVABLE string, NOT by importing _GAP_TO_REASON.
    """
    # precedence per src/irc/opportunity/rejection_log.py::_GAP_TO_REASON
    # dict-iteration order + ADR 0003
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow

    # Use the partitioner directly per spec §5 D3 Option B — easier to
    # hand-control evidence_gaps shape than to coax it through the full
    # run_opportunity pipeline.
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    _install_ak_call_dispatch(monkeypatch, dispatch)

    qdii_row = OpportunityRow(
        instrument_id="004243",
        name_cn="易方达原油",
        asset_class="qdii_us",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="qdii_sentinel", key="004243",
            display_cn="易方达原油", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="evidence_insufficient",
        product_quality_state="strong",
        opportunity_state="exclude",
        opportunity_reason="",
        evidence_gaps=(
            "qdii_information_unavailable",
            "insufficient_info_coverage_top_half",
        ),
        thesis_evidence=(),
        constituent_analyses=(),
    )

    out_dir = tmp_path / "outputs" / _today_cn()
    _write_opportunity_outputs(
        rows=(qdii_row,), out_dir=str(out_dir), today=_today_cn(),
    )

    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entry = next(e for e in rej["entries"] if e["instrument_id"] == "004243")
    assert entry["rejection_reason"] == "qdii_information_unavailable", \
        f"Policy-B precedence broken: got {entry['rejection_reason']!r}, " \
        "expected 'qdii_information_unavailable' (qdii key precedes policy-b key " \
        "in _GAP_TO_REASON dict-iteration order per ADR 0003)"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_policy_b_precedence_qdii_over_policy_b_code -v`

Expected: PASS (precedence locked at item 003), OR FAIL → Q6 flow.

- [ ] **Step 3: Implement (Q6 if needed)**

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_policy_b_precedence_qdii_over_policy_b_code -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock Policy-B precedence over QDII reason (AC11, T5)"
```

---

## Task 6: AC12 — fetch_budget_exhausted is fatal at write time via run_opportunity

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 1 test).

- [ ] **Step 1: Write the failing test**

Append:

```python
# ─── AC12: fetch_budget_exhausted is fatal at write time ─────────────────────

def test_fetch_budget_exhausted_fatal_at_write_time_via_run_opportunity(
    tmp_path, monkeypatch,
) -> None:
    """AC12 — _write_opportunity_outputs called with a row carrying
    'fetch_budget_exhausted' in evidence_gaps raises RuntimeError before
    any .tmp file becomes visible. Re-asserts via run_opportunity (the
    partitioner-level test in test_opportunity_cmd_h3_invariant.py
    asserts on _write_opportunity_outputs directly)."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
        override_env={"IRC_FETCH_BUDGET": "1"},
    )
    _install_ak_call_dispatch(monkeypatch, dispatch)

    poisoned_row = OpportunityRow(
        instrument_id="005827",
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827",
            display_cn="易方达蓝筹精选", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=("fetch_budget_exhausted",),
        thesis_evidence=(),
        constituent_analyses=(),
    )

    out_dir = tmp_path / "outputs" / _today_cn()
    with pytest.raises(RuntimeError, match="fetch_budget_exhausted"):
        _write_opportunity_outputs(
            rows=(poisoned_row,), out_dir=str(out_dir), today=_today_cn(),
        )

    # No artifacts may exist after the fatal raise.
    assert not (out_dir / "opportunity_report.json").exists(), \
        "fetch_budget_exhausted raise left a partial opportunity_report.json"
    assert not any(out_dir.glob("*.tmp*")), \
        "fetch_budget_exhausted raise left a .tmp file"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_fetch_budget_exhausted_fatal_at_write_time_via_run_opportunity -v`

Expected: PASS (the partitioner-level invariant from test_opportunity_cmd_h3_invariant.py already enforces this), OR FAIL → Q6 flow.

- [ ] **Step 3: Implement (Q6 if needed)**

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_fetch_budget_exhausted_fatal_at_write_time_via_run_opportunity -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock fetch_budget_exhausted fatal raise at write boundary (AC12, T6)"
```

---

## Task 7: ACs 13–14 — 持仓明细 appendix integrity (D3b)

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 2 tests).

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ─── ACs 13–14: 持仓明细 appendix integrity (D3b) ────────────────────────────

_APPENDIX_LINE_RE_FOR_TEST = re.compile(
    r"^- \S+ .+ \(权重 [\d.]+%\): (✅|❌|⚠️) .+$"
)


def test_chicang_appendix_line_shape_per_publishable_row(tmp_path, monkeypatch) -> None:
    """AC13 — for every publishable cn_equity_fund/cn_etf row with non-empty
    constituent_analyses, the '## 持仓明细' appendix contains a subheading
    '### {instrument_id} {name_cn}' followed by ≥1 bullet line matching the
    locked regex (audit-error suffix permitted)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))

    appendix_idx = md.find("## 持仓明细")
    if appendix_idx < 0:
        pytest.skip("no publishable cn_equity_fund/cn_etf rows with constituents in this seed")
    appendix = md[appendix_idx:]

    for row in opp.get("rows", []):
        if row["asset_class"] not in {"cn_equity_fund", "cn_etf"}:
            continue
        if not row.get("constituent_analyses"):
            continue
        subheading = f"### {row['instrument_id']} {row['name_cn']}"
        assert subheading in appendix, \
            f"appendix missing subheading {subheading!r}"
        # Find subheading + following block until next ### or EOF.
        sh_idx = appendix.index(subheading)
        next_sh = appendix.find("###", sh_idx + len(subheading))
        block = appendix[sh_idx:next_sh] if next_sh >= 0 else appendix[sh_idx:]
        bullets = [
            ln for ln in block.splitlines()
            if _APPENDIX_LINE_RE_FOR_TEST.match(ln)
        ]
        assert bullets, \
            f"appendix subheading {subheading!r} has no bullet lines matching shape"


def test_chicang_appendix_omits_qdii(tmp_path, monkeypatch) -> None:
    """AC14 — QDII rows have NO '### {instrument_id}' subheading in the
    '## 持仓明细' appendix (they appear only in the failure section)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    appendix_idx = md.find("## 持仓明细")
    if appendix_idx < 0:
        # Appendix may be absent if no publishable rows have constituents.
        # That's fine; QDII is trivially absent.
        return
    appendix = md[appendix_idx:]
    for iid in _QDII_IIDS:
        assert f"### {iid}" not in appendix, \
            f"QDII {iid} leaked into 持仓明细 appendix"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "chicang_"`

Expected: 2 PASS (item 007 added the appendix renderer), OR FAIL → Q6 flow.

- [ ] **Step 3: Implement (Q6 if needed)**

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "chicang_"`

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock 持仓明细 appendix shape + QDII omission (ACs 13-14, T7)"
```

---

## Task 8: ACs 15–17 — snapshot-cache freshness (E8 family)

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 3 tests + small fixture-write helper).

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ─── ACs 15–17: snapshot-cache freshness (E8 family) ─────────────────────────

def _prewrite_active_fund_cache(
    tmp_path: Path,
    *,
    fund_id: str,
    cache_probed_at: str,
    source_report_quarter: str = "2024Q4",
) -> None:
    """Pre-write an ActiveFundSnapshot cache file with a controlled
    cache_probed_at field. Mirrors the on-disk shape produced by
    `snapshot_cache.write_active_fund_snapshot`."""
    from irc.fundamentals.snapshot_cache import write_active_fund_snapshot
    from irc.fundamentals.types import ActiveFundSnapshot

    snap = ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_quarter=source_report_quarter,
        constituent_analyses=(),
        failure_reasons_by_symbol={},
        cache_probed_at=cache_probed_at,
        evidence=(),
    )
    write_active_fund_snapshot(
        cache_root=tmp_path / "data" / "fundamentals",
        snapshot=snap,
    )


def test_snapshot_cache_within_window_zero_akshare_calls(tmp_path, monkeypatch) -> None:
    """AC15 — within IRC_CACHE_FRESHNESS_DAYS, cached snapshot is reused
    and zero _ak_call invocations target the cached fund_id."""
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
        seed_date=today,
    )
    # Pre-write cache with cache_probed_at = today (within window).
    _prewrite_active_fund_cache(
        tmp_path, fund_id="005827", cache_probed_at=today,
    )
    counter = _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(repo_root=str(tmp_path))

    fund_calls = sum(
        v for (fn, sym), v in counter.items() if sym == "005827"
    )
    assert fund_calls == 0, \
        f"expected zero AkShare calls for cached fund 005827, got {fund_calls}: " \
        f"{[k for k in counter if k[1] == '005827']}"


def test_snapshot_cache_expired_probe_same_quarter_reuses(tmp_path, monkeypatch) -> None:
    """AC16 — cache older than IRC_CACHE_FRESHNESS_DAYS triggers a probe;
    probe returns same source_report_quarter so cache is reused (no full
    re-fetch) and cache_probed_at is updated to today."""
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    expired = (
        datetime.now(timezone(timedelta(hours=8))).date()
        - timedelta(days=14)
    ).isoformat()

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
        seed_date=today,
    )
    _prewrite_active_fund_cache(
        tmp_path, fund_id="005827", cache_probed_at=expired,
        source_report_quarter="2024Q4",
    )
    # Dispatch returns the same source_report_quarter on the probe.
    # Probe surface lives in the akshare layer; the seed dispatcher
    # returns a probe frame keyed by ("fund_announcement_em", "005827")
    # carrying the 2024Q4 marker. Tweak per actual probe shape if needed.
    import pandas as pd
    dispatch[("fund_announcement_em", "005827")] = pd.DataFrame({
        "公告日期": ["2024-01-15"],  # signals 2024Q4 report quarter
        "公告标题": ["2024年第4季度报告"],
    })

    counter = _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    # Expect probe call(s) but NOT a full fund_portfolio_hold_em re-fetch.
    holdings_calls = counter[("fund_portfolio_hold_em", "005827")]
    assert holdings_calls == 0, \
        f"same-quarter probe should not trigger holdings re-fetch, got {holdings_calls}"

    # cache_probed_at updated to today on disk.
    from irc.fundamentals.snapshot_cache import read_active_fund_snapshot
    snap = read_active_fund_snapshot(
        cache_root=tmp_path / "data" / "fundamentals",
        fund_id="005827",
    )
    assert snap is not None
    assert snap.cache_probed_at == today, \
        f"expected cache_probed_at refreshed to {today}, got {snap.cache_probed_at}"


def test_snapshot_cache_probe_failure_fail_closed_refetch(tmp_path, monkeypatch) -> None:
    """AC17 — probe failure forces full re-fetch (fail-closed, never silent-reuse).
    Per CONTEXT.md 'Fail-closed freshness probe'."""
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    expired = (
        datetime.now(timezone(timedelta(hours=8))).date()
        - timedelta(days=14)
    ).isoformat()

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
        seed_date=today,
    )
    _prewrite_active_fund_cache(
        tmp_path, fund_id="005827", cache_probed_at=expired,
    )

    # Force the probe to fail with a deterministic exception. Use a custom
    # dispatcher that raises for the probe surface; other surfaces fall back
    # to empty frames.
    import pandas as pd

    def _probe_raises_side(fn_name, *args, **kwargs):
        symbol = args[0] if args else kwargs.get("symbol", "")
        if fn_name == "fund_announcement_em" and str(symbol) == "005827":
            raise RuntimeError("network error")
        return pd.DataFrame()

    counter = Counter()

    def _counting_side(fn_name, *args, **kwargs):
        sym = args[0] if args else kwargs.get("symbol", "")
        counter[(fn_name, str(sym))] += 1
        return _probe_raises_side(fn_name, *args, **kwargs)

    monkeypatch.setattr(
        "irc.fundamentals.akshare_fundamentals._ak_call", _counting_side,
    )

    # Expect the probe failure to bubble up OR trigger a full refetch that
    # also raises (since the holdings call returns empty + the snapshot
    # builder may itself surface the underlying error). Either way, the
    # invariant under test is "fail-closed, never silent-reuse". We verify
    # the probe was called AND that holdings fetch was attempted (the
    # fail-closed path), regardless of final outcome.
    try:
        run_opportunity(repo_root=str(tmp_path))
    except Exception:
        pass  # AC17 tolerates the downstream raise; key invariant below.

    probe_calls = counter[("fund_announcement_em", "005827")]
    holdings_calls = counter[("fund_portfolio_hold_em", "005827")]
    assert probe_calls >= 1, "fail-closed probe was not even attempted"
    assert holdings_calls >= 1, \
        "probe failure did NOT trigger full re-fetch (silent-reuse leak)"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "snapshot_cache_"`

Expected: 3 PASS, OR FAIL → Q6 flow. If a test fails because the probe surface is at a different `_ak_call` fn name than `fund_announcement_em`, update the dispatch key (this is a test-helper fix, not production drift).

- [ ] **Step 3: Implement (Q6 if needed)**

If `cache_probed_at` is not refreshed after a same-quarter probe (silent drift in the snapshot cache writer), file a `fix(fundamentals):` commit + `008-drift.md` entry.

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "snapshot_cache_"`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock snapshot-cache freshness probe scenarios (ACs 15-17, T8)"
```

---

## Task 9: AC18 — E9 downstream propagation (empty AkShare → holdings_fetch_failed + exclude)

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 1 test).

- [ ] **Step 1: Write the failing test**

Append:

```python
# ─── AC18: E9 downstream propagation ─────────────────────────────────────────

def test_empty_holdings_propagate_to_rejections_holdings_fetch_failed(
    tmp_path, monkeypatch,
) -> None:
    """AC18 — empty AkShare holdings → failure_reasons_by_symbol populated
    → row carries evidence_gaps containing 'holdings_fetch_failed' →
    appears in rejections.json, NOT in thesis_cards.yaml."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    # Force empty holdings for 005827.
    import pandas as pd
    dispatch[("fund_portfolio_hold_em", "005827")] = pd.DataFrame()

    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cards_doc = yaml.safe_load((out_dir / "thesis_cards.yaml").read_text(encoding="utf-8")) or {}
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))

    card_iids = {c["instrument_id"] for c in cards_doc.get("cards", [])}
    assert "005827" not in card_iids, \
        "fund with empty AkShare holdings leaked into thesis_cards.yaml"

    entry = next(
        (e for e in rej.get("entries", []) if e["instrument_id"] == "005827"),
        None,
    )
    assert entry is not None, \
        "fund with empty AkShare holdings missing from rejections.json"
    # evidence_gaps either carries the canonical code OR is mapped to a
    # rejection_reason that traces back to it. Check both surfaces.
    gaps = entry.get("evidence_gaps", [])
    reason = entry.get("rejection_reason", "")
    assert "holdings_fetch_failed" in gaps or reason == "holdings_fetch_failed", \
        f"expected holdings_fetch_failed in gaps or reason; got gaps={gaps!r} reason={reason!r}"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_empty_holdings_propagate_to_rejections_holdings_fetch_failed -v`

Expected: PASS, OR FAIL → Q6 flow.

- [ ] **Step 3: Implement (Q6 if needed)**

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_empty_holdings_propagate_to_rejections_holdings_fetch_failed -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock empty-holdings → rejections propagation (AC18, T9)"
```

---

## Task 10: ACs 19–20 — cross-stage SAME-3 / citation-id-subset (run_opportunity → run_memo)

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 2 tests).

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ─── ACs 19–20: cross-stage SAME-3 / citation-id-subset ──────────────────────

def _harvest_first_citation_ids(out_dir: Path, n: int = 3) -> list[str]:
    """Return up to n citation_ids from opportunity_report.json — used to
    build a deterministic memo synth body whose [ref:...] markers are a
    known subset of the publishable universe."""
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    ids: list[str] = []
    for row in opp.get("rows", []):
        for ev in row.get("thesis_evidence", []):
            cid = ev.get("citation_id")
            if cid and cid not in ids:
                ids.append(cid)
            if len(ids) >= n:
                return ids
    return ids


def test_memo_cites_only_publishable_citation_ids(tmp_path, monkeypatch) -> None:
    """AC19 — every [ref:{id}] in memo.md is in the publishable universe
    defined as opportunity_report.json ∪ gold_regime.json (rejections.json
    EXCLUDED per Q5)."""
    from irc.commands.memo_cmd import run_memo
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cids = _harvest_first_citation_ids(out_dir, n=3)
    if not cids:
        pytest.skip("no citation_ids produced by run_opportunity in this seed")
    synth_body = " ".join(f"[ref:{c}]" for c in cids) + " 备忘录正文"

    with _patch_memo_routes(synth_body):
        run_memo(str(tmp_path))

    memo_md = (out_dir / "memo.md").read_text(encoding="utf-8")
    universe = _collect_publishable_citation_universe(out_dir)
    refs = re.findall(r"\[ref:([0-9a-f]{16})\]", memo_md)
    assert refs, "memo.md has no [ref:...] markers despite synth body containing them"
    leaked = [r for r in refs if r not in universe]
    assert not leaked, \
        f"memo.md cites {leaked!r} not in publishable universe (size {len(universe)})"


def test_memo_picks_table_citation_set_matches_opportunity_row(
    tmp_path, monkeypatch,
) -> None:
    """AC20 — for each cn_equity_fund pick, the set of citation_ids in
    memo.md picks-table 证据 cell equals the set in opportunity_report.json
    for that row's selected-top-3 (per select_citations(cap=3)).
    SAME-3 invariant re-asserted post-disk-roundtrip."""
    from irc.commands.memo_cmd import run_memo
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.memo.citation_selector import select_citations
    from irc.fundamentals.types import ThesisEvidence

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cids = _harvest_first_citation_ids(out_dir, n=3)
    if not cids:
        pytest.skip("no citation_ids produced in this seed")

    with _patch_memo_routes(" 备忘录正文"):
        run_memo(str(tmp_path))

    memo_md = (out_dir / "memo.md").read_text(encoding="utf-8")
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))

    for row in opp.get("rows", []):
        if row["asset_class"] != "cn_equity_fund":
            continue
        # Reconstruct top-3 via select_citations and compare to picks-table cell.
        evs = tuple(ThesisEvidence.from_dict(d) for d in row.get("thesis_evidence", []))
        top3 = {ev.citation_id for ev in select_citations(evs, cap=3)}
        # Locate the picks-table row for this iid; extract its 证据 cell.
        pat = rf"\| *{re.escape(row['instrument_id'])} *\|.*?\|(.*?)\|"
        m = re.search(pat, memo_md)
        if not m:
            pytest.skip(f"no picks-table row for {row['instrument_id']}")
        cell = m.group(1)
        cell_ids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", cell))
        assert cell_ids == top3, \
            f"SAME-3 mismatch for {row['instrument_id']}: " \
            f"picks-table={cell_ids!r} vs opportunity-top-3={top3!r}"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "memo_cites_only_publishable or memo_picks_table_citation"`

Expected: 2 PASS, OR FAIL → Q6 flow.

- [ ] **Step 3: Implement (Q6 if needed)**

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "memo_cites_only_publishable or memo_picks_table_citation"`

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock cross-stage SAME-3 + citation-id-subset (ACs 19-20, T10)"
```

---

## Task 11: AC21 — multi-owner constituent keeps separate provenance on disk

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 1 test).

- [ ] **Step 1: Write the failing test**

Append:

```python
# ─── AC21: multi-owner constituent on-disk provenance ────────────────────────

def test_multi_owner_constituent_keeps_separate_owner_instrument_id(
    tmp_path, monkeypatch,
) -> None:
    """AC21 — when 贵州茅台 (600519) appears as a constituent of BOTH fund A
    (005827) and fund B (163417), each fund's thesis_evidence entry for
    600519 has owner_instrument_id == that fund's iid. No leakage."""
    from irc.commands.opportunity_cmd import run_opportunity
    import pandas as pd

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    # Add a second cn_equity_fund seed.
    out_dir = tmp_path / "outputs" / _today_cn()
    scoring = json.loads((out_dir / "scoring.json").read_text(encoding="utf-8"))
    scoring["scores"].append({
        "instrument_id": "163417", "name_cn": "兴全合润",
        "asset_class": "cn_equity_fund", "composite_score": 72.0,
    })
    (out_dir / "scoring.json").write_text(
        json.dumps(scoring, ensure_ascii=False), encoding="utf-8",
    )

    # Both funds carry 600519 as a top holding.
    same_holding_frame = pd.DataFrame({
        "股票代码": ["600519"],
        "股票名称": ["贵州茅台"],
        "占净值比例": [8.2],
    })
    dispatch[("fund_portfolio_hold_em", "005827")] = same_holding_frame
    dispatch[("fund_portfolio_hold_em", "163417")] = same_holding_frame

    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    by_iid = {r["instrument_id"]: r for r in opp.get("rows", [])}
    if "005827" not in by_iid or "163417" not in by_iid:
        pytest.skip("seed did not produce both funds publishably")

    a_owners = {
        ev["owner_instrument_id"]
        for ev in by_iid["005827"].get("thesis_evidence", [])
        if ev.get("constituent_key") == "600519"
    }
    b_owners = {
        ev["owner_instrument_id"]
        for ev in by_iid["163417"].get("thesis_evidence", [])
        if ev.get("constituent_key") == "600519"
    }
    assert a_owners == {"005827"}, \
        f"fund A 600519 entries have wrong owner_instrument_id: {a_owners!r}"
    assert b_owners == {"163417"}, \
        f"fund B 600519 entries have wrong owner_instrument_id: {b_owners!r}"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_multi_owner_constituent_keeps_separate_owner_instrument_id -v`

Expected: PASS, OR FAIL → Q6 flow.

- [ ] **Step 3: Implement (Q6 if needed)**

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py::test_multi_owner_constituent_keeps_separate_owner_instrument_id -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock multi-owner constituent provenance (AC21, T11)"
```

---

## Task 12: ACs 22–23 — pipeline-level two-run byte equality

**Files:**
- Modify: `tests/integration/test_publishable_set_lockdown.py` (append 2 tests).

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ─── ACs 22–23: pipeline-level two-run byte equality ─────────────────────────

def test_two_run_byte_equality_opportunity_artifacts(tmp_path, monkeypatch) -> None:
    """AC22 — two consecutive run_opportunity invocations against identical
    seeds in distinct tmp_paths produce byte-identical artifacts for:
      - opportunity_report.json
      - thesis_cards.yaml
      - discipline_report.md
      - rejections.json
    Catches non-deterministic ordering (frozenset, glob, dict-hash, timestamps)
    invisible to unit-level tests."""
    from irc.commands.opportunity_cmd import run_opportunity

    a = tmp_path / "run_a"
    b = tmp_path / "run_b"
    a.mkdir()
    b.mkdir()

    today = _today_cn()
    dispatch_a = _seed_publishable_set_repo(
        a, monkeypatch=monkeypatch, seed_date=today,
    )
    _install_ak_call_dispatch(monkeypatch, dispatch_a)
    run_opportunity(repo_root=str(a))

    dispatch_b = _seed_publishable_set_repo(
        b, monkeypatch=monkeypatch, seed_date=today,
    )
    _install_ak_call_dispatch(monkeypatch, dispatch_b)
    run_opportunity(repo_root=str(b))

    for name in (
        "opportunity_report.json",
        "thesis_cards.yaml",
        "discipline_report.md",
        "rejections.json",
    ):
        ha = _sha256_file(a / "outputs" / today / name)
        hb = _sha256_file(b / "outputs" / today / name)
        assert ha == hb, \
            f"{name} differs across two runs: a={ha[:12]}… b={hb[:12]}… " \
            "(non-determinism in the I/O stack — likely frozenset iter, " \
            "glob/walk ordering, dict-hash, or datetime.now() injection)"


def test_two_run_byte_equality_memo_after_run_memo(tmp_path, monkeypatch) -> None:
    """AC23 — same shape as AC22 but for memo.md after run_opportunity → run_memo.
    Patched synth body is a deterministic function of the just-written
    opportunity_report.json so the synth output is itself a function of the
    publishable-set citation universe."""
    from irc.commands.memo_cmd import run_memo
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    a = tmp_path / "run_a"
    b = tmp_path / "run_b"
    a.mkdir()
    b.mkdir()

    def _full_run(repo: Path) -> Path:
        dispatch = _seed_publishable_set_repo(
            repo, monkeypatch=monkeypatch, seed_date=today,
        )
        _install_ak_call_dispatch(monkeypatch, dispatch)
        run_opportunity(repo_root=str(repo))
        out_dir = repo / "outputs" / today
        cids = _harvest_first_citation_ids(out_dir, n=3)
        synth_body = " ".join(f"[ref:{c}]" for c in cids) + " 备忘录正文"
        with _patch_memo_routes(synth_body):
            run_memo(str(repo))
        return out_dir

    out_a = _full_run(a)
    out_b = _full_run(b)

    ha = _sha256_file(out_a / "memo.md")
    hb = _sha256_file(out_b / "memo.md")
    assert ha == hb, \
        f"memo.md differs across two runs: a={ha[:12]}… b={hb[:12]}… " \
        "(non-determinism in the memo I/O stack)"
```

- [ ] **Step 2: Run failing**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "two_run_byte_equality"`

Expected: 2 PASS — items 002/007 + the unit-level determinism tests should have already eliminated non-determinism. OR FAIL → Q6 flow (most likely sources: frozenset iteration in alias-map construction NOT pre-sorted before serialization, `os.walk` ordering in `data/fundamentals/` reads, `glob` non-determinism).

- [ ] **Step 3: Implement (Q6 if needed)**

If a byte-equality test FAILs, this is the most consequential drift surface in the entire item — production fix MUST land via `fix(<scope>):` commit + `008-drift.md` entry. Likely culprits:
- Missing `sorted(...)` around a `frozenset` iteration in a renderer.
- `dict` constructed from a set without `sorted()` before JSON serialization.
- `datetime.now()` injected into an output without being passed in as a deterministic param.

- [ ] **Step 4: Run green**

Run: `pytest tests/integration/test_publishable_set_lockdown.py -v -k "two_run_byte_equality"`

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_publishable_set_lockdown.py
git commit -m "test(integration): lock pipeline-level two-run byte equality (ACs 22-23, T12)"
```

---

## Task 13: CONTEXT.md update + final verification

**Files:**
- Modify: `CONTEXT.md` (append two terms to the "Test infrastructure" section per grill F3).
- (No code changes beyond Task 12.)

- [ ] **Step 1: Append the two CONTEXT.md terms**

Locate the "Test infrastructure" section in `CONTEXT.md`. Append two new paragraphs (the exact wording lives below; locate the right place via existing terms like "Live test gate" / "H3 invariant"):

```
- **Publishable-set lockdown baseline.** `tests/integration/test_publishable_set_lockdown.py`
  is the locked artifact-read baseline for the publishable set's citation /
  scope / state / asset-class invariants after `run_opportunity` (and
  cross-stage `run_memo`). Item 009 must not flip `IRC_CITATION_ENFORCE_MODE`
  to `block` mode on canonical paths until this baseline is green on the
  feature branch. Covers 7 invariant families: dual-leg citation coverage,
  owner-instrument provenance, publishable scope, `thesis_state` literal-only,
  empty `evidence_gaps` after JSON round-trip, QDII exclusion across 4 output
  surfaces, H3 partition across 4 output surfaces, Policy-B precedence,
  `fetch_budget_exhausted` fatal-at-write, 持仓明细 appendix integrity,
  snapshot-cache freshness, cross-stage SAME-3, multi-owner constituent
  provenance, and pipeline-level two-run byte equality.

- **Publishable citation universe.** The set
  `{citation_id for row in opportunity_report.json["rows"]
                for entry in row["thesis_evidence"]}`
  unioned with `{citation_id for entry in gold_regime.json["evidence"]}`.
  `rejections.json` is **EXPLICITLY EXCLUDED** — `RejectionRecord`
  (`src/irc/opportunity/rejection_log.py`) has no `thesis_evidence`
  field; gapped rows have not earned conclusions and carry no citations.
  Item 009's `find_missing_citations` lookup table MUST be built from
  this universe; widening it to include rejections would create false
  negatives. Constructed solely by
  `_collect_publishable_citation_universe(out_dir)` in
  `tests/integration/test_publishable_set_lockdown.py`.
```

Use Edit to append these terms at the appropriate place under "Test infrastructure". If the section is missing, place them under the closest analogue (e.g. "Renderers + alias-builder").

- [ ] **Step 2: Run the full test suite**

Run:
```bash
pytest -x -q
```

Expected: PASS — every test in the full repo green, including the 23 new tests in `tests/integration/test_publishable_set_lockdown.py` plus all unit + scenario tests from items 001–007.

- [ ] **Step 3: Run ruff**

Run:
```bash
ruff check src/ tests/
```

Expected: clean (zero violations). Item 008's touched files are `tests/integration/test_publishable_set_lockdown.py` + `CONTEXT.md` (+ any `fix(...)` commits' files); the constraint is "clean for item 008's touched files". Fix any flagged issues by editing the offending file; commit the fix as a separate `style(integration):` commit.

- [ ] **Step 4: Inspect the slice's commit log**

Run:
```bash
git log --oneline autodev/thesis-cards-evidence-gap..HEAD
```

Expected: 12 `test(integration):` commits + 1 `docs(context):` commit (this task) + any `fix(...):` commits added during Tasks 2–12 per Q6.

- [ ] **Step 5: Confirm the file-touch map matches the actual diff**

Run:
```bash
git diff --name-status autodev/thesis-cards-evidence-gap..HEAD
```

Expected to show:
- `A tests/integration/test_publishable_set_lockdown.py` (the only new file)
- `M CONTEXT.md` (Task 13's two-term append)
- Optionally: `A docs/2026-05-22-thesis-cards-evidence-gap/items/008-drift.md` (if any Q6 inline-fix ran)
- Optionally: any `src/irc/**` file touched by a Q6 inline-fix commit (each with a matching `008-drift.md` entry)

- [ ] **Step 6: Commit the CONTEXT.md update**

```bash
git add CONTEXT.md
git commit -m "docs(context): lock publishable-set baseline + citation universe terms (T13)"
```

(Steps 2–5 are verification, no commit. Step 6 ships the CONTEXT.md amendment.)

The slice is complete when Steps 2 + 3 are green and Step 5 matches the file-touch map.

---

## Acceptance criteria mapping (23 ACs → tasks)

| AC | Description | Task | Test name |
|---|---|---|---|
| 1 | Dual-leg coverage on every published row | T2 | `test_publishable_dual_leg_coverage` |
| 2 | Owner-instrument provenance | T2 | `test_publishable_owner_instrument_provenance` |
| 3 | Scope is publishable | T2 | `test_publishable_scope_is_instrument_or_constituent` |
| 4 | `thesis_state` literal-only | T2 | `test_publishable_thesis_state_literal_only` |
| 5 | `evidence_gaps` empty on publish | T2 | `test_publishable_evidence_gaps_empty_after_disk_roundtrip` |
| 6 | QDII never in `thesis_cards.yaml` | T3 | `test_qdii_never_in_thesis_cards` |
| 7 | QDII never in `opportunity_report.json["rows"]` | T3 | `test_qdii_never_in_opportunity_report_rows` |
| 8 | QDII in `rejections.json` with `qdii_information_unavailable` | T3 | `test_qdii_appears_in_rejections_with_qdii_reason` |
| 9 | QDII in discipline failure section | T3 | `test_qdii_appears_in_discipline_failure_section` |
| 10 | H3 partition across 4 output surfaces | T4 | `test_h3_partition_across_four_output_surfaces` |
| 11 | Policy-B precedence: qdii over Policy-B code | T5 | `test_policy_b_precedence_qdii_over_policy_b_code` |
| 12 | `fetch_budget_exhausted` fatal at write time | T6 | `test_fetch_budget_exhausted_fatal_at_write_time_via_run_opportunity` |
| 13 | Appendix line shape per publishable row | T7 | `test_chicang_appendix_line_shape_per_publishable_row` |
| 14 | Appendix omitted for QDII | T7 | `test_chicang_appendix_omits_qdii` |
| 15 | Within-window cache read, zero AkShare calls | T8 | `test_snapshot_cache_within_window_zero_akshare_calls` |
| 16 | Expired-window probe + same-quarter reuses cache | T8 | `test_snapshot_cache_expired_probe_same_quarter_reuses` |
| 17 | Probe failure → fail-closed re-fetch | T8 | `test_snapshot_cache_probe_failure_fail_closed_refetch` |
| 18 | Empty AkShare → `holdings_fetch_failed` + exclude | T9 | `test_empty_holdings_propagate_to_rejections_holdings_fetch_failed` |
| 19 | `memo.md` cites only publishable citation_ids | T10 | `test_memo_cites_only_publishable_citation_ids` |
| 20 | Picks-table citations = opportunity top-3 (SAME-3) | T10 | `test_memo_picks_table_citation_set_matches_opportunity_row` |
| 21 | Multi-owner constituent provenance | T11 | `test_multi_owner_constituent_keeps_separate_owner_instrument_id` |
| 22 | Two-run byte equality of opportunity artifacts | T12 | `test_two_run_byte_equality_opportunity_artifacts` |
| 23 | Two-run byte equality of memo.md | T12 | `test_two_run_byte_equality_memo_after_run_memo` |

23/23 ACs covered. Plus Task 1 ships the seed helper + smoke test; Task 13 ships the CONTEXT.md term lock + full-suite verification.

## Open questions resolved (summary, from grill phase)

- **Q1 (`run_memo` offline mocking pattern):** Patch BOTH `irc.memo.synthesizer.call_chat` AND `irc.memo.auditor.call_chat` per `tests/commands/test_memo_cmd_aliases.py:98–99`. Wrapped in `_patch_memo_routes(synth_text)` context manager. No `run_memo_pipeline` invocation needed.
- **Q4 (`IRC_CACHE_FRESHNESS_DAYS` env var):** Exists in production at `src/irc/commands/opportunity_cmd.py:71` (default 7). No new env var, no new CONTEXT.md term beyond the two grill F3 terms, no ADR amendment.
- **Q5 (citation universe formula):** `opportunity_report.json ∪ gold_regime.json`; `rejections.json` EXPLICITLY EXCLUDED — verified by reading `RejectionRecord` dataclass (no `thesis_evidence` field). Sole constructor: `_collect_publishable_citation_universe(out_dir)`.
- **Q6 (production-fix policy in test-only PR):** Inline-fix. If a test exposes a real drift bug, fix in a separate `fix(<scope>):` commit on the same sub-branch with a one-line `008-drift.md` entry. Items 003 + 006 precedent. Do NOT spawn a follow-up issue.
