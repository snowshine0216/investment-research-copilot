from __future__ import annotations
import logging
from evals.monitor_suite.driver import (
    build_case_details, build_stage_report, cost_entry_from, drive_case,
)
from irc.llm._types import ChatResponse


def _resp(text):
    return ChatResponse(text=text, prompt_tokens=10, completion_tokens=5, latency_ms=42)


def test_cost_entry_from_maps_fields():
    ce = cost_entry_from("monitor_impact", "minimax", "MiniMax-Text-01", _resp("{}"))
    assert ce.task == "monitor_impact" and ce.provider == "minimax"
    assert ce.model == "MiniMax-Text-01"
    assert ce.prompt_tokens == 10 and ce.completion_tokens == 5 and ce.latency_ms == 42
    assert ce.ts  # ISO timestamp present


def test_drive_case_returns_parsed_output_and_cost():
    def fake_call(task, messages, route, **kw):
        return _resp('{"impacts": [{"impact": 0.8, "citation_ids": []}]}')
    out, cost, ok = drive_case(
        task="monitor_impact", messages=[{"role": "user", "content": "x"}],
        route=object(), call=fake_call, provider="minimax", model="m",
    )
    assert ok is True
    assert out == {"impacts": [{"impact": 0.8, "citation_ids": []}]}
    assert cost is not None and cost.task == "monitor_impact"


def test_drive_case_degrades_on_transport_error():
    def boom(task, messages, route, **kw):
        raise RuntimeError("network down")
    out, cost, ok = drive_case(
        task="monitor_impact", messages=[{"role": "user", "content": "x"}],
        route=object(), call=boom, provider="minimax", model="m",
    )
    assert ok is False
    assert out == {}            # empty output → scorer treats as category failure
    assert cost is None         # no billed call


def test_drive_case_degrades_on_unparseable_json():
    def junk(task, messages, route, **kw):
        return _resp("not json at all")
    out, cost, ok = drive_case(
        task="monitor_impact", messages=[{"role": "user", "content": "x"}],
        route=object(), call=junk, provider="minimax", model="m",
    )
    assert ok is False and out == {}
    assert cost is not None      # the call WAS billed even though parse failed


def test_drive_case_logs_transport_error(caplog):
    """Finding 7 [P1]: transport errors must be logged with exc_info before degrading."""
    def boom(task, messages, route, **kw):
        raise RuntimeError("network down logged")
    with caplog.at_level(logging.WARNING, logger="evals.monitor_suite.driver"):
        out, cost, ok = drive_case(
            task="monitor_impact", messages=[{"role": "user", "content": "x"}],
            route=object(), call=boom, provider="minimax", model="m",
        )
    assert ok is False and out == {}
    assert any("network down logged" in r.getMessage() or "network down logged" in str(r.exc_info)
               for r in caplog.records), "transport error must be logged"


def test_drive_case_logs_parse_error(caplog):
    """Finding 7 [P1]: parse errors must be logged with exc_info before degrading."""
    def junk(task, messages, route, **kw):
        return _resp("totally not json {{{")
    with caplog.at_level(logging.WARNING, logger="evals.monitor_suite.driver"):
        out, cost, ok = drive_case(
            task="monitor_impact", messages=[{"role": "user", "content": "x"}],
            route=object(), call=junk, provider="minimax", model="m",
        )
    assert ok is False and out == {}
    assert any(r.exc_info for r in caplog.records), "parse error must be logged with exc_info"


def test_build_case_details_pairs_cases_with_outputs():
    # Per-case diagnostic rows so a metric FAIL (e.g. magnitude_band_pass) is
    # explainable from the artifact: which case, its expected band, and the raw output.
    cases = [
        {"category": "directional-neutral", "expected": {"max_abs": 0.3},
         "messages_seed": {"fund_id": "x"}, "evidence_pool": []},
        {"category": "directional-strong", "expected": {"min_abs": 0.5, "sign": "+"},
         "messages_seed": {}, "evidence_pool": []},
    ]
    outputs = [
        {"impacts": [{"impact": 0.42, "citation_ids": []}]},   # out of the <=0.3 band
        {"impacts": [{"impact": 0.7, "citation_ids": []}]},
    ]
    details = build_case_details(cases, outputs)
    assert len(details) == 2
    assert details[0]["index"] == 0 and details[0]["category"] == "directional-neutral"
    assert details[0]["expected"] == {"max_abs": 0.3}
    assert details[0]["output"] == {"impacts": [{"impact": 0.42, "citation_ids": []}]}
    assert details[1]["output"]["impacts"][0]["impact"] == 0.7
    # inputs (evidence/messages) are NOT echoed — only what's needed to diagnose
    assert "evidence_pool" not in details[0] and "messages_seed" not in details[0]


def test_build_stage_report_overall_is_worst():
    rpt = build_stage_report(
        stage="monitor_impact",
        named_values=[("sign_accuracy", 0.5, {"warn_below": 0.9, "fail_below": 0.8}, "higher_is_better")],
        n=2, based_on=["cases/impact"],
    )
    assert rpt.stage == "monitor_impact"
    assert rpt.overall == "FAIL"  # 0.5 < fail_below 0.8
    assert rpt.metrics[0].name == "sign_accuracy"
