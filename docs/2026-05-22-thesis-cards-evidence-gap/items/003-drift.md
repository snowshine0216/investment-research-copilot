Verdict: FAIL

Subagent: sonnet
Plan tasks: 24
Verified present in diff: 23

Drift findings:
  - Task 22 — divergent (scope: CLI flag wiring)
    Evidence: `src/irc/cli.py:125` calls `run_opportunity(repo_root=repo_root)` — `output_dir`, `limit`, `rebuild_fundamentals` are accepted by the Click handler but silently dropped. `src/irc/commands/opportunity_cmd.py:595` — `run_opportunity` signature is `def run_opportunity(repo_root: str) -> int:` (no extra kwargs). `validate_cli_args` exists at `opportunity_cmd.py:243` but is never called from `run_opportunity`. `_build_rows` at `opportunity_cmd.py:417` has no `limit` or `rebuild_fundamentals` params. The plan (Task 22 Step 3) explicitly required: (a) extending `run_opportunity`'s signature, (b) calling `validate_cli_args` inside it, (c) threading `limit`/`rebuild_fundamentals` into `_build_rows`, and (d) passing flags from `cli.py` through. All four sub-requirements are unimplemented.
    Action: plan amended inline with DRIFT NOTE at end of Task 22 Step 5 — commit below.

  - Task 22 (incidental file omission) — accepted
    Evidence: `src/irc/commands/run_cmd.py` was not modified, despite the plan mentioning plumbing `--limit`/`--rebuild-fundamentals` into the `run --from opportunity` pipeline path (`003-plan.md:3255-3270`). Since `run_opportunity` itself is not wired, the `run_cmd.py` gap is downstream of the same root cause and is already covered by the FAIL finding above.

  - `tests/opportunity/test_thesis_relevance_gate.py` — scope-creep (accepted, incidental)
    Evidence: `git diff` shows 3 lines updated from 4-tuple to 5-tuple unpacking of `derive_thesis_from_evidence`. Not in plan's file-touch map, but is a mechanical consequence of the signature change in Task 15. No new test logic. Accepted.

  - Task 21 probe semantics — accepted (sensible interpretation, not drift)
    Evidence: `opportunity_cmd.py:216` — `if not probe.source_report_quarter: return snap, True`. Probe returns `HoldingsResult((), "2024-03-31", "2024Q1")`; empty constituents tuple but non-empty quarter string → `refresh=False`, cache reused. Test at `test_opportunity_cmd.py:517` explicitly asserts this. The spec's phrase "probe exception OR empty" at §"Cache layout + freshness contract" is ambiguous: "empty" here means "empty quarter string" (i.e., the provider returned no useful quarter information), not "empty constituents tuple" (the probe is a top_n=1 cheapness check, not a holdings completeness check). ADR 0002 §2 says "Probe succeeds with same quarter → update `cache_probed_at`, reuse cached body" — a probe that returns a non-empty quarter string IS a success regardless of constituent count. Judgment: sensible interpretation, NOT drift.

  - Task 7 (implementer-reported deviation) — verified correct, NOT drift
    Evidence: `tests/fundamentals/test_akshare_fundamentals.py:278` asserts `exchanges == ["HK", "HK", "HK", "SH", "US", "BJ"]` where `"AAPL"` is position 4 → `exchange="US"`. The AAPL fixture row in `_HK_HOLDINGS_FRAME` at line 215 is used for the HK-routing test; the exchange assertion at line 278 confirms `exchange="US"` is returned for AAPL.

  - Task 10 (implementer-reported deviation) — verified correct update, NOT drift
    Evidence: `test_thesis_evidence.py` commit `2e21621` replaces `assert "constituent_not_applicable" in gaps` with `assert "constituent_missing" in gaps` + `assert "constituent_not_applicable" not in gaps`. This matches spec §A1: once `cn_equity_fund` is removed from `NON_INDEXABLE_ASSET_CLASSES`, `_refined_table_gap` returns `"constituent_missing"` (not `"constituent_not_applicable"`) for it. Correct update.

  - Task 11 (`constituent_not_applicable` → `constituent_missing` rename) — verified correct, NOT drift
    Evidence: `src/irc/opportunity/states.py:414-415` — `_refined_table_gap` returns `"constituent_not_applicable"` only for non-indexable classes (gold, cn_bond_fund, qdii_global); `"constituent_missing"` for everything else. Since `cn_equity_fund` was removed from `NON_INDEXABLE_ASSET_CLASSES` by Task 11, it now falls through to `"constituent_missing"`. Spec §A1 and the updated test are consistent.

Invariant checks:
  - citation_id preimage unchanged: `src/irc/opportunity/types.py:130-133` — `citation_id: str = ""` at line 130; comment at line 132 reads "Appended AFTER citation_id; NOT part of the hash preimage (ADR 0001 §2)."; `holding_weight_pct: float | None = None` at line 133; `__post_init__` at line 154 computes hash without `holding_weight_pct`. PASS.
  - active-fund cache path uses provider-declared quarter: `src/irc/fundamentals/snapshot_cache.py:127` — `def active_fund_cache_path(fund_id: str, quarter: str, root: Path) -> Path` takes `quarter` as a parameter; `snapshot_cache.py:212` calls it as `active_fund_cache_path(snap.fund_id, snap.source_report_quarter, root)` using the provider-declared field, not `date.today()` or `calendar_quarter`. PASS.
  - HK forbidden adapter pairs: `src/irc/fundamentals/snapshot.py:253-289` — `elif holding.exchange == "HK":` branch calls only `fetch_hk_filing_digest` (line 255) and `fetch_hk_stock_news` (line 274); no `fetch_cn_filing_digest`, `fetch_cn_broker_reports`, or `fetch_cn_stock_news` calls in the HK branch. PASS.
  - HK news stub-empty fallback: `src/irc/fundamentals/hkex_client.py:174-183` — `hk_news_adapter_available()` uses `hasattr(ak, "stock_hk_news_em")`; `snapshot.py:269-270` — `if not hk_news_adapter_available(): failures.append(f"hk_news_unsupported_adapter:{holding.symbol}")` and `news = ()`. Returns `()` when adapter unavailable, stamps `hk_news_unsupported_adapter:{symbol}`. PASS.
  - no evidence_gaps stamping: `src/irc/opportunity/thesis_evidence.py:349` — comment "Item 003: do NOT stamp evidence_gaps yet; item 006 H2 owns that."; the ActiveFundSnapshot branch at lines 341-356 returns `gaps: tuple[str, ...] = ()` always. `_build_rows` at `opportunity_cmd.py:487-492` passes `snapshot=snap_obj` to `build_opportunity_row` which does not add new gap codes for constituent failures. PASS.
  - default env values: `src/irc/commands/opportunity_cmd.py:55-57` — `TOP_N_DEFAULT = 10`, `IRC_FETCH_BUDGET_DEFAULT = 2000`, `IRC_CACHE_FRESHNESS_DAYS_DEFAULT = 7`; `opportunity_cmd.py:173` — `IRC_OPPORTUNITY_AUTOBUILD` default `"1"`. PASS.
  - --limit canonical-path rejection: `src/irc/commands/opportunity_cmd.py:250-261` — `validate_cli_args` raises `SystemExit(2)` with stderr `"--limit is rejected on canonical output paths"` when `output_dir` ends with `outputs/{today}` and `limit is not None`. Test at `test_opportunity_cmd.py:567-576` confirms exit code 2. NOTE: the function is implemented and tested but not called from `run_opportunity` — this is the Task 22 divergence. The invariant (exit code 2) is satisfied at the unit level but the end-to-end CLI path does not invoke it. PARTIAL PASS (unit) / FAIL (integration).
  - fcntl.flock advisory lock: `src/irc/commands/opportunity_cmd.py:97-106` — stdlib `fcntl` imported with Windows no-op fallback; `opportunity_cmd.py:156` — `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)`. No new third-party dependency. PASS.
