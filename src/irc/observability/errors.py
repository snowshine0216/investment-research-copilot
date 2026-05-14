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


_DEFAULT_ID_PREVIEW = 5


@dataclass
class ErrorTally:
    """Collects (item_id, exception) pairs during a loop and renders a tree
    summary at the end. One tally per logical loop (metadata, prices, NAV)."""

    label: str
    _by_category: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def add(self, item_id: str, exc: BaseException) -> None:
        category, _ = classify_exception(exc)
        self._by_category.setdefault(category, []).append((item_id, str(exc)[:120]))

    def total_skipped(self) -> int:
        return sum(len(v) for v in self._by_category.values())

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._by_category.items()}

    def render(self, ok_count: int, console=None, *, verbose: bool = False) -> None:
        """Prints the tree summary. `console` defaults to the shared observability
        Console (imported lazily to avoid a circular import at module load)."""
        if console is None:
            from irc.observability.console import console as _default_console
            console = _default_console

        skipped = self.total_skipped()
        console.print(f"  {self.label}: {ok_count} ok / {skipped} skipped")
        if skipped == 0:
            return

        sorted_cats = sorted(self._by_category.items(), key=lambda kv: -len(kv[1]))
        for i, (category, entries) in enumerate(sorted_cats):
            is_last = i == len(sorted_cats) - 1
            branch = "└─" if is_last else "├─"
            _, description = classify_exception(_synthetic_exception_for(category))
            console.print(
                f"    {branch} {len(entries):>2} {category:<10} {description}"
            )
            if verbose:
                for item_id, _msg in entries:
                    indent = "       " if is_last else "    │  "
                    console.print(f"{indent}  - {item_id}")
            else:
                preview = entries[:_DEFAULT_ID_PREVIEW]
                if preview:
                    indent = "       " if is_last else "    │  "
                    ids = ", ".join(item_id for item_id, _ in preview)
                    suffix = "" if len(entries) <= _DEFAULT_ID_PREVIEW else f" (+{len(entries) - _DEFAULT_ID_PREVIEW} more)"
                    console.print(f"{indent}  e.g. {ids}{suffix}")


def _synthetic_exception_for(category: str) -> BaseException:
    """Produce an exception that classifies as `category`. Used so the renderer
    can look up the human description without storing it twice."""
    synthetic = {
        "ssl": __import__("ssl").SSLError("synthetic"),
        "proxy": type("ProxyError", (Exception,), {})("synthetic"),
        "timeout": TimeoutError("synthetic"),
        "data-key": KeyError("data"),
        "schema": KeyError("'col' not in index"),
        "not-found": type("FundNotFound", (LookupError,), {})("synthetic"),
        "empty": ValueError("empty synthetic"),
    }
    return synthetic.get(category, RuntimeError("synthetic"))
