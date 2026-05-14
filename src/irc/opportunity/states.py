from __future__ import annotations

import math

from irc.opportunity.types import (
    HeatState,
    OpportunityInput,
    OpportunityRow,
    OpportunityState,
    ProductQualityState,
    ThesisState,
    ValuationState,
)


# ---------------------------------------------------------------------------
# Task 3: Valuation classifier
# ---------------------------------------------------------------------------

def _percentile(inp: OpportunityInput) -> float | None:
    """Prefer self-history percentile; fall back to vs-benchmark."""
    if inp.valuation_percentile_self is not None:
        return inp.valuation_percentile_self
    return inp.valuation_percentile_vs_benchmark


def classify_valuation(inp: OpportunityInput) -> tuple[ValuationState, str]:
    """Classify valuation state. Bands:
      cheap: pct < 0.20
      reasonable_low: 0.20 <= pct < 0.40
      fair: 0.40 <= pct < 0.70
      expensive: 0.70 <= pct < 0.90
      very_expensive: pct >= 0.90
    Drawdown alone is NEVER evidence of cheapness.
    """
    pct = _percentile(inp)
    if pct is None:
        return "evidence_insufficient", "估值数据缺失，未能判定。"
    if pct < 0.20:
        return "cheap", f"估值百分位 {pct:.0%} 偏低。"
    if pct < 0.40:
        return "reasonable_low", f"估值百分位 {pct:.0%} 偏低但未极低。"
    if pct < 0.70:
        return "fair", f"估值百分位 {pct:.0%} 中性。"
    if pct < 0.90:
        return "expensive", f"估值百分位 {pct:.0%} 偏高。"
    return "very_expensive", f"估值百分位 {pct:.0%} 极高。"


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


def classify_product_quality(inp: OpportunityInput) -> tuple[ProductQualityState, str]:
    """Classify product quality. Active funds require manager tenure +
    AUM stability evidence to exceed 'weak'."""
    if _is_active_fund(inp):
        if inp.manager_tenure_years is None or inp.aum_stability_pct is None:
            if inp.manager_tenure_years is None and inp.aum_stability_pct is None:
                return "evidence_insufficient", "主动基金缺少基金经理与AUM稳定性证据。"
            return "weak", "主动基金证据不足，未达可推荐水平。"
        if inp.manager_tenure_years < 2.0:
            return "weak", "基金经理任职年限不足两年。"
        score, n = _passive_quality_score(inp)
        if n < 2:
            return "weak", "主动基金成本/规模证据不足。"
        if score >= 0.5 and inp.manager_tenure_years >= 5.0:
            return "strong", "主动基金长期经理 + 优良成本/规模。"
        if score >= 0.0:
            return "acceptable", "主动基金达到可观察标准。"
        return "weak", "主动基金成本或规模存在明显劣势。"

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

from irc.opportunity.lookthrough import map_lookthrough  # noqa: E402


def compose_opportunity_state(
    valuation: ValuationState,
    heat: HeatState,
    thesis: ThesisState,
    product_quality: ProductQualityState,
) -> tuple[OpportunityState, str]:
    """Compose final opportunity state from four sub-states."""
    if thesis == "falsified" or product_quality == "poor":
        return "exclude", "长期逻辑被证伪或产品质量过差，禁止建仓。"

    cheap_or_low = valuation in ("cheap", "reasonable_low")
    expensive = valuation in ("expensive", "very_expensive")
    quiet_heat = heat in ("cold", "normal")
    hot_heat = heat in ("crowded", "overheated")
    intact_thesis = thesis == "intact"
    decent_product = product_quality in ("acceptable", "strong")

    if cheap_or_low and quiet_heat and intact_thesis and decent_product:
        return "core_dca", "估值便宜、热度可控、长期逻辑完好、产品质量合格，适合定投。"

    if expensive or hot_heat:
        return "pause_wait", "估值偏高或热度偏高，暂停加仓等待回落。"

    return "small_watch", "证据不完整或信号不一致，列入小仓位观察。"


def _evidence_gaps(inp: OpportunityInput) -> tuple[str, ...]:
    gaps: list[str] = []
    if inp.valuation_percentile_self is None and inp.valuation_percentile_vs_benchmark is None:
        gaps.append("valuation")
    if inp.ret_3m is None and inp.ret_6m is None and inp.premium_discount_pct is None:
        gaps.append("heat")
    if inp.theme is None:
        gaps.append("theme_thesis")
    if inp.expense_ratio is None and inp.aum_cny is None:
        gaps.append("product_quality")
    return tuple(gaps)


def build_opportunity_row(
    inp: OpportunityInput,
    theme_thesis: dict[str, str] | None,
) -> OpportunityRow:
    """Compose a full OpportunityRow for a single instrument. Pure function."""
    valuation, val_reason = classify_valuation(inp)
    heat, heat_reason = classify_heat(inp)
    thesis, thesis_reason = classify_thesis(inp, theme_thesis)
    product, product_reason = classify_product_quality(inp)
    state, state_reason = compose_opportunity_state(valuation, heat, thesis, product)
    target = map_lookthrough(inp)
    gaps = _evidence_gaps(inp)
    reason = " | ".join([state_reason, val_reason, heat_reason, thesis_reason, product_reason])
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
        evidence_gaps=gaps,
    )
