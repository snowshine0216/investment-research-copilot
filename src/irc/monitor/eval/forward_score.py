"""PURE forward scorer: deduped ledger rows + per-fund nav_history series →
matured ForwardRows projected into the three metric populations. Three dates kept
strictly separate (anchor=run_date). No I/O."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from irc.monitor.eval.join import series_entry_outcome


@dataclass(frozen=True)
class ForwardRow:
    run_date: str
    fund_id: str
    as_of_date: str
    raw_status: str
    raw_composite: float
    raw_bias: str | None
    entry_nav_date: str
    fwd_ret: float
    from_latest_nav: float           # as_of-anchored diagnostic ONLY (look-ahead)
    market_composite: float | None = None
    market_bias: str | None = None


def _is_iso_date(s) -> bool:
    if not isinstance(s, str):
        return False
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def prefilter_ledger(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Pre-maturity ledger-quality filter (§2.2). Drop rows where nav_acc is None,
    as_of_date is missing/'N/A'/non-ISO, or as_of_date > run_date. Excluded under
    null_signal_nav — these never enter any metric population."""
    kept: list[dict] = []
    excl: dict[str, int] = {}
    for r in rows:
        bad = (
            r.get("nav_acc") is None
            or not _is_iso_date(r.get("as_of_date"))
            or not _is_iso_date(r.get("run_date"))
            or r["as_of_date"] > r["run_date"]
        )
        if bad:
            excl["null_signal_nav"] = excl.get("null_signal_nav", 0) + 1
        else:
            kept.append(r)
    return kept, excl


_LEGACY_ENGINE = "0"


def _row_engine(r: dict) -> str:
    mv = r.get("manifest_versions") or {}
    return str(mv.get("engine", _LEGACY_ENGINE))


def _filter_engine(
    rows: list[dict], target_engine: str | None,
) -> tuple[list[dict], dict[str, int]]:
    """When target_engine is set, drop rows whose engine != target (missing → legacy
    '0'); count drops under engine_mismatch. None → no-op (back-compat)."""
    if target_engine is None:
        return rows, {}
    kept, n = [], 0
    for r in rows:
        if _row_engine(r) == target_engine:
            kept.append(r)
        else:
            n += 1
    return kept, ({"engine_mismatch": n} if n else {})


def _series_for(nav_rows: list[dict]) -> tuple[tuple[str, float], ...]:
    return tuple((r["nav_date"], float(r["nav_acc"])) for r in nav_rows)


def _from_latest_nav(series, run_date, outcome_idx) -> float:
    """as_of-anchored (look-ahead) diagnostic: return from the LAST obs <= run_date
    to the outcome obs. Stored labeled; never a headline."""
    idx = -1
    for i, (d, _) in enumerate(series):
        if d <= run_date:
            idx = i
    if idx < 0 or outcome_idx >= len(series) or series[idx][1] <= 0:
        return float("nan")
    return series[outcome_idx][1] / series[idx][1] - 1.0


def score_forward(
    ledger_rows: list[dict], nav_by_fund: dict[str, list[dict]],
    *, h: int, today: str, target_engine: str | None = None,
) -> tuple[list[ForwardRow], dict[str, int]]:
    """Pre-filter → engine filter → maturity join (anchor=run_date, strict >) → ForwardRows.
    Excluded reasons accumulate (engine_mismatch, null_signal_nav, no_entry_obs, not_matured,
    bad_nav). target_engine=None preserves today's no-filter behavior (back-compat)."""
    eng_kept, eng_excl = _filter_engine(ledger_rows, target_engine)
    kept, excl = prefilter_ledger(eng_kept)
    excl = {**eng_excl, **excl}
    out: list[ForwardRow] = []
    for r in kept:
        nav_rows = nav_by_fund.get(r["fund_id"], [])
        series = _series_for(nav_rows)
        eo = series_entry_outcome(series, anchor=r["run_date"], h=h, today=today)
        if eo.reason != "ok":
            excl[eo.reason] = excl.get(eo.reason, 0) + 1
            continue
        mc = r.get("market_composite")
        out.append(ForwardRow(
            run_date=r["run_date"], fund_id=r["fund_id"], as_of_date=r["as_of_date"],
            raw_status=r["raw_status"], raw_composite=float(r["raw_composite"]),
            raw_bias=r.get("raw_bias"),
            entry_nav_date=eo.entry_nav_date, fwd_ret=eo.fwd_ret,
            from_latest_nav=_from_latest_nav(series, r["run_date"], eo.outcome_idx),
            market_composite=float(mc) if mc is not None else None,
            market_bias=r.get("market_bias"),
        ))
    return out, excl
