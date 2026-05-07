from __future__ import annotations
from importlib import resources
from pathlib import Path


_TEMPLATE_FILES: tuple[str, ...] = (
    "inputs/account.yaml",
    "inputs/preferences.yaml",
    "config/llm.yaml",
    "config/scoring.yaml",
    "config/gold_drivers.yaml",
    "config/discovery.yaml",
    "config/valuation_buckets.yaml",
    "config/triggers.yaml",
    "config/overrides.yaml",
    "config/macro_view.yaml",
    "config/universe/qdii_us.yaml",
    "config/universe/qdii_hk.yaml",
    "config/universe/cn_funds.yaml",
    "config/universe/gold.yaml",
)


def _read_template(rel_path: str) -> str:
    """Read a packaged template by its relative path under irc/templates/."""
    parts = rel_path.split("/")
    pkg = "irc.templates" + "".join(f".{p}" for p in parts[:-1])
    leaf = parts[-1]
    return resources.files(pkg).joinpath(leaf).read_text(encoding="utf-8")


def run_init(repo_root: str, force: bool) -> int:
    """Copy packaged templates into the repo root. Returns exit code."""
    root = Path(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    skipped: list[str] = []
    for rel in _TEMPLATE_FILES:
        dest = root / rel
        if dest.exists() and not force:
            skipped.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_read_template(rel), encoding="utf-8")
        written.append(rel)
    print(f"wrote {len(written)} files; skipped {len(skipped)} existing.")
    if skipped:
        print(f"  skipped (use --force to overwrite): {', '.join(skipped)}")
    return 0
