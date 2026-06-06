from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.config_loader import load_repo_configs
from irc.llm.gateway import resolve_route
from irc.queries.parser import parse_query
from irc.queries.responder import respond_to_query


MAX_QUESTION_LEN = 2000
MEMO_MAX_CHARS = 6000
SCORES_TOPN = 15
DECISION_REPORT_MAX_CHARS = 3000


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _read_text(path: Path, limit: int) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")[:limit]


def _load_context(out_dir: Path) -> dict[str, str]:
    context: dict[str, str] = {}
    memo = _read_text(out_dir / "memo.md", MEMO_MAX_CHARS)
    if memo:
        context["memo"] = memo
    scoring_path = out_dir / "scoring.json"
    if scoring_path.exists():
        data = json.loads(scoring_path.read_text(encoding="utf-8"))
        context["scores"] = json.dumps(data.get("scores", [])[:SCORES_TOPN], ensure_ascii=False)
    gold_regime_path = out_dir / "gold_regime.json"
    if gold_regime_path.exists():
        context["gold_regime"] = gold_regime_path.read_text(encoding="utf-8")
    gold_band_path = out_dir / "gold_band.yaml"
    if gold_band_path.exists():
        context["gold_band"] = gold_band_path.read_text(encoding="utf-8")
    decision = _read_text(out_dir / "decision_report.md", DECISION_REPORT_MAX_CHARS)
    if decision:
        context["decision_report"] = decision
    return context


def run_ask(repo_root: str, question: str) -> int:
    import logging as _logging
    from datetime import datetime, timezone, timedelta
    from irc.llm.cost_tracker import CostEntry, append_cost
    from irc.spend.record_run import record_command_run
    from irc.commands.spend_cmd import preflight_gate
    gate_rc = preflight_gate(repo_root, "ask")
    if gate_rc != 0:
        return gate_rc
    if len(question) > MAX_QUESTION_LEN:
        print(f"ERROR: question exceeds max length ({len(question)} > {MAX_QUESTION_LEN})")
        return 2
    root = Path(repo_root)
    _today_date = datetime.now(timezone(timedelta(hours=8))).date()
    bundle = load_repo_configs(root)
    out_dir = root / "outputs" / _today_date.isoformat()
    context = _load_context(out_dir)
    route = resolve_route("interactive_query", bundle.llm)
    parsed = parse_query(question)
    history: list[CostEntry] = []
    try:
        resp = respond_to_query(parsed, context, route)
        _ts = datetime.now(timezone(timedelta(hours=8))).isoformat()
        history = append_cost(history, CostEntry(
            task=route.task, provider=route.provider, model=route.model,
            prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
            latency_ms=getattr(resp, "latency_ms", 0), ts=_ts,
        ))
        print(resp.text)
        return 0
    finally:
        try:
            record_command_run(
                repo_root=root, history=history, search_units={}, today=_today_date,
            )
        except Exception:
            _logging.getLogger(__name__).warning("spend recorder failed", exc_info=True)
