"""PURE: RotationReport → md + json projections (spec §5, D8).

json = source of truth (schema_version 1, radar_version 1, byte-stable sorted
keys). md = display-only additive subset, NO [ref:] markers (pure market data,
outside citation/SAME-3/H3 machinery — AC8). No I/O.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from irc.rotation.types import RotationReport

SCHEMA_VERSION = 1
RADAR_VERSION = 1  # bump ONLY on weight/window/hysteresis change (monitor lesson)


def to_json(report: RotationReport) -> str:
    """Pure: byte-stable sorted-key JSON (the source of truth)."""
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def _state_line(bs) -> str:
    chase = " ⚠追高" if bs.chase_risk else ""
    pe = f"{bs.pe_pctl:.2f}" if bs.pe_pctl is not None else "N/A"
    return (f"| {bs.board_code} | {bs.board_name} | {bs.state} | "
            f"{bs.days_in_state} | {bs.composite_pctl:.2f} | {pe} |{chase}")


def _cand_line(c) -> str:
    tags = []
    if c.on_discovered_watchlist:
        tags.append("watchlist")
    if c.in_monitor_set:
        tags.append("monitor")
    if c.held:
        tags.append("held")
    surface = ",".join(tags) or "新"
    return (f"| {c.fund_id} | {c.name_cn} | {c.board_name} | "
            f"{c.exposure_pct:.1f}% | {surface} | {c.holdings_as_of or 'N/A'} |")


def _diag_value_str(value) -> str:
    """Pure: render one diagnostics value human-readably (counts + list contents)."""
    if isinstance(value, (list, tuple)):
        return f"{len(value)}" + (f"（{', '.join(str(v) for v in value)}）" if value else "")
    if isinstance(value, dict):
        return "; ".join(f"{k}={_diag_value_str(v)}" for k, v in sorted(value.items()))
    return str(value)


def _diag_line(key: str, value) -> str:
    return f"- {key}: {_diag_value_str(value)}"


def _diagnostics_section(diagnostics: dict) -> list[str]:
    """Pure: render every diagnostics field (AC8 — json is additive source of
    truth, md suppresses nothing). Sorted by key for byte-stability (AC3)."""
    if not diagnostics:
        return []
    return ["", "## 诊断"] + [_diag_line(k, diagnostics[k]) for k in sorted(diagnostics)]


def to_md(report: RotationReport) -> str:
    """Pure: display markdown (additive subset; NO [ref:] markers — AC8)."""
    lines = [f"# 板块轮动雷达 (data_status: {report.data_status})", ""]
    if report.data_status == "abstain":
        lines.append(f"雷达今日弃权：{report.diagnostics.get('failure', '未知')}")
        return "\n".join(lines) + "\n"
    lines += ["## 板块状态", "| 板块 | 名称 | 状态 | 天数 | 分位 | PE分位 |",
              "|---|---|---|---|---|---|"]
    lines += [_state_line(b) for b in report.board_states
              if b.state != "quiet"]
    lines += ["", "## 轮动候选基金", "| 基金 | 名称 | 板块 | 敞口 | 现有面 | 持仓季度 |",
              "|---|---|---|---|---|---|"]
    lines += [_cand_line(c) for c in report.candidates]
    lines += _diagnostics_section(report.diagnostics)
    return "\n".join(lines) + "\n"


def abstain_report(reason: str) -> RotationReport:
    """Pure: the total-failure abstain stub (§7, AC5)."""
    return RotationReport(schema_version=SCHEMA_VERSION, radar_version=RADAR_VERSION,
                          data_status="abstain", board_states=(), candidates=(),
                          diagnostics={"failure": reason})


def cold_holdings_note() -> str:
    """Pure: the single actionable line when the holdings cache is cold (§7)."""
    return "持仓缓存为空：先运行 `uv run irc rotation seed` 以填充持仓+行业映射。"
