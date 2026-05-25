from __future__ import annotations

import re

from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse


_SYSTEM = (
    "你是投资合规审核员。检查备忘录是否包含无根据的预测或违规表达，"
    "并给出修改建议。如无问题，回复'审核通过'。"
)


def audit_memo(draft: str, route: ResolvedRoute) -> ChatResponse:
    user_msg = f"请审核以下投资备忘录：\n\n{draft}"
    return call_chat(
        route=route,
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": user_msg}],
        temperature=0.1,
    )


# Adversarial review §H (2026-05-19): the 2026-05-19 audit produced
# 审核未通过 with 3 P-tier 高风险 findings but the memo was committed
# anyway. The audit must be a publish-blocker.
_P_TIER_LINE_RE = re.compile(r"^\|\s*P\d+\b")
_AUDIT_REJECT_TOKENS: tuple[str, ...] = (
    "审核未通过", "不予直接通过", "需修订后重新提交",
)
_AUDIT_PASSED_TOKEN = "审核通过"


_VERDICT_TOKENS: tuple[tuple[str, str], ...] = (
    ("审核未通过", "审核未通过"),
    ("不予直接通过", "审核未通过"),
    ("需修订后重新提交", "审核未通过"),
    ("条件通过", "条件通过"),
    ("审核通过", "审核通过"),
)

# Broader P1 detection than audit_blocks_publish. The current auditor format
# uses several incarnations of P1: pipe-table rows (`| P1 |`), bold-decorated
# rows (`| **P1（必改）** |`), and bullet items from the numeric audit
# (`- [005561] cheap_claim_vs_state: ...`). The trust-check doc (A6)
# specifically calls out the cheap_claim_vs_state / expensive_claim_vs_state
# numeric-audit contradictions as P1-grade.
_P_TIER_TABLE_RE = re.compile(r"\|\s*(?:\*+\s*)?P\d\b")
_NUMERIC_AUDIT_FINDING_RE = re.compile(
    r"^-\s*\[[^\]]+\]\s*(cheap_claim_vs_state|expensive_claim_vs_state|"
    r"weak_claim_vs_state|state_mismatch)"
)


def extract_audit_summary(audit_text: str) -> dict:
    """Return a structured summary of an auditor.py-style memo audit.

    Schema: ``{"verdict": str, "p1_count": int, "p1_findings": list[str]}``.

    - ``verdict`` is one of ``审核通过`` / ``条件通过`` / ``审核未通过`` /
      ``未知`` (no marker found). If multiple verdict tokens appear, the
      strictest one wins (``审核未通过`` > ``条件通过`` > ``审核通过``).
    - ``p1_count`` is the total number of P1-grade findings detected
      across both the priority table and the numeric-audit bullets.
    - ``p1_findings`` lists up to the first 10 trimmed finding lines.
    """
    if not audit_text:
        return {"verdict": "未知", "p1_count": 0, "p1_findings": []}
    verdict = "未知"
    for token, label in _VERDICT_TOKENS:
        if token in audit_text:
            verdict = label
            break
    findings: list[str] = []
    for raw in audit_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _P_TIER_TABLE_RE.search(line) or _NUMERIC_AUDIT_FINDING_RE.match(line):
            findings.append(line)
    return {
        "verdict": verdict,
        "p1_count": len(findings),
        "p1_findings": findings[:10],
    }


def audit_blocks_publish(audit_text: str) -> tuple[bool, tuple[str, ...]]:
    """Classify audit content. Pure function.

    Returns (is_blocked, reasons).
    Block when:
      - The audit explicitly says ``审核未通过``.
      - One or more table rows opens with ``| P1 ``, ``| P2 ``, ... (the
        existing audit format uses ``| P<N> | 🔴 高 | … |`` for high-risk
        findings).
    Does NOT block when only 中风险/低风险 findings are present or the
    audit explicitly says ``审核通过``.
    """
    if not audit_text:
        return False, ()
    reasons: list[str] = []
    for reject_token in _AUDIT_REJECT_TOKENS:
        if reject_token in audit_text:
            reasons.append(f"审核报告含 '{reject_token}' 明确否决")
            break
    p_tier_lines = [
        line.strip()
        for line in audit_text.splitlines()
        if _P_TIER_LINE_RE.match(line.strip())
    ]
    if p_tier_lines:
        reasons.append(
            "存在 P-tier 高风险项：" + " / ".join(p_tier_lines[:3])
        )
    return (bool(reasons), tuple(reasons))
