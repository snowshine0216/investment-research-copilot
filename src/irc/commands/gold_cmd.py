from __future__ import annotations
from datetime import datetime, timezone, timedelta
from dataclasses import asdict
from pathlib import Path
import json
import re as _re
import yaml
import pandas as pd
from dataclasses import asdict as _dc_asdict
from irc.config_loader import load_repo_configs
from irc.data.freshness import require_fresh_ingest
from irc.data.duckdb_helper import connect, ensure_schema
from irc.data.wgc_ingest import cb_purchases_yearly_tons, etf_holdings_30d_change_tons
from irc.io_utils import atomic_write_text
from irc.memo.macro_pillar import (
    MacroSnapshot,
    ThemeReportRef,
    build_macro_evidence,
)
from irc.research.persistence import extract_prose_from_report_md, load_theme_reports
from irc.research.geopolitical_stress import geopolitical_stress_from_theme_report
from irc.research.theme_research import ThemeReport
from irc.scoring.regime_detect import classify_regime
from irc.scoring.gold_band import compute_band, classify_zone
from irc.scoring.gold_scenarios import classify_scenario
from irc.scoring.gold_score import (
    compute_gold_score,
    GoldDriverInputs,
    GoldTilt,
    gold_tilt_from_score,
)


# Tilt magnitude ordering for the regime-vs-drivers clamp.
_TILT_ORDER: tuple[GoldTilt, ...] = (
    "underweight", "neutral_minus", "neutral", "neutral_plus", "overweight",
)


# F5: paragraph-accumulator constants (per ADR 0008).
#
# `_BOLD_ONLY_RE` matches lines whose stripped form is ENTIRELY wrapped in
# `**...**` with NO trailing prose. Pure bold subheadings (e.g.
# `**1. Bond Market Pressure...**`) skip; bold + trailing prose (e.g.
# `**政策优化信号**：本周国常会…`) DOES NOT skip — the trailing colon and
# prose disqualifies the fullmatch. Same shape for underscore-bold.
_BOLD_ONLY_RE = _re.compile(r"\*\*[^*]+\*\*")
_UNDERSCORE_BOLD_RE = _re.compile(r"__[^_]+__")

# Sentence terminators counted toward the ≥3-terminator stop rule.
_SENTENCE_TERMINATORS: frozenset[str] = frozenset({".", "。", "！", "!", "?", "？"})

# Paragraph accumulator stop thresholds (per ADR 0008 §1).
_PARAGRAPH_CHAR_FLOOR: int = 150
_PARAGRAPH_TERMINATOR_FLOOR: int = 3


def _combine_tilts(
    regime: str,
    drivers_tilt: GoldTilt,
    drivers_availability: str,
) -> GoldTilt:
    """Combine the regime-only tilt and the driver-score tilt.

    Adversarial review §B2: drivers_tilt should drive the decision when
    data is complete. When the regime contradicts the drivers (e.g.
    drivers say overweight but the price is trending down), clamp to
    neutral_plus so we never aggressively buy into a downtrend.
    """
    if drivers_availability == "unavailable":
        return "neutral"  # honest fallback — no driver signal
    if drivers_availability == "partial":
        # Be conservative: take the more cautious of regime-neutral vs drivers.
        idx = _TILT_ORDER.index(drivers_tilt)
        cautious_idx = min(idx, _TILT_ORDER.index("neutral_plus"))
        return _TILT_ORDER[cautious_idx]
    # complete: drivers dominate; clamp on trending_down + overweight
    if regime == "trending_down" and drivers_tilt == "overweight":
        return "neutral_plus"
    return drivers_tilt


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _gold_prices(con, instrument_id: str) -> pd.Series:
    df = con.execute(
        "SELECT date, close FROM prices WHERE instrument_id = ? ORDER BY date",
        [instrument_id],
    ).fetch_df()
    return df["close"]


def _macro_value_or_none(con, series: str) -> float | None:
    row = con.execute(
        "SELECT value FROM macro_series WHERE series_id = ? ORDER BY date DESC LIMIT 1",
        [series],
    ).fetchone()
    return float(row[0]) if row else None


def _macro_value(con, series: str, default: float) -> float:
    value = _macro_value_or_none(con, series)
    return value if value is not None else default


def _real_yield_10y_tips(con) -> float:
    value = _macro_value_or_none(con, "real_yield_10y_tips")
    if value is not None:
        return value
    return _macro_value(con, "DGS10", 1.65) - 2.30


_MACRO_DISPLAY_NAMES: dict[str, tuple[str, str]] = {
    # series_id → (display_name, unit)
    "real_yield_10y_tips": ("美国10Y TIPS 实际利率", "%"),
    "DXY":                 ("美元指数 DXY", ""),
    "vix":                 ("VIX 波动率指数", ""),
    "inflation_5y5y":      ("5Y5Y 通胀预期", "%"),
    "DGS10":               ("美国10Y 国债收益率", "%"),
}


_THEME_DISPLAY_NAMES: dict[str, str] = {
    "us_monetary":               "美国货币政策",
    "us_fiscal_politics":        "美国财政与政治",
    "cn_monetary":               "中国货币政策",
    "cn_equity_property_policy": "中国股市与地产政策",
    "geopolitics":               "地缘政治",
    "gold_drivers":              "黄金驱动因素",
    "holdings_sector":           "持仓行业要闻",
}


def _load_macro_snapshots(con) -> tuple[MacroSnapshot, ...]:
    """Pull the latest value + date for each interesting macro series.

    Series missing from the table are skipped silently (returns no snapshot
    for that series) — the renderer falls back to its anti-fabrication
    paragraph when EVERY snapshot is missing.
    """
    out: list[MacroSnapshot] = []
    for series_id, (display, unit) in _MACRO_DISPLAY_NAMES.items():
        row = con.execute(
            "SELECT value, date FROM macro_series "
            "WHERE series_id = ? ORDER BY date DESC LIMIT 1",
            [series_id],
        ).fetchone()
        if not row:
            continue
        value, date_val = row
        if value is None or date_val is None:
            continue
        out.append(MacroSnapshot(
            series_id=series_id,
            display_name=display,
            value=float(value),
            unit=unit,
            date=str(date_val),
        ))
    return tuple(out)


def _is_skip_line(stripped: str, *, buffer_has_prose: bool) -> bool:
    """Return True if this stripped line should be skipped during the
    paragraph extraction. See ADR 0008 §1 "Skip rule".

    - `##`-prefixed lines (markdown subheading at any depth) ALWAYS skip.
    - Pure bold-only lines (`**foo**` / `__foo__`) ALWAYS skip.
    - Empty lines skip only when no prose line is in the buffer yet;
      they terminate accumulation (not skipped) once buffer is non-empty.
    """
    if not stripped:
        return not buffer_has_prose
    if stripped.startswith("##"):
        return True
    if _BOLD_ONLY_RE.fullmatch(stripped):
        return True
    if _UNDERSCORE_BOLD_RE.fullmatch(stripped):
        return True
    return False


def _strip_bullet_marker(stripped: str) -> str:
    """Strip a leading `- `, `* `, or `+ ` bullet marker. Per grill Q10
    this runs on EVERY accepted accumulator line so bullet-list reports
    (e.g. geopolitics) reach the 150-char floor with content not markers."""
    if stripped.startswith(("- ", "* ", "+ ")):
        return stripped[2:].lstrip()
    return stripped


def _truncate_at_cap(text: str, *, max_chars: int) -> str:
    """If `text` exceeds `max_chars`, truncate to `max_chars - 1` visible
    chars and append a single `…` (horizontal-ellipsis). Otherwise return
    `text` unchanged. Per ADR 0008 §2."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _first_prose_paragraph(prose: str, *, max_chars: int) -> str:
    """Extract the first prose paragraph from a stripped theme-report body.

    Algorithm (locked by ADR 0008 §1):
      1. Walk lines top-to-bottom.
      2. For each stripped line, apply `_is_skip_line`; skipped lines do
         not enter the buffer.
      3. Once a non-skip prose line is found, strip its bullet marker and
         append to the buffer.
      4. Continue accumulating non-skip lines (bullets stripped) until any
         terminator fires:
         (i)  buffer's sentence-terminator count ≥ `_PARAGRAPH_TERMINATOR_FLOOR`
         (ii) buffer's len ≥ `_PARAGRAPH_CHAR_FLOOR`
         (iii) a blank line is encountered AFTER ≥1 prose line is in the buffer
      5. Truncate at `max_chars` with `…` suffix per `_truncate_at_cap`.
      6. Return the buffer joined by single ASCII space. If no prose line
         was ever found, return the empty string (caller maps to the
         `（报告为空）` sentinel).

    Pure function — no I/O.
    """
    buffer: list[str] = []
    char_count = 0
    terminator_count = 0
    for line in prose.splitlines():
        stripped = line.strip()
        if _is_skip_line(stripped, buffer_has_prose=bool(buffer)):
            continue
        if not stripped:
            # Blank line + buffer has prose → terminate.
            break
        accepted = _strip_bullet_marker(stripped)
        if not accepted:
            # Bullet marker stripped down to empty — treat as skip.
            continue
        buffer.append(accepted)
        char_count += len(accepted) + (1 if len(buffer) > 1 else 0)
        terminator_count += sum(1 for ch in accepted if ch in _SENTENCE_TERMINATORS)
        if terminator_count >= _PARAGRAPH_TERMINATOR_FLOOR:
            break
        if char_count >= _PARAGRAPH_CHAR_FLOOR:
            break
    if not buffer:
        return ""
    joined = " ".join(buffer)
    return _truncate_at_cap(joined, max_chars=max_chars)


def _summary_from_theme_report(report: ThemeReport, *, max_chars: int = 400) -> str:
    """Extract a paragraph-shaped summary from a ThemeReport.

    Per ADR 0008: skip-rule + paragraph accumulator. Default `max_chars`
    raised to 400 (was 220) so paragraph-shaped excerpts have room. The
    kwarg is preserved as a test override.

    Returns the failure_reason verbatim when the report failed; returns
    the legacy `（報告为空）` sentinel when no prose line is found.
    """
    if report.failure_reason:
        return f"研究采集失败：{report.failure_reason}"
    prose = extract_prose_from_report_md(report.report_md or "")
    paragraph = _first_prose_paragraph(prose, max_chars=max_chars)
    if not paragraph:
        return "（报告为空）"
    return paragraph


def _evidence_to_dict(ev) -> dict:
    """Serialise a `ThesisEvidence` to the same JSON shape used in
    `opportunity_report.json["rows"][*]["thesis_evidence"]` so the
    publishable-universe loader (`from_dict`) can round-trip it."""
    return {
        "type": ev.type,
        "source": ev.source,
        "url": ev.url,
        "date": ev.date,
        "summary": ev.summary,
        "scope": ev.scope,
        "citation_kind": ev.citation_kind,
        "owner_instrument_id": ev.owner_instrument_id,
        "parent_fund_id": ev.parent_fund_id,
        "constituent_key": ev.constituent_key,
        "citation_id": ev.citation_id,
        "holding_weight_pct": ev.holding_weight_pct,
    }


def _build_theme_refs(
    reports: dict[str, ThemeReport],
    *,
    today: str,
) -> tuple[ThemeReportRef, ...]:
    """Order theme refs by a stable preference list so reruns are byte-identical."""
    order = (
        "us_monetary", "cn_monetary", "geopolitics",
        "us_fiscal_politics", "cn_equity_property_policy",
        "gold_drivers", "holdings_sector",
    )
    out: list[ThemeReportRef] = []
    for theme in order:
        report = reports.get(theme)
        if report is None:
            continue
        out.append(ThemeReportRef(
            theme=theme,
            display_name=_THEME_DISPLAY_NAMES.get(theme, theme),
            summary=_summary_from_theme_report(report),
            date=today,
        ))
    return tuple(out)


def run_gold(repo_root: str) -> int:
    root = Path(repo_root)
    if not require_fresh_ingest(root, stage="gold"):
        print("ERROR: gold stage halted — ingest is stale. "
              "See outputs/<today>/STALE_INGEST.md or set IRC_ALLOW_STALE=1.")
        return 1
    bundle = load_repo_configs(root)
    cfg = bundle.gold_drivers
    exchange_gold = [i for i in bundle.universe_gold.instruments if i.market != "cmb_internal"]
    if not exchange_gold:
        print("WARN: no exchange-traded gold instrument in universe/gold.yaml")
        return 1
    gold_id = exchange_gold[0].instrument_id
    con = connect(root / "data" / "local.duckdb")
    try:
        ensure_schema(con)
        prices = _gold_prices(con, gold_id)
        if prices.empty:
            print("WARN: no gold prices in DuckDB; run `irc ingest` first.")
            return 1
        regime = classify_regime(
            prices,
            vol_ratio_threshold=cfg.regime_detection.vol_ratio_range_threshold,
            adx_threshold=cfg.regime_detection.adx_range_threshold,
            window_recent_days=cfg.regime_detection.vol_window_months * 30,
            window_baseline_days=cfg.regime_detection.vol_baseline_window_months * 30,
        )
        band = compute_band(prices, window_months=cfg.band.rolling_window_months)
        current_price = float(prices.iloc[-1])
        zone = classify_zone(current_price, band)
        today = _today()
        wgc = root / "data" / "wgc"
        cb_tons = cb_purchases_yearly_tons(wgc / "cb_purchases.csv", as_of_year=int(today[:4]))
        etf_change = etf_holdings_30d_change_tons(wgc / "etf_holdings.csv", as_of=today)
        reports = load_theme_reports(root)
        # Use the "geopolitics" theme report — geopolitical risk is computed
        # from the dedicated geopolitics research (not the gold theme report).
        # This intentionally deviates from 010-spec.md which referenced "gold";
        # the geopolitics report is the semantically correct source for this signal.
        geo_stress = geopolitical_stress_from_theme_report(
            reports.get("geopolitics"),
        )
        # Track which drivers are real vs fallback so the gold report
        # can honestly say "drivers_availability=partial" when WGC data
        # is missing. Adversarial review §B2.
        unavailable_drivers: list[str] = []
        if cb_tons == 0.0:
            unavailable_drivers.append("cb_purchases_wgc")
        if etf_change == 0.0:
            unavailable_drivers.append("etf_holdings_gld")
        inputs = GoldDriverInputs(
            real_yield_10y_tips=_real_yield_10y_tips(con),
            dxy=_macro_value(con, "DXY", 104.0),
            inflation_5y5y=_macro_value(con, "inflation_5y5y", 2.30),
            cb_purchases_yearly_tons=cb_tons,
            etf_holdings_30d_change_tons=etf_change,
            geopolitical_stress_0to1=geo_stress,
        )
        if unavailable_drivers:
            print(
                "WARN: gold driver(s) using stub value; "
                f"WGC CSV absent for {', '.join(unavailable_drivers)} → 0.0 fallback"
            )
        drivers_score = compute_gold_score(inputs, cfg)
        drivers_tilt = gold_tilt_from_score(drivers_score)
        # 2 or more unavailable → "unavailable"; 1 → "partial"; 0 → "complete"
        if len(unavailable_drivers) >= 2:
            drivers_availability = "unavailable"
        elif unavailable_drivers:
            drivers_availability = "partial"
        else:
            drivers_availability = "complete"
        tilt = _combine_tilts(regime.regime, drivers_tilt, drivers_availability)
        scenario = classify_scenario(
            real_yield=inputs.real_yield_10y_tips, dxy=inputs.dxy,
            cb_purchases_yearly_tons=inputs.cb_purchases_yearly_tons,
            geopolitical_stress=inputs.geopolitical_stress_0to1,
        )
        macro_snapshots = _load_macro_snapshots(con)
    finally:
        con.close()
    # Macro/theme evidence — these citation_ids enter the publishable
    # universe via `gold_regime.json["evidence"]` (see
    # `tests/integration/_publishable_set_helper.py`). memo §2 / §3 pick
    # them up by source key.
    theme_refs = _build_theme_refs(reports, today=today)
    macro_evidence = build_macro_evidence(macro_snapshots, theme_refs)
    out_dir = root / "outputs" / _today()
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "gold_regime.json", json.dumps({
        "regime": regime.regime, "vol_ratio": regime.vol_ratio, "adx": regime.adx,
        "trend_sign": regime.trend_sign,
        # Legacy "score" preserved as alias of drivers_score for downstream
        # consumers; new fields are the source of truth.
        "score": drivers_score,
        "drivers_score": drivers_score,
        "drivers_tilt": drivers_tilt,
        "drivers_availability": drivers_availability,
        "drivers_unavailable": unavailable_drivers,
        "tilt": tilt,
        "zone": zone,
        "scenario": scenario.scenario, "scenario_triggers": list(scenario.triggers_met),
        # Macro snapshots (raw data the memo deterministically renders).
        "macro_snapshots": [_dc_asdict(s) for s in macro_snapshots],
        "theme_refs": [_dc_asdict(t) for t in theme_refs],
        # ThesisEvidence list — adds to the publishable citation universe.
        "evidence": [_evidence_to_dict(ev) for ev in macro_evidence],
    }, ensure_ascii=False, indent=2))
    atomic_write_text(out_dir / "gold_band.yaml", yaml.safe_dump(asdict(band), sort_keys=False))
    print(
        f"gold OK: regime={regime.regime} drivers={drivers_score:.1f} "
        f"({drivers_availability}) tilt={tilt}"
    )
    return 0
