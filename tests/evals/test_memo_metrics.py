from __future__ import annotations
from evals.memo.metrics import (
    seven_sections_present,
    raw_ref_reachability_in_memo,
    auditor_no_factual_flags,
    length_drift_vs_baseline,
)

_FULL_MEMO = "\n".join([
    "## TL;DR",
    "Summary here.",
    "## 1. 当前组合",
    "Current portfolio.",
    "## 2. 推荐动作",
    "Recommended actions.",
    "## 3. 推导",
    "Derivation.",
    "## 4. 因子分解",
    "Factor breakdown.",
    "## 5. 风险与证伪",
    "Risk and falsification.",
    "## 6. 数据完整性",
    "Data integrity.",
    "## 7. 用户覆盖记录",
    "User coverage log.",
])


def test_seven_sections_present_all():
    assert seven_sections_present(_FULL_MEMO) == 1.0


def test_seven_sections_present_partial():
    partial = "## TL;DR\nSome content.\n## 1. 当前组合\nOther."
    score = seven_sections_present(partial)
    assert abs(score - 2 / 8) < 1e-9


def test_seven_sections_present_empty():
    assert seven_sections_present("") == 0.0


def test_raw_ref_reachability_in_memo_all_found():
    refs = ("Summary", "portfolio", "Derivation")
    rate = raw_ref_reachability_in_memo(_FULL_MEMO, refs)
    assert rate == 1.0


def test_raw_ref_reachability_in_memo_none_found():
    refs = ("MISSING_REF_XYZ", "ANOTHER_MISSING")
    rate = raw_ref_reachability_in_memo(_FULL_MEMO, refs)
    assert rate == 0.0


def test_raw_ref_reachability_in_memo_empty_refs():
    assert raw_ref_reachability_in_memo(_FULL_MEMO, ()) == 1.0


def test_auditor_no_factual_flags_clean():
    audit = {"factual_flags": [], "total_claims": 10}
    assert auditor_no_factual_flags(audit) == 1.0


def test_auditor_no_factual_flags_with_flags():
    audit = {"factual_flags": ["claim X is wrong", "date Y is incorrect"], "total_claims": 10}
    assert abs(auditor_no_factual_flags(audit) - 0.8) < 1e-9


def test_auditor_no_factual_flags_zero_claims():
    audit = {"factual_flags": [], "total_claims": 0}
    assert auditor_no_factual_flags(audit) == 1.0


def test_length_drift_no_drift():
    assert length_drift_vs_baseline("hello", len("hello")) == 1.0


def test_length_drift_longer():
    assert abs(length_drift_vs_baseline("hello world", 5) - 2.2) < 1e-9


def test_length_drift_zero_baseline():
    assert length_drift_vs_baseline("anything", 0) == 1.0
