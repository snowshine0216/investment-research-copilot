from __future__ import annotations

import logging
from dataclasses import dataclass

from irc.llm.http_client import call_chat
from irc.discovery.universe import UniverseRow

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WriteReasonContext:
    role: str
    peer_summary: str
    macro_snapshot: str
    raw_refs: tuple[str, ...]


@dataclass(frozen=True)
class ReasonResult:
    instrument_id: str
    reason_text: str
    cited_refs: tuple[str, ...]
    prompt_tokens: int
    completion_tokens: int


def _sanitize(text: str, max_len: int = 200) -> str:
    """Strip control characters and truncate external-sourced strings before LLM use."""
    cleaned = "".join(ch for ch in str(text) if ch.isprintable() or ch in (" ", "\t"))
    return cleaned[:max_len]


def _system_prompt() -> str:
    return (
        "You are an investment-research assistant. For the given instrument and role, "
        "write at most 3 sentences explaining why it is a candidate for that role, "
        "then 1 short 'Risk: ...' sentence. You MUST cite at least one of the provided "
        "raw_ref tokens by including its exact id in your reasoning. Output plain text."
    )


def _user_prompt(row: UniverseRow, ctx: WriteReasonContext) -> str:
    return (
        f"Instrument: {row.instrument_id} {_sanitize(row.name_cn)} ({row.ticker}) — {row.asset_class}\n"
        f"Tracked index: {_sanitize(str(row.tracked_index))}\n"
        f"Role: {ctx.role}\n"
        f"Peers: {ctx.peer_summary}\n"
        f"Macro snapshot: {ctx.macro_snapshot}\n"
        f"Available raw_refs: {', '.join(ctx.raw_refs)}"
    )


def write_reason(
    row: UniverseRow | None = None,
    ctx: WriteReasonContext | None = None,
    route: object = None,
    max_retries: int = 1,
    *,
    role: str | None = None,
    instrument_id: str | None = None,
) -> ReasonResult | str | None:
    """Step 5: produce a 3-sentence reason + 1 risk line, citing >= 1 raw_ref.
    Returns None if grounding fails after all attempts.

    Simplified mode (role + instrument_id kwargs): makes a bare call_chat request
    and returns '' on failure with a structured warning log.
    """
    # Simplified calling convention: write_reason(role=..., instrument_id=..., route=...)
    if role is not None and instrument_id is not None and row is None:
        try:
            resp = call_chat(
                route,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": f"{role}: {instrument_id}"}],
                timeout_s=30,
            )
            return resp.text.strip()
        except Exception as e:
            _log.warning(
                "write_reason failed for %s/%s: %s", role, instrument_id, e,
                extra={"role": role, "instrument_id": instrument_id},
            )
            return ""
    last_exc: Exception | None = None
    ungrounded_attempts = 0
    assert row is not None and ctx is not None, "row and ctx required in standard mode"
    if not ctx.raw_refs:
        _log.warning(
            "skipping reason for %s (role=%s): no raw_refs available — "
            "ingest produced no prices/NAV for this instrument, so the LLM "
            "has nothing to cite. Check upstream data coverage.",
            row.instrument_id, ctx.role,
        )
        return None
    for _attempt in range(max_retries + 1):
        try:
            resp = call_chat(
                route,  # type: ignore[arg-type]
                messages=[
                    {"role": "system", "content": _system_prompt()},
                    {"role": "user", "content": _user_prompt(row, ctx)},
                ],
                timeout_s=30,
            )
            cited = tuple(r for r in ctx.raw_refs if r in resp.text)
            if not cited:
                ungrounded_attempts += 1
                continue
            return ReasonResult(
                instrument_id=row.instrument_id,
                reason_text=resp.text.strip(),
                cited_refs=cited,
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _log.warning("attempt %d failed for %s: %s", _attempt, row.instrument_id, exc)
    if last_exc is not None:
        _log.warning(
            "skipping reason for %s (role=%s): LLM call failed after %d attempts — %s. "
            "Check llm.yaml provider credentials / network.",
            row.instrument_id, ctx.role, max_retries + 1, last_exc,
        )
    elif ungrounded_attempts > 0:
        _log.warning(
            "skipping reason for %s (role=%s): LLM produced %d response(s) but none "
            "cited any of the %d raw_refs. Likely the model ignored the citation "
            "instruction; consider stricter system prompt or larger ref pool.",
            row.instrument_id, ctx.role, ungrounded_attempts, len(ctx.raw_refs),
        )
    return None
