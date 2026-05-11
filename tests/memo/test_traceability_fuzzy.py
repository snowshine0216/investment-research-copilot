from __future__ import annotations
from irc.memo.traceability import check_traceability


def test_paraphrased_citation_still_scores_above_zero():
    refs = ("openbb:prices:VTI:2026-05-07", "akshare:nav:006075:2026-05-06")
    memo = (
        "VTI closed at 245.10 per OpenBB on 2026-05-07. "
        "Fund 006075's NAV (akshare 2026-05-06) was 1.20."
    )
    out = check_traceability(memo_text=memo, raw_refs=refs)
    assert out["coverage_ratio"] >= 0.5


def test_no_refs_returns_full_coverage():
    out = check_traceability(memo_text="anything", raw_refs=())
    assert out["coverage_ratio"] == 1.0


def test_completely_missing_citations_score_zero():
    out = check_traceability(memo_text="nothing here", raw_refs=("openbb:prices:VTI:2026-05-07",))
    assert out["coverage_ratio"] == 0.0
