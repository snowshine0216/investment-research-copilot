Verdict: PASS

Subagent: sonnet
Plan checklist items: 55 (10 Tasks)
Verified present in diff: 55
Drift findings:
  - None. All plan Tasks and steps are accounted for.

---

## Verification summary by Task

### Task 1: SoT catalog module `sector_indices.py`
OK — `src/irc/opportunity/sector_indices.py` created. Frozen `SectorIndex` dataclass with `(slug, code, display_cn, official_cn, aliases)`. `SECTOR_INDICES` tuple has exactly 17 rows (confirmed by `grep -c "SectorIndex("` → 17). All 4 derived maps present: `SECTOR_INDEX_CODE`, `SECTOR_INDEX_DISPLAY`, `SECTOR_INDEX_KEYS`, `SECTOR_NAME_TO_SLUG`. `_build_name_to_slug` raises on collision. `csi_machine_tool` has alias `("中证机床ZZ",)`, `csi_nonferrous` has alias `("中证有色",)`. Pure, no I/O. `tests/opportunity/test_sector_indices.py` created with all 7 tests including 17-slug structural check, alias-collision, parametrized resolution (all 17 cases), curated-config coverage.

### Task 2: `lookthrough.py` imports derived maps
OK — `lookthrough.py` drops inline 3-entry sector dicts and imports `SECTOR_INDEX_DISPLAY`, `SECTOR_INDEX_KEYS`, `SECTOR_NAME_TO_SLUG` from `sector_indices`. Legacy private names `_SECTOR_INDEX_DISPLAY`, `_SECTOR_INDEX_KEYS`, `_INDEX_NAME_TO_SLUG`, `_INDEX_VALUATION_KEYS` re-bound from SoT. `tests/opportunity/test_lookthrough_sector_keys.py` updated to 17-slug reality.

### Task 3: `akshare_index_valuation.py` imports `SECTOR_INDEX_CODE`
OK — inline 3-entry `_SECTOR_INDEX_CODE` dict dropped; `SECTOR_INDEX_CODE` imported from `irc.opportunity.sector_indices`. Legacy alias `_SECTOR_INDEX_CODE: dict[str, str] = SECTOR_INDEX_CODE` preserved. Two new tests added to `tests/fundamentals/test_akshare_index_valuation.py`: `test_sector_code_map_is_sot_backed` (identity check with `is`) and `test_sector_fetch_resolves_new_slug_code` (monkeypatched `_ak_call`, asserts `symbol == "H30590"` for `csi_robotics`).

### Task 4: Config schema + template
OK — `SectorIndexGroundingConfig(FrozenModel)` with `activated_slugs: list[str] = Field(default_factory=list)` added to `src/irc/schemas/valuation.py` after `ActiveFundLookthroughConfig`. `ValuationBucketsConfig` gains `sector_index_grounding: SectorIndexGroundingConfig = Field(default_factory=SectorIndexGroundingConfig)`. Template `src/irc/templates/config/valuation_buckets.yaml` gains `sector_index_grounding: { activated_slugs: [] }` block. No committed `config/valuation_buckets.yaml` created (confirmed: `git diff --name-only -- config/` is empty). `tests/schemas/test_valuation_sector_grounding.py` created with 3 tests.

### Task 5: Read-gate in `_index_valuation_metrics`
OK — Load-bearing check confirmed against actual diff lines:
- Signature adds keyword-only `activated_sector_slugs: frozenset[str] = frozenset()` (line 159 in diff).
- Import: `from irc.opportunity.sector_indices import SECTOR_INDEX_KEYS` (line 18 in diff).
- Gate at line 182: `if slug in SECTOR_INDEX_KEYS and slug not in activated_sector_slugs: return None, None, None, None, None` — FULL 5-tuple (withholds raw pe/pb/div AND percentile, not a partial short-circuit). Positioned correctly AFTER `_INDEX_VALUATION_KEYS` membership check, BEFORE `df = _index_valuation_series(con, slug)`.
- `tests/opportunity/test_index_valuation_gate.py` created with 6 tests covering: off-allowlist → full None, default → full None, on-allowlist + mature → PE populated / PB None, metals-off-allowlist → full None, broad-unaffected (empty allowlist), broad-unaffected (non-empty allowlist).

### Task 6: Thread allowlist `populate_inputs → _build_input → _build_rows → run_opportunity`
OK — Each hop verified against actual diff lines:
- `populate_inputs` (`inputs_loader.py`): gains `activated_sector_slugs: frozenset[str] = frozenset()` and passes it to `_index_valuation_metrics(..., activated_sector_slugs=activated_sector_slugs)`.
- `_build_input` (`inputs_build.py`): gains param and forwards to `populate_inputs`.
- `_build_rows` (`opportunity_cmd.py`): gains param and forwards to `_build_input` call.
- `run_opportunity` (`opportunity_cmd.py`): sources `frozenset(bundle.valuation_buckets.sector_index_grounding.activated_slugs)` and passes to `_build_rows`. All are keyword-only forwarding — no global read.
- `tests/opportunity/test_sector_allowlist_threading.py` created with 4 live DuckDB tests + 1 source-inspection guard verifying `activated_sector_slugs` in `_build_input`, `_build_rows`, `sector_index_grounding` in `run_opportunity`.

### Task 7: Per-slug audit helper `audit_sector_ingest`
OK — `SectorIngestAudit` frozen dataclass + `_audit_one_slug` + `audit_sector_ingest` added to `src/irc/data/index_valuation_ingestor.py`. Imports `MIN_PE_DAYS`, `MIN_PE_POINTS` from `lookthrough_valuation` and `SECTOR_INDEX_KEYS` from `sector_indices`. Returns `tuple[SectorIngestAudit, ...]` sorted by slug. `tests/data/test_sector_ingest_audit.py` created with 3 tests: empty → 17 rows / all row_count=0, accumulating not-mature (20 points), mature (200 points).

### Task 8: Strengthen live identity guard (author only)
OK — `tests/fundamentals/test_sector_index_valuation_live.py` overhauled. `_CSI_CATALOG_ABSENT = {"000685"}` documents SSE-listed code. `test_sector_index_pe_ttm_numeric_live` (renamed from `test_sector_index_pe_ttm_live`, removed final `print`) parametrized over `sorted(_SECTOR_INDEX_CODE)` — now covers all 17 slugs. `test_sector_codes_identity_in_csindex_all_live` added (loads `index_csindex_all` once, checks code↔official_cn identity for all non-SSE codes). Double-gate `pytest.mark.live_akshare + skipif(IRC_RUN_LIVE_AKSHARE != "1")` preserved — test is NOT executed in autonomous flow.

### Task 9: Docs
OK — `CONTEXT.md` gains a new bullet for `sector_index_grounding.activated_slugs` under "Valuation inputs" (long entry describing the 17 slugs, PE-only, allowlist threading, metals now allowlist-governed, B2 path). `CHANGELOG.md` gains `### Added — Phase B sector-index PE onboarding (B1, activation OFF, 2026-06-05)` block under `[Unreleased]`. `docs/ROADMAP.md` Phase B table row updated from `☐ open` to `◑ B1 done (onboarding; activation OFF)`, and `### Phase B — Sector expansion` section gains a status line.

### Task 10: Final verification
OK — This is a verification-only task; no new committed changes expected. `config/universe/*.yaml` confirmed untouched (zero diff under `config/`). Template-only YAML change confirmed. All prior tasks' structural + threading + gate tests present.

---

## Key load-bearing checks (per task specification)

All 9 explicitly requested checks verified against actual diff lines:

1. **`sector_indices.py` structure** — frozen `SectorIndex` dataclass, 17-row `SECTOR_INDICES` tuple, all 4 derived maps (`SECTOR_INDEX_CODE`/`SECTOR_INDEX_DISPLAY`/`SECTOR_INDEX_KEYS`/`SECTOR_NAME_TO_SLUG`). Pure, no I/O. OK.
2. **Read-gate full-None short-circuit** — `if slug in SECTOR_INDEX_KEYS and slug not in activated_sector_slugs: return None, None, None, None, None` (full 5-tuple, not partial). Raw pe/pb/div AND percentile withheld. OK.
3. **Allowlist threading — no global read** — keyword-only param forwarded at each hop: `run_opportunity` → `_build_rows` → `_build_input` → `populate_inputs` → `_index_valuation_metrics`. All as explicit `activated_sector_slugs=activated_sector_slugs` keyword calls. OK.
4. **`akshare_index_valuation.py` imports SoT** — `from irc.opportunity.sector_indices import SECTOR_INDEX_CODE`; inline 3-entry dict dropped; legacy alias `_SECTOR_INDEX_CODE = SECTOR_INDEX_CODE` kept. OK.
5. **`lookthrough.py` imports SoT maps** — 3-map import block present; inline sector dicts removed; legacy private names re-bound. OK.
6. **Config schema** — `SectorIndexGroundingConfig` + field on `ValuationBucketsConfig`; template gains `activated_slugs: []`; no committed `config/valuation_buckets.yaml`. OK.
7. **`config/universe/*.yaml` untouched** — `git diff --name-only -- config/` empty. `中证机床ZZ` resolved via alias only. OK.
8. **`audit_sector_ingest` helper** — Added to `index_valuation_ingestor.py`; per-slug rows. OK.
9. **Live test double-gated** — `pytest.mark.live_akshare + skipif`; numeric `市盈率1` + code↔official identity assertions; NOT run in autonomous flow. OK.
