from __future__ import annotations

import json
import textwrap
from pathlib import Path

from irc.commands.monitor_cmd import run_monitor

_YAML = textwrap.dedent("""
schema_version: 1
history: { minimum_observations: 10, fetch_calendar_days: 550 }
defaults: { signal_bands: { buy: 0.40, sell: -0.40 }, minimum_confidence: 0.50 }
funds:
  - { id: "008986", name_cn: 金, market: cn_off_exchange, analysis_profile: gold, themes: [gold_drivers, geopolitics], constituent_news: false }
""")


def _patch_edges(monkeypatch):
    import irc.commands.monitor_cmd as mc
    from irc.monitor.fetch import NavFetchResult
    from irc.monitor.evidence import make_evidence_item
    from irc.monitor.impacts import ImpactsResult
    from irc.monitor.impact_validate import ValidatedImpact
    from irc.monitor.narrative import NarrativeResult
    from irc.monitor.types import NarrativeDoc

    series = tuple((f"d{i}", 1.0 + 0.01 * i) for i in range(60))
    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(mc, "nav_series_for", lambda fid, **k: NavFetchResult(fid, 2.13, "2026-06-15", series))
    ev = make_evidence_item("Reuters", "yields", "2026-06-15", "https://r", "008986")
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: (ev,))
    monkeypatch.setattr(mc, "gather_impacts", lambda **k: ImpactsResult(
        k["fund_id"],
        (ValidatedImpact("gold_drivers", 0.5, 0.9, (ev.citation_id,)),
         ValidatedImpact("geopolitics", 0.4, 0.8, (ev.citation_id,))),
        "ok",
        (),
    ))
    monkeypatch.setattr(mc, "gather_narrative", lambda **k: NarrativeResult(
        NarrativeDoc(k["fund_id"], (), (), (), "ok"), (),
    ))


def test_run_monitor_writes_all_outputs(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")
    _patch_edges(monkeypatch)
    rc = run_monitor(repo_root=str(tmp_path), today="2026-06-15")
    assert rc == 0
    out = tmp_path / "outputs" / "2026-06-15" / "monitor"
    for name in ("report.html", "signal.json", "impacts.json", "narrative.json", "monitor.json"):
        assert (out / name).exists(), name
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "金" in html


def test_preflight_block_returns_code(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")
    _patch_edges(monkeypatch)
    import irc.commands.monitor_cmd as mc
    monkeypatch.setattr(mc, "preflight_gate", lambda *a, **k: 5)
    assert run_monitor(repo_root=str(tmp_path), today="2026-06-15") == 5
