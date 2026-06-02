from __future__ import annotations

from irc.commands import narrative_autobuild as NA


def test_autobuild_on_default_true(monkeypatch) -> None:
    monkeypatch.delenv("IRC_NARRATIVE_AUTOBUILD", raising=False)
    assert NA._narrative_autobuild_on() is True


def test_autobuild_off_when_env_zero(monkeypatch) -> None:
    monkeypatch.setenv("IRC_NARRATIVE_AUTOBUILD", "0")
    assert NA._narrative_autobuild_on() is False
