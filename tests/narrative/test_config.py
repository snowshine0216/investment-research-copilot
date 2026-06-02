from __future__ import annotations

from pathlib import Path

import pytest

from irc.narrative.config import available_narratives, load_narrative_basket
from irc.narrative.schemas import NarrativeBasket

REPO = Path(__file__).resolve().parents[2]


def test_load_compute_metals_parses() -> None:
    b = load_narrative_basket("compute_metals", REPO)
    assert isinstance(b, NarrativeBasket)
    assert b.narrative_id == "compute_metals"
    assert b.display_name_cn == "算力金属"
    assert any(s.symbol == "601899" for s in b.basket)
    assert b.min_basket_weight_pct == 15.0
    assert b.min_overlap_count == 2
    assert b.top_n == 15
    assert "有色金属/工业金属" in b.industries_sw


def test_missing_narrative_lists_available(tmp_path: Path) -> None:
    (tmp_path / "config" / "narratives").mkdir(parents=True)
    (tmp_path / "config" / "narratives" / "ai.yaml").write_text("x", encoding="utf-8")
    with pytest.raises(FileNotFoundError) as exc:
        load_narrative_basket("nope", tmp_path)
    assert "ai" in str(exc.value)


def test_malformed_config_rejected(tmp_path: Path) -> None:
    d = tmp_path / "config" / "narratives"
    d.mkdir(parents=True)
    (d / "bad.yaml").write_text("narrative_id: bad\nbasket: not-a-list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_narrative_basket("bad", tmp_path)


def test_available_narratives_includes_compute_metals() -> None:
    assert "compute_metals" in available_narratives(REPO)
