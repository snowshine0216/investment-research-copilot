from pathlib import Path
from irc.config_loader import _FILENAME_TO_SCHEMA
from irc.schemas.monitor import MonitorConfig


def test_monitor_yaml_is_registered():
    assert _FILENAME_TO_SCHEMA.get("config/monitor.yaml") is MonitorConfig
