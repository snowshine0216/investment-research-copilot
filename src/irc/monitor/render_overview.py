"""PURE 今日速览 (today-at-a-glance) overview strip for report v3 (spec §7).
Three rows: 偏向变化 (bias flips vs prior run) / 可操作 (actionable, gate-
respecting) / 数据健康 (dark-factor + gate + stale-eval counts). Each row
dropped when empty; all-empty -> one muted quiet line. No I/O — all inputs
already exist in the command layer."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from html import escape

from irc.monitor.eval.gate import published_state


@dataclass(frozen=True)
class BiasFlip:
    fund_id: str
    name_cn: str
    from_bias: str
    to_bias: str
    prior_run_date: str


@dataclass(frozen=True)
class ActionableFund:
    fund_id: str
    name_cn: str
    bias: str
    purchase_restricted: bool


@dataclass(frozen=True)
class DataHealthCounts:
    dark_factor_fractions: dict[str, tuple[int, int]]
    gated_fund_count: int
    stale_eval_count: int


def _flip_row(flips: tuple[BiasFlip, ...]) -> str:
    if not flips:
        return ""
    items = "".join(
        f'<li>{escape(f.name_cn)}({escape(f.fund_id)}) '
        f'<span class="flip-from">{escape(f.from_bias)}</span>→'
        f'<span class="flip-to">{escape(f.to_bias)}</span> '
        f'<span class="muted">(vs {escape(f.prior_run_date)})</span></li>'
        for f in flips
    )
    return f'<div class="overview-row"><b>偏向变化</b><ul>{items}</ul></div>'


def _actionable_row(actionable: tuple[ActionableFund, ...]) -> str:
    if not actionable:
        return ""
    items = "".join(
        f'<li>{escape(a.name_cn)}({escape(a.fund_id)}) '
        f'<span class="badge {a.bias.lower()}">{escape(a.bias)}</span>'
        + (' <span class="restricted-tag">限购</span>' if a.purchase_restricted else "")
        + "</li>"
        for a in actionable
    )
    return f'<div class="overview-row"><b>可操作</b><ul>{items}</ul></div>'


def _health_row(health: DataHealthCounts) -> str:
    if (not health.dark_factor_fractions and health.gated_fund_count == 0
            and health.stale_eval_count == 0):
        return ""
    dark_parts = "、".join(
        f"{escape(name)} {dark}/{elig}"
        for name, (dark, elig) in sorted(health.dark_factor_fractions.items())
    )
    dark_txt = f"因子暗：{dark_parts}" if dark_parts else ""
    gated_txt = f"{health.gated_fund_count} 只基金被评估门禁" if health.gated_fund_count else ""
    stale_txt = f"过期评估 {health.stale_eval_count}" if health.stale_eval_count else ""
    parts = " · ".join(p for p in (dark_txt, gated_txt, stale_txt) if p)
    return f'<div class="overview-row"><b>数据健康</b> {parts}</div>'


def overview_html(
    *, flips: tuple[BiasFlip, ...], actionable: tuple[ActionableFund, ...],
    health: DataHealthCounts,
) -> str:
    """PURE: 今日速览 strip. Each row dropped when empty; all-empty -> quiet line."""
    rows = "".join((_flip_row(flips), _actionable_row(actionable), _health_row(health)))
    if not rows:
        return '<section class="overview"><p class="muted">今日无变化，数据健康</p></section>'
    return f'<section class="overview"><h2>今日速览</h2>{rows}</section>'


def compute_flips(
    views: tuple, prior: dict | None, prior_run_date: str | None,
) -> tuple[BiasFlip, ...]:
    """PURE: bias flips vs the prior run's signal.json snapshot (the existing
    prior_signal read, the orange-dot data). prior=None or prior_run_date=None
    -> () (no prior run to compare against). A fund absent from prior (new
    fund, or prior run failed) -> no flip (nothing to compare)."""
    if not prior or prior_run_date is None:
        return ()
    out: list[BiasFlip] = []
    for v in views:
        prev = prior.get(v.fund_id)
        if prev is None:
            continue
        prev_bias = prev.get("bias")
        cur_bias = v.signal.bias
        if prev_bias is not None and cur_bias is not None and prev_bias != cur_bias:
            out.append(BiasFlip(v.fund_id, v.name_cn, prev_bias, cur_bias, prior_run_date))
    return tuple(out)


_ACTIONABLE_BIASES = frozenset({"ADD_BIAS", "REDUCE_BIAS"})


def compute_actionable(
    views: tuple, gates: dict, purchase_tags: dict[str, str | None],
) -> tuple[ActionableFund, ...]:
    """PURE: funds whose published_state (signal+gate) is ADD_BIAS/REDUCE_BIAS
    — i.e. NOT NO_CALL, NOT EVAL_GATED, NOT NEUTRAL. published_state already
    encodes the gate-respect contract (eval/gate.py: EVAL_GATED when
    gate.suppressed, else the raw bias) — reusing it here means an
    EVAL-GATED fund can never appear, by construction (spec §11)."""
    out: list[ActionableFund] = []
    for v in views:
        gate = gates.get(v.fund_id)
        if gate is None:
            continue
        state = published_state(v.signal, gate)
        if state not in _ACTIONABLE_BIASES:
            continue
        tag = purchase_tags.get(v.fund_id)
        out.append(ActionableFund(v.fund_id, v.name_cn, state, tag is not None))
    return tuple(out)


_PROFILE_INELIGIBLE = "profile_ineligible"


def _dark_fractions(views: tuple) -> dict[str, tuple[int, int]]:
    counts: dict[str, list[int]] = {}   # name -> [dark_n, eligible_n]
    for v in views:
        for s in v.factor_scores:
            if s.reason == _PROFILE_INELIGIBLE:
                continue   # structurally not applicable — excluded entirely (spec §7)
            bucket = counts.setdefault(s.name, [0, 0])
            bucket[1] += 1
            if not s.eligible:
                bucket[0] += 1
    return {name: (dark, elig) for name, (dark, elig) in counts.items()}


def _gated_count(gates: dict) -> int:
    return sum(1 for g in gates.values() if g.suppressed)


def _stale_count(panel_rows: tuple, *, stale_eval_days: int, today: str) -> int:
    """PURE — `today` is REQUIRED (threaded/derived at the call site); NO
    datetime.now() fallback anywhere in render code (spec §2 render purity,
    Global Constraints). Unparseable `today` -> 0 (cannot age-compare)."""
    try:
        _today = date.fromisoformat(today)
    except (ValueError, TypeError):
        return 0
    n = 0
    for row in panel_rows:
        try:
            ran_at = datetime.fromisoformat(row.ran_at)
        except (ValueError, TypeError):
            continue
        # >= : same 10-day boundary as the panel amber cue — spec §11 is
        # authoritative ("10-day boundary (9 green, 10 amber)") over §7/§8's
        # looser ">10d" prose; same reconciliation as Step 6.20.
        if (_today - ran_at.date()).days >= stale_eval_days:
            n += 1
    return n


def compute_data_health(
    views: tuple, gates: dict, panel_rows: tuple, *, stale_eval_days: int,
    today: str, predictive_stale: bool = False,
) -> DataHealthCounts:
    """PURE: dark-factor fractions (profile_ineligible excluded from BOTH
    numerator and denominator), gated-fund count, stale-eval count = suite
    panel rows aged >= stale_eval_days PLUS the stale predictive-artifact
    component (spec §7: '过期评估 K (suite stamps aging + stale predictive
    artifact)' — PredictivePanelModel.stale is computed at the edge and passed
    in as a bool). `today` is REQUIRED — no clock read in render code."""
    return DataHealthCounts(
        dark_factor_fractions=_dark_fractions(views),
        gated_fund_count=_gated_count(gates),
        stale_eval_count=(
            _stale_count(panel_rows, stale_eval_days=stale_eval_days, today=today)
            + (1 if predictive_stale else 0)
        ),
    )
