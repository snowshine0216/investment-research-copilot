from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from irc.llm._types import ResolvedRoute
from irc.llm.cost_tracker import CostEntry, append_cost
from irc.llm.http_client import call_chat
from irc.opportunity.types import OpportunityRow

_log = logging.getLogger(__name__)

__all__ = [
    "DefenseResult",
    "FalsificationResult",
    "ThesisDebate",
    "run_defend",
    "run_falsify",
    "run_debates",
    "pair_debate",
    "compose_thesis_debate_markdown",
]


@dataclass(frozen=True)
class DefenseResult:
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class FalsificationResult:
    conditions: tuple[str, ...]


@dataclass(frozen=True)
class ThesisDebate:
    instrument_id: str
    name_cn: str
    thesis_state: str
    defense: DefenseResult
    falsification: FalsificationResult


_DEFEND_SYS = (
    "Given an investment thesis card (name, derived state, summary, evidence), "
    "steelman the BULL case: list 3-5 arguments for why the long-term logic is "
    'alive. Output JSON: {"arguments": ["...", "..."]}'
)
_FALSIFY_SYS = (
    "Given an investment thesis card (name, derived state, summary, evidence), "
    "steelman the BEAR case: list 3-5 falsification conditions that, if observed, "
    'would invalidate the thesis. Output JSON: {"conditions": ["...", "..."]}'
)

_MAX_ITEMS = 10
_MAX_ITEM_LEN = 300


def _sanitize(s: str) -> str:
    """Strip whitespace, flatten newlines, cap length (mirrors falsification.py)."""
    return str(s).strip().replace("\n", " ").replace("\r", "")[:_MAX_ITEM_LEN]


def _evidence_lines(row: OpportunityRow, n: int = 5) -> str:
    return "; ".join(e.summary for e in row.thesis_evidence[:n])


def _thesis_card(row: OpportunityRow) -> str:
    return (
        f"name: {row.name_cn}\n"
        f"derived_thesis_state: {row.thesis_state}\n"
        f"summary: {row.opportunity_reason}\n"
        f"evidence: {_evidence_lines(row)}"
    )


def run_defend(
    row: OpportunityRow, route: ResolvedRoute,
) -> "tuple[DefenseResult, object | None]":
    """Returns (DefenseResult, ChatResponse | None). None on failure (Shape B)."""
    try:
        resp = call_chat(route, messages=[
            {"role": "system", "content": _DEFEND_SYS},
            {"role": "user", "content": _thesis_card(row)},
        ], timeout_s=30, temperature=0.2)
        raw = json.loads(resp.text).get("arguments", [])
        items = (raw if isinstance(raw, list) else [])[:_MAX_ITEMS]
        return DefenseResult(arguments=tuple(_sanitize(i) for i in items)), resp
    except Exception as exc:
        _log.warning(
            "run_defend failed for %s (%s): %s",
            row.instrument_id, row.name_cn, type(exc).__name__,
        )
        return DefenseResult(arguments=()), None


def run_falsify(
    row: OpportunityRow, route: ResolvedRoute,
) -> "tuple[FalsificationResult, object | None]":
    """Returns (FalsificationResult, ChatResponse | None). None on failure (Shape B)."""
    try:
        resp = call_chat(route, messages=[
            {"role": "system", "content": _FALSIFY_SYS},
            {"role": "user", "content": _thesis_card(row)},
        ], timeout_s=30, temperature=0.2)
        raw = json.loads(resp.text).get("conditions", [])
        items = (raw if isinstance(raw, list) else [])[:_MAX_ITEMS]
        return FalsificationResult(conditions=tuple(_sanitize(i) for i in items)), resp
    except Exception as exc:
        _log.warning(
            "run_falsify failed for %s (%s): %s",
            row.instrument_id, row.name_cn, type(exc).__name__,
        )
        return FalsificationResult(conditions=()), None


def pair_debate(
    row: OpportunityRow, defense: DefenseResult, falsification: FalsificationResult,
) -> ThesisDebate:
    return ThesisDebate(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        thesis_state=row.thesis_state,
        defense=defense,
        falsification=falsification,
    )


def _resp_to_entry(resp: object, route: ResolvedRoute, ts: str) -> CostEntry:
    return CostEntry(
        task=route.task,
        provider=route.provider,
        model=route.model,
        prompt_tokens=getattr(resp, "prompt_tokens", 0),
        completion_tokens=getattr(resp, "completion_tokens", 0),
        latency_ms=getattr(resp, "latency_ms", 0),
        ts=ts,
    )


def _debate_one(
    row: OpportunityRow, defend_route: ResolvedRoute, falsify_route: ResolvedRoute,
    ts: str,
) -> "tuple[ThesisDebate, list[CostEntry]]":
    defense, resp_d = run_defend(row, defend_route)
    falsification, resp_f = run_falsify(row, falsify_route)
    entries: list[CostEntry] = []
    if resp_d is not None:
        entries.append(_resp_to_entry(resp_d, defend_route, ts))
    if resp_f is not None:
        entries.append(_resp_to_entry(resp_f, falsify_route, ts))
    return pair_debate(row, defense, falsification), entries


def run_debates(
    rows: list[OpportunityRow],
    routes: tuple[ResolvedRoute, ResolvedRoute],
) -> "tuple[tuple[ThesisDebate, ...], list[CostEntry]]":
    """Effect orchestrator: one defend + one falsify per row, per-row isolated.

    `routes` = (defend_route, falsify_route).
    Returns (debates, cost_entries) where cost_entries contains one CostEntry per
    successful LLM call, tagged with the correct task name (Shape B).
    """
    defend_route, falsify_route = routes
    out: list[ThesisDebate] = []
    all_entries: list[CostEntry] = []
    ts = datetime.now(timezone(timedelta(hours=8))).isoformat()
    for row in rows:
        try:
            debate, entries = _debate_one(row, defend_route, falsify_route, ts)
            out.append(debate)
            all_entries.extend(entries)
        except Exception:
            out.append(pair_debate(row, DefenseResult(()), FalsificationResult(())))
    debates = tuple(out)
    if rows and all(
        not d.defense.arguments and not d.falsification.conditions for d in debates
    ):
        _log.warning(
            "run_debates: adversarial debate generated no content for any of %d row(s) "
            "— check LLM route credentials and connectivity",
            len(rows),
        )
    return debates, all_entries


_PLACEHOLDER = "（本行未能生成辩论）"


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {i}" for i in items)


def _render_section(d: ThesisDebate) -> str:
    head = f"### {d.instrument_id} {d.name_cn}\n\n推导 thesis_state: {d.thesis_state}\n"
    if not d.defense.arguments and not d.falsification.conditions:
        return f"{head}\n{_PLACEHOLDER}\n"
    bull = f"\n**看多**\n\n{_bullets(d.defense.arguments)}\n" if d.defense.arguments else ""
    bear = f"\n**看空**\n\n{_bullets(d.falsification.conditions)}\n" if d.falsification.conditions else ""
    return f"{head}{bull}{bear}"


def compose_thesis_debate_markdown(debates: tuple[ThesisDebate, ...]) -> str:
    """Pure, deterministic: same ThesisDebate tuple → byte-identical Markdown."""
    header = "# 多空辩论 / Bull-Bear Debate (advisory)\n"
    sections = "\n".join(_render_section(d) for d in debates)
    return f"{header}\n{sections}\n" if debates else f"{header}\n"
