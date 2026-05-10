from __future__ import annotations
from dataclasses import dataclass
import json
from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat


@dataclass(frozen=True)
class FalsificationResult:
    conditions: tuple[str, ...]


_SYS = (
    "Given an investment thesis summary, list 3-5 falsification conditions: events that, "
    "if observed, would invalidate the thesis. Output JSON: "
    '{"conditions": ["...", "..."]}'
)


def generate_falsification(thesis_summary: str, route: ResolvedRoute) -> FalsificationResult:
    try:
        resp = call_chat(route, messages=[
            {"role": "system", "content": _SYS},
            {"role": "user", "content": thesis_summary},
        ], timeout_s=30, temperature=0.2)
        data = json.loads(resp.text)
        conds = data.get("conditions", [])
        return FalsificationResult(conditions=tuple(str(c) for c in conds))
    except (json.JSONDecodeError, KeyError, ValueError, Exception):
        return FalsificationResult(conditions=())
