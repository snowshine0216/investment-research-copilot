# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Weekly research/recommendation system for gold + Mainland-China funds + ETFs (CN/HK/US via QDII proxy). A staged data pipeline (`irc` CLI) ingests market + fundamentals + web research, then produces a discovered watchlist, scores, gold-regime view, allocation, trade plan, LLM-synthesised memo, and an opportunity/discipline layer with thesis cards.

## References (read these before touching the relevant area)

- [`README.md`](README.md) — user-facing operations manual: env setup, workflows by cadence, output inspection, evidence-refresh order.
- [`CONTEXT.md`](CONTEXT.md) — **domain glossary; source of truth for terminology.** Defines `ActiveFundSnapshot`, `FundLevelSnapshot`, `Policy B`, dual-coverage gate, H3 / SAME-3 invariants, `[ref:...]` marker, live-test gate, and more. Read before touching opportunity / memo / discipline / fundamentals code.
- [`docs/diagrams/overall-workflow.html`](docs/diagrams/overall-workflow.html) — end-to-end pipeline diagram including the opportunity/discipline post-stages.
- [`docs/diagrams/stage0-ingest-to-plan.html`](docs/diagrams/stage0-ingest-to-plan.html) — detailed view of `ingest → discover → score → gold → allocate → plan` data flow.
- `docs/adr/0001..0004` — current data-contract decisions: citation model, active-fund fetch engine, failure-mode + Policy B, renderer determinism + alias policy.
- `docs/superpowers/specs/` — design specs. `docs/superpowers/plans/` — per-milestone implementation plans.

## Commands

Stack: Python 3.12+, [uv](https://docs.astral.sh/uv/), Click CLI, DuckDB, pandas, AkShare, OpenBB. Entry point: `irc = "irc.cli:main"`.

```bash
uv sync --all-extras                 # install
uv run irc init                      # write defaults to inputs/ and config/
uv run irc config validate           # re-run after editing any YAML
uv run irc run                       # default 7-stage pipeline (no research, no fundamentals refresh)
uv run irc run --from <stage>        # resume from stage: ingest|research|discover|score|gold|allocate|plan|memo
uv run irc run --only <stage>        # run a single stage
uv run irc run --resume              # resume the last halted run (today only)
uv run irc opportunity               # post-pipeline opportunity + thesis + discipline outputs
uv run irc decision                  # decision report
uv run irc ask "..."                 # grounded Q&A over today's outputs
uv run irc universe build-cn-funds   # monthly: regenerate config/universe/cn_funds.generated.yaml
uv run irc fundamentals snapshot --target all --top-n 10  # quarterly: refresh constituent filings/broker reports
DEBUG=true uv run irc <cmd>          # verbose tracebacks
```

Tests:

```bash
uv run pytest                                          # unit + integration (no network)
uv run pytest tests/path/to/test_file.py::test_name    # single test
uv run pytest -m integration                           # cross-module integration tests
uv run pytest -m live_akshare                          # hits real AkShare; requires IRC_RUN_LIVE_AKSHARE=1
RUN_LIVE_LLM_TESTS=1 uv run pytest tests/llm/test_live_smoke.py
uv run ruff check src tests                            # lint (line-length 100, target py312)
```

`tests/` mirrors `src/irc/` one-for-one. Live tests are double-gated: a `pytest.mark.<name>` marker AND an `IRC_*=1` env var must both be set ("Live test gate" in CONTEXT.md).

## Architecture

`src/irc/` is the package; layout mirrors the design spec §5.A. Each subpackage owns one stage of the pipeline plus its own types and pure transforms; I/O is confined to thin wrappers and the CLI command modules.

Stage flow (default `irc run`):

```
ingest → [research?] → discover → score → gold → allocate → plan → memo
                                                                     ↓
                                                  opportunity → decision   (run separately)
```

- `src/irc/cli.py` — Click entry, dispatches to `src/irc/commands/<stage>_cmd.py`. Commands are thin: parse args, load config, call into the stage package, write outputs.
- `src/irc/{discovery,scoring,allocation,trades,memo,opportunity,decision,gold_score (under evals),fundamentals,research,news,queries}/` — pure-logic stage packages.
- `src/irc/data/`, `src/irc/io_utils.py` — DuckDB + manifest I/O; the only place mutable filesystem state lives.
- `src/irc/llm/` — provider routing (DeepSeek, OpenRouter) driven by `config/llm.yaml`. Tasks (`memo_synthesis`, `memo_audit`, scoring rationales, thesis checks, Q&A) are looked up by task name.
- `src/irc/settings.py` — pydantic-settings; reads `.env`. `DEEPSEEK_API_KEY` is required for full validation; `irc init`/`irc config validate` fall back to raw env so they work without secrets.
- `src/irc/http_proxy.py` — single `IRC_HTTPS_PROXY` is applied uniformly to LLM, web-search, Jina extractor, and DXY-via-EastMoney calls. Other AkShare calls stay direct (CN domains).
- `src/irc/pipeline_state.py`, `pipeline_halt.py`, `pipeline_outputs.py` — orchestrator state, halt-and-resume, output contracts.
- `src/irc/observability/` — structured logging; `setup_logging(debug=...)` is called at CLI startup.

Outputs are date-partitioned at `outputs/<YYYY-MM-DD>/`. Atomic writes use the `.tmp.{pid} → os.replace` pattern.

Data flows through frozen dataclasses / pydantic models defined alongside their stage (`*/types.py` or `schemas/`). Snapshot caches live under `data/fundamentals/<quarter>/...` keyed by **provider-declared disclosure quarter**, not calendar quarter.

## Conventions (enforced)

These rules come from the project's `.cursor`/AGENTS guidance, ADRs, and global FP guidance. Apply them when writing or modifying code.

- **TDD.** Red → green → refactor. Never write implementation without a failing test first. Test file mirrors source (`foo.py` → `tests/.../test_foo.py`).
- **Functional, immutable.** Pure functions, `const`-style by default. Never mutate arguments. Use spread/`map`/`filter`/`reduce`-style transforms over in-place mutation. Fluent builders return new instances (frozen dataclass + `dataclasses.replace`, or `{**state, key: val}`-equivalent for dicts).
- **Effects at edges.** I/O (filesystem, network, LLM, AkShare/OpenBB) is confined to thin wrapper functions and the `commands/` layer. Stage cores are pure and unit-testable without mocks.
- **Size budget.** Files < 200 lines, functions < 20 lines (ideal). Extract helpers rather than nest > 3 levels.
- **No shared mutable module state.** No globals; pass dependencies explicitly through function signatures.
- **Secrets in `.env` only.** YAML configs reference env var names; never inline keys.
- **Skill routing** (from `AGENTS.md`): match user requests to skills via the Skill tool when one applies.

## Things you'll trip over if you don't know them

Pointers only — the rules themselves live in CONTEXT.md / the named ADR.

- `irc opportunity` reads **cached** evidence; it does not fetch live. Refresh order is fixed: see README "Evidence refresh order".
- `fundamentals snapshot --target all` is **sequential** (one target × N constituents) and takes 5–15 min. Deliberately not part of `irc run` — treat as a quarterly job.
- Active-fund publishability is decided by **Policy B** (ADR 0003 / CONTEXT.md "Failure-mode + audit policy"). `OpportunityRow.thesis_state` is set **only** by `derive_thesis_from_evidence`, never by Policy B.
- **H3 universal gapped-row invariant** and **SAME-3 invariant** govern the `_write_opportunity_outputs` partition and the picks/evidence-pool/discipline citation-set equality. See CONTEXT.md "Renderers + alias-builder" and ADR 0004.
- **Citation ID format** is locked at 16 hex chars; match regex `\[ref:[0-9a-f]{16}\]` (ADR 0001).
- **`基金概况` indicator is forbidden** in production fetch code — enforced by an acceptance test that greps for the literal string. Information-leg citations come only from `fetch_fund_announcements`.
- `fetch_budget_exhausted` is a **fatal sentinel** at the `_write_opportunity_outputs` boundary — should have been raised pre-build by `FetchBudgetExceeded`.
