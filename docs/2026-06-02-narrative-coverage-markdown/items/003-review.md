Verdict: PASS
Source: /ship steps 8+9 (pr-review-toolkit:code-reviewer + silent-failure-hunter + adversarial), with a pre-push fix round + re-review

## Summary
Initial pre-landing review surfaced 4 substantive findings + 1 cosmetic — all fixed before push (commits 3ca2d2a, 74c9a9b, de20f34, c809105). Re-review: P0 none, all 5 verified resolved; one docstring-vs-code mismatch nit, fixed inline. Zero blockers, zero latent bugs remaining.

## Findings → resolution
- **AC8 .json gap (latent / self-AC, fixed 3ca2d2a)** — `_evidence_dict` dropped `summary`/`url` that item 003's `.md` footnotes now render, violating AC8 ("`.md` adds no datum the `.json` lacks"). Added both (additive; existing keys/order preserved); covers thesis + constituent evidence. (The drop was pre-existing on base, but 003's `.md` enrichment is what created the inconsistency.)
- **Dangling constituent footnote refs (latent bug, fixed 74c9a9b)** — `_footnote_lines` built the pool from `r.thesis_evidence` only while `_appendix_constituent_line` emits refs from `c.evidence` (⊆ invariant unenforced). Now builds the pool from `_union_evidence(r)` = thesis_evidence ∪ all constituent evidence, so every inline ref resolves regardless. Test added (constituent-only ref resolves).
- **Non-deterministic dedup (latent determinism risk, fixed 74c9a9b)** — `{cid: ev}` was input-order-dependent; now first-write-wins over a fixed traversal + citation_id-sorted output → byte-identical across input reorderings. Test added.
- **M2 `质量=weak` misleading (fixed de20f34)** — added a report-level legend (when any fund is `weak`) noting `质量` is a structural floor pending F-1, so readers weight the surfaced `产品驱动`. No per-fund over-claim; `classify_product_quality` untouched.
- **Markdown safety (cosmetic, fixed c809105)** — `_safe_summary` collapses newlines + omits the trailing `·` on empty summary; applied to inline bullet + footnote.
- **Docstring-vs-code mismatch (nit, fixed inline)** — corrected `_footnote_lines` docstring to describe the actual first-write-wins dedup.

## Verification
- `uv run pytest tests/narrative` → 133 passed, 1 skipped; `tests/memo/test_same_3_invariant.py` → 3 passed (SAME-3 untouched).
- `uv run ruff check` (touched files) → All checks passed.
- `git diff …states.py` empty (classifier untouched, F-1 deferred).
- Re-review: code-reviewer P0=none; determinism + citation-16-hex + SAME-3 confirmed.

## Noted, deferred
- Full `from_dict` round-trip of all provenance fields: broader pre-existing `.json` concern; AC8 satisfied by adding the rendered `summary`+`url`. Flagged for run-level doc-sync.
- `classify_product_quality` structural floor → follow-up F-1.
