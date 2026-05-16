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


def _section(n: int, title: str, body: str) -> str:
    return f"## {n}. {title}\n\n{body}\n"


def render_skeleton(inputs: MemoInputs) -> str:
    picks_section = inputs.picks_table_md.strip() or (
        "\n".join(f"- {p}" for p in inputs.top_picks) or "（待填写）"
    )
    risks_md = "\n".join(f"- {r}" for r in inputs.risk_notes) or "（待填写）"
    tldr_md = "\n".join(f"- {t}" for t in inputs.tldr_lines) or "（待填写）"
    sections = [
        f"# 投资决策备忘录 {inputs.date_str}\n",
        _section(1, "TL;DR", tldr_md),
        _section(2, "宏观环境", inputs.macro_summary),
        _section(3, "黄金视角",
                 f"- 市场形态：{inputs.gold_regime}\n"
                 f"- 价格区间：{inputs.gold_zone}\n"
                 f"- 仓位倾斜：{inputs.gold_tilt}"),
        _section(4, "资产配置", f"- 建仓模式：{inputs.allocation_mode}"),
        _section(5, "精选标的", picks_section),
        _section(6, "风险提示", risks_md),
        _section(7, "执行要点", "<!-- 由AI合成器填充 -->"),
    ]
    return "\n".join(sections)
