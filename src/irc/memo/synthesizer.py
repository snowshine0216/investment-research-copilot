from __future__ import annotations
from irc.llm._types import ResolvedRoute
from irc.llm.http_client import call_chat, ChatResponse


_SYSTEM = (
    "你是一位专业投资研究员，负责撰写简洁、准确、基于数据的投资决策备忘录。"
    "以中文书写，风格专业简洁，避免套话。"
)


# Glossary prepended to the synthesizer user prompt. Calls out the one
# semantic collision that produced the 2026-05-18 audit finding: the
# ``状态=A/B/C/D`` token and the ``cost_grade`` number look like they both
# measure "valuation", but they are independent axes.
_GLOSSARY = (
    "字段说明（务必遵守，不要混用）：\n"
    "- 状态=A/B/C/D：分别是估值百分位分桶（A）、热度（B）、长期逻辑（C）、产品质量（D）。"
    "其中估值分桶 A ∈ {cheap, reasonable_low, fair, expensive, very_expensive, evidence_insufficient}。\n"
    "- cost_grade：0-100 的持有成本评分（费率 + 折溢价），数值越高表示成本越友好（费率越低）。\n"
    "  cost_grade 与 状态 中的估值分桶是两个独立维度——cost_grade=85 不等于估值高，"
    "也不等于估值低。回避把 cost_grade 解读为「估值贵」或「估值便宜」，必须分别引用 状态 与 cost_grade。\n"
    "- risk / quality / macro_fit / thesis_news：均为 0-100 评分，按各自字面意义解读。"
)


# Hard guardrails added 2026-05-20 in response to audit P2 / P3 / P6:
# - P2: '对金价短期不利' was an unsupported directional prediction.
# - P3: '估值处于历史中位附近' and '偏高位置' were fabricated specifics
#       co-existing in one paragraph with no data backing.
# - P6: '敞口可接受' was claimed in §4 while §6 said the underlying
#       QDII premium/discount data was never collected.
# Rules 8-10 added 2026-05-25 in response to the citation-gate halts:
# - LLM produced a multi-ETF summary paragraph with zero [ref:...] markers
#   ("证据池中五只黄金 ETF（518880、159937、159934、518800、518850）..." → 5×
#   `uncited_conclusion` findings, blocking publication).
# - LLM keeps paraphrasing TL;DR portfolio summaries with action keywords
#   ('暂停加仓', '减速定投') in novel phrasings the audit exemption list
#   doesn't recognize → `uncited_portfolio_conclusion`.
# The synthesizer must read these rules before drafting any section.
_GUARDRAILS = (
    "撰写规则（硬性约束，违反将被审核拒绝）：\n"
    "1. 禁止对未来价格走势做方向性预测。不得使用'对…不利'、'对…有利'、'即将上涨/下跌'、"
    "'短期承压'、'回撤风险尚未释放'等暗示未来方向的措辞；如需引用历史规律，须使用"
    "'根据历史经验'前缀并附'不构成对未来走势的预测'免责说明。\n"
    "2. 数据缺失必须显式声明，禁止自行推断或编造具体数值。若证据池未提供某一字段"
    "（如 A 股估值百分位、QDII 溢价/折价），必须在该处显式标注'本期数据缺失，待补充'，"
    "而非给出'中位附近'、'偏高位置'这类无数据支撑的定性结论。\n"
    "3. QDII 溢价/折价数据缺失时，禁止在第 4 节或任何处给出'敞口可接受'或'敞口不可接受'"
    "的结论；正确表述：'本期 QDII 溢价/折价数据未采集，敞口是否可接受暂无法确认，"
    "须在交易前查阅二级市场溢价后方可执行。'\n"
    "4. 同一段落内的估值描述必须自洽：不得既说'中位附近'又说'偏高位置'。\n"
    "5. 单独呈现个股或底层持仓的正面逻辑时，必须同段或相邻句对等披露该标的的负面信号，"
    "尤其是 very_expensive、overheated、weak 等状态；正面逻辑不得写成加仓依据。"
    "遇到 revenue_yoy 原始小数值时，不得主动换算为百分比/百分数；如必须提及，只能写"
    "'revenue_yoy=原始字段值（具体含义及换算口径待核实，不得直接引用为业绩依据）'。\n"
    "6. 凡是对具体标的、基金代码、ETF、底层持仓或组合权重作出状态/行动/风险结论，"
    "必须在同一段或同一行放入对应证据的 [ref:...] 标记；不要把多个标的混在同一段里共用引用。\n"
    "7. 所有 target_weight/目标权重 均必须写作'权重上限'或'上限约束'，非强制建仓目标；"
    "条件性定投/减速定投在触发条件未满足时实际执行量为零。\n"
    "8. 多个标的（如多只黄金 ETF、多只宽基 ETF）必须按「每只一行 bullet」展开，"
    "每行 bullet 末尾放入该标的对应的 [ref:...] 标记。**禁止**写成"
    "'证据池中 N 只 X（A、B、C、D、E）状态均为...' 这类**无 [ref:...] 标记**的"
    "聚合段落——这会触发每个标的的 `uncited_conclusion`。\n"
    "正确示例（黄金 ETF 段落）：\n"
    "  - 518880 黄金ETF华安：状态=expensive/normal/intact/strong，"
    "opportunity=pause_wait [ref:abc1234567890def]\n"
    "  - 159937 黄金ETF博时：状态=expensive/normal/intact/strong，"
    "opportunity=pause_wait [ref:def0987654321abc]\n"
    "9. TL;DR（第 1 节）的组合层结论涉及 core_dca/small_watch/pause_wait 桶计数或"
    "条件性减速定投执行模式时，**必须**使用以下任一固定措辞（已通过审核白名单），"
    "不要自创新表达：\n"
    "  - '所有可执行标的均为条件性减速定投（触发条件未满足时实际执行量为零）'\n"
    "  - '本期无核心定投候选，建仓节奏以小仓位观察为主'\n"
    "  - '执行行均为条件性减速定投或暂缓执行，触发条件未达成时实际执行量为零'\n"
    "  - '估值或热度高于阈值时暂停加仓'\n"
    "  - '本期黄金 ETF 全部暂停加仓'\n"
    "  - '条件性减速定投在第 7 节触发条件未满足时实际执行量为零'\n"
    "  禁止使用'暂不主动加仓'、'本期无主动加仓信号'、'5 个标的列入...暂停加仓'"
    "这类需要审核员逐一新增白名单的变体。\n"
    "10. 任何提及具体基金代码（≥4 位数字 ID）的段落都必须以 [ref:...] 结尾，"
    "即便是「描述性」表述（如「状态分布」「估值分桶」）。规则 6 的同段引用要求"
    "适用于一切提及标的代码的段落，不区分章节。"
)


def _sanitize_ref(ref: str) -> str:
    """Strip control characters to prevent prompt injection from external data sources."""
    return ref.replace("\n", " ").replace("\r", " ").strip()[:400]


def synthesize_memo(skeleton: str, raw_ref_pool: list[str], route: ResolvedRoute) -> ChatResponse:
    refs_block = "\n".join(f"- {_sanitize_ref(r)}" for r in raw_ref_pool[:40])
    # When section 7 was prefilled deterministically (marker present), tell
    # the LLM to copy that section verbatim. Otherwise leave today's
    # behavior unchanged — the LLM still fills the placeholder.
    section7_instruction = ""
    if "<!-- IRC_EXECUTION_LINES_BEGIN -->" in skeleton:
        section7_instruction = (
            "第7节『执行要点』的内容已由系统生成（位于 IRC_EXECUTION_LINES_BEGIN/END "
            "标记之间），必须**原样保留**这两个 HTML 注释之间的所有 bullet，"
            "不要改写、合并或扩写其中的任何条目。"
        )
    user_msg = (
        f"{_GLOSSARY}\n\n"
        f"{_GUARDRAILS}\n\n"
        f"以下是备忘录骨架：\n\n{skeleton}\n\n"
        f"以下是相关原始数据摘录（请结合数据充实各章节，勿发明数据）：\n{refs_block}\n\n"
        f"{section7_instruction}\n\n"
        "请按骨架章节结构输出完整备忘录。"
    )
    return call_chat(
        route=route,
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": user_msg}],
        temperature=0.3,
    )
