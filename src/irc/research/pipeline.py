from __future__ import annotations
from pathlib import Path

from irc.llm._types import ResolvedRoute
from irc.research.search.types import ContentExtractor, SearchProvider
from irc.research.persistence import write_research_outputs
from irc.research.theme_research import build_theme_reports


def run_research_pipeline(
    repo_root: Path,
    themes: tuple[str, ...],
    *,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
) -> int:
    """Run the research pipeline for all themes.

    Returns 0 for all completed runs, including degraded runs where individual themes failed.
    Returns non-zero only for unrecoverable conditions: pipeline-level exceptions or IO failures.
    Per-theme failures are represented in research_status.json with failure_reason set.
    """
    out_dir = repo_root / "data" / "research"
    reports = build_theme_reports(
        themes=themes, providers=providers, extractor=extractor, route=route,
    )
    write_research_outputs(out_dir, reports)
    return 0
