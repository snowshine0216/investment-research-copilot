from __future__ import annotations
from pathlib import Path

from irc.llm._types import ResolvedRoute
from irc.io_utils import atomic_write_text
from irc.research.search.types import ContentExtractor, SearchProvider
from irc.research.synthesize import Citation
from irc.research.theme_research import build_theme_reports


def _format_report(
    theme: str,
    body_md: str,
    citations: list[Citation],
    failure_reason: str,
) -> str:
    if failure_reason:
        return f"# {theme}\n\n_research failed: {failure_reason}_\n"
    cit_lines = "\n".join(f"[{c.index}] {c.title} — {c.url}" for c in citations)
    return f"# {theme}\n\n{body_md}\n\n## Citations\n{cit_lines}\n"


def run_research_pipeline(
    repo_root: Path,
    themes: tuple[str, ...],
    *,
    providers: tuple[SearchProvider, ...],
    extractor: ContentExtractor,
    route: ResolvedRoute,
) -> int:
    out_dir = repo_root / "data" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = build_theme_reports(
        themes=themes, providers=providers, extractor=extractor, route=route,
    )
    for r in reports:
        atomic_write_text(
            out_dir / f"{r.theme}.md",
            _format_report(r.theme, r.report_md, r.citations, r.failure_reason),
        )
    has_failures = any(r.failure_reason for r in reports)
    return 2 if has_failures else 0
