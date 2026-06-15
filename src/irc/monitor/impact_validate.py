from __future__ import annotations
from dataclasses import dataclass
from irc.monitor.evidence import resolve_in_pool
from irc.monitor.types import EvidenceItem


class ImpactValidationError(ValueError):
    """Typed: message starts with one of schema_invalid|unresolved_citation|empty_pool."""


@dataclass(frozen=True)
class ValidatedImpact:
    key: str
    impact: float
    confidence: float
    citation_ids: tuple[str, ...]


def validate_impacts(
    rows: list[dict], pool: tuple[EvidenceItem, ...], *, owner_fund_id: str,
) -> tuple[ValidatedImpact, ...]:
    """Pure: validate LLM impact rows against the per-fund evidence pool. Raises a
    typed ImpactValidationError on the first violation (caller decides retry)."""
    if not pool:
        raise ImpactValidationError("empty_pool: no evidence for fund")
    out: list[ValidatedImpact] = []
    for r in rows:
        impact, conf = r.get("impact"), r.get("confidence")
        if not isinstance(impact, (int, float)) or not (-1.0 <= impact <= 1.0):
            raise ImpactValidationError(f"schema_invalid: impact out of range: {impact!r}")
        if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
            raise ImpactValidationError(f"schema_invalid: confidence out of range: {conf!r}")
        cids = tuple(r.get("citation_ids", ()))
        for cid in cids:
            if resolve_in_pool(cid, pool) is None:
                raise ImpactValidationError(f"unresolved_citation: {cid}")
        out.append(ValidatedImpact(str(r.get("key", "")), float(impact), float(conf), cids))
    return tuple(out)
