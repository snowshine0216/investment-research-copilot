from __future__ import annotations
from pathlib import Path
import json
import sys


def run_freshness(repo_root: str) -> int:
    root = Path(repo_root)
    manifest_dir = root / "data" / "_manifest"
    if not manifest_dir.exists():
        print("no manifest yet — run `irc ingest` once data ingestion ships in Plan 2.")
        return 0
    files = sorted(manifest_dir.glob("*.json"))
    if not files:
        print("no manifest entries — manifest dir is empty.")
        return 0
    print(f"{'source':<16} {'last_run_at':<32} {'schema_version'}")
    for f in files:
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  warning: skipping malformed manifest {f.name}: {exc}", file=sys.stderr)
            continue
        print(f"{m.get('source','?'):<16} {m.get('last_run_at','?'):<32} {m.get('schema_version','?')}")
    return 0
