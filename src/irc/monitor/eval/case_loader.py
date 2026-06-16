"""PURE corpus loader (M1 §3.1). Loads a cases/<suite>/ dir into an
ordered tuple of case dicts. No network, no LLM — the corpus is data,
loaded identically by the pure scorer tests and the live runner."""
from __future__ import annotations
import json
from pathlib import Path


def load_cases(case_dir: Path) -> tuple[dict, ...]:
    """Load every *.json under case_dir, ordered by filename (deterministic)."""
    files = sorted(p for p in case_dir.glob("*.json"))
    return tuple(json.loads(p.read_text(encoding="utf-8")) for p in files)
