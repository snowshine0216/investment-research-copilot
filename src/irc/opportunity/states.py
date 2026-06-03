from __future__ import annotations

import math

from irc.fundamentals.types import (
    ActiveFundSnapshot,
    ConstituentSnapshot,
    FundLevelSnapshot,
)
from irc.opportunity.lookthrough import map_lookthrough
from irc.opportunity.thesis_evidence import (
    NON_INDEXABLE_ASSET_CLASSES,
    derive_thesis_from_evidence,
)
from irc.opportunity.types import (
    HeatState,
    OpportunityInput,
    OpportunityRow,
    OpportunityState,
    ProductQualityState,
    ThesisState,
    ValuationState,
)
from irc.opportunity.advisory_gaps import ADVISORY_GAP_CODES
from irc.opportunity.valuation_fundamental import (
    ValuationFundamental,
    _fundamental_reason_phrase,
    valuation_fundamental_signal,
)
from irc.research.theme_research import ThemeReport


EXPECTED_OMISSION_CODES: frozenset[str] = frozenset({
    "constituent_not_applicable",
})


def _partition_gaps(
    gaps: tuple[str, ...] | list[str],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Split a flat gap list into (real_gaps, expected_omissions, advisory_gaps).

    - real_gaps: row-blocking signals (H3 routes any non-empty value to gapped_rows).
    - expected_omissions: structural non-features by design (e.g.
      `constituent_not_applicable` for asset classes without constituents).
    - advisory_gaps: non-blocking advisories that publishable rows still surface
      (ADR 0005). H3 partition predicate stays `evidence_gaps == ()` — orthogonal.
    """
    real, expected, advisory = [], [], []
    for g in gaps:
        if g in EXPECTED_OMISSION_CODES:
            expected.append(g)
        elif g in ADVISORY_GAP_CODES:
            advisory.append(g)
        else:
            real.append(g)
    return tuple(real), tuple(expected), tuple(advisory)


_FETCH_TYPE_ORDER: tuple[str, ...] = (
    "holdings", "nav", "announcements", "filing", "broker", "news",
)


def _fetch_type_from_failure(reason: str) -> str | None:
    if reason.startswith("holdings_"):
        return "holdings"
    if reason.startswith("fund_nav_"):
        return "nav"
    if reason.startswith("fund_announcements_"):
        return "announcements"
    if reason.startswith("filing_"):
        return "filing"
    if reason.startswith("broker_"):
        return "broker"
    if reason.startswith(("news_", "hk_news_")):
        return "news"
    return None


def _ordered_fetch_types(types: set[str]) -> tuple[str, ...]:
    return tuple(t for t in _FETCH_TYPE_ORDER if t in types)


def derive_fetch_types_attempted(
    snapshot: ConstituentSnapshot | ActiveFundSnapshot | FundLevelSnapshot | None,
) -> tuple[str, ...]:
    """Infer fetch-path provenance from a snapshot without mutating it."""
    if snapshot is None:
        return ()
    attempted: set[str] = set()
    if isinstance(snapshot, ActiveFundSnapshot):
        attempted.add("holdings")
        for reason in snapshot.fund_level_failure_reasons:
            fetch_type = _fetch_type_from_failure(reason)
            if fetch_type is not None:
                attempted.add(fetch_type)
        for analysis in snapshot.constituent_analyses:
            attempted.update(e.type for e in analysis.evidence)
            for reason in analysis.failure_reasons:
                fetch_type = _fetch_type_from_failure(reason)
                if fetch_type is not None:
                    attempted.add(fetch_type)
        return _ordered_fetch_types(attempted)
    if isinstance(snapshot, FundLevelSnapshot):
        if "qdii_information_unavailable" in snapshot.evidence_gaps:
            return ()
        attempted.update(
            "nav" if e.type == "snapshot" else e.type
            for e in snapshot.evidence
        )
        for reason in snapshot.fund_level_failure_reasons:
            fetch_type = _fetch_type_from_failure(reason)
            if fetch_type is not None:
                attempted.add(fetch_type)
        return _ordered_fetch_types(attempted)
    if isinstance(snapshot, ConstituentSnapshot):
        if snapshot.filings:
            attempted.add("filing")
        if snapshot.broker_reports:
            attempted.add("broker")
        for reason in snapshot.failure_reasons:
            fetch_type = _fetch_type_from_failure(reason)
            if fetch_type is not None:
                attempted.add(fetch_type)
        return _ordered_fetch_types(attempted)
    return ()


# ---------------------------------------------------------------------------
# Task 3: Valuation classifier
# ---------------------------------------------------------------------------

def _percentile(inp: OpportunityInput) -> float | None:
    """Prefer self-history percentile; fall back to vs-benchmark."""
    if inp.valuation_percentile_self is not None:
        return inp.valuation_percentile_self
    return inp.valuation_percentile_vs_benchmark


_BOND_ASSET_CLASSES: frozenset[str] = frozenset({"cn_bond_fund"})
_EQUITY_ASSET_CLASSES: frozenset[str] = frozenset({
    "cn_equity_fund", "cn_etf", "us_etf", "hk_etf", "qdii_global",
})
_EXPENSIVE_VALUATION_STATES: frozenset[str] = frozenset({"expensive", "very_expensive"})
_NOTCHABLE_VALUATION_STATES: frozenset[str] = frozenset({"cheap", "reasonable_low"})

DIVERGENCE_PCT_GAP: float = 0.25
VALUATION_DIVERGENCE_CODE: str = "valuation_price_fundamental_divergence"

# Shared band thresholds — the single source of truth for the percentile->band
# mapping used by classify_valuation AND valuation_divergence_code (DRY).
_VALUATION_BANDS: tuple[tuple[float, str], ...] = (
    (0.20, "cheap"),
    (0.40, "reasonable_low"),
    (0.70, "fair"),
    (0.90, "expensive"),
)


def _band(pct: float) -> str:
    """Map a percentile to its valuation band tier (matches classify_valuation)."""
    for upper, name in _VALUATION_BANDS:
        if pct < upper:
            return name
    return "very_expensive"


def valuation_divergence_code(inp: OpportunityInput) -> str | None:
    """Return the advisory code when the fundamental and NAV percentiles
    disagree (different band-tier OR |gap| >= DIVERGENCE_PCT_GAP); else None.

    Single source of truth (R2): classify_valuation uses it for the reason note;
    build_opportunity_row folds it into advisory_gaps.
    """
    f, n = inp.valuation_percentile_fundamental, inp.valuation_percentile_self
    if f is None or n is None:
        return None
    if _band(f) != _band(n) or abs(f - n) >= DIVERGENCE_PCT_GAP:
        return VALUATION_DIVERGENCE_CODE
    return None


def expected_real_return_positive(inp: OpportunityInput) -> bool | None:
    """Earnings-yield vs real-yield sanity anchor (review §B3).

    Returns:
      True  — equity offers a positive expected real return
              (earnings_yield > real_yield_10y)
      False — equity offers a negative or zero expected real return
      None  — either input missing; no opinion
    """
    if inp.earnings_yield is None or inp.real_yield_10y is None:
        return None
    return float(inp.earnings_yield) > float(inp.real_yield_10y)


def classify_bond_valuation(inp: OpportunityInput) -> tuple[ValuationState, str]:
    """Classify bond-fund valuation from 10Y CGB yield percentile.

    A pure-bond fund's NAV percentile is a momentum proxy with no
    economic interpretation. The right anchor is the local yield curve:
    high yield-percentile ⇔ yields elevated ⇔ bonds cheap.

    Bands on ``cn_bond_yield_percentile``:
      cheap:           pct >= 0.80
      reasonable_low:  0.60 <= pct < 0.80
      fair:            0.30 <= pct < 0.60
      expensive:       0.10 <= pct < 0.30
      very_expensive:  pct < 0.10
    """
    pct = inp.cn_bond_yield_percentile
    if pct is None:
        return (
            "evidence_insufficient",
            "10Y CGB 收益率百分位数据缺失，未能对债券估值给出方向性结论。",
        )
    if pct >= 0.80:
        return "cheap", f"10Y 收益率位于 {pct:.0%} 高位，债券估值便宜。"
    if pct >= 0.60:
        return "reasonable_low", f"10Y 收益率位于 {pct:.0%} 偏高位，估值偏低。"
    if pct >= 0.30:
        return "fair", f"10Y 收益率位于 {pct:.0%} 中位区间，估值中性。"
    if pct >= 0.10:
        return "expensive", f"10Y 收益率位于 {pct:.0%} 低位，债券估值偏贵。"
    return "very_expensive", f"10Y 收益率位于 {pct:.0%} 极低，债券估值极贵。"


def classify_valuation(inp: OpportunityInput) -> tuple[ValuationState, str]:
    """Classify valuation state. Bonds use a yield-curve anchor; all
    other asset classes use the price/percentile bands:
      cheap: pct < 0.20
      reasonable_low: 0.20 <= pct < 0.40
      fair: 0.40 <= pct < 0.70
      expensive: 0.70 <= pct < 0.90
      very_expensive: pct >= 0.90
    Drawdown alone is NEVER evidence of cheapness.
    """
    if inp.asset_class in _BOND_ASSET_CLASSES:
        return classify_bond_valuation(inp)
    # Phase 1 (item 001): the FUNDAMENTAL index PE-TTM percentile decides the
    # band when present; otherwise fall back to the NAV self-history percentile
    # (AC2 — byte-for-byte unchanged for vehicles with no fundamental data).
    fund_pct = inp.valuation_percentile_fundamental
    if fund_pct is not None:
        pct = fund_pct
        anchor_label = "PE 百分位"
    else:
        pct = _percentile(inp)
        anchor_label = "估值百分位"
    if pct is None:
        return "evidence_insufficient", "估值数据缺失，未能判定。"
    if pct < 0.20:
        state, reason = "cheap", f"{anchor_label} {pct:.0%} 偏低。"
    elif pct < 0.40:
        state, reason = "reasonable_low", f"{anchor_label} {pct:.0%} 偏低但未极低。"
    elif pct < 0.70:
        state, reason = "fair", f"{anchor_label} {pct:.0%} 中性。"
    elif pct < 0.90:
        state, reason = "expensive", f"{anchor_label} {pct:.0%} 偏高。"
    else:
        state, reason = "very_expensive", f"{anchor_label} {pct:.0%} 极高。"
    # Equity sanity anchor (§B3): high price percentile can persist for years
    # (1995-2000); if earnings_yield - real_yield_10y > 0 the equity is still
    # offering a positive expected real return, which a DCA investor should know
    # before treating "very_expensive" as "avoid".
    if (
        state in _EXPENSIVE_VALUATION_STATES
        and inp.asset_class in _EQUITY_ASSET_CLASSES
    ):
        signal = expected_real_return_positive(inp)
        if signal is True:
            reason = (
                f"{reason} 但 earnings_yield - real_yield 为正，"
                f"长期 DCA 视为正期望，估值高位不等于退出信号。"
            )
        elif signal is False:
            reason = (
                f"{reason} 且 earnings_yield - real_yield 非正，"
                f"长期实际回报预期偏弱。"
            )
    if inp.asset_class in _EQUITY_ASSET_CLASSES:
        # Step 3 (§4.4): price/fundamental divergence reason note. The advisory
        # code itself is folded into advisory_gaps by build_opportunity_row (R2);
        # here we only annotate the reason. classify_valuation keeps (state, reason).
        if valuation_divergence_code(inp) is not None:
            nav_pct = _percentile(inp)
            reason = (
                f"{reason} 价格与基本面估值百分位背离"
                f"（价格 {nav_pct:.0%} vs 基本面 {fund_pct:.0%}），"
                f"以基本面为准。"
            )
        # Step 4 (§4.4, Q5): PB corroboration note — cyclical/earnings-quality
        # caveat when PE says cheap but PB percentile is elevated. NO state change.
        pb_pct = inp.valuation_percentile_fundamental_pb
        if (
            state in _NOTCHABLE_VALUATION_STATES
            and pb_pct is not None
            and pb_pct >= 0.70
        ):
            reason = (
                f"{reason} 但 PB 百分位 {pb_pct:.0%} 偏高，"
                f"或为周期性盈利高估，便宜判断需谨慎。"
            )
        fundamental = valuation_fundamental_signal(inp)
        if fundamental is not None:
            reason = f"{reason} {_fundamental_reason_phrase(fundamental, inp)}"
            # AC3: corroboration-only one-notch move toward cheaper. Never
            # toward more-expensive; never promotes fair/expensive/very_expensive.
            if fundamental == "cheap" and state in _NOTCHABLE_VALUATION_STATES:
                state = "cheap"
    return state, reason


# ---------------------------------------------------------------------------
# Task 4: Heat classifier
# ---------------------------------------------------------------------------

def _heat_score(inp: OpportunityInput) -> tuple[float, int]:
    """Compute a heat score in [-1, 1] and count of evidence pieces."""
    contributions: list[float] = []
    if inp.ret_1m is not None:
        contributions.append(max(-1.0, min(1.0, inp.ret_1m * 5.0)))
    if inp.ret_3m is not None:
        contributions.append(max(-1.0, min(1.0, inp.ret_3m * 2.5)))
    if inp.ret_6m is not None:
        contributions.append(max(-1.0, min(1.0, inp.ret_6m * 1.5)))
    if inp.ret_12m is not None:
        contributions.append(max(-1.0, min(1.0, inp.ret_12m * 1.0)))
    if inp.premium_discount_pct is not None:
        contributions.append(max(-1.0, min(1.0, inp.premium_discount_pct * 40.0)))
    if inp.flow_pct_30d is not None:
        contributions.append(max(-1.0, min(1.0, inp.flow_pct_30d * 5.0)))
    if not contributions:
        return 0.0, 0
    return sum(contributions) / len(contributions), len(contributions)


def classify_heat(inp: OpportunityInput) -> tuple[HeatState, str]:
    """Classify trading heat / crowding state.

    Recent strong returns INCREASE heat risk. This is intentional.
    """
    score, n = _heat_score(inp)
    if n < 2:
        return "evidence_insufficient", "热度数据不足，未能判定。"
    if score >= 0.55:
        return "overheated", f"近期涨幅与溢价共同显示极度过热（score={score:.2f}）。"
    if score >= 0.30:
        return "crowded", f"近期涨幅较大，存在追高风险（score={score:.2f}）。"
    if score <= -0.10:
        return "cold", f"近期表现偏弱，市场关注度低（score={score:.2f}）。"
    return "normal", f"热度处于正常区间（score={score:.2f}）。"


# ---------------------------------------------------------------------------
# Task 5: Thesis classifier
# ---------------------------------------------------------------------------

_VALID_THESIS_TABLE_VALUES: frozenset[str] = frozenset(
    {"intact", "under_pressure", "falsified", "evidence_insufficient"}
)


def classify_thesis(
    inp: OpportunityInput,
    theme_thesis: dict[str, str] | None,
) -> tuple[ThesisState, str]:
    """Classify long-term thesis state for the instrument's theme."""
    if theme_thesis is None:
        return "evidence_insufficient", "长期逻辑数据未就绪。"
    theme = inp.theme
    if theme is None:
        return "evidence_insufficient", "标的未标注主题，无法引用长期逻辑表。"
    raw = theme_thesis.get(theme)
    if raw is None or raw not in _VALID_THESIS_TABLE_VALUES:
        return "evidence_insufficient", f"主题 {theme} 在长期逻辑表中无记录。"
    if raw == "intact" and inp.style_drift_flag:
        return "under_pressure", "主题逻辑完好，但产品存在风格漂移迹象。"
    return raw, f"主题 {theme} 逻辑状态：{raw}。"  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Task 6: Product quality classifier
# ---------------------------------------------------------------------------

def _is_active_fund(inp: OpportunityInput) -> bool:
    return inp.asset_class == "cn_equity_fund" and inp.market != "cn_on_exchange"


def _passive_quality_score(inp: OpportunityInput) -> tuple[float, int]:
    contributions: list[float] = []
    if inp.expense_ratio is not None:
        contributions.append(max(-1.0, min(1.0, (0.02 - inp.expense_ratio) / 0.02)))
    if inp.aum_cny is not None:
        log_aum = math.log10(max(inp.aum_cny, 1.0))
        contributions.append(max(-1.0, min(1.0, (log_aum - 8.7) / 1.0)))
    if inp.tracking_error is not None:
        contributions.append(max(-1.0, min(1.0, (0.005 - inp.tracking_error) / 0.005)))
    if inp.premium_discount_pct is not None:
        contributions.append(max(-1.0, min(1.0, (0.01 - abs(inp.premium_discount_pct)) / 0.01)))
    if not contributions:
        return 0.0, 0
    return sum(contributions) / len(contributions), len(contributions)


# aum_stability_pct is a coefficient-of-variation-style measure (lower = more
# stable; see scoring/factors/quality._aum_stability_score). A value at or below
# this bound lifts a sound active fund to 'strong'; its ABSENCE only caps the
# ceiling at 'acceptable' — it never floors an otherwise-sound product.
_AUM_STABILITY_STRONG_MAX: float = 0.20


def _classify_active_quality(inp: OpportunityInput) -> tuple[ProductQualityState, str]:
    """Grade an active fund on manager tenure + cost/scale evidence.

    aum_stability_pct is optional corroboration (the F-1 data slice is not yet
    ingested): when present and low it permits 'strong'; its absence caps the
    fund at 'acceptable' but never floors a sound product to 'weak'.
    """
    if inp.manager_tenure_years is None:
        return "evidence_insufficient", "主动基金缺少基金经理任职年限证据。"
    if inp.manager_tenure_years < 2.0:
        return "weak", "基金经理任职年限不足两年。"
    score, n = _passive_quality_score(inp)
    if n < 2:
        return "weak", "主动基金成本/规模证据不足。"
    aum_stable = (
        inp.aum_stability_pct is not None
        and inp.aum_stability_pct <= _AUM_STABILITY_STRONG_MAX
    )
    if score >= 0.5 and inp.manager_tenure_years >= 5.0 and aum_stable:
        return "strong", "主动基金长期经理 + 优良成本/规模 + AUM稳定。"
    if score >= 0.0:
        return "acceptable", "主动基金达到可观察标准。"
    return "weak", "主动基金成本或规模存在明显劣势。"


def classify_product_quality(inp: OpportunityInput) -> tuple[ProductQualityState, str]:
    """Classify product quality. Active funds are graded on manager tenure +
    cost/scale evidence; AUM stability is optional corroboration (F-1)."""
    if _is_active_fund(inp):
        return _classify_active_quality(inp)

    score, n = _passive_quality_score(inp)
    if n < 2:
        return "evidence_insufficient", "产品成本/规模数据不足。"
    if score >= 0.55:
        return "strong", "费率低、规模大、跟踪误差小。"
    if score >= 0.10:
        return "acceptable", "产品质量在合理范围内。"
    if score >= -0.30:
        return "weak", "产品质量存在明显短板。"
    return "poor", "产品质量极差，不适合主仓位。"


# ---------------------------------------------------------------------------
# Task 7: Opportunity state composer + evidence-gap tracking
# ---------------------------------------------------------------------------


def _weak_link_label(
    valuation: ValuationState,
    heat: HeatState,
    thesis: ThesisState,
    product_quality: ProductQualityState,
) -> str:
    """Pick a short Chinese label describing the weakest sub-state.

    Priority mirrors the ordering reviewers care about: product quality
    fundamentals first, then thesis evidence, then valuation data, then heat.
    When no single sub-state stands out the label is the generic
    'signal conflict' fallback.
    """
    if product_quality == "weak":
        return "产品质量薄弱"
    if thesis == "evidence_insufficient":
        return "主题逻辑证据不足"
    if valuation == "evidence_insufficient":
        return "估值数据缺失"
    if heat == "evidence_insufficient":
        return "热度信号不足"
    return "信号方向冲突"


def compose_opportunity_state(
    valuation: ValuationState,
    heat: HeatState,
    thesis: ThesisState,
    product_quality: ProductQualityState,
    venue_compatible: bool = True,
    valuation_fundamental: ValuationFundamental | None = None,
) -> tuple[OpportunityState, str]:
    """Compose final opportunity state from four sub-states.

    `valuation_fundamental` (item 002, grill Q-T2): when `"rich"` AND the
    percentile path is cheap/reasonable_low, the cheap-AND-intact `core_dca`
    gate is refused (the row falls through to `small_watch`). Default `None`
    keeps every existing caller byte-identical. `valuation_state` itself stays
    `cheap` — only the opportunity state falls through (AC3-preserving).
    """
    # Priority order: thesis/quality failures → exclude (hardest gate);
    # then valuation/heat signals → pause_wait or core_dca.
    # venue_compatible is tracked separately for execution notes but does NOT
    # downgrade the opportunity state.
    if thesis == "falsified" or product_quality == "poor":
        return "exclude", "长期逻辑被证伪或产品质量过差，禁止建仓。"

    cheap_or_low = valuation in ("cheap", "reasonable_low")
    expensive = valuation in ("expensive", "very_expensive")
    quiet_heat = heat in ("cold", "normal")
    hot_heat = heat in ("crowded", "overheated")
    intact_thesis = thesis == "intact"
    decent_product = product_quality in ("acceptable", "strong")

    fundamental_contradiction = valuation_fundamental == "rich" and cheap_or_low
    if (
        cheap_or_low and quiet_heat and intact_thesis and decent_product
        and not fundamental_contradiction
    ):
        return "core_dca", "估值便宜、热度可控、长期逻辑完好、产品质量合格，适合定投。"

    if expensive or hot_heat:
        return "pause_wait", "估值或热度高于规则阈值，暂停加仓；如估值或热度回到规则阈值内再评估。"

    label = _weak_link_label(valuation, heat, thesis, product_quality)
    return (
        "small_watch",
        f"证据不完整或信号不一致（{label}），列入小仓位观察。",
    )


def derive_contributing_dimensions(
    valuation: ValuationState,
    heat: HeatState,
    thesis: ThesisState,
    product: ProductQualityState,
    opportunity_state: OpportunityState,
) -> frozenset[str]:
    """Return the subset of {valuation, heat, thesis, product_quality} that
    drove `opportunity_state`. Pure; mirrors `compose_opportunity_state`'s
    branches. Used by the per-driver citation gate (Slice D2a, item 009).

    `small_watch` priority chain mirrors `_weak_link_label` but returns
    dimension keys, not Chinese labels — calling `_weak_link_label` and
    reverse-mapping would couple us to a display-string lookup table.
    """
    if opportunity_state == "exclude":
        dims: set[str] = set()
        if thesis == "falsified":
            dims.add("thesis")
        if product == "poor":
            dims.add("product_quality")
        return frozenset(dims)
    if opportunity_state == "core_dca":
        return frozenset({"valuation", "heat", "thesis", "product_quality"})
    if opportunity_state == "pause_wait":
        dims = set()
        if valuation in ("expensive", "very_expensive"):
            dims.add("valuation")
        if heat in ("crowded", "overheated"):
            dims.add("heat")
        return frozenset(dims)
    if opportunity_state == "small_watch":
        if product == "weak":
            return frozenset({"product_quality"})
        if thesis == "evidence_insufficient":
            return frozenset({"thesis"})
        if valuation == "evidence_insufficient":
            return frozenset({"valuation"})
        if heat == "evidence_insufficient":
            return frozenset({"heat"})
        return frozenset()
    return frozenset()


def _structural_evidence_gaps(inp: OpportunityInput) -> list[str]:
    """Gaps for the non-thesis classifier inputs, using the typed labels from
    the May-14 spec (`missing_valuation_data`, `missing_flow_or_return_data`,
    `missing_product_metadata`)."""
    gaps: list[str] = []
    if inp.valuation_percentile_self is None and inp.valuation_percentile_vs_benchmark is None:
        gaps.append("missing_valuation_data")
    heat_n = sum(1 for x in [
        inp.ret_1m, inp.ret_3m, inp.ret_6m, inp.ret_12m,
        inp.premium_discount_pct, inp.flow_pct_30d,
    ] if x is not None)
    # Require at least 2 independent heat signals to classify heat reliably.
    # With only 1 signal the direction of crowding cannot be confirmed.
    if heat_n < 2:
        gaps.append("missing_flow_or_return_data")
    if inp.expense_ratio is None and inp.aum_cny is None:
        gaps.append("missing_product_metadata")
    return gaps


def _refined_table_gap(asset_class: str | None) -> str | None:
    """Refined gap label for the table-fallback path (no snapshot, no theme_report)."""
    if asset_class is None:
        return None
    if asset_class in NON_INDEXABLE_ASSET_CLASSES:
        return "constituent_not_applicable"
    return "constituent_missing"


def build_opportunity_row(
    inp: OpportunityInput,
    theme_thesis: dict[str, str] | None,
    *,
    snapshot: ConstituentSnapshot | ActiveFundSnapshot | FundLevelSnapshot | None = None,
    theme_report: ThemeReport | None = None,
) -> OpportunityRow:
    """Compose a full OpportunityRow for a single instrument. Pure function.

    Thesis state is preferentially derived from `snapshot` + `theme_report`
    via `derive_thesis_from_evidence` (concrete fundamentals). When neither
    is provided, fall back to the table-based `classify_thesis` path so the
    function stays usable in CLI contexts where the fundamentals layer has
    not yet been wired in. Either way, typed evidence-gap labels surface in
    `evidence_gaps`.
    """
    valuation, val_reason = classify_valuation(inp)
    heat, heat_reason = classify_heat(inp)
    product, product_reason = classify_product_quality(inp)

    structural_gaps = _structural_evidence_gaps(inp)
    constituent_analyses: tuple = ()
    if snapshot is not None or theme_report is not None:
        thesis, thesis_reason, evidence, thesis_gaps, constituent_analyses = (
            derive_thesis_from_evidence(
                snapshot, theme_report,
                asset_class=inp.asset_class,
                owner_instrument_id=inp.instrument_id,
            )
        )
    else:
        thesis, thesis_reason = classify_thesis(inp, theme_thesis)
        evidence = ()
        refined = _refined_table_gap(inp.asset_class)
        # Table-fallback path runs only when neither snapshot nor theme_report
        # was provided, so the news side is unambiguously stage_skipped.
        legacy = ("missing_constituent_snapshot", "news_stage_skipped")
        thesis_gaps = legacy + ((refined,) if refined is not None else ())

    state, state_reason = compose_opportunity_state(
        valuation, heat, thesis, product, inp.venue_compatible,
        valuation_fundamental=valuation_fundamental_signal(inp),
    )
    dimensions = derive_contributing_dimensions(valuation, heat, thesis, product, state)
    target = map_lookthrough(inp)
    reason = " | ".join([state_reason, val_reason, heat_reason, thesis_reason, product_reason])
    combined_gaps = tuple(structural_gaps) + tuple(thesis_gaps)
    evidence_gaps_filtered, expected_omissions, advisory_gaps = (
        _partition_gaps(combined_gaps)
    )
    return OpportunityRow(
        instrument_id=inp.instrument_id,
        name_cn=inp.name_cn,
        asset_class=inp.asset_class,
        theme=inp.theme,
        lookthrough_target=target,
        valuation_state=valuation,
        heat_state=heat,
        thesis_state=thesis,
        product_quality_state=product,
        opportunity_state=state,
        opportunity_reason=reason,
        evidence_gaps=evidence_gaps_filtered,
        expected_omissions=expected_omissions,
        advisory_gaps=advisory_gaps,
        thesis_evidence=evidence,
        contributing_dimensions=dimensions,
        fetch_types_attempted=derive_fetch_types_attempted(snapshot),
        constituent_analyses=constituent_analyses,
    )
