Verdict: PASS

Subagent: sonnet
Source: /verify
Entry point exercised:
  - `uv run irc --help`
  - `uv run irc monitor --help`
  - `uv run irc monitor flow-capture --help`
  - `uv run irc monitor flow-capture --repo-root <scratch>` (real CLI entry, unpatched)
  - `uv run python -c ...` against `irc.http_proxy.resolve_cn_proxy` / `proxy_env`
  - `uv run python <script>` against `irc.commands.monitor_cmd.run_flow_capture`,
    `_load_flow_store_slice`, with `fetch_flow_today_batch` / `_capture_union_symbols`
    monkeypatched and a seeded trading-calendar cache (no live network)
  - `uv run python <script>` against `irc.monitor.industry_valuation.fetch_industry_pe`
    with an injected `fetch`
  - `uv run irc config validate`
  - `grep` / `bash -n` / `plutil -lint` on invariants and launchd artifacts

Observed behavior:
  - `irc --help` exits 0; `monitor` group present in the command list.
  - `irc monitor --help` exits 0; `flow-capture` listed alongside `snapshot`
    ("15:45 job: append the completed-day flow batch to the...").
  - `irc monitor flow-capture --help` exits 0; shows `--repo-root` and `--help` only.
  - `irc config validate` → `OK: all 15 YAML files validated` (secret-free surface intact,
    ADR 0017).
  - D1/D2 proxy contract (`resolve_cn_proxy`): unset → `None`; bare `host:port` →
    normalized `http://host:port`; full URL → passthrough; `IRC_CN_PROXY_MODE=off` →
    `None` even with URL set; mode unset + URL set → `on` (default). `proxy_env(None)`
    is a true no-op (no env mutation); `proxy_env(url)` sets `HTTP(S)_PROXY`/lowercase
    and restores originals on exit. No proxy secrets were read from the real `.env` or
    printed — a dummy value was used throughout.
  - Offline `run_flow_capture` smoke (real orchestration: `load_monitor_config` →
    `_capture_union_symbols` (patched to a fixed 2-symbol tuple) → `fetch_flow_today_batch`
    (patched) → `load_trading_days` (seeded cache, no fetch) → `append_today` →
    atomic write): run 1 wrote `data/monitor/fund_flow_series.json` with the completed-day
    row for both symbols (`{"600690": [["2026-07-02", 1.2345]], "600233": [["2026-07-02",
    -0.5678]]}`), rc 0, printed `flow-capture OK: 2026-07-02 appended 2/2 symbols`. Run 2
    (same day, same inputs) produced a **byte-identical** file (idempotent completed-day
    append, D6). Run 3 with a raising `fetch_flow_today_batch` logged a warning
    (`exc_info=True`, caught inside `run_flow_capture`'s `try/except`) and returned rc 0
    with the store file **byte-identical** to before the call (untouched).
  - Store→brief consumption (`_load_flow_store_slice`): sliced the store from the run
    above against `("600690", "600233", "999999")` → numeric values mapped back correctly
    (`(("2026-07-02", 1.2345),)` etc.), missing symbol → `None` (no KeyError). Corrupting
    the store file (`{not valid json!!`) made the internal `load_store` degrade to `{}`
    (logged, not raised) and the slice degrade to `{"600690": None, "600233": None}` — a
    safe all-`None` shape, not a crash. (Note: literal task wording said "degrade-to-`{}`"
    for the *slice*; actual code degrades the *store* to `{}` internally and the slice
    still maps every requested symbol to `None` — this is the correct/intended behavior
    per the function's own docstring "Degrades to {} on any error — the flow factor then
    reads all-None", just a shape clarification, not a defect.)
  - Industry default-fetch identity (`fetch_industry_pe`): a 2-board injected frame
    (黄金 18.46, 白色家电 12.3) parsed to `{"黄金": 18.46, "白色家电": 12.3}` and wrote a
    cache file. An empty frame parsed to `{}` and — per D3 — **no cache file was written**
    (`industry_pe_cache_empty/` stayed empty), confirming the "never cache an empty parse"
    contract that fixes the F4 wart.
  - D10: `grep -rn fetch_flow_series src/irc/commands/` → no matches (retired from the
    run path). `grep -rln fetch_flow_series src/irc/` → still present in
    `holding_metrics.py` (docstring reference only, not a call), `industry_valuation.py`,
    `flow_fetch.py` (library code, kept for D7 seed / Tier-2 spot-checks per D10).
  - Invariants: `_ENGINE_VERSION = "3"` in `src/irc/commands/monitor_cmd.py` (untouched,
    D4). `_SCHEMA_VERSION = ` appears exactly once in `src/irc/monitor/eval/trace.py`
    with value `"5"` (single bump, D9). `bash -n ops/launchd/run-flow-capture.sh` — clean
    syntax. `plutil -lint ops/launchd/com.irc.flow-capture.plist` → `OK`.
  - 🔍 Probe: invoked the real CLI entry point directly
    (`uv run irc monitor flow-capture --repo-root <scratch-with-empty-fundamentals-cache>`)
    with `_capture_union_symbols` **unpatched** — correctly hit the documented early-return
    path (`monitor_cmd.py:940-942`): logged `WARNING flow-capture: no active-fund symbols;
    nothing to capture`, rc 0. Confirms the CLI wiring `irc.cli:monitor_flow_capture` →
    `run_flow_capture` is live end-to-end, not just the Python-level function.
  - 🔍 Probe: re-ran the store-slice corruption check after an earlier interrupted run had
    left the scratch store genuinely corrupted on disk from a prior script — caught by the
    assertion failing for the wrong reason, re-seeded a clean store via a fresh
    `run_flow_capture` call before re-verifying. No product defect; scratch-state hygiene
    only.

Failures: none

Out of scope for this verify (per spec §7, Tier-2/post-merge/live): EastMoney reachability
through the real proxy, GATE-2 4dp equivalence, real 15:45 launchd firing, `nav_cover`
recovery after `irc fundamentals stock-valuation --force`, and the week-long 06-25
non-recurrence check. None of these were probed, per the task's explicit no-live-network
instruction.
