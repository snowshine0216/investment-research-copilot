"""Pure diff-report builder for the Phase D look-through (spec §8, gate-#5 artifact).

Per active fund: would-flip band (NAV-derived vs PE-derived valuation band),
Δpercentile (PE − NAV), per-metric covered-weight ratio + source mix (PE and PB
SEPARATELY, since their covered sets can differ), the current-basket caveat, and
a coverage-floor sensitivity table at 0.40/0.50/0.60. Computes regardless of the
`enabled` flag. NO I/O — the command (lookthrough_diff_cmd) supplies cached data.

Band boundaries reused from opportunity/states._band / _VALUATION_BANDS (cheap <.20 ·
reasonable_low <.40 · fair <.70 · expensive <.90 · very_expensive ≥.90), matching
the divergence detector's band semantics (CONTEXT.md valuation_divergence_code).
`_band` is imported directly as the single source of truth; `_band_label` wraps it
to handle None → "—".
"""
from __future__ import annotations

from dataclasses import dataclass

from irc.opportunity.lookthrough_valuation import FundValuationResult
from irc.opportunity.states import _band

_CAVEAT_CN = (
    "注意：本估值为「当前持仓 × 历史个股 PE」构造的 current-basket 序列，"
    "并非基金真实历史 PE（不存历史持仓）。"
)


def _band_label(pct: float | None) -> str:
    """Wrap _band to handle None → '—'."""
    if pct is None:
        return "—"
    return _band(pct)


@dataclass(frozen=True)
class FundDiffRow:
    instrument_id: str
    name_cn: str
    nav_band: str
    pe_band: str
    would_flip: bool
    delta_percentile: float | None
    pe_coverage_ratio: float
    pb_coverage_ratio: float
    pe_source_mix: tuple[str, ...]
    pb_source_mix: tuple[str, ...]


def build_fund_diff_row(
    *, instrument_id: str, name_cn: str,
    nav_percentile: float | None, result: FundValuationResult,
) -> FundDiffRow:
    """Build a per-fund diff row from cached NAV percentile + look-through result."""
    pe_pct = result.pe.percentile
    nav_band = _band_label(nav_percentile)
    pe_band = _band_label(pe_pct)
    delta = (
        pe_pct - nav_percentile
        if pe_pct is not None and nav_percentile is not None
        else None
    )
    return FundDiffRow(
        instrument_id=instrument_id,
        name_cn=name_cn,
        nav_band=nav_band,
        pe_band=pe_band,
        would_flip=(pe_pct is not None and nav_band != pe_band),
        delta_percentile=delta,
        pe_coverage_ratio=result.pe.coverage_ratio,
        pb_coverage_ratio=result.pb.coverage_ratio,
        pe_source_mix=result.pe.source_mix,
        pb_source_mix=result.pb.source_mix,
    )


def build_floor_sensitivity(
    coverage_ratios: list[float], *, floors: tuple[float, ...] = (0.40, 0.50, 0.60),
) -> dict[float, int]:
    """Grounded-fund count at each floor (a fund is grounded iff its PE
    coverage ratio meets the floor)."""
    return {f: sum(1 for r in coverage_ratios if r >= f) for f in floors}


def _format_mix(mix: tuple[str, ...]) -> str:
    return "/".join(mix) if mix else "—"


def render_diff_report(
    rows: list[FundDiffRow], floor_sensitivity: dict[float, int]
) -> str:
    """Render the gate-#5 diff report as a Markdown string."""
    lines = ["# Phase D look-through diff report (gate #5)", "", _CAVEAT_CN, ""]
    lines.append("## Per-fund flip & coverage")
    lines.append(
        "| id | 名称 | NAV band | PE band | flip | Δpct | "
        "PE cov | PE src | PB cov | PB src |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: x.instrument_id):
        delta = "—" if r.delta_percentile is None else f"{r.delta_percentile:+.2f}"
        lines.append(
            f"| {r.instrument_id} | {r.name_cn} | {r.nav_band} | {r.pe_band} | "
            f"{'YES' if r.would_flip else 'no'} | {delta} | "
            f"{r.pe_coverage_ratio:.2f} | {_format_mix(r.pe_source_mix)} | "
            f"{r.pb_coverage_ratio:.2f} | {_format_mix(r.pb_source_mix)} |"
        )
    lines += ["", "## Coverage-floor sensitivity (grounded funds)", ""]
    lines.append("| floor | grounded funds |")
    lines.append("|---|---|")
    for floor in sorted(floor_sensitivity):
        lines.append(f"| {floor:.2f} | {floor_sensitivity[floor]} |")
    return "\n".join(lines) + "\n"
