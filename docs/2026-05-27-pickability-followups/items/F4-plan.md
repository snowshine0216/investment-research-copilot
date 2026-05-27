# F4 — `thesis_news` real-content scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire real `data/research/` theme reports into `score_thesis_news` via a deterministic per-asset-class theme mapping, replacing the `news_summaries={}` literal in `score_cmd.py` that forces every instrument to the 50.0 neutral fallback.

**Architecture:** Add a pure module `src/irc/scoring/news_summaries.py` that exports two pure functions: `themes_for_instrument(asset_class) -> tuple[str, ...]` (static mapping via `MappingProxyType`) and `build_news_summaries(reports, watchlist) -> dict[str, tuple[str, ...]]` (iterates the watchlist, looks up per-asset-class themes, pulls `report_md` from the supplied reports dict, skipping failed/empty reports, returning sorted-by-theme-name tuples for determinism). Wire it into `src/irc/commands/score_cmd.py` after watchlist load and before `run_scoring`, calling `load_theme_reports(root)` at the command edge (effects at edges per CLAUDE.md). The existing `score_thesis_news` factor and its empty-input fallback are untouched.

**Tech Stack:** Python 3.12+, pandas, `types.MappingProxyType`, pytest. No new dependencies. No LLM, no AkShare.

---

## Constraints / Non-goals (DO NOT VIOLATE)

- DO NOT modify `derive_thesis_from_evidence` or anything in `src/irc/opportunity/thesis_evidence.py` — F4 changes scoring rubric only (ADR 0007 Non-goals; spec non-goal #6).
- DO NOT introduce LLM calls — position (a) is keyword-only per ADR-0007 §1.
- DO NOT change the existing `_POS` / `_NEG` keyword lexicons in `src/irc/scoring/factors/thesis_news.py` — ADR 0007 §1 explicitly defers this (spec non-goal #2).
- DO NOT modify the empty-input fallback branch at `src/irc/scoring/factors/thesis_news.py` lines 47–51 — preserves the invariant for instruments missing news content (ADR 0007 §3; spec AC #5).
- DO NOT touch `_write_opportunity_outputs`, `thesis_evidence`, `evidence_pool`, or memo renderers (spec non-goal #4).
- DO NOT modify `scoring.yaml` weights or `compose_score` (spec non-goal #7).
- DO NOT add new `[ref:...]` citation rows (spec non-goal #5; ADR 0007 Non-goals).
- DO NOT add `market` to the `themes_for_instrument` signature — grill Q2 dropped it.
- DO NOT add a network/AkShare/web-search call in the new module or in `build_news_summaries` — pure function, no I/O (spec constraint #6; ADR 0007 Non-goals).

## File Structure

**Create:**
- `src/irc/scoring/news_summaries.py` — pure module with `THEMES_BY_ASSET_CLASS` (immutable `MappingProxyType`), `themes_for_instrument(asset_class)`, `build_news_summaries(reports, watchlist)`. Target < 80 lines.
- `tests/scoring/test_news_summaries.py` — unit tests for `themes_for_instrument` (per asset_class), `build_news_summaries` (empty, populated, failed-report skip, sorted-tuple determinism, two-call byte equality of dict). Target ~140 lines.

**Modify:**
- `src/irc/commands/score_cmd.py` — import `load_theme_reports` from `irc.research.persistence` and `build_news_summaries` from `irc.scoring.news_summaries`; replace `news_summaries={}` at line ~69 with `news_summaries=build_news_summaries(load_theme_reports(root), watchlist)`. Net change ~5 lines.
- `tests/scoring/test_pipeline.py` — add a regression test that calls `run_scoring` with a non-empty `news_summaries` dict and asserts the resulting `thesis_news` factor score is not 50.0 for the instrument with mapped, populated news.

---

## Task 0: Cut the sub-branch off the feature branch

**Files:** (no edits, branch only)

- [ ] **Step 0.1: Verify base branch and clean tree**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
git status
git branch --show-current
```
Expected: working tree clean; current branch `autodev/pickability-followups-feature`.

- [ ] **Step 0.2: Cut the F4 sub-branch**

Run:
```bash
git checkout -b claude/pickability-followups-F4
git branch --show-current
```
Expected output: `claude/pickability-followups-F4`.

---

## Task 1: Red test for `themes_for_instrument` (per asset_class)

**Files:**
- Test: `tests/scoring/test_news_summaries.py`

- [ ] **Step 1.1: Create the test file with the asset_class mapping tests**

Create `tests/scoring/test_news_summaries.py` with:

```python
# tests/scoring/test_news_summaries.py
from __future__ import annotations

import pandas as pd
import pytest

from irc.research.theme_research import ThemeReport
from irc.research.synthesize import Citation
from irc.scoring.news_summaries import (
    THEMES_BY_ASSET_CLASS,
    build_news_summaries,
    themes_for_instrument,
)


# ---- themes_for_instrument: per real asset_class ----

@pytest.mark.parametrize(
    "asset_class, expected",
    [
        ("gold", ("geopolitics", "gold_drivers", "us_monetary")),
        ("cn_equity_fund", ("cn_equity_property_policy", "cn_monetary", "holdings_sector")),
        ("cn_etf", ("cn_equity_property_policy", "cn_monetary", "holdings_sector")),
        ("cn_bond_fund", ("cn_monetary",)),
        (
            "hk_etf",
            ("cn_equity_property_policy", "cn_monetary", "geopolitics", "holdings_sector"),
        ),
        ("us_etf", ("geopolitics", "us_fiscal_politics", "us_monetary")),
        ("qdii_global", ("geopolitics", "us_fiscal_politics", "us_monetary")),
    ],
)
def test_themes_for_instrument_real_asset_classes(asset_class, expected):
    assert themes_for_instrument(asset_class) == expected


def test_themes_for_instrument_unknown_returns_empty_tuple():
    assert themes_for_instrument("not_a_real_class") == ()
    assert themes_for_instrument("") == ()


def test_themes_for_instrument_returns_sorted_ascending():
    for asset_class in THEMES_BY_ASSET_CLASS:
        themes = themes_for_instrument(asset_class)
        assert list(themes) == sorted(themes), (
            f"{asset_class} mapping must be sorted ASC for determinism"
        )


def test_themes_by_asset_class_is_immutable():
    with pytest.raises(TypeError):
        THEMES_BY_ASSET_CLASS["cn_etf"] = ("anything",)  # type: ignore[index]
```

- [ ] **Step 1.2: Run the test to verify it fails**

Run:
```bash
cd /Users/snow/Documents/Repository/investment-research-copilot
uv run pytest tests/scoring/test_news_summaries.py -v
```
Expected: collection/import error — `ModuleNotFoundError: No module named 'irc.scoring.news_summaries'`. This proves the module does not yet exist.

---

## Task 2: Green — create `news_summaries.py` with the mapping + `themes_for_instrument`

**Files:**
- Create: `src/irc/scoring/news_summaries.py`

- [ ] **Step 2.1: Create the module with the mapping and the lookup function only**

Create `src/irc/scoring/news_summaries.py` with:

```python
# src/irc/scoring/news_summaries.py
"""Theme→asset-class plumbing for the `thesis_news` scoring factor.

Pure module: no I/O, no logging, no module-level mutable state. The mapping
table is immutable (`MappingProxyType`). See ADR 0007 for the locked design.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

import pandas as pd

from irc.research.theme_research import ThemeReport


# Locked by ADR 0007 §2. Keys are the seven real asset_class values present
# in config/universe/*.yaml. Values are tuples of theme names sorted ASC for
# determinism (regression-tested in tests/scoring/test_news_summaries.py).
THEMES_BY_ASSET_CLASS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "cn_bond_fund": ("cn_monetary",),
    "cn_equity_fund": ("cn_equity_property_policy", "cn_monetary", "holdings_sector"),
    "cn_etf": ("cn_equity_property_policy", "cn_monetary", "holdings_sector"),
    "gold": ("geopolitics", "gold_drivers", "us_monetary"),
    "hk_etf": (
        "cn_equity_property_policy", "cn_monetary", "geopolitics", "holdings_sector",
    ),
    "qdii_global": ("geopolitics", "us_fiscal_politics", "us_monetary"),
    "us_etf": ("geopolitics", "us_fiscal_politics", "us_monetary"),
})


def themes_for_instrument(asset_class: str) -> tuple[str, ...]:
    """Return the sorted theme tuple mapped to a given asset_class.

    Unknown asset_class returns the empty tuple (silent fallback, per ADR 0007
    §2). The empty tuple feeds the existing neutral-50 invariant in
    `score_thesis_news`.
    """
    return THEMES_BY_ASSET_CLASS.get(asset_class, ())
```

- [ ] **Step 2.2: Run the `themes_for_instrument` tests; verify pass**

Run:
```bash
uv run pytest tests/scoring/test_news_summaries.py -v
```
Expected: 10 passed (7 parametrised real-asset-class cases + unknown + sorted-ASC + immutability).

- [ ] **Step 2.3: Commit the mapping module + its tests**

Run:
```bash
git add src/irc/scoring/news_summaries.py tests/scoring/test_news_summaries.py
git commit -m "test+feat(scoring): add THEMES_BY_ASSET_CLASS + themes_for_instrument (pure)"
```
Expected: one commit recorded; `git status` clean.

---

## Task 3: Red test for `build_news_summaries` (empty, populated, failed-skip, determinism)

**Files:**
- Modify: `tests/scoring/test_news_summaries.py`

- [ ] **Step 3.1: Append the `build_news_summaries` tests**

Append the following to `tests/scoring/test_news_summaries.py`:

```python


# ---- build_news_summaries: empty input ----

def _watchlist(*rows: dict) -> pd.DataFrame:
    """Tiny helper: build a watchlist DataFrame for tests."""
    return pd.DataFrame(list(rows))


def _report(theme: str, report_md: str = "", failure_reason: str = "") -> ThemeReport:
    return ThemeReport(
        theme=theme,
        query="",
        locale="EN",
        report_md=report_md,
        citations=[],
        failure_reason=failure_reason,
        provider_failures=(),
    )


def test_build_news_summaries_empty_reports_and_empty_watchlist():
    out = build_news_summaries(reports={}, watchlist=_watchlist())
    assert out == {}


def test_build_news_summaries_empty_reports_populated_watchlist():
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports={}, watchlist=wl)
    # Key present, but value is empty tuple (gold has mapped themes, none populated)
    assert out == {"518880": ()}


def test_build_news_summaries_gold_uses_mapped_themes():
    reports = {
        "us_monetary": _report("us_monetary", "Fed signals patience on hikes."),
        "gold_drivers": _report("gold_drivers", "Strong demand for gold ETFs."),
        "geopolitics": _report("geopolitics", "Middle East tensions rise."),
        "cn_monetary": _report("cn_monetary", "PBoC unrelated text."),
    }
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    # Sorted ASC by theme name: geopolitics, gold_drivers, us_monetary
    assert out == {
        "518880": (
            "Middle East tensions rise.",
            "Strong demand for gold ETFs.",
            "Fed signals patience on hikes.",
        ),
    }


def test_build_news_summaries_qdii_global_themes():
    reports = {
        "us_monetary": _report("us_monetary", "Fed text."),
        "us_fiscal_politics": _report("us_fiscal_politics", "Fiscal text."),
        "geopolitics": _report("geopolitics", "Geopolitics text."),
    }
    wl = _watchlist({"instrument_id": "QD0001", "asset_class": "qdii_global"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    # Sorted ASC: geopolitics, us_fiscal_politics, us_monetary
    assert out == {
        "QD0001": ("Geopolitics text.", "Fiscal text.", "Fed text."),
    }


def test_build_news_summaries_skips_failed_reports_silently():
    reports = {
        "us_monetary": _report("us_monetary", "", failure_reason="provider 503"),
        "gold_drivers": _report("gold_drivers", "Real gold-drivers prose."),
        "geopolitics": _report("geopolitics", "Real geopolitics prose."),
    }
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    # us_monetary skipped (failure_reason set); only the two populated themes survive.
    assert out == {"518880": ("Real geopolitics prose.", "Real gold-drivers prose.")}


def test_build_news_summaries_skips_empty_report_md():
    reports = {
        "us_monetary": _report("us_monetary", ""),  # empty prose, no failure_reason
        "gold_drivers": _report("gold_drivers", "Real gold-drivers prose."),
        "geopolitics": _report("geopolitics", "Real geopolitics prose."),
    }
    wl = _watchlist({"instrument_id": "518880", "asset_class": "gold"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    assert out == {"518880": ("Real geopolitics prose.", "Real gold-drivers prose.")}


def test_build_news_summaries_unknown_asset_class_gives_empty_tuple():
    reports = {"us_monetary": _report("us_monetary", "anything")}
    wl = _watchlist({"instrument_id": "X1", "asset_class": "totally_new_class"})
    out = build_news_summaries(reports=reports, watchlist=wl)
    assert out == {"X1": ()}


def test_build_news_summaries_mixed_watchlist_keys_every_row():
    reports = {
        "cn_monetary": _report("cn_monetary", "PBoC text."),
        "gold_drivers": _report("gold_drivers", "Gold text."),
        "geopolitics": _report("geopolitics", "Geo text."),
        "us_monetary": _report("us_monetary", "Fed text."),
    }
    wl = _watchlist(
        {"instrument_id": "511880", "asset_class": "cn_bond_fund"},
        {"instrument_id": "518880", "asset_class": "gold"},
        {"instrument_id": "MM01", "asset_class": "totally_new_class"},
    )
    out = build_news_summaries(reports=reports, watchlist=wl)
    assert out == {
        "511880": ("PBoC text.",),
        "518880": ("Geo text.", "Gold text.", "Fed text."),
        "MM01": (),
    }


def test_build_news_summaries_is_deterministic_two_calls_equal():
    reports = {
        "us_monetary": _report("us_monetary", "Fed text."),
        "gold_drivers": _report("gold_drivers", "Gold text."),
        "geopolitics": _report("geopolitics", "Geo text."),
        "cn_monetary": _report("cn_monetary", "PBoC text."),
    }
    wl = _watchlist(
        {"instrument_id": "518880", "asset_class": "gold"},
        {"instrument_id": "511880", "asset_class": "cn_bond_fund"},
    )
    a = build_news_summaries(reports=reports, watchlist=wl)
    b = build_news_summaries(reports=reports, watchlist=wl)
    assert a == b
    # Stronger: the serialised form must be byte-identical too (sorted tuples
    # protect against dict-ordering drift in the per-instrument value).
    import json
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
```

- [ ] **Step 3.2: Run; verify the new tests fail (build_news_summaries not yet defined)**

Run:
```bash
uv run pytest tests/scoring/test_news_summaries.py -v
```
Expected: ImportError or collection error for `build_news_summaries` — the existing themes tests still pass; the new tests fail because the function symbol does not yet exist.

---

## Task 4: Green — implement `build_news_summaries`

**Files:**
- Modify: `src/irc/scoring/news_summaries.py`

- [ ] **Step 4.1: Append `build_news_summaries` to the module**

Append to `src/irc/scoring/news_summaries.py`:

```python


def _summary_for_theme(theme: str, reports: Mapping[str, ThemeReport]) -> str:
    """Return the prose body for a theme, or '' if absent/failed/empty.

    Pure: no I/O. Failed reports (non-empty `failure_reason`) and empty
    `report_md` both return '' so the caller can filter them out uniformly.
    """
    report = reports.get(theme)
    if report is None:
        return ""
    if report.failure_reason:
        return ""
    return report.report_md or ""


def build_news_summaries(
    reports: Mapping[str, ThemeReport],
    watchlist: pd.DataFrame,
) -> dict[str, tuple[str, ...]]:
    """Build the `news_summaries` dict consumed by `run_scoring`.

    For every watchlist row, look up the row's asset_class, expand to its
    mapped themes (sorted ASC), and fetch each theme's `report_md` from
    `reports`. Failed or empty reports are skipped silently. The
    per-instrument value is a tuple of summary strings whose order matches
    the sorted theme-name order returned by `themes_for_instrument`.

    Pure function: no filesystem reads, no logging, no mutation.
    """
    if watchlist.empty:
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for row in watchlist.itertuples(index=False):
        iid = str(getattr(row, "instrument_id", ""))
        if not iid:
            continue
        asset_class = str(getattr(row, "asset_class", "") or "")
        themes = themes_for_instrument(asset_class)
        summaries = tuple(
            s for s in (_summary_for_theme(t, reports) for t in themes) if s
        )
        out[iid] = summaries
    return out
```

- [ ] **Step 4.2: Run all news_summaries tests**

Run:
```bash
uv run pytest tests/scoring/test_news_summaries.py -v
```
Expected: 19 passed (10 from Task 2 + 9 new `build_news_summaries` tests).

- [ ] **Step 4.3: Verify the module size budget (< 200 lines)**

Run:
```bash
wc -l src/irc/scoring/news_summaries.py
```
Expected: a number well under 200 (target ~60–80).

- [ ] **Step 4.4: Commit**

Run:
```bash
git add src/irc/scoring/news_summaries.py tests/scoring/test_news_summaries.py
git commit -m "test+feat(scoring): build_news_summaries pure assembler over theme reports"
```
Expected: one commit recorded; tree clean.

---

## Task 5: Red regression test in pipeline — non-empty `news_summaries` ⇒ non-50 score

**Files:**
- Modify: `tests/scoring/test_pipeline.py`

- [ ] **Step 5.1: Inspect the existing pipeline test for fixture patterns**

Run:
```bash
uv run pytest tests/scoring/test_pipeline.py -v --collect-only
```
Expected: a list of existing tests; note any helper fixtures defined at module scope so the new test can reuse them. (Read the file to confirm.)

- [ ] **Step 5.2: Append a regression test**

Append the following block to `tests/scoring/test_pipeline.py`. The test calls `run_scoring` directly (the same entrypoint `score_cmd.run_score` calls) and asserts the `thesis_news` factor lands somewhere other than 50.0 for an instrument whose news_summaries contain positive keywords from `_POS`.

```python


def test_run_scoring_with_non_empty_news_summaries_differentiates_thesis_news():
    """Regression for F4: when news_summaries is non-empty, the thesis_news
    factor must escape the empty-input 50.0 fallback for the matching row.
    Locks the call-site contract at src/irc/scoring/pipeline.py:116-119.
    """
    import pandas as pd

    from irc.config_loader import load_repo_configs
    from irc.scoring.pipeline import run_scoring

    # Two-row watchlist: gold has positive news, cn_bond_fund has none.
    watchlist = pd.DataFrame([
        {
            "instrument_id": "518880",
            "ticker": "518880",
            "name_cn": "黄金ETF",
            "asset_class": "gold",
            "market": "cn_on_exchange",
            "tracked_index": "",
            "cited_refs": "",
            "role": "satellite",
        },
        {
            "instrument_id": "511880",
            "ticker": "511880",
            "name_cn": "国债ETF",
            "asset_class": "cn_bond_fund",
            "market": "cn_on_exchange",
            "tracked_index": "",
            "cited_refs": "",
            "role": "core",
        },
    ])
    metrics = pd.DataFrame([
        {"instrument_id": "518880"},
        {"instrument_id": "511880"},
    ])
    news_summaries = {
        # Hits two _POS terms ("demand", "buy"): momentum +1, base 80.
        "518880": ("Strong demand and central bank buy signals.",),
        # No mapped theme content → fallback path.
        "511880": (),
    }

    # load_repo_configs needs a real repo root for scoring weights; the test
    # repo is the project root itself.
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    bundle = load_repo_configs(repo_root)

    out = run_scoring(
        watchlist=watchlist,
        metrics=metrics,
        news_summaries=news_summaries,
        regime_summary="",
        route=None,  # macro_fit catches None and returns neutral 50
        cfg_scoring=bundle.scoring,
        qdii_premium_resolver=None,
    )
    scores = {row["instrument_id"]: row for row in out["scores"]}

    # AMENDMENT (impl agent, 2026-05-27): factor_breakdown["thesis_news"] is a dict
    # {"score": float, "raw_refs": [...], "components": {...}} per instrument_score.py:59-65.
    # Plan originally accessed the dict directly; corrected to use ["score"] key.
    gold_thesis = scores["518880"]["factor_breakdown"]["thesis_news"]["score"]
    bond_thesis = scores["511880"]["factor_breakdown"]["thesis_news"]["score"]

    # Gold row sees real positive news → must escape the 50.0 fallback.
    assert gold_thesis != 50.0, (
        f"thesis_news for gold should differentiate from 50.0 fallback; got {gold_thesis}"
    )
    # Bond row has empty summaries → preserves the empty-input invariant.
    assert bond_thesis == 50.0, (
        f"thesis_news for cn_bond_fund must preserve 50.0 fallback; got {bond_thesis}"
    )
```

- [ ] **Step 5.3: Verify the regression test fails for the right reason if hard-coded fallback is reintroduced (sanity), then passes today**

Run:
```bash
uv run pytest tests/scoring/test_pipeline.py::test_run_scoring_with_non_empty_news_summaries_differentiates_thesis_news -v
```
Expected: PASS — `run_scoring` at `src/irc/scoring/pipeline.py:116` already routes `news_summaries.get(r.instrument_id, ())` into `score_thesis_news`; the failing edge today is the call site, not the consumer. This test locks the consumer contract so a future refactor cannot quietly regress it.

If the test fails: the consumer at `pipeline.py:116` has drifted from the design in ADR 0007 §4. Stop and reconcile before continuing.

- [ ] **Step 5.4: Commit**

Run:
```bash
git add tests/scoring/test_pipeline.py
git commit -m "test(scoring): lock pipeline.run_scoring consumer contract for news_summaries"
```
Expected: one commit recorded; tree clean.

---

## Task 6: Red — integration test that `score_cmd.run_score` no longer ships `news_summaries={}`

**Files:**
- Modify: `tests/scoring/test_news_summaries.py`

- [ ] **Step 6.1: Append a wiring-test that intercepts `run_scoring` from inside `score_cmd`**

Append to `tests/scoring/test_news_summaries.py`:

```python


def test_score_cmd_run_score_passes_non_empty_news_summaries_when_research_exists(
    tmp_path, monkeypatch,
):
    """Plumbing AC #1 + AC #10: when data/research/research_status.json exists
    with at least one populated theme report, score_cmd.run_score must call
    run_scoring with a non-empty news_summaries dict (not {}).
    """
    import json
    from pathlib import Path

    import pandas as pd

    # 1) Stage a minimal repo skeleton under tmp_path: configs, watchlist,
    #    research outputs, and a DuckDB file.
    repo_root = tmp_path
    (repo_root / "outputs" / "2099-01-01").mkdir(parents=True)
    (repo_root / "data" / "research").mkdir(parents=True)
    (repo_root / "data").mkdir(exist_ok=True)
    (repo_root / "config").mkdir(exist_ok=True)

    # Minimal watchlist with one gold row (gold maps to three themes).
    watchlist_df = pd.DataFrame([{
        "instrument_id": "518880",
        "ticker": "518880",
        "name_cn": "黄金ETF",
        "asset_class": "gold",
        "market": "cn_on_exchange",
        "tracked_index": "",
        "cited_refs": "",
        "role": "satellite",
    }])
    watchlist_df.to_csv(
        repo_root / "outputs" / "2099-01-01" / "discovered_watchlist.csv",
        index=False,
    )

    # Stage one populated theme report (gold_drivers).
    theme_md = repo_root / "data" / "research" / "gold_drivers.md"
    theme_md.write_text("# gold_drivers\n\nStrong demand for gold.\n", encoding="utf-8")
    status = {
        "generated_at_iso": "2099-01-01T00:00:00+00:00",
        "overall": "pass",
        "theme_count": 1,
        "failure_count": 0,
        "themes": [{
            "theme": "gold_drivers",
            "query": "",
            "locale": "EN",
            "report_path": "data/research/gold_drivers.md",
            "citation_count": 0,
            "citations": [],
            "failure_reason": "",
            "provider_failures": [],
        }],
    }
    (repo_root / "data" / "research" / "research_status.json").write_text(
        json.dumps(status, ensure_ascii=False), encoding="utf-8",
    )

    # 2) Pin today() to the staged date and stub the I/O surface so the test
    #    stays pure-function-shaped (no DuckDB, no LLM).
    from irc.commands import score_cmd

    monkeypatch.setattr(score_cmd, "_today", lambda: "2099-01-01")
    monkeypatch.setattr(score_cmd, "_macro_summary", lambda con: "")

    class _StubCon:
        def execute(self, *a, **kw):  # pragma: no cover - safety net
            class _R:
                def fetchall(self_inner): return []
            return _R()
        def close(self): pass

    monkeypatch.setattr(score_cmd, "connect", lambda path: _StubCon())
    monkeypatch.setattr(score_cmd, "ensure_schema", lambda con: None)
    monkeypatch.setattr(
        score_cmd, "load_scoring_metrics",
        lambda con, ids: pd.DataFrame([{"instrument_id": iid} for iid in ids]),
    )
    monkeypatch.setattr(score_cmd, "resolve_route", lambda task, llm_cfg: None)

    # Intercept run_scoring to capture the news_summaries kwarg.
    captured: dict = {}

    def _fake_run_scoring(**kwargs):
        captured.update(kwargs)
        return {"scores": [{
            "instrument_id": "518880",
            "composite_score": 50.0,
            "action": "hold",
            "conviction": "low",
            "factor_breakdown": {},
            "data_completeness": 0.0,
            "missing_data": [],
            "weights_version": "v1",
        }]}

    monkeypatch.setattr(score_cmd, "run_scoring", _fake_run_scoring)

    # 3) Use the real load_repo_configs from the project repo; copy the
    #    config tree into tmp_path so loader resolves.
    import shutil
    project_root = Path(__file__).resolve().parents[2]
    shutil.copytree(project_root / "config", repo_root / "config", dirs_exist_ok=True)
    shutil.copytree(project_root / "inputs", repo_root / "inputs", dirs_exist_ok=True)

    rc = score_cmd.run_score(str(repo_root))
    assert rc == 0
    assert "news_summaries" in captured
    ns = captured["news_summaries"]
    # AC #1: dict is non-empty (every watchlist row gets a key).
    assert ns, f"news_summaries should be non-empty when research exists; got {ns!r}"
    # AC #1 specifically: the gold row resolves to a non-empty tuple
    # because gold_drivers is populated.
    assert ns["518880"], (
        f"gold row should map to non-empty news prose; got {ns['518880']!r}"
    )
    assert any("Strong demand for gold" in s for s in ns["518880"])
```

- [ ] **Step 6.2: Run the new wiring test; verify it fails**

Run:
```bash
uv run pytest tests/scoring/test_news_summaries.py::test_score_cmd_run_score_passes_non_empty_news_summaries_when_research_exists -v
```
Expected: FAIL. The reason should be that `captured["news_summaries"]` is `{}` (still the literal at `score_cmd.py:69`). If the failure is instead an `ImportError`, configure-related, or fixture-related, stop and reconcile.

---

## Task 7: Green — wire `build_news_summaries` into `score_cmd.run_score`

**Files:**
- Modify: `src/irc/commands/score_cmd.py`

- [ ] **Step 7.1: Add the imports**

Open `src/irc/commands/score_cmd.py` and locate the import block at the top. Add these two imports next to the other `irc.*` imports (keep alphabetical-ish grouping):

```python
from irc.research.persistence import load_theme_reports
from irc.scoring.news_summaries import build_news_summaries
```

The relevant section should end up like:

```python
from irc.config_loader import load_repo_configs
from irc.data.akshare_client import fetch_qdii_premium_pct
from irc.data.duckdb_helper import connect, ensure_schema
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route
from irc.research.persistence import load_theme_reports
from irc.scoring.metrics_loader import load_scoring_metrics
from irc.scoring.news_summaries import build_news_summaries
from irc.scoring.pipeline import run_scoring
from irc.scoring.qdii_premium import qdii_premium_for_row
```

- [ ] **Step 7.2: Replace the `news_summaries={}` literal**

In `src/irc/commands/score_cmd.py`, locate the `out = run_scoring(...)` call (currently around line 66–74). Replace the line:

```python
        news_summaries={},
```

with:

```python
        news_summaries=build_news_summaries(
            reports=load_theme_reports(root),
            watchlist=watchlist,
        ),
```

The resulting call should read:

```python
    out = run_scoring(
        watchlist=watchlist,
        metrics=metrics,
        news_summaries=build_news_summaries(
            reports=load_theme_reports(root),
            watchlist=watchlist,
        ),
        regime_summary=regime,
        route=route,
        cfg_scoring=bundle.scoring,
        qdii_premium_resolver=_resolve_qdii_premium,
    )
```

- [ ] **Step 7.3: Re-run the wiring test; verify pass**

Run:
```bash
uv run pytest tests/scoring/test_news_summaries.py::test_score_cmd_run_score_passes_non_empty_news_summaries_when_research_exists -v
```
Expected: PASS.

- [ ] **Step 7.4: Greppable AC — confirm the literal is gone**

Run:
```bash
git grep -n "news_summaries={}" src/irc/commands/score_cmd.py
```
Expected: empty output (no match). This is spec AC #10.

- [ ] **Step 7.5: Commit the wiring**

Run:
```bash
git add src/irc/commands/score_cmd.py tests/scoring/test_news_summaries.py
git commit -m "feat(scoring): wire thesis_news real-content scoring via news_summaries plumbing"
```
Expected: one commit recorded; tree clean.

---

## Task 8: Run the full scoring suite and lint gates

- [ ] **Step 8.1: Run the entire scoring test tree**

Run:
```bash
uv run pytest tests/scoring -v
```
Expected: all green. Specifically:
- existing `tests/scoring/factors/test_thesis_news.py` — 3 passed (unchanged, including `test_no_news_returns_neutral_with_low_completeness` proving the empty-input invariant is preserved per spec AC #5).
- new `tests/scoring/test_news_summaries.py` — 20 passed (10 mapping + 9 builder + 1 score_cmd wiring).
- existing `tests/scoring/test_pipeline.py` — original tests still pass + the new regression test from Task 5 passes.

If anything fails, stop and reconcile against the spec.

- [ ] **Step 8.2: Run ruff**

Run:
```bash
uv run ruff check src tests
```
Expected: no findings. If ruff flags any line in the new module or modified `score_cmd.py` (e.g. line length, unused imports), fix in place and re-run.

- [ ] **Step 8.3: Run the broader (non-network) unit suite as a sanity sweep**

Run:
```bash
uv run pytest -q
```
Expected: full green. F4 changes are confined to scoring; no other suite should react.

If anything outside `tests/scoring/` fails: investigate whether it was already failing on `autodev/pickability-followups-feature` before this branch (run `git stash && uv run pytest <path> -q` on the feature branch's tip). Do not blanket-disable failing tests.

---

## Task 9: End-state acceptance check + final greppable AC

- [ ] **Step 9.1: Confirm spec AC #10 (greppable)**

Run:
```bash
git grep -n "news_summaries={}" src/irc/commands/score_cmd.py
echo "exit=$?"
```
Expected: no matching lines; `git grep` exits non-zero (`exit=1`) which is fine — the assertion is "no matches".

- [ ] **Step 9.2: Confirm the immutability guard is real**

Run:
```bash
uv run python -c "from irc.scoring.news_summaries import THEMES_BY_ASSET_CLASS; \
import types; assert isinstance(THEMES_BY_ASSET_CLASS, types.MappingProxyType); \
print('THEMES_BY_ASSET_CLASS is MappingProxyType — OK')"
```
Expected: `THEMES_BY_ASSET_CLASS is MappingProxyType — OK`.

- [ ] **Step 9.3: Confirm the empty-input invariant is byte-untouched**

Run:
```bash
uv run pytest tests/scoring/factors/test_thesis_news.py::test_no_news_returns_neutral_with_low_completeness -v
```
Expected: PASS. Spec AC #5.

- [ ] **Step 9.4: Confirm `_POS` / `_NEG` lexicons are unchanged**

Run:
```bash
git diff autodev/pickability-followups-feature -- src/irc/scoring/factors/thesis_news.py
```
Expected: empty diff (no change). Spec non-goal #2 + ADR 0007 §1.

---

## Task 10: Verify branch state for handoff

- [ ] **Step 10.1: Inspect the per-branch commit log**

Run:
```bash
git log --oneline autodev/pickability-followups-feature..HEAD
```
Expected: three to four commits on top of `autodev/pickability-followups-feature`:
1. `test+feat(scoring): add THEMES_BY_ASSET_CLASS + themes_for_instrument (pure)`
2. `test+feat(scoring): build_news_summaries pure assembler over theme reports`
3. `test(scoring): lock pipeline.run_scoring consumer contract for news_summaries`
4. `feat(scoring): wire thesis_news real-content scoring via news_summaries plumbing`

- [ ] **Step 10.2: Confirm tree is clean and branch is ready for PR**

Run:
```bash
git status
git branch --show-current
```
Expected: working tree clean; on branch `claude/pickability-followups-F4`. **Do NOT push.** The orchestrator handles the PR open against `autodev/pickability-followups-feature`.

---

## Verification map (spec AC → plan task)

| Spec AC | Where it is satisfied |
|---|---|
| #1 — `news_summaries` non-empty when research exists | Task 6 wiring test + Task 7 implementation |
| #2 — `themes_for_instrument(asset_class)` pure mapping | Task 1 test + Task 2 implementation |
| #3 — `build_news_summaries(reports, watchlist)` pure, no I/O | Task 3 test + Task 4 implementation |
| #4 — Production differentiation (measured, not gated) | Out of plan scope — measured post-ship via `outputs/2026-05-27/scoring.json`. Plan delivers the plumbing that makes the measurement meaningful (Task 5 regression locks the consumer side). If <3-of-top-10 differ by ≥10pt, add SKIPPED entry `F4-followup-llm-rubric` per ADR 0007 §5. |
| #5 — Empty-input invariant preserved | Task 9.3 explicit re-run + Task 9.4 lexicon diff guard |
| #6 — Determinism (byte-equal `scoring.json`) | Task 3 (`test_build_news_summaries_is_deterministic_two_calls_equal`) + sorted-tuple invariant verified by Task 1's `test_themes_for_instrument_returns_sorted_ascending`. Scoring-output byte equality is downstream of these two layers — the existing pipeline is already deterministic given deterministic inputs. |
| #7 — Tests cover new code (TDD red-first) | Tasks 1, 3, 5, 6 all write red tests before the matching green implementation in Tasks 2, 4, 7. |
| #8 — ADR 0007 lands | Already present at `docs/adr/0007-thesis-news-scoring.md` (grill phase committed it). No plan task needed. |
| #9 — No regression in `IRC_*_BEGIN/END` / H3 / SAME-3 | Task 8.3 full-suite sweep. Plan touches no memo / opportunity / discipline code. |
| #10 — `news_summaries={}` literal gone | Task 7.4 + Task 9.1 explicit grep. |

## Judgment-call notes (for the impl agent)

- **DataFrame iteration order.** Spec/ADR §4 invokes "CSV row order"; pandas `itertuples(index=False)` preserves it. The new module relies on this; if a future change introduces a `set_index`-based iteration, the determinism contract must be reasserted with a regression test. Out of scope for F4.
- **Empty `instrument_id`.** Defensive guard added in Task 4.1 (`if not iid: continue`) — not specified by ADR 0007 but obvious for a real-world CSV; not tested explicitly. If the impl agent prefers strictness, they may drop the guard and add an assertion; either is acceptable.
- **Test 6 fixture surface.** `score_cmd.run_score` reaches into DuckDB and the LLM router; the wiring test stubs both via `monkeypatch`. This keeps the test fast and gate-free per spec Q24 ("no live-test gate needed"). The stubs are explicit at the function level and disappear at test teardown.
