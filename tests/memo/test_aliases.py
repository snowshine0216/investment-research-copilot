"""Item 007 D1c — alias-builder.

Tests cover acceptance criteria 7–9 + multi-owner + collision invariant
per [ADR 0004 §1 + §2](../../../docs/adr/0004-renderer-determinism-and-alias-policy.md).
"""
import pytest


def _opportunity_row(
    *, iid: str, name_cn: str = "", asset_class: str = "cn_equity_fund",
    constituent_analyses: tuple = (), lookthrough_key: str = "",
):
    """Factory: minimal OpportunityRow for alias-builder tests."""
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    return OpportunityRow(
        instrument_id=iid,
        name_cn=name_cn,
        asset_class=asset_class,
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key=lookthrough_key or iid,
            display_cn=name_cn, provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=(),
        thesis_evidence=(),
        constituent_analyses=constituent_analyses,
    )


def _constituent(symbol: str, name_cn: str = "", weight: float = 5.0):
    from irc.fundamentals.types import ConstituentAnalysis
    return ConstituentAnalysis(
        symbol=symbol, name_cn=name_cn or symbol, weight_pct=weight,
        evidence=(), failure_reasons=(), one_line_view="",
    )


def test_build_alias_maps_instrument_aliases_basic() -> None:
    from irc.memo.aliases import build_alias_maps
    rows = (
        _opportunity_row(iid="005827", name_cn="易方达蓝筹精选"),
        _opportunity_row(iid="163417", name_cn="兴全合润"),
        _opportunity_row(iid="518880", name_cn="黄金ETF",
                         asset_class="gold"),
    )
    inst, _ = build_alias_maps(rows)
    assert inst["005827"] == "005827"
    assert inst["易方达蓝筹精选"] == "005827"
    assert inst["163417"] == "163417"
    assert inst["兴全合润"] == "163417"
    assert inst["518880"] == "518880"
    assert inst["黄金ETF"] == "518880"


def test_build_alias_maps_skips_empty_name_cn() -> None:
    from irc.memo.aliases import build_alias_maps
    rows = (_opportunity_row(iid="005827", name_cn=""),)
    inst, _ = build_alias_maps(rows)
    assert "" not in inst
    assert inst["005827"] == "005827"


def test_build_alias_maps_constituent_aliases_multi_owner() -> None:
    """600519 held by both 005827 and 163417 → frozenset of 2 tuples."""
    from irc.memo.aliases import build_alias_maps
    rows = (
        _opportunity_row(iid="005827", name_cn="易方达蓝筹精选",
                         constituent_analyses=(
                             _constituent("600519", "贵州茅台", 8.2),
                             _constituent("300750", "宁德时代", 6.0),
                         )),
        _opportunity_row(iid="163417", name_cn="兴全合润",
                         constituent_analyses=(
                             _constituent("600519", "贵州茅台", 7.5),
                             _constituent("601318", "中国平安", 5.5),
                         )),
    )
    _, cons = build_alias_maps(rows)
    assert cons["600519"] == frozenset({("005827", "600519"), ("163417", "600519")})
    assert cons["贵州茅台"] == frozenset({("005827", "600519"), ("163417", "600519")})
    assert cons["300750"] == frozenset({("005827", "300750")})
    assert cons["宁德时代"] == frozenset({("005827", "300750")})
    assert cons["601318"] == frozenset({("163417", "601318")})


def test_build_alias_maps_constituent_aliases_skip_empty_name() -> None:
    from irc.memo.aliases import build_alias_maps
    rows = (_opportunity_row(iid="005827", name_cn="X",
                              constituent_analyses=(
                                  _constituent("600519", "", 8.2),
                              )),)
    _, cons = build_alias_maps(rows)
    assert "" not in cons
    assert cons["600519"] == frozenset({("005827", "600519")})


def test_build_alias_maps_instrument_collision_raises() -> None:
    """Two rows with the same name_cn but different instrument_id → raise."""
    from irc.memo.aliases import build_alias_maps, InstrumentAliasCollisionError
    rows = (
        _opportunity_row(iid="005827", name_cn="某基金"),
        _opportunity_row(iid="163417", name_cn="某基金"),
    )
    with pytest.raises(InstrumentAliasCollisionError) as exc:
        build_alias_maps(rows)
    msg = str(exc.value)
    assert "005827" in msg
    assert "163417" in msg
    assert "某基金" in msg


def test_build_alias_maps_duplicate_iid_does_not_raise() -> None:
    """Two rows sharing the SAME instrument_id collapse without raising
    (a bug in upstream H3 partition; alias-builder is permissive)."""
    from irc.memo.aliases import build_alias_maps
    rows = (
        _opportunity_row(iid="005827", name_cn="易方达蓝筹精选"),
        _opportunity_row(iid="005827", name_cn="易方达蓝筹精选"),
    )
    inst, _ = build_alias_maps(rows)
    assert inst["005827"] == "005827"
    assert inst["易方达蓝筹精选"] == "005827"


def test_build_alias_maps_empty_rows_returns_empty_maps() -> None:
    from irc.memo.aliases import build_alias_maps
    inst, cons = build_alias_maps(())
    assert inst == {}
    assert cons == {}


def test_build_alias_maps_collision_error_message_lists_iids_sorted() -> None:
    """Error message includes both instrument_id values, sorted ASC."""
    from irc.memo.aliases import build_alias_maps, InstrumentAliasCollisionError
    rows = (
        _opportunity_row(iid="163417", name_cn="某基金"),
        _opportunity_row(iid="005827", name_cn="某基金"),
    )
    with pytest.raises(InstrumentAliasCollisionError) as exc:
        build_alias_maps(rows)
    msg = str(exc.value)
    # Sorted ascending — '005827' appears before '163417'.
    assert msg.index("005827") < msg.index("163417")


def test_build_alias_maps_returns_dict_types() -> None:
    """Return shape: (dict[str, str], dict[str, frozenset[tuple[str, str]]])."""
    from irc.memo.aliases import build_alias_maps
    rows = (_opportunity_row(iid="005827", name_cn="X",
                              constituent_analyses=(_constituent("600519", "Y"),)),)
    inst, cons = build_alias_maps(rows)
    assert isinstance(inst, dict)
    assert isinstance(cons, dict)
    for v in cons.values():
        assert isinstance(v, frozenset)
        for tup in v:
            assert isinstance(tup, tuple) and len(tup) == 2


def test_build_alias_maps_two_etfs_with_same_shared_lookthrough_key_do_not_collide() -> None:
    """Regression — post-ship code-review surfaced that `_instrument_alias_keys`
    appended `lookthrough_target.key` unconditionally when distinct from
    `instrument_id`. For broad-index ETFs that key is a SHARED descriptor
    (`csi300`, `gold`, `cn_bond`, `qdii_us`, …), causing every pair of
    publishable ETFs tracking the same index to raise
    `InstrumentAliasCollisionError`. Fix: only include the lookthrough key
    when it textually contains the `instrument_id` (i.e. it's a unique
    venue-suffixed or `fund_{iid}` form, not a shared descriptor)."""
    from irc.fundamentals.types import LookthroughTarget
    from irc.memo.aliases import build_alias_maps
    from irc.opportunity.types import OpportunityRow

    def _bi_row(iid: str, name: str) -> OpportunityRow:
        return OpportunityRow(
            instrument_id=iid, name_cn=name, asset_class="cn_etf", theme=None,
            lookthrough_target=LookthroughTarget(
                kind="broad_index", key="csi300", display_cn="沪深300",
                provider_symbol=iid,
            ),
            valuation_state="fair", heat_state="normal",
            thesis_state="intact", product_quality_state="strong",
            opportunity_state="core_dca", opportunity_reason="",
            evidence_gaps=(), thesis_evidence=(),
            constituent_analyses=(),
        )

    rows = (
        _bi_row("510300", "华泰柏瑞沪深300ETF"),
        _bi_row("159919", "嘉实沪深300ETF"),
    )
    # MUST NOT raise (used to raise InstrumentAliasCollisionError before the fix).
    inst, _ = build_alias_maps(rows)
    # The shared `csi300` key is NEVER an alias for either ETF.
    assert "csi300" not in inst, \
        "shared lookthrough_target.key must not appear as alias"
    # The bare iid + name_cn aliases ARE present.
    assert inst["510300"] == "510300"
    assert inst["159919"] == "159919"
    assert inst["华泰柏瑞沪深300ETF"] == "510300"
    assert inst["嘉实沪深300ETF"] == "159919"


def test_build_alias_maps_includes_lookthrough_key_when_it_embeds_iid() -> None:
    """The `fund_{iid}` form (active_fund kind) MUST still alias because the
    key uniquely identifies the row. Same for hypothetical `{iid}.SH` venue
    forms."""
    from irc.fundamentals.types import LookthroughTarget
    from irc.memo.aliases import build_alias_maps
    from irc.opportunity.types import OpportunityRow

    row = OpportunityRow(
        instrument_id="005827", name_cn="易方达蓝筹精选", asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="fund_005827", display_cn="易方达蓝筹精选",
            provider_symbol="005827",
        ),
        valuation_state="fair", heat_state="normal",
        thesis_state="intact", product_quality_state="strong",
        opportunity_state="core_dca", opportunity_reason="",
        evidence_gaps=(), thesis_evidence=(),
        constituent_analyses=(),
    )
    inst, _ = build_alias_maps((row,))
    assert inst["fund_005827"] == "005827", \
        "fund_{iid} embeds the iid → safe to alias"
