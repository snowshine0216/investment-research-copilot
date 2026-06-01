from __future__ import annotations

import sys
from pathlib import Path

import duckdb

from irc.config_loader import load_repo_configs
from irc.fundamentals.provider import default_cn_provider
from irc.fundamentals.snapshot_cache import load_active_fund_cache
from irc.io_utils import atomic_write_text
from irc.opportunity.fund_eval import (
    EvalItem,
    evaluate_funds,
    render_fund_eval_json,
    render_fund_eval_md,
)
from irc.opportunity.inputs_build import _build_input
from irc.schemas.universe import Instrument


def _parse_ids(ids: str | None, ids_file: str | None) -> list[str]:
    if ids_file:
        raw = Path(ids_file).read_text(encoding="utf-8")
    elif ids:
        raw = ids
    else:
        return []
    return [tok.strip() for tok in raw.replace("\n", ",").split(",") if tok.strip()]


def _instr_by_id(root: Path) -> dict[str, Instrument]:
    bundle = load_repo_configs(root)
    index: dict[str, Instrument] = {}
    for uni in (
        bundle.universe_qdii_us, bundle.universe_qdii_hk,
        bundle.universe_cn_funds, bundle.universe_gold,
    ):
        for instr in uni.instruments:
            index.setdefault(instr.instrument_id, instr)
    return index


def _latest_quarter(root: Path) -> str | None:
    base = root / "data" / "fundamentals"
    if not base.exists():
        return None
    quarters = sorted({
        p.parent.parent.name for p in base.glob("*/active_fund/fund_*.json")
    })
    return quarters[-1] if quarters else None


def _today() -> str:
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def run_eval_funds(
    repo_root: str,
    *,
    ids: str | None = None,
    ids_file: str | None = None,
    quarter: str | None = None,
    role: str = "satellite_cn_metals",
    db_path: str | None = None,
    out_path: str | None = None,
) -> int:
    root = Path(repo_root)
    fund_ids = _parse_ids(ids, ids_file)
    if not fund_ids:
        print("ERROR: provide --ids or --ids-file (comma-separated fund ids).",
              file=sys.stderr)
        return 2
    db = Path(db_path) if db_path else (root / "data" / "local.duckdb")
    if not db.exists():
        print(f"ERROR: DuckDB not found at {db}; run `irc ingest` first.",
              file=sys.stderr)
        return 2
    resolved_quarter = quarter or _latest_quarter(root)
    if resolved_quarter is None:
        print("ERROR: no cached snapshot quarter found under "
              "data/fundamentals/*/active_fund/; pass --quarter.", file=sys.stderr)
        return 2

    instr_index = _instr_by_id(root)
    provider = default_cn_provider()
    con = duckdb.connect(str(db), read_only=True)
    try:
        items: list[EvalItem] = []
        for iid in fund_ids:
            instr = instr_index.get(iid)
            asset_class = instr.asset_class if instr is not None else "cn_equity_fund"
            score_row = {"instrument_id": iid, "asset_class": asset_class, "role": role}
            inp = _build_input(
                score_row, instr, None, None, 0.0, set(), con, provider=provider,
            )
            snapshot = load_active_fund_cache(iid, resolved_quarter, root / "data")
            items.append(EvalItem(inp=inp, snapshot=snapshot, role=role))
    finally:
        con.close()

    evals = evaluate_funds(items)
    out = Path(out_path) if out_path else (
        root / "outputs" / _today() / "fund_eval.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, render_fund_eval_md(evals))
    atomic_write_text(out.with_suffix(".json"), render_fund_eval_json(evals))

    n_core = sum(1 for e in evals if e.core_dca)
    print(f"eval-funds OK: {n_core} core_dca / {len(evals)} evaluated -> {out}")
    return 0
