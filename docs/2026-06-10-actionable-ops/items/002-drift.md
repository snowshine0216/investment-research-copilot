Verdict: FAIL

Subagent: sonnet
Plan checklist items: 51 steps across 6 tasks
Verified present in diff: 51/51 (all steps implemented)

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

### F2 — AC7 URL-not-logged test scoped to app logger only — REAL LEAK, FAIL

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

**Required fix (not applied in this diff — must be resolved before shipping):**
In `notify_cmd._send_feishu` (or at the top of `_dispatch`), add:
```python
logging.getLogger("httpx").setLevel(logging.WARNING)
```
This suppresses httpx's INFO-level URL log for the duration of the process (idempotent,
low-blast-radius). Alternatively, pass `httpx.Client(...)` with a no-log transport, or
use `respx` / monkey-patch in tests to assert the httpx logger emits nothing at INFO.
The test must be extended to also assert no record from the `"httpx"` logger contains
the token.

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

F2 is a **functional gap**: the spec requires the webhook URL to never appear in logs,
the CLAUDE.md global rule forbids logging webhook URLs in full, and the real
implementation leaks it to stderr → launchd `StandardErrorPath` log files whenever
Feishu is enabled. The test was deliberately scoped to the app logger to avoid seeing
the httpx leak, which means the AC7 acceptance criterion is not actually verified.
This must be fixed before the branch ships. Verdict: FAIL.
