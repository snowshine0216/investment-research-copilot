# SKIPPED / DEFERRED — Monitor forward-eval engine-drop WARN (FU1)

No IN-scope items were skipped. The following are **deferred follow-ups** the
source spec explicitly sequences outside this implementation run (recorded here
so they are not silently dropped):

## §8.1 — Standalone as-built doc-sync diagram PR (shared #168 doc-debt, NOT FU1-owned)

Bring `evals/docs/monitor-eval-workflow.html` and `docs/diagrams/monitor-workflow.html`
to current shipped reality (schema node → `"3"`; engine-isolation path; `flow`
factor + `drilldown.html`; fix stale "v2.0: valuation/heat → N/A" wording).

- **Blocker:** The spec marks this *"shared #168 doc-debt, **not** FU1-owned"* and a
  prerequisite for **both** FU1 and Spec B. It is a separate, broader PR than this
  feature's code+tests. Bundling it would conflate shared doc-debt with FU1.
- **Unblock path:** A dedicated doc-sync PR (its own autodev/spec run or a manual
  doc pass) that updates both HTML diagrams to as-built reality. FU1 code+tests do
  **not** depend on it (§8.2).

## §8.3 — FU1 diagram overlay (dashed `engine_population` box)

Add a dashed "planned" `engine_population` box to the `monitor_forward` node in the
diagram, promoted to solid at ship (mirrors the existing dashed M4 box).

- **Blocker:** Spec §8.3 sequences this to **wait for §8.1** — overlaying onto a
  stale diagram would produce a mixed stale/planned artifact.
- **Unblock path:** After §8.1 lands, add the overlay box in a small follow-up.

> CONTEXT.md edits (§9) and the ADR 0019 addendum are **NOT** skipped — they are
> IN scope and land with the FU1 merge (see MASTER-SPEC).
