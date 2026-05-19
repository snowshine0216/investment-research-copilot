from __future__ import annotations

from irc.memo.auditor import extract_audit_summary


def test_extract_summary_conditional_pass_with_p1():
    text = """
    | 优先级 | 问题 | 建议操作 |
    |---|---|---|
    | **P1（必改）** | §3/§5 隐含价格回落预测 | 改为条件句 |
    | **P1（必改）** | §6 QDII溢价数据缺失未设强制提示 | 增加禁止执行提示 |

    > **本备忘录审核结果：条件通过**
    """
    summary = extract_audit_summary(text)
    assert summary["verdict"] == "条件通过"
    assert summary["p1_count"] >= 1
    assert any("P1" in finding for finding in summary["p1_findings"])


def test_extract_summary_clean_pass():
    text = "审核通过. 全文无问题."
    summary = extract_audit_summary(text)
    assert summary["verdict"] == "审核通过"
    assert summary["p1_count"] == 0
    assert summary["p1_findings"] == []


def test_extract_summary_blocked_verdict():
    text = "审核未通过. 多处违规."
    summary = extract_audit_summary(text)
    assert summary["verdict"] == "审核未通过"


def test_extract_summary_empty_text():
    summary = extract_audit_summary("")
    assert summary["verdict"] == "未知"
    assert summary["p1_count"] == 0
    assert summary["p1_findings"] == []


def test_extract_summary_detects_numeric_audit_p1():
    # The numeric-audit block uses bullet syntax, not table rows.
    # cheap_claim_vs_state / expensive_claim_vs_state are flagged as
    # P1-grade contradictions per the trust-check doc.
    text = """
    ### 自动数值审核 (numeric audit)
    - [005561] cheap_claim_vs_state: ...
    - [000139] expensive_claim_vs_state: ...

    > **本备忘录审核结果：条件通过**
    """
    summary = extract_audit_summary(text)
    # These numeric-audit contradictions count as P1.
    assert summary["p1_count"] >= 2
    assert any("cheap_claim_vs_state" in f or "expensive_claim_vs_state" in f
               for f in summary["p1_findings"])


def test_extract_summary_findings_capped_at_10():
    findings_block = "\n".join(
        f"| **P1（必改）** | 问题{i} | fix it |" for i in range(20)
    )
    text = f"{findings_block}\n\n> **本备忘录审核结果：条件通过**"
    summary = extract_audit_summary(text)
    assert len(summary["p1_findings"]) <= 10
