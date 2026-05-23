"""Item 007 — memo_cmd wires build_alias_maps over publishable rows."""
from __future__ import annotations

import json
import yaml
import pytest

from pathlib import Path
from unittest.mock import patch

from irc.llm.http_client import ChatResponse


def _resp(text: str) -> ChatResponse:
    return ChatResponse(text=text, prompt_tokens=10, completion_tokens=20, latency_ms=50, raw={})


def test_run_memo_builds_alias_maps_over_publishable_rows(monkeypatch, tmp_path) -> None:
    """run_memo invokes build_alias_maps on the publishable subset of opportunity rows."""
    from irc.commands.init_cmd import run_init
    from irc.data.manifest import ManifestEntry, write_manifest
    from datetime import datetime, timezone, timedelta
    import irc.commands.memo_cmd as mc
    from irc.memo import aliases as alias_mod

    # Set up a full repo structure.
    run_init(str(tmp_path), force=False)
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=datetime.now(timezone.utc).isoformat(),
        schema_version="v1", record_counts={"prices": 100},
    ))
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    scoring = {"scores": [
        {"instrument_id": "005827", "composite_score": 70.0,
         "asset_class": "cn_equity_fund"},
    ]}
    (out_dir / "scoring.json").write_text(json.dumps(scoring), encoding="utf-8")
    (out_dir / "gold_regime.json").write_text(
        json.dumps({"regime": "bull", "zone": "normal"}), encoding="utf-8",
    )
    (out_dir / "proposed_allocation.yaml").write_text(
        yaml.safe_dump({"gold_tilt": "overweight", "selected_instruments": []}),
        encoding="utf-8",
    )
    opportunity = {
        "date": today,
        "summary": {"core_dca_count": 1, "small_watch_count": 0,
                    "pause_wait_count": 0, "exclude_count": 0},
        "rows": [
            {
                "instrument_id": "005827",
                "name_cn": "易方达蓝筹精选",
                "asset_class": "cn_equity_fund",
                "theme": None,
                "lookthrough_target": "易方达蓝筹精选",
                "lookthrough_kind": "active_fund",
                "lookthrough_key": "005827",
                "valuation_state": "fair",
                "heat_state": "normal",
                "thesis_state": "intact",
                "product_quality_state": "strong",
                "opportunity_state": "core_dca",
                "opportunity_reason": "",
                "evidence_gaps": [],
                "thesis_evidence": [],
                "contributing_dimensions": [],
                "constituent_analyses": [],
                "fetch_types_attempted": [],
                "expected_omissions": [],
            },
        ],
    }
    (out_dir / "opportunity_report.json").write_text(
        json.dumps(opportunity, ensure_ascii=False), encoding="utf-8",
    )
    (out_dir / "trade_plan.yaml").write_text(
        yaml.safe_dump({"mode": "build", "trades": [
            {"target": "005827", "target_weight": 0.1, "role": "",
             "buy_method": "limit", "granularity": "default",
             "triggers": [], "venue_note": ""},
        ]}),
        encoding="utf-8",
    )

    captured: list[tuple] = []
    real_build = alias_mod.build_alias_maps

    def spy_build_alias_maps(rows):
        captured.append(tuple(rows))
        return real_build(rows)

    monkeypatch.setattr(alias_mod, "build_alias_maps", spy_build_alias_maps)
    # Also patch at the memo_cmd import-site.
    if hasattr(mc, "build_alias_maps"):
        monkeypatch.setattr(mc, "build_alias_maps", spy_build_alias_maps)

    with patch("irc.memo.synthesizer.call_chat", return_value=_resp("合成备忘录内容")), \
         patch("irc.memo.auditor.call_chat", return_value=_resp("审核通过")):
        rc = mc.run_memo(str(tmp_path))

    # If build_alias_maps was wired, captured should be non-empty.
    assert captured, \
        "build_alias_maps was not invoked by run_memo — wiring missing"
