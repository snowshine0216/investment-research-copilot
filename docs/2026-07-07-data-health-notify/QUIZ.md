# Run quiz — data-health-notify (2026-07-07)

Non-blocking comprehension gate. Answers at the bottom.

**Q1.** AC1's original text said today's monitor notification severity "stays clean", yet the shipped runtime proof records `degraded`. Why is `degraded` the correct outcome, and which locked decision forces it?
**Q1 (中文).** AC1 原文说今天的 monitor 通知严重级"保持 clean"，但实际跑出来是 `degraded`。为什么 `degraded` 才是正确结果？是哪条锁定决策决定的？

**Q2.** At 15:45, what pages when `irc rotation` crashes before writing `rotation_radar.json`, versus when it writes the file with `data_status: "abstain"`? What stays unchanged in both cases?
**Q2 (中文).** 15:45 时，如果 `irc rotation` 在写出 `rotation_radar.json` 之前就崩溃，会推送什么？如果它写出了 `abstain` 的雷达文件呢？两种情况下有什么是不变的？

**Q3.** Why does `degraded` sit ABOVE `action` in the precedence, and why must it be in `_ALWAYS_NOTIFY`?
**Q3 (中文).** 为什么 `degraded` 在优先级里排在 `action` 之上？为什么它必须加入 `_ALWAYS_NOTIFY`？

**Q4.** On a day when the radar recovers (abstain→ok) but a health warning also fires (e.g. flow store has a stale symbol), what notification goes out — the recovery notice or something else?
**Q4 (中文).** 某天雷达恢复了（abstain→ok），但同时又有健康告警（比如 flow store 有滞后股票），最终发出的是恢复通知还是别的？

**Q5.** What was the in-branch P0 the ship review caught, and what general rule does its fix enforce?
**Q5 (中文).** 这次 ship 评审抓到的分支内 P0 是什么？它的修复强制执行了什么通用规则？

---

## Answer key

**A1.** The live flow store has symbol 688072 stale since 06-26 (>3 trading days). Locked G-Q5→B says any store symbol >3td stale is a warn; a warn on an otherwise-clean run escalates to `degraded`. The spec's "stays clean" wording predates the store's current state — the spec's own §3.1 example is this exact case. (板块PE STALE-1 alone would NOT escalate — it is info-only per G-Q6.)
**A2.** Crash-before-write → the notify tail's sentinel check (`today_dir_exists` keyed on `rotation_radar.json`) yields severity `failed` → pages. Abstain radar → health digest warn → `degraded` → pages (exit code is 0 by design, so health is the only surface). Unchanged in both: the wrapper's own `$rc` — the rotation step stays advisory and never alters the wrapper exit code.
**A3.** A buy/sell action derived from degraded data should be tagged by its trust problem first (the action rollup stays in the body). `_ALWAYS_NOTIFY` membership is load-bearing: with `IRC_NOTIFY_ON_CLEAN=0`, a clean-run-with-DARK day would otherwise be silent — recreating exactly the invisibility this feature removes (G-Q2).
**A4.** The `degraded` page fires; the recovery notice is suppressed (recovery is returned only at final severity `clean`). Locked design, pinned by `test_degraded_warn_suppresses_recovery` — the notification still fires truthfully, so recovery visibility is not lost, it is superseded by the more important warning.
**A5.** `_build_flow_capture_health` silently produced NO item when `fund_flow_series.json` was missing/corrupt (`cov=None` → coverage check skipped). Fixed by merging `health_unknown` into the digest (`2e7d473e` + regression test). Rule: spec §3.3 — an unreadable input must surface as `health_unknown`, never as silence; silence and "clean" must never be indistinguishable from a broken read.
