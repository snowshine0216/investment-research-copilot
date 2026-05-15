# Handoff Document
*Last updated: 2026-05-15 late night CST (post-push)*

---

## Session: May 15 (late night) — Slice 3: wire ConstituentSnapshot + ThemeReport into opportunity.states

### Goal
Per the May-14 spec ("Constituent Fundamentals" + acceptance criterion #15: "`thesis_evidence` is populated when `ConstituentSnapshot` is present and empty (with appropriate gap) when absent"), derive `thesis_state` deterministically from concrete fundamentals rather than the free-text theme-thesis table, and surface typed `evidence_gaps` + a `thesis_evidence` citation list on every `OpportunityRow` / `ThesisCard`.

### Current Progress
**Slice 3 complete; +20 new tests, 0 regressions. Full suite: 908 passed, 17 skipped, plus 5 e2e passed.**

- `src/irc/opportunity/types.py` — added `ThesisEvidence` frozen dataclass (`type` ∈ {filing, broker, news, policy, snapshot}, `source`, `url`, `date`, `summary`). Added `thesis_evidence: tuple[ThesisEvidence, ...] = ()` to both `OpportunityRow` and `ThesisCard`.
- `src/irc/opportunity/thesis_evidence.py` — new pure function `derive_thesis_from_evidence(snapshot, theme_report) -> (state, reason, evidence, gap_labels)` implementing the spec's deterministic rules:
  - `falsified`: ≥60% of constituents with reported YoY are negative.
  - `intact`: ≥60% positive YoY AND <30% negative YoY AND broker consensus not negative.
  - `under_pressure`: ≥30% negative YoY OR broker consensus < 0.
  - `evidence_insufficient`: snapshot missing, no constituents, no filings with revenue_yoy, or direction ambiguous.
  - Broker consensus is sum of rating sentiments — positive tokens {买入, 增持, Buy, Overweight, …}, negative tokens {卖出, 减持, Sell, Underweight, …}.
  - Evidence assembly: top-3 filings by |YoY|, top-2 most recent broker reports, top-2 theme-report citations. Caps keep cards readable.
- `src/irc/opportunity/states.py` — `build_opportunity_row(inp, theme_thesis, *, snapshot=None, theme_report=None)` now prefers the evidence-derived thesis path when either is supplied; otherwise falls back to the legacy table-based `classify_thesis` and tags `missing_constituent_snapshot` + `missing_recent_news` as typed gaps. The structural gaps (`missing_valuation_data`, `missing_flow_or_return_data`, `missing_product_metadata`) now use the typed labels from the May-14 spec instead of free-form strings.
- `src/irc/opportunity/cards.py` — propagates `row.thesis_evidence` into `ThesisCard.thesis_evidence`. No other changes.
- `src/irc/opportunity/report.py` — no code changes needed; `dataclasses.asdict` already round-trips `ThesisEvidence` cleanly into YAML, verified with a new assertion test.
- Tests added/updated (TDD throughout):
  - `tests/opportunity/test_types.py` — 2 new tests for `ThesisEvidence` immutability + valid kinds.
  - `tests/opportunity/test_thesis_evidence.py` — 14 new tests (insufficiency paths, intact / under_pressure / falsified branches, evidence assembly, capping, typed gaps).
  - `tests/opportunity/test_states.py` — migrated 3 existing tests to the typed labels, added 3 new tests for the snapshot path / table fallback / missing-snapshot gap.
  - `tests/opportunity/test_cards.py` — 1 new test for thesis_evidence propagation.
  - `tests/opportunity/test_report.py` — 1 new test for YAML serialization.

### What Worked
- **Keeping the legacy `classify_thesis(inp, theme_thesis)` path as a fallback** — let the CLI keep functioning unchanged; the snapshot wiring becomes opt-in. The default `OpportunityRow.thesis_evidence = ()` and the typed `missing_constituent_snapshot` gap make the absence explicit in every output, not hidden.
- **Evidence cap (3 filings / 2 brokers / 2 news)** — keeps cards readable; the spec's example card has only 2 evidence entries, so the caps match expected fidelity.
- **Resolving the spec's intact/under_pressure boundary**: the spec uses "AND" for intact and "OR" for under_pressure, which conflict at e.g. 60% pos / 40% neg. The implementation requires `pct_pos ≥ 60% AND pct_neg < 30%` for intact, which is strictly stronger than the spec's literal intact rule but matches its intent ("predominantly positive without significant negative tail"). Documented in the function's docstring.
- **Reusing `dataclasses.asdict`** in report.py — no serialization code changes needed; nested frozen dataclasses round-trip cleanly into PyYAML.
- **Switching evidence_gap labels to the spec's typed set** in one slice rather than over multiple slices — the existing tests were the only consumers, and they're now aligned with the spec.

### What Didn't Work
- **First-draft intact rule (`pct_pos ≥ 60% OR (under_pressure not triggered)`)** — failed when 60% pos / 40% neg fired both intact and under_pressure rules. Tightened intact to require both ≥60% positive AND <30% negative AND non-negative broker consensus.
- **Initial `_evidence_insufficient_when_all_filings_lack_yoy`** test expected `missing_constituent_snapshot` in gaps; first impl only marked that when `snapshot is None or empty filings`. Added the same label when filings exist but none have YoY (so the downstream `evidence_gaps` consistently distinguishes "no snapshot at all" vs. "snapshot too sparse to use").

### Next Steps
1. ~~**Commit this slice.**~~ Done — `79f0833 feat(opportunity): derive thesis_state from ConstituentSnapshot + ThemeReport`, pushed to `origin/feat/opportunity-thesis-discipline`.
2. **Wire snapshots into `opportunity_cmd.py`.** Currently `build_opportunity_row(inp, theme_thesis or None)` is called without `snapshot` / `theme_report`. To exercise the new path end-to-end, the CLI should:
   - Build a `lookthrough_target` → `ConstituentSnapshot` map (load from `data/fundamentals/<quarter>/<target>.json` via `irc.fundamentals.snapshot.load_cached_snapshot`).
   - Build a `theme` → `ThemeReport` map (read `data/research/<theme>.md` artifacts, or re-run if `--refresh-research` is passed — needs design).
   - Pass `snapshot=snapshot_by_target[row.lookthrough_target.display_cn]`, `theme_report=report_by_theme[row.theme]` per row.
   - Surface skipped/missing pairs as warnings, not errors.
3. **Extend `_TARGET_REGISTRY` as themes onboard.** Still only 沪深300 / 中证500 are seeded in `irc.fundamentals.snapshot._TARGET_REGISTRY`. The May-14 spec themes (cn_monetary, cn_equity_property_policy, holdings_sector, us, gold, geopolitics) each need a matching `_TargetSpec`. For US/HK targets, the registry needs static symbol lists (no readily available top-N constituents fetcher for those markets) — this is a separate research/data slice.
4. **README operational section** — once slice 2 above lands and outputs exist with real evidence, document where the citations come from / how to interpret thesis_evidence types / refresh cadence per the spec's README Follow-Up.

### Key Files & Locations
| File | What it is |
| :--- | :--- |
| `src/irc/opportunity/types.py` | Added `ThesisEvidence` dataclass + `thesis_evidence` field on `OpportunityRow` and `ThesisCard`. |
| `src/irc/opportunity/thesis_evidence.py` | New — pure `derive_thesis_from_evidence(snapshot, theme_report)`. |
| `src/irc/opportunity/states.py` | `build_opportunity_row` accepts optional `snapshot` + `theme_report` kwargs; typed `evidence_gaps` labels. |
| `src/irc/opportunity/cards.py` | Propagates `thesis_evidence` into the card. |
| `tests/opportunity/test_thesis_evidence.py` | New — 14 tests. |
| `tests/opportunity/test_types.py`, `test_states.py`, `test_cards.py`, `test_report.py` | Extended for new fields + typed gaps. |

### Context & Notes
- **Branch**: `feat/opportunity-thesis-discipline`, now 3 commits ahead of `main` for this initiative: `09a6011 research adapter stack`, `f73e2e4 fundamentals layer`, `79f0833 thesis_state from snapshot`. All pushed to origin.
- **All tests run under 25 s** (full suite + e2e). The slice keeps the codebase fast.
- **Spec divergence noted**: the intact rule's literal spec wording would conflict with the under_pressure rule at the boundary. The implementation resolves it deterministically (intact requires both ≥60% positive AND <30% negative AND non-negative broker consensus) and the function docstring documents the resolution. If quarterly real-world testing produces too few `intact` rows, relax the negative cap from 30% to 35% as a first knob.
- **No CLI wiring yet** — `opportunity_cmd.py` still uses the table-based path. This is intentional: it keeps the slice atomic and reviewable. Wiring is the very next step (see Next Steps #2).

---

## Session: May 15 (later) — Constituent Fundamentals layer (CN + US + HK + snapshot cache)

### Goal
Build the `src/irc/fundamentals/` module per the May-15 adapter-signatures spec, so the opportunity layer can derive deterministic `thesis_state` decisions from concrete constituent-level evidence (filings, broker reports, holdings) rather than free-text LLM outputs.

### Current Progress
**All 5 modules + 6 test files added under TDD; +45 tests, 0 regressions. Full suite: 892 passed, 17 skipped.**

- `src/irc/fundamentals/types.py` — frozen dataclasses `Constituent`, `FilingDigest`, `BrokerReport`, `ConstituentSnapshot` (5 tests).
- `src/irc/fundamentals/akshare_fundamentals.py` — 4 CN fetchers using the `_ak_call` indirection (same pattern as `irc.data.akshare_client`):
  - `fetch_cn_index_constituents` — CSI index weights, normalizes percent → fraction, suffix CN tickers (.SH/.SZ by code prefix).
  - `fetch_cn_etf_holdings` — EastMoney `fund_portfolio_hold_em`, filters to latest 季度.
  - `fetch_cn_broker_reports` — `stock_research_report_em`, filtered by `days` window, newest first; EastMoney feed has no target_price → always None.
  - `fetch_cn_filing_digest` — `stock_financial_abstract` (wide-format); maps `YYYYMMDD` column → period label (`FY` if `1231`, else `Q1/Q2/Q3`); computes YoY against same-period prior year; gross_margin = 1 − 营业成本/营业总收入. (15 tests.)
- `src/irc/fundamentals/edgar_client.py` — SEC EDGAR JSON, two endpoints:
  - `https://www.sec.gov/files/company_tickers.json` for ticker → CIK
  - `https://data.sec.gov/api/xbrl/companyfacts/CIK*.json` for XBRL facts
  - Tries `Revenues` → `RevenueFromContractWithCustomerExcludingAssessedTax` → `SalesRevenueNet`; similar list for cost. Latest filing = max(filed) among form ∈ {10-K, 10-Q}. SSRF guard via `irc.llm.http_client.verify_host_resolves_publicly`. UA header per SEC fair-use policy. (9 tests.)
- `src/irc/fundamentals/hkex_client.py` — uses EastMoney's HK feed (`stock_financial_hk_report_em` long-format with REPORT_DATE/STD_ITEM_NAME/AMOUNT). Pivots in-memory for 营业额 / 股东应占溢利 / 毛利, matches prior year by date offset, infers period from (REPORT_DATE − START_DATE) days. Symbol normalized to 5-digit EM format. (6 tests.)
- `src/irc/fundamentals/snapshot.py` — orchestration + JSON cache:
  - `_TARGET_REGISTRY` dispatches `lookthrough_target` → `_TargetSpec(kind, code/symbols)` with three kinds: `cn_index`, `us_symbols`, `hk_symbols`.
  - Seeded with 沪深300 / 中证500; extend as themes onboard.
  - `build_snapshot` never raises; per-symbol failures (missing digest, etc.) recorded in `failure_reasons`.
  - `cache_path` = `<root>/fundamentals/<quarter>/<lookthrough_target>.json`; `_infer_quarter` follows earnings-season convention (calendar Q2 → tagged Q1 of the just-reported quarter, not the current calendar quarter). `write_snapshot` / `load_cached_snapshot` round-trip all fields including unicode targets. (10 tests.)

### What Worked
- **`_ak_call` indirection mirrored from `irc.data.akshare_client`** — uniform pattern across the codebase, makes `patch("module._ak_call")` trivially clean. Tests don't need akshare installed at collection time.
- **SSRF guard via `verify_host_resolves_publicly` BEFORE httpx.get** — matches the LLM gateway's existing pattern (line 75-83 of `http_client.py`). Test fixture monkeypatches it to a no-op so respx mocks aren't shadowed by real DNS.
- **EastMoney for HK fundamentals (`stock_financial_hk_report_em`)** instead of scraping HKEX disclosure feeds directly — same library/dependency surface as CN, single mock pattern.
- **Snapshot dispatch via `_TargetSpec` dataclass + module-level registry** — keeps the public `build_snapshot(target, *, top_n, as_of_iso)` signature clean (matches the spec exactly) while letting tests inject new targets via `monkeypatch.setitem(snapshot._TARGET_REGISTRY, ...)`.
- **Per-symbol failures recorded as strings in `failure_reasons`** — `evidence_gaps` typing in the May 14 spec can map these directly without exception handling at the call site.

### What Didn't Work
- **`_infer_quarter` first attempt mapped to current calendar quarter** (`(month - 1) // 3 + 1`). Round-trip test caught it: a snapshot taken on 2026-05-15 should be tagged `2026Q1` (the just-reported quarter), not `2026Q2`. Fixed to subtract one from calendar quarter and roll Q1 back to prior-year Q4. The earnings-season convention is now documented in the function's docstring.
- **Initial CN broker reports test had no `_today_iso` indirection** — relative date math against `pd.Timestamp.now()` would have made the 90-day cutoff test flaky in 2027. Added `_today_iso()` helper and patched it in the relevant tests.
- **`stock_zh_a_disclosure_relation_cninfo` (mentioned in the May 15 signatures spec)** is actually a *pre-disclosure calendar* endpoint, not a filing URL feed. Skipped it; use a stable sina FinanceSummary URL pattern as `source_url` for CN filings instead. The spec is slightly aspirational here; treat it as "use whatever produces a stable, citable URL."

### Next Steps
1. **Commit this slice.** Branch `feat/opportunity-thesis-discipline` still uncommitted from May 15 morning's research-stack work — the user prefers to review diffs before committing. Suggest two commits: (a) "feat: research adapter stack (LDR replacement)" for the May 15 morning work, (b) "feat: constituent fundamentals layer (CN/US/HK + snapshot cache)" for tonight's work.
2. **Slice 3: wire `ConstituentSnapshot` + `ThemeReport` into `opportunity.states`.** Per the May 14 spec, implement the deterministic `thesis_state` rules (e.g. "≥60% of top-N constituents have revenue_yoy > 0 → intact", "median broker rating downgrade → review", etc.). Populate `thesis_evidence` in cards. Map snapshot `failure_reasons` into typed `evidence_gaps` (`missing_constituent_snapshot`, `missing_broker_coverage`, …).
3. **Extend `_TARGET_REGISTRY` as themes onboard.** Currently only 沪深300 / 中证500 are seeded. The May 14 spec themes (cn_monetary, cn_equity_property_policy, holdings_sector, us, gold, geopolitics) each need a matching `_TargetSpec`. For US/HK targets, the registry will need static symbol lists (no readily available top-N constituents fetcher for those markets).
4. **README operational section** — once slice 3 outputs exist, document where candidates come from / how often to run each command / how to interpret DCA/pause/review/trim/exit per the May 14 spec's README Follow-Up.
5. **(Optional) End-to-end smoke** — set real Tavily + Bocha keys in `.env`, run `RESEARCH_ENABLED=true uv run irc run --only research`, verify `data/research/<theme>.md` files come out with citations. The research stack from this morning's session has not yet been exercised against live APIs.

### Key Files & Locations
| File | What it is |
| :--- | :--- |
| `src/irc/fundamentals/types.py` | New — 4 frozen dataclasses for constituent evidence |
| `src/irc/fundamentals/akshare_fundamentals.py` | New — 4 CN fetchers (constituents, holdings, broker reports, filing digest) |
| `src/irc/fundamentals/edgar_client.py` | New — SEC EDGAR companyfacts JSON adapter, SSRF-guarded |
| `src/irc/fundamentals/hkex_client.py` | New — EastMoney HK income-statement adapter, long-format pivot |
| `src/irc/fundamentals/snapshot.py` | New — orchestration + on-disk JSON cache, `_TARGET_REGISTRY` |
| `tests/fundamentals/` | New — 5+15+9+6+10 = 45 tests |
| (unchanged from morning) `src/irc/research/search/`, `synthesize.py`, `theme_research.py`, `pipeline.py`, `commands/research_cmd.py`, `settings.py`, `config/llm.yaml`, `.env.example` | All still uncommitted from morning's session |

### Context & Notes
- **Branch**: `feat/opportunity-thesis-discipline`. Nothing committed yet for either today's session — uncommitted diff now spans both the research-adapter stack (morning) and the fundamentals layer (evening).
- **TDD discipline held throughout** — every implementation was preceded by a failing test; only one bug surfaced (the quarter inference off-by-one) and was caught by the round-trip test before the module was claimed done.
- **akshare 1.18.60 is installed via `uv run`**. All 4 endpoints (`index_stock_cons_weight_csindex`, `fund_portfolio_hold_em`, `stock_research_report_em`, `stock_financial_abstract`) plus the HK endpoint `stock_financial_hk_report_em` exist and were probed once for real column shapes; mocks match production schema. CN broker reports endpoint took ~20s on first probe (large per-stock crawl behind the scenes).
- **Test suite runtime is ~14 min** end-to-end (lots of integration smoke). Targeted runs (`pytest tests/fundamentals/`) are <1s — prefer those during slice 3 development.
- **The Hong Kong client uses EastMoney, not HKEX directly.** This is a soft deviation from the spec's wording ("via HKEX disclosure feed") but matches the spec's intent: a free, structured, library-mockable source. If HKEX direct access becomes important later (e.g., for prospectus / circular content not in EastMoney), add a second adapter alongside.

---

## Session: May 15 (morning) — LDR Removal + Research Adapter Stack (search providers + synthesis)

### Goal
Replace the slow LDR (Local Deep Research) self-hosted agent loop with a pluggable, fast research stack (Tavily + Brave + Bocha + Jina Reader + bounded LLM synth) so the opportunity/thesis/discipline layer designed on May 14 has fast, citable thesis evidence. Update the May 14 spec to reflect this and to add a constituent-fundamentals layer that fills the "industry/company depth" gap.

### Current Progress

**Spec edits**
- New: `docs/superpowers/specs/2026-05-15-research-adapter-signatures.md` — pins all adapter signatures + dataclasses + config + test surface. Updated to reflect implementation drift (`synthesize_report` takes `ResolvedRoute`; `build_theme_reports` takes injected providers/extractor/route).
- Edited: `docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md`:
  - LDR removed everywhere (Non-Goals, Quarterly Thesis Research, Acceptance Criteria explicitly demands deletion).
  - New section **Constituent Fundamentals** between Opportunity Identification and Opportunity State — top-N constituents, filing digest, broker reports, quarterly disk cache, concrete `thesis_state` derivation rules.
  - New section **Configuration And Setup** — Tavily / Brave / Bocha / Jina signup URLs, first-run checklist, per-key failure behavior.
  - `thesis_evidence: [{type, source, url, date, summary}]` added to thesis card.
  - Error Handling: typed `evidence_gaps` (`missing_constituent_snapshot`, `missing_broker_coverage`, etc.).
  - Performance Contract: ≤30 s/theme, ≤5 min weekly, ≤30 s daily light, ≤15 min quarterly snapshot rebuild.

**Implementation (TDD throughout — 55 new tests across 8 files)**
- Search adapters (each = httpx call mocked via respx, failures degrade into `SearchResult(failure_reason=...)`):
  - `src/irc/research/search/types.py` — `Locale`, `SearchHit`, `SearchResult`, `ExtractedPage`, Protocols.
  - `src/irc/research/search/tavily_provider.py` — POST + Bearer auth.
  - `src/irc/research/search/brave_provider.py` — GET + `X-Subscription-Token`, freshness bucketed pd/pw/pm/py.
  - `src/irc/research/search/bocha_provider.py` — POST + Bearer auth, app-level error codes, oneDay/oneWeek/oneMonth/oneYear/noLimit.
  - `src/irc/research/search/jina_reader.py` — GET `r.jina.ai/<url>`, optional auth.
  - `src/irc/research/search/dispatch.py` — `providers_for_locale`, `multi_provider_search` (locale fan-out + URL dedupe + partial-success), `extract_top_pages` (catches extractor exceptions).
  - `src/irc/research/search/factory.py` — builds providers + extractor from `Settings`.
- LLM synthesis: `src/irc/research/synthesize.py` — `Citation`, `ResearchReport`, `synthesize_report(query, hits, pages, *, route)`. Citations built from input pool so LLM can't hallucinate URLs.
- Theme research: `src/irc/research/theme_research.py` rewritten — `theme_locale()` mapper (us/gold/geopolitics → EN; cn/hk/holdings → ZH), per-theme failure isolation, queries in CN for ZH themes.
- Pipeline: `src/irc/research/pipeline.py` — `run_research_pipeline(repo_root, themes, *, providers, extractor, route)`.
- CLI integration: `src/irc/commands/research_cmd.py` — skips with a clear message when no providers configured, never crashes. `run_cmd.py` gate flipped from `LDR_ENABLED` → `RESEARCH_ENABLED`. `cli.py` help text updated.
- LLM task added: `config/llm.yaml` + `src/irc/templates/config/llm.yaml` — `research_synth: deepseek-chat`.
- Settings: `ldr_*` fields removed; `tavily_api_key`, `brave_api_key`, `bocha_api_key`, `jina_api_key` added (all `SecretStr`).
- `.env.example` rewritten — LDR block replaced with the four new keys + signup URLs.
- Deleted: `src/irc/research/ldr_client.py`, `tests/research/test_ldr_client.py`.
- Tests updated: `tests/test_settings.py`, `tests/test_e2e_plan3_full_pipeline.py`, `tests/commands/test_research_cmd.py`, `tests/commands/test_run_cmd.py`, `tests/research/test_pipeline.py`, `tests/research/test_theme_research.py`.

**Final test state:** `uv run pytest` → 847 passed, 17 skipped, 0 failures.

### What Worked
- **Inject providers + extractor + route into `build_theme_reports`** — keeps theme research pure and trivially testable with fake providers. Real CLI wires up via `factory.build_providers(settings)`.
- **Citations from the input pool, not LLM output** — `synthesize.py` indexes URLs from `pages` (preferred) and `hits`, feeds numbered sources to the LLM, which can only reference [n]. The LLM cannot invent URLs.
- **`failure_reason` on every adapter return** — no exceptions cross the dispatch boundary. Partial-success search (one provider down, others up) works automatically.
- **`respx`** for httpx mocking — already a project dep, makes header / body / param assertions clean.
- **Following the existing `call_chat(route, messages, ...)` + `patch("module.call_chat", ...)` pattern** from `memo/synthesizer.py` rather than introducing dependency injection for the LLM. Less drift, easier test writing.
- **TDD caught a real bug early**: the synthesize happy-path test asserted `published_iso="2026-05-08"`. My first impl lost the hit's `published_iso` when a page existed for the same URL. Fixed before moving on.

### What Didn't Work
- **Original signatures spec proposed `synthesize_report(..., model="deepseek-chat")`** — drifted from the codebase pattern. Switched to `route: ResolvedRoute` + `config/llm.yaml` task routing, then reconciled the spec.
- **First version of `test_research_cmd_skips_when_no_providers_configured`** didn't `chdir` away from the project root, so `Settings()` picked up the user's real `.env` (which has `TAVILY_API_KEY` set). Fix: `monkeypatch.chdir(elsewhere)`. Same fragility hit `test_settings_optional_fields_default_empty` — fixed with explicit `monkeypatch.delenv` for optional keys.
- **First Brave/Bocha freshness mapping was finer-grained** (custom date ranges). Dropped to coarse buckets (pd/pw/pm/py and oneDay/oneWeek/oneMonth/oneYear/noLimit) — simpler, deterministic, no clock dependency.

### Next Steps
1. **`/handoff` is just-now done. Resume work by saying: "continue from HANDOFF.md".**
2. **Constituent Fundamentals layer (next coherent slice).** Build `src/irc/fundamentals/` per the signatures spec:
   - `types.py` — `Constituent`, `FilingDigest`, `BrokerReport`, `ConstituentSnapshot`.
   - `akshare_fundamentals.py` — top-N constituents, holdings, 券商研报, financial abstract (use AkShare endpoints `index_stock_cons_weight_csindex`, `fund_portfolio_hold_em`, `stock_research_report_em`, `stock_financial_abstract`).
   - `edgar_client.py` — SEC EDGAR JSON.
   - `hkex_client.py` — HKEX disclosure.
   - `snapshot.py` — orchestrate + on-disk cache at `data/fundamentals/<quarter>/<lookthrough_target>.json`.
   - All under TDD; AkShare's `requests`-based clients mock cleanly.
3. **Wire `ConstituentSnapshot` + `ThemeReport` into `opportunity.states`** — implement the deterministic `thesis_state` rules drafted in the spec (e.g. "≥60% top-N constituents revenue YoY > 0 → intact"). Populate `thesis_evidence` in cards. Update `evidence_gaps` to typed labels.
4. **README operational section** — once outputs exist, add "Where candidates come from / how often to run each command / how to interpret DCA/pause/review/trim/exit" per the spec's README Follow-Up.
5. **(Optional) End-to-end smoke** — set real Tavily + Bocha keys in `.env`, run `RESEARCH_ENABLED=true uv run irc run --only research`, verify `data/research/<theme>.md` files come out with citations.

### Key Files & Locations
| File | What it is |
| :--- | :--- |
| `docs/superpowers/specs/2026-05-15-research-adapter-signatures.md` | New — adapter interfaces + config + tests + module layout |
| `docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md` | Updated — LDR removed, Constituent Fundamentals + Configuration sections added, typed evidence gaps, perf budgets |
| `src/irc/research/search/` | New module — `types.py`, `tavily_provider.py`, `brave_provider.py`, `bocha_provider.py`, `jina_reader.py`, `dispatch.py`, `factory.py` |
| `src/irc/research/synthesize.py` | New — bounded LLM call, citation-safe |
| `src/irc/research/theme_research.py` | Rewritten — locale-aware, injected adapters |
| `src/irc/research/pipeline.py` | Rewritten — accepts providers/extractor/route |
| `src/irc/commands/research_cmd.py` | Rewritten — factory + provider check, no LDR |
| `src/irc/commands/run_cmd.py` | Gate is now `RESEARCH_ENABLED` |
| `src/irc/settings.py` | `ldr_*` removed; `tavily_api_key`, `brave_api_key`, `bocha_api_key`, `jina_api_key` added |
| `.env.example` | LDR block replaced with new search-key block |
| `config/llm.yaml` and `src/irc/templates/config/llm.yaml` | `research_synth: deepseek-chat` added |
| `tests/research/search/` | New — 7+8+7+7+11 = 40 adapter tests |
| `tests/research/test_synthesize.py`, `tests/research/test_theme_research.py`, `tests/research/test_pipeline.py` | New / rewritten — 3+8+2 |
| (deleted) `src/irc/research/ldr_client.py`, `tests/research/test_ldr_client.py` | Gone |

### Context & Notes
- **Branch**: `feat/opportunity-thesis-discipline`. No commits yet for this session — diff is uncommitted; the user typically reviews before committing.
- **User has real Tavily key set in their local `.env`** (visible because they had `.env` open in the IDE during the conversation). This is why some tests needed `monkeypatch.chdir(elsewhere)` to avoid picking it up. Tests are now robust regardless.
- **User's environment**: Mainland China; OpenRouter still needs `OPENROUTER_HTTPS_PROXY=http://10.27.7.110:8080` for Anthropic models, but research synthesis uses DeepSeek which works direct (per `research_synth` task in `llm.yaml`).
- **Bocha API**: Mainland-China search; ZH theme queries (`cn_monetary`, `cn_equity_property_policy`, `holdings_sector`) route there exclusively because Tavily/Brave indexes underweight eastmoney/xueqiu/cls/wallstreetcn.
- **The May 14 session entry below is now mostly superseded** — its "Next Steps" #1 (write opportunity spec) and #3 (sidecar implementation) are addressed by the May 15 work for the research dependency; the opportunity-layer pieces themselves (lookthrough.py, states.py, etc.) still need implementing as that session described.
- **Wall-clock budget enforcement is not yet measured** — the spec targets ≤30 s/theme, but no integration test asserts it. Add when running with real keys.

---


