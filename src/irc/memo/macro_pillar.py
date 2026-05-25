"""Deterministic macro/gold evidence pillar for memo §2 and §3.

Pure functions that turn (macro_series snapshots, theme reports, gold-regime
JSON) into:

  1. A tuple of `ThesisEvidence` records with `scope="asset_class_macro"` —
     written to `gold_regime.json["evidence"]` so they enter the publishable
     citation universe defined in `tests/integration/_publishable_set_helper.py`.
  2. A rendered `§2 宏观环境` markdown body with embedded `[ref:...]` markers
     pointing at those citation_ids.
  3. A rendered §3 gold-evidence bullet list (appended after the existing
     regime/zone/tilt lines).

The numbers and excerpts come from real data sources already on disk:
  * macro_series (DuckDB) — `real_yield_10y_tips`, `DXY`, `vix`,
    `inflation_5y5y` ingested from FRED.
  * theme reports under `data/research/` — `us_monetary`, `cn_monetary`,
    `geopolitics`, `gold_drivers`, `cn_equity_property_policy`,
    `us_fiscal_politics`.

The LLM synthesizer is instructed to copy §2 and the gold-evidence bullets
verbatim, the same way §7 execution lines are locked. Determinism beats
"let the LLM paraphrase the data" — the latter routinely lost the [ref:...]
markers and triggered uncited-portfolio findings.
"""
from __future__ import annotations

from dataclasses import dataclass

from irc.fundamentals.types import ThesisEvidence


# Sentinel owner used for macro-scope citations. Macro evidence has no
# instrument owner, but `ThesisEvidence.__post_init__` insists on a
# non-empty value. The audit gate excludes `scope="asset_class_macro"`
# from per-instrument provenance checks (build_cited_map only loads from
# `OpportunityRow.thesis_evidence`, not from gold_regime.json — the macro
# universe is read straight from the gold-regime evidence field).
_MACRO_OWNER = "macro"


@dataclass(frozen=True)
class MacroSnapshot:
    """A single macro-series datapoint pulled from `macro_series`."""
    series_id: str          # e.g. "real_yield_10y_tips"
    display_name: str       # e.g. "美国10Y TIPS 实际利率"
    value: float            # 2.18
    unit: str               # "%" / "" / "index"
    date: str               # ISO date string


@dataclass(frozen=True)
class ThemeReportRef:
    """A reference into a single theme report under `data/research/`."""
    theme: str              # e.g. "us_monetary"
    display_name: str       # e.g. "美国货币政策"
    summary: str            # one-paragraph excerpt the LLM can quote
    date: str               # ISO date (report generation)


def _snapshot_to_evidence(snap: MacroSnapshot) -> ThesisEvidence:
    """Each macro datapoint becomes a `snapshot` evidence row."""
    return ThesisEvidence(
        type="snapshot",
        source=snap.series_id,
        url="",
        date=snap.date,
        # summary doubles as the human-readable label rendered in §2 prose.
        summary=f"{snap.display_name} {snap.value:g}{snap.unit} @ {snap.date}",
        scope="asset_class_macro",
        citation_kind="data",
        owner_instrument_id=_MACRO_OWNER,
        parent_fund_id=None,
        constituent_key=None,
    )


def _theme_to_evidence(ref: ThemeReportRef) -> ThesisEvidence:
    """Each theme report becomes a `news` evidence row (closest existing
    `ThesisEvidenceKind`; "policy" would imply a regulatory primary
    source)."""
    return ThesisEvidence(
        type="news",
        source=f"research:{ref.theme}",
        url="",
        date=ref.date,
        summary=ref.summary,
        scope="asset_class_macro",
        citation_kind="information",
        owner_instrument_id=_MACRO_OWNER,
        parent_fund_id=None,
        constituent_key=None,
    )


def build_macro_evidence(
    snapshots: tuple[MacroSnapshot, ...],
    theme_refs: tuple[ThemeReportRef, ...],
) -> tuple[ThesisEvidence, ...]:
    """Compose the full macro evidence list. Order is stable so reruns
    produce byte-identical gold_regime.json output."""
    return tuple(_snapshot_to_evidence(s) for s in snapshots) + tuple(
        _theme_to_evidence(t) for t in theme_refs
    )


# ─── Section renderers ──────────────────────────────────────────────────────


MACRO_SECTION_MARKER_BEGIN = "<!-- IRC_MACRO_LINES_BEGIN -->"
MACRO_SECTION_MARKER_END = "<!-- IRC_MACRO_LINES_END -->"
GOLD_EVIDENCE_MARKER_BEGIN = "<!-- IRC_GOLD_EVIDENCE_BEGIN -->"
GOLD_EVIDENCE_MARKER_END = "<!-- IRC_GOLD_EVIDENCE_END -->"


def _ref_marker(ev: ThesisEvidence) -> str:
    return f"[ref:{ev.citation_id}]"


def render_macro_section_body(
    snapshots: tuple[MacroSnapshot, ...],
    theme_refs: tuple[ThemeReportRef, ...],
    evidence_by_source: dict[str, ThesisEvidence],
) -> str:
    """Render §2 markdown body.

    Renders one bullet per macro datapoint and one bullet per theme-report
    excerpt. Each bullet ends with a `[ref:...]` marker. The synthesizer
    must NOT paraphrase or merge these bullets — the markers carry the
    audit-gate binding.
    """
    if not snapshots and not theme_refs:
        return _ANTI_FABRICATION_FALLBACK
    bullets: list[str] = []
    if snapshots:
        bullets.append("- **关键宏观指标**：")
        for snap in snapshots:
            ev = evidence_by_source[snap.series_id]
            bullets.append(
                f"  - {snap.display_name}：{snap.value:g}{snap.unit} "
                f"（截至 {snap.date}） {_ref_marker(ev)}"
            )
    if theme_refs:
        bullets.append("- **本周宏观研究要点**（一段话摘录，详见 data/research/）：")
        for ref in theme_refs:
            ev = evidence_by_source[f"research:{ref.theme}"]
            bullets.append(
                f"  - **{ref.display_name}**（{ref.date}）：{ref.summary} {_ref_marker(ev)}"
            )
    bullets.append("")
    bullets.append(_DISCLAIMER)
    body = "\n".join(bullets)
    return (
        f"{MACRO_SECTION_MARKER_BEGIN}\n{body}\n{MACRO_SECTION_MARKER_END}"
    )


def render_gold_evidence_body(
    snapshots: tuple[MacroSnapshot, ...],
    theme_refs: tuple[ThemeReportRef, ...],
    evidence_by_source: dict[str, ThesisEvidence],
    *,
    only_series: tuple[str, ...] = ("real_yield_10y_tips", "DXY"),
    only_themes: tuple[str, ...] = ("gold_drivers", "geopolitics"),
) -> str:
    """Render gold-section evidence bullets (appended to memo §3)."""
    bullets: list[str] = []
    for snap in snapshots:
        if snap.series_id not in only_series:
            continue
        ev = evidence_by_source.get(snap.series_id)
        if ev is None:
            continue
        bullets.append(
            f"- {snap.display_name}：{snap.value:g}{snap.unit} "
            f"（截至 {snap.date}） {_ref_marker(ev)}"
        )
    for ref in theme_refs:
        if ref.theme not in only_themes:
            continue
        ev = evidence_by_source.get(f"research:{ref.theme}")
        if ev is None:
            continue
        bullets.append(
            f"- **{ref.display_name}**（{ref.date}）：{ref.summary} {_ref_marker(ev)}"
        )
    if not bullets:
        return ""
    body = "\n".join(bullets)
    return (
        f"{GOLD_EVIDENCE_MARKER_BEGIN}\n{body}\n{GOLD_EVIDENCE_MARKER_END}"
    )


def evidence_by_source_key(
    evidence: tuple[ThesisEvidence, ...],
) -> dict[str, ThesisEvidence]:
    """Index evidence by source string (matches MacroSnapshot.series_id
    and `research:{theme}` for ThemeReportRef)."""
    return {ev.source: ev for ev in evidence}


_DISCLAIMER = (
    "> 上述指标与研究摘录为系统采集的原始数据快照，不构成方向性预测；"
    "如需进一步背景，请查阅原始研究文件。"
)


_ANTI_FABRICATION_FALLBACK = (
    "实际利率、美元指数、A 股估值百分位等宏观数据采集失败。"
    "本期不展开宏观判断；不要自行编造、补足或外推。"
)
