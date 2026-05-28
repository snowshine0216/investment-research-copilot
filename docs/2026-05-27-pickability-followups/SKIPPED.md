# SKIPPED — Pickability Follow-ups

All three deferred items from the prior `instrument-pickability` run (F4, F5, F6) are IN-scope this run per the user's explicit decision at intake. Below are the follow-ups discovered DURING this run that did not make it into scope.

## F5-followup-prompt-eval — LLM prompt redesign + 5-week eval bench

**Blocker**: F5's spec considered a path (c) "redesign the LLM `memo_synthesis` / `theme_research` prompt to emit paragraph-level summaries by default + build a 5-week historical eval corpus to confirm quality." The grill (Q1, Q12) confirmed this is the rigorous answer but rejected it for this run on three grounds:

1. The 5-week historical eval corpus does not exist (no preserved theme reports older than 1 week; rebuilding requires re-running the research stage 5 times against historical dates that may no longer be reachable via the same web sources).
2. The eval harness itself does not exist — would need a scoring rubric for "paragraph quality", baseline / variant prompts, and a way to record per-week regressions without hand-labeling.
3. The deterministic-extractor improvement chosen by F5 closes the heading-fragment symptom in §2 for all 4 problem themes (verified post-impl). Building the eval bench dwarfs that benefit until evidence shows the extractor approach is structurally inadequate.

**Recommended unblock path**: Run only when post-deployment observation surfaces a real "paragraph quality" complaint that the deterministic extractor cannot fix. At that point: (a) preserve 5+ consecutive weeks of `data/research/*.md` outputs as a corpus; (b) write a small paragraph-quality rubric (length, sentence count, terminology grounding); (c) bench current prompt vs paragraph-redesigned prompt against the corpus; (d) commit prompt change only if quality improves on ≥4 of 5 weeks. Separate autodev run.

ADR 0008 §4 documents this same deferral.
