from __future__ import annotations
from irc.memo.traceability import check_traceability


def test_verbatim_quote_counts_as_covered():
    refs = ("[BABA 阿里巴巴] score=75.5",)
    memo = "重点关注 [BABA 阿里巴巴] score=75.5 — 估值便宜。"
    out = check_traceability(memo_text=memo, raw_refs=refs)
    assert out["n_refs_provided"] == 1
    assert out["n_refs_quoted_verbatim"] == 1
    assert out["n_refs"] == 1  # back-compat alias


def test_paraphrased_quote_does_not_count():
    refs = ("[BABA 阿里巴巴] score=75.5",)
    memo = "Alibaba scored about 75 on our composite."
    out = check_traceability(memo_text=memo, raw_refs=refs)
    assert out["n_refs_provided"] == 1
    assert out["n_refs_quoted_verbatim"] == 0
    assert out["n_refs"] == 1


def test_no_refs_returns_zero_provided_zero_quoted():
    out = check_traceability(memo_text="anything", raw_refs=())
    assert out["n_refs_provided"] == 0
    assert out["n_refs_quoted_verbatim"] == 0
    assert out["n_refs"] == 0


def test_partial_coverage_counts_each_ref_independently():
    refs = ("ref-A:exact", "ref-B:exact", "ref-C:exact")
    memo = "Only ref-A:exact and ref-C:exact appear here."
    out = check_traceability(memo_text=memo, raw_refs=refs)
    assert out["n_refs_provided"] == 3
    assert out["n_refs_quoted_verbatim"] == 2


def test_coverage_ratio_key_is_no_longer_present():
    """Regression: the old, misleading coverage_ratio key must be gone."""
    out = check_traceability(memo_text="x", raw_refs=("y",))
    assert "coverage_ratio" not in out
    assert "n_covered" not in out
