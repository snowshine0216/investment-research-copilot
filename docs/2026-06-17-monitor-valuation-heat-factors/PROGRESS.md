# PROGRESS — Monitor valuation + heat factor wiring

Mode: spec (N=3) · Project type: non-web · PR shape: A · Feature branch: `monitor-valuation-heat-wiring`

Legend: ⏳ pending · 🔄 in-progress · ✅ done · ⚠️ soft-fail (fix loop) · ⏭️ skipped · ⛔ refused gate

| id | spec | grill | plan | branch | impl | drift | PR | verify | review | pr-review | fix | merge |
|----|------|-------|------|--------|------|-------|----|--------|--------|-----------|-----|-------|
| 001 | ✅ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 002 | ✅ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 003 | ✅ | ⏭️ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

### Notes

- **spec** ✅: per-item spec excerpts written at decompose (`items/<id>-spec.md`), drawn verbatim
  from the master design doc. Source: `docs/superpowers/specs/2026-06-17-monitor-valuation-heat-factors-design.md`.
- **grill** ⏭️: pre-completed (spec mode) — user authored & grilled the design doc; orchestrator
  must not auto-invoke grill.
- **verify** column is the non-web post-ship verifier (`/verify`); `/qa` is N/A for this CLI project.
- Items: 001 = index-path valuation + vocab unification · 002 = look-through valuation ·
  003 = heat restriction leg.

### Artifact links (filled as phases complete)

- 001: spec → [items/001-spec.md](items/001-spec.md)
- 002: spec → [items/002-spec.md](items/002-spec.md)
- 003: spec → [items/003-spec.md](items/003-spec.md)
