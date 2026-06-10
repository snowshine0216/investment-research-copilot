Verdict: PASS

Subagent: sonnet
Plan checklist items: 51 steps across 6 tasks
Verified present in diff: 51/51 (all steps implemented)

> **Re-verification (2026-06-10, fix commit `55ecd8a`):** F2 is FIXED — verdict
> upgraded FAIL → PASS. Evidence in F2 below.

---

## Drift findings

### F1 — "unknown" vs "unavailable" in classifier body — ACCEPTED (plan amended)

**Type:** minor text divergence, plan vague vs spec  
**Evidence:** Plan Task 2 Step 3 (`classify.py`) gives body string:
`"Sell-side signals unavailable (stale artifact) — re-run \`irc opportunity\`."` but
implementation has:
`"Sell-side state unknown (stale artifact) — re-run \`irc opportunity\`."`.
**Adjudication:** The spec (§Classification item 4 + AC2) mandates the word **"unknown"**
explicitly (`"sell-side state UNKNOWN"`, `"named as unknown (not '0' / not 'healthy')"`).
The test asserts `"unknown" in decision.body.lower()`. The plan's word "unavailable" is
inconsistent with the spec's MUST; the implementation is more spec-correct.
**Action:** Plan amended at Task 2 Step 3 to use the spec-compliant wording. No code
change required.

---

### F2 — AC7 URL-not-logged test scoped to app logger only — REAL LEAK → FIXED (commit `55ecd8a`)

**Type:** functional gap — test passes but the real leak path is unguarded  
**Evidence:** The `test_feishu_post_does_not_log_full_url` test uses
`caplog.at_level(logging.INFO, logger="irc.commands.notify_cmd")` and then filters
`caplog.records` to `r.name == "irc.commands.notify_cmd"`, intentionally excluding the
`"httpx"` logger. This makes the test green.

However, the real leak path is confirmed:

1. `src/irc/observability/console.py` `setup_logging()` calls
   `logging.basicConfig(level=logging.INFO, force=True)` — this sets the **root logger**
   to INFO with a RichHandler writing to **stderr**.
2. `httpx._client` uses `logging.getLogger("httpx")` and calls
   `logger.info("HTTP Request: %s %s ...", request.method, request.url, ...)` on every
   completed request (confirmed in httpx source at `_client.py:1024` and `:1739`).
3. The `"httpx"` logger propagates to root by default; root is at INFO → the RichHandler
   emits the full URL (including the secret token path segment) to stderr.
4. The launchd plists have `StandardErrorPath` → `outputs/_logs/launchd-daily.err.log`,
   so every Feishu call writes the full webhook URL (token included) to a log file in the
   repo.

This contradicts AC7 ("The URL never appears in logs") and the global CLAUDE.md rule
("never logged in full") and the spec constraint ("must not be logged in full").

The accepted deviation noted in the impl summary ("test scoped to the app logger") is
NOT acceptable: it papers over the actual leak rather than fixing it.

**Fix applied (commit `55ecd8a`, RED-first):**

- `src/irc/commands/notify_cmd.py`: module-level
  `logging.getLogger("httpx").setLevel(logging.WARNING)` (with a comment explaining the
  leak path). httpcore left alone — source inspection confirms it has zero
  `logger.info`/`logger.warning` calls (DEBUG-only).
- `tests/commands/test_notify_cmd.py::test_feishu_post_does_not_log_full_url` rewritten
  to capture at **root scope** (`caplog.at_level(logging.INFO)`, no logger filter) and
  assert the token is absent from **every** record from **any** logger, with a
  leak-naming failure message. The previous app-logger allow-list filter is removed.

**Re-verification evidence (drift reviewer, independent of the impl agent's claims):**

1. `uv run pytest tests/notify/ tests/commands/test_notify_cmd.py -q` → **42 passed**.
2. **Production-path simulation (fix present):** `setup_logging(debug=False)` (root at
   INFO) + recording handler on root + `notify_cmd._send_feishu` against a respx-mocked
   `https://open.feishu.cn/hook/SECRET-TOKEN-1234` → the ONLY record reaching the root
   handler is `irc.commands.notify_cmd: "posting Feishu notification to
   host=open.feishu.cn"`. No token, no full URL, from any logger.
3. **Counterfactual (fix reverted in-process):** resetting the `httpx` logger to
   `NOTSET` and repeating the same simulation reproduces the leak — the
   `httpx` record `HTTP Request: POST https://open.feishu.cn/hook/SECRET-TOKEN-1234 …`
   reaches the root handler. The fix is load-bearing; the rewritten test would be RED
   without it (confirms the impl agent's RED-first claim).
4. **httpcore claim verified:** walked every `httpcore` submodule's source; all
   `.info(` matches are `connection.info()` methods, zero `logger.info`/`logger.warning`
   calls — DEBUG-only logging confirmed, no suppression needed.
5. `uv run ruff check` on both touched files → All checks passed.

---

### F3 — `config/cn_market_holidays.yaml` force-added against gitignore — ACCEPTED (consistent pattern)

**Type:** minor / configuration file tracking  
**Evidence:** `.gitignore` contains the line `config/` which would exclude all files
under `config/`. The file was force-added (`git add -f` or the agent bypassed
gitignore). However, `git ls-files config/` shows nine files already tracked:
`config/discovery.yaml`, `config/narratives/ai.yaml`, multiple universe YAMLs, and
`config/spend_*.yaml`. The `cn_market_holidays.yaml` is a template (empty list `[]`,
user-fills-in-annually) analogous to the tracked `discovery.yaml` template. This is
consistent with the established project pattern of force-tracking config templates while
gitignoring user-specific overrides.  
**Action:** No change required.

---

### F4 — pre-existing ruff noise — ACCEPTED (baseline)

**Type:** pre-existing  
**Evidence:** `uv run ruff check src tests` passes clean on all new files. No new
violations introduced.  
**Action:** None.

---

## Gates

- `uv run pytest tests/notify/ tests/commands/test_notify_cmd.py -q` → 42 passed
- `plutil -lint ops/launchd/*.plist` → both OK
- `bash -n` on all 4 scripts → OK
- `uv run ruff check src/irc/notify tests/notify src/irc/commands/notify_cmd.py tests/commands/test_notify_cmd.py` → All checks passed

---

## Verdict rationale

Initial verdict (2026-06-10) was **FAIL** on F2: the spec requires the webhook URL to
never appear in logs, the CLAUDE.md global rule forbids logging webhook URLs in full,
and the implementation leaked it to stderr → launchd `StandardErrorPath` log files
whenever Feishu was enabled, with the AC7 test scoped to avoid seeing the leak.

**Re-verification after fix commit `55ecd8a`:** the leak path is closed (production-path
simulation shows only the host-only app log reaching the root handler; counterfactual
reverting the fix reproduces the leak, proving the test is load-bearing). F1/F3/F4
remain accepted; all gates re-run green (42 tests, plutil, bash -n, ruff). AC7 is now
genuinely verified at root-logger scope. Verdict: **PASS**.
