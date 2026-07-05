"""AC11: NOTHING in monitor/discovery/scoring/memo/opportunity imports irc.rotation.
rotation imports FROM monitor, never the reverse (one-way dependency)."""
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "irc"
_FORBIDDEN_IMPORTERS = ("monitor", "discovery", "scoring", "memo", "opportunity")


def test_no_upstream_imports_rotation():
    offenders = []
    for pkg in _FORBIDDEN_IMPORTERS:
        for py in (_SRC / pkg).rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "irc.rotation" in text or "from irc import rotation" in text:
                offenders.append(str(py))
    assert offenders == [], f"rotation imported by upstream packages: {offenders}"
