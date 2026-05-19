# 002 — Thesis intact requires relevance

## Why

`thesis_cards.yaml` contains 25 cards, every single one with
`thesis_state: intact`, every single one citing the same two unrelated
URLs (a software-industry report and a steel-mill blog republishing a
PBOC press release). The system treats "we got ≥N citations back" as
"thesis is sound" — a category error noted in adversarial review §A2.

## What changes

1. In `src/irc/opportunity/thesis_evidence.py`, the
   `derive_thesis_from_evidence()` function currently can return
   `intact` based on the YoY-positive constituent threshold OR
   (implicitly) when there is no constituent data but news/broker
   evidence is present. Tighten this:

   - `intact` requires BOTH:
     - existing YoY/broker condition, OR
     - at least one news-citation passes relevance filter (item 001) AND
       its source-tier (item 004) is ≤ PAPER (i.e. not republisher/unknown).
   - If neither condition holds, downgrade to `evidence_insufficient`
     with a rationale that names the gap.

2. In the new logic, surface a per-card field
   `thesis_news_relevance_score` in `ThesisCard`:
   - `relevant_high` — ≥1 wire/paper source mentioning a holding/sector
   - `relevant_low` — only republisher/unknown sources
   - `irrelevant` — no source matches relevance keywords
   - `no_data` — research not run / theme failed

3. In `src/irc/opportunity/states.py` (where the `thesis_news` numeric
   score is computed for the scoring layer), default to `None` (not 50)
   when relevance score is `irrelevant` or `no_data`. The scoring layer
   already handles `None` by re-normalizing weights across the available
   factors.

## Acceptance criteria

- After re-run, no `ThesisCard` carries `thesis_state: intact` if its
  only news evidence is irrelevant or republisher-tier.
- `opportunity_report.json` rows with no relevant news evidence have
  `thesis_news_score = null` (not 50), and the composite score
  recomputes correctly with re-normalized weights.

## Tests to add

- `tests/opportunity/test_thesis_relevance_gate.py`:
  - news evidence with relevant Reuters citation → `intact`
  - news evidence with only mysteel republisher → not `intact`
  - empty news + healthy YoY constituents → still `intact`
  - empty news + no constituents → `evidence_insufficient`
