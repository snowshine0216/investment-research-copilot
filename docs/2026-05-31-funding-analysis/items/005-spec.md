# Item 005 — Bull/bear debate behind `--adversarial`

> Run: `funding-analysis` · Source: `docs/funding-analysis-review.md` → "## Recommended changes" #5
> Status: spec · Authored 2026-05-31 (autonomous run, no user — decisions made and recorded below)
> Depends on: **nothing** (dependency-scan: "purely additive … depends on nothing, blocks nothing").
> Final item of the backlog.

## Goal

The review's recommendation #5: IRC already runs the LLM "as skeptic, not oracle" — a `thesis_falsify`
half that steelmans the bear case against a derived `thesis_state`. Borrowing the TradingAgents
bull-vs-bear pattern, item 005 adds the **defend** half: a sibling `thesis_defend` LLM task that
steelmans the **bull** case for the same thesis, and an optional `--adversarial` flag on
`irc opportunity` that, when set, runs **both halves** to produce a paired bull/bear debate. The
debate is a **reasoning aid only** — an advisory artifact a human reads alongside the report. It is
emitted as a **separate output file** and **never** feeds `thesis_state` (owned exclusively by
`derive_thesis_from_evidence`, ADR 0003), Policy B publishability, `valuation_state`/`core_dca`, the
deterministic memo pillars (§2/§3/§5/§7), the citation surface, H3/SAME-3, or any state/gate/classifier.
The flag defaults **off**: when absent, the opportunity stage's outputs are byte-identical to today
(there is no thesis-LLM call on the default path — `thesis_falsify` is a registered-but-unwired task
slot today, so both halves are first wired here, behind the flag). Opt-in, so the default LLM cost
is unchanged; `--adversarial` roughly **doubles** the per-row thesis-LLM calls (defend + falsify).

## Context grounding (verified, not assumed)

- **`thesis_falsify` is registered but has NO production call-site.** `config/llm.yaml` (and the
  template `src/irc/templates/config/llm.yaml:15`) declares `thesis_falsify: { provider: deepseek,
  model: deepseek-reasoner }`, but a grep of `src/irc/**/*.py` finds **zero** references to the
  literal `"thesis_falsify"`. The opportunity stage today makes **no thesis-LLM call**. Therefore
  item 005 wires BOTH halves for the first time, behind the flag — there is no pre-existing default-path
  falsify call to preserve. (`grep -rn '"thesis_falsify"' src/` → empty; `interactive_query`/
  `scoring_rationale` ARE wired, via `ask_cmd.py:56` / `score_cmd.py:56`, and are the live precedent
  for the task-lookup-by-name mechanism.)
- **The structural template is `research/falsification.py`.** `generate_falsification(thesis_summary,
  route) -> FalsificationResult` (`src/irc/research/falsification.py`) is the exact shape to mirror:
  a frozen-dataclass result, a system prompt asking for JSON, `call_chat(route, messages, …)`,
  `json.loads`, per-item sanitisation (`_sanitize_condition`: strip newlines, `[:300]` cap), and a
  graceful `except Exception: return <empty>` degrade. `thesis_defend` reuses this skeleton verbatim
  (it argues FOR instead of listing falsifiers).
- **Task-lookup-by-name + route resolution.** `resolve_route(task, config) -> ResolvedRoute`
  (`llm/gateway.py:14`) raises `KeyError` on an unknown task; `call(...)` / `call_chat(route, …)` are
  the effect entry points. `LLMConfig` (`schemas/llm.py:78-92`) requires only `REQUIRED_TASKS =
  ("memo_synthesis","memo_audit")`; **extra tasks are allowed**, so adding `thesis_defend` cannot
  break config validation. Mock pattern: `@patch("<module>.call_chat")` returning a `MagicMock(text=…)`
  (`tests/research/test_falsification.py`).
- **`run_opportunity` already has the LLM config in scope.** `load_repo_configs(root)` returns a
  bundle with `bundle.llm: LLMConfig` (`config_loader.py:88,125`); `run_opportunity`
  (`commands/opportunity_cmd.py:1478`) already calls it. Threading a route into the debate is trivial
  and adds no new config plumbing.
- **The debate's inputs already exist on `OpportunityRow`.** `OpportunityRow` (`opportunity/types.py:149`)
  carries `name_cn`, `thesis_state`, `opportunity_reason`, and `thesis_evidence` — the exact "thesis
  card + evidence" the two halves argue over. No new producer fields are required.
- **`--adversarial` attaches at the SAME layer as `--rebuild-fundamentals`.** `irc opportunity`
  (`cli.py:115-131`) declares `--repo-root`, `--output-dir`, `--limit`, `--rebuild-fundamentals` as
  `is_flag`/options and threads them into `run_opportunity(...)`. `--adversarial` is a new
  `is_flag=True, default=False` option threaded the same way.
- **The opportunity write boundary.** `_write_opportunity_outputs` (`commands/opportunity_cmd.py:1211`)
  emits the five canonical artifacts (`opportunity_report.json`, `thesis_cards.yaml`,
  `discipline_report.md`, `rejections.json`) via `atomic_write_text` after the H3 partition. The debate
  file is a **sixth, additive** artifact written here only when the flag is on — it does NOT enter the
  H3 partition, the cards/report/discipline buckets, the citation gate, or `rejections.json`.
- **Reason-only / advisory precedent.** Items 001/002/004 (`consensus_upside_pct`, `pe_ttm`/`pb`,
  `KeyRatios`) all establish the "plain output, drives no state/gate/classifier, no `ThesisEvidence`,
  no `[ref:...]`" posture (CONTEXT.md `consensus_upside_pct` / `KeyRatios`; ADR 0009). The debate is the
  LLM-prose analogue: advisory, citation-free, state-free.
- **Memo pillar locks.** Memo §2/§3/§5/§7 are deterministic; the LLM is kept verbatim only between the
  `IRC_*_BEGIN/END` markers (MEMORY.md "Memo pillar locks"). The debate file is **not** a memo input and
  is **never** spliced into a deterministic pillar — `irc memo` does not read it.

## Decisions (auto-resolved; brainstorming, no user in loop)

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| D1 | `thesis_defend` task contract — model? | **`{ provider: deepseek, model: deepseek-reasoner }`**, identical to `thesis_falsify`. | The master-spec frames it as the falsify **sibling**; a reasoner-class model fits an adversarial steelman; symmetry keeps the debate balanced (same model both sides). Reuse, do not diverge. |
| D2 | `thesis_defend` inputs | The same thesis card the falsify half sees: `name_cn`, `thesis_state`, `opportunity_reason` (the derived thesis summary), and the top-N `thesis_evidence` summaries — all read off the already-built `OpportunityRow`. | These are exactly what `derive_thesis_from_evidence` produced; the debate argues over the derived state, never recomputes it. No new producer field. |
| D3 | `thesis_defend` prompt job | Steelman the **bull** case: given the thesis + evidence, argue why the long-term logic is alive — mirroring how falsify steelmans the bear case (lists conditions that would invalidate it). Output JSON. | Direct mirror of `generate_falsification`'s "list 3-5 falsification conditions". A symmetric bull list (`arguments`) is the minimal divergence. |
| D4 | `thesis_defend` output shape | Frozen dataclass `DefenseResult(arguments: tuple[str, ...])`, parallel to `FalsificationResult(conditions: tuple[str, ...])`. Same `_MAX_*` caps + per-item sanitise + `except → empty` degrade. | "Reuse falsify's structure as the template — do NOT invent a divergent shape." Same field count, same degrade, same sanitisation. |
| D5 | Where does `--adversarial` attach + default | A new `@click.option("--adversarial", is_flag=True, default=False)` on the `opportunity` command (`cli.py`), threaded into `run_opportunity(..., adversarial=False)`. **Default OFF.** | Same layer as `--rebuild-fundamentals`. Additive; absent ⇒ no behaviour change. |
| D6 | What does the flag gate | When **on**: for each **publishable** row, run BOTH `thesis_defend` AND `thesis_falsify`, pair them, and write one debate artifact. When **off** (default): run **neither** — zero thesis-LLM calls (today's behaviour). | Default path stays byte-identical (no falsify call exists today). The debate is the paired bull/bear, not falsify-alone. |
| D7 | Where the debate surfaces | A **new advisory file** `thesis_debate.md` (Markdown, one section per row: `### {iid} {name_cn}` → derived `thesis_state` → 看多 (defend) bullets → 看空 (falsify) bullets) written via `atomic_write_text` in `_write_opportunity_outputs`, **only** when the flag is on. NOT added to the 5 canonical artifacts, NOT a memo input, NOT a thesis-card field. | Separate file = zero risk of leaking into H3 partition, SAME-3 citation-set equality, `rejections.json`, memo pillars, or the publishable-set lockdown. Advisory by construction. |
| D8 | Does the debate touch any state / citation? | **No.** It reads `OpportunityRow` (post-derivation) and emits prose only. It produces no `ThesisEvidence`, no `[ref:...]`, no `evidence_gaps`/`advisory_gaps`, and changes no `thesis_state`/`valuation_state`/`opportunity_state`/`core_dca`/Policy-B verdict. | ADR 0003: `thesis_state` is owned solely by `derive_thesis_from_evidence`; Policy B sets publishability, never state. The debate is downstream of both and read-only w.r.t. them. |
| D9 | Pure vs effect split | Pure: prompt construction, JSON parse/sanitise, pairing two results into a `ThesisDebate`, and the `compose_thesis_debate_markdown(debates) -> str` renderer — all unit-testable without the LLM. Effect: the two `call_chat` calls, confined to a thin wrapper + the command layer. | CLAUDE.md "effects at edges"; mirrors `falsification.py` (pure result type + single effectful call). |
| D10 | Which rows get a debate | **Publishable rows only** (the H3 `evidence_gaps == ()` set, i.e. `publishable_rows` after the citation gate). Gapped rows have not earned a thesis conclusion, so debating them is meaningless and would risk leaking gapped-row context. | Mirrors H3: only rows that earned a `thesis_state` get downstream treatment. Keeps debate cost bounded to the publishable set. |
| D11 | Module placement | New pure module `src/irc/opportunity/debate.py` (the `ThesisDebate`/`DefenseResult` types, prompt builders, JSON parse, pairing, markdown renderer); the two effectful `call_chat` invocations live in a thin runner in the same module (mirroring `falsification.py` having its one `call_chat`) and are orchestrated from `commands/opportunity_cmd.py`. No new ADR (additive, high-reversibility, no new architectural decision — flag-gated opt-in). | Keeps debate logic isolated, files <200 lines. CONTEXT.md gains a `thesis_debate` / `--adversarial` glossary entry. |
| D12 | Per-row LLM failure handling | Each half degrades to an empty result on any exception (mirroring `generate_falsification`); a row whose both halves are empty renders a `（本行未能生成辩论）` placeholder line. **One row's LLM failure never aborts the run** and never blocks the 5 canonical artifacts (those are already written before/independently of the debate file). | Effects-at-edges robustness; the debate is advisory — a failed call must not break the deterministic outputs. |

## Acceptance criteria

1. **AC1 — `thesis_defend` task registered.** `config/llm.yaml` AND `src/irc/templates/config/llm.yaml`
   gain `thesis_defend: { provider: deepseek, model: deepseek-reasoner }` (model identical to
   `thesis_falsify`). `resolve_route("thesis_defend", cfg)` returns a `ResolvedRoute` with
   `model == "deepseek-reasoner"`; `LLMConfig.model_validate(...)` still passes (extra tasks allowed).
2. **AC2 — `--adversarial` flag added, default off.** `irc opportunity --help` lists `--adversarial`
   (`is_flag`, default `False`); `run_opportunity` gains an `adversarial: bool = False` parameter
   threaded from the CLI. No other command gains the flag.
3. **AC3 — flag-off byte-identical to today.** A test runs the opportunity stage twice on the same
   fixture — once on `main`-equivalent code, once with item 005 merged and `--adversarial` absent —
   and asserts the five canonical artifacts (`opportunity_report.json`, `thesis_cards.yaml`,
   `discipline_report.md`, `rejections.json`, and the memo when run) are byte-identical, AND that
   **no thesis-LLM call is made** on the default path (assert `call_chat` is not invoked when the flag
   is off, via a patched/spy LLM). `thesis_debate.md` is **not written** when the flag is off.
4. **AC4 — `DefenseResult` mirrors `FalsificationResult`.** A frozen dataclass
   `DefenseResult(arguments: tuple[str, ...])` exists (single tuple field, parallel to
   `FalsificationResult(conditions: tuple[str, ...])`), with the same item-cap + per-item sanitise
   (strip newlines, length cap) + `except Exception → DefenseResult(arguments=())` graceful degrade.
   A test mocks `call_chat` (returning `MagicMock(text='{"arguments": ["…","…"]}')`) and asserts the
   parsed `arguments`; a second test asserts invalid JSON → `arguments == ()`.
5. **AC5 — debate runs both halves only when on.** With `--adversarial`, for each publishable row both
   `thesis_defend` and `thesis_falsify` are invoked (verified by counting mocked `call_chat` calls:
   `2 × n_publishable_rows`); with the flag off, **zero** thesis-LLM calls. Gapped rows get no debate.
6. **AC6 — debate surfaces as an advisory file only.** When on, `thesis_debate.md` is written via
   `atomic_write_text` to the output dir with one section per publishable row
   (`### {iid} {name_cn}` + derived `thesis_state` + 看多/看空 bullets). The file is NOT one of the five
   canonical artifacts, is NOT referenced by `irc memo`, and adds NO field to `thesis_cards.yaml` /
   `opportunity_report.json` / `discipline_report.md` / `rejections.json`.
7. **AC7 — no state / gate / classifier / Policy-B / `thesis_state` change.** A regression test asserts
   that for a fixture run, every `OpportunityRow`'s `thesis_state`, `valuation_state`,
   `product_quality_state`, `heat_state`, `opportunity_state`, `evidence_gaps`, `advisory_gaps`, and the
   Policy B verdict are byte-identical with vs without `--adversarial`. No edit to
   `derive_thesis_from_evidence`, `opportunity/states.py` classifiers, `valuation_fundamental.py`,
   `policy_b.py`, or `compose_opportunity_state`.
8. **AC8 — deterministic memo pillars untouched.** A test asserts the memo §2/§3/§5/§7 deterministic
   pillars and the `IRC_*_BEGIN/END` verbatim regions are byte-identical with vs without the debate file
   present; `irc memo` does not read `thesis_debate.md`. (The debate is not a memo input.)
9. **AC9 — no new citation / citation-invariants preserved.** The debate produces no `ThesisEvidence`
   and no `[ref:...]` marker; a test greps `thesis_debate.md` for `\[ref:[0-9a-f]{16}\]` and asserts
   the debate adds none of its own (it may quote evidence prose, but emits no new citation id). SAME-3,
   dual-coverage, H3 partition, and the publishable-set lockdown tests stay green.
10. **AC10 — pure logic unit-testable without the LLM.** Prompt construction, JSON parse/sanitise, the
    pairing into `ThesisDebate`, and `compose_thesis_debate_markdown(debates) -> str` are pure and have
    unit tests that never touch the network/LLM (no `call_chat`). `compose_thesis_debate_markdown` is
    deterministic: same `ThesisDebate` tuple in → byte-identical Markdown out (asserted by calling
    twice).
11. **AC11 — LLM call is an effect at the edge; live test double-gated.** The two `call_chat`
    invocations live in a thin runner; unit tests mock them. A live LLM test is added to
    `tests/llm/test_live_smoke.py` (or a sibling) gated on `RUN_LIVE_LLM_TESTS=1` AND `DEEPSEEK_API_KEY`
    (the project's existing live-LLM convention), asserting `resolve_route("thesis_defend", cfg)`
    resolves and a real `call_chat` returns parseable JSON. Default `pytest` skips it.
12. **AC12 — per-row failure isolation.** A test with a `call_chat` that raises for one row asserts the
    run still completes, the five canonical artifacts are still written, and that row renders the
    `（本行未能生成辩论）` placeholder rather than aborting the debate file.
13. **AC13 — cost is opt-in.** A test/asserted note documents that `--adversarial` issues
    `2 × n_publishable_rows` thesis-LLM calls and the default path issues **0**; the cost doubling
    applies only under the flag.
14. **AC14 — size + TDD budget.** New code lives in files <200 lines, functions <20 lines (ideal);
    every behaviour landed red-first; tests mirror source (`opportunity/debate.py` →
    `tests/opportunity/test_debate.py`). CONTEXT.md gains a `thesis_debate` / `--adversarial` entry.

## Non-goals (explicit)

- **No trading signal.** The debate is a reasoning aid, NOT a buy/sell/score/factor/ranking input.
  (Scope boundary — A-share quant lives in `ashare-quant`; master-spec OUT-OF-SCOPE for 005.)
- **No change to `thesis_state` derivation.** `derive_thesis_from_evidence` remains the sole owner of
  `thesis_state` (ADR 0003); the debate reads it, never sets it.
- **No change to Policy B publishability** (ADR 0003), the H3 / SAME-3 invariants (ADR 0004), the
  citation surface (ADR 0001), or `valuation_state` / `core_dca` / any state classifier.
- **No change to the deterministic memo pillars** (§2/§3/§5/§7) or the `IRC_*_BEGIN/END` verbatim
  regions; the debate file is not a memo input.
- **Not on by default.** Absent `--adversarial`, behaviour and cost are unchanged; no thesis-LLM call.
- **No new canonical artifact / no new `OpportunityRow` / `ThesisCard` / report field.** The debate is a
  standalone advisory file only.
- **No re-running the falsify half on the default path.** Today there is no falsify call; item 005 does
  not add one to the default path — both halves are flag-gated.
- **No multi-round debate / no judge / no convergence loop.** A single bull pass + single bear pass,
  paired and rendered. (TradingAgents' multi-turn debate is deferred; YAGNI for a reasoning aid.)

## Constraints (enforced)

- **TDD** red→green→refactor; test file mirrors source (`debate.py` → `tests/opportunity/test_debate.py`).
- **Functional / immutable.** `DefenseResult`, `FalsificationResult`-shape, and `ThesisDebate` are frozen
  dataclasses; prompt builders, JSON parse/sanitise, pairing, and the markdown renderer are pure.
- **Effects at edges.** The only new effect is `call_chat` (defend + falsify), confined to a thin runner
  + the `commands/` layer; the pure core is mockless-testable.
- **Size budget.** Files <200 lines, functions <20 lines (ideal).
- **LLM task-by-name registry.** `thesis_defend` is resolved via `resolve_route("thesis_defend", cfg)`;
  no inline model strings. Secrets stay in `.env` (`DEEPSEEK_API_KEY`); YAML references the env var name.
- **Citation ID** 16 hex unchanged; the debate introduces no `[ref:...]` token. `\[ref:[0-9a-f]{16}\]`
  contract untouched.
- **`基金概况` forbidden** — N/A (no new fetch); the grep acceptance test stays green.
- **Memo pillar locks** — the debate file is never spliced into a deterministic pillar or a verbatim
  marker region.
- **Live-test gate** — the live LLM test is double-gated (marker/skipif + `RUN_LIVE_LLM_TESTS=1` +
  `DEEPSEEK_API_KEY`), matching the existing `tests/llm/test_live_smoke.py` convention.

## Open questions resolved during brainstorming

All recorded in the **Decisions** table (D1–D12). The load-bearing ones:

- **`thesis_falsify` is unwired today** (no call-site) — so item 005 wires BOTH halves, behind the flag;
  there is no default-path falsify call to preserve, which is what makes flag-off byte-identical
  trivially true (D6, AC3).
- **`thesis_defend` mirrors `FalsificationResult` exactly**: frozen dataclass, single tuple field,
  deepseek-reasoner, `call_chat` + JSON + sanitise + graceful degrade (D1–D4, D9).
- **`--adversarial` attaches on `irc opportunity`, default off**, threaded like `--rebuild-fundamentals`
  (D5).
- **The debate surfaces as a separate `thesis_debate.md`**, advisory-only, publishable-rows-only, never
  touching states/Policy-B/citations/memo pillars (D7, D8, D10).
- **Cost doubles only under the flag** (`2 × n_publishable_rows`); default cost unchanged (D6, AC13).

## Could-not-fully-resolve (grill targets)

- **G1 — debate-file format: Markdown vs YAML/JSON.** I chose `thesis_debate.md` (human-readable, matches
  `discipline_report.md`'s advisory-prose register). If the planner wants a machine-readable
  `thesis_debate.yaml` (parallel to `thesis_cards.yaml`) for downstream tooling, that is a renderer swap —
  grill to confirm the consumer is a human reader, not a tool.
- **G2 — does `thesis_falsify` keep its own result type or reuse one?** `thesis_falsify` is unwired, so
  there is no existing falsify *call-site* in the opportunity stage to reuse — only
  `research/falsification.py`'s `generate_falsification`/`FalsificationResult` (which targets *theme*
  theses, not constituent thesis cards). Decision leans: add a thin opportunity-stage `generate_defense`
  + `generate_falsification`-equivalent pair in `debate.py` rather than reaching into `research/`. Grill
  to confirm we are NOT reusing the `research/falsification.py` theme-falsifier verbatim (its prompt is
  theme-shaped, not card-shaped) and that a fresh card-shaped falsify runner is acceptable scope.
- **G3 — debate input granularity: fund-row-level vs constituent-level.** I chose **row-level** (one
  debate per publishable `OpportunityRow`, arguing over its derived `thesis_state` + top-N evidence).
  A constituent-level debate (one per holding) would be far more LLM-expensive and is YAGNI for a
  reasoning aid. Grill to confirm row-level is the intended granularity.
- **G4 — flag interaction with `--limit` / canonical-path rules.** `--limit` is rejected on canonical
  `outputs/<today>/` paths. Is `--adversarial` permitted on canonical paths (it does not change the
  publishable set, only adds an advisory file)? Decision leans **yes** (it is purely additive and
  cannot corrupt the canonical artifacts). Grill to confirm no canonical-path restriction is wanted.
- **G5 — temperature / determinism of the LLM halves.** `generate_falsification` uses `temperature=0.2`;
  `respond_to_query` likewise. The debate prose is inherently non-deterministic (LLM), so the
  byte-stability ACs (AC3) apply to the **default path only** (flag off ⇒ no file). Grill to confirm the
  flag-on `thesis_debate.md` is explicitly exempt from two-run byte-equality (it is an LLM artifact).
