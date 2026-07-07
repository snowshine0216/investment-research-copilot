# FACTS — investment-research-copilot (read me at session start; never re-ask these)

> Per-repo registry of things a session tends to re-ask: service endpoints, env-var
> NAMES (never values), proxies, canonical model IDs, known traps, and verification
> commands. Every line below is traceable to a repo source cited in parens. Credentials
> live in `.env` — this file references the key name only, never a secret/proxy value.
>
> **Live-incident entries carry a date and a verification command, and must be re-verified
> before being acted on.** A line describing a *transient* condition — a geo-block, an
> outage, a "currently unset / currently set" env var (re-verify any such claim with
> `grep -oE '^NAME=' .env`, substituting the real var name — names only, never values), a
> "currently blocked" egress plane — rots fast: the F8 board-plane entry below went stale
> **within 2 days** (written
> "hard-blocked", already superseded by a 2026-07-06 seed success at review time). Treat any
> dated live-incident line as a hypothesis, not a fact — run its cited one-liner (the
> `uv run python -c …` / CN-egress probes already in this file are the pattern) and trust the
> result, not the prose.

## Services & endpoints

- **AkShare / EastMoney (board plane)** — `push2.eastmoney.com/api/qt/clist/get` (board
  snapshot + board PE) and `push2his` (board kline). Geo-throttled on some non-CN
  egresses; routed through `$IRC_CN_PROXY` when set (`README.md:129-133`,
  `src/irc/http_proxy.py:38-47`).
  **As of 2026-07-07 this plane is INTERMITTENT at day granularity, not hard-blocked** —
  `IRC_CN_PROXY` was dropped from `.env` on 2026-07-06 and direct egress now carries it:
  full success 2026-07-06 (rotation seed completed 200 boards × 60 rows, board-PE recovered
  69/70, forward ledger started 52 rows), refused again 2026-07-07 (`RemoteDisconnected`).
  Expect a mix of ok/abstain days; `irc rotation` writes `data_status: "abstain"` only on
  refused days — cheap and safe. `push2his`-via-`$IRC_HTTPS_PROXY` (the DXY route) stays dead
  — a separate problem. See `TODOS.md` "Sector rotation radar" §0-corrected entries and
  `docs/2026-07-05-sector-rotation-radar/F8-DIAGNOSIS-FIX-PLAN.md`. **Re-verify with the CN
  egress board-plane one-liners below before acting — this describes a live incident.**
- **AkShare / EastMoney (flow plane)** — `ulist.np` batch endpoint. Stays reachable
  direct even when the board plane is geo-throttled; no proxy needed (`README.md:133`).
- **Tushare** (`api.tushare.pro`) — mainland-CN fundamentals fallback (filing digest,
  broker reports, index valuation). Called **direct**, never through `$IRC_HTTPS_PROXY`.
  Auth: `$TUSHARE_TOKEN` (ADR 0010; `src/irc/fundamentals/tushare_provider.py:15`).
- **SEC EDGAR** — US filing fetches. Needs `$EDGAR_CONTACT_EMAIL` set to a real address
  (SEC fair-use User-Agent policy) or fetches may be rate-limited/blocked
  (`.env.example`).
- **Web search providers** (research stage, `RESEARCH_ENABLED=true` only) — Tavily
  (`api.tavily.com`, `$TAVILY_API_KEY`), Brave (`api.search.brave.com`,
  `$BRAVE_API_KEY`), Bocha (`api.bochaai.com`, `$BOCHA_API_KEY` — ZH provider). Routed
  through `$IRC_HTTPS_PROXY` (`README.md:118-125`).
- **Jina Reader** (`r.jina.ai`) — URL→markdown extractor; free tier keyless, paid tier
  `$JINA_API_KEY`. Routed through `$IRC_HTTPS_PROXY`.
- **LLM providers per pipeline stage** (`config/llm.yaml`, task→provider/model table;
  auth resolved at the call edge, never at `Settings()` construction —
  `src/irc/settings.py`, ADR 0017):
  - **DeepSeek** (`api.deepseek.com`, `$DEEPSEEK_API_KEY`) — legacy `irc run` tasks
    (news/scoring/thesis/interactive-query; also this repo's *current local override*
    for `memo_synthesis`/`memo_audit` — see Model roster below).
  - **OpenRouter** (`openrouter.ai/api/v1`, `$OPENROUTER_API_KEY`) — the **shipped
    default** route for `memo_synthesis`/`memo_audit` (Anthropic models via OpenRouter).
    Required for a fresh install even if you never touch OpenRouter directly
    (`README.md:38`).
  - **MiniMax** (base url `$MINIMAX_BASE_URL`, `$MINIMAX_API_KEY`) — `irc monitor`
    tasks only (`monitor_impact`, `monitor_narrative`). Model pinned by
    `$MINIMAX_MODEL` — see the non-reasoning-model rule below.
- No committed secrets were found in tracked files during this audit (`git ls-files`
  scanned for API-key-shaped strings, zero hits outside `.env.example`). `.env` itself
  is correctly gitignored (`.gitignore` "# Secrets" block).

## Environment

- **`$IRC_CN_PROXY`** — CN egress for the EastMoney **board plane** only (`irc
  rotation`, `irc rotation seed`, `irc monitor`'s board-PE leg, `irc fundamentals
  stock-valuation`). *Opposite direction* from `$IRC_HTTPS_PROXY` — the two never mix
  (`README.md:129-140`). Accepts a URL or bare `host:port`. Kill switch:
  `$IRC_CN_PROXY_MODE=off` forces CN-direct even when the URL is set. **Currently unset
  in this repo's `.env`** (only `IRC_CN_PROXY_MODE` and `IRC_HTTPS_PROXY` are set —
  verified via `grep -oE '^IRC_[A-Z_]*=' .env`, values not read). Verify it works:
  ```bash
  # irc rotation — did the board snapshot reach the boards (not abstain)?
  uv run python -c "import json,glob; f=sorted(glob.glob('outputs/*/rotation/rotation_radar.json'))[-1]; d=json.load(open(f)); print(f,'| data_status:',d['data_status'],'| boards:',len(d['board_states'])); print('OK' if d['data_status']!='abstain' and d['board_states'] else 'FAIL — board fetch blocked')"

  # irc monitor — is the board-PE (industry-valuation) leg lit, not dark?
  uv run python -c "import json,glob; f=sorted(glob.glob('data/monitor/industry_pe/*.json'))[-1]; d=json.load(open(f)); print(f,'| entries:',len(d)); print('OK — board-PE lit' if len(d)>0 else 'DARK — clist/get blocked')"
  ```
  (`README.md:141-146`). `degraded_flow_dark`/`degraded_turn_dark` is fine; only
  `abstain` means the board fetch itself failed. **T2 (spec, 2026-07-05):** never test
  EM endpoints through curl-through-proxy — it false-fails; use `requests` (Python) as
  the code does (`docs/superpowers/specs/2026-07-05-sector-rotation-radar-design.md`
  §13).
- **`$IRC_HTTPS_PROXY`** — applied uniformly to LLM providers (DeepSeek, OpenRouter,
  MiniMax), web-search providers (Tavily, Brave, Bocha), Jina Reader, and DXY-via-
  EastMoney ingest. Other AkShare calls (mostly mainland-CN domains) stay direct
  (`README.md:118-125`). Currently **set** in this repo's `.env` (value not read here).
- **Python via `uv`.** Stack is Python 3.12+, entry point `irc = "irc.cli:main"`. Install:
  `uv sync --all-extras`. Never call `python`/`pip` directly for this repo — always
  `uv run irc ...` / `uv run pytest ...` (`CLAUDE.md`).
- **DuckDB single-writer constraint.** `data/local.duckdb` is written by
  `src/irc/data/` / `io_utils.py` — "the only place mutable filesystem state lives"
  (`CLAUDE.md` Architecture section). DuckDB's single-writer constraint is upstream of
  this codebase and is the caller's responsibility to serialize
  (`docs/2026-05-22-thesis-cards-evidence-gap/items/010-spec.md:364`). **Concurrent
  `irc` invocations (e.g. a manual `irc monitor` while the weekly `irc run` is still
  executing) can conflict writing `data/local.duckdb`.** The launchd per-wrapper
  single-instance locks (`.monitor.lock`, `.weekly.lock`, `.snapshot.lock`,
  `.flow-capture.lock`) exist primarily to avoid duplicate paid LLM spend and wasted
  concurrent work, not specifically to guard the DB — so a **manual** run started
  alongside a scheduled one is not blocked by them and can still hit the single-writer
  conflict (`ops/launchd/README.md` "Per-wrapper single-instance locks").

## Model roster (canonical IDs)

- **`irc monitor` tasks (`monitor_impact`, `monitor_narrative`) → MiniMax.** `$MINIMAX_MODEL`
  **MUST be a fast, non-reasoning chat model** (e.g. `MiniMax-Text-01`). A reasoning
  model (e.g. `MiniMax-M3`) overruns the per-call deadline and degrades the daily brief
  to `NO_CALL` (`README.md:210-211`, `ops/launchd/README.md` "Install" section,
  `README.md:37`). **Currently set correctly** in this repo's `.env`:
  `MINIMAX_MODEL=MiniMax-Text-01` (a non-reasoning model — compliant).
- **Legacy `irc run` tasks → DeepSeek**, per the packaged template
  (`src/irc/templates/config/llm.yaml`): `news_summary`/`news_dedup`/`factor_screening`/
  `watchlist_reason`/`research_synth` → `deepseek-chat`; `scoring_rationale`/
  `thesis_falsify`/`thesis_defend`/`interactive_query` → `deepseek-reasoner`.
- **`memo_synthesis` / `memo_audit` — shipped default vs. this repo's local override.**
  The packaged template routes both through **OpenRouter** to Anthropic models:
  `memo_synthesis → anthropic/claude-opus-4.7`, `memo_audit → anthropic/claude-sonnet-4.6`
  (`src/irc/templates/config/llm.yaml`, `CONTEXT.md:314`). **This repo's runtime
  `config/llm.yaml` currently overrides both to DeepSeek** (`memo_synthesis` and
  `memo_audit` → `provider: deepseek, model: deepseek-reasoner`) — a supported local
  edit, not a change to the shipped default (`README.md:38`). Don't assume memo calls
  hit OpenRouter/Anthropic on this machine without re-checking `config/llm.yaml`.
- Model choice is validated at the **LLM call edge**, not at `Settings()` construction —
  `irc init` / `irc config validate` are secret- and model-free (ADR 0017,
  `CLAUDE.md` Architecture section).

## Known traps

- **`tests/commands/` as a whole directory can hang instead of failing.** Documented in
  the repo's own scar-tissue list: "`pytest tests/commands/` whole-dir hangs (suite
  ordering) — run per-file in CI steps"
  (`docs/superpowers/specs/2026-07-05-sector-rotation-radar-design.md` §13, trap T5).
  **Empirically reproduced 2026-07-06**: `uv run pytest tests/commands/` stalls (bash
  `timeout` had to kill it, rc 124; low CPU time relative to wall time — a blocked call,
  not a compute loop), while `--co` (collect-only, 513 items) finishes in <1s. The stall
  point was **not confined to one file** in this session's reproduction — it also
  appeared inside `tests/commands/test_ingest_cmd.py` run alone. This repo's real `.env`
  has a live `$IRC_HTTPS_PROXY` configured, and the ops docs independently document that
  "a non-LLM, non-`cached_fetch` network call with no timeout... can hang a half-open
  socket forever" (`ops/launchd/README.md` "Watchdog" section) — a plausible root cause
  if a test's mocking is incomplete and a real request leaks through to an unreachable
  proxy. **Practical mitigation:** run one test file (or `-k`) at a time; if a run still
  stalls, Ctrl-C and check whether `$IRC_HTTPS_PROXY`/`$IRC_CN_PROXY` are reachable from
  your current network before assuming a test regression.
- **`.gitignore:23`'s `config/` rule is unanchored — it shadows BOTH the root `config/`
  AND `src/irc/templates/config/`, not just the root one.** (Correction to an earlier
  draft of this file, which wrongly claimed only root `config/` was affected —
  disproven by testing a fresh untracked file directly: `git check-ignore` reports both
  paths matched by the same `.gitignore:23:config/` rule.) The comment above the rule
  ("Templates live in `src/irc/templates/{config,inputs}`; the root copies are
  user-specific... and must not be committed", `.gitignore:20-23`) only *intends* the
  root copy, but the pattern text itself has no leading `/` or `**/` anchor, so git
  matches a directory named `config` at **any depth** — including the packaged
  template dir. In practice this mostly bites on the root `config/` (nearly all its
  content is untracked, user-edited YAML), but **any genuinely new file you add under
  `src/irc/templates/config/` is silently gitignored too** and needs `git add -f` just
  like the root copy. Already-tracked files under either path (most of
  `src/irc/templates/config/*.yaml`, which were added with `-f` historically) don't
  show as ignored by `git check-ignore` — that's a property of already-tracked paths,
  not proof the pattern doesn't apply to new files there. Verify for yourself:
  ```bash
  touch src/irc/templates/config/__zz_probe.tmp && git check-ignore -v src/irc/templates/config/__zz_probe.tmp && rm src/irc/templates/config/__zz_probe.tmp
  ```
  Source: `.gitignore:20-23`;
  `docs/2026-06-06-spend-balance-gate-phase2/items/001-plan.md:27` ("`config/` is
  gitignored → any new committed config is `git add -f`'d").
- **EastMoney field-code semantics are interface-specific, not endpoint-agnostic.**
  行业 (industry) is field **`f127`** in `stock/get`/`clist` — but in the batch
  `ulist.np` endpoint, `f127` is a **numeric** field (涨速/change-rate) and 行业 rides on
  **`f100`** instead. Requesting `f127` on the batch endpoint silently returns a number,
  not an industry string (root-caused by probe 2026-07-04; T1 in the same spec's trap
  list). Sources: `src/irc/monitor/flow_batch_fetch.py:13-16`,
  `docs/adr/0020-monitor-dual-track-valuation.md:81`,
  `docs/superpowers/specs/2026-07-05-sector-rotation-radar-design.md` §13 (T1).
- **The `cached_fetch` breaker is protective, not a retry queue.** A blocked/throttled
  run must never self-extend by retrying — there is a documented >40-minute self-DoS
  incident in ADR 0019's history from exactly this (spec T3,
  `docs/superpowers/specs/2026-07-05-sector-rotation-radar-design.md` §13).
- **Never run `irc monitor flow-capture` manually before the 15:00 CN market close** —
  a midday capture corrupts the close-based flow series (spec T4); the manual path is
  unguarded (`docs/monitor/README.md:44`). This is also why the scheduled job chains at
  15:45, not at the 12:15 monitor brief time.
- **Scheduled launchd runs execute from whatever is checked out in the working tree at
  fire time.** Each plist sets `WorkingDirectory` to the literal repo root
  (`ops/launchd/com.irc.monitor.plist` — `WorkingDirectory: __REPO_ROOT__`, same
  pattern in the other 3 plists); there is no separate deploy/pin step. A branch switch
  or `git checkout` left in place across a 12:15 / 15:45 / Saturday-09:00 trigger will
  make that scheduled run execute against whatever is on disk at that moment. *(Inferred
  from the plists' `WorkingDirectory` mechanism, not a verbatim repo warning — no actual
  incident of this is on record.)*
- **`monitor.json` is the ONLY valid completion sentinel — never `report.html`.**
  `_write_outputs` writes `report.html` **first**, then `signal.json` → `impacts.json`
  → `narrative.json` → `monitor.json` **last**. A crash between those writes leaves a
  present-but-incomplete set; keying success detection on `report.html` was a real bug
  (fixed 2026-06-30, `TODOS.md:50`, `ops/launchd/README.md` "Why not a stable launchd
  log file" section / plist comments). Both `run-monitor.sh`'s idempotency guard and
  `notify-status`'s success detection must stay keyed on `monitor.json` — if you touch
  either, touch both.
- **launchd `StandardOutPath`/`StandardErrorPath` are deliberately `/dev/null`, not a
  log file.** A persistent launchd-owned log file gets tagged with the macOS
  `com.apple.provenance` xattr on first write; the **next** scheduled spawn is denied
  reopening it (`EX_CONFIG` / exit 78) and the job silently stops firing forever after
  that. Symptom: `launchctl print gui/$(id -u)/com.irc.monitor` shows `last exit code =
  78` with `runs` incrementing but no new log content. Each wrapper writes its own
  fresh per-run log instead (`ops/launchd/README.md` "Logs" section).

## Verification commands

- **Run the monitor manually:** `uv run irc monitor` → writes
  `outputs/<date>/monitor/{report.html,drilldown.html,eval_trace.json}` and appends to
  `data/monitor/forward_ledger.jsonl` (`CLAUDE.md` Commands section, `README.md:391`).
- **Completion sentinel** (the only reliable one — see Known traps):
  `outputs/<date>/monitor/monitor.json` must exist and be non-empty; it is the LAST of
  the 5 atomic writes in `monitor_cmd._write_outputs`
  (`ops/launchd/README.md`; `docs/monitor/README.md:230`).
- **Forward ledger check:** `tail -n 5 data/monitor/forward_ledger.jsonl` — confirm an
  appended row for today's `run_date`. Cross-run cumulative state, lives under `data/`
  (not date-partitioned `outputs/`) by design (`CONTEXT.md:35`).
- **Eval health check (free, offline, no LLM spend):**
  ```bash
  uv run irc eval --all          # every in_all_suite stage; rc = max(0/1/2)
  uv run irc eval monitor_signal # single artifact eval, part of the green suite
  ```
  Return codes: `0=PASS`, `1=WARN`, `2=FAIL`, `3=SKIPPED` (`evals/README.md`). Live-LLM
  suites (spend real MiniMax budget, double-gated, excluded from `--all`):
  ```bash
  IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_impact
  IRC_RUN_LIVE_LLM_EVAL=1 uv run irc eval monitor_narrative
  ```
  Unset the env → `SKIPPED` (rc 3), never a false success (`evals/README.md`).
- **Launchd agent labels:** `com.irc.monitor` (daily 12:15), `com.irc.flow-capture`
  (daily 15:45, chains `irc rotation`), `com.irc.fundamentals-quarterly` (quarterly
  08:00), `com.irc.weekly` (Saturday 09:00) (`ops/launchd/README.md` schedule table).
  Legacy `com.irc.daily` / `com.irc.weekly-full` are retired — `bash
  ops/launchd/uninstall.sh` boots them out if present.
- **`launchctl` status:**
  ```bash
  launchctl print gui/$(id -u)/com.irc.monitor   # check `last exit code` + armed StartCalendarInterval triggers
  ```
  (`ops/launchd/README.md` "Watchdog" section). Repeat with the other 3 labels above.
- **Plist/script validation before installing:**
  ```bash
  plutil -lint ops/launchd/*.plist        # all must print OK
  for s in ops/launchd/*.sh; do bash -n "$s"; done
  ```
  (`ops/launchd/README.md` "Validation" section).
- **CN egress board-plane check:** see the two `uv run python -c ...` one-liners under
  "Environment" above (rotation `data_status` / `industry_pe` non-empty).
