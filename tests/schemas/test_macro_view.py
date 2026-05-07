from __future__ import annotations
from irc.schemas.macro_view import MacroViewConfig


def test_macro_view_minimal():
    raw = {"views": [], "active": False}
    cfg = MacroViewConfig.model_validate(raw)
    assert cfg.active is False


def test_macro_view_with_views():
    raw = {
        "views": [{"text": "Fed will cut by July", "biased_factor": "macro_fit", "bias": 0.10}],
        "active": True,
    }
    cfg = MacroViewConfig.model_validate(raw)
    assert cfg.views[0].bias == 0.10
