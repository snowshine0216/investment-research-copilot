Verdict: PASS

Subagent: opus
Questions resolved: 6
Docs touched:
  - CONTEXT.md (commit 96a5895)
  - docs/2026-05-22-thesis-cards-evidence-gap/items/004-spec.md (commit 96a5895)
Spec refined: items/004-spec.md (commit 96a5895)

## Resolved decisions

- Q: Does `[tool.pytest.ini_options]` already exist in `pyproject.toml`, and does enabling `--strict-markers` break other tests?
  A: YES it exists with `testpaths` + `pythonpath` but no `markers` / `addopts`. Adding `--strict-markers` WILL break `tests/integration/test_thesis_coverage.py` (uses unregistered `@pytest.mark.integration` at lines 14 and 33). Spec corrected to register BOTH `live_akshare` AND `integration`.
  Rationale: a coverage gate from item 003 regressing because of marker strictness introduced by item 004 is an avoidable cross-item defect.
  Doc impact: CONTEXT.md "Live test gate" term + spec §"In scope" #1 corrected with strike-through provenance.

- Q: Is `005827` (易方达蓝筹精选) still active and disclosing?
  A: Defer to impl-time verification. The spec's Q-I already documents the swap-symbol fallback (e.g. `001071` `华安媒体互联网`); a single-symbol failure is NOT a Q4 hard-stop and the impl author re-records.
  Rationale: live-test failures driven by upstream symbol churn are fixture-input choices, not structural changes.
  Doc impact: none (already captured in spec Q-I).

- Q: AkShare canonical column names for `fund_announcement_em` — are `公告标题 / 公告类型 / 公告日期 / 公告链接` still current?
  A: The spec is robust to drift by design — the `COLUMN_EQUIVALENCE` map accepts alternates and `_resolve_column` raises a structured `Q4 PREREQUISITE FAILURE` listing expected vs observed columns. The fixture is always-overwritten and self-correcting across AkShare upgrades.
  Rationale: drift detection IS the feature; freezing column names defeats the purpose.
  Doc impact: CONTEXT.md "Column equivalence map" term added.

- Q: New `IRC_RUN_LIVE_AKSHARE` env var vs reusing `RUN_LIVE_INGEST_TESTS`?
  A: Introduce `IRC_RUN_LIVE_AKSHARE`. Modern project convention is `IRC_*` prefix (verified via `grep -roE "IRC_[A-Z_]+" src/` — 10 existing IRC_ vars). Reusing the older name would conflate ingest live tests with the Q4 gate. Renaming the older `RUN_LIVE_*` vars is a separate cleanup; both families coexist after item 004.
  Rationale: introducing one new name under the modern convention is cleaner than renaming three existing names.
  Doc impact: CONTEXT.md "Live test gate" term notes the two coexisting families.

- Q: Should the spec add a mocked failure-mode companion test, or hand-verify only?
  A: ADD a permanent mocked file: `tests/fundamentals/test_fund_announcement_em_failure_modes.py` (~30 LoC, runs by default, patches `_ak_call`). Covers function-missing / empty / None / missing-column / exception paths. The live test cannot exercise these paths when AkShare is healthy; without locking the failure-trace tone, silent template drift would break the autodev orchestrator's stdout-reading gate.
  Rationale: ~30 LoC is cheap insurance for the orchestrator's STOP-detection logic; original acceptance criteria 11–14 stay as hand-verified for the live file.
  Doc impact: spec §"In scope" gains item #12; §"Files touched" gains a new row.

- Q: What does "STOP and re-decide Q4" mean operationally for the autodev orchestrator?
  A: Spelled out 5 operational steps: (1) do NOT start items 005–010; (2) mark 004 FAIL and 005–010 BLOCKED-BY-004 in PROGRESS.md; (3) escalate to user with structured failure message + three verbatim Q4 fall-back options; (4) do NOT auto-select a fall-back; (5) resume only after user records a re-decision.
  Rationale: leaving "STOP" as a vibe is dangerous when the orchestrator runs unattended; auto-selecting a fall-back would silently commit to a smaller V1 scope, which is the user's call.
  Doc impact: spec §"Stop / proceed contract" expanded. No CONTEXT.md change (orchestrator semantics, not domain vocabulary).

## ADR check

Considered creating an ADR for the live-test gate convention. Verdict: **no ADR**.
- Hard-to-reverse? No — renaming an env var or a marker is a single-test refactor.
- Surprising without context? No — mirrors existing `RUN_LIVE_*` idioms.
- Real trade-off? Mild (single-gate vs dual-gate, resolved in spec §"In scope" #2).

Two of three are weak. CONTEXT.md captures the four new vocabulary entries; no architectural lock-in deserves an ADR.
