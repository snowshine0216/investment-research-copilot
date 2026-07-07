"""Guard: doc version strings must match the code constants (review §1.4 item 5).

Kills the schema/engine/radar drift class (D5/D7): a version bump in code that
forgets a doc fails CI here instead of rotting. Pure file reads — no `irc`
imports, so it cannot pull the LLM/network layers.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _const(rel: str, name: str) -> str:
    """Extract `NAME = <int>` (optionally quoted) from a source file, MULTILINE-anchored."""
    m = re.search(rf'^{re.escape(name)}\s*=\s*["\']?(\d+)["\']?', _read(rel), re.MULTILINE)
    assert m, f"{name} assignment not found in {rel}"
    return m.group(1)


SCHEMA = _const("src/irc/monitor/eval/trace.py", "SCHEMA_VERSION")       # "7"
ENGINE = _const("src/irc/commands/monitor_cmd.py", "_ENGINE_VERSION")    # "4"
RADAR = _const("src/irc/rotation/report.py", "RADAR_VERSION")           # "1"
ROT_SCHEMA = _const("src/irc/rotation/report.py", "SCHEMA_VERSION")      # "1"


def test_readme_eval_schema_matches_code():
    text = _read("README.md")
    assert f"schema {SCHEMA}" in text, f"README.md must state 'schema {SCHEMA}'"
    assert "schema 6" not in text, "README.md still carries the stale 'schema 6'"


def test_docs_monitor_readme_engine_matches_code():
    text = _read("docs/monitor/README.md")
    assert f"engine {ENGINE}" in text, f"docs/monitor/README.md must state 'engine {ENGINE}'"
    assert "engine-3" not in text and "engine 3" not in text, "stale engine-3 ref"


def test_monitor_workflow_diagram_matches_code():
    text = _read("docs/diagrams/monitor-workflow.html")
    assert f'engine "{ENGINE}"' in text, f'diagram must state engine "{ENGINE}"'
    assert f'schema "{SCHEMA}"' in text, f'diagram must state eval schema "{SCHEMA}"'
    assert "engine-3" not in text and "engine 3" not in text, "diagram stale engine-3"


def test_monitor_workflow_diagram_batch_industry_field_is_f100():
    """The ulist.np batch flow-capture call's industry field is f100, not f127
    (flow_batch_fetch.py: f127 is numeric there; 行业 rides on f100 — the correct
    f127 belongs only to the per-symbol stock/get fallback, not this batch call)."""
    text = _read("docs/diagrams/monitor-workflow.html")
    assert "f184+f100" in text, "diagram must depict the ulist.np batch call as f184+f100, not f127"
    assert "f100 store merge" in text, "diagram must depict the batch job's industry-map merge as f100, not f127"
    assert "f127" not in text, "diagram must not claim f127 for the batch-industry field"


def test_rotation_report_docstring_matches_constants():
    """Self-consistency: report.py module docstring numbers == the constants."""
    text = _read("src/irc/rotation/report.py")
    assert f"schema_version {ROT_SCHEMA}" in text, "report.py docstring schema_version drift"
    assert f"radar_version {RADAR}" in text, "report.py docstring radar_version drift"
