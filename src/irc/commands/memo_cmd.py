from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import yaml
from irc.config_loader import load_repo_configs
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route
from irc.memo.template import MemoInputs
from irc.memo.pipeline import run_memo_pipeline


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _latest_file(root: Path, pattern: str) -> Path | None:
    candidates = sorted(root.glob(pattern))
    return candidates[-1] if candidates else None


def run_memo(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()

    scoring_path = (root / "outputs" / today / "scoring.json")
    if not scoring_path.exists():
        p = _latest_file(root, "outputs/*/scoring.json")
        if p is None:
            print("ERROR: no scoring.json; run `irc score` first.")
            return 2
        scoring_path = p

    gold_path = (root / "outputs" / today / "gold_regime.json")
    alloc_path = (root / "outputs" / today / "proposed_allocation.yaml")
    plan_path = (root / "outputs" / today / "trade_plan.yaml")

    scoring = json.loads(scoring_path.read_text(encoding="utf-8"))
    gold = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.exists() else {}
    alloc = yaml.safe_load(alloc_path.read_text(encoding="utf-8")) if alloc_path.exists() else {}
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}

    raw_ref_pool: list[str] = []
    for s in scoring.get("scores", []):
        for _factor, detail in s.get("factor_breakdown", {}).items():
            raw_ref_pool.extend(detail.get("raw_refs", []))

    top_picks = [t["target"] for t in plan.get("trades", [])]
    inputs = MemoInputs(
        date_str=today,
        gold_regime=gold.get("regime", "unknown"),
        gold_zone=gold.get("zone", "unknown"),
        gold_tilt=alloc.get("gold_tilt", "neutral"),
        allocation_mode=plan.get("mode", "unknown"),
        macro_summary="实际利率趋势及全球宏观背景（由AI填充）",
        top_picks=top_picks,
        risk_notes=["请参阅风险因子"],
        tldr_lines=["本期要点由AI合成器自动生成"],
    )

    synth_route = resolve_route("memo_synthesis", bundle.llm)
    audit_route = resolve_route("memo_audit", bundle.llm)
    output = run_memo_pipeline(inputs, raw_ref_pool, synth_route, audit_route)

    out_dir = root / "outputs" / today
    atomic_write_text(out_dir / "memo.md", output.draft)
    atomic_write_text(out_dir / "memo_audit.txt", output.audit_notes)
    atomic_write_text(out_dir / "memo_traceability.json", json.dumps({
        "coverage_ratio": output.traceability.coverage_ratio,
        "missing_count": len(output.traceability.missing_refs),
    }, indent=2))
    print(f"memo OK: coverage={output.traceability.coverage_ratio:.0%} → {out_dir/'memo.md'}")
    return 0
