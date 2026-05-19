"""Audit-blocking gate (item 009, 2026-05-19)."""
from __future__ import annotations

import pytest

from irc.memo.auditor import audit_blocks_publish


def test_empty_audit_does_not_block() -> None:
    blocked, reasons = audit_blocks_publish("")
    assert not blocked
    assert reasons == ()


def test_audit_passed_does_not_block() -> None:
    blocked, reasons = audit_blocks_publish(
        "审核通过：未发现合规问题。"
    )
    assert not blocked
    assert reasons == ()


def test_audit_failed_token_blocks() -> None:
    blocked, reasons = audit_blocks_publish(
        "审核未通过：建议修订后再发布。"
    )
    assert blocked
    assert any("审核未通过" in r for r in reasons)


def test_p_tier_table_row_blocks() -> None:
    """The existing audit format uses a P-tier table per the 2026-05-19
    audit:
        | P1 | 🔴 高 | 512960/003624 名称及来源缺失 | 补全或移除 |
    """
    audit = """
| P1 | 🔴 高 | 512960/003624 名称及来源缺失 | 补全或移除 |
| P2 | 🔴 高 | 000190 行动与理由矛盾 | 统一表述 |
| P3 | 🔴 高 | 000176 代理标的自我引用 | 修正为正确代理 |
"""
    blocked, reasons = audit_blocks_publish(audit)
    assert blocked
    p_reason = next((r for r in reasons if "P-tier" in r), None)
    assert p_reason is not None
    assert "P1" in p_reason
    assert "P2" in p_reason
    assert "P3" in p_reason


def test_medium_low_findings_alone_do_not_block() -> None:
    """中风险/低风险 entries don't open with | P\\d in the audit format."""
    audit = """
### 中风险
- 1) 表格中某些数字未给单位
- 2) 部分缩写未首次出现时展开

### 低风险
- 1) 排版偶有空行不一致
"""
    blocked, _ = audit_blocks_publish(audit)
    assert not blocked


def test_mixed_findings_block_when_p_tier_present() -> None:
    audit = """
### 中风险
- 1) 某些数字未给单位

| P1 | 🔴 高 | … | … |
"""
    blocked, reasons = audit_blocks_publish(audit)
    assert blocked
    assert any("P1" in r for r in reasons)


def test_audit_failed_takes_priority_over_passed_token_appearing_later() -> None:
    """If both tokens appear (rare LLM output), 审核未通过 still blocks."""
    audit = "审核未通过 (但部分条目审核通过)"
    blocked, _ = audit_blocks_publish(audit)
    assert blocked
