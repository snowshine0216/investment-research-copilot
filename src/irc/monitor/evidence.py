from __future__ import annotations
import hashlib
from irc.monitor.types import EvidenceItem
from irc.memo.pipeline import sanitize_refs_for_auditor


def citation_id_for(*, owner_fund_id: str, url: str, date: str, source: str = "") -> str:
    """16-hex sha256 of the MONITOR preimage (independent of ADR 0001).
    preimage = owner_fund_id:url_or_fallback:date (fallback = source:date when url empty)."""
    canonical = url or f"{source}:{date}"
    preimage = f"{owner_fund_id}:{canonical}:{date}".encode("utf-8")
    return hashlib.sha256(preimage).hexdigest()[:16]


def make_evidence_item(
    source: str, title: str, date: str, url: str, owner_fund_id: str,
) -> EvidenceItem:
    cid = citation_id_for(owner_fund_id=owner_fund_id, url=url, date=date, source=source)
    return EvidenceItem(
        source=source, title=title, date=date, url=url,
        owner_fund_id=owner_fund_id, citation_id=cid,
    )


def resolve_in_pool(citation_id: str, pool: tuple[EvidenceItem, ...]) -> EvidenceItem | None:
    """Return the owner-bound EvidenceItem matching this id, else None."""
    for ev in pool:
        if ev.citation_id == citation_id:
            return ev
    return None


def sanitize_untrusted(text: str) -> str:
    """Redact prompt-injection patterns in untrusted titles/snippets (reuses memo)."""
    return sanitize_refs_for_auditor((text,))[0]
