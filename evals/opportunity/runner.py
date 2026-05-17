from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from evals._shared.missing_input import (
    EVAL_RC_FAIL,
    EVAL_RC_PASS,
    EVAL_RC_WARN,
    missing_input_report,
    write_missing_input_report,
)
from evals._shared.report_schema import MetricReport, StageReport, report_to_dict
from evals._shared.status import classify_status, worst_status
from evals.opportunity.metrics import (
    drawdown_not_auto_sell,
    hot_chase_prevention,
    no_external_worktree_path,
    opportunity_evidence_gap_visibility,
    same_theme_distinct_index_limit,
    thesis_card_required_field_completeness,
    valid_action_enums,
)
from irc.io_utils import atomic_write_text


_TZ = timezone(timedelta(hours=8))
_HIGH_TH = {"warn_below": 0.95, "fail_below": 0.80}
_BINARY_TH = {"warn_below": 1.0, "fail_below": 1.0}


def _today() -> str:
    return datetime.now(_TZ).date().isoformat()


def _locate_inputs(root: Path) -> tuple[Path | None, Path | None, Path | None, str]:
    today = _today()
    today_dir = root / "outputs" / today
    target_dir = today_dir if today_dir.exists() else None
    if target_dir is None:
        dated = sorted((root / "outputs").glob("*/opportunity_report.json"))
        if not dated:
            return None, None, None, today
        target_dir = dated[-1].parent
    report = target_dir / "opportunity_report.json"
    cards = target_dir / "thesis_cards.yaml"
    md = target_dir / "discipline_report.md"
    return (
        report if report.exists() else None,
        cards if cards.exists() else None,
        md if md.exists() else None,
        target_dir.name,
    )


def _read_opportunity_cmd_source() -> str:
    from irc.commands import opportunity_cmd as opp_mod
    return Path(opp_mod.__file__).read_text(encoding="utf-8")


def run(repo_root: Path) -> int:
    root = Path(repo_root)
    report_path, cards_path, md_path, date_str = _locate_inputs(root)

    if report_path is None:
        report = missing_input_report(
            stage="opportunity",
            reason="no opportunity_report.json found — opportunity stage did not run",
            based_on_path=None,
        )
        write_missing_input_report(root, report)
        print(f"opportunity eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    rows = json.loads(report_path.read_text(encoding="utf-8")).get("rows", [])
    cards = (
        yaml.safe_load(cards_path.read_text(encoding="utf-8")).get("cards", [])
        if cards_path is not None else []
    )
    md = md_path.read_text(encoding="utf-8") if md_path is not None else ""
    src = _read_opportunity_cmd_source()

    metrics_values = {
        "thesis_card_required_field_completeness": thesis_card_required_field_completeness(cards),
        "opportunity_evidence_gap_visibility": opportunity_evidence_gap_visibility(rows),
        "same_theme_distinct_index_limit": same_theme_distinct_index_limit(rows),
        "drawdown_not_auto_sell": drawdown_not_auto_sell(md, cards),
        "hot_chase_prevention": hot_chase_prevention(rows),
        "valid_action_enums": valid_action_enums(cards),
        "no_external_worktree_path": no_external_worktree_path(src),
    }
    thresholds = {
        "thesis_card_required_field_completeness": _HIGH_TH,
        "opportunity_evidence_gap_visibility": _HIGH_TH,
        "same_theme_distinct_index_limit": _BINARY_TH,
        "drawdown_not_auto_sell": _BINARY_TH,
        "hot_chase_prevention": _BINARY_TH,
        "valid_action_enums": _BINARY_TH,
        "no_external_worktree_path": _BINARY_TH,
    }
    n_obs = {
        "thesis_card_required_field_completeness": len(cards),
        "opportunity_evidence_gap_visibility": len(rows),
        "same_theme_distinct_index_limit": len(rows),
        "drawdown_not_auto_sell": len(cards),
        "hot_chase_prevention": len(rows),
        "valid_action_enums": len(cards),
        "no_external_worktree_path": 1,
    }
    metrics_list = [
        MetricReport(
            name=name, value=value,
            status=classify_status(value, thresholds[name], "higher_is_better"),
            n_observations=n_obs[name], threshold=thresholds[name],
        )
        for name, value in metrics_values.items()
    ]
    overall = worst_status([m.status for m in metrics_list])
    report = StageReport(
        stage="opportunity", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(report_path)] + ([str(cards_path)] if cards_path else [])
        + ([str(md_path)] if md_path else []),
        metrics=metrics_list, overall=overall,
    )
    _write(root, report, date_str)
    print(f"opportunity eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)


def _write(repo_root: Path, report: StageReport, date_str: str) -> None:
    out_dir = repo_root / "outputs" / date_str / "evals" / "opportunity"
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_dir / "report.json",
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
    )
