Verdict: PASS

## Verification: QDII premium memo surfacing (item 003)

**Branch:** `claude/instrument-pickability-003`
**Commits on branch vs main:** 12
**Entry point:** `uv run irc opportunity` → `uv run irc run --only memo`
**Method:** Cold start (no verifier skill). Both pipeline stages ran to completion without hitting the citation gate.

---

### Steps

1. ✅ `uv run irc opportunity` → completed: `opportunity OK: 79 rows, 16 cards, 79 discipline entries, 0 rejections -> outputs/2026-05-27`

2. ✅ `uv run irc run --only memo` → completed: `memo OK: 40/40 refs quoted verbatim → outputs/2026-05-27/memo.md` (64 s)

3. ✅ `outputs/2026-05-27/qdii_premium.json` produced — schema correct:
   - Top-level keys: `evidence_cutoff`, `generated_at`, `threshold_pct`, `rows`
   - `threshold_pct: 0.05`, `evidence_cutoff: "2026-05-27"`, `generated_at` UTC+8 ISO
   - `rows` count: 30, sorted by `instrument_id` ASC ✓
   - Blocking rows: `159501` (+6.92%), `159941` (+6.48%), `513300` (+5.99%) — all above 5% threshold ✓
   - Row keys: `asset_class`, `blocking`, `instrument_id`, `market`, `name_cn`, `qdii_premium_pct`, `render_cell` ✓

4. ✅ §5 picks table — 13-column header confirmed:
   `| 代码 | 名称 | 角色 | 权重上限 | 综合分* | 决策 | 机会状态 | 本期行动 | 主要理由 | 单次定投上限 | 溢价 | 触发状态 | 证据 |`
   Cell rendering observed in real output:
   - Non-QDII (518850, 003318, …): `—`
   - Off-exchange QDII (161716, 017641, 019441): `0.00%（场外申赎）`
   - On-exchange hk_etf (513690): `-0.34%`

5. ✅ §6 `IRC_QDII_PREMIUM_BEGIN/END` marker block present and correct — 3 instruments marked 超阈值，已暂缓执行 (159501 +6.92%, 159941 +6.48%, 513300 +5.99%), threshold/cutoff header line correct.

6. ✅ §7 — no `⛔ qdii_premium_too_high` prefixes, which is correct: the 3 above-threshold instruments are `pause_wait`-state watch-not-picked (NG2 scope exclusion); none of the 10 §7 picks is above threshold.

7. ✅ Targeted tests:

   | Command | Result |
   |---|---|
   | `pytest tests/memo/test_picks_table.py -k 'column or qdii or premium'` | **11 passed**, 19 deselected |
   | `pytest tests/memo/test_qdii_premium_lines.py` | **26 passed** |
   | `pytest tests/commands/test_memo_cmd.py -k 'prefix or qdii_premium'` | **6 passed**, 5 deselected |
   | `pytest tests/commands/test_memo_cmd.py::test_no_qdii_premium_high_synonym_in_src -v` | **1 passed** (uses `Path(__file__).resolve().parents[2]` — P0 fix confirmed) |
   | Full regression sweep (opportunity + memo + commands) | **846 passed, 1 skipped** |

8. ✅ Second memo run — `IRC_QDII_PREMIUM_BEGIN/END` block byte-identical across both runs; picks table header identical. `generated_at` differs (expected: production caller uses live clock per spec; AC14 byte-equality test stubs the clock).

9. 🔍 Probe — `name_cn` and `market` fields are empty strings (`""`) in `qdii_premium.json` for all rows. `score_rows` in `scoring.json` carry `instrument_id` and `qdii_premium_pct` but not `name_cn`; the projection builder reads `score_row.get("name_cn")` which returns `None`. The §6 marker block renders `- 513690 ：-0.34%` (id-only, no name). This is a cosmetic gap vs the spec example which showed `港股红利ETF博时` — but the test suite passes (tests supply `name_cn` in fixtures), and no AC directly requires non-empty `name_cn` in the production artefact.

---

### Findings

- ✅ All 5 AC-targeted pytest commands passed with the expected counts (11 + 26 + 6 + 1 + 846/1).
- ✅ Real-world pipeline completed without citation gate halt on both runs.
- ✅ `qdii_premium.json` schema and blocking logic correct; 3 above-threshold instruments correctly flagged.
- ✅ 13-column picks table live in real memo output with correct cell rendering across all three paths (`—` / `0.00%（场外申赎）` / signed pct).
- ✅ `IRC_QDII_PREMIUM_BEGIN/END` locked section deterministic across two live runs.
- ✅ AC13 P0 fix (repo-root via `Path(__file__).resolve().parents[2]`) confirmed passing.
- ⚠ `name_cn` / `market` fields are empty in `qdii_premium.json` (score_rows lack these fields). §6 shows instrument IDs only, not names. No AC is violated — tests supply `name_cn` in fixtures and pass — but the production artefact loses the human-readable label. A follow-up item that joins opportunity_rows to the projection builder would restore the spec example's name display.
- The 3 above-threshold instruments (159501/159941/513300) are `pause_wait` state not picks, so §7 has no ⛔ prefixes — correct per NG2.
