import json

from irc.rotation.report import to_json, to_md, abstain_report
from irc.rotation.types import BoardState, RotationCandidate, RotationReport


def _report(status="ok"):
    return RotationReport(
        schema_version=1, radar_version=1, data_status=status,
        board_states=(BoardState("BK1", "半导体", "emerging", 2, 0.85, 1.2, 1.5,
                                 0.4, 0.95, True),),
        candidates=(RotationCandidate("F1", "基金一", "BK1", "半导体", 20.0,
                                      True, False, False, "2026Q1"),),
        diagnostics={"coverage_pct": 88.0, "immature_boards": 3})


def test_json_is_byte_stable_and_sorted():
    a, b = to_json(_report()), to_json(_report())
    assert a == b  # deterministic (AC3)
    parsed = json.loads(a)
    assert parsed["schema_version"] == 1 and parsed["radar_version"] == 1
    assert parsed["data_status"] == "ok"


def test_md_has_no_ref_marker():
    md = to_md(_report())
    assert "[ref:" not in md  # AC8 grep test — pure market data, no citations


def test_md_is_additive_subset_of_json():
    rep = _report()
    md = to_md(rep)
    json.loads(to_json(rep))  # confirm json still parses for this report shape
    # every board code / candidate fund in json appears in md (nothing extra suppressed)
    assert "BK1" in md and "半导体" in md and "F1" in md


def test_md_renders_all_json_diagnostics():
    # AC8 guard: md must surface every diagnostics field the json carries on the
    # ok/degraded paths — nothing dropped except formatting. A md that omits the
    # diagnostics section entirely must FAIL this test.
    rep = _report()
    js = json.loads(to_json(rep))
    md = to_md(rep)
    assert js["diagnostics"] == {"coverage_pct": 88.0, "immature_boards": 3}
    assert "coverage_pct" in md and "88" in md  # coverage % surfaced
    assert "immature_boards" in md and "3" in md  # immature-board count surfaced
    assert "[ref:" not in md  # AC8 second clause: no citation marker on diagnostics


def test_md_renders_pe_coverage_and_unmapped_diagnostics():
    # Real production diagnostics shape (item 001-plan §_resolve_candidates):
    # pe_coverage.{with_pe,without_pe} and unmapped_syms must both be visible.
    rep = RotationReport(
        schema_version=1, radar_version=1, data_status="ok",
        board_states=(BoardState("BK1", "半导体", "emerging", 2, 0.85, 1.2, 1.5,
                                 0.4, 0.95, True),),
        candidates=(),
        diagnostics={
            "pe_coverage": {"with_pe": 2, "without_pe": ["BK2"]},
            "unmapped_syms": ["600000", "600001"],
            "immature_boards": ["BK9"],
        })
    md = to_md(rep)
    assert "pe_coverage" in md
    assert "with_pe=2" in md
    assert "BK2" in md  # without_pe board code surfaced, not just a count
    assert "unmapped_syms" in md
    assert "600000" in md and "600001" in md  # unmapped stock symbols surfaced
    assert "immature_boards" in md and "BK9" in md


def test_json_carries_pe_pctl_and_chase_risk():
    js = json.loads(to_json(_report()))
    bs = js["board_states"][0]
    assert bs["pe_pctl"] == 0.95 and bs["chase_risk"] is True


def test_md_renders_pe_pctl_and_chase_flag():
    md = to_md(_report())
    assert "追高" in md  # chase_risk annotation surfaced
    assert "0.95" in md or "95" in md  # pe_pctl rendered on the row


def test_abstain_report_shape():
    rep = abstain_report("snapshot dead after retries")
    js = json.loads(to_json(rep))
    assert js["data_status"] == "abstain"
    assert js["board_states"] == [] and js["candidates"] == []
    assert js["diagnostics"]["failure"] == "snapshot dead after retries"
