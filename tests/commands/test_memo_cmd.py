from __future__ import annotations
from pathlib import Path
import json
import yaml
import pytest
from unittest.mock import patch
from irc.llm.http_client import ChatResponse
from irc.commands.init_cmd import run_init
from irc.commands.memo_cmd import run_memo


def _resp(text: str) -> ChatResponse:
    return ChatResponse(text=text, prompt_tokens=10, completion_tokens=20, latency_ms=50, raw={})


@pytest.fixture
def repo_with_inputs(tmp_path: Path) -> Path:
    run_init(str(tmp_path), force=False)
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    out = tmp_path / "outputs" / today
    out.mkdir(parents=True)
    (out / "scoring.json").write_text(json.dumps({"scores": []}), encoding="utf-8")
    (out / "gold_regime.json").write_text(json.dumps({"regime": "bull", "zone": "normal"}), encoding="utf-8")
    (out / "proposed_allocation.yaml").write_text(yaml.safe_dump({"gold_tilt": "overweight", "selected_instruments": []}), encoding="utf-8")
    (out / "trade_plan.yaml").write_text(yaml.safe_dump({"mode": "hybrid", "trades": []}), encoding="utf-8")
    return tmp_path


def test_memo_writes_output(repo_with_inputs: Path):
    with patch("irc.memo.synthesizer.call_chat", return_value=_resp("合成备忘录内容")), \
         patch("irc.memo.auditor.call_chat", return_value=_resp("审核通过")):
        rc = run_memo(str(repo_with_inputs))
    assert rc == 0
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    assert (repo_with_inputs / "outputs" / today / "memo.md").exists()
    assert (repo_with_inputs / "outputs" / today / "memo_audit.txt").exists()
