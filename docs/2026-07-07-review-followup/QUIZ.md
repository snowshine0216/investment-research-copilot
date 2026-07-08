# Run quiz — review-followup (2026-07-07)

Non-blocking comprehension gate. Answers at the bottom. 每题中英双语；答案见文末。

**Q1.** The rotation candidates join was dead for the radar's entire life, yet every test was green. What exactly masked it, and what rule now prevents the recurrence?
轮动候选 join 从上线起就是死的，但所有测试都是绿的。到底是什么掩盖了它？现在哪条新规则防止复发？

**Q2.** After item 005, when does a stale (>30d) stock→行业 mapping actually get healed — on the next daily `irc rotation` run, or only on something else? Why does that distinction matter for the ~2026-08-05 cliff?
005 之后，>30 天的股票→行业映射什么时候才会真正被修复——每日 `irc rotation` 会修吗？这个区别对 ~2026-08-05 的"悬崖日"意味着什么？

**Q3.** The data-health digest can be "more honest than the report" until M-1 lands. Give the concrete example shipped in this run (which factor, which symbol class), and name the one 15:45 failure mode that pages `degraded` even when the wrapper exits 0.
在 M-1 落地前，数据健康摘要可能"比报告更诚实"。举出本次交付的具体例子（哪个因子、哪类症状），并说出哪种 15:45 失败即使 wrapper 退出码为 0 也会以 `degraded` 呼叫。

**Q4.** Item 002's version-grep guard originally asserted each version number in only ONE doc surface. Why was that a false-pass risk, and what's the rule now?
002 的版本 grep 守卫最初每个版本号只断言一个文档面。为什么那是假通过风险？现在的规则是什么？

**Q5.** The new "production-shaped test data" convention exempts one category of hand-built test data. Which, and why would banning it have destroyed coverage this very run added?
新的"生产形状测试数据"约定豁免了一类手工构造的测试数据。是哪一类？为什么禁止它反而会摧毁本次运行自己新增的覆盖？

---

## Answer key · 答案

**A1.** A hand-crafted `"BK1"`-in-the-industry-slot fixture stood in for the store's *normal* shape, so tests never saw the real 行业-name shape; the join filtered names against BK codes → always 0 candidates, silently. New CLAUDE.md convention: normal-shape stand-ins must be committed snapshots copied/reduced from real artifacts (any test tier — not the `-m integration` marker); deliberately-adversarial data is exempt but visibly synthetic.
掩盖者是手工造的 `"BK1"` 放在 industry 槽里，冒充商店的**正常形状**；测试从未见过真实的行业名形状。新约定：正常形状的测试数据必须是从真实工件复制/裁剪的已提交快照。

**A2.** Only on a **seed run** (`irc rotation seed`) — the daily rotation run is read-only on the store (neither ages nor refreshes entries); `seen_at` is written only by the monitor's daily batch (~60 symbols) and by seed. So the ~640 non-monitor mappings all cross the 30-day window ~2026-08-05, and healing requires a re-seed (unpaced burst risk = deferred R-5).
只有 **seed 运行**才会修复——每日运行对商店只读。~640 个非监控映射会在 ~08-05 同时过期，需要重新 seed（未限速的突发风险 = 已登记 R-5）。

**A3.** Flow staleness: symbol 688072's newest flow row is 2026-06-26 (>3 trading days), which the report still renders as fresh (M-1 unbuilt) but the monitor digest names as `1 只滞后>3td`. The rc=0 paging failure mode: a soft capture failure — today's capture appended <80% of the flow store's union symbols — pages `degraded` with `flow-capture: N/M` (the spec-line-89 check Codex found missing from the plan).
资金流滞后：688072 最新行是 06-26，报告仍当"新鲜"渲染，而摘要如实标注滞后。rc=0 仍呼叫的失败模式：软性采集失败（当日覆盖 <80% 联合符号）→ `flow-capture: N/M` 以 `degraded` 呼叫。

**A4.** The single-owner docs still *state* the numbers in multiple surfaces; a future bump could fix the one asserted file and leave the operator manual stale while CI passes. Rule now: every surface that states a version number gets both a current-value-present and stale-value-absent assertion (18 asserts / 8 tests).
单一所有者声明并不阻止其他文档**陈述**数字；只断言一个面时，升级可能只改那一个而让操作手册悄悄过期。现在：每个陈述版本号的面都被双向断言。

**A5.** Deliberately-adversarial test data (mismatches, duplicates, malformed shapes — visibly synthetic). Banning it would have outlawed this run's own regression tests: the dropped-name/duplicate-board warning tests (004/ship round) and the malformed-shape totality tests (001: `funds:"x"`, `macro_snapshots:null`), which exist precisely to prove no-silent-degradation.
故意对抗性的测试数据（错配、重名、畸形形状——显式合成）。禁止它会摧毁本次运行自己新增的回归测试（004 的翻译告警测试、001 的畸形形状全性测试）。
