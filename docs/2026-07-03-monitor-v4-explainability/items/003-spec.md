# Item 003 — WS-3 Divergence detail (P6)

**Run:** monitor-v4-explainability · **Source:** MASTER-SPEC item 003 / source spec §2 P6, §3 WS-3, §4 bullet 3
**Size:** small · **Schema-neutral** (6→7 bump is carried by item 001) · **No `_ENGINE_VERSION` change**

## Goal

Replace the fixed divergence caveat strings on fund-card risk blocks with parametrized detail
that names the disagreeing factors and their signed values. Today
`render_cards.risk_block_html` (call site verified at `src/irc/monitor/render_cards.py:102`)
maps each `SignalRecord.divergence_codes` entry through the static
`render_factors._DIVERGENCE_CAVEATS` table, so the reader sees `因子分歧较大：各因子方向/强度不一致`
without knowing which factors disagree or by how much — even though
`SignalRecord.contributions` (carrying every present factor's value) sits right next to the
call site. This item adds one new pure function
`divergence_caveat_detail(code, contributions)` in `src/irc/monitor/render_factors.py`
that renders the P6-locked detail formats, keeps the static map as fallback for unknown
codes / missing factors, and swaps the single call site. Render-only: no trace fields, no
signal-math change, no other consumers exist (grep-verified: `divergence_caveat` has exactly
one production caller).

## Acceptance criteria

Each independently verifiable:

1. **New pure function.** `divergence_caveat_detail(code: str, contributions: tuple[FactorContribution, ...]) -> str`
   exists in `src/irc/monitor/render_factors.py`; deterministic, no I/O, does not mutate
   its arguments (unit-testable without mocks).
2. **Pairwise formats (exact strings, ASCII `{:+.2f}` signs, 2dp).** With both factors present
   in `contributions`:
   - `trend_macro_conflict` → `趋势与宏观背离：趋势 -0.75（价格动能向下） vs 宏观 +0.62（新闻/宏观偏多）`
   - `trend_valuation_conflict` → `趋势与估值背离：趋势 +0.45（价格动能向上） vs 估值 -0.80（估值偏贵）`
   - `valuation_flow_conflict` → `估值与资金流背离：估值 +0.80（估值偏便宜） vs 资金流 -0.45（资金净流出）`
   Chinese display names locked: trend→趋势, macro_tilt→宏观, valuation→估值, flow→资金流.
   Sign glosses locked (per factor: value < 0 → negative gloss, else positive gloss):
   trend 价格动能向上/价格动能向下 · macro_tilt 新闻/宏观偏多/新闻/宏观偏空 ·
   valuation 估值偏便宜/估值偏贵 · flow 资金净流入/资金净流出.
   Factor order within each line follows the code name (trend before macro, etc.).
3. **`low_factor_agreement`, mixed-sign trigger.** When contribution values have both a
   positive and a negative member: every present factor listed, grouped by sign — group
   order fixed 偏多 ↔ 偏空 (then 中性), members within each group in `CANONICAL_FACTOR_ORDER` —
   raw (English) factor names per the locked example:
   `因子分歧较大：偏多 heat +0.30、macro_tilt +0.62 ↔ 偏空 trend -0.75`.
   Exact-zero factors (no sign) append as a trailing `中性` group (`… ↔ 偏空 trend -0.75、中性 constituent +0.00`)
   so "every present factor" holds; group omitted when empty.
4. **`low_factor_agreement`, dispersion-only trigger.** When signs are NOT mixed and
   `statistics.pstdev(values) >= threshold`: `因子分歧较大：强度离散 σ=0.56 ≥ 0.5`
   (σ = pstdev of the contribution values, 2dp). The rendered threshold comes from a named
   module constant in `src/irc/monitor/signal.py` (the existing inline `0.5` literal in
   `_divergence`, promoted to a name and imported by the renderer) — the display can never
   drift from the gate. Promoting the literal changes no behavior (`tests/monitor/test_signal.py`
   green unchanged).
5. **Fallback paths (static map retained).** `divergence_caveat_detail` returns the exact
   current `_DIVERGENCE_CAVEATS` string when: a pairwise code's required factor is absent
   from `contributions`; `low_factor_agreement` has fewer than 2 contribution values; or the
   dispersion-only branch finds recomputed σ below threshold (inconsistent inputs — never
   render a false `σ ≥ 0.5` claim). Unknown code → `escape(code)` passthrough. The existing
   public `divergence_caveat(code)` function is retained unchanged as the fallback carrier;
   the exact-string tests at `tests/monitor/test_render_factors.py:13-26` still pass unmodified.
6. **Call-site swap.** `risk_block_html` in `src/irc/monitor/render_cards.py` (the caveats
   comprehension, currently line 102) calls `divergence_caveat_detail(code, rec.contributions)`;
   import at line 5 updated. No other call site exists or is added.
7. **No bare static string when data is available.** A `tests/monitor/test_render_cards.py`
   test builds a `SignalRecord` with divergence codes AND the required contributions and
   asserts the risk block contains the factor names with signed values and does NOT contain
   `各因子方向/强度不一致` (source-spec §4 acceptance bullet 3).
8. **HTML safety.** Factor names interpolated into the detail string are passed through
   `html.escape` (they land inside `<li>` unescaped by the caller); a test with a hostile
   factor name (e.g. `<b>`) asserts escaping.
9. **Schema/engine neutrality.** No edits under `src/irc/monitor/eval/`; no `schema_version`
   or `_ENGINE_VERSION` change; `git diff` for this item touches only `render_factors.py`,
   `render_cards.py`, the named-constant promotion in `signal.py`, and their mirror tests.
10. **TDD + hygiene.** Tests written first (red→green) in `tests/monitor/test_render_factors.py`
    and `tests/monitor/test_render_cards.py`; `uv run ruff check src tests` clean;
    `uv run pytest tests/monitor/` green; `tests/commands/` per-file only if touched (not
    expected — no command-layer edit); both source files stay < 200 lines, functions < 20 lines.

## Non-goals

- No change to divergence **trigger logic** in `signal._divergence` (thresholds, code set,
  firing conditions) — the constant promotion in AC-4 is a pure rename of an existing literal.
- No trace/schema additions (`gate.reason`, `mechanism`, `board_pe_freshness` belong to
  items 001/002/004; the single 6→7 bump is item 001's).
- No `_ENGINE_VERSION` bump (P9: render-only class).
- No drilldown (`render_drilldown.py`) or overview/今日速览 changes; no 数据健康 dark-factor counts (spec §5).
- No localization of the raw factor names in the `low_factor_agreement` list (locked example
  uses `heat`/`macro_tilt`/`trend` as-is); no confidence values on the caveat line.
- No σ suffix on the mixed-sign grouped form (the σ sentence is the dispersion-ONLY wording).
- No reuse of `annotate.factor_annotation` for the parenthetical glosses (see resolved Q1).

## Constraints

- **Purity/immutability:** the new function is pure (no I/O, no logging, no mutation);
  gloss/display-name tables are module-level immutable constants.
- **Public-API stability:** `divergence_caveat`, `factor_table_html`, `returns_table_html`,
  `CANONICAL_FACTOR_ORDER`, and all `render_cards` exports keep their signatures.
  `divergence_caveat_detail` is additive.
- **Determinism:** same inputs → byte-identical output; formatting via Python `{:+.2f}`
  (ASCII sign) and fixed-order iteration (`CANONICAL_FACTOR_ORDER`); no locale-dependent calls.
  Report renderer determinism per ADR 0004 is preserved.
- **Dependencies:** stdlib only (`statistics.pstdev`, `html.escape` — both already used in
  the touched modules); no new packages.
- **Performance:** trivial — pstdev over ≤ 6 floats per fund per code, render path only.
- **Security:** untrusted-ish interpolations (factor names) HTML-escaped; unknown codes stay
  escaped-passthrough (existing behavior).
- **Size budget:** `render_factors.py` grows from 80 to an estimated ~135–150 lines (< 200);
  helpers split so no function exceeds ~20 lines.

## Open questions resolved during brainstorming (with rationale)

- **Q1 — Gloss source: reuse `annotate.factor_annotation` or a new static map?** New local
  per-(factor, sign) gloss map. `factor_annotation` emits banded phrases (强上行/横盘/下行)
  plus a `·新闻面·易变` volatility mark on macro_tilt — neither matches the P6-locked example
  text (`价格动能向下`, `新闻/宏观偏多`), and the mark is noise inside a parenthetical. The
  locked examples define simple sign glosses, so a 4-factor × 2-sign table is the faithful
  minimal design. Glosses for the two factors P6 left "analogous" (valuation, flow) are fixed
  in AC-2 following the same pattern and `annotate.py` vocabulary (便宜/偏贵, 净流入/净流出).
- **Q2 — How can the function detect the dispersion-only trigger without receiving σ?**
  Recompute from `contributions`: `signal._contributions` copies `s.value` verbatim from the
  same `present` tuple `_divergence` reads, so `pstdev([c.value ...])` and the mixed-sign
  check reproduce the gate's inputs exactly. Pure, deterministic, no signature change beyond
  the locked one.
- **Q3 — σ threshold lives as an inline `0.5` literal in `signal._divergence`; duplicate it?**
  No — promote to a named module constant in `signal.py` and import it in the renderer
  (precedent: `annotate.py` imports `_FAMILY_OF` from `signal`). Hardcoding `0.5` twice
  invites silent drift between the gate and the rendered `≥ 0.5` claim. No behavior change.
- **Q4 — Mixed-sign AND σ ≥ 0.5 both true: which form?** Grouped-by-sign. P6 reserves the σ
  sentence for the dispersion-only trigger; naming the disagreeing factors is strictly more
  informative when signs actually conflict.
- **Q5 — Zero-valued factors in the grouped form?** Trailing `中性` group. P6 says "every
  present factor grouped by sign"; zero has no sign, and silently dropping a factor would
  contradict "every present factor". Rare in practice (values are floats), cheap to render.
- **Q6 — Typographic minus (U+2212) in the spec examples vs ASCII?** ASCII via `{:+.2f}`.
  The whole report formats numbers with Python `+`-format (`decision_line_html`,
  `returns_table_html`); the `−` glyph is document typography, not a byte-level requirement.
  Tests assert ASCII exact strings.
- **Q7 — Keep or delete the old `divergence_caveat`?** Keep unchanged. It IS the "static map
  retained as fallback" from the locked decision, its exact-string tests double as the
  fallback contract, and removing it would churn tests for zero benefit.
- **Q8 — Ordering inside sign groups?** `CANONICAL_FACTOR_ORDER`. The locked example lists
  `heat` before `macro_tilt`, which matches canonical order (it also happens to match
  alphabetical, but canonical is the report-wide convention — `factor_table_html` already
  iterates it). Unknown names (defensive) append after canonical ones in input order.
- **Q9 — Defensive honesty on inconsistent inputs (dispersion-only branch, recomputed σ below
  threshold)?** Fall back to the static string rather than render a false `σ=0.32 ≥ 0.5`.
  Same class as the missing-factor fallback the locked decision already mandates.
- **Q10 — Call-site line number:** verified current as of this spec — the comprehension is
  exactly `render_cards.py:102` (`caveats = [f"<li>{divergence_caveat(code)}</li>" for code in rec.divergence_codes]`),
  with the import at line 5. Recorded per the item ground rules; the implementer re-verifies
  before editing (001 lands after 003 in execution order, so drift is unlikely but possible).

**None unresolved** — all questions closed from MASTER-SPEC, the source spec, and the code.
