from __future__ import annotations

import textwrap

from irc.commands.monitor_cmd import run_monitor_snapshot

_YAML = textwrap.dedent("""
schema_version: 1
defaults: { signal_bands: { buy: 0.40, sell: -0.40 } }
funds:
  - { id: "008986", name_cn: 金, market: cn_off_exchange, analysis_profile: gold, themes: [gold_drivers, geopolitics], constituent_news: false }
  - { id: "519069", name_cn: 价值, market: cn_off_exchange, analysis_profile: active_cn_equity, themes: [cn_monetary, geopolitics], constituent_news: true }
""")


def test_snapshot_builds_typed_targets(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")
    built = []

    def fake_build_snapshot(target, **kw):
        built.append(target)

        class _S:  # minimal snapshot stub
            failure_reasons = ()

        return _S()

    monkeypatch.setattr("irc.commands.monitor_cmd.build_snapshot", fake_build_snapshot)
    monkeypatch.setattr("irc.commands.monitor_cmd.write_snapshot", lambda s, d: d / "x.json")

    rc = run_monitor_snapshot(repo_root=str(tmp_path))
    assert rc == 0
    kinds = {t.kind for t in built}
    assert "active_fund" in kinds and "gold" in kinds
    assert all(t.provider_symbol for t in built)  # never broad_index w/o symbol
    assert "broad_index" not in kinds
