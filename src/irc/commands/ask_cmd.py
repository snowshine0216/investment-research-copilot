from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.config_loader import load_repo_configs
from irc.llm.gateway import resolve_route
from irc.queries.parser import parse_query
from irc.queries.responder import respond_to_query


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def run_ask(repo_root: str, question: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()
    context: dict[str, str] = {}
    memo_path = root / "outputs" / today / "memo.md"
    if memo_path.exists():
        context["memo"] = memo_path.read_text(encoding="utf-8")[:4000]
    scoring_path = root / "outputs" / today / "scoring.json"
    if scoring_path.exists():
        data = json.loads(scoring_path.read_text(encoding="utf-8"))
        context["scores"] = json.dumps(data.get("scores", [])[:10], ensure_ascii=False)
    route = resolve_route("interactive_query", bundle.llm)
    parsed = parse_query(question)
    resp = respond_to_query(parsed, context, route)
    print(resp.text)
    return 0
