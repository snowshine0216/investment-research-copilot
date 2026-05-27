from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoInputs:
    date_str: str
    gold_regime: str
    gold_zone: str
    gold_tilt: str
    allocation_mode: str
    macro_summary: str
    top_picks: tuple[str, ...]
    risk_notes: tuple[str, ...]
    tldr_lines: tuple[str, ...]
    picks_table_md: str = ""
    # One bullet per trade plan row. When non-empty, section 7 renders
    # deterministically and the synthesizer is asked to leave it alone.
    # When empty (dry-run with no trades), section 7 falls back to the
    # legacy placeholder.
    execution_lines: tuple[str, ...] = ()
    # Optional gold-section evidence bullets (real_yield / DXY / theme-
    # report excerpts) rendered after the regime/zone/tilt lines in §3.
    # When non-empty the synthesizer is told to leave them verbatim
    # (matches the §7 lock pattern). When empty, §3 keeps the legacy
    # three-line summary only.
    gold_evidence_md: str = ""


_LEGACY_EXECUTION_PLACEHOLDER = "<!-- 由AI合成器填充 -->"
# Marker the synthesizer prompt can grep for to know it must NOT touch
# this section. See synthesizer.py — when the marker is present, the
# prompt explicitly instructs the LLM to copy the section verbatim.
EXECUTION_SECTION_MARKER = "<!-- IRC_EXECUTION_LINES_BEGIN -->"
EXECUTION_SECTION_MARKER_END = "<!-- IRC_EXECUTION_LINES_END -->"
PICKS_SECTION_MARKER_BEGIN = "<!-- IRC_PICKS_TABLE_BEGIN -->"
PICKS_SECTION_MARKER_END = "<!-- IRC_PICKS_TABLE_END -->"
EVIDENCE_GAP_MARKER_BEGIN = "<!-- IRC_EVIDENCE_GAP_BEGIN -->"
EVIDENCE_GAP_MARKER_END = "<!-- IRC_EVIDENCE_GAP_END -->"
_COMPLIANCE_STATEMENT = (
    "【合规声明】本备忘录所有内容（含宏观判断、标的评分、目标权重、执行触发条件）"
    "均基于内部模型及截至证据池日期的有限数据生成，仅供内部参考，"
    "不构成任何形式的投资建议或收益承诺。投资者须自行承担投资决策风险。"
)
_EXECUTION_PREAMBLE = (
    "触发条件为纪律性执行阈值，反映在价格回落时分批执行的规则；"
    "不构成对标的价格走势的预测或判断。\n"
    "QDII标的执行前须查阅二级市场溢价/折价；溢价过高时暂缓执行。"
)


def _section(n: int, title: str, body: str) -> str:
    return f"## {n}. {title}\n\n{body}\n"


def _render_execution_section(lines: tuple[str, ...]) -> str:
    if not lines:
        return _LEGACY_EXECUTION_PLACEHOLDER
    body = "\n".join(f"- {line}" for line in lines)
    return (
        f"{EXECUTION_SECTION_MARKER}\n{_EXECUTION_PREAMBLE}\n{body}\n"
        f"{EXECUTION_SECTION_MARKER_END}"
    )


def render_skeleton(inputs: MemoInputs) -> str:
    picks_md = inputs.picks_table_md.strip()
    if picks_md:
        # Lock the picks table inside MARKER bullets so the synthesizer
        # keeps it byte-for-byte. The pre-Phase-B run let the LLM rewrite
        # the table and substitute citations (e.g. 159937 cross-borrowing
        # 518880's announcement ref → wrong_instrument_citation finding).
        picks_section = (
            f"{PICKS_SECTION_MARKER_BEGIN}\n{picks_md}\n{PICKS_SECTION_MARKER_END}"
        )
    else:
        picks_section = (
            "\n".join(f"- {p}" for p in inputs.top_picks) or "（待填写）"
        )
    risks_md = "\n".join(f"- {r}" for r in inputs.risk_notes) or "（待填写）"
    tldr_md = "\n".join(f"- {t}" for t in inputs.tldr_lines) or "（待填写）"
    gold_body = (
        f"- 市场形态：{inputs.gold_regime}\n"
        f"- 价格区间：{inputs.gold_zone}\n"
        f"- 仓位倾斜：{inputs.gold_tilt}"
    )
    if inputs.gold_evidence_md.strip():
        gold_body = f"{gold_body}\n\n{inputs.gold_evidence_md}"
    sections = [
        f"# 投资决策备忘录 {inputs.date_str}\n\n{_COMPLIANCE_STATEMENT}\n",
        _section(1, "TL;DR", tldr_md),
        _section(2, "宏观环境", inputs.macro_summary),
        _section(3, "黄金视角", gold_body),
        _section(4, "资产配置", f"- 建仓模式：{inputs.allocation_mode}"),
        _section(5, "精选标的（含观察标的）", picks_section),
        _section(6, "风险提示", risks_md),
        _section(7, "执行要点", _render_execution_section(inputs.execution_lines)),
    ]
    return "\n".join(sections)
