"""Pure promotion-diff tests: newly-promoted funds between two opportunity
report row sets. A promotion is an instrument NEWLY reaching core_dca
(opportunity_state track) or accelerate_dca (dca_action track) relative to the
most recent prior run."""
from __future__ import annotations

from irc.decision.promotions import (
    PromotionDiff,
    diff_promotions,
    promotions_block,
)


def _row(iid: str, state: str = "small_watch", dca: str = "normal_dca",
         name: str = "基金") -> dict:
    return {
        "instrument_id": iid, "name_cn": name,
        "opportunity_state": state, "dca_action": dca,
    }


def test_state_promotion_detected_with_prior_state():
    today = [_row("161903", state="core_dca")]
    prior = [_row("161903", state="small_watch")]
    diff = diff_promotions(today, prior, prior_date="2026-06-16")
    assert diff.prior_date == "2026-06-16"
    assert len(diff.promotions) == 1
    p = diff.promotions[0]
    assert (p.instrument_id, p.kind, p.prior, p.current) == (
        "161903", "state", "small_watch", "core_dca"
    )


def test_unchanged_core_dca_is_not_a_promotion():
    today = [_row("161903", state="core_dca")]
    prior = [_row("161903", state="core_dca")]
    diff = diff_promotions(today, prior, prior_date="2026-06-16")
    assert diff.promotions == ()


def test_debut_core_dca_counts_when_prior_report_exists():
    today = [_row("018132", state="core_dca")]
    diff = diff_promotions(today, [], prior_date="2026-06-16")
    assert len(diff.promotions) == 1
    assert diff.promotions[0].prior is None


def test_no_prior_report_yields_empty_diff():
    """First-ever run must not page every core_dca fund as newly promoted."""
    today = [_row("161903", state="core_dca", dca="accelerate_dca")]
    diff = diff_promotions(today, [], prior_date=None)
    assert diff == PromotionDiff(prior_date=None, promotions=())


def test_dca_promotion_detected_and_both_tracks_reported():
    today = [_row("519069", state="core_dca", dca="accelerate_dca")]
    prior = [_row("519069", state="pause_wait", dca="pause_dca")]
    diff = diff_promotions(today, prior, prior_date="2026-06-16")
    kinds = sorted(p.kind for p in diff.promotions)
    assert kinds == ["dca", "state"]
    # instrument_ids dedups across tracks
    assert diff.instrument_ids == ("519069",)


def test_demotion_is_ignored():
    today = [_row("161903", state="pause_wait", dca="pause_dca")]
    prior = [_row("161903", state="core_dca", dca="accelerate_dca")]
    diff = diff_promotions(today, prior, prior_date="2026-06-16")
    assert diff.promotions == ()


def test_rows_without_instrument_id_are_skipped():
    today = [{"opportunity_state": "core_dca", "dca_action": "normal_dca"}]
    diff = diff_promotions(today, [], prior_date="2026-06-16")
    assert diff.promotions == ()


def test_promotions_block_is_json_shaped():
    today = [_row("161903", state="core_dca", name="万家行业优选")]
    prior = [_row("161903", state="small_watch")]
    diff = diff_promotions(today, prior, prior_date="2026-06-16")
    block = promotions_block(diff)
    assert block["prior_date"] == "2026-06-16"
    assert block["rows"] == [{
        "instrument_id": "161903", "name_cn": "万家行业优选",
        "kind": "state", "prior": "small_watch", "current": "core_dca",
    }]


def test_promotions_section_lines_renders_rows():
    from irc.decision.report import promotions_section_lines
    block = {"prior_date": "2026-06-16", "rows": [
        {"instrument_id": "161903", "name_cn": "万家行业优选", "kind": "state",
         "prior": "small_watch", "current": "core_dca"},
    ]}
    text = "\n".join(promotions_section_lines(block))
    assert "新晋" in text
    assert "161903" in text
    assert "small_watch → core_dca" in text
    assert "2026-06-16" in text


def test_promotions_section_empty_when_no_rows():
    from irc.decision.report import promotions_section_lines
    assert promotions_section_lines({"prior_date": "2026-06-16", "rows": []}) == []
    assert promotions_section_lines(None) == []
