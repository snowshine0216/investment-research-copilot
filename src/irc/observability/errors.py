"""Error classification and tallying for the ingest pipeline.

`classify_exception` is pure: same exception → same category, no I/O.
`ErrorTally` collects exceptions during a loop and renders a tree summary.
"""
from __future__ import annotations

import ssl
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class _Rule:
    category: str
    matches: Callable[[BaseException], bool]
    description: str


# Order matters: first match wins. data-key is checked before generic KeyError
# fallthrough; schema is checked after data-key so it doesn't shadow.
_RULES: tuple[_Rule, ...] = (
    _Rule(
        "ssl",
        lambda e: isinstance(e, ssl.SSLError) or "SSL" in type(e).__name__ or "SSL" in repr(e),
        "SSL handshake failure (transient — rerun usually fixes)",
    ),
    _Rule(
        "proxy",
        lambda e: "ProxyError" in type(e).__name__ or "ProxyError" in repr(e),
        "Proxy unreachable (check HTTP_PROXY env)",
    ),
    _Rule(
        "timeout",
        lambda e: isinstance(e, TimeoutError) or "Timeout" in type(e).__name__,
        "Upstream timeout (transient)",
    ),
    _Rule(
        "data-key",
        lambda e: isinstance(e, KeyError) and str(e).strip("'\"") == "data",
        "Fund not in XueQiu catalog (expected for new/obscure funds)",
    ),
    _Rule(
        "schema",
        lambda e: isinstance(e, KeyError) and "not in index" in str(e),
        "Upstream response missing expected column",
    ),
    _Rule(
        "not-found",
        lambda e: type(e).__name__ == "FundNotFound",
        "Fund code not in akshare catalog",
    ),
    _Rule(
        "empty",
        lambda e: isinstance(e, ValueError) and "empty" in str(e).lower(),
        "Upstream returned no rows",
    ),
)


def classify_exception(exc: BaseException) -> tuple[str, str]:
    """Returns (category, human_description). Always succeeds (never raises).

    First-match wins. Unrecognized exceptions return ("other", repr(exc)[:120]).
    """
    for rule in _RULES:
        if rule.matches(exc):
            return rule.category, rule.description
    return "other", repr(exc)[:120]
