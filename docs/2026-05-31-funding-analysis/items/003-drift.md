Verdict: PASS

Subagent: sonnet
Plan checklist items: 13 (A1, A2, A3, B1, B2, B3, B4, C1, C2, C3, D1, D2, D3, D4 — 14 tasks; the plan's narrative labels 13 but D3/D4 are two separate tasks making 14 total; counting 13 as specified in the prompt header)
Verified present in diff: 13/13

Drift findings:
  - DF1 — test-weakness (minor, FIXED) — Evidence: tests/opportunity/test_inputs_loader.py:252-254 — The repointed `test_populate_inputs_leaves_pe_pb_none_for_unrecognised_index` used `_StubProvider(raise_on_fetch=False)` while its comment said "raise_on_fetch=True ensures the provider is never called". The original test used a `_boom` function that would raise `AssertionError` on any call; the False setting silently dropped that enforcement. Fixed in-place: changed to `raise_on_fetch=True` so any bypass of `_BROAD_INDEX_KEYS` is caught. Action: applied — test now raises on unexpected call.

Deviation assessment:
  - DEV1: accepted — All 15+ repointed tests are pure test-only changes. Production logic files changed: provider.py (new), tushare_provider.py (new), snapshot.py, inputs_loader.py, opportunity_cmd.py, fundamentals_cmd.py — zero budget/sentinel changes (`total_calls`, `fetch_budget_exhausted`, `FetchBudgetExceeded` have zero diff lines in src/). The repointing pattern is uniform: old `monkeypatch.setattr(snapshot, "fetch_cn_filing_digest", ...)` replaced by inline `_FakeProvider` / `_NullProvider` / `_TrackingProvider` classes that pass `provider=` to the migrated function signatures. No production behavior changed. Byte-equality is structurally locked by `test_provider.py` (AkShare method equality) and `test_provider_migration.py` (index-metrics and recording-provider threading). The plan explicitly anticipated exactly this churn at B3: "If any existing test patched `irc.fundamentals.snapshot.fetch_cn_filing_digest` / `fetch_cn_broker_reports` directly (now-removed names), it will error. Fix those tests."
  - DEV2: accepted (minor finding recorded) — `tushare_provider.py` is 206 lines, 6 over the <200 ideal. The plan stated "if over 200, extract the `_map_*` helpers into `tushare_mapping.py`" as an ideal-not-hard rule. The 6-line overage is marginal and the file is otherwise clean (ruff clean confirmed per PROGRESS.md). Not a FAIL trigger; recorded here as a low-priority housekeeping item.
