# Research Stack Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the research-stack replacement so the Tavily/Brave/Bocha/Jina implementation is operable, evaluable, documented, and consumed by the opportunity layer.

**Architecture:** Keep HTTP adapters isolated and pure-ish, but add a persistence/status boundary around `run_research_pipeline`. `irc research` should support narrow smoke tests, write markdown plus machine-readable status, and never halt the full pipeline just because one locale/provider is missing. Opportunity CLI should read cached constituent snapshots plus persisted theme reports and pass them into the already-pure `build_opportunity_row(..., snapshot=..., theme_report=...)` path.

**Tech Stack:** Python 3.12, Click, pytest, dataclasses, existing `irc.io_utils.atomic_write_text`, existing research/fundamentals/opportunity modules.

---

## Current Implementation Status And Gap Map

### 1. What Is Already There

The core research replacement exists. This plan should not rewrite it; it should finish the missing operational seams around it.

- **Search adapter contracts and providers are implemented.** `src/irc/research/search/types.py` defines `Locale`, `SearchHit`, `SearchResult`, `ExtractedPage`, and the provider protocols. `tavily_provider.py`, `brave_provider.py`, `bocha_provider.py`, and `jina_reader.py` normalize provider responses into these dataclasses and return `failure_reason` instead of raising for expected HTTP/JSON failures.
- **Provider construction is implemented.** `src/irc/research/search/factory.py` reads `Settings` and constructs only the providers with configured keys: Tavily, Brave, Bocha, plus Jina Reader as the extractor.
- **Theme research orchestration is implemented.** `src/irc/research/theme_research.py` maps themes to EN/ZH locales, searches, extracts top pages, calls `synthesize_report`, and returns `ThemeReport` objects.
- **Bounded synthesis is implemented.** `src/irc/research/synthesize.py` builds citations from the input source pool and performs one `call_chat` call through the existing `research_synth` LLM route.
- **Pipeline-level research execution exists.** `src/irc/research/pipeline.py` writes per-theme markdown files under `data/research/<theme>.md`.
- **Settings and `.env.example` are mostly current.** `src/irc/settings.py` has `tavily_api_key`, `brave_api_key`, `bocha_api_key`, and `jina_api_key`; `.env.example` documents the new keys and `RESEARCH_ENABLED`.
- **The LDR client code path is removed from `src/irc/research/`.** No `ldr_client.py` remains in the source tree.
- **Fundamentals snapshot primitives are implemented.** `src/irc/fundamentals/` contains dataclasses, CN/US/HK fetchers, `build_snapshot`, `write_snapshot`, `load_cached_snapshot`, and JSON cache layout support.
- **Pure opportunity thesis derivation is implemented.** `src/irc/opportunity/thesis_evidence.py` derives `thesis_state`, typed `evidence_gaps`, and capped `thesis_evidence` from `ConstituentSnapshot` plus `ThemeReport`.
- **Opportunity rows can already accept evidence inputs.** `build_opportunity_row(..., snapshot=None, theme_report=None)` exists and prefers the deterministic evidence path when either input is supplied.
- **Focused tests are green before this plan starts.** Verification command `uv run pytest tests/research tests/fundamentals tests/commands/test_research_cmd.py tests/commands/test_run_cmd.py tests/evals/test_research_metrics.py tests/evals/test_spot_check.py tests/opportunity/test_states.py -q` reported `162 passed`.

### 2. Confirmed Gaps

The missing work is not another adapter rewrite. The missing work is operability, diagnostics, eval alignment, documentation, and end-to-end evidence consumption.

| Gap | Why It Matters | Required Work | Covered By |
| :--- | :--- | :--- | :--- |
| README still documents LDR install, `LDR_ENABLED`, and old LDR quarterly research commands. | User setup instructions are wrong; new API keys and output checks are not discoverable. | Remove LDR instructions; add `RESEARCH_ENABLED`, search keys, smoke tests, output inspection, and error inspection. | Task 8 |
| `irc research` has no `--theme` option. | Spec first-run checklist cannot be executed; users cannot smoke-test EN and ZH paths independently. | Add repeatable `--theme` option and pass selected themes into `run_research_pipeline`. | Task 1 |
| Research output has only markdown. | Users cannot quickly check which themes failed, which providers failed, citation counts, or output paths. | Add `data/research/research_status.json` with per-theme status, citations, provider diagnostics, and failure reasons. | Tasks 2-3 |
| Provider failure details are dropped after search fan-out. | Partial degradation is invisible when one provider succeeds and another fails. | Add a diagnostic helper that preserves raw `SearchResult` objects and persist `provider_failures`. | Task 3 |
| `run_research_pipeline` returns nonzero when any theme fails. | `RESEARCH_ENABLED=true uv run irc run` can halt on a degraded theme, contrary to the spec's “degrade evidence, do not halt” behavior. | Return `0` for completed research runs and represent per-theme failures in status JSON. | Task 2 |
| `evals/research` still reads `outputs/research/reports.json` and uses `ldr_citation_validity`. | Research eval is measuring the removed implementation, not the new stack. | Read `data/research/research_status.json`; replace LDR metrics with theme coverage, success rate, citation validity, and failure visibility. | Task 7 |
| Spot-check eval still samples `ldr_citations`. | Manual review queue vocabulary is stale and points reviewers at the wrong artifact type. | Rename to `research_citations` and keep behavior otherwise identical. | Task 7 |
| `irc opportunity` does not pass `snapshot` or `theme_report` into `build_opportunity_row`. | The pure deterministic thesis evidence path is implemented but not exercised end-to-end. | Load persisted theme reports and latest cached snapshots, then pass both into `build_opportunity_row`. | Task 4 |
| `_TARGET_REGISTRY` only registers `沪深300` and `中证500`. | `LookthroughTarget.display_cn` resolves to `中证1000`, `上证50`, `科创50`, `中证红利`, etc. for broad-index instruments; without registry entries Task 4 wiring lands but `load_latest_cached_snapshot` returns `None` for every theme except two, leaving the spec acceptance criterion *"each `thesis_card` with `thesis_state != evidence_insufficient` carries at least one `thesis_evidence` entry"* unverifiable in practice. | Extend `_TARGET_REGISTRY` to cover every entry in `_BROAD_INDEX_DISPLAY`, with a coupling test so future drift between the two modules surfaces in CI. Sector themes (`半导体`, `医药`, …) and QDII targets (`纳斯达克100`, `恒生科技`, …) are explicit follow-up. | Task 5 |
| There is no CLI workflow for quarterly snapshot rebuilds. | `data/fundamentals/<quarter>/<target>.json` can exist in tests, but users have no command to refresh it operationally. | Add `irc fundamentals snapshot --target ...` command that calls `build_snapshot` and `write_snapshot`. | Task 6 |

### 3. What Needs To Be Done

Implement the work in this order:

1. Add targeted `irc research --theme` runs so EN/ZH smoke tests are possible.
2. Add research persistence: markdown plus `research_status.json`, with completed degraded runs returning `0`.
3. Preserve provider diagnostics and expose them in `research_status.json`.
4. Wire persisted research reports and cached snapshots into `irc opportunity`.
5. Expand `_TARGET_REGISTRY` so `LookthroughTarget.display_cn` outputs for broad CN indices actually resolve to real snapshot specs, and add a coupling test between `_BROAD_INDEX_DISPLAY` and `_TARGET_REGISTRY` so the two modules cannot drift silently.
6. Add an explicit fundamentals snapshot rebuild command for quarterly cache refreshes.
7. Modernize research and spot-check evals to read the new artifacts and names.
8. Update README so setup, search changes, output checks, and error checks match the implementation (do not duplicate the DCA-action interpretation block already shipped in plan 5).
9. Document the change in `CHANGELOG.md`.

---

## File Structure

Modify:

- `src/irc/cli.py` — add `--theme` option to `irc research`; register `irc fundamentals snapshot`.
- `src/irc/commands/research_cmd.py` — accept selected themes, load env, pass selected themes into pipeline.
- `src/irc/research/theme_research.py` — preserve per-provider diagnostics and expose enough data for status output.
- `src/irc/research/search/dispatch.py` — add diagnostic search helper without breaking existing `multi_provider_search` callers.
- `src/irc/research/pipeline.py` — write markdown and `data/research/research_status.json`; return 0 for completed runs with visible theme failures.
- `src/irc/commands/opportunity_cmd.py` — load theme reports and cached snapshots, pass them into `build_opportunity_row`.
- `src/irc/fundamentals/snapshot.py` — add a public helper for the current cache quarter or latest cached snapshot lookup.
- `evals/research/metrics.py` — replace LDR metrics with research-stack metrics.
- `evals/research/runner.py` — read `data/research/research_status.json`.
- `evals/spot_check/runner.py` and tests — rename `ldr_citations` sampling to `research_citations`.
- `README.md` — remove LDR, add env/search/output/error/eval instructions.
- `CHANGELOG.md` — document the user-facing research-stack completion.

Create:

- `src/irc/research/persistence.py` — serialize/deserialize `ThemeReport` status and markdown.
- `src/irc/commands/fundamentals_cmd.py` — quarterly snapshot rebuild command wrapper.
- `tests/research/test_persistence.py` — persistence behavior.
- `tests/commands/test_fundamentals_cmd.py` — snapshot rebuild command behavior.

Update tests:

- `tests/commands/test_research_cmd.py`
- `tests/commands/test_fundamentals_cmd.py`
- `tests/commands/test_run_cmd.py` (specifically `test_pipeline_fails_fast_on_enabled_research_failure` — see Task 2)
- `tests/research/test_pipeline.py`
- `tests/research/test_theme_research.py`
- `tests/research/search/test_dispatch.py`
- `tests/evals/test_research_metrics.py`
- `tests/evals/test_spot_check.py`
- `tests/commands/test_opportunity_cmd.py`
- `tests/opportunity/test_lookthrough.py` (registry coupling — see Task 5)
- `tests/fundamentals/test_snapshot.py`

Keep green (no behavioral change required, but verify after Task 4 lands):

- `tests/integration/test_decision_without_opportunity.py` — the spec's "decision command works when opportunity outputs are absent" regression guard.

---

### Task 1: Add Targeted Research CLI Runs

**Files:**

- Modify: `src/irc/cli.py`
- Modify: `src/irc/commands/research_cmd.py`
- Test: `tests/commands/test_research_cmd.py`

- [ ] **Step 1: Write failing tests for selected themes**

Add tests that prove selected themes reach the pipeline unchanged:

```python
def test_research_cmd_accepts_selected_themes(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    other_cwd = tmp_path / "elsewhere"
    repo_root.mkdir()
    other_cwd.mkdir()
    (repo_root / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-test\nTAVILY_API_KEY=tvly-test\nBOCHA_API_KEY=bocha-test\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(other_cwd)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    with patch("irc.commands.research_cmd.run_research_pipeline", return_value=0) as mock_pipeline, \
         patch("irc.commands.research_cmd.load_repo_configs") as mock_cfg, \
         patch("irc.commands.research_cmd.resolve_route") as mock_route:
        mock_cfg.return_value.llm = object()
        mock_route.return_value = object()
        rc = run_research(repo_root=str(repo_root), themes=("us_monetary", "cn_monetary"))

    assert rc == 0
    assert mock_pipeline.call_args.kwargs["themes"] == ("us_monetary", "cn_monetary")
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest tests/commands/test_research_cmd.py::test_research_cmd_accepts_selected_themes -q
```

Expected: fails because `run_research()` does not accept `themes`.

- [ ] **Step 3: Implement `themes` argument in command wrapper**

Change `run_research` signature and default:

```python
def run_research(repo_root: str, themes: tuple[str, ...] = _DEFAULT_THEMES) -> int:
    ...
    return run_research_pipeline(
        repo_root=root,
        themes=themes,
        providers=providers,
        extractor=extractor,
        route=route,
    )
```

- [ ] **Step 4: Add Click option**

Update `irc research`:

```python
@main.command(help="Run web-research jobs; write data/research/<theme>.md.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--theme", "themes", multiple=True, help="Theme key to run. Repeat for multiple themes. Defaults to all configured research themes.")
def research(repo_root: str, themes: tuple[str, ...]) -> None:
    from irc.commands.research_cmd import run_research
    rc = run_research(repo_root=repo_root, themes=themes or None)
    raise SystemExit(rc)
```

If `themes or None` is used, make `run_research(..., themes: tuple[str, ...] | None = None)` and normalize to `_DEFAULT_THEMES` inside the function.

- [ ] **Step 5: Verify command help**

Run:

```bash
uv run irc research --help
```

Expected: help includes `--theme` and no LDR wording.

---

### Task 2: Persist Research Status And Errors

**Files:**

- Create: `src/irc/research/persistence.py`
- Modify: `src/irc/research/pipeline.py`
- Test: `tests/research/test_pipeline.py`
- Test: `tests/research/test_persistence.py`

- [ ] **Step 1: Write failing pipeline status test**

Add to `tests/research/test_pipeline.py`:

```python
def test_research_pipeline_writes_status_json(mock_build, tmp_path: Path):
    mock_build.return_value = [_ok_report("us_monetary"), _failed_report("gold_drivers", "timeout")]
    rc = run_research_pipeline(
        repo_root=tmp_path,
        themes=("us_monetary", "gold_drivers"),
        providers=(),
        extractor=None,  # type: ignore[arg-type]
        route=_route(),
    )

    status_path = tmp_path / "data/research/research_status.json"
    assert rc == 0
    assert status_path.exists()
    body = json.loads(status_path.read_text(encoding="utf-8"))
    assert body["overall"] == "warn"
    assert body["themes"][0]["theme"] == "us_monetary"
    assert body["themes"][0]["citation_count"] == 1
    assert body["themes"][1]["failure_reason"] == "timeout"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest tests/research/test_pipeline.py::test_research_pipeline_writes_status_json -q
```

Expected: fails because no status file exists and current rc is 2.

- [ ] **Step 3: Add persistence helpers**

Implement `src/irc/research/persistence.py`:

```python
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from irc.io_utils import atomic_write_text
from irc.research.synthesize import Citation
from irc.research.theme_research import ThemeReport


def format_report_markdown(report: ThemeReport) -> str:
    if report.failure_reason:
        return f"# {report.theme}\n\n_research failed: {report.failure_reason}_\n"
    cit_lines = "\n".join(
        f"[{c.index}] {c.title} — {c.url}" for c in report.citations
    )
    return f"# {report.theme}\n\n{report.report_md}\n\n## Citations\n{cit_lines}\n"


def status_for_reports(reports: list[ThemeReport]) -> dict[str, Any]:
    failures = [r for r in reports if r.failure_reason]
    return {
        "generated_at_iso": datetime.now(timezone.utc).isoformat(),
        "overall": "pass" if not failures else "warn",
        "theme_count": len(reports),
        "failure_count": len(failures),
        "themes": [
            {
                "theme": r.theme,
                "query": r.query,
                "locale": r.locale,
                "report_path": f"data/research/{r.theme}.md",
                "citation_count": len(r.citations),
                "citations": [asdict(c) for c in r.citations],
                "failure_reason": r.failure_reason,
            }
            for r in reports
        ],
    }


def write_research_outputs(out_dir: Path, reports: list[ThemeReport]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for report in reports:
        atomic_write_text(out_dir / f"{report.theme}.md", format_report_markdown(report))
    import json
    atomic_write_text(
        out_dir / "research_status.json",
        json.dumps(status_for_reports(reports), ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 4: Use persistence in pipeline**

Replace `_format_report` logic in `src/irc/research/pipeline.py` with `write_research_outputs(out_dir, reports)` and return `0` for a *completed* run, including runs where individual themes carry `failure_reason`. Unrecoverable conditions (build_theme_reports raised, no providers AND no configured keys to even attempt research, IO error writing the status file) must still propagate non-zero so the parent pipeline can fail loudly. Document this contract in the function docstring.

- [ ] **Step 5: Update old rc expectation**

Change `test_research_pipeline_returns_nonzero_when_any_theme_fails` to expect `rc == 0`, status `overall == "warn"`, and markdown containing `research failed`.

- [ ] **Step 6: Confirm `test_run_cmd.py` regression guard still encodes "unrecoverable errors are fatal"**

`tests/commands/test_run_cmd.py::test_pipeline_fails_fast_on_enabled_research_failure` injects a fake research runner that returns `2` and asserts `run_pipeline` halts. This test must keep passing — Task 2's "rc=0 for degraded runs" only relaxes per-theme failures inside `run_research_pipeline`; the parent `run_pipeline`'s fail-fast contract for true non-zero exits is unchanged. If the test currently relies on `run_research_pipeline`'s old rc=2 semantic (rather than an injected fake), rewrite it to inject a fake runner that returns 2 explicitly so the regression guard tests the parent's behavior, not the now-removed child semantic.

- [ ] **Step 7: Run pipeline tests**

Run:

```bash
uv run pytest tests/research/test_pipeline.py tests/research/test_persistence.py -q
```

Expected: all pass.

---

### Task 3: Preserve Provider Diagnostics

**Files:**

- Modify: `src/irc/research/search/dispatch.py`
- Modify: `src/irc/research/theme_research.py`
- Modify: `src/irc/research/persistence.py`
- Test: `tests/research/search/test_dispatch.py`
- Test: `tests/research/test_theme_research.py`

- [ ] **Step 1: Write failing diagnostic helper test**

Add a helper that returns raw `SearchResult` records without changing existing `multi_provider_search`:

```python
def test_provider_results_keeps_failure_reasons():
    a = FakeProvider(name="a", locale=Locale.EN, failure="timeout")
    b = FakeProvider(name="b", locale=Locale.EN, hits_to_return=(_hit("https://x/1"),))

    results = provider_results("q", Locale.EN, (a, b), max_results=5)

    assert [r.provider for r in results] == ["a", "b"]
    assert results[0].failure_reason == "timeout"
    assert results[1].hits[0].url == "https://x/1"
```

- [ ] **Step 2: Implement `provider_results`**

```python
def provider_results(
    query: str,
    locale: Locale,
    providers: tuple[SearchProvider, ...],
    *,
    max_results: int = 10,
    freshness_days: int | None = None,
    include_domains: tuple[str, ...] = (),
) -> tuple[SearchResult, ...]:
    out: list[SearchResult] = []
    for provider in providers:
        if provider.locale != locale:
            continue
        try:
            out.append(provider.search(
                query,
                max_results=max_results,
                freshness_days=freshness_days,
                include_domains=include_domains,
            ))
        except Exception as exc:
            out.append(SearchResult(
                query=query,
                locale=locale,
                provider=provider.name,
                failure_reason=f"provider raised: {exc}",
            ))
    return tuple(out)
```

Keep `multi_provider_search` as the compatibility wrapper that dedupes successful hits from these results.

- [ ] **Step 3: Extend `ThemeReport` diagnostics**

Add field:

```python
provider_failures: tuple[str, ...] = ()
```

Build values like `("tavily: timeout", "brave_news: http 503")` from `provider_results`.

- [ ] **Step 4: Persist diagnostics**

Add `provider_failures` to each theme entry in `research_status.json`.

- [ ] **Step 5: Verify diagnostics tests**

Run:

```bash
uv run pytest tests/research/search/test_dispatch.py tests/research/test_theme_research.py -q
```

Expected: all pass.

---

### Task 4: Wire Cached Research + Snapshots Into Opportunity CLI

**Files:**

- Modify: `src/irc/fundamentals/snapshot.py`
- Modify: `src/irc/commands/opportunity_cmd.py`
- Create or modify: `src/irc/research/persistence.py`
- Test: `tests/commands/test_opportunity_cmd.py`

- [ ] **Step 1: Add cached snapshot lookup helper test**

Add to `tests/fundamentals/test_snapshot.py`:

```python
def test_load_latest_cached_snapshot_picks_newest_quarter(tmp_path: Path) -> None:
    old = ConstituentSnapshot("沪深300", "2026-02-01", (), (), ())
    new = ConstituentSnapshot("沪深300", "2026-05-15", (), (), ())
    (tmp_path / "fundamentals/2025Q4").mkdir(parents=True)
    (tmp_path / "fundamentals/2026Q1").mkdir(parents=True)
    write_snapshot(old, tmp_path)
    write_snapshot(new, tmp_path)

    loaded = load_latest_cached_snapshot("沪深300", tmp_path)

    assert loaded is not None
    assert loaded.as_of_iso == "2026-05-15"
```

- [ ] **Step 2: Implement latest snapshot helper**

```python
def load_latest_cached_snapshot(
    lookthrough_target: str,
    root: Path,
) -> ConstituentSnapshot | None:
    base = root / "fundamentals"
    candidates = sorted(base.glob(f"*/{lookthrough_target}.json"))
    for path in reversed(candidates):
        quarter = path.parent.name
        loaded = load_cached_snapshot(lookthrough_target, quarter, root)
        if loaded is not None:
            return loaded
    return None
```

Callers should pass `repo_root / "data"` so the effective path is `data/fundamentals/<quarter>/<target>.json`.

- [ ] **Step 3: Add theme-report loader**

In `src/irc/research/persistence.py`:

```python
def load_theme_reports(root: Path) -> dict[str, ThemeReport]:
    status_path = root / "data" / "research" / "research_status.json"
    if not status_path.exists():
        return {}
    import json
    body = json.loads(status_path.read_text(encoding="utf-8"))
    reports: dict[str, ThemeReport] = {}
    for item in body.get("themes", []):
        theme = str(item.get("theme", ""))
        if not theme:
            continue
        md_path = root / item.get("report_path", f"data/research/{theme}.md")
        report_md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        citations = tuple(Citation(**c) for c in item.get("citations", []))
        reports[theme] = ThemeReport(
            theme=theme,
            query=str(item.get("query", "")),
            locale=str(item.get("locale", "")),
            report_md=report_md,
            citations=list(citations),
            failure_reason=str(item.get("failure_reason", "")),
            provider_failures=tuple(item.get("provider_failures", ())),
        )
    return reports
```

Adjust for the final `ThemeReport` field type chosen in Task 3.

- [ ] **Step 4: Write failing opportunity command test**

Patch `build_opportunity_row` and verify `snapshot` and `theme_report` kwargs are supplied when artifacts exist. Critical: the fixture's test instrument must use a `tracked_index` or `theme` whose `map_lookthrough(...).display_cn` matches an entry in `_TARGET_REGISTRY` (see Task 5). The simplest reliable choice is a CSI300-tracking instrument that resolves to `沪深300` — already in the V1 registry.

```python
def test_opportunity_cmd_passes_snapshot_and_theme_report(tmp_path: Path, monkeypatch) -> None:
    # Use the existing command fixtures in this file to create scoring/config/account.
    # The scoring/account fixture must reference an instrument whose lookthrough
    # display_cn is `沪深300` (already registered in _TARGET_REGISTRY).
    # Then write data/research/research_status.json and data/fundamentals/<quarter>/沪深300.json.
    # Patch irc.commands.opportunity_cmd.build_opportunity_row and assert kwargs.
    assert mock_build.call_args.kwargs["snapshot"] is not None
    assert mock_build.call_args.kwargs["theme_report"] is not None
```

Use the existing fixture helpers from `tests/commands/test_opportunity_cmd.py`; do not create a second full fixture system.

Also add a negative case: when `data/research/research_status.json` and the per-quarter snapshot file are both absent, `build_opportunity_row` is still called, but with `snapshot=None` and `theme_report=None`. This is the spec's degrade-evidence-do-not-halt contract.

- [ ] **Step 5: Implement opportunity wiring**

In `run_opportunity` before the scoring loop:

```python
from irc.fundamentals.snapshot import load_latest_cached_snapshot
from irc.opportunity.lookthrough import map_lookthrough
from irc.research.persistence import load_theme_reports

theme_reports = load_theme_reports(root)
snapshot_cache: dict[str, ConstituentSnapshot | None] = {}
```

Inside the loop, after `_build_input` and before `build_opportunity_row`:

```python
target = map_lookthrough(inp)
target_name = target.display_cn
if target_name not in snapshot_cache:
    snapshot_cache[target_name] = load_latest_cached_snapshot(target_name, root / "data")
row = build_opportunity_row(
    inp,
    theme_thesis or None,
    snapshot=snapshot_cache[target_name],
    theme_report=theme_reports.get(inp.theme or ""),
)
```

`LookthroughTarget.display_cn` is the current human-readable target name used by the snapshot cache, for example `沪深300`.

- [ ] **Step 6: Verify opportunity command tests + decision regression guard**

Run:

```bash
uv run pytest tests/commands/test_opportunity_cmd.py tests/opportunity/test_states.py tests/opportunity/test_thesis_evidence.py tests/integration/test_decision_without_opportunity.py -q
```

Expected: all pass. `tests/integration/test_decision_without_opportunity.py` is the spec's "decision command works when opportunity outputs are absent" guard and must stay green after the wiring change — if Task 4 introduces an import-time dependency or accidentally exercises opportunity from decision, this regression test catches it.

- [ ] **Step 7: Scope note for sector themes and QDII**

Document in `opportunity_cmd.py` (one-line comment above the snapshot lookup) that V1 broad-CN-index targets resolve to real snapshots while sector themes (`半导体`, `医药`, …) and QDII targets (`纳斯达克100`, `恒生科技`, …) currently miss the registry and fall through to `snapshot=None`. This is intentional for V1; expansion is tracked separately. Without the note, the `None` cache hits look like a bug.

---

### Task 5: Expand `_TARGET_REGISTRY` To Match `LookthroughTarget.display_cn`

**Files:**

- Modify: `src/irc/fundamentals/snapshot.py`
- Test: `tests/fundamentals/test_snapshot.py`
- Test: `tests/opportunity/test_lookthrough.py`

`_TARGET_REGISTRY` currently registers only `沪深300` and `中证500`. The opportunity layer (Task 4) calls `load_latest_cached_snapshot(target.display_cn, ...)`, where `target.display_cn` is produced by `map_lookthrough` and can be `中证1000`, `上证50`, `科创50`, `中证红利`, etc. Without registry entries, Task 4 wiring lands but exercises only two broad indices and the spec acceptance criterion *"each `thesis_card` with `thesis_state != evidence_insufficient` carries at least one `thesis_evidence` entry"* is never tested end-to-end. This task closes that gap for the broad-CN index family. Sector themes and QDII targets are explicit follow-up — they need sector-index codes and US/HK constituent universes that are not in scope here.

- [ ] **Step 1: Write failing test enforcing registry ⊇ broad-index display table**

Add to `tests/opportunity/test_lookthrough.py`:

```python
def test_target_registry_covers_broad_index_display_table() -> None:
    from irc.fundamentals.snapshot import _TARGET_REGISTRY
    from irc.opportunity.lookthrough import _BROAD_INDEX_DISPLAY

    missing = sorted(set(_BROAD_INDEX_DISPLAY.values()) - set(_TARGET_REGISTRY))
    assert missing == [], f"missing broad-index registry entries: {missing}"
```

- [ ] **Step 2: Run test and verify failure**

```bash
uv run pytest tests/opportunity/test_lookthrough.py::test_target_registry_covers_broad_index_display_table -q
```

Expected: fails listing the seven missing entries (`中证1000`, `中证A500`, `上证50`, `科创50`, `创业板`, `中证红利`, `红利低波`).

- [ ] **Step 3: Add registry entries with verified index codes**

Update `_TARGET_REGISTRY` in `src/irc/fundamentals/snapshot.py`:

```python
_TARGET_REGISTRY: dict[str, _TargetSpec] = {
    "沪深300":   _TargetSpec(kind="cn_index", code="000300"),
    "中证500":   _TargetSpec(kind="cn_index", code="000905"),
    "中证1000":  _TargetSpec(kind="cn_index", code="000852"),
    "中证A500":  _TargetSpec(kind="cn_index", code="000510"),
    "上证50":    _TargetSpec(kind="cn_index", code="000016"),
    "科创50":    _TargetSpec(kind="cn_index", code="000688"),
    "创业板":    _TargetSpec(kind="cn_index", code="399006"),
    "中证红利":  _TargetSpec(kind="cn_index", code="000922"),
    "红利低波":  _TargetSpec(kind="cn_index", code="930740"),
}
```

`code` must be the AkShare-compatible index symbol. If a code cannot be verified at implementation time, leave that single entry out and open a TODO — do not guess; an unverified code produces a snapshot of constituents from the wrong index.

- [ ] **Step 4: Document scope of the registry**

Replace the existing one-line comment above `_TARGET_REGISTRY` with:

```python
# Keys MUST equal values produced by
# `irc.opportunity.lookthrough.map_lookthrough(...).display_cn`. The coupling test
# in tests/opportunity/test_lookthrough.py prevents silent drift.
#
# V1 scope: broad CN equity indices only. Sector themes (`半导体`, `医药`, …)
# and QDII targets (`纳斯达克100`, `恒生科技`, …) resolve to `evidence_insufficient`
# thesis_state via the snapshot=None path in opportunity_cmd until their
# corresponding _TargetSpec entries are added.
```

- [ ] **Step 5: Verify**

```bash
uv run pytest tests/fundamentals/test_snapshot.py tests/opportunity/test_lookthrough.py -q
```

Expected: all pass.

---

### Task 6: Add Fundamentals Snapshot Rebuild Workflow

**Files:**

- Create: `src/irc/commands/fundamentals_cmd.py`
- Modify: `src/irc/cli.py`
- Test: `tests/commands/test_fundamentals_cmd.py`

- [ ] **Step 1: Write failing command wrapper tests**

Create `tests/commands/test_fundamentals_cmd.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from irc.commands.fundamentals_cmd import run_snapshot_rebuild
from irc.fundamentals.types import ConstituentSnapshot


def _snapshot(target: str = "沪深300") -> ConstituentSnapshot:
    return ConstituentSnapshot(
        lookthrough_target=target,
        as_of_iso="2026-05-15",
        constituents=(),
        filings=(),
        broker_reports=(),
        failure_reasons=(),
    )


def test_snapshot_rebuild_requires_at_least_one_target(tmp_path: Path) -> None:
    rc = run_snapshot_rebuild(repo_root=str(tmp_path), targets=(), top_n=10)

    assert rc == 2


def test_snapshot_rebuild_builds_and_writes_each_target(tmp_path: Path) -> None:
    output_path = tmp_path / "data" / "fundamentals" / "2026Q1" / "沪深300.json"
    with patch(
        "irc.commands.fundamentals_cmd.build_snapshot",
        return_value=_snapshot(),
    ) as mock_build, patch(
        "irc.commands.fundamentals_cmd.write_snapshot",
        return_value=output_path,
    ) as mock_write:
        rc = run_snapshot_rebuild(
            repo_root=str(tmp_path),
            targets=("沪深300",),
            top_n=5,
        )

    assert rc == 0
    mock_build.assert_called_once_with("沪深300", top_n=5)
    mock_write.assert_called_once()
    assert mock_write.call_args.args[1] == tmp_path / "data"


def test_snapshot_rebuild_warns_but_completes_when_snapshot_has_failures(tmp_path: Path) -> None:
    failed_snapshot = ConstituentSnapshot(
        lookthrough_target="未知指数",
        as_of_iso="2026-05-15",
        constituents=(),
        filings=(),
        broker_reports=(),
        failure_reasons=("unknown lookthrough_target: 未知指数",),
    )
    with patch(
        "irc.commands.fundamentals_cmd.build_snapshot",
        return_value=failed_snapshot,
    ), patch(
        "irc.commands.fundamentals_cmd.write_snapshot",
        return_value=tmp_path / "data" / "fundamentals" / "2026Q1" / "未知指数.json",
    ):
        rc = run_snapshot_rebuild(
            repo_root=str(tmp_path),
            targets=("未知指数",),
            top_n=10,
        )

    assert rc == 0
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/commands/test_fundamentals_cmd.py -q
```

Expected: fails because `irc.commands.fundamentals_cmd` does not exist.

- [ ] **Step 3: Implement command wrapper**

Create `src/irc/commands/fundamentals_cmd.py`:

```python
from __future__ import annotations

from pathlib import Path

from irc.fundamentals.snapshot import build_snapshot, write_snapshot


def run_snapshot_rebuild(
    repo_root: str,
    targets: tuple[str, ...],
    top_n: int = 10,
) -> int:
    if not targets:
        print("ERROR: provide at least one --target for snapshot rebuild.")
        return 2

    root = Path(repo_root)
    for target in targets:
        snapshot = build_snapshot(target, top_n=top_n)
        path = write_snapshot(snapshot, root / "data")
        if snapshot.failure_reasons:
            joined = "; ".join(snapshot.failure_reasons)
            print(f"WARNING: {target} snapshot has gaps: {joined}")
        print(f"fundamentals snapshot OK: {target} -> {path}")
    return 0
```

- [ ] **Step 4: Register CLI command**

Add a `fundamentals` command group to `src/irc/cli.py` near the other top-level groups:

```python
@main.group(help="Fundamentals snapshot cache management.")
def fundamentals() -> None:
    pass


@fundamentals.command("snapshot", help="Rebuild cached constituent snapshot(s).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--target", "targets", multiple=True, required=True, help="Lookthrough target to rebuild. Repeat for multiple targets.")
@click.option("--top-n", type=int, default=10, show_default=True, help="Top constituents to fetch per target.")
def fundamentals_snapshot(repo_root: str, targets: tuple[str, ...], top_n: int) -> None:
    from irc.commands.fundamentals_cmd import run_snapshot_rebuild
    rc = run_snapshot_rebuild(repo_root=repo_root, targets=targets, top_n=top_n)
    raise SystemExit(rc)
```

- [ ] **Step 5: Verify command tests and help**

Run:

```bash
uv run pytest tests/commands/test_fundamentals_cmd.py -q
uv run irc fundamentals snapshot --help
```

Expected: tests pass; help shows `--target` and `--top-n`.

---

### Task 7: Modernize Research Evals

**Files:**

- Modify: `evals/research/metrics.py`
- Modify: `evals/research/runner.py`
- Modify: `evals/spot_check/runner.py`
- Test: `tests/evals/test_research_metrics.py`
- Test: `tests/evals/test_spot_check.py`

- [ ] **Step 1: Replace LDR metric tests**

Use status-shaped reports:

```python
def _status_themes():
    return [
        {"theme": "us_monetary", "citation_count": 2, "failure_reason": ""},
        {"theme": "cn_monetary", "citation_count": 1, "failure_reason": ""},
        {"theme": "gold_drivers", "citation_count": 0, "failure_reason": "timeout"},
    ]


def test_research_success_rate_counts_non_failed_themes():
    assert research_success_rate(_status_themes()) == 2 / 3


def test_research_citation_validity_requires_citations_on_successful_themes():
    assert research_citation_validity(_status_themes()) == 1.0


def test_research_failure_visibility_requires_reason_for_failed_themes():
    assert research_failure_visibility(_status_themes()) == 1.0
```

- [ ] **Step 2: Implement new metrics**

```python
_REQUIRED_THEMES = (
    "us_monetary", "us_fiscal_politics", "cn_monetary",
    "cn_equity_property_policy", "geopolitics", "gold_drivers", "holdings_sector",
)


def theme_coverage(themes: list[dict]) -> int:
    covered = {r.get("theme") for r in themes if r.get("theme")}
    return sum(1 for theme in _REQUIRED_THEMES if theme in covered)


def research_success_rate(themes: list[dict]) -> float:
    if not themes:
        return 1.0
    ok = sum(1 for r in themes if not r.get("failure_reason"))
    return ok / len(themes)


def research_citation_validity(themes: list[dict]) -> float:
    successful = [r for r in themes if not r.get("failure_reason")]
    if not successful:
        return 1.0
    ok = sum(1 for r in successful if int(r.get("citation_count") or 0) > 0)
    return ok / len(successful)


def research_failure_visibility(themes: list[dict]) -> float:
    failed = [r for r in themes if r.get("failure_reason")]
    if not failed:
        return 1.0
    visible = sum(1 for r in failed if str(r.get("failure_reason", "")).strip())
    return visible / len(failed)
```

- [ ] **Step 3: Update runner input path**

`evals/research/runner.py` should read:

```python
status_file = repo_root / "data" / "research" / "research_status.json"
```

The metrics should be based on `body.get("themes", [])`.

- [ ] **Step 4: Rename spot-check pool**

Change docs/tests/code from `ldr_citations` to `research_citations`. Keep a compatibility fallback only if needed for old local queues, but new samples should emit `research_citations`.

- [ ] **Step 5: Run eval tests**

Run:

```bash
uv run pytest tests/evals/test_research_metrics.py tests/evals/test_spot_check.py -q
```

Expected: all pass and no test imports `ldr_citation_validity`.

---

### Task 8: Update README Operational Guidance

**Files:**

- Modify: `README.md`
- Test: no dedicated test; verify by grep.

README already contains a "How to read DCA and risk actions" subsection from plan 5 (currently around `README.md:128`). Do not duplicate or rewrite it; this task only adjusts the research-setup, smoke-test, output-inspection, and cadence-table content around it.

- [ ] **Step 1: Remove LDR instructions**

Delete the Local Deep Research install/server block, all `LDR_ENABLED` examples, the `ldr-web` startup lines, and the LDR mention in the top-of-file `> **Status:**` line.

- [ ] **Step 2: Add `.env` research setup**

Add concise setup text:

```markdown
### Web research setup

Research uses provider API keys from `.env`:

- `TAVILY_API_KEY` or `BRAVE_API_KEY` for English themes.
- `BOCHA_API_KEY` for Mainland-China themes.
- `JINA_API_KEY` is optional; without it, Jina Reader uses the rate-limited free tier.

Set `RESEARCH_ENABLED=true` only when you want `irc run` to include the research stage.
```

- [ ] **Step 3: Add smoke-test commands**

```markdown
uv run irc research --theme us_monetary
uv run irc research --theme cn_equity_property_policy
RESEARCH_ENABLED=true uv run irc run
```

- [ ] **Step 4: Add output inspection commands**

```markdown
ls data/research
sed -n '1,80p' data/research/us_monetary.md
jq '.themes[] | {theme, citation_count, failure_reason, provider_failures}' data/research/research_status.json
jq '.themes[] | select(.failure_reason != "")' data/research/research_status.json
uv run irc eval research
```

- [ ] **Step 5: Update opportunity cadence**

Change quarterly row to the new stack:

```markdown
| Quarterly thesis research | Theme search + citations and constituent snapshot refresh | `uv run irc research` plus `uv run irc fundamentals snapshot --target 沪深300` |
```

- [ ] **Step 6: Verify grep**

Run:

```bash
rg -n "LDR|LDR_ENABLED|local-deep-research|ldr-web" README.md
```

Expected: no matches.

- [ ] **Step 7: Verify DCA interpretation block remains untouched**

```bash
rg -n "How to read DCA and risk actions" README.md
```

Expected: exactly one match. The plan-5 DCA-action interpretation is the source of truth — this task must not delete, move, or reword it.

---

### Task 9: Document Changelog And TODO Cleanup

**Files:**

- Modify: `CHANGELOG.md`
- Modify: `TODOS.md` only if an existing TODO is completed by the implementation.

- [ ] **Step 1: Add changelog entry**

Under `[Unreleased]`, add:

```markdown
### Changed
- Completed the web research stack operational wiring: targeted `irc research --theme` runs, machine-readable `data/research/research_status.json`, research evals based on the new status file, fundamentals snapshot rebuild command, and README setup/output/error instructions.
```

- [ ] **Step 2: Update TODOs only after code lands**

Do not move TODOs during planning. After Task 4 lands, add or complete a TODO for opportunity snapshot/theme-report CLI wiring.

---

## Verification

Run focused tests first:

```bash
uv run pytest tests/research tests/fundamentals tests/commands/test_research_cmd.py tests/commands/test_run_cmd.py tests/commands/test_opportunity_cmd.py tests/commands/test_fundamentals_cmd.py tests/evals/test_research_metrics.py tests/evals/test_spot_check.py tests/opportunity/test_states.py tests/opportunity/test_thesis_evidence.py tests/opportunity/test_lookthrough.py tests/integration/test_decision_without_opportunity.py -q
```

Then run full suite before claiming completion:

```bash
uv run pytest
```

Manual smoke checks after setting real keys in `.env`. Time the research run against the spec's ≤30s-per-theme budget (`docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md` §Performance Contract):

```bash
time uv run irc research --theme us_monetary
time uv run irc research --theme cn_equity_property_policy
uv run irc fundamentals snapshot --target 沪深300 --top-n 10
jq '.overall, .themes[] | {theme, citation_count, failure_reason, provider_failures}' data/research/research_status.json
uv run irc opportunity
jq '.rows[] | select(.thesis_state != "evidence_insufficient") | {instrument_id, thesis_state, evidence_gaps}' "outputs/$(date -u +%Y-%m-%d)/opportunity_report.json"
uv run irc eval research
```

Expected:

- `data/research/<theme>.md` exists for each selected theme.
- `data/research/research_status.json` exists; `provider_failures` is present (may be empty) for every theme entry.
- Each `time` line reports wall-clock ≤30s under normal network conditions; ≥1 theme materially over budget is a flag, not necessarily a blocker.
- `data/fundamentals/<quarter>/沪深300.json` exists after the snapshot command.
- Successful themes have `citation_count > 0`.
- Failed themes have non-empty `failure_reason` and do not prevent other themes from writing output.
- At least one row in `opportunity_report.json` whose `lookthrough_target.display_cn` is `沪深300` (or another registered broad-CN target) shows `thesis_state` other than `evidence_insufficient` AND carries `thesis_evidence` entries — this validates the spec's headline acceptance criterion end-to-end.
- README has no LDR setup or `LDR_ENABLED` references and still contains exactly one "How to read DCA and risk actions" subsection.
