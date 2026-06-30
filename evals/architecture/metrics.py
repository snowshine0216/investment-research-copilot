from __future__ import annotations
from pathlib import Path
import ast


_REQUIRED_OUTPUTS: tuple[str, ...] = (
    "discovered_watchlist.csv", "scoring.json",
    "gold_regime.json", "gold_band.yaml",
    "proposed_allocation.yaml", "trade_plan.yaml",
    "memo.md",
)


def _imports_in(path: Path) -> set[str]:
    """Find local irc.* imports in a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("irc."):
            out.add(node.module.split(".", 2)[1])  # top-level subpackage
    return out


def unparseable_sources(package_root: Path) -> tuple[str, ...]:
    """Source files (excluding ``__init__.py``, mirroring ``dag_acyclic_check``'s
    scan) that fail to parse. ``dag_acyclic_check`` silently ``continue``s past
    these, so their import edges vanish from the graph — a syntax error can
    therefore hide a real cycle and yield a false PASS. Surfacing them lets the
    runner WARN instead. Returns relative paths, sorted, never raises."""
    if not package_root.exists():
        return ()
    bad: list[str] = []
    for py in sorted(package_root.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        try:
            ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, ValueError):
            bad.append(str(py.relative_to(package_root)))
    return tuple(bad)


def dag_acyclic_check(package_root: Path) -> bool:
    """Build module → set(deps) graph and ensure no cycle."""
    if not package_root.exists():
        return True
    graph: dict[str, set[str]] = {}
    for py in package_root.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        rel = py.relative_to(package_root)
        module = str(rel.with_suffix("")).replace("/", ".")
        try:
            top_level = module.split(".", 1)[0]
            imports = _imports_in(py)
            # Exclude self-imports (imports within the same top-level package)
            external_imports = {imp for imp in imports if imp != top_level}
            graph[top_level] = graph.get(top_level, set()) | external_imports
        except Exception:
            continue
    # Topological sort to detect cycles
    visited: dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=visited

    def visit(node: str) -> bool:
        if visited.get(node) == 1:
            return False  # cycle
        if visited.get(node) == 2:
            return True
        visited[node] = 1
        for dep in graph.get(node, set()):
            if not visit(dep):
                return False
        visited[node] = 2
        return True

    for n in list(graph.keys()):
        if not visit(n):
            return False
    return True


def max_file_loc(root: Path) -> int:
    """Max line count among .py files under root."""
    counts = []
    for py in root.rglob("*.py"):
        counts.append(sum(1 for _ in py.open(encoding="utf-8")))
    return max(counts) if counts else 0


def output_files_present(out_dir: Path) -> dict[str, float]:
    found = sum(1 for n in _REQUIRED_OUTPUTS if (out_dir / n).exists())
    return {"found": float(found), "expected": float(len(_REQUIRED_OUTPUTS)),
            "completeness": found / len(_REQUIRED_OUTPUTS)}
