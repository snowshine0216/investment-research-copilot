from __future__ import annotations
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import evals.monitor_narrative.runner as runner
from irc.llm._types import ChatResponse


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _clean_narrative_reply(cid):
    """Report v3 macro-block shape: JSON keyed by theme (runner defaults every
    case to 'geopolitics' when messages_seed lacks a theme key, matching the
    corpus's own "theme": "geopolitics" fixtures)."""
    return ChatResponse(
        text=json.dumps({
            "geopolitics": [
                {"claim": "估值偏低，情绪偏谨慎。", "attribution_strength": "consistent_with",
                 "citation_ids": [cid]}],
        }),
        prompt_tokens=20, completion_tokens=10, latency_ms=40,
    )


def _prep(tmp_path: Path, monkeypatch):
    src = Path(__file__).resolve().parents[2] / "src/irc/monitor/eval/cases"
    dst = tmp_path / "src/irc/monitor/eval/cases"
    dst.parent.mkdir(parents=True)
    shutil.copytree(src, dst)
    (tmp_path / "config").mkdir()
    shutil.copy(Path(__file__).resolve().parents[2] / "config/llm.yaml",
                tmp_path / "config/llm.yaml")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://example.com")
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Text-01")


def test_narrative_runner_writes_report_and_records(tmp_path: Path, monkeypatch):
    _prep(tmp_path, monkeypatch)

    def fake_call(task, messages, route, **kw):
        # resolve the first cid from the evidence block in the user message
        block = messages[1]["content"]
        cid = block.split("[", 1)[1].split("]", 1)[0] if "[" in block else "x"
        return _clean_narrative_reply(cid)
    monkeypatch.setattr(runner, "_call", fake_call)

    seen = {}
    monkeypatch.setattr(runner, "record_command_run",
                        lambda **kw: seen.update({"history": list(kw["history"])}))
    rc = runner.run(tmp_path)
    report_path = tmp_path / "outputs" / _today() / "evals" / "monitor_narrative" / "report.json"
    assert report_path.exists()
    names = {m["name"] for m in json.loads(report_path.read_text())["metrics"]}
    assert {"citation_resolution", "entailment_ablation_pass", "attribution_honesty",
            "hallucination_rate", "injection_resistance"} == names
    assert rc in (0, 1, 2)
    assert seen["history"] and all(ce.task == "monitor_narrative" for ce in seen["history"])


def test_narrative_runner_record_crash_does_not_propagate(tmp_path: Path, monkeypatch):
    """Finding 4 [P0]: record_command_run raising must not crash the narrative runner."""
    _prep(tmp_path, monkeypatch)

    def fake_call(task, messages, route, **kw):
        block = messages[1]["content"]
        cid = block.split("[", 1)[1].split("]", 1)[0] if "[" in block else "x"
        return _clean_narrative_reply(cid)
    monkeypatch.setattr(runner, "_call", fake_call)

    def boom(**kw):
        raise RuntimeError("corrupt spend_actuals.json")
    monkeypatch.setattr(runner, "record_command_run", boom)

    rc = runner.run(tmp_path)  # must NOT raise
    report_path = tmp_path / "outputs" / _today() / "evals" / "monitor_narrative" / "report.json"
    assert report_path.exists()
    assert rc in (0, 1, 2)


def test_narrative_runner_degrades_without_crash(tmp_path: Path, monkeypatch):
    _prep(tmp_path, monkeypatch)
    calls = {"n": 0}
    def flaky(task, messages, route, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return _clean_narrative_reply("x")
    monkeypatch.setattr(runner, "_call", flaky)
    monkeypatch.setattr(runner, "record_command_run", lambda **kw: None)
    rc = runner.run(tmp_path)  # must not raise
    assert (tmp_path / "outputs" / _today() / "evals" / "monitor_narrative" / "report.json").exists()
    assert rc in (0, 1, 2)
