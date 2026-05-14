from __future__ import annotations


_REQUIRED_CARD_FIELDS: tuple[str, ...] = (
    "instrument_id", "name_cn", "asset_class", "theme", "role",
    "lookthrough_target", "entry_reason", "valuation_state", "heat_state",
    "thesis_state", "product_quality_state", "opportunity_state",
    "dca_action", "risk_action", "falsification_triggers", "trim_triggers",
    "do_not_sell_just_because", "review_cadence", "evidence_gaps",
)

_LEGAL_DCA: frozenset[str] = frozenset(
    {"accelerate_dca", "normal_dca", "slow_dca", "pause_dca", "do_not_buy"}
)
_LEGAL_RISK: frozenset[str] = frozenset(
    {"none", "review_required", "trim_review", "exit_review"}
)


def thesis_card_required_field_completeness(cards: list[dict]) -> float:
    if not cards:
        return 1.0
    ratios: list[float] = []
    for c in cards:
        present = sum(1 for k in _REQUIRED_CARD_FIELDS if k in c and c[k] is not None and c[k] != "")
        ratios.append(present / len(_REQUIRED_CARD_FIELDS))
    return sum(ratios) / len(ratios)


def opportunity_evidence_gap_visibility(rows: list[dict]) -> float:
    insufficient_states = {"evidence_insufficient"}
    relevant: list[dict] = [
        r for r in rows
        if any(
            r.get(field) in insufficient_states
            for field in ("valuation_state", "heat_state", "thesis_state", "product_quality_state")
        )
    ]
    if not relevant:
        return 1.0
    visible = sum(1 for r in relevant if r.get("evidence_gaps"))
    return visible / len(relevant)


def same_theme_distinct_index_limit(rows: list[dict]) -> float:
    """1.0 if every theme has <=2 distinct lookthrough_key entries."""
    by_theme: dict[str, set[str]] = {}
    for r in rows:
        theme = r.get("theme") or "_unthemed"
        key = r.get("lookthrough_key") or r.get("lookthrough_target") or ""
        by_theme.setdefault(theme, set()).add(key)
    if not by_theme:
        return 1.0
    ok = sum(1 for keys in by_theme.values() if len(keys) <= 2)
    return ok / len(by_theme)


def drawdown_not_auto_sell(markdown: str, cards: list[dict]) -> float:
    """Full score requires BOTH:
       - Markdown contains the section header,
       - Every card lists `drawdown_since_entry >= 0.20` under do_not_sell_just_because.
    """
    parts: list[float] = []
    parts.append(1.0 if "## \u5173\u4e8e\u56de\u64a4\u7684\u8bf4\u660e" in markdown else 0.0)
    if cards:
        ok = sum(
            1 for c in cards
            if any("0.20" in t for t in c.get("do_not_sell_just_because", []))
        )
        parts.append(ok / len(cards))
    else:
        parts.append(1.0)
    return sum(parts) / len(parts)


def hot_chase_prevention(rows: list[dict]) -> float:
    """A row is hot-chasing if heat is crowded/overheated AND opportunity_state
    puts it in a buy bucket (core_dca or small_watch)."""
    if not rows:
        return 1.0
    hot_states = {"crowded", "overheated"}
    buy_buckets = {"core_dca", "small_watch"}
    bad = sum(
        1 for r in rows
        if r.get("heat_state") in hot_states
        and r.get("opportunity_state") in buy_buckets
    )
    return (len(rows) - bad) / len(rows)


def valid_action_enums(cards: list[dict]) -> float:
    if not cards:
        return 1.0
    ok = sum(
        1 for c in cards
        if c.get("dca_action") in _LEGAL_DCA and c.get("risk_action") in _LEGAL_RISK
    )
    return ok / len(cards)


def no_external_worktree_path(source: str) -> float:
    return 0.0 if "investment-research-copilot.worktrees" in source else 1.0
