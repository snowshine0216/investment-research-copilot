from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from irc.config_loader import load_repo_configs
from irc.io_utils import atomic_write_text
from irc.opportunity.cards import build_thesis_card
from irc.opportunity.discipline import (
    PositionContext,
    derive_dca_action,
    derive_risk_action,
)
from irc.opportunity.report import (
    compose_discipline_markdown,
    compose_opportunity_report,
    compose_thesis_cards_yaml,
)
from irc.commands.theme_thesis import load_theme_thesis
from irc.opportunity.selection import SelectionQuality, demote_unstable_active, reduce_same_theme
from irc.opportunity.states import build_opportunity_row
from irc.opportunity.types import (
    DisciplineRow,
    OpportunityInput,
    OpportunityRow,
)
from irc.schemas.inputs import AccountFile, Holding
from irc.schemas.universe import Instrument, UniverseConfig


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _locate_scoring(root: Path, today: str) -> Path | None:
    today_path = root / "outputs" / today / "scoring.json"
    if today_path.exists():
        return today_path
    candidates = sorted((root / "outputs").glob("*/scoring.json"))
    return candidates[-1] if candidates else None


def _load_scores(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return list(raw.get("scores", []))
    if isinstance(raw, list):
        return list(raw)
    return []


def _instrument_index(uni_list: list[UniverseConfig]) -> dict[str, Instrument]:
    index: dict[str, Instrument] = {}
    for u in uni_list:
        for instr in u.instruments:
            index.setdefault(instr.instrument_id, instr)
    return index


def _holdings_index(account: AccountFile) -> dict[str, Holding]:
    idx: dict[str, Holding] = {}
    for acc in account.accounts:
        for h in acc.holdings:
            if h.instrument_id is not None:
                idx[h.instrument_id] = h
    return idx


def _build_input(
    score_row: dict,
    instr: Instrument | None,
    holding: Holding | None,
    target_band: tuple[float, float] | None,
    portfolio_total_cny: float,
    available_venues: set[str],
) -> OpportunityInput:
    asset_class = score_row.get("asset_class") or (instr.asset_class if instr else "unknown")
    market = instr.market if instr else "cn_off_exchange"
    theme = instr.theme if instr else None
    tracked_index = instr.tracked_index if instr else None
    name_cn = instr.name_cn if instr else score_row.get("instrument_id", "")
    weight = None
    if holding is not None and portfolio_total_cny > 0:
        weight = holding.cost_basis_cny / portfolio_total_cny
    # Empty available_venues means no venue restriction configured — treat as compatible.
    if available_venues and instr is not None and instr.venue_required:
        venue_ok = bool(set(instr.venue_required) & available_venues)
    else:
        venue_ok = True
    return OpportunityInput(
        instrument_id=score_row.get("instrument_id", ""),
        asset_class=asset_class,
        market=market,
        theme=theme,
        tracked_index=tracked_index,
        name_cn=name_cn,
        role=score_row.get("role", ""),
        is_holding=holding is not None,
        portfolio_weight=weight,
        target_band_low=target_band[0] if target_band else None,
        target_band_high=target_band[1] if target_band else None,
        venue_compatible=venue_ok,
        drawdown_since_entry=None,
        valuation_percentile_self=None,
        valuation_percentile_vs_benchmark=None,
        expense_ratio=None,
        aum_cny=None,
        manager_tenure_years=None,
    )


def _selection_quality_from(input_row: OpportunityInput) -> SelectionQuality:
    return SelectionQuality(
        expense_ratio=input_row.expense_ratio,
        aum_cny=input_row.aum_cny,
        tracking_error=input_row.tracking_error,
        premium_discount_abs=(
            abs(input_row.premium_discount_pct)
            if input_row.premium_discount_pct is not None else None
        ),
        history_days=None,
        data_completeness=1.0,
    )


def _role_for(row: OpportunityRow, roles: dict[str, str]) -> str:
    """Return the role label for a row; falls back to 'watchlist' if absent."""
    return roles.get(row.instrument_id) or "watchlist"


def _discipline_row_from(
    row: OpportunityRow, position: PositionContext,
) -> DisciplineRow:
    dca = derive_dca_action(row)
    risk = derive_risk_action(row, position)
    note = row.opportunity_reason.split(" | ")[0] if row.opportunity_reason else ""
    return DisciplineRow(
        instrument_id=row.instrument_id,
        name_cn=row.name_cn,
        asset_class=row.asset_class,
        theme=row.theme,
        opportunity_state=row.opportunity_state,
        dca_action=dca,
        risk_action=risk,
        note_cn=note,
    )


def run_opportunity(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()
    available_venues: set[str] = {
        v for acc in bundle.account.accounts for v in acc.available_venues
    }

    scoring_path = _locate_scoring(root, today)
    if scoring_path is None:
        print("ERROR: no scoring.json; run `irc score` first.")
        return 2
    # Outputs follow the convention outputs/{YYYY-MM-DD}/scoring.json;
    # compare the parent directory name to today's date to detect staleness.
    if scoring_path.parent.name != today:
        print(f"WARNING: using stale scoring from {scoring_path.parent.name}")
    scores = _load_scores(scoring_path)

    try:
        theme_thesis = load_theme_thesis(root)
    except ValueError as exc:
        print(f"ERROR: theme_thesis.yaml invalid: {exc}")
        return 2
    instr_index = _instrument_index([
        bundle.universe_qdii_us, bundle.universe_qdii_hk,
        bundle.universe_cn_funds, bundle.universe_gold,
    ])
    holdings = _holdings_index(bundle.account)
    portfolio_total_cny = sum(
        h.cost_basis_cny for acc in bundle.account.accounts for h in acc.holdings
    )

    rows: list[OpportunityRow] = []
    positions: dict[str, PositionContext] = {}
    qualities: dict[str, SelectionQuality] = {}
    roles: dict[str, str] = {}
    for score in scores:
        iid = score.get("instrument_id", "")
        if not iid:
            print(f"WARNING: skipping score row with missing instrument_id: {score}")
            continue
        instr = instr_index.get(iid)
        holding = holdings.get(iid)
        target_band: tuple[float, float] | None = None
        if instr is not None:
            tgt = bundle.preferences.asset_class_targets.get(instr.asset_class)
            if tgt is not None:
                target_band = (tgt.band[0], tgt.band[1])
        inp = _build_input(score, instr, holding, target_band, portfolio_total_cny, available_venues)
        row = build_opportunity_row(inp, theme_thesis or None)
        rows.append(row)
        positions[iid] = PositionContext(
            portfolio_weight=inp.portfolio_weight,
            target_band_low=inp.target_band_low,
            target_band_high=inp.target_band_high,
            drawdown_since_entry=inp.drawdown_since_entry,
            is_holding=inp.is_holding,
        )
        qualities[iid] = _selection_quality_from(inp)
        roles[iid] = inp.role or (instr.theme if instr else "") or ""

    # Warn when all classifiers globally lack data (skeleton mode).
    # This happens when ingest hasn't wired signal fields yet (Phase 1 gap).
    if rows:
        _insuf = "evidence_insufficient"
        all_val = all(r.valuation_state == _insuf for r in rows)
        all_heat = all(r.heat_state == _insuf for r in rows)
        all_thesis = all(r.thesis_state == _insuf for r in rows)
        all_product = all(r.product_quality_state == _insuf for r in rows)
        if all_val and all_heat and all_thesis and all_product:
            print(
                f"WARNING: opportunity layer running in skeleton mode — "
                f"valuation/heat/thesis/product data not yet wired from ingest; "
                f"all {len(rows)} instruments show evidence_insufficient. "
                "See TODOS.md."
            )
        else:
            n_missing_val = sum(1 for r in rows if r.valuation_state == _insuf)
            if n_missing_val:
                print(
                    f"WARNING: {n_missing_val}/{len(rows)} instruments missing "
                    "valuation data — those states degraded to evidence_insufficient."
                )

    # Same-theme reduction inside each theme bucket.
    # Note: reduce_same_index (per-index primary+backup selection) is available
    # in irc.opportunity.selection for callers that need it directly. The
    # reduce_same_theme Stage 1 already collapses each index key to a single
    # best representative; wiring in per-index backups is deferred (see TODOS.md).
    by_theme: dict[str, list[OpportunityRow]] = {}
    for r in rows:
        by_theme.setdefault(r.theme or "_unthemed", []).append(r)
    kept_rows: list[OpportunityRow] = []
    dropped_rows: list[OpportunityRow] = []
    for theme, group in by_theme.items():
        if theme == "_unthemed":
            kept_rows.extend(group)
            continue
        kept, dropped = reduce_same_theme(group, qualities, max_per_theme=2)
        kept_rows.extend(kept)
        dropped_rows.extend(dropped)

    # Always include current holdings even if reduction dropped them.
    held_ids = set(holdings.keys())
    for r in dropped_rows:
        if r.instrument_id in held_ids and r not in kept_rows:
            kept_rows.append(r)

    # Demote active funds to small_watch when a passive alternative in the
    # same theme is at least as good (selection quality comparison).
    kept_rows_t, demoted_active = demote_unstable_active(list(kept_rows), qualities)
    kept_rows = list(kept_rows_t)
    if demoted_active:
        print(
            f"INFO: demoted {len(demoted_active)} active fund(s) to small_watch "
            "(passive alternative available in same theme)"
        )

    cards = [
        build_thesis_card(
            row=r,
            position=positions[r.instrument_id],
            role=_role_for(r, roles),
            entry_reason=r.opportunity_reason.split(" | ")[0] if r.opportunity_reason else "",
        )
        for r in kept_rows
        if r.instrument_id in holdings or r.opportunity_state in ("core_dca", "small_watch")
    ]

    discipline_rows = [
        _discipline_row_from(r, positions[r.instrument_id]) for r in kept_rows
    ]

    out_dir = root / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    atomic_write_text(
        out_dir / "opportunity_report.json",
        json.dumps(compose_opportunity_report(kept_rows, today), ensure_ascii=False, indent=2),
    )
    atomic_write_text(
        out_dir / "thesis_cards.yaml",
        compose_thesis_cards_yaml(cards),
    )
    atomic_write_text(
        out_dir / "discipline_report.md",
        compose_discipline_markdown(discipline_rows, today),
    )

    print(
        f"opportunity OK: {len(kept_rows)} rows, {len(cards)} cards, "
        f"{len(discipline_rows)} discipline entries -> {out_dir}"
    )
    return 0
