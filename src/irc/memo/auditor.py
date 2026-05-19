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
_AUDIT_FAILED_TOKEN = "审核未通过"
_AUDIT_PASSED_TOKEN = "审核通过"


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
    if _AUDIT_FAILED_TOKEN in audit_text:
        reasons.append(f"审核报告含 '{_AUDIT_FAILED_TOKEN}' 明确否决")
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
