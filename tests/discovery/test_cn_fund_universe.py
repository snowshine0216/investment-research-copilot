from __future__ import annotations

from irc.discovery.cn_fund_universe import (
    UniverseBuildOptions,
    build_cn_fund_universe,
    classify_catalog_fund,
    dedupe_share_classes,
    infer_theme,
    normalize_catalog_rows,
    serialize_universe,
)


def test_normalize_catalog_rows_uses_stable_column_names() -> None:
    rows = [
        {"fund_code": 110022, "fund_name": "易方达消费行业股票A", "fund_type": "股票型"},
        {"fund_code": "003095", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"},
    ]

    out = normalize_catalog_rows(rows)

    assert [fund.fund_code for fund in out] == ["110022", "003095"]
    assert out[0].fund_name == "易方达消费行业股票A"


def test_normalize_catalog_rows_skips_rows_without_required_fields() -> None:
    rows = [
        {"fund_code": "110022", "fund_name": "易方达消费行业股票A", "fund_type": "股票型"},
        {"fund_code": "", "fund_name": "无代码基金", "fund_type": "股票型"},
        {"fund_code": "000000", "fund_name": "", "fund_type": "股票型"},
    ]

    out = normalize_catalog_rows(rows)

    assert [fund.fund_code for fund in out] == ["110022"]


def test_excludes_money_market_short_cash_fof_and_abnormal_status() -> None:
    instruments = build_cn_fund_universe([
        {"fund_code": "000001", "fund_name": "华夏现金增利货币A", "fund_type": "货币型"},
        {"fund_code": "000002", "fund_name": "招商短债债券A", "fund_type": "债券型"},
        {"fund_code": "000003", "fund_name": "南方养老FOF", "fund_type": "FOF"},
        {"fund_code": "000004", "fund_name": "某某基金清算", "fund_type": "混合型"},
        {"fund_code": "000005", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"},
    ])

    assert [instrument.instrument_id for instrument in instruments] == ["000005"]


def test_theme_inference_matches_supported_literals() -> None:
    assert infer_theme("华泰柏瑞沪深300ETF", "指数型") == "broad"
    assert infer_theme("中证红利低波ETF", "指数型") == "dividend"
    assert infer_theme("科技创新混合A", "混合型") == "tech"
    assert infer_theme("半导体芯片ETF", "指数型") == "semiconductor"
    assert infer_theme("军工龙头股票A", "股票型") == "defense"
    assert infer_theme("中欧医疗健康混合A", "混合型") == "healthcare"
    assert infer_theme("新能源车电池ETF", "指数型") == "new_energy"
    assert infer_theme("消费食品饮料股票A", "股票型") == "consumer"
    assert infer_theme("银行证券金融ETF", "指数型") == "finance"
    assert infer_theme("有色金属资源ETF", "指数型") == "metals"
    assert infer_theme("房地产ETF", "指数型") == "real_estate"
    assert infer_theme("央企国企改革ETF", "指数型") == "soe"
    assert infer_theme("朱少醒价值精选混合A", "混合型") is None


def test_classifies_active_equity_without_theme_as_cn_equity_fund() -> None:
    fund = normalize_catalog_rows([
        {"fund_code": "519035", "fund_name": "富国天博创新主题混合A", "fund_type": "混合型"}
    ])[0]

    classified = classify_catalog_fund(fund)

    assert classified is not None
    assert classified.asset_class == "cn_equity_fund"
    assert classified.market == "cn_off_exchange"
    assert classified.theme is None
    assert classified.venue_required == ("cmb_fund",)


def test_classifies_domestic_etf_only_with_exchange_traded_evidence() -> None:
    etf = normalize_catalog_rows([
        {"fund_code": "510300", "fund_name": "华泰柏瑞沪深300ETF", "fund_type": "指数型-股票"}
    ])[0]
    index_fund = normalize_catalog_rows([
        {"fund_code": "110020", "fund_name": "易方达沪深300指数增强A", "fund_type": "指数型"}
    ])[0]

    classified_etf = classify_catalog_fund(etf)
    classified_index = classify_catalog_fund(index_fund)

    assert classified_etf is not None
    assert classified_etf.asset_class == "cn_etf"
    assert classified_etf.market == "cn_on_exchange"
    assert classified_etf.tracked_index == "沪深300"
    assert classified_index is not None
    assert classified_index.asset_class == "cn_equity_fund"
    assert classified_index.market == "cn_off_exchange"


def test_classifies_qdii_us_and_hk_exposure() -> None:
    instruments = build_cn_fund_universe([
        {"fund_code": "006075", "fund_name": "易方达标普500人民币A", "fund_type": "QDII"},
        {"fund_code": "159920", "fund_name": "恒生ETF华夏", "fund_type": "QDII-ETF"},
    ])

    by_id = {instrument.instrument_id: instrument for instrument in instruments}
    assert by_id["006075"].asset_class == "us_etf"
    assert by_id["006075"].market == "cn_off_exchange"
    assert by_id["006075"].tracked_index == "S&P 500"
    assert by_id["159920"].asset_class == "hk_etf"
    assert by_id["159920"].market == "cn_on_exchange"
    assert by_id["159920"].tracked_index == "Hang Seng"


def test_dedupes_share_classes_preferring_a_over_c() -> None:
    funds = normalize_catalog_rows([
        {"fund_code": "003096", "fund_name": "中欧医疗健康混合C", "fund_type": "混合型"},
        {"fund_code": "003095", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"},
    ])

    out = dedupe_share_classes(funds)

    assert [fund.fund_code for fund in out] == ["003095"]


def test_caps_candidates_by_asset_class_and_theme() -> None:
    rows = [
        {"fund_code": f"10{i:04d}", "fund_name": f"消费行业股票{i}A", "fund_type": "股票型"}
        for i in range(5)
    ] + [
        {"fund_code": f"20{i:04d}", "fund_name": f"均衡成长混合{i}A", "fund_type": "混合型"}
        for i in range(5)
    ] + [
        {"fund_code": f"30{i:04d}", "fund_name": f"债券精选{i}A", "fund_type": "债券型"}
        for i in range(5)
    ]
    options = UniverseBuildOptions(active_broad_cap=2, theme_cap=3, bond_cap=2, cn_etf_cap=10, us_qdii_cap=10, hk_qdii_cap=10)

    out = build_cn_fund_universe(rows, options=options)

    consumer = [instrument for instrument in out if instrument.theme == "consumer"]
    growth = [instrument for instrument in out if instrument.asset_class == "cn_equity_fund" and instrument.theme is None]
    bonds = [instrument for instrument in out if instrument.asset_class == "cn_bond_fund"]
    assert len(consumer) == 3
    assert len(growth) == 2
    assert len(bonds) == 2


def test_serialized_universe_validates_as_yaml_compatible_shape() -> None:
    instruments = build_cn_fund_universe([
        {"fund_code": "003095", "fund_name": "中欧医疗健康混合A", "fund_type": "混合型"}
    ])

    out = serialize_universe(instruments)

    assert out == {
        "instruments": [
            {
                "instrument_id": "003095",
                "ticker": "003095",
                "market": "cn_off_exchange",
                "name_cn": "中欧医疗健康混合A",
                "asset_class": "cn_equity_fund",
                "currency": "cny",
                "theme": "healthcare",
                "venue_required": ["cmb_fund"],
            }
        ]
    }


def test_dedupe_excludes_etf_feeder_in_favor_of_main_etf() -> None:
    out = build_cn_fund_universe([
        {"fund_code": "510300", "fund_name": "华泰柏瑞沪深300ETF", "fund_type": "指数型-股票"},
        {"fund_code": "000311", "fund_name": "华泰柏瑞沪深300ETF联接A", "fund_type": "指数型"},
        {"fund_code": "004752", "fund_name": "华泰柏瑞沪深300ETF联接C", "fund_type": "指数型"},
    ])
    ids = [i.instrument_id for i in out]
    assert "510300" in ids
    assert "000311" not in ids
    assert "004752" not in ids


def test_candidate_rank_with_returns_prefers_higher_1y_return():
    from irc.discovery.cn_fund_universe import (
        CatalogFund, ClassifiedFund, _candidate_rank_with_returns,
    )

    def make(code: str, name: str = "test fund") -> ClassifiedFund:
        return ClassifiedFund(
            catalog=CatalogFund(fund_code=code, fund_name=name, fund_type=""),
            asset_class="cn_equity_fund",
            market="cn_off_exchange",
            currency="cny",
            tracked_index=None,
            theme=None,
            venue_required=("cmb_fund",),
        )

    returns = {"270023": 45.3, "000001": -3.5, "100100": 12.0}
    items = [make("000001"), make("270023"), make("100100"), make("999999")]
    rank = _candidate_rank_with_returns(returns)
    ordered = sorted(items, key=rank)

    # 270023 (45.3%) first, then 100100 (12.0%), then 000001 (-3.5%),
    # then 999999 (no return — sorts last by fund_code among unranked).
    assert [it.catalog.fund_code for it in ordered] == ["270023", "100100", "000001", "999999"]


def test_candidate_rank_with_returns_falls_back_to_fund_code_when_empty():
    from irc.discovery.cn_fund_universe import (
        CatalogFund, ClassifiedFund, _candidate_rank, _candidate_rank_with_returns,
    )

    def make(code: str) -> ClassifiedFund:
        return ClassifiedFund(
            catalog=CatalogFund(fund_code=code, fund_name="x", fund_type=""),
            asset_class="cn_equity_fund",
            market="cn_off_exchange",
            currency="cny",
            tracked_index=None,
            theme=None,
            venue_required=("cmb_fund",),
        )

    items = [make("270023"), make("000001"), make("100100")]
    legacy = sorted(items, key=_candidate_rank)
    via_empty_map = sorted(items, key=_candidate_rank_with_returns({}))

    assert [it.catalog.fund_code for it in legacy] == [it.catalog.fund_code for it in via_empty_map]


def test_candidate_rank_with_returns_preserves_feeder_penalty():
    from irc.discovery.cn_fund_universe import (
        CatalogFund, ClassifiedFund, _candidate_rank_with_returns,
    )

    feeder = ClassifiedFund(
        catalog=CatalogFund(fund_code="000001", fund_name="某基金联接A", fund_type=""),
        asset_class="cn_equity_fund", market="cn_off_exchange", currency="cny",
        tracked_index=None, theme=None, venue_required=("cmb_fund",),
    )
    direct = ClassifiedFund(
        catalog=CatalogFund(fund_code="000002", fund_name="某基金A", fund_type=""),
        asset_class="cn_equity_fund", market="cn_off_exchange", currency="cny",
        tracked_index=None, theme=None, venue_required=("cmb_fund",),
    )

    # Feeder has a higher 1Y return but should still sort after direct because of penalty.
    returns = {"000001": 99.9, "000002": 1.0}
    ordered = sorted([feeder, direct], key=_candidate_rank_with_returns(returns))
    assert [it.catalog.fund_code for it in ordered] == ["000002", "000001"]


def test_build_universe_uses_returns_to_select_high_performers_under_cap():
    from irc.discovery.cn_fund_universe import build_cn_fund_universe, UniverseBuildOptions

    rows = [
        {"fund_code": f"00010{i}", "fund_name": f"老基金{i}股票A", "fund_type": "股票型"}
        for i in range(5)
    ] + [
        {"fund_code": "270023", "fund_name": "广发新王者股票A", "fund_type": "股票型"},
    ]
    returns = {"270023": 50.0}  # everyone else has no return data
    options = UniverseBuildOptions(active_broad_cap=3)

    # Without returns: lowest 3 fund codes (000100, 000101, 000102) win.
    without = build_cn_fund_universe(rows, options=options)
    assert [it.instrument_id for it in without] == ["000100", "000101", "000102"]

    # With returns: 270023 jumps to position 1 because it has the only positive return.
    with_returns = build_cn_fund_universe(rows, options=options, returns=returns)
    ids = [it.instrument_id for it in with_returns]
    assert "270023" in ids
    assert len(ids) == 3
