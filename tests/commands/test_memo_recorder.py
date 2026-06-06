"""memo command, with LLM calls faked, records actuals + folds the profile."""
import json
from pathlib import Path
import yaml
import pytest
from irc.llm._types import ChatResponse
from irc.commands.init_cmd import run_init
from irc.commands.memo_cmd import run_memo


@pytest.fixture
def memo_repo(tmp_path):
    """Minimal repo so run_memo can load configs and the recorder can load pricing."""
    run_init(str(tmp_path), force=False)
    # Overwrite spend_pricing.yaml with seeds at known values for numeric assertions.
    (tmp_path / "config/spend_pricing.yaml").write_text(yaml.safe_dump({
        "margin": 1.2,
        "llm": {"deepseek": {"currency": "CNY", "models": {
            "deepseek-chat": {"input_per_mtok": 1.0, "output_per_mtok": 2.0},
            "deepseek-reasoner": {"input_per_mtok": 3.0, "output_per_mtok": 6.0},
        }}},
        "search": {},
        "seeds": {
            "memo_synthesis": {"calls": 4, "prompt_tokens": 4000, "completion_tokens": 2000},
            "memo_audit": {"calls": 2, "prompt_tokens": 1000, "completion_tokens": 300},
        },
        "search_seeds": {},
    }), encoding="utf-8")
    # Write minimal pipeline output files so run_memo can load them.
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    out = tmp_path / "outputs" / today
    out.mkdir(parents=True, exist_ok=True)
    (out / "scoring.json").write_text(json.dumps({"scores": []}), encoding="utf-8")
    (out / "gold_regime.json").write_text(
        json.dumps({"regime": "bull", "zone": "normal"}), encoding="utf-8"
    )
    (out / "proposed_allocation.yaml").write_text(
        yaml.safe_dump({"gold_tilt": "overweight", "selected_instruments": []}), encoding="utf-8"
    )
    (out / "trade_plan.yaml").write_text(
        yaml.safe_dump({"mode": "hybrid", "trades": []}), encoding="utf-8"
    )
    from irc.data.manifest import ManifestEntry, write_manifest
    from datetime import datetime, timezone
    write_manifest(tmp_path / "data", ManifestEntry(
        source="akshare", last_run_at=datetime.now(timezone.utc).isoformat(),
        schema_version="v1", record_counts={"prices": 100},
    ))
    return tmp_path


def test_memo_run_records_actuals_and_converges(memo_repo, monkeypatch):
    # Fake the two LLM legs so no network; tokens are the "actuals" we expect recorded.
    monkeypatch.setattr("irc.memo.synthesizer.call_chat",
                        lambda **k: ChatResponse(text="memo", prompt_tokens=1000,
                                                 completion_tokens=500, latency_ms=10))
    monkeypatch.setattr("irc.memo.auditor.call_chat",
                        lambda **k: ChatResponse(text="审核通过", prompt_tokens=800,
                                                 completion_tokens=120, latency_ms=5))
    rc = run_memo(str(memo_repo))
    assert rc == 0

    prof = json.loads((memo_repo / "data/spend/usage_profile.json").read_text())
    assert prof["memo_synthesis"]["samples"] == 1
    assert prof["memo_synthesis"]["avg_prompt_tokens"] == 0.3 * 1000.0 + 0.7 * 4000.0

    actuals = json.loads(next((memo_repo / "outputs").rglob("spend_actuals.json")).read_text())
    assert actuals["tasks"]["memo_audit"]["avg_completion_tokens"] == 120.0
