from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

from irc.llm._types import ResolvedRoute
from irc.llm.cost_tracker import CostEntry, append_cost
from irc.research.quality_gate import evaluate_research_quality
from irc.research.search.types import ContentExtractor, SearchProvider
from irc.research.persistence import write_research_outputs
from irc.research.theme_research import ThemeReport, build_theme_reports

_log = logging.getLogger(__name__)


def _print_summary(reports: list[ThemeReport]) -> None:
    ok = [r for r in reports if not r.failure_reason]
    failed = [r for r in reports if r.failure_reason]
    print(
        f"research summary: {len(ok)} ok / {len(failed)} failed "
        f"(total {len(reports)})"
    )
    for r in failed:
        print(f"  ✗ {r.theme} [{r.locale}] — {r.failure_reason}")
    for r in ok:
        print(f"  ✓ {r.theme} [{r.locale}] — {len(r.citations)} citations")


def _cost_entries_from_responses(
    responses: list[Any],
    route: ResolvedRoute,
) -> list[CostEntry]:
    """Build CostEntry list from LLM responses collected during research (Shape B)."""
    from datetime import datetime, timezone, timedelta
    history: list[CostEntry] = []
    _ts = datetime.now(timezone(timedelta(hours=8))).isoformat()
    for resp in responses:
        history = append_cost(history, CostEntry(
            task=route.task,
            provider=route.provider,
            model=route.model,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            latency_ms=getattr(resp, "latency_ms", 0),
            ts=_ts,
        ))
    return history


def run_research_pipeline(
    repo_root: Path,
    themes: tuple[str, ...],
    *,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
    holdings_keywords: tuple[str, ...] = (),
) -> tuple[int, list[CostEntry], dict[str, int]]:
    """Run all theme research; persist outputs; return (rc, cost_entries, search_units).

    rc: 0 = pass (or warn, run continues); 2 = fail (caller should halt).
    cost_entries: one CostEntry per successful LLM synthesize call (Shape B).
    search_units: dict[str, int] keyed by provider/extractor name — 1 unit per
        provider.search() call + 1 unit per extractor.extract() call (ADR 0013).
    """
    out_dir = repo_root / "data" / "research"
    reports, llm_responses, search_units = build_theme_reports(
        themes=themes, providers=providers, extractor=extractor, route=route,
        holdings_keywords=holdings_keywords,
    )
    write_research_outputs(out_dir, reports)
    _print_summary(reports)

    verdict = evaluate_research_quality(reports)
    for reason in verdict.reasons:
        if verdict.passed:
            _log.warning("research quality WARN: %s", reason)
        else:
            _log.error("research quality FAIL: %s", reason)
    if not verdict.passed:
        print("ERROR: research quality gate failed — see errors above for details")
    cost_entries = _cost_entries_from_responses(llm_responses, route)
    return verdict.exit_code, cost_entries, search_units
