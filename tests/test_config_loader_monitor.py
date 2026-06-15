import textwrap
from pathlib import Path
from irc.config_loader import _FILENAME_TO_SCHEMA
from irc.schemas.monitor import MonitorConfig


def test_monitor_yaml_is_registered():
    assert _FILENAME_TO_SCHEMA.get("config/monitor.yaml") is MonitorConfig


from irc.config_loader import load_monitor_config

_YAML = textwrap.dedent("""
schema_version: 1
history: { minimum_observations: 251, fetch_calendar_days: 550 }
defaults:
  signal_bands: { buy: 0.40, sell: -0.40 }
  minimum_confidence: 0.50
funds:
  - { id: "008986", name_cn: 金, market: cn_off_exchange, analysis_profile: gold, themes: [gold_drivers, geopolitics], constituent_news: false }
""")


def test_load_monitor_config_reads_only_monitor_yaml(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")
    cfg = load_monitor_config(tmp_path)
    assert cfg.funds[0].id == "008986"


def test_load_monitor_config_ignores_poisoned_legacy(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "monitor.yaml").write_text(_YAML, encoding="utf-8")
    # Poison legacy files the contract forbids the monitor from reading.
    (tmp_path / "inputs" / "preferences.yaml").write_text("{ not: valid: preferences", encoding="utf-8")
    (tmp_path / "config" / "universe").mkdir()
    (tmp_path / "config" / "universe" / "gold.yaml").write_text(":::garbage", encoding="utf-8")
    cfg = load_monitor_config(tmp_path)   # must NOT raise
    assert cfg.funds[0].id == "008986"
