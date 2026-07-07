Verdict: PASS

## Run-level end-to-end verification — review-followup (2026-07-07)

Subagent: sonnet

Source: `autodev/review-followup-feature` @ `cc86ac26` (all 5 items' merge
squashes confirmed present in `git log`: `76359c69` #208 (004), `6dc5d83b` #209
(005), `ecf264f6` #212 (001), `803e0415` #213 (002), `d47388e8` #214 (003)).
`Skill(skill="verify")` was invoked; no project-level `.claude/skills/verify`
existed (only unrelated `ops-verify`/`report-interpret`), so this ran a cold
start per the generic skill's protocol — real CLI subprocess, real on-disk
`data/`/`outputs/`, no mocks except a PATH-shim `osascript` to suppress an
actual macOS notification popup.

### Entry points exercised

- `uv run python <scratchpad>/replay_004_final.py` (offline candidates replay,
  production `resolve`-path functions, real `data/rotation/board_series.json`
  + `data/monitor/stock_industry_map.json` + `data/narrative_holdings/`)
- `uv run irc notify-status --run-kind flow-capture --last-exit-code 0`
- `uv run irc notify-status --run-kind monitor --last-exit-code 0`
- `uv run pytest tests/docs/ -q`
- `uv run irc --help`
- `uv run irc config validate`

### Cross-item flow observed

**(a) Rotation offline replay — items 004+005 store semantics compose**

Ran the Task-5-pattern script (004-plan.md) unmodified in intent against real
`data/` (no network). Full output:

```
active_boards=21 funds=446 seen_syms=699 unresolved_names=0
PRE-FIX  candidates=0 coverage=67.8016 unmapped=331
POST-FIX candidates=38 raw_pre_cap=111 coverage=67.8016 unmapped=331
per_board(raw active >=10%)={'BK1036': 69, 'BK0465': 19, 'BK0727': 15, 'BK0474': 3, 'BK1044': 3, 'BK0473': 1, 'BK1259': 1}
ALL INVARIANTS PASS
```

Invariants held: pre-translation (names fed as codes) → 0 candidates
(reproduces the bug 004 fixed); post-fix production path → 38 candidates > 0;
raw pre-cap (111) ≥ capped (38), cap (`CAND_TOP_N=10`) bites on `BK1036` (69
raw); coverage byte-identical pre/post (67.8016%); all 699 seen 行业 names
resolve to a board code (0 unresolved). `resolve_candidates`/`rank_candidates`
is the same production function exercised by `irc rotation`'s live path, so
004's join fix and 005's freshness-gated store (`fresh_slice`) compose
correctly end to end.

**(b) Notify surface — items 001+004+005 territory (store, radar, digest)**

PATH-shimmed `osascript` (logs invocation, exits 0) so no real notification
fired; `IRC_FEISHU_WEBHOOK_URL` confirmed unset in both `.env` and shell env →
Feishu leg is a true no-op (not attempted) per `_dispatch`'s `if url:` guard.

`--run-kind flow-capture` (today's real rotation state: `outputs/2026-07-07/
rotation/rotation_radar.json` → `data_status: "abstain"`, 0 board_states):

```
[23:12:55] INFO  notify-status severity=degraded notify=True
[osascript-shim] called with: -e display notification
  "Run completed; nothing actionable. · 轮动雷达: 弃权 (连续第 1 日)"
  with title "IRC data degraded"
```

Degraded + 弃权 wording confirmed. The flow-capture N/M coverage line
(`flow_capture_partial`, added since `d9a06161`) did **not** appear — verified
this is correct, not a miss: today's real `data/monitor/fund_flow_series.json`
delta is 29/30 symbols at `2026-07-07` (96.7%), above the 80% `_COVERAGE_FLOOR`
in `src/irc/notify/health.py`, so the conditional in `flow_capture_health`
correctly stays silent. (Computed independently via a manual `_newest_by_symbol`
equivalent over the real store before running the CLI, to have an a-priori
expectation rather than reverse-fitting the observed output.)

`--run-kind monitor` (today's `outputs/2026-07-07/monitor/monitor.json`
sentinel present):

```
[23:13:06] INFO  notify-status severity=degraded notify=True
[osascript-shim] called with: -e display notification
  "Run completed; nothing actionable. · 板块PE: STALE-1 (2026-07-06) ·
   资金流: 最新 2026-07-07 · 覆盖 29/30 · 1 只滞后>3td(最旧 2026-06-26)"
  with title "IRC data degraded"
```

Degraded + the real flow-lag warn (`1 只滞后>3td`, oldest `2026-06-26`)
confirmed, sourced from the same real `fund_flow_series.json` used in (a)'s
adjacent data. Both CLI invocations exited 0 (dispatch succeeded: shim
osascript rc 0, Feishu skipped).

**(c) 002 docs-sync + version guard**

```
$ uv run pytest tests/docs/ -q
.........
9 passed in 0.01s
```

9/9 as expected.

**(d) CLI sanity**

`uv run irc --help` → exit 0; command list includes both `rotation` and
`notify-status` (plus 002/003's untouched surface — `config`, etc.).

`uv run irc config validate` → exit 0, secret-free:
```
OK: all 15 YAML files validated.
  scoring weights version: 2026-05-19-v2
  universe size: 471 instruments
  llm tasks configured: 13
  spend: margin 1.2, 13 task seeds
```

### Failures

None. 0 failures across (a)-(d).
