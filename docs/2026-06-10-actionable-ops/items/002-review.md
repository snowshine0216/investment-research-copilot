Verdict: PASS-WITH-NITS
Source: /ship steps 8+9
Findings (all fixed pre-push — see items/002-ship-blocked.md + items/002-drift.md):
- drift F2 (P0) — httpx INFO logged Feishu token URL → launchd err log — FIXED 55ecd8a.
- P0-1 — missing summary keys defaulted to 0, masking "unknown" sell-side state (ADR 0015) — FIXED dc8c468.
- P0-2 — uv PATH-resolved; launchd stripped PATH → exit 127, zero notifications — FIXED e305f7e (__UV_BIN__ templating).
- P0-3 — no pipeline timeout; hang = total silence — FIXED e305f7e (portable watchdog, rc=124 → "timeout").
- P0-4 — malformed holiday YAML crashed the notifier pre-notification — FIXED dc8c468 (graceful degrade).
- P0 (adversarial round 2) — set -e + wait skipped notify-status on EVERY non-zero pipeline exit — FIXED 8b01906 (+ real-wrapper regression test 6b8ec17).
- P1s — corrupt-JSON buys-only → clean (FIXED, unreadable→failed); substring grep skip (FIXED, anchored); newline escaping (FIXED).
Remaining (accepted): CN-TZ drift on non-CN machines — documented assumption (ADR 0016, README warning + install.sh +0800 check); weekend-date-dependent test flagged as follow-up; osascript failure logs at WARNING.
Adversarial final: RISKS (P2 only).
