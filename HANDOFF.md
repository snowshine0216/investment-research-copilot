# Handoff Document
*Last updated: 2026-05-14 14:29 CST*

---

## Session: May 14 — Opportunity / Thesis / Discipline Strategy Design

### Goal
Enhance the investment research copilot so it can find Mainland China purchasable funds/ETFs that are cold or undervalued but whose long-term thesis is not broken, while also giving the user a disciplined hold/sell framework that prevents panic-selling after drawdowns.

### Current Progress
- Used `superpowers:brainstorming` for strategy design. The brainstorming gate is still active: implementation should not begin until the user reviews and approves the written spec, then the next skill should be `superpowers:writing-plans`.
- Wrote and committed the design spec:
  - `docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md`
  - Commit: `72a2e8f docs: design opportunity thesis discipline`
- Core product decisions captured:
  - Use **方案 2: Thesis + Discipline closed loop**.
  - Product scope: Mainland purchasable ETF/index funds as main line; active funds only as supplementary observation.
  - Long-term sell discipline: mixed thesis/valuation/portfolio/risk framework, not automatic price stop-loss.
  - Short-term layer: only DCA rhythm and risk warnings (`accelerate_dca`, `normal_dca`, `slow_dca`, `pause_dca`, `review_required`, `trim_review`, `exit_review`), not active 1-3 month rotation trading.
- Spec details added at user request:
  - Candidate source and performance model.
  - Do not deeply analyze all public funds each run.
  - Analysis cadence: daily light check, weekly full analysis, monthly universe rebuild, quarterly thesis research, event-triggered reviews.
  - Same-theme fund selection rules.
  - Generated-universe bootstrap rule.
  - README follow-up requirement.
- Candidate source clarified:
  - Runtime should read current repo root files only: `config/universe/cn_funds.yaml` plus optional `config/universe/cn_funds.generated.yaml`, merged by `load_repo_configs()`.
  - External worktree file `/Users/snow/Documents/Repository/investment-research-copilot.worktrees/copilot-subagent-driven-dev/config/universe/cn_funds.generated.yaml` is only a bootstrap reference, not a runtime dependency.
  - If needed, copy/regenerate it into the current repo as `config/universe/cn_funds.generated.yaml`.
- Compared universe files in `/Users/snow/Documents/Repository/investment-research-copilot/config/universe/`:
  - `cn_funds.generated.yaml`: 359 instruments; broad generated pool, mostly `cn_off_exchange` and `cmb_fund`; includes 238 `cn_equity_fund`, 40 `cn_bond_fund`, 1 `cn_etf`, 40 `hk_etf`, 40 `us_etf`.
  - `qdii_hk.yaml`: 13 hand-curated HK exposure products, all `hk_etf`, all `cn_on_exchange`.
  - `qdii_us.yaml`: 13 hand-curated US exposure products, all `us_etf`, 10 `cn_on_exchange`, 3 `cn_off_exchange`.
  - `gold.yaml`: 6 gold products, CMB paper gold plus 5 gold ETFs.
  - No `instrument_id` overlap found between generated file and qdii/gold files.
- Discussed eval requirements:
  - Add one new eval stage: `evals/opportunity/`.
  - Metrics should cover thesis card completeness, evidence gap visibility, same-theme limits, drawdown-not-auto-sell, hot-chase prevention, valid action enums, and absence of external worktree path references.
  - Register `opportunity` in `src/irc/commands/eval_cmd.py`.
  - Do not update architecture output-file eval until opportunity outputs are part of default `irc run`.

### What Worked
- Reading existing code before design was useful: the repo already has `discover`, `score`, `allocate`, `plan`, `memo`, and `decision`, so the new feature should be a sidecar opportunity/thesis/discipline layer first, not a replacement.
- Related notes in `/Users/snow/Documents/Repository/snow-knowledge-database` were useful:
  - Dexter: use research-orchestrator and scratchpad patterns, not final trade decisions.
  - TradingAgents: role separation is useful later, but too heavy for first implementation.
  - Kronos: only a future quantitative signal, not the buy/sell engine.
  - Anthropic financial-services: thesis tracker, catalyst calendar, and rebalance workflow patterns map well to this feature.
  - OpenBB/Scrapling/LDR: data layer, last-mile public data collection, and cited theme research respectively.
- Candidate funnel design resolved performance concerns: thousands -> generated hundreds -> filtered tens -> thesis cards for holdings/watchlist/winners.
- Explicitly treating a 20% drawdown as a review trigger, not a sell trigger, matches the user's behavioral problem.

### What Didn't Work
- Full-market LLM analysis was ruled out. It is slow, expensive, unstable, and unnecessary; deterministic filters and same-theme reduction must happen first.
- Directly reading generated universe files from another worktree was ruled out. It makes runs non-reproducible and hides dependencies.
- Multi-agent debate and Kronos were ruled out for first implementation. They are future enhancements after deterministic discipline is stable.
- Updating existing architecture evals immediately was ruled out. Opportunity outputs should become required only after the command is wired into default `irc run`.

### Next Steps
1. Ask the user to review `docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md`. If they approve, invoke `superpowers:writing-plans` and create the implementation plan. Do not implement before approval.
2. In the implementation plan, include `evals/opportunity/` from the beginning:
   - `evals/opportunity/metrics.py`
   - `evals/opportunity/runner.py`
   - `tests/evals/test_opportunity_metrics.py`
   - `tests/evals/test_opportunity_runner.py`
   - CLI registration in `src/irc/commands/eval_cmd.py`
3. Plan first implementation as a sidecar after scoring:
   - `src/irc/opportunity/lookthrough.py`
   - `src/irc/opportunity/states.py`
   - `src/irc/opportunity/selection.py`
   - `src/irc/opportunity/cards.py`
   - `src/irc/opportunity/discipline.py`
   - `src/irc/opportunity/report.py`
   - `src/irc/commands/opportunity_cmd.py`
4. If real candidate data is needed in the current worktree, copy or regenerate `config/universe/cn_funds.generated.yaml` into `/Users/snow/.codex/worktrees/6a85/investment-research-copilot/config/universe/`; do not read the external worktree path at runtime.
5. Keep README changes for after implementation, as the spec says: README should get concise operational guidance once commands and outputs exist.

### Key Files & Locations
| File | Purpose |
| :--- | :--- |
| `docs/superpowers/specs/2026-05-14-opportunity-thesis-discipline-design.md` | New approved-by-conversation design spec awaiting final user review |
| `src/irc/config_loader.py` | Shows current universe merge behavior: curated `cn_funds.yaml` plus optional generated file |
| `src/irc/discovery/universe.py` | Combines qdii US, qdii HK, CN funds, and gold universes, deduping by `instrument_id` |
| `/Users/snow/Documents/Repository/investment-research-copilot/config/universe/cn_funds.generated.yaml` | Existing broad generated universe used for comparison |
| `/Users/snow/Documents/Repository/investment-research-copilot/config/universe/qdii_hk.yaml` | Existing curated HK universe used for comparison |
| `/Users/snow/Documents/Repository/investment-research-copilot/config/universe/qdii_us.yaml` | Existing curated US universe used for comparison |
| `/Users/snow/Documents/Repository/investment-research-copilot/config/universe/gold.yaml` | Existing gold universe used for comparison |

### Context & Notes
- Current active workspace for code/spec work: `/Users/snow/.codex/worktrees/6a85/investment-research-copilot`.
- The repository is currently on a detached HEAD after committing `72a2e8f`.
- User prefers Chinese for investment/product reasoning; English is fine for code architecture.
- The user's core finance goal is value-oriented long-term DCA without chasing hot funds, plus a technical/evidence framework for when to hold, pause, trim, or exit.
- Avoid framing outputs as definitive financial advice. The system should produce research and discipline reports for human review.
- Existing `HANDOFF.md` below contains older May 8 and May 7 context that may still matter for pipeline/data/universe debugging.

---

## Session: May 8 — Pipeline Empty-Output Investigation + Universe Expansion

### Goal
`uv run irc run` was producing nearly-empty output files (0 candidates → 0 trades). Find out *why* (was it Plan-4 deferral? bugs? config?) and unblock the pipeline so it produces a meaningful portfolio matching the user's `preferences.yaml` targets.

### Current Progress

**Three commits landed on `main`**:
- `cd7c1d1` — `fix(cli)`: `.env` was never loaded; added `load_dotenv()` at CLI entry. Settings class existed but was never instantiated; `os.environ.get()` only saw shell-exported vars.
- `63873f7` — `feat(llm)`: per-provider `{PROVIDER}_HTTPS_PROXY` support + `scripts/check_openrouter.py` diagnostic. Anthropic models on OpenRouter return `403 "not available in your region"` from mainland China; corporate proxy `10.27.7.110:8080` bypasses cleanly. Provider-scoped so DeepSeek + AKShare + OpenBB stay direct.
- `324457c` — `fix(ingest+discovery)`: three pre-existing bugs that produced 0 candidates regardless of universe size:
  1. `cn_funds.yaml` entries excluded from ingest's price-fetch list → 510300/510500 etc. had only NAV, no prices, dropped by daily-volume hard filter
  2. `_is_active_fund` matched any asset_class ending in `*_fund`, flagging passive bond ETFs as active and requiring `manager_tenure_years` they don't have. Now keyed on `market`.
  3. `raw_ref_pool` grew with the data (104k entries at 59 funds) and was joined verbatim into every LLM prompt → DeepSeek 400 Bad Request. Now filtered per-instrument and capped at 30 most-recent refs.

**Local-only changes (NOT committed — `config/` is gitignored per project design)**:
- Universe expanded from 13 → 59 instruments via akshare-grounded ETF list (top-N by AUM per category):
  - `qdii_us.yaml`: 5 → 13 (added 国泰/景顺/华夏/嘉实纳指, 标普500 三家, 道琼斯, 美国50)
  - `qdii_hk.yaml`: 3 → 13 (added 恒生科技 3 家, 中概互联 2 家, 港股红利 3 家)
  - `cn_funds.yaml`: 2 → 27 (added 沪深300 多家, 上证50, 中证A500, 中证500/1000, 创业板, 科创50, 红利, **8 只 cn_bond_fund — 之前完全空白**)
  - `gold.yaml`: 3 → 6
- `.env`: added `OPENROUTER_HTTPS_PROXY=http://10.27.7.110:8080`

**Final pipeline state**:
- Discovery: **0 → 3 candidates** (only 沪深300 ETFs: 510300, 510310, 159919)
- Trade plan: 0 → 2 trades, but `target_weight: 0` because of asset_class mismatch (see "Still Blocking")
- Memo: synthesizes via Anthropic Opus 4.7 through proxy, but `coverage=0%` (traceability check is exact-match — Plan-4 deferred)

### What Worked
- `python-dotenv` is a transitive dep of `pydantic-settings`; calling `load_dotenv()` in the click group's `main()` populates `os.environ` before any subcommand
- Provider-keyed proxy env vars (`{PROVIDER}_HTTPS_PROXY`) — cleanly scopes proxy to OpenRouter without affecting Chinese data sources
- `scripts/check_openrouter.py` two-step diagnostic (auth/key + chat/completion) — surfaced 403 was geo, not auth
- `akshare.fund_etf_spot_em()` returns 1451 ETFs with AUM/volume — perfect for top-N universe selection
- `akshare.fund_etf_fund_daily_em()` is the *separate* endpoint for bond ETFs (52 found) — they don't show up in `fund_etf_spot_em`
- TDD with `mock_writer.call_args.args[1]` to assert per-instrument ref filtering
- Per-instrument ref filtering via `f":{instrument_id}:" in ref` (refs are `source:topic:instrument_id:date` format)

### What Didn't Work
- **Direct Anthropic API**: same geo-restriction would apply, no point using `ANTHROPIC_API_KEY` directly
- **Switching memo synthesis to gpt-5.5**: not needed once proxy worked; Opus 4.7 quality preserved
- **Random/truncated ref pool sampling**: produces semantically meaningless citations (LLM citing 510300's NAV when reasoning about a gold ETF) — per-instrument filter is the right semantic
- **Expense ratio threshold `us_etf_expense_ratio_max: 0.003`**: calibrated for direct US ETFs (5–20 bps) but the universe is QDII feeder funds (60–115 bps). Drops 26/59. Not yet adjusted.

### Still Blocking (in priority order)

1. **Quality filter `manager_tenure_years_min: 2`** kills 8 bond ETFs with the same "ETFs aren't active funds" bug — but in `src/irc/discovery/quality_filter.py` (the ingest fix only addressed the metadata-fetch side). Same `_is_active_fund` heuristic needs to be applied at quality-filter level.

2. **Quality filter `drawdown_3y_max: 24%`** is too tight:
   - All gold ETFs (24.8%–24.9%) — barely fail by ~1pp
   - 创业板 ETF (33.7%), 科创50 (38.8%), 中证1000 (36%), 港股科技 (35%)
   - Either widen threshold to ~30% or accept that growth/satellite categories don't pass

3. **Asset-class mismatch between preferences and universe**: `inputs/preferences.yaml` targets `cn_equity_fund: 0.25`, but the expanded universe is mostly `cn_etf`. The allocator can't fill the bucket → `target_weight: 0`. Either:
   - Update `preferences.yaml` to target `cn_etf` directly (probably what the user wants given the universe)
   - Or add a mapping/aggregation in allocation logic

4. **`venue_compatible: false` with `instrument 510300 not in universe`** despite 510300 being in the universe. Bug in venue-compatibility check; locate via grep for "not in universe".

5. **Hard filter `etf_daily_volume_cny_min: 10M`** still drops 39 instruments — most are real funds whose 3-year averaged volume dips below 10M even though current volumes are much higher. Threshold sensible for liquidity but kills small-but-real funds. Worth re-checking after fixes 1–4.

### Next Steps (resume here)

1. **Fix quality filter's `_is_active_fund` equivalent** — same logic as the ingest fix in commit `324457c`. Find the manager_tenure check in `src/irc/discovery/quality_filter.py`, gate it on `instrument.market != "cn_on_exchange"`. Add test, run, expect 8 more candidates (bond ETFs).

2. **Investigate `venue_compatible` "not in universe"** — grep `src/irc/` for the literal string. Likely a string-match bug between `instrument_id` and venue list.

3. **Reconcile asset-class targets** — confirm with user: do they want `cn_etf` as the cn-equity bucket, or `cn_equity_fund`? Update either `preferences.yaml` or allocation mapping. Probably the former (universe is ETF-based by intent).

4. **Decide drawdown threshold** — propose to user: relax `quality_filters.drawdown_3y_buffer` so gold (24.9%) and growth ETFs (33–39%) can pass. Or split per-bucket (gold-specific cap higher than overall).

5. **After 1–4, re-run `irc run` end-to-end** — expect candidates across gold, cn_bond, cn_equity, hk, us; allocation should produce non-zero target_weights matching the 20/25/15/10/25/5 split.

6. **Plan 4 backlog (deferred, not blocking the above)** — `TODOS.md` lines 42–46 cover Plan-4 items: tracking_error stub, gold drivers stub, traceability fuzzy matcher, correlation filter, `ChatResponse.raw` unbounded.

### Key Files & Locations

| File | What changed this session |
| :--- | :--- |
| `src/irc/cli.py` | `load_dotenv()` at CLI entry |
| `src/irc/llm/http_client.py` | `_resolve_proxy()` per-provider proxy |
| `src/irc/commands/ingest_cmd.py` | `_is_active_fund` market-aware; `cn_funds` in price path |
| `src/irc/discovery/pipeline.py` | `_refs_for_instrument()` per-instrument filter + cap=30 |
| `tests/llm/test_http_client.py` | +4 proxy tests |
| `tests/discovery/test_pipeline.py` | +4 ref-filter tests |
| `scripts/check_openrouter.py` | New diagnostic (auth + chat probe) |
| `config/universe/*.yaml` | **Local-only** universe expansion (gitignored) |
| `.env` | **Local-only** `OPENROUTER_HTTPS_PROXY` |
| `.env.example` | Documented `{PROVIDER}_HTTPS_PROXY` convention |

### Context & Notes

- **User is in mainland China**: Anthropic models geo-blocked. Must keep `OPENROUTER_HTTPS_PROXY=http://10.27.7.110:8080` in `.env` for the memo step to work. DeepSeek (used for most other tasks) works direct.
- **Universe YAMLs are gitignored by design** (per `9b3bc97`) — they're treated as per-user config. Don't try to commit `config/universe/*.yaml`. If the expanded universe should ship as a default, update `src/irc/templates/config/universe/*.yaml` instead.
- **User prefers Chinese explanations** for product/finance decisions; English fine for code/architecture.
- **Auto mode is on** — proceed autonomously where it's clearly correct (bug fixes, low-risk refactors). Stop and ask on product decisions (which threshold to relax, which asset-class mapping to choose).
- **Repo state**: branch `main`, HEAD `324457c`, in sync with origin. All 11 http_client tests + 57 discovery tests + 15 ingest tests pass.
- **Cost note**: each end-to-end `irc run` makes Anthropic Opus 4.7 + Sonnet 4.6 calls via OpenRouter (~$0.04/run based on `auth/key` usage history).

### Quick-Start Commands

```bash
# Re-run discovery only (cheapest iteration during debugging)
uv run irc discover

# Trace funnel manually (fastest way to see which filter drops what)
uv run python -c "
from pathlib import Path
from irc.config_loader import load_repo_configs
from irc.data.duckdb_helper import connect, ensure_schema
from irc.discovery.universe import enumerate_universe
from irc.discovery.hard_filter import apply_hard_filter
from irc.discovery.quality_filter import apply_quality_filter
from irc.commands.discover_cmd import _fetch_metadata_metrics
from irc.schemas.inputs import RiskBand
b = load_repo_configs(Path('.'))
con = connect(Path('data/local.duckdb')); ensure_schema(con)
metadata, metrics = _fetch_metadata_metrics(con); con.close()
u = enumerate_universe(b.universe_qdii_us, b.universe_qdii_hk, b.universe_cn_funds, b.universe_gold)
hard = apply_hard_filter(u, metadata, b.discovery, b.overrides)
risk = RiskBand.model_validate({'max_drawdown':[0.05, b.preferences.risk_band.max_drawdown[1]], 'horizon':'long_core_medium_rotation'})
qual = apply_quality_filter(hard.passed, metrics, b.discovery, risk)
print(f'universe={len(u)} → hard={len(hard.passed)} → quality={len(qual.passed)}')
for r in qual.rejected: print('  ', r.instrument_id, r.reasons)
"

# Verify OpenRouter connection
uv run python scripts/check_openrouter.py

# Full end-to-end
uv run irc run
```

---

## Session: May 7 — Investment Research Copilot Planning + Repo Analysis

### Goal
Design a new investment-research project for a beginner finance user who wants a thorough, explainable system for gold plus domestic/international fund and ETF allocation analysis. The system should combine data, research, scoring, and multi-factor reasoning, not rely only on autoregressive price forecasts.

### Current Progress
- Used the `repo-analysis` skill to analyze 9 repositories and saved structured markdown reports:
  - `ai-engineering/kronos.md`
  - `claude/financial-services.md`
  - `rag-and-knowledge/local-deep-research.md`
  - `agent-frameworks/dexter.md`
  - `agent-frameworks/tradingagents.md`
  - `dev-tools/insforge.md`
  - `dev-tools/ladybird.md`
  - `dev-tools/scrapling.md`
  - `dev-tools/openbb.md`
- Verified all 9 reports include required frontmatter and the fixed section structure: Repo Snapshot, Primary Use Cases, When To Use, Benefits, Limitations and Risks, Practical Insights.
- Ran `git diff --check`; no whitespace errors.
- Began `superpowers:brainstorming` for the actual project design. The hard gate from that skill is active: do not scaffold or implement until the design is approved and written as a spec.
- Decided the investment project should be a separate repo, not a subfolder of `snow-knowledge-database`.
- Approved project-start approach: **Option 1, minimal research system**.
- Approved first design section, Project Boundary:
  - New repo name: `investment-research-copilot`.
  - First version focuses on gold plus domestic/international funds and ETFs.
  - No auto-trading, no broker integration, no high-frequency trading, no dashboard at first.
  - First outputs are Markdown reports plus CSV/JSON data.

### User Decisions Captured
- MVP scope: **A — gold plus domestic/international fund allocation analysis**.
- Investable universe: **B — Mainland China products plus HK/US ETFs**.
- Decision cadence: **D — long-term allocation as core, medium-term rotation as support, no high-frequency short-term trading**.
- Risk profile: **B — steady, accepts roughly 10%-20% max drawdown**.
- Input mode: **C — analyze real holdings and maintain a watchlist/candidate pool**.
- Holding privacy: **C — anonymized holdings; normalize total assets to 100 or 1,000,000**.
- Interface path: **D — start with Markdown reports and CSV/JSON, later upgrade to dashboard**.
- Data-source assumption: **D — free/public data first, pluggable paid/data-vendor sources later**.

### What Worked
- GitHub CLI (`gh repo view`, `gh api`) worked well for repository metadata, README, and selected key docs.
- Repo classification used the knowledge database's six-topic rule; OpenBB stayed under `dev-tools`, Kronos under `ai-engineering`, TradingAgents/Dexter under `agent-frameworks`, Local Deep Research under `rag-and-knowledge`, and Anthropic financial-services under `claude`.
- The most useful architecture mapping from repo analysis:
  - OpenBB = primary financial data layer.
  - Scrapling = missing public web/fund factsheet collector.
  - Local Deep Research = cited research and knowledge-memory layer.
  - Kronos = auxiliary market-sequence signal generator, not final decision maker.
  - TradingAgents = multi-role decision chamber for technical, macro, news, risk, and portfolio views.
  - Dexter = interactive financial research agent pattern, useful later for stock/tool orchestration.
  - Anthropic financial-services = process templates for idea generation, thesis tracking, catalyst calendar, and portfolio rebalance.
  - InsForge = possible later backend platform, not first MVP.
  - Ladybird = no near-term role for investment analysis.

### What Didn't Work
- `gh repo view --json readme` failed because this GitHub CLI version does not expose `readme` as a JSON field. The working fallback was `gh api repos/<owner>/<repo>/readme -H 'Accept: application/vnd.github.raw'`.
- `qgithub.com/shiyu-coder/Kronos` is not a normal GitHub URL; analysis used the intended repo `https://github.com/shiyu-coder/Kronos`.
- Starting with dashboard or database platform was ruled out as too heavy before validating the finance logic.
- Using Kronos or any autoregressive model as the final buy/sell engine was explicitly ruled out.
- Putting the runnable project inside this knowledge database was ruled out because this repo is mainly an Obsidian/content system.

### Next Steps
1. Continue `superpowers:brainstorming` from **Design Section 2**. Present the next section for approval, likely:
   - data model and input files (`portfolio.csv`, `watchlist.csv`, `risk-profile.yaml`)
   - asset classes and required fields
   - free/public source strategy
2. Then present and approve later design sections:
   - scoring framework
   - report/memo format
   - system architecture and data flow
   - error handling and data-quality rules
   - testing approach
   - future dashboard path
3. After all design sections are approved, write the spec to:
   - `docs/superpowers/specs/2026-05-07-investment-research-copilot-design.md`
4. Self-review the spec for placeholders, contradictions, scope creep, and ambiguity.
5. Ask user to review the written spec before moving to implementation planning.
6. Only after user approval, invoke `superpowers:writing-plans` and create the implementation plan. Do not scaffold the new repo before this approval.

### Key Files & Locations
| File | Purpose |
| :--- | :--- |
| `ai-engineering/kronos.md` | Repo analysis for financial K-line foundation model |
| `claude/financial-services.md` | Repo analysis for Claude financial-services workflows and skills |
| `rag-and-knowledge/local-deep-research.md` | Repo analysis for research and knowledge-memory layer |
| `agent-frameworks/dexter.md` | Repo analysis for autonomous financial research agent |
| `agent-frameworks/tradingagents.md` | Repo analysis for multi-agent trading/research framework |
| `dev-tools/openbb.md` | Repo analysis for financial data platform; updated existing file |
| `dev-tools/scrapling.md` | Repo analysis for scraping/data extraction layer |
| `dev-tools/insforge.md` | Repo analysis for possible later backend platform |
| `dev-tools/ladybird.md` | Repo analysis; concluded no first-version role |
| `HANDOFF.md` | This handoff file |

### Context & Notes
- Current workspace: `/Users/snow/Documents/Repository/snow-knowledge-database`.
- At handoff time, `git status --short --untracked-files=all` returned clean.
- The user prefers Chinese explanations for the investment-project discussion.
- The user has explicitly chosen a cautious MVP. Keep scope focused on an explainable weekly/monthly research system for gold and funds/ETFs.
- Avoid implying financial advice. The product should output research memos and recommendations for human review, not automatic trade execution.
- The design should preserve future extension points for individual-stock analysis, Kronos, TradingAgents, InsForge, and dashboard UI, but these should not dominate the first implementation.

---

## Session: April 19 — Answer Guide Rendering Fix + Course Transcription

### Goal
Fix the broken Answer Guide rendering in all course notes (Obsidian was displaying them as walls of text), update the template so future notes are generated correctly, and continue the EVC pipeline for the RAG and Agentic AI courses.

### What Was Done

#### Answer Guide Format Fix
- **Root cause identified**: `<details>/<summary>` HTML blocks suppress all markdown rendering inside them in Obsidian — bullets, tables, bold, code all collapse into unstyled prose.
- **Fix**: Replaced with Obsidian-native collapsible callout `> [!example]-` syntax. Markdown inside callouts renders fully.
- **New format**: Each answer now gets its own `#### Qn — Short Title` heading for navigation; complex answers use tables.

#### Files Changed
- ✅ `courses/zero-to-hero/01-the-spelled-out-intro-to-neural-networks-and-backpropagation-building-micrograd_VMj-3S1tku0.md` — reformatted answer guide + added new Q4 (why tanh?)
- ✅ `.claude/skills/content-summarizer/references/template-lecture-text.md` — updated canonical template: replaced all `<details>` references with callout syntax, added explicit "Forbidden Patterns" entry banning `<details>/<summary>`, updated Required Structure list and rules section
- ✅ `scripts/enhance-answer-guides.py` — new batch script: finds all `courses/**/*.md` with old `<details>` answer guides, calls Claude Haiku API to reformat each one, writes in-place

#### New Q4 Added to Micrograd Course
Pre-test Q4: *"In micrograd's neuron formula `output = tanh(sum(w_i * x_i) + b)`, why is `tanh` applied after the weighted sum? What would happen if you removed it?"*

Answer guide covers: non-linearity (layers collapse without it), bounded output (−1 to 1), zero-centering vs Sigmoid, and cheap gradient $1 - y^2$. Includes a reasons table and a linear-vs-tanh comparison table.

### What Worked
- **Obsidian callout syntax** (`> [!example]-`): fully renders markdown, tables, math, code inside the collapsed block
- **`#### Qn — Title` pattern**: gives each answer a navigable heading; Q3 table format is especially clean for the training-loop answer

### What Didn't Work
- **`<details>/<summary>` HTML**: never use this for answer guides in Obsidian — markdown does not render inside HTML blocks regardless of Obsidian version

### Next Steps
1. **Run the batch script** to fix all remaining course files with old `<details>` answer guides:
   ```bash
   python3 scripts/enhance-answer-guides.py --dry-run  # preview
   python3 scripts/enhance-answer-guides.py            # apply
   ```
2. **RAG course**: lessons 046 and 047 were dispatched for write-up; ~15 lessons still need audio download + transcription.
3. **Agentic AI course**: transcription in progress (17+ of 29 files done as of ~noon); write-up agents need to run for newly transcribed lessons.
4. **Wiki index**: verify `wiki/_index.md` has rows for all newly written lessons.

### Key Files
| File | Purpose |
| :--- | :--- |
| `scripts/enhance-answer-guides.py` | Batch-convert old `<details>` answer guides to callout format |
| `.claude/skills/content-summarizer/references/template-lecture-text.md` | Canonical template for EVC lecture write-ups — updated |
| `courses/zero-to-hero/01-*-micrograd_VMj-3S1tku0.md` | Reference file with new callout format + Q4 |

---

## Session: April 18 — yt-video-summarizer + EVC Pipeline Setup

### Goal
Extend the yt-video-summarizer skill to automatically extract all video URLs from course pages (DeepLearning.AI, Coursera, Udemy) and process them systematically with progress tracking.

### What Was Done
- ✅ Extended yt-video-summarizer with Playwright-based course enumeration and adapter system
- ✅ Progress tracking (JSON-based, resume-capable)
- ✅ Cookie support via yt-dlp browser export
- ✅ Demo structure for `courses/fine-tuning-large-language-models/`
- ✅ Playwright browsers installed (Chromium v1217)

### What Worked
- Adapter pattern for platform-specific enumeration
- Leveraging existing yt-video-summarizer pipeline
- Browser cookie export/import (mirrors encrypted-video-capture approach)

### What Didn't Work
- **DeepLearning.AI headless access**: bot protection blocks headless Playwright; needs visible browser or alternative auth
- **Simple cookie persistence**: required more sophisticated parsing for Chrome's microsecond timestamps

### Next Steps (from Apr 18, may already be done)
1. Try persistent browser context with manual login for DeepLearning.AI
2. Test Coursera/Udemy adapters
3. Connect course processor to content-summarizer for markdown generation
4. Add wiki compilation for processed courses

### Key Files
- **Skill**: `.claude/skills/yt-video-summarizer/`
- **Course processor**: `scripts/process_course.py`
- **Playwright enumerator**: `playwright/course-enumerator.mjs`
- **Platform adapters**: `playwright/adapters/`
- **Target course dir**: `courses/fine-tuning-large-language-models/`

### Quick Start
```bash
cd .claude/skills/yt-video-summarizer/
yt-dlp --cookies-from-browser chrome --cookies /tmp/course-cookies.txt --skip-download <course-url>
node playwright/course-enumerator.mjs "<course-url>" --cookies /tmp/course-cookies.txt --no-headless
python3 scripts/process_course.py "<course-url>" --course-name course-name --dry-run
```
