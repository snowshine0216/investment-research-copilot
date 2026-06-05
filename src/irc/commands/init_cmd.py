from __future__ import annotations
from importlib import resources
from pathlib import Path
import sys
from irc.config_loader import TEMPLATE_FILES

# Spend gate configs are committed defaults the user edits; `irc config validate`
# requires them, so a fresh `irc init` must scaffold them too. They are NOT part
# of TEMPLATE_FILES / load_repo_configs (they load via irc.spend.config), so they
# are written alongside but tracked separately.
_SPEND_TEMPLATE_FILES: tuple[str, ...] = (
    "config/spend_pricing.yaml",
    "config/spend_balances.yaml",
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
    for rel in (*TEMPLATE_FILES, *_SPEND_TEMPLATE_FILES):
        dest = root / rel
        if dest.exists() and not force:
            skipped.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_text(_read_template(rel), encoding="utf-8")
        except Exception as exc:
            print(f"error writing {rel}: {exc}", file=sys.stderr)
            return 1
        written.append(rel)
    print(f"wrote {len(written)} files; skipped {len(skipped)} existing.")
    if skipped:
        print(f"  skipped (use --force to overwrite): {', '.join(skipped)}")
    return 0
