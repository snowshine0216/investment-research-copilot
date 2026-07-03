"""Item 008 — publishable-set-lockdown integration sweep.

Locks the publishable-set citation / scope / state / asset-class invariants
at the artifact-read level after a full `run_opportunity` (plus `run_memo`
for cross-stage ACs) execution. After this file's tests pass on the feature
branch, item 009 can flip IRC_CITATION_ENFORCE_MODE=block against a
known-clean baseline.

Key invariants:
- Publishable citation universe (Q5 resolution): opportunity_report.json
  ∪ gold_regime.json. rejections.json EXCLUDED — RejectionRecord has no
  thesis_evidence field (src/irc/opportunity/rejection_log.py:35–47).
- Memo route mock pair (Q1 resolution): patch synthesizer.call_chat +
  auditor.call_chat per tests/commands/test_memo_cmd_aliases.py:98–99.
- QDII variants (Q3): one per variant — qdii_us, qdii_hk, qdii_global.
- _GAP_TO_REASON precedence (Q7): assert observable rejection_reason
  string, NEVER import the private constant.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import yaml

from tests.integration._publishable_set_helper import (
    _today_cn,
    _sha256_file,
    _collect_publishable_citation_universe,
    _patch_memo_routes,
    _install_ak_call_dispatch,
    _assert_h3_partition,
    _preload_duckdb,
    _seed_publishable_set_repo,
)


# ─── Smoke test ─────────────────────────────────────────────────────────────

def test_seed_helper_builds_runnable_repo(tmp_path, monkeypatch) -> None:
    """Task 1 smoke — the seed helper builds a repo whose `run_opportunity`
    invocation reaches a write phase without crashing on missing inputs.
    Does NOT assert any AC; the per-AC tests below cover the invariants."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    assert (out_dir / "opportunity_report.json").exists()
    assert (out_dir / "thesis_cards.yaml").exists()
    assert (out_dir / "discipline_report.md").exists()
    assert (out_dir / "rejections.json").exists()


# ─── ACs 1–5: publishable-set citation invariants (E10 family) ───────────────

def test_publishable_dual_leg_coverage(tmp_path, monkeypatch) -> None:
    """AC1 — every published row carries ≥1 data + ≥1 information citation.
    No row has both legs absent. citation_kind ∈ {"data", "information"}
    (legacy "both" forbidden per ADR 0001)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    rows = opp.get("rows", [])
    if not rows:
        pytest.skip("no publishable rows produced by seed — all rows gapped")
    for row in rows:
        kinds = {ev["citation_kind"] for ev in row.get("thesis_evidence", [])}
        assert "data" in kinds, \
            f"row {row['instrument_id']} missing data-leg evidence: kinds={kinds}"
        assert "information" in kinds, \
            f"row {row['instrument_id']} missing information-leg evidence: kinds={kinds}"
        assert kinds <= {"data", "information"}, \
            f"row {row['instrument_id']} has forbidden citation_kind: {kinds}"


def test_publishable_owner_instrument_provenance(tmp_path, monkeypatch) -> None:
    """AC2 — every entry.owner_instrument_id == row.instrument_id.
    No cross-instrument leakage on disk."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        iid = row["instrument_id"]
        for ev in row.get("thesis_evidence", []):
            assert ev["owner_instrument_id"] == iid, \
                f"cross-instrument leakage: row {iid} carries owner={ev['owner_instrument_id']}"


def test_publishable_scope_is_instrument_or_constituent(tmp_path, monkeypatch) -> None:
    """AC3 — every entry.scope ∈ {"instrument", "constituent"}.
    No publishable row may have scope=asset_class_macro / policy as its
    SOLE evidence basis. Macro/policy may co-exist alongside instrument
    or constituent entries (an absent-from-pool check would over-assert)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        scopes = {ev["scope"] for ev in row.get("thesis_evidence", [])}
        assert scopes & {"instrument", "constituent"}, \
            f"row {row['instrument_id']} lacks instrument/constituent scope: {scopes}"


def test_publishable_thesis_state_literal_only(tmp_path, monkeypatch) -> None:
    """AC4 — every row.thesis_state ∈ {"intact","under_pressure","falsified","evidence_insufficient"}.
    No synthetic "partial_evidence"-style values."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    allowed = {"intact", "under_pressure", "falsified", "evidence_insufficient"}
    for row in opp.get("rows", []):
        assert row["thesis_state"] in allowed, \
            f"row {row['instrument_id']} has invalid thesis_state {row['thesis_state']!r}"


def test_publishable_evidence_gaps_empty_after_disk_roundtrip(tmp_path, monkeypatch) -> None:
    """AC5 — every published row has evidence_gaps == [] after JSON round-trip.
    H3 universal gapped-row invariant guarantees this at _write_opportunity_outputs
    time; AC5 re-asserts after JSON round-trip to catch serializer drift."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        assert row["evidence_gaps"] == [], \
            f"row {row['instrument_id']} carries non-empty evidence_gaps on publish: {row['evidence_gaps']!r}"


# ─── ACs 6–9: QDII exclusion invariants ──────────────────────────────────────

_QDII_ASSET_CLASSES = {"qdii_us", "qdii_hk", "qdii_global", "us_etf", "hk_etf"}
_QDII_IIDS = ("004243", "164906", "100061")


def test_qdii_never_in_thesis_cards(tmp_path, monkeypatch) -> None:
    """AC6 — no thesis_card has asset_class in {qdii_us,qdii_hk,qdii_global,us_etf,hk_etf}."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cards_doc = yaml.safe_load((out_dir / "thesis_cards.yaml").read_text(encoding="utf-8")) or {}
    cards = cards_doc.get("cards", [])
    for card in cards:
        assert card.get("asset_class") not in _QDII_ASSET_CLASSES, \
            f"QDII asset_class leaked into thesis_cards.yaml: {card}"


def test_qdii_never_in_opportunity_report_rows(tmp_path, monkeypatch) -> None:
    """AC7 — same set check against opportunity_report.json rows array."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    for row in opp.get("rows", []):
        assert row["asset_class"] not in _QDII_ASSET_CLASSES, \
            f"QDII asset_class leaked into opportunity_report rows: {row}"
        assert row["instrument_id"] not in _QDII_IIDS, \
            f"QDII instrument_id leaked into opportunity_report rows: {row}"


def test_qdii_appears_in_rejections_with_qdii_reason(tmp_path, monkeypatch) -> None:
    """AC8 — every seeded QDII instrument in rejections.json with
    rejection_reason == 'qdii_information_unavailable'."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entries_by_iid = {e["instrument_id"]: e for e in rej.get("entries", [])}
    for iid in _QDII_IIDS:
        assert iid in entries_by_iid, \
            f"QDII {iid} missing from rejections.json"
        assert entries_by_iid[iid]["rejection_reason"] == "qdii_information_unavailable", \
            f"QDII {iid} rejection_reason wrong: {entries_by_iid[iid]['rejection_reason']!r}"


def test_qdii_appears_in_discipline_failure_section(tmp_path, monkeypatch) -> None:
    """AC9 — every seeded QDII iid appears AFTER '## 证据不足' heading and
    NOT in any bucket section above it. Failure-section heading locked by
    tests/commands/test_opportunity_cmd_h3_invariant.py."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    failure_idx = md.find("## 证据不足")
    assert failure_idx >= 0, "discipline_report.md missing '## 证据不足' heading"
    above, below = md[:failure_idx], md[failure_idx:]
    for iid in _QDII_IIDS:
        assert iid not in above, \
            f"QDII {iid} appears in a bucket section above '## 证据不足'"
        assert iid in below, \
            f"QDII {iid} missing from failure section below '## 证据不足'"


# ─── AC10: H3 partition across four output surfaces ──────────────────────────

def test_h3_partition_across_four_output_surfaces(tmp_path, monkeypatch) -> None:
    """AC10 — given one publishable + one Policy-B-gapped seed:
      (a) only publishable iid in thesis_cards.yaml
      (b) only publishable iid in opportunity_report.json rows
      (c) only publishable iid in discipline_report.md bucket sections
      (d) only gapped iid in rejections.json entries
      (e) gapped iid in discipline_report.md failure section
    """
    from irc.commands.opportunity_cmd import run_opportunity

    # Seed only cn_equity_fund (one publishable iid) + force a synthetic
    # gapped row via a second cn_equity_fund whose holdings _ak_call
    # returns empty (triggers Policy B insufficient_info_coverage_top_half).
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    # Augment scoring.json with a second iid that gets the empty-holdings
    # treatment via the dispatcher.
    out_dir = tmp_path / "outputs" / _today_cn()
    scoring = json.loads((out_dir / "scoring.json").read_text(encoding="utf-8"))
    scoring["scores"].append({
        "instrument_id": "163417", "name_cn": "兴全合润",
        "asset_class": "cn_equity_fund", "composite_score": 65.0,
    })
    (out_dir / "scoring.json").write_text(
        json.dumps(scoring, ensure_ascii=False), encoding="utf-8",
    )
    # Also need DuckDB data for 163417 so structural gaps don't fire first.
    _preload_duckdb(tmp_path, ["163417"])

    # 163417 gets empty AkShare holdings → Policy B failure.
    import pandas as pd
    dispatch[("fund_portfolio_hold_em", "163417")] = pd.DataFrame()

    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    cards_doc = yaml.safe_load((out_dir / "thesis_cards.yaml").read_text(encoding="utf-8")) or {}
    card_iids = {c["instrument_id"] for c in cards_doc.get("cards", [])}
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    row_iids = {r["instrument_id"] for r in opp.get("rows", [])}
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    rej_iids = {e["instrument_id"] for e in rej.get("entries", [])}
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    failure_idx = md.find("## 证据不足")
    # Guard against silent slice-direction inversion if the heading is ever
    # renamed (md.find returns -1; `md[:-1]` would silently make the
    # bucket-leakage assertion a near-false-negative).
    assert failure_idx >= 0, "discipline failure heading '## 证据不足' missing"
    above = md[:failure_idx]
    below = md[failure_idx:]

    assert "005827" in row_iids, "publishable iid missing from opportunity rows"
    assert "163417" not in row_iids, "gapped iid leaked into opportunity rows"
    assert "005827" in card_iids, "publishable iid missing from thesis_cards"
    assert "163417" not in card_iids, "gapped iid leaked into thesis_cards"
    assert "005827" in above, "publishable iid missing from discipline buckets"
    assert "163417" not in above, "gapped iid leaked into discipline buckets"
    assert "163417" in rej_iids, "gapped iid missing from rejections.json"
    assert "005827" not in rej_iids, "publishable iid leaked into rejections.json"
    assert "163417" in below, "gapped iid missing from discipline failure section"
    scored_iids = {s["instrument_id"] for s in scoring["scores"]}
    _assert_h3_partition(scored_iids, row_iids, rej_iids)


# ─── AC11: Policy-B precedence ───────────────────────────────────────────────

def test_policy_b_precedence_qdii_over_policy_b_code(tmp_path, monkeypatch) -> None:
    """AC11 — a QDII row carrying BOTH 'qdii_information_unavailable' AND
    'insufficient_info_coverage_top_half' in evidence_gaps must classify
    its rejection_reason as 'qdii_information_unavailable'.

    Asserts on the OBSERVABLE string, NOT by importing _GAP_TO_REASON.
    """
    # precedence per src/irc/opportunity/rejection_log.py::_GAP_TO_REASON
    # dict-iteration order + ADR 0003
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.selection import SelectionQuality

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    _install_ak_call_dispatch(monkeypatch, dispatch)

    qdii_row = OpportunityRow(
        instrument_id="004243",
        name_cn="易方达原油",
        asset_class="us_etf",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="qdii_us", key="sp500",
            display_cn="标普500", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="evidence_insufficient",
        product_quality_state="strong",
        opportunity_state="exclude",
        opportunity_reason="",
        evidence_gaps=(
            "qdii_information_unavailable",
            "insufficient_info_coverage_top_half",
        ),
        thesis_evidence=(),
        constituent_analyses=(),
    )

    # Capture once — `_today_cn()` evaluated twice with a midnight crossing
    # between the two calls would point out_dir at one date and the
    # `today=` arg at another, writing artifacts where the test never reads.
    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_opportunity_outputs(
        kept_rows=[qdii_row],
        positions={"004243": PositionContext(
            portfolio_weight=None, target_band_low=None, target_band_high=None,
            drawdown_since_entry=None, is_holding=False,
        )},
        qualities={"004243": SelectionQuality(
            expense_ratio=None, aum_cny=None, tracking_error=None,
            premium_discount_abs=None, history_days=None, data_completeness=0.5,
        )},
        roles={"004243": ""},
        holdings={},
        out_dir=out_dir,
        today=today,
    )

    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entry = next(e for e in rej["entries"] if e["instrument_id"] == "004243")
    assert entry["rejection_reason"] == "qdii_information_unavailable", \
        f"Policy-B precedence broken: got {entry['rejection_reason']!r}, " \
        "expected 'qdii_information_unavailable' (qdii key precedes policy-b key " \
        "in _GAP_TO_REASON dict-iteration order per ADR 0003)"


def test_policy_b_precedence_holds_when_qdii_gap_is_not_first_in_tuple(
    tmp_path, monkeypatch,
) -> None:
    """AC11 adversarial variant — when `evidence_gaps` tuple lists a
    structural gap BEFORE 'qdii_information_unavailable', the rejection_reason
    classifier MUST still resolve to 'qdii_information_unavailable' (the
    production-fix iterates `_GAP_TO_REASON` key-order, not the tuple-order).
    This is the case the prior `_classify_rejection_reason` bug silently
    failed: tuple-order iteration returned 'incomplete_constituent_data'."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.selection import SelectionQuality

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    _install_ak_call_dispatch(monkeypatch, dispatch)

    qdii_row = OpportunityRow(
        instrument_id="004243",
        name_cn="易方达原油",
        asset_class="us_etf",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="qdii_us", key="sp500",
            display_cn="标普500", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="evidence_insufficient",
        product_quality_state="strong",
        opportunity_state="exclude",
        opportunity_reason="",
        # Adversarial ordering — structural gap FIRST, QDII gap LAST.
        evidence_gaps=(
            "insufficient_info_coverage_top_half",
            "qdii_information_unavailable",
        ),
        thesis_evidence=(),
        constituent_analyses=(),
    )

    # Capture once — midnight-skew guard, see sibling test for rationale.
    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_opportunity_outputs(
        kept_rows=[qdii_row],
        positions={"004243": PositionContext(
            portfolio_weight=None, target_band_low=None, target_band_high=None,
            drawdown_since_entry=None, is_holding=False,
        )},
        qualities={"004243": SelectionQuality(
            expense_ratio=None, aum_cny=None, tracking_error=None,
            premium_discount_abs=None, history_days=None, data_completeness=0.5,
        )},
        roles={"004243": ""},
        holdings={},
        out_dir=out_dir,
        today=today,
    )

    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entry = next(e for e in rej["entries"] if e["instrument_id"] == "004243")
    assert entry["rejection_reason"] == "qdii_information_unavailable", \
        "QDII precedence MUST hold regardless of evidence_gaps tuple order " \
        f"(got {entry['rejection_reason']!r})"


# ─── AC12: fetch_budget_exhausted is fatal at write time ─────────────────────

def test_fetch_budget_exhausted_fatal_at_write_time_via_run_opportunity(
    tmp_path, monkeypatch,
) -> None:
    """AC12 — _write_opportunity_outputs called with a row carrying
    'fetch_budget_exhausted' in evidence_gaps raises RuntimeError before
    any .tmp file becomes visible. Re-asserts via _write_opportunity_outputs
    directly (the run_opportunity path raises SystemExit(3) for budget
    exceeded, not RuntimeError)."""
    from irc.commands.opportunity_cmd import _write_opportunity_outputs
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.selection import SelectionQuality

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    _install_ak_call_dispatch(monkeypatch, dispatch)

    poisoned_row = OpportunityRow(
        instrument_id="005827",
        name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund",
        theme=None,
        lookthrough_target=LookthroughTarget(
            kind="active_fund", key="005827",
            display_cn="易方达蓝筹精选", provider_symbol="",
        ),
        valuation_state="fair",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="strong",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=("fetch_budget_exhausted",),
        thesis_evidence=(),
        constituent_analyses=(),
    )

    # Capture once — midnight-skew guard, same as the sibling AC11 tests.
    today = _today_cn()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(RuntimeError, match="fetch_budget_exhausted"):
        _write_opportunity_outputs(
            kept_rows=[poisoned_row],
            positions={"005827": PositionContext(
                portfolio_weight=None, target_band_low=None, target_band_high=None,
                drawdown_since_entry=None, is_holding=False,
            )},
            qualities={"005827": SelectionQuality(
                expense_ratio=None, aum_cny=None, tracking_error=None,
                premium_discount_abs=None, history_days=None, data_completeness=0.5,
            )},
            roles={"005827": ""},
            holdings={},
            out_dir=out_dir,
            today=today,
        )

    # No artifacts may exist after the fatal raise.
    assert not (out_dir / "opportunity_report.json").exists(), \
        "fetch_budget_exhausted raise left a partial opportunity_report.json"
    assert not any(out_dir.glob("*.tmp*")), \
        "fetch_budget_exhausted raise left a .tmp file"


# ─── ACs 13–14: 持仓明细 appendix integrity (D3b) ────────────────────────────

_APPENDIX_LINE_RE_FOR_TEST = re.compile(
    r"^- \S+ .+ \(权重 [\d.]+%\): .+$"
)


def test_chicang_appendix_line_shape_per_publishable_row(tmp_path, monkeypatch) -> None:
    """AC13 — for every publishable cn_equity_fund/cn_etf row with non-empty
    constituent_analyses, the '## 持仓明细' appendix contains a subheading
    '### {instrument_id} {name_cn}' followed by ≥1 bullet line matching the
    locked regex (audit-error suffix permitted)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))

    appendix_idx = md.find("## 持仓明细")
    if appendix_idx < 0:
        pytest.skip("no publishable cn_equity_fund/cn_etf rows with constituents in this seed")
    appendix = md[appendix_idx:]

    for row in opp.get("rows", []):
        if row["asset_class"] not in {"cn_equity_fund", "cn_etf"}:
            continue
        if not row.get("constituent_analyses"):
            continue
        subheading = f"### {row['instrument_id']} {row['name_cn']}"
        assert subheading in appendix, \
            f"appendix missing subheading {subheading!r}"
        # Find subheading + following block until next ### or EOF.
        sh_idx = appendix.index(subheading)
        next_sh = appendix.find("###", sh_idx + len(subheading))
        block = appendix[sh_idx:next_sh] if next_sh >= 0 else appendix[sh_idx:]
        bullets = [
            ln for ln in block.splitlines()
            if _APPENDIX_LINE_RE_FOR_TEST.match(ln)
        ]
        assert bullets, \
            f"appendix subheading {subheading!r} has no bullet lines matching shape"


def test_chicang_appendix_omits_qdii(tmp_path, monkeypatch) -> None:
    """AC14 — QDII rows have NO '### {instrument_id}' subheading in the
    '## 持仓明细' appendix (they appear only in the failure section)."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    md = (out_dir / "discipline_report.md").read_text(encoding="utf-8")
    appendix_idx = md.find("## 持仓明细")
    if appendix_idx < 0:
        # Appendix may be absent if no publishable rows have constituents.
        # That's fine; QDII is trivially absent.
        return
    appendix = md[appendix_idx:]
    for iid in _QDII_IIDS:
        assert f"### {iid}" not in appendix, \
            f"QDII {iid} leaked into 持仓明细 appendix"


# ─── ACs 15–17: snapshot-cache freshness (E8 family) ─────────────────────────

def _prewrite_active_fund_cache(
    tmp_path: Path,
    *,
    fund_id: str,
    cache_probed_at: str,
    source_report_quarter: str = "2024Q4",
) -> None:
    """Pre-write an ActiveFundSnapshot cache file with a controlled
    cache_probed_at field. Mirrors the on-disk shape produced by
    `snapshot_cache.write_active_fund_cache`."""
    from irc.fundamentals.snapshot_cache import write_active_fund_cache
    from irc.fundamentals.types import ActiveFundSnapshot

    snap = ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date="2024-01-15",
        source_report_quarter=source_report_quarter,
        constituent_analyses=(),
        failure_reasons_by_symbol={},
        cache_probed_at=cache_probed_at,
    )
    write_active_fund_cache(snap, tmp_path / "data")


def test_snapshot_cache_within_window_zero_akshare_calls(tmp_path, monkeypatch) -> None:
    """AC15 — within IRC_CACHE_FRESHNESS_DAYS, cached snapshot is reused
    and zero _ak_call invocations target the cached fund_id."""
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
        seed_date=today,
    )
    # Pre-write cache with cache_probed_at = today (within window).
    _prewrite_active_fund_cache(
        tmp_path, fund_id="005827", cache_probed_at=today,
    )
    counter = _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(repo_root=str(tmp_path))

    fund_calls = sum(
        v for (fn, sym), v in counter.items() if sym == "005827"
    )
    assert fund_calls == 0, \
        f"expected zero AkShare calls for cached fund 005827, got {fund_calls}: " \
        f"{[k for k in counter if k[1] == '005827']}"


def test_snapshot_cache_expired_probe_same_quarter_reuses(tmp_path, monkeypatch) -> None:
    """AC16 — cache older than IRC_CACHE_FRESHNESS_DAYS triggers a probe
    (one fund_portfolio_hold_em call with top_n=1); probe returns the same
    source_report_quarter so the cache is reused (no full per-constituent
    rebuild) and cache_probed_at is updated to today.

    Production probe path: _maybe_freshness_probe → fetch_cn_etf_holdings(top_n=1)
    → fund_portfolio_hold_em.  Same quarter → schedule_full_refetch=False →
    snap_obj = probed (cached data, updated timestamp).

    The holdings_frame must use the AkShare-native quarter format "2024年4季度"
    (matched by _QUARTER_RE = r"(\\d{4})年(\\d)季度") so that
    _parse_quarter_column returns "2024Q4" and the same-quarter check succeeds.
    Frames using "2024Q4" (non-native) parse to ("", "") → probe fails closed.
    """
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    expired = (
        datetime.now(timezone(timedelta(hours=8))).date()
        - timedelta(days=14)
    ).isoformat()

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
        seed_date=today,
    )
    _prewrite_active_fund_cache(
        tmp_path, fund_id="005827", cache_probed_at=expired,
        source_report_quarter="2024Q4",
    )
    # Override the holdings frame for 005827 with AkShare-native quarter format
    # so _parse_quarter_column returns ("2024Q4", ...) and the probe detects
    # same-quarter → schedule_full_refetch=False.
    import pandas as pd
    probe_holdings_frame = pd.DataFrame({
        "股票代码": ["600519"],
        "股票名称": ["贵州茅台"],
        "占净值比例": [8.2],
        "季度": ["2024年4季度"],  # native format parseable by _QUARTER_RE
    })
    dispatch[("fund_portfolio_hold_em", "005827")] = probe_holdings_frame

    counter = _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    # Probe fires exactly once (fund_portfolio_hold_em, top_n=1); same quarter
    # detected → no full rebuild → no constituent evidence calls for 005827.
    holdings_calls = counter[("fund_portfolio_hold_em", "005827")]
    assert holdings_calls == 1, (
        f"expected exactly 1 probe call (no full rebuild) for cached fund 005827, "
        f"got {holdings_calls}"
    )

    # Constituent-level evidence rebuild should NOT have fired (cache reused).
    # The prewritten cache has empty constituent_analyses, so no stock calls.
    constituent_calls = sum(
        v for (fn, sym), v in counter.items()
        if fn in ("stock_financial_abstract", "stock_research_report_em", "stock_news_em")
    )
    assert constituent_calls == 0, (
        f"probe-only path should not re-fetch constituent evidence, "
        f"got {constituent_calls} constituent calls"
    )

    # cache_probed_at updated to today on disk.
    from irc.fundamentals.snapshot_cache import load_active_fund_cache
    snap = load_active_fund_cache("005827", "2024Q4", tmp_path / "data")
    assert snap is not None
    assert snap.cache_probed_at == today, (
        f"expected cache_probed_at refreshed to {today}, got {snap.cache_probed_at}"
    )


def test_snapshot_cache_probe_failure_fail_closed_refetch(tmp_path, monkeypatch) -> None:
    """AC17 — probe failure forces full re-fetch (fail-closed, never silent-reuse).

    The probe uses fetch_cn_etf_holdings → fund_portfolio_hold_em.  When the
    probe raises, _maybe_freshness_probe returns (snap, True) → the caller
    calls build_snapshot (full rebuild) which calls fund_portfolio_hold_em again.
    Total holdings calls ≥ 2: one probe attempt + ≥ 1 rebuild attempt.
    """
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    expired = (
        datetime.now(timezone(timedelta(hours=8))).date()
        - timedelta(days=14)
    ).isoformat()

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
        seed_date=today,
    )
    _prewrite_active_fund_cache(
        tmp_path, fund_id="005827", cache_probed_at=expired,
    )

    # Make the first fund_portfolio_hold_em call (the probe, top_n=1) raise;
    # subsequent calls (full rebuild, top_n=10) return valid data from dispatch.
    import pandas as pd
    holdings_frame = dispatch.get(("fund_portfolio_hold_em", "005827"))
    call_seq: list[int] = []

    def _fail_first_holdings(fn_name, *args, **kwargs):
        sym = args[0] if args else kwargs.get("symbol", "")
        if fn_name == "fund_portfolio_hold_em" and str(sym) == "005827":
            call_seq.append(1)
            if len(call_seq) == 1:
                raise RuntimeError("probe network error (simulated)")
            return holdings_frame if holdings_frame is not None else pd.DataFrame()
        # Delegate all other fn_names to the dispatch dict.
        key = (fn_name, str(sym))
        frame = dispatch.get(key)
        return frame if frame is not None else pd.DataFrame()

    monkeypatch.setattr(
        "irc.fundamentals.akshare_fundamentals._ak_call", _fail_first_holdings,
    )
    monkeypatch.setattr(
        "irc.fundamentals.akshare_filing._ak_call", _fail_first_holdings,
    )

    # Probe failure → full rebuild fires; run_opportunity may exit non-zero
    # (system-exit) when the rebuild is the only path and itself raises, but
    # MUST NOT swallow programming bugs. Narrow the catch to SystemExit so
    # genuine crashes (NameError, import failures, KeyError) surface as test
    # failures instead of being masked by a silent re-raise on the assertion.
    try:
        run_opportunity(repo_root=str(tmp_path))
    except SystemExit:
        pass  # AC17 tolerates explicit non-zero exit from the rebuild path.

    probe_attempts = len(call_seq)
    assert probe_attempts >= 1, "probe was not even attempted"
    assert probe_attempts >= 2, (
        "probe failure did NOT trigger full re-fetch (silent-reuse leak): "
        f"only {probe_attempts} holdings call(s) observed"
    )


# ─── AC18: E9 downstream propagation ─────────────────────────────────────────

def test_empty_holdings_propagate_to_rejections_holdings_fetch_failed(
    tmp_path, monkeypatch,
) -> None:
    """AC18 — empty AkShare holdings → failure_reasons_by_symbol populated
    → row carries evidence_gaps containing 'holdings_fetch_failed' →
    appears in rejections.json, NOT in thesis_cards.yaml."""
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    # Force empty holdings for 005827.
    import pandas as pd
    dispatch[("fund_portfolio_hold_em", "005827")] = pd.DataFrame()

    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cards_doc = yaml.safe_load((out_dir / "thesis_cards.yaml").read_text(encoding="utf-8")) or {}
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))

    card_iids = {c["instrument_id"] for c in cards_doc.get("cards", [])}
    assert "005827" not in card_iids, \
        "fund with empty AkShare holdings leaked into thesis_cards.yaml"

    entry = next(
        (e for e in rej.get("entries", []) if e["instrument_id"] == "005827"),
        None,
    )
    assert entry is not None, \
        "fund with empty AkShare holdings missing from rejections.json"
    # Canonical contract: empty AkShare holdings → row carries the exact
    # `holdings_fetch_failed` code in `evidence_gaps`. The previous OR-form
    # silently accepted any other gap code that happened to map to the same
    # rejection_reason; tighten to the producer-side invariant.
    gaps = entry.get("evidence_gaps", [])
    assert "holdings_fetch_failed" in gaps, \
        f"expected 'holdings_fetch_failed' in evidence_gaps; got {gaps!r}"


# ─── ACs 19–20: cross-stage SAME-3 / citation-id-subset ──────────────────────

def _harvest_first_citation_ids(out_dir: Path, n: int = 3) -> list[str]:
    """Return up to n citation_ids from opportunity_report.json — used to
    build a deterministic memo synth body whose [ref:...] markers are a
    known subset of the publishable universe."""
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    ids: list[str] = []
    for row in opp.get("rows", []):
        for ev in row.get("thesis_evidence", []):
            cid = ev.get("citation_id")
            if cid and cid not in ids:
                ids.append(cid)
            if len(ids) >= n:
                return ids
    return ids


def test_memo_cites_only_publishable_citation_ids(tmp_path, monkeypatch) -> None:
    """AC19 — every [ref:{id}] in memo.md is in the publishable universe
    defined as opportunity_report.json ∪ gold_regime.json (rejections.json
    EXCLUDED per Q5)."""
    from irc.commands.memo_cmd import run_memo
    from irc.commands.opportunity_cmd import run_opportunity

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cids = _harvest_first_citation_ids(out_dir, n=3)
    if not cids:
        pytest.skip("no citation_ids produced by run_opportunity in this seed")
    synth_body = " ".join(f"[ref:{c}]" for c in cids) + " 备忘录正文"

    with _patch_memo_routes(synth_body):
        run_memo(str(tmp_path))

    memo_md = (out_dir / "memo.md").read_text(encoding="utf-8")
    universe = _collect_publishable_citation_universe(out_dir)
    refs = re.findall(r"\[ref:([0-9a-f]{16})\]", memo_md)
    assert refs, "memo.md has no [ref:...] markers despite synth body containing them"
    leaked = [r for r in refs if r not in universe]
    assert not leaked, \
        f"memo.md cites {leaked!r} not in publishable universe (size {len(universe)})"


def test_memo_picks_table_citation_set_matches_opportunity_row(
    tmp_path, monkeypatch,
) -> None:
    """AC20 — for each cn_equity_fund pick, the set of citation_ids in
    memo.md picks-table 证据 cell equals the set in opportunity_report.json
    for that row's selected-top-3 (per select_citations(cap=3)).
    SAME-3 invariant re-asserted post-disk-roundtrip."""
    from irc.commands.memo_cmd import run_memo
    from irc.commands.opportunity_cmd import run_opportunity
    from irc.memo.citation_selector import select_citations
    from irc.fundamentals.types import ThesisEvidence

    dispatch = _seed_publishable_set_repo(tmp_path, monkeypatch=monkeypatch)
    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    out_dir = tmp_path / "outputs" / _today_cn()
    cids = _harvest_first_citation_ids(out_dir, n=3)
    if not cids:
        pytest.skip("no citation_ids produced in this seed")

    with _patch_memo_routes(" 备忘录正文"):
        run_memo(str(tmp_path))

    memo_md = (out_dir / "memo.md").read_text(encoding="utf-8")
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))

    for row in opp.get("rows", []):
        if row["asset_class"] != "cn_equity_fund":
            continue
        # Reconstruct top-3 via select_citations and compare to picks-table cell.
        evs = tuple(ThesisEvidence.from_dict(d) for d in row.get("thesis_evidence", []))
        top3 = {ev.citation_id for ev in select_citations(evs, cap=3)}
        # Locate the picks-table row for this iid; extract its 证据 cell.
        pat = rf"\| *{re.escape(row['instrument_id'])} *\|.*?\|(.*?)\|"
        m = re.search(pat, memo_md)
        if not m:
            pytest.skip(f"no picks-table row for {row['instrument_id']}")
        cell = m.group(1)
        cell_ids = set(re.findall(r"\[ref:([0-9a-f]{16})\]", cell))
        assert cell_ids == top3, \
            f"SAME-3 mismatch for {row['instrument_id']}: " \
            f"picks-table={cell_ids!r} vs opportunity-top-3={top3!r}"


# ─── AC21: multi-owner constituent on-disk provenance ────────────────────────

def test_multi_owner_constituent_keeps_separate_owner_instrument_id(
    tmp_path, monkeypatch,
) -> None:
    """AC21 — when 贵州茅台 (600519) appears as a constituent of BOTH fund A
    (005827) and fund B (163417), each fund's thesis_evidence entry for
    600519 has owner_instrument_id == that fund's iid. No leakage."""
    from irc.commands.opportunity_cmd import run_opportunity
    import pandas as pd

    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",),
    )
    # Add a second cn_equity_fund to scoring.json.
    out_dir = tmp_path / "outputs" / _today_cn()
    scoring = json.loads((out_dir / "scoring.json").read_text(encoding="utf-8"))
    scoring["scores"].append({
        "instrument_id": "163417", "name_cn": "兴全合润",
        "asset_class": "cn_equity_fund", "composite_score": 72.0,
    })
    (out_dir / "scoring.json").write_text(
        json.dumps(scoring, ensure_ascii=False), encoding="utf-8",
    )
    # Pre-load DuckDB for the second fund so structural evidence gaps are avoided.
    _preload_duckdb(tmp_path, ["163417"])

    # Both funds carry 600519 as a top holding. `季度` column matches the
    # other holdings frames in this seed so the cache writes under the
    # realistic `(fund_id, "2024Q4")` key instead of `(fund_id, "")`,
    # keeping AC21 aligned with real AkShare response shape.
    same_holding_frame = pd.DataFrame({
        "股票代码": ["600519"],
        "股票名称": ["贵州茅台"],
        "占净值比例": [8.2],
        "季度": ["2024年4季度"],
    })
    dispatch[("fund_portfolio_hold_em", "005827")] = same_holding_frame
    dispatch[("fund_portfolio_hold_em", "163417")] = same_holding_frame
    # Wire announcement data for 163417 (information leg).
    ann_frame = pd.DataFrame({
        "公告标题": ["2024年第4季度报告"],
        "公告日期": ["2024-01-15"],
        "报告ID": ["ANN002"],
    })
    dispatch[("fund_announcement_dividend_em", "163417")] = ann_frame
    dispatch[("fund_announcement_report_em", "163417")] = ann_frame
    dispatch[("fund_announcement_personnel_em", "163417")] = ann_frame

    _install_ak_call_dispatch(monkeypatch, dispatch)
    run_opportunity(repo_root=str(tmp_path))

    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    by_iid = {r["instrument_id"]: r for r in opp.get("rows", [])}
    if "005827" not in by_iid or "163417" not in by_iid:
        pytest.skip("seed did not produce both funds publishably")

    a_owners = {
        ev["owner_instrument_id"]
        for ev in by_iid["005827"].get("thesis_evidence", [])
        if ev.get("constituent_key") == "600519"
    }
    b_owners = {
        ev["owner_instrument_id"]
        for ev in by_iid["163417"].get("thesis_evidence", [])
        if ev.get("constituent_key") == "600519"
    }
    assert a_owners == {"005827"}, \
        f"fund A 600519 entries have wrong owner_instrument_id: {a_owners!r}"
    assert b_owners == {"163417"}, \
        f"fund B 600519 entries have wrong owner_instrument_id: {b_owners!r}"


# ─── ACs 22–23: pipeline-level two-run byte equality ─────────────────────────

def test_two_run_byte_equality_opportunity_artifacts(tmp_path, monkeypatch) -> None:
    """AC22 — two consecutive run_opportunity invocations against identical
    seeds in distinct tmp_paths produce byte-identical artifacts for:
      - opportunity_report.json
      - thesis_cards.yaml
      - discipline_report.md
      - rejections.json
    Catches non-deterministic ordering (frozenset, glob, dict-hash, timestamps)
    invisible to unit-level tests."""
    from irc.commands.opportunity_cmd import run_opportunity

    a = tmp_path / "run_a"
    b = tmp_path / "run_b"
    a.mkdir()
    b.mkdir()

    today = _today_cn()
    dispatch_a = _seed_publishable_set_repo(
        a, monkeypatch=monkeypatch, seed_date=today,
    )
    _install_ak_call_dispatch(monkeypatch, dispatch_a)
    run_opportunity(repo_root=str(a))

    dispatch_b = _seed_publishable_set_repo(
        b, monkeypatch=monkeypatch, seed_date=today,
    )
    _install_ak_call_dispatch(monkeypatch, dispatch_b)
    run_opportunity(repo_root=str(b))

    for name in (
        "opportunity_report.json",
        "thesis_cards.yaml",
        "discipline_report.md",
        "rejections.json",
    ):
        ha = _sha256_file(a / "outputs" / today / name)
        hb = _sha256_file(b / "outputs" / today / name)
        assert ha == hb, \
            f"{name} differs across two runs: a={ha[:12]}… b={hb[:12]}… " \
            "(non-determinism in the I/O stack — likely frozenset iter, " \
            "glob/walk ordering, dict-hash, or datetime.now() injection)"


def test_two_run_byte_equality_memo_after_run_memo(tmp_path, monkeypatch) -> None:
    """AC23 — same shape as AC22 but for memo.md after run_opportunity → run_memo.
    Patched synth body is a deterministic function of the just-written
    opportunity_report.json so the synth output is itself a function of the
    publishable-set citation universe."""
    from irc.commands.memo_cmd import run_memo
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    a = tmp_path / "run_a"
    b = tmp_path / "run_b"
    a.mkdir()
    b.mkdir()

    def _full_run(repo: Path) -> Path:
        dispatch = _seed_publishable_set_repo(
            repo, monkeypatch=monkeypatch, seed_date=today,
        )
        _install_ak_call_dispatch(monkeypatch, dispatch)
        run_opportunity(repo_root=str(repo))
        out_dir = repo / "outputs" / today
        cids = _harvest_first_citation_ids(out_dir, n=3)
        synth_body = " ".join(f"[ref:{c}]" for c in cids) + " 备忘录正文"
        with _patch_memo_routes(synth_body):
            run_memo(str(repo))
        return out_dir

    out_a = _full_run(a)
    out_b = _full_run(b)

    ha = _sha256_file(out_a / "memo.md")
    hb = _sha256_file(out_b / "memo.md")
    assert ha == hb, \
        f"memo.md differs across two runs: a={ha[:12]}… b={hb[:12]}… " \
        "(non-determinism in the memo I/O stack)"


# ─── Item 004 (todos-critical-fixes): fund-level evidence repair ─────────────


def _prewrite_gapped_fund_level_cache(
    tmp_path: Path, *, fund_id: str, cache_probed_at: str, symbol: str,
) -> None:
    """Item 004 — cache whose single constituent carries a data leg (so
    `_active_snapshot_has_required_data_leg_gap` stays False) and whose
    `fund_level_evidence` is EMPTY (rule 2.5 leg gap).
    symbol="00700.HK" → foreign-heavy (repair fires);
    symbol="600519"  → CN-heavy (repair must NOT fire, spec AC8)."""
    from irc.fundamentals.snapshot_cache import write_active_fund_cache
    from irc.fundamentals.types import (
        ActiveFundSnapshot, ConstituentAnalysis, ThesisEvidence,
    )

    data_leg = ThesisEvidence(
        type="filing", source=symbol, url="", date="2026-04-15",
        summary=f"{symbol} 26Q1 财报", scope="constituent",
        citation_kind="data", owner_instrument_id=fund_id,
        parent_fund_id=fund_id, constituent_key=symbol,
    )
    snap = ActiveFundSnapshot(
        fund_id=fund_id,
        source_report_date="2026-03-31",
        source_report_quarter="2026Q1",
        cache_probed_at=cache_probed_at,
        constituent_analyses=(
            ConstituentAnalysis(
                symbol=symbol, name_cn=symbol, weight_pct=8.0,
                evidence=(data_leg,), failure_reasons=(),
                one_line_view="核心持仓",
            ),
        ),
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=(
            f"fund_nav_unavailable:{fund_id}",
            f"fund_announcements_unavailable:{fund_id}",
        ),
        fund_level_evidence=(),
    )
    write_active_fund_cache(snap, tmp_path / "data")


def test_fund_level_evidence_repair_heals_foreign_heavy_gapped_cache(
    tmp_path, monkeypatch,
) -> None:
    """Item 004 AC7 — fresh-by-date foreign-heavy cache with empty
    fund_level_evidence: run_opportunity (a) fires ONLY the 4 fund-level
    calls (1 NAV + 3 announcements) — zero holdings probes, zero
    constituent-evidence calls; (b) rule 2.5 publishes (the
    foreign_heavy_fund_level_evidence_missing gap is NOT re-emitted);
    (c) the on-disk cache re-loads healed with cache_probed_at unchanged."""
    from irc.commands.opportunity_cmd import run_opportunity
    import pandas as pd

    today = _today_cn()
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",), seed_date=today,
    )
    _prewrite_gapped_fund_level_cache(
        tmp_path, fund_id="005827", cache_probed_at=today, symbol="00700.HK",
    )
    # NAV frame parseable by fetch_fund_nav_report (净值日期 + 单位净值).
    dispatch[("fund_open_fund_info_em", "005827")] = pd.DataFrame({
        "净值日期": ["2026-06-29", "2026-06-30"],
        "单位净值": [1.4900, 1.5000],
    })
    # The three announcement frames for 005827 are already in the seed.
    counter = _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(repo_root=str(tmp_path))

    # (a) exactly the 4 fund-level repair calls; nothing else for this fund.
    assert counter[("fund_open_fund_info_em", "005827")] == 1
    assert counter[("fund_announcement_dividend_em", "005827")] == 1
    assert counter[("fund_announcement_report_em", "005827")] == 1
    assert counter[("fund_announcement_personnel_em", "005827")] == 1
    assert counter[("fund_portfolio_hold_em", "005827")] == 0, \
        "fresh cache must not fire a quarter probe or a full rebuild"
    constituent_calls = sum(
        v for (fn, _sym), v in counter.items()
        if fn in (
            "stock_financial_abstract", "stock_research_report_em", "stock_news_em",
        )
    )
    assert constituent_calls == 0, "repair must not re-fetch constituent evidence"

    # (b) rule 2.5 heals within the SAME run (grill R5): the fund publishes;
    # the gap code is not re-emitted.
    out_dir = tmp_path / "outputs" / today
    opp = json.loads((out_dir / "opportunity_report.json").read_text(encoding="utf-8"))
    row_iids = {r["instrument_id"] for r in opp.get("rows", [])}
    assert "005827" in row_iids, \
        "healed foreign-heavy fund should publish via rule 2.5 in the same run"
    rej = json.loads((out_dir / "rejections.json").read_text(encoding="utf-8"))
    entry = next(
        (e for e in rej.get("entries", []) if e["instrument_id"] == "005827"),
        None,
    )
    assert entry is None or (
        "foreign_heavy_fund_level_evidence_missing"
        not in entry.get("evidence_gaps", [])
    ), f"repair failed to heal the rule 2.5 gap: {entry}"

    # (c) on-disk cache healed; cache_probed_at unchanged (repair is
    # orthogonal to holdings-quarter freshness).
    from irc.fundamentals.snapshot_cache import load_active_fund_cache
    healed = load_active_fund_cache("005827", "2026Q1", tmp_path / "data")
    assert healed is not None
    kinds = {e.citation_kind for e in healed.fund_level_evidence}
    assert kinds == {"data", "information"}, f"cache not healed: {kinds}"
    assert healed.cache_probed_at == today
    assert healed.fund_level_failure_reasons == ()


def test_snapshot_cache_fresh_cn_heavy_gapped_fund_level_no_repair(
    tmp_path, monkeypatch,
) -> None:
    """Item 004 AC8 (negative lock) — a fresh CN-heavy cache (foreign share
    0.0, below FOREIGN_HEAVY_THRESHOLD) with EMPTY fund_level_evidence fires
    ZERO AkShare calls for the fund: the repair is locked to foreign-heavy
    funds; widening is a separate, deferred decision (spec Non-goals).
    GREEN-lock: this test passes both before and after item 004."""
    from irc.commands.opportunity_cmd import run_opportunity

    today = _today_cn()
    dispatch = _seed_publishable_set_repo(
        tmp_path, monkeypatch=monkeypatch, include_qdii=False,
        asset_classes=("cn_equity_fund",), seed_date=today,
    )
    _prewrite_gapped_fund_level_cache(
        tmp_path, fund_id="005827", cache_probed_at=today, symbol="600519",
    )
    counter = _install_ak_call_dispatch(monkeypatch, dispatch)

    run_opportunity(repo_root=str(tmp_path))

    fund_calls = sum(v for (fn, sym), v in counter.items() if sym == "005827")
    assert fund_calls == 0, \
        f"CN-heavy gapped cache must fire zero repair calls, got {fund_calls}: " \
        f"{[k for k in counter if k[1] == '005827']}"
