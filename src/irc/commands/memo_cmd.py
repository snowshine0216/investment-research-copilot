from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import yaml
from irc.config_loader import load_repo_configs
from irc.data.freshness import require_fresh_ingest
from irc.io_utils import atomic_write_text
from irc.llm.gateway import resolve_route
from irc.memo.auditor import audit_blocks_publish
from irc.memo.diagnostics import (
    compose_execution_drift_lines,
    compose_fx_qdii_lines,
    compose_role_bucket_banner,
)
from irc.memo.evidence_pool import build_evidence_pool
from irc.memo.picks_table import PickRow, render_picks_table
from irc.memo.template import MemoInputs
from irc.memo.pipeline import extract_evidence_cutoff, run_memo_pipeline


_DEFAULT_TIMELINESS_NOTE = (
    "数据时效：行情/净值通常为T+1；具体日期见证据池。"
)


# Audit P1 (2026-05-20) flagged the prior "实际利率与美元走向是黄金定价的
# 主导变量" phrasing as a deterministic causal claim. Softened text frames
# real-yield/USD as one set of reference variables among several (地缘 +
# 央行购金) and defers A-share valuation specifics to the evidence pool.
_MACRO_SUMMARY = (
    "实际利率与美元走向通常被视为黄金定价的重要参考变量之一；"
    "地缘风险、央行购金行为等其他因素同样可能对金价产生显著影响。"
    "A 股宽基估值百分位以证据池中的具体读数为准，本节不做定性结论。"
    " 数据请以证据池中的具体数字为准，不要自行编造。"
)


def _format_threshold(threshold: object) -> str:
    """Render a trigger threshold for display.

    Numeric thresholds (real_yield, VIX, weekly_return) render with their
    repr to preserve sign and decimals; categorical string thresholds
    (valuation_state, heat_state) render verbatim.
    """
    if isinstance(threshold, bool):
        return str(threshold)
    if isinstance(threshold, (int, float)):
        return f"{threshold}"
    return str(threshold)


def _format_trigger(trigger: dict) -> str:
    """Render a single trigger as `name (data_field comparator threshold)`.

    Audit P4 (2026-05-20) flagged the prior bare-code form
    ('real_yield_low，weekly_drawdown_4pct') as ambiguous — executors had
    no comparator or threshold without consulting trade_plan.yaml.
    """
    name = str(trigger.get("name", "") or "")
    data_field = str(trigger.get("data_field", "") or "")
    comparator = str(trigger.get("comparator", "") or "")
    threshold = _format_threshold(trigger.get("threshold"))
    if not (name and data_field and comparator):
        return name or "无"
    return f"{name} ({data_field} {comparator} {threshold})"


def _compose_execution_lines(
    trades: list[dict],
    opportunity_rows: list[dict],
) -> tuple[str, ...]:
    """Build one bullet per trade row for memo section 7.

    Sourcing data deterministically from the trade plan removes the
    LLM-fillable placeholder that left section 7 empty in 2026-05-18.
    Each bullet carries: id+name, target weight cap, buy_method,
    granularity, fully-qualified triggers (or "无"), and venue_note.

    Multi-trigger trades render with a 满足任一 (any-of / OR) marker —
    triggers in the plan are independent by construction
    (see ``src/irc/trades/triggers.py:emit_triggers_for_trade``).
    """
    name_by_id = {str(r.get("instrument_id")): r.get("name_cn", "")
                  for r in opportunity_rows}
    lines: list[str] = []
    for t in trades:
        iid = str(t.get("target", ""))
        name = name_by_id.get(iid, "")
        weight = float(t.get("target_weight") or 0.0)
        raw_triggers = list(t.get("triggers") or [])
        formatted = [_format_trigger(tr) for tr in raw_triggers]
        formatted = [f for f in formatted if f]
        if not formatted:
            triggers = "无"
        elif len(formatted) == 1:
            triggers = formatted[0]
        else:
            triggers = "满足任一：" + "；".join(formatted)
        venue_note = str(t.get("venue_note", ""))
        bullet = (
            f"**{iid} {name}** | 目标权重 ≤ {weight*100:.1f}% | "
            f"建仓方式 {t.get('buy_method', 'unknown')} ({t.get('granularity', 'default')}) | "
            f"触发 {triggers} | 渠道 {venue_note}"
        )
        lines.append(bullet)
    return tuple(lines)


def _compose_risk_notes(cutoff: str | None) -> tuple[str, ...]:
    """Return the memo risk-notes tuple, with the data-timeliness bullet
    rewritten when we know the evidence-pool cutoff date.

    When ``cutoff`` is non-None, the bullet calls out the exact ISO date the
    snapshot was taken plus the typical lag patterns (境内 T+1, QDII 跨境结算
    更长). When None, fall back to today's boilerplate so the path is
    backwards-compatible.
    """
    if cutoff is None:
        timeliness = _DEFAULT_TIMELINESS_NOTE
    else:
        timeliness = (
            f"数据时效：证据池截止 {cutoff}（akshare 净值/价格快照）；"
            "境内净值/价格通常滞后 1 个交易日，QDII 跨境结算可能滞后更长，"
            "节假日/停牌将进一步延长。所有数值不代表实时市场状态，执行前须自行核实。"
        )
    return (
        "实际利率上行风险：实际利率反弹会压制金价。",
        "估值压力：宽基ETF在估值百分位偏高时回撤风险加大。",
        "渠道与汇率：venue_compatible=false的标的不可执行，仅观察。",
        timeliness,
    )


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _latest_file(root: Path, pattern: str) -> Path | None:
    candidates = sorted(root.glob(pattern))
    return candidates[-1] if candidates else None


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_discovery_diagnostics(out_dir: Path) -> list[dict]:
    """Best-effort read of discovery_diagnostics.csv for the role-bucket
    banner (item 010, 2026-05-19). Returns an empty list when the file
    is absent or unreadable so memo can still render."""
    import csv

    path = out_dir / "discovery_diagnostics.csv"
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except (OSError, csv.Error):
        return []


def _names_from_watchlist_csv(out_dir: Path) -> dict[str, str]:
    """Best-effort `instrument_id → name_cn` map from discovered_watchlist.csv.

    Used as a fallback when opportunity_report.json is absent (e.g. earlier
    pipeline run skipped the opportunity stage) so picks-table rows never
    render their id in the 名称 column.
    """
    import csv

    path = out_dir / "discovered_watchlist.csv"
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8", newline="") as f:
            return {
                str(row.get("instrument_id") or ""): str(row.get("name_cn") or "")
                for row in csv.DictReader(f)
                if row.get("instrument_id") and row.get("name_cn")
            }
    except (OSError, csv.Error):
        return {}


def _names_from_universes(bundle) -> dict[str, str]:
    """`instrument_id → name_cn` from configured universes.

    Covers venue proxies (e.g. ``cmb_paper_gold`` → ``招商银行账户金``) that
    appear in trade_plan.yaml as targets but are never scored, so they
    don't appear in scoring.json or opportunity_report.json.
    """
    names: dict[str, str] = {}
    for uni in (
        getattr(bundle, "universe_qdii_us", None),
        getattr(bundle, "universe_qdii_hk", None),
        getattr(bundle, "universe_cn_funds", None),
        getattr(bundle, "universe_gold", None),
    ):
        if uni is None:
            continue
        for instr in getattr(uni, "instruments", ()) or ():
            iid = getattr(instr, "instrument_id", None)
            name = getattr(instr, "name_cn", None)
            if iid and name and iid not in names:
                names[iid] = name
    return names


def _derive_tldr_lines(gold: dict, alloc: dict, opportunity: dict, plan: dict) -> tuple[str, ...]:
    summary = opportunity.get("summary") or {}
    n_core = summary.get("core_dca_count", 0)
    n_watch = summary.get("small_watch_count", 0)
    n_pause = summary.get("pause_wait_count", 0)
    lines: list[str] = []
    lines.append(
        f"黄金：regime={gold.get('regime', '?')}，zone={gold.get('zone', '?')}，"
        f"仓位倾斜={alloc.get('gold_tilt', '?')}。"
    )
    lines.append(f"建仓模式：{plan.get('mode') or 'build'}（按节奏定投，不一次性投入）。")
    lines.append(
        f"机会面：core_dca={n_core}，small_watch={n_watch}，pause_wait={n_pause}。"
    )
    return tuple(lines)


def _build_pick_rows(
    trades: list[dict],
    opportunity: dict,
    scoring: dict,
    extra_names: dict[str, str] | None = None,
) -> list[PickRow]:
    op_by_id = {r["instrument_id"]: r for r in (opportunity.get("rows") or [])}
    score_by_id = {s["instrument_id"]: s for s in (scoring.get("scores") or [])}
    extra_names = extra_names or {}
    rows: list[PickRow] = []
    seen: set[str] = set()  # Canonical dedup; render_picks_table has a safety-net guard.
    for t in trades:
        iid = t.get("target")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        op = op_by_id.get(iid) or {}
        sc = score_by_id.get(iid) or {}
        # Sanitize: strip newlines before the string enters the LLM skeleton.
        reason = (op.get("opportunity_reason") or "").split(" | ")[0].replace("\n", " ").strip()
        opp_state = op.get("opportunity_state", "small_watch")
        dca = {"core_dca": "normal_dca", "small_watch": "slow_dca",
               "pause_wait": "pause_dca", "exclude": "do_not_buy"}.get(opp_state, "slow_dca")
        # Trade plan carries composite_score directly; prefer it so venue
        # proxies (whose target id isn't in scoring.json) still show the
        # underlying instrument's score instead of 0.0.
        score = t.get("composite_score")
        if score is None:
            score = sc.get("composite_score") or 0.0
        name = op.get("name_cn") or extra_names.get(str(iid)) or iid
        rows.append(PickRow(
            instrument_id=iid,
            name_cn=name,
            asset_class=op.get("asset_class") or t.get("asset_class", ""),
            role=t.get("role") or "",
            target_weight=float(t.get("target_weight") or 0.0),
            composite_score=float(score),
            opportunity_state=opp_state,
            dca_action=dca,
            risk_action="none",
            one_line_reason=reason or "—",
        ))
    return rows


def run_memo(repo_root: str) -> int:
    root = Path(repo_root)
    if not require_fresh_ingest(root, stage="memo"):
        print("ERROR: memo stage halted — ingest is stale. "
              "See outputs/<today>/STALE_INGEST.md or set IRC_ALLOW_STALE=1.")
        return 1
    bundle = load_repo_configs(root)
    today = _today()

    scoring_path = root / "outputs" / today / "scoring.json"
    if not scoring_path.exists():
        p = _latest_file(root, "outputs/*/scoring.json")
        if p is None:
            print("ERROR: no scoring.json; run `irc score` first.")
            return 2
        scoring_path = p

    out_today = scoring_path.parent  # use same date dir as scoring

    scoring = json.loads(scoring_path.read_text(encoding="utf-8"))
    gold = _load_json(out_today / "gold_regime.json")
    alloc = _load_yaml(out_today / "proposed_allocation.yaml")
    plan = _load_yaml(out_today / "trade_plan.yaml")
    opportunity = _load_json(out_today / "opportunity_report.json")

    trades = list(plan.get("trades") or [])
    # Resilience: when opportunity_report.json is missing (e.g. an older
    # pipeline run that skipped the opportunity stage) or when the trade
    # target is a venue proxy that doesn't exist in opportunity rows,
    # fall back to universe-config / watchlist-CSV names so the 名称
    # column never renders an instrument id verbatim.
    fallback_names = {
        **_names_from_watchlist_csv(out_today),
        **_names_from_universes(bundle),
    }
    pick_rows = _build_pick_rows(trades, opportunity, scoring, fallback_names)
    picks_table_md = render_picks_table(pick_rows)

    gold_regime = {
        "regime": gold.get("regime", "unknown"),
        "zone": gold.get("zone", "unknown"),
        "tilt": alloc.get("gold_tilt", "neutral"),
    }
    raw_ref_pool = build_evidence_pool(
        opportunity_rows=list(opportunity.get("rows") or []),
        scoring_rows=list(scoring.get("scores") or []),
        plan_trades=trades,
        gold_regime=gold_regime,
    )

    tldr = _derive_tldr_lines(gold, alloc, opportunity, plan)

    cutoff = extract_evidence_cutoff(raw_ref_pool)
    risk_notes = _compose_risk_notes(cutoff)
    # Deterministic diagnostics injected into risk_notes so the LLM can't
    # omit them and the audit gate can verify presence
    # (adversarial-review items 013, 014).
    cash_target_center = float(
        getattr(bundle.preferences.asset_class_targets.get("cash", None), "center", 0.05) or 0.05
    )
    drift_lines = compose_execution_drift_lines(alloc, cash_target_center)
    if drift_lines:
        risk_notes = tuple(drift_lines) + risk_notes
    usd_tol_pair: tuple[float, float] | None = None
    _usd_tol = getattr(bundle.preferences.currency_tolerance, "usd", None)
    if _usd_tol and len(_usd_tol) >= 2:
        usd_tol_pair = (float(_usd_tol[0]), float(_usd_tol[1]))
    fx_policy = getattr(getattr(bundle.preferences, "fx_hedge", None), "policy", None)
    fx_lines = compose_fx_qdii_lines(alloc, usd_tol_pair, fx_hedge_policy=fx_policy)
    if fx_lines:
        risk_notes = tuple(fx_lines) + risk_notes
    # Role-bucket banner (item 010): adversarial review §E.
    diag_rows = _load_discovery_diagnostics(out_today)
    role_lines = compose_role_bucket_banner(diag_rows)
    if role_lines:
        risk_notes = tuple(role_lines) + risk_notes
    execution_lines = _compose_execution_lines(trades, opportunity.get("rows") or [])

    inputs = MemoInputs(
        date_str=today,
        gold_regime=gold.get("regime", "unknown"),
        gold_zone=gold.get("zone", "unknown"),
        gold_tilt=alloc.get("gold_tilt", "neutral"),
        allocation_mode=plan.get("mode", "unknown"),
        macro_summary=_MACRO_SUMMARY,
        top_picks=tuple(r.instrument_id for r in pick_rows),
        risk_notes=risk_notes,
        tldr_lines=tldr,
        picks_table_md=picks_table_md,
        execution_lines=execution_lines,
    )

    synth_route = resolve_route("memo_synthesis", bundle.llm)
    audit_route = resolve_route("memo_audit", bundle.llm)
    output = run_memo_pipeline(inputs, raw_ref_pool, synth_route, audit_route)

    out_dir = root / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    # Audit-blocking gate (item 009, 2026-05-19): if the auditor returned
    # 审核未通过 OR P-tier 高风险 findings, refuse to publish memo.md;
    # write memo_blocked.md instead and exit non-zero.
    blocked, block_reasons = audit_blocks_publish(output.audit_notes)
    atomic_write_text(out_dir / "memo_audit.txt", output.audit_notes)
    atomic_write_text(out_dir / "memo_traceability.json", json.dumps({
        "n_refs_provided": output.traceability["n_refs_provided"],
        "n_refs_quoted_verbatim": output.traceability["n_refs_quoted_verbatim"],
        "n_refs": output.traceability["n_refs"],
    }, indent=2))
    if blocked:
        block_header = (
            "# 备忘录发布被审核拒绝\n\n"
            "审核报告含 P-tier 高风险项或 '审核未通过' 明确否决；"
            "下面是被拒草稿，仅供修订使用，请勿直接对外发布。\n\n"
            "## 阻断原因\n\n"
            + "\n".join(f"- {r}" for r in block_reasons)
            + "\n\n---\n\n"
        )
        atomic_write_text(out_dir / "memo_blocked.md", block_header + output.draft)
        # Remove a stale memo.md from a prior good run so it can't be
        # mistaken for the current verdict.
        memo_path = out_dir / "memo.md"
        if memo_path.exists():
            memo_path.unlink()
        print(
            "memo BLOCKED: audit gate flagged the draft — "
            f"see {out_dir/'memo_blocked.md'} and {out_dir/'memo_audit.txt'}"
        )
        for reason in block_reasons:
            print(f"  - {reason}")
        return 2
    atomic_write_text(out_dir / "memo.md", output.draft)
    print(
        f"memo OK: {output.traceability['n_refs_quoted_verbatim']}/"
        f"{output.traceability['n_refs_provided']} refs quoted verbatim "
        f"→ {out_dir/'memo.md'}"
    )
    return 0
