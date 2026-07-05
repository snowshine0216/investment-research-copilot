# MASTER-SPEC — Sector rotation radar (`irc rotation`)

**Mode:** spec (single feature) · **Detected:** 2026-07-05
**Input:** [`docs/superpowers/specs/2026-07-05-sector-rotation-radar-design.md`](../../superpowers/specs/2026-07-05-sector-rotation-radar-design.md) — grilled + locked (status line in the spec), ADR [0023](../../adr/0023-sector-rotation-radar.md).
**Verbatim spec copy:** [`items/001-spec.md`](items/001-spec.md)

Mode inference (one line): **spec** — the input is a design spec with `Goal` / `Non-goals` / `Locked decisions` / `Acceptance criteria (AC1–AC12)` / single-feature scope; its own status line reads "grilled + locked, ready for autodev (not built)". No numbered impl steps / shell commands / `Run:`/`Expected:` markers → not plan mode. One feature → not backlog.

## IN scope (this run)

| # | Item | Source |
|---|------|--------|
| 001 | **Sector rotation radar** — new `src/irc/rotation/` package + `irc rotation` / `irc rotation seed` commands + flow-capture wrapper chaining. Daily deterministic zero-LLM radar: L1 ranks EM industry boards by a rotation composite → `rotation_state`; L2 resolves emerging/hot boards to candidate CN funds by holdings look-through. Advisory-only; forward ledger from day 1. | spec §1–§13 (full) |

Item 001 is the entire spec. Everything the spec calls **in scope** ships in this one item (it is a coherent single vertical: types → fetch/store edges → pure composite/states/exposure/candidates → report/ledger → command → wrapper chaining → docs). Sub-structure lives in [MASTER-PLAN.md](MASTER-PLAN.md)'s plan reference and `items/001-plan.md`.

## OUT of scope (explicitly deferred by the spec — NOT skipped-for-blocker)

The spec's §2 non-goals and §12 named follow-ups are OUT **by design**, recorded here for the audit trail. They are *not* SKIPPED items (no blocker to unblock) — they are deliberately-deferred future work named in the spec:

- **F1** `irc eval rotation_forward` — needs ~4–6 weeks of ledger rows before it can score. Ledger accumulates from day 1 (in scope); the eval command is deferred.
- **F2** Surface integration (weekly-memo / monitor-brief 轮动雷达 pointer) — touches locked memo pillars / monitor schema; separate item.
- **F3** Dynamic `hot_sector` research query — interacts with ADR 0007 static theme mapping; grill before building.
- **F4** Auto-generated narrative baskets — contradicts the frozen "Narrative selector" domain decision; needs a CONTEXT.md amendment grill.
- **F5** `tracked_index` precision join for ETFs (board → CSIndex) + CSIndex momentum overlay.
- No new LLM / paid-search calls anywhere → spend/balance gate is **not** involved (§2, §8).

These are documented, not silently omitted. See [SKIPPED.md](SKIPPED.md) (empty — nothing is blocked; the above are deferred-by-design, not blocked).

## Prerequisite already landed

The **f127→f100 stock-industry field-code correction** (monitor `flow_batch_fetch.py` / `industry_map_store.py` + docs) is a prerequisite for the radar (spec §13-T1, AC1: the seed's stock→board map reads `f100` in `ulist.np`). It was completed-but-uncommitted in the working tree; per user direction it was committed as the **prep commit** (`2c1b844b`) at the base of this feature branch, ahead of the design-artifact commit.
