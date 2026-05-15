from __future__ import annotations
import logging
from pathlib import Path

from irc.llm._types import ResolvedRoute
from irc.research.quality_gate import evaluate_research_quality
from irc.research.search.types import ContentExtractor, SearchProvider
from irc.research.persistence import write_research_outputs
from irc.research.theme_research import build_theme_reports

_log = logging.getLogger(__name__)


def _print_summary(reports: list[ThemeReport]) -> None:
    ok = [r for r in reports if not r.failure_reason]
    failed = [r for r in reports if r.failure_reason]
    print(
        f"research summary: {len(ok)} ok / {len(failed)} failed "
        f"(total {len(reports)})"
    )
    for r in failed:
        print(f"  \u2717 {r.theme} [{r.locale}] \u2014 {r.failure_reason}")
    for r in ok:
        print(f"  \u2713 {r.theme} [{r.locale}] \u2014 {len(r.citations)} citations")


def run_research_pipeline(
    repo_root: Path,
    themes: tuple[str, ...],
    *,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
) -> int:
    """Run all theme research; persist outputs; return rc per the quality gate.

    0 = pass (or warn, run continues); 2 = fail (caller should halt).
    """
    out_dir = repo_root / "data" / "research"
    reports = build_theme_reports(
        themes=themes, providers=providers, extractor=extractor, route=route,
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
    return verdict.exit_code
