from __future__ import annotations

from irc.memo.picks_table import PickRow, render_picks_table
from irc.opportunity.types import ThesisEvidence


def test_render_picks_table_dedupes_and_lists_action_and_rationale():
    rows = [
        PickRow(
            instrument_id="518880", name_cn="华安黄金ETF", asset_class="gold",
            role="core_gold_hedge", target_weight=0.564, composite_score=51.8,
            opportunity_state="core_dca", dca_action="normal_dca", risk_action="none",
            one_line_reason="估值百分位 18% 偏低；近期回报 -3% 热度可控；产品费率 0.5% 合规",
        ),
        PickRow(
            instrument_id="006075", name_cn="易方达标普500", asset_class="us_etf",
            role="core_us_equity", target_weight=0.161, composite_score=52.4,
            opportunity_state="small_watch", dca_action="slow_dca", risk_action="none",
            one_line_reason="估值百分位 78% 偏高；放慢定投",
        ),
        # Duplicate of 006075 — must be dropped
        PickRow(
            instrument_id="006075", name_cn="易方达标普500", asset_class="us_etf",
            role="core_us_equity", target_weight=0.161, composite_score=52.4,
            opportunity_state="small_watch", dca_action="slow_dca", risk_action="none",
            one_line_reason="重复",
        ),
    ]
    md = render_picks_table(rows)
    assert "518880" in md and "华安黄金ETF" in md
    assert md.count("006075") == 1, "duplicate instrument_id must be deduped"
    # Header columns
    for col in ("代码", "名称", "角色", "权重上限", "机会状态", "本期行动", "主要理由"):
        assert col in md
    assert "综合分*" in md
    # Action labels expanded into Chinese
    assert "正常定投" in md  # normal_dca
    assert "减速定投" in md  # slow_dca
    # Target weights formatted as percentages, 1 decimal
    assert "56.4%" in md
    assert "16.1%" in md


def test_render_picks_table_appends_scoring_methodology_footnote():
    """Audit P5 (2026-05-20) — 综合分 is used to order picks but the memo
    never discloses methodology. Footnote must reference multi-factor
    derivation and include the explicit '不构成投资建议' disclaimer."""
    rows = [
        PickRow(
            instrument_id="518880", name_cn="华安黄金ETF", asset_class="gold",
            role="core_gold_hedge", target_weight=0.564, composite_score=51.8,
            opportunity_state="core_dca", dca_action="normal_dca", risk_action="none",
            one_line_reason="reason",
        ),
    ]
    md = render_picks_table(rows)
    assert "综合分" in md
    # Footnote present (the load-bearing disclaimer phrase from the audit):
    assert "不构成投资建议" in md
    # Mention factor composition so the score isn't a black box:
    assert ("估值" in md and "热度" in md) or "多因子" in md


def test_render_picks_table_marks_scores_with_incomplete_valuation_data():
    row = PickRow(
        instrument_id="511010", name_cn="国债ETF国泰", asset_class="bond",
        role="defensive_bond", target_weight=0.1, composite_score=75.6,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="估值数据缺失，列入观察",
        valuation_state="evidence_insufficient",
    )
    md = render_picks_table([row])
    assert "75.6（估值维度缺失，不得用于优先级比较）" in md
    assert "N/A（估值维度数据缺失，分值无效，不得用于优先级比较）" not in md


def test_render_picks_table_slow_dca_is_conditionally_worded():
    row = PickRow(
        instrument_id="519770", name_cn="交银优择回报灵活配置混合A",
        asset_class="active_fund", role="satellite", target_weight=0.1,
        composite_score=74.2, opportunity_state="small_watch",
        dca_action="slow_dca", risk_action="none",
        one_line_reason="等待回撤触发",
    )
    md = render_picks_table([row])
    assert "条件性减速定投（触发条件见第7节；未触发则不执行）" in md


def test_render_picks_table_footnote_defines_weight_as_cap_and_score_limits():
    row = PickRow(
        instrument_id="511220", name_cn="城投债ETF海富通", asset_class="bond",
        role="defensive_bond", target_weight=0.04, composite_score=75.6,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="估值数据缺失",
        valuation_state="evidence_insufficient",
    )
    md = render_picks_table([row])
    assert "权重均为上限约束" in md
    assert "非强制建仓目标" in md
    assert "不得单独依据分值高低" in md


def test_render_picks_table_footnote_only_once_even_with_many_rows():
    """Two rows in, one footnote out — footnote must not be duplicated per row."""
    rows = [
        PickRow(
            instrument_id="A", name_cn="一", asset_class="x", role="r",
            target_weight=0.1, composite_score=10.0, opportunity_state="core_dca",
            dca_action="normal_dca", risk_action="none", one_line_reason="x",
        ),
        PickRow(
            instrument_id="B", name_cn="二", asset_class="x", role="r",
            target_weight=0.1, composite_score=10.0, opportunity_state="core_dca",
            dca_action="normal_dca", risk_action="none", one_line_reason="x",
        ),
    ]
    md = render_picks_table(rows)
    assert md.count("不构成投资建议") == 1


def test_render_picks_table_marks_no_proxy_venue_as_currently_unexecutable():
    row = PickRow(
        instrument_id="511220", name_cn="城投债ETF海富通", asset_class="bond",
        role="defensive_bond", target_weight=0.04, composite_score=75.6,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="估值数据缺失",
        venue_note="venue mismatch and no proxy available",
    )
    md = render_picks_table([row])
    assert "渠道不匹配，当前无法执行" in md
    assert "待渠道开通方可执行" in md


def test_render_picks_table_footnote_emitted_even_when_no_rows():
    """Empty picks table still gets the disclaimer — methodology disclosure
    is decoupled from row count. Header row must also be present so the
    footnote isn't a bare blockquote (review nit)."""
    md = render_picks_table([])
    assert "不构成投资建议" in md
    # Header invariant: the table scaffolding (column titles + separator)
    # must render regardless of row count, otherwise the footnote would
    # appear as a bare blockquote.
    assert "代码" in md and "名称" in md
    assert "|---|" in md


def test_render_picks_table_groups_zero_weight_as_observation_only():
    rows = [
        PickRow(
            instrument_id="510050", name_cn="上证50ETF", asset_class="cn_etf",
            role="core_cn_equity", target_weight=0.0, composite_score=59.9,
            opportunity_state="small_watch", dca_action="slow_dca", risk_action="none",
            one_line_reason="渠道不可购买，仅观察",
        ),
    ]
    md = render_picks_table(rows)
    assert "仅观察" in md
    assert "0.0%" in md or "观察" in md


def _evidence(**over) -> ThesisEvidence:
    base = dict(
        type="filing", source="600519",
        url="https://example.com/600519", date="2026-04-28",
        summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="510300",
        parent_fund_id=None, constituent_key="600519",
    )
    base.update(over)
    return ThesisEvidence(**base)


def test_render_picks_table_emits_citation_markers_in_evidence_column():
    """证据 column renders `[ref:{citation_id}] {type}·{source}·{date}` per citation;
    multiple citations on one row joined by `<br>` so the markdown cell stays
    single-row."""
    ev_a = _evidence(url="https://example.com/a", date="2026-04-28")
    ev_b = _evidence(url="https://example.com/b", date="2026-05-02",
                     type="broker", source="中信证券", citation_kind="information")
    row = PickRow(
        instrument_id="510300", name_cn="华泰柏瑞沪深300ETF",
        asset_class="cn_etf", role="core_cn_equity",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="r",
        citations=(ev_a, ev_b),
    )
    md = render_picks_table([row])
    # Header includes 证据 column.
    assert "证据" in md
    # Each citation renders its citation_id marker.
    assert f"[ref:{ev_a.citation_id}]" in md
    assert f"[ref:{ev_b.citation_id}]" in md
    # Joined by <br> in a single cell.
    assert "<br>" in md
    # Render format includes type·source·date.
    assert "filing·600519·2026-04-28" in md
    assert "broker·中信证券·2026-05-02" in md


def test_render_picks_table_includes_decision_column_with_zh_map():
    """决策 column lives between 综合分* and 机会状态. Cell value maps
    decision_status to ZH per the spec."""
    rows = [
        PickRow(
            instrument_id="A", name_cn="ai", asset_class="x", role="r",
            target_weight=0.1, composite_score=50.0,
            opportunity_state="core_dca", dca_action="normal_dca",
            risk_action="none", one_line_reason="x",
            decision_status="actionable_buy",
        ),
        PickRow(
            instrument_id="B", name_cn="bi", asset_class="x", role="r",
            target_weight=0.1, composite_score=50.0,
            opportunity_state="pause_wait", dca_action="pause_dca",
            risk_action="none", one_line_reason="x",
            decision_status="blocked",
        ),
        PickRow(
            instrument_id="C", name_cn="ci", asset_class="x", role="r",
            target_weight=0.1, composite_score=50.0,
            opportunity_state="small_watch", dca_action="slow_dca",
            risk_action="none", one_line_reason="x",
            decision_status="watch_only",
        ),
        PickRow(
            instrument_id="D", name_cn="di", asset_class="x", role="r",
            target_weight=0.1, composite_score=50.0,
            opportunity_state="exclude", dca_action="do_not_buy",
            risk_action="none", one_line_reason="x",
            decision_status="avoid",
        ),
    ]
    md = render_picks_table(rows)
    # New 决策 column header is present and positioned between 综合分* and 机会状态.
    header_line = next(line for line in md.split("\n") if line.startswith("| 代码"))
    cols = [c.strip() for c in header_line.strip("|").split("|")]
    assert "决策" in cols
    assert cols.index("决策") == cols.index("综合分*") + 1
    assert cols.index("决策") + 1 == cols.index("机会状态")
    # ZH map renders on the four rows.
    assert "候选可执行" in md
    assert "阻断" in md
    assert "观察" in md
    assert "回避" in md


def test_pick_row_decision_status_defaults_to_watch_only():
    """Existing tests build PickRow without decision_status. Default keeps
    backwards compatibility so they still pass."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
    )
    assert row.decision_status == "watch_only"


def test_pick_row_tranche_cap_pct_defaults_to_none():
    """Backward compatibility: existing callers/tests omit the new field;
    default keeps the legacy construction site call sites compiling unchanged."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
    )
    assert row.tranche_cap_pct is None


def test_pick_row_trigger_status_defaults_to_empty_string():
    """Backward compatibility: omitted field defaults to '' so the renderer
    emits em-dash, matching the empty-citations convention."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
    )
    assert row.trigger_status == ""


def test_picks_table_header_contains_tranche_cap_and_trigger_status_columns():
    """Header order locked: ... | 主要理由 | 单次定投上限 | 触发状态 | 证据 |."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
    )
    md = render_picks_table([row])
    header_line = next(line for line in md.split("\n") if line.startswith("| 代码"))
    cols = [c.strip() for c in header_line.strip("|").split("|")]
    assert "单次定投上限" in cols
    assert "触发状态" in cols
    # Order: 主要理由 → 单次定投上限 → 触发状态 → 证据
    assert cols.index("单次定投上限") == cols.index("主要理由") + 1
    assert cols.index("触发状态") == cols.index("单次定投上限") + 1
    assert cols.index("证据") == cols.index("触发状态") + 1


def test_picks_table_tranche_cap_renders_with_two_decimals_and_le_prefix():
    """`tranche_cap_pct=0.05` → cell shows `≤ 5.00%` (two decimals, locked)."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.2, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        tranche_cap_pct=0.05,
    )
    md = render_picks_table([row])
    assert "≤ 5.00%" in md


def test_picks_table_tranche_cap_none_renders_em_dash():
    """`tranche_cap_pct=None` → cell shows `—` (matches empty-citations convention)."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.0, composite_score=50.0,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
        tranche_cap_pct=None,
    )
    md = render_picks_table([row])
    # Find the data row and confirm an em-dash appears
    data_lines = [line for line in md.split("\n")
                  if line.startswith("| A ")]
    assert data_lines, "no data row found for A"
    assert "| — |" in data_lines[0]


def test_picks_table_tranche_cap_zero_renders_em_dash():
    """`tranche_cap_pct=0.0` (observation-only pick) → cell shows `—`,
    not `≤ 0.00%` which would be visually misleading."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.0, composite_score=50.0,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", one_line_reason="x",
        tranche_cap_pct=0.0,
    )
    md = render_picks_table([row])
    data_lines = [line for line in md.split("\n")
                  if line.startswith("| A ")]
    assert "≤ 0.00%" not in data_lines[0]
    assert "| — |" in data_lines[0]


def test_picks_table_trigger_status_renders_verbatim_when_non_empty():
    """Pre-formatted string is rendered as-is — renderer does not re-evaluate."""
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        trigger_status="vix_above_25 ✓<br>weekly_drawdown_4pct ✗",
    )
    md = render_picks_table([row])
    assert "vix_above_25 ✓<br>weekly_drawdown_4pct ✗" in md


def test_picks_table_trigger_status_empty_renders_em_dash():
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        trigger_status="",
    )
    md = render_picks_table([row])
    data_lines = [line for line in md.split("\n")
                  if line.startswith("| A ")]
    assert "| — |" in data_lines[0]


def test_picks_table_footnote_explains_tranche_cap_and_trigger_status():
    """Footnote text gains a short clause about both new columns. Existing
    audit P5 disclaimer (不构成投资建议) must remain the closing token."""
    md = render_picks_table([])
    assert "单次定投上限" in md
    assert "触发状态" in md
    assert "build" in md or "目标权重" in md
    # P5 lock: 不构成投资建议 stays present
    assert "不构成投资建议" in md


def test_picks_table_new_columns_carry_no_citation_markers():
    """SAME-3 invariant guard: 单次定投上限 + 触发状态 cells must not emit
    any [ref:...] markers. All citations live in the 证据 column."""
    import re
    row = PickRow(
        instrument_id="A", name_cn="ai", asset_class="x", role="r",
        target_weight=0.2, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="x",
        tranche_cap_pct=0.05,
        trigger_status="vix_above_25 ✓<br>weekly_drawdown_4pct ✗",
    )
    md = render_picks_table([row])
    data_lines = [line for line in md.split("\n")
                  if line.startswith("| A ")]
    assert data_lines
    cells = [c.strip() for c in data_lines[0].strip("|").split("|")]
    # The two new cells are at positions [-3] and [-2] (证据 is last)
    tranche_cell = cells[-3]
    trigger_cell = cells[-2]
    assert not re.search(r"\[ref:[0-9a-f]{16}\]", tranche_cell)
    assert not re.search(r"\[ref:[0-9a-f]{16}\]", trigger_cell)


def test_render_picks_table_empty_citations_renders_dash():
    """When PickRow.citations is empty, the 证据 cell renders `—`."""
    row = PickRow(
        instrument_id="518880", name_cn="华安黄金ETF", asset_class="gold",
        role="core_gold_hedge", target_weight=0.1, composite_score=50.0,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", one_line_reason="r",
    )
    md = render_picks_table([row])
    # Find the data row for 518880 and confirm the dash appears as a cell.
    rows_lines = [line for line in md.split("\n")
                  if "518880" in line and "|" in line]
    assert rows_lines, "no data row found for 518880"
    assert "| — |" in rows_lines[0]
