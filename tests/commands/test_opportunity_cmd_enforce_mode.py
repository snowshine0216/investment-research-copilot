"""Item 009 — _resolve_enforce_mode + _write_citation_audit_shadow_log unit tests."""
from __future__ import annotations

import json
from pathlib import Path


def test_resolve_enforce_mode_canonical_forces_block(monkeypatch, tmp_path):
    """AC11 — canonical path forces 'block' regardless of env var."""
    from irc.commands.opportunity_cmd import _resolve_enforce_mode
    canonical = tmp_path / "outputs" / "2026-05-22"
    canonical.mkdir(parents=True)
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    assert _resolve_enforce_mode(canonical, "2026-05-22") == "block"
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "warn")
    assert _resolve_enforce_mode(canonical, "2026-05-22") == "block"


def test_resolve_enforce_mode_non_canonical_honours_env(monkeypatch, tmp_path):
    """AC11 — non-canonical (tmp_path scratch) honours IRC_CITATION_ENFORCE_MODE."""
    from irc.commands.opportunity_cmd import _resolve_enforce_mode
    scratch = tmp_path / "scratch_outputs"
    scratch.mkdir()
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    assert _resolve_enforce_mode(scratch, "2026-05-22") == "off"
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "warn")
    assert _resolve_enforce_mode(scratch, "2026-05-22") == "warn"
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "block")
    assert _resolve_enforce_mode(scratch, "2026-05-22") == "block"


def test_resolve_enforce_mode_non_canonical_unknown_value_falls_back_to_block(
    monkeypatch, tmp_path, capsys,
):
    """AC11 — unknown value → fallback to 'block' + stderr warning."""
    from irc.commands.opportunity_cmd import _resolve_enforce_mode
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "bogus_value")
    assert _resolve_enforce_mode(scratch, "2026-05-22") == "block"
    err = capsys.readouterr().err
    assert "WARN citation-audit" in err
    assert "bogus_value" in err


def test_resolve_enforce_mode_canonical_path_date_from_dir_name(monkeypatch, tmp_path):
    """AC11 — date is read from out_dir.name, NOT wall-clock today.
    This handles end-of-day skew and cross-day --output-dir invocations."""
    from irc.commands.opportunity_cmd import _resolve_enforce_mode
    # out_dir.name = '2026-05-22' but `today` (wall-clock) = '2026-06-01'.
    canonical = tmp_path / "outputs" / "2026-05-22"
    canonical.mkdir(parents=True)
    monkeypatch.setenv("IRC_CITATION_ENFORCE_MODE", "off")
    assert _resolve_enforce_mode(canonical, "2026-06-01") == "block"


def test_resolve_enforce_mode_default_when_env_unset(monkeypatch, tmp_path):
    """Env unset on non-canonical → default 'block'."""
    from irc.commands.opportunity_cmd import _resolve_enforce_mode
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.delenv("IRC_CITATION_ENFORCE_MODE", raising=False)
    assert _resolve_enforce_mode(scratch, "2026-05-22") == "block"


def test_write_citation_audit_shadow_log_writes_json_atomically(tmp_path):
    """AC13 — file lands at out_dir/citation_audit.json with the locked schema."""
    from irc.commands.opportunity_cmd import _write_citation_audit_shadow_log
    payload = {
        "run_date": "2026-05-22",
        "enforce_mode": "block",
        "canonical_path": True,
        "out_dir": str(tmp_path),
        "opportunity_findings": [],
        "constituent_findings": [],
        "discipline_findings": [],
        "memo_findings": [],
        "summary": {"total": 0, "blocking": False},
    }
    _write_citation_audit_shadow_log(tmp_path, payload)
    written = json.loads((tmp_path / "citation_audit.json").read_text(encoding="utf-8"))
    assert written["run_date"] == "2026-05-22"
    assert written["summary"] == {"total": 0, "blocking": False}
