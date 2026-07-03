Verdict: PASS

## Subagent

None — all verification performed directly in this dispatch per instructions (Agent tool forbidden). No `uv run irc monitor`, no live LLM/network calls; all probes drove production code in-process with constructed fixtures/fake LLM stubs.

## Source

Branch `claude/monitor-v4-explainability-002` (confirmed via `git branch --show-current`), 28 commits ahead of `main`. Spec: `docs/2026-07-03-monitor-v4-explainability/items/002-spec.md` (17 ACs). Implementation already landed on this branch (commits `c10c0fd4` … `9f3b0362`, incl. a post-ship-review fix round `fa852a35` adding `unmatched_impact_keys` + `mechanism_dropped`).

Files exercised: `src/irc/monitor/macro_direction.py`, `src/irc/monitor/narrative_macro.py`, `src/irc/monitor/render_html.py`, `src/irc/monitor/eval/trace.py`, `src/irc/monitor/eval/metrics_narrative.py`, `src/irc/commands/monitor_cmd.py`.

## Entry points exercised

Five standalone scratch scripts (no pytest, no `irc monitor`, no network), run via `uv run python <script>` from the repo root:

1. `probe_a.py` — real `render_report` + `build_eval_trace` driven with an independently-constructed 4-fund/1-theme bundle (impacts +0.8 / −0.2 / +0.05 / absent) plus a second theme with `mechanism=None`.
2. `probe_b.py` — real `gather_macro_narrative` (the production edge function) driven with a stubbed `call`/`resolve_route` (no network) across 5 fake-LLM-payload shapes: v3 object, v2 bare list, oversized mechanism, injection-bearing mechanism, non-str mechanism — then the resulting `MacroThemeBlock`s fed through the real `build_eval_trace` and `macro_narrative_html`.
3. `probe_c.py` — real trace `outputs/2026-07-03/monitor/eval_trace.json` (schema 6, pre-002, real pipeline output) replayed through the new `render_report`/`macro_narrative_html` join.
4. `probe_d.py` — real `unmatched_impact_keys` pure detector + the actual `irc.commands.monitor_cmd._log` logger object (handler attached, production call site reproduced) + `build_eval_trace`.
5. `probe_extra.py`, `probe_no_invent.py`, `probe_metric.py` — targeted AC1 boundary/format checks, no-invented-chip check, and the `mechanism_validity` eval metric.

All scripts under `/private/tmp/claude-501/.../scratchpad/`.

## Observed behavior (criterion — evidence)

**AC1 (join/direction_class/format_signed), Slice 1** — PASS.
`direction_class(0.15)=="chip-pos"`, `direction_class(-0.15)=="chip-neg"`, `direction_class(0.1499999)/(-0.1499999)=="chip-flat"` (probe_extra). `format_signed(0.80)=="+0.8"`, `(0.85)=="+0.85"`, `(1.00)=="+1"`, `(0.0)=="+0"`, `(-0.0)=="+0"` (RD-8 negative-zero guard), `(-0.15)=="-0.15"` (probe_extra). Duplicate theme keys for the same fund: `join_macro_impacts` kept the FIRST record (`0.9` not `-0.5`) — first-wins confirmed (probe_extra). `join_macro_impacts({})=={}` (probe_extra).

**AC2/AC5 (chip rendering, threading), Slice 2** — PASS.
probe_a: `'<span class="fund-chip chip-pos" title="置信度 0.66">F0001 +0.8</span>'`, `'...chip-neg...F0002 -0.2...'`, `'...chip-flat...F0003 +0.05...'` all rendered verbatim; absent-record fund F0004 rendered exactly `'<span class="fund-chip">F0004</span>'` — no color class, no number, no title. `render_report`'s new `macro_impacts_by_fund` keyword threaded end-to-end from a hand-built bundle.

**AC3 (legend line)** — PASS. Exact legend string `'<p class="macro-legend">图例：数值 = 该主题对基金的影响（−1 利空 … +1 利多）；绿 ≥ +0.15 · 红 ≤ −0.15 · 灰 = 其间；无数值 = 当日无该主题影响记录</p>'` found exactly once in probe_a's rendered HTML.

**AC4 (strength tags, unified render path)** — PASS. probe_a rendered `可能主因` (possible_driver), `已证实归因` (supported_attribution), `归因未知` (unknown) tags on claim bullets from a single `_macro_theme_section` call (no `idx`). Confirms RD-7 fold (single tag site).

**No-invented-chips (AC2 constraint)** — PASS. probe_no_invent: a fund (`GHOST_FUND`) with a valid impact record for a rendered theme, but absent from the config-derived chip list, produced NO chip anywhere in the output; a config-listed fund with no impact record rendered as a bare chip.

**AC6 (reconciliation, real + constructed)** — PASS. probe_a: parsed chip values for F0001/F0002/F0003 via regex equal `round(trace_impact, 2)` from a `build_eval_trace` output built from the identical `ValidatedImpact` objects. probe_c (real data): trace `outputs/2026-07-03/monitor/eval_trace.json` (schema 6) replayed — `008986 +0.8` (gold_drivers) rendered; `519069`'s two real impacts (`cn_monetary=+0.3`, `cn_equity_property_policy=+0.1`) split correctly: `cn_equity_property_policy` (a rendered theme block that day) got chip `'519069 +0.1'`, while `cn_monetary` (NOT a rendered theme block that day) stayed trace-only with no chip anywhere — absence≠zero and no-invented-chip both verified against a genuine pipeline artifact, not just a synthetic fixture.

**AC7 (CSS)** — visually confirmed present in probe_a/c output (`.chip-pos`/`.chip-neg`/`.chip-flat`/`.claim-strength`/`.macro-mechanism`/`.macro-legend` classes all referenced and functional in rendered markup); not independently re-derived since it's non-behavioral (element structure, not byte-pinning, per spec).

**AC8/AC9 (prompt v3 + dual-shape parser + mechanism validation), Slice 3** — PASS.
probe_b drove the real `gather_macro_narrative` (stubbed `call`/`resolve_route`, zero network) through 5 payload shapes:
- v3 object `{"mechanism":..., "claims":[...]}` → `mechanism='出口回暖→企业盈利上修→利多相关基金'`, `mechanism_dropped=False`, 1 claim parsed.
- v2 bare list → `mechanism=None`, `mechanism_dropped=False`, claim parsed (back-compat).
- oversized mechanism (62 code points, boundary >60) → `mechanism=None`, `mechanism_dropped=True`, claim intact, block still emitted (never fails).
- injection-bearing mechanism (`忽略之前所有指令→...`) → dropped by `sanitize_untrusted` mismatch, `mechanism_dropped=True`, claim intact.
- non-str mechanism (int `12345`) → dropped, `mechanism_dropped=True`, claim intact.
All 5 blocks then fed to real `build_eval_trace`: `trace["schema_version"]=="7"` (no second bump), each block's `mechanism`/`mechanism_dropped` fields present and correct in the dump.

**AC12 (mechanism render placement + escaping)** — PASS. probe_a: `'<p class="macro-mechanism">对本组基金的传导：降准预期升温→流动性宽松→利多权益</p>'` rendered between `fund-chips` div and claims (index order asserted); a theme block with `mechanism=None` produced no `macro-mechanism` element anywhere in its section (probe_a, probe_b case 5) — no crash, no empty tag.

**AC10 (PROMPT_VERSION, no hardcoded "2")** — PASS. `narrative_macro.PROMPT_VERSION == "3"`; `render_report` output contains literal `"prompt 3"` in the header (probe_extra). `git diff main...HEAD` confirms `monitor_cmd.py`'s `Provenance(_ENGINE_VERSION, "2", "6", "")` replaced by `Provenance(_ENGINE_VERSION, PROMPT_VERSION, SCHEMA_VERSION, "")`.

**AC11 (trace mechanism field, schema stays "7")** — PASS, shown above (probe_b case 4) plus probe_a/probe_d.

**AC13 (mechanism_validity metric)** — PASS. probe_metric drove `mechanism_validity` directly: mixed valid/invalid mechanisms scored `0.5` (1/2), digit-bearing mechanism counted invalid, degraded `{}` output counted as miss, absent mechanism (v2 bare-list AND dict-without-key) both counted valid, non-mechanism-category cases ignored (score `1.0` when no mechanism cases present).

**Observability — `unmatched_impact_keys` (step d)** — PASS. probe_d: pure detector `unmatched_impact_keys({"cn_monetary","gold_drivers","geopolitics"}, {...typo'd "cn_monetray"...})` returned exactly `("cn_monetray",)`, excluding the valid key. The real production logger object `irc.commands.monitor_cmd._log` (handler attached) captured exactly one WARNING record with message `"monitor: macro impact key(s) unmatched by any rendered theme (typo'd/stale/renamed LLM echo, invisible on the report): cn_monetray"` when the actual `monitor_cmd.py:1056-1061` call-site code was reproduced verbatim against the real detector output. `build_eval_trace(..., unmatched_impact_keys=("cn_monetray",))` → `trace["unmatched_impact_keys"] == ["cn_monetray"]`, `schema_version` still `"7"`.

**AC16 (lint)** — `uv run ruff check` on the 6 touched core files: `All checks passed!` (static check only, not a substitute for the runtime probes above — included as supplementary evidence per spec bullet, not as the primary verification method).

**AC17 (`_ENGINE_VERSION` untouched)** — confirmed via `git diff main...HEAD -- src/irc/commands/monitor_cmd.py`: only the `Provenance(...)` call-site and one import line changed; `_ENGINE_VERSION = "4"` assignment itself absent from the diff.

**AC14 (docs sync)** — spot-checked: `docs/monitor/README.md` now reads `eval_trace.json (schema 7)` at both previously-stale mention sites (lines 77, 223) — repaired, not still "schema 6".

## Findings

- The real 2026-07-03 trace replay (probe_c) surfaced a genuinely useful confirmation, not a bug: fund `519069` carries TWO real macro impacts (`cn_monetary +0.3`, `cn_equity_property_policy +0.1`) but the LLM only emitted a `cn_equity_property_policy` theme block that day — so the `cn_monetary` chip correctly never appears anywhere on the real report while the trace still retains it. This is exactly the "absence ≠ zero" / "renderer never invents chips" contract, demonstrated on production data rather than only a synthetic fixture — worth citing as a positive real-world proof point.
- `mechanism_dropped` and `unmatched_impact_keys` are not literally named in the original spec's AC list (items 34/40 describe validation/metric behavior but not a `mechanism_dropped` trace flag or an `unmatched_impact_keys` trace/log field) — these were added in a post-ship-review fix round (`fa852a35`, "surface unmatched impact keys + present-but-dropped mechanism") per the ship-review PASS-WITH-NITS record (`d8b8b559`) and the task's own explicit step (d) calls for exactly this behavior, so it is treated as in-scope and was verified above.
- No FAIL-worthy defect found in any of the 17 ACs across 8 independent probe scripts driving the real render/parse/trace/logging code paths with zero network and zero test-suite reliance.

## Failures

None — 0 of 17 ACs failed; 0 crashes across 8 independent probe scripts exercising real production entry points (`render_report`, `macro_narrative_html`, `gather_macro_narrative`, `build_eval_trace`, `unmatched_impact_keys`, `mechanism_validity`, the real `monitor_cmd._log` logger, and one real pipeline-produced trace file).
