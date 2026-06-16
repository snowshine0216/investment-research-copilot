# MASTER-SPEC — Monitor report verdict-justification redesign

Date: 2026-06-15
Mode: spec (single feature, N=1)
Source: approved brainstorming design (this session) + mockup `monitor_card_redesign_mockup`.

## Problem

`irc monitor` computes a full `SignalRecord` per fund (composite `C`, per-factor
`contributions` with value/renorm-weight/contribution/confidence, `present_families`,
`divergence_codes`) and attaches it to `FundView.signal`, but the renderer
(`src/irc/monitor/render_html.py`) discards everything except the bias badge. Each
per-fund card shows only: badge, SVG chart, an **always-empty** returns table
(`return_table` is hardcoded `{}`), an undifferentiated blob of `<p>` claims (price
action + signal rationale + risk all merged, unlabeled), and a bare N/A list. The user
cannot see *why* a fund is ADD_BIAS / NEUTRAL / REDUCE_BIAS / NO_CALL.

The approved spec §7 already *requires* a per-fund "factor-contribution table" and
"divergence caveats" — the shipped renderer is a simplified version that dropped them.

## IN scope (single item: 001)

| id | item | type |
|----|------|------|
| 001 | Re-surface verdict justification in the monitor report renderer | feature |

001 delivers, per fund card:
1. **Verdict block** — deterministic clause (`C` vs bands → the call, always rendered)
   + the concise MiniMax `signal_rationale_commentary` (the "why this signal", capped).
2. **Factor-contribution table** — all factors in canonical order; present factors show
   value `sᵢ` / renorm weight `w'ᵢ` / contribution `w'ᵢ·sᵢ` / confidence; N/A factors
   show a dimmed row with their eligibility reason; footer row carries `C`, confidence,
   available weight, present families.
3. **Returns table** — newly computed `[5,20,60,120,250]d` total returns off the
   `COALESCE(nav_acc, nav)` series (fixes the empty `{}`).
4. **Risk & divergence block** — `divergence_codes` → plain-language caveats + the MiniMax
   `risk_commentary`, under a distinct labeled heading.
5. **Sectioned narrative** — price-action claims in their own labeled section (no longer
   merged with rationale + risk).

## OUT of scope

- The signal engine (`signal.py`), factor computation, fetch, LLM prompts, schedule.
- The intentionally-lossy `signal.json` (`{status,bias}` is the prior-signal contract).
- The English-vs-Chinese narrative-language issue (MiniMax returned English) — a
  prompt/LLM concern, not rendering. Noted, deferred.

## Acceptance criteria

- Renderer stays a **pure, byte-stable** function (narrative is an existing input;
  determinism + golden-file test hold). XSS-escaping of every untrusted field preserved.
- H3 universal-rows invariant (every fund has a summary entry + a card, incl. NO_CALL)
  and citation-closure invariant (rendered `[ref:…]` anchors == evidence-appendix ids)
  preserved.
- NO_CALL funds are self-explaining (verdict block states the gate failure; factor table
  shows which factors were N/A and why).
- New unit tests for the returns helper and each render helper; hostile-title XSS test;
  NO_CALL self-explanation test; refreshed golden file.
- **Exit gate:** regenerate today's `outputs/2026-06-15/monitor/report.html` (reusing
  cached impacts/narrative where hashes match) and confirm each per-fund card renders the
  verdict block + factor table + returns + risk block as in the approved mockup.

## Project type

non-web (Python CLI emitting a static HTML file) → post-ship verification uses
`/verify`, not `/qa`. The exit-gate report refresh IS the verification.
