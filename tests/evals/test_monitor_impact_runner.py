from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import evals.monitor_impact.runner as runner
from irc.llm._types import ChatResponse


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _good_impact_reply(impact: float, cids):
    return ChatResponse(
        text=json.dumps({"impacts": [{"key": "t", "impact": impact, "confidence": 0.9,
                                       "citation_ids": list(cids)}]}),
        prompt_tokens=12, completion_tokens=6, latency_ms=30,
    )


def _stub_perfect_call(case_by_fund):
    """Return a fake `call` that answers each case content-correctly."""
    def fake_call(task, messages, route, **kw):
        # decode which case from the user message fund id is overkill; answer
        # generically: strong→0.8/+ or -0.8/-, neutral/contradiction/injection→0.0
        text = messages[1]["content"]
        if "半导体" in text:
            return _good_impact_reply(0.8, ["aaaa000000000001"])
        if "新能源车" in text:
            return _good_impact_reply(-0.8, ["aaaa000000000002"])
        return _good_impact_reply(0.0, [])
    return fake_call


def test_runner_writes_report_and_records_spend(tmp_path: Path, monkeypatch):
    # symlink/copy the real corpora into tmp repo so the runner finds them
    src = Path(__file__).resolve().parents[2] / "src/irc/monitor/eval/cases"
    dst = tmp_path / "src/irc/monitor/eval/cases"
    dst.parent.mkdir(parents=True)
    import shutil
    shutil.copytree(src, dst)
    (tmp_path / "config").mkdir()
    shutil.copy(Path(__file__).resolve().parents[2] / "config/llm.yaml",
                tmp_path / "config/llm.yaml")

    monkeypatch.setenv("MINIMAX_BASE_URL", "https://example.com")
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Text-01")
    monkeypatch.setattr(runner, "_call", _stub_perfect_call(None))

    recorded = {}
    def fake_record(*, repo_root, history, search_units, today, out_dir=None):
        recorded["calls"] = len(history)
        recorded["tasks"] = {c.task for c in history}
    monkeypatch.setattr(runner, "record_command_run", fake_record)

    rc = runner.run(tmp_path)
    report_path = tmp_path / "outputs" / _today() / "evals" / "monitor_impact" / "report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    names = {m["name"] for m in report["metrics"]}
    assert {"sign_accuracy", "magnitude_band_pass", "injection_resistance",
            "citation_validity"} == names
    assert rc in (0, 1, 2)
    # spend recorded: one CostEntry per case driven
    assert recorded["calls"] >= 1
    assert recorded["tasks"] == {"monitor_impact"}
    # per-case diagnostic details land beside the report (one row per case, raw output)
    details_path = tmp_path / "outputs" / _today() / "evals" / "monitor_impact" / "details.json"
    assert details_path.exists()
    details = json.loads(details_path.read_text(encoding="utf-8"))
    assert len(details) == report["metrics"][0]["n_observations"]  # one row per case
    assert {"index", "category", "expected", "output"} <= set(details[0])


def test_runner_degrades_one_case_without_crash(tmp_path: Path, monkeypatch):
    src = Path(__file__).resolve().parents[2] / "src/irc/monitor/eval/cases"
    dst = tmp_path / "src/irc/monitor/eval/cases"
    dst.parent.mkdir(parents=True)
    import shutil
    shutil.copytree(src, dst)
    (tmp_path / "config").mkdir()
    shutil.copy(Path(__file__).resolve().parents[2] / "config/llm.yaml",
                tmp_path / "config/llm.yaml")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://example.com")
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Text-01")

    calls = {"n": 0}
    def flaky(task, messages, route, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transport boom on first case")
        return _good_impact_reply(0.0, [])
    monkeypatch.setattr(runner, "_call", flaky)
    monkeypatch.setattr(runner, "record_command_run", lambda **kw: None)

    rc = runner.run(tmp_path)  # must NOT raise
    report_path = tmp_path / "outputs" / _today() / "evals" / "monitor_impact" / "report.json"
    assert report_path.exists()  # report still written despite the degraded case
    assert rc in (0, 1, 2)


def test_runner_record_command_run_crash_does_not_propagate(tmp_path: Path, monkeypatch):
    """Finding 4 [P0]: record_command_run raising must not crash the runner.
    The report is written; the exception is logged and swallowed."""
    src = Path(__file__).resolve().parents[2] / "src/irc/monitor/eval/cases"
    dst = tmp_path / "src/irc/monitor/eval/cases"
    dst.parent.mkdir(parents=True)
    import shutil
    shutil.copytree(src, dst)
    (tmp_path / "config").mkdir()
    shutil.copy(Path(__file__).resolve().parents[2] / "config/llm.yaml",
                tmp_path / "config/llm.yaml")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://example.com")
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Text-01")
    monkeypatch.setattr(runner, "_call", _stub_perfect_call(None))

    def boom(**kw):
        raise RuntimeError("corrupt spend_actuals.json")
    monkeypatch.setattr(runner, "record_command_run", boom)

    rc = runner.run(tmp_path)  # must NOT raise
    report_path = tmp_path / "outputs" / _today() / "evals" / "monitor_impact" / "report.json"
    assert report_path.exists()
    assert rc in (0, 1, 2)


def test_runner_details_write_crash_does_not_propagate(tmp_path: Path, monkeypatch):
    """A failure writing the diagnostic details.json must NOT crash an eval whose
    report.json was already written — details is a side-artifact, not the verdict.
    Mirrors the record_command_run degrade-not-crash contract."""
    src = Path(__file__).resolve().parents[2] / "src/irc/monitor/eval/cases"
    dst = tmp_path / "src/irc/monitor/eval/cases"
    dst.parent.mkdir(parents=True)
    import shutil
    shutil.copytree(src, dst)
    (tmp_path / "config").mkdir()
    shutil.copy(Path(__file__).resolve().parents[2] / "config/llm.yaml",
                tmp_path / "config/llm.yaml")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://example.com")
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Text-01")
    monkeypatch.setattr(runner, "_call", _stub_perfect_call(None))
    monkeypatch.setattr(runner, "record_command_run", lambda **kw: None)

    def boom(*a, **kw):
        raise RuntimeError("disk full writing details.json")
    monkeypatch.setattr(runner, "write_details", boom)

    rc = runner.run(tmp_path)  # must NOT raise
    report_path = tmp_path / "outputs" / _today() / "evals" / "monitor_impact" / "report.json"
    assert report_path.exists()  # the verdict survived the details failure
    assert rc in (0, 1, 2)


def test_runner_feeds_costentries_to_record_command_run(tmp_path: Path, monkeypatch):
    src = Path(__file__).resolve().parents[2] / "src/irc/monitor/eval/cases"
    dst = tmp_path / "src/irc/monitor/eval/cases"
    dst.parent.mkdir(parents=True)
    import shutil
    shutil.copytree(src, dst)
    (tmp_path / "config").mkdir()
    shutil.copy(Path(__file__).resolve().parents[2] / "config/llm.yaml",
                tmp_path / "config/llm.yaml")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://example.com")
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Text-01")
    monkeypatch.setattr(runner, "_call", _stub_perfect_call(None))

    seen = {}
    def fake_record(*, repo_root, history, search_units, today, out_dir=None):
        seen["history"] = list(history)
        seen["search_units"] = dict(search_units)
    monkeypatch.setattr(runner, "record_command_run", fake_record)

    runner.run(tmp_path)
    assert seen["history"], "runner must feed CostEntrys to record_command_run"
    assert all(ce.task == "monitor_impact" for ce in seen["history"])
    assert all(ce.prompt_tokens >= 0 and ce.completion_tokens >= 0 for ce in seen["history"])
    assert seen["search_units"] == {}
