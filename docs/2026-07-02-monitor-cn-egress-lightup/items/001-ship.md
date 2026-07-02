PR: https://github.com/snowshine0216/investment-research-copilot/pull/189
Mode: A
Branch: claude/monitor-cn-egress-lightup-001
Base: autodev/monitor-cn-egress-lightup-feature
Title: feat(monitor): CN-egress data-plane light-up — IRC_CN_PROXY, batch flow, industry raw fetchers (001)

Ship tool: /ship (16-step workflow, orchestrator-driven)
- Steps 0-3: platform GitHub; base = feature branch (autodev override, protected-base avoided); pre-flight clean; base already merged.
- Step 5 tests (post-fix state 759eccc9, scoped per repo caveats — full suite ~61min/24 known pre-existing failures; tests/commands whole-dir hang trap respected): tests/monitor 814p/12s; tests/ops 54p; tests/test_http_proxy 9p; tests/data/test_akshare_client 53p/2s; tests/scripts 12p; fundamentals+eval files 132p; tests/commands per-file (4 files) 21p. Zero in-branch failures.
- Steps 8+9 reviews: see items/001-review.md (P0 fixed pre-push).
- Step 10 VERSION: intentionally NOT bumped (repo convention: accumulate under CHANGELOG [Unreleased] at static VERSION 0.9.3).
- Step 11 CHANGELOG: [Unreleased] entry landed in-branch (Task 15, a5bcbae0) — not duplicated.
- Step 12 TODOS.md: 5 follow-ups appended (592a167c).
- Steps 13-15: tree clean, pushed, PR created.
