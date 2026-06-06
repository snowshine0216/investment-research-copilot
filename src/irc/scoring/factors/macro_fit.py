from __future__ import annotations

import json
import math
from dataclasses import dataclass

from irc.llm._types import ChatResponse
from irc.llm.http_client import call_chat
from irc.scoring.factors.valuation_cost import FactorScore

_SYS = (
    "You are a macro analyst. Score how well the instrument's profile fits the current "
    "macro regime, on a 0-100 scale. Output JSON ONLY: "
    '{"score": <int 0-100>, "rationale": "<one-sentence>"}.'
)


@dataclass(frozen=True)
class MacroFitContext:
    regime_summary: str
    instrument_profile: str
    raw_refs: tuple[str, ...]


def score_macro_fit(
    ctx: MacroFitContext, route: object,
) -> tuple[FactorScore, ChatResponse | None]:
    """LLM-based macro_fit factor. Returns (score, chat_response) for usage tracking.

    chat_response is None when the call was not attempted (no route) or failed;
    in both cases the score falls back to neutral 50.
    """
    user = (
        f"Regime: {ctx.regime_summary}\n"
        f"Instrument: {ctx.instrument_profile}\n"
        f"Cite at least one raw_ref token: {', '.join(ctx.raw_refs)}\n"
    )
    _neutral = FactorScore(score=50.0, raw_refs=ctx.raw_refs, components={"fallback": 1.0})
    if route is None:
        return _neutral, None
    try:
        resp = call_chat(
            route,  # type: ignore[arg-type]
            messages=[
                {"role": "system", "content": _SYS},
                {"role": "user", "content": user},
            ],
            timeout_s=30,
            temperature=0.1,
        )
    except Exception:
        return _neutral, None
    try:
        data = json.loads(resp.text)
        raw = float(data["score"])
        if not math.isfinite(raw):
            return _neutral, resp
        score = max(0.0, min(100.0, raw))
        return FactorScore(score=score, raw_refs=ctx.raw_refs, components={"llm_score": score}), resp
    except (json.JSONDecodeError, KeyError, ValueError):
        return _neutral, resp
