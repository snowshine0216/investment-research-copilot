# Item 010 — Wire `geopolitical_stress_0to1` from news sentiment

## Problem

`src/irc/commands/gold_cmd.py:74` has a hardcoded `geopolitical_stress_0to1 = 0.4` with a TODO comment ("wire from news sentiment"). This is one of six driver inputs to the gold tilt score. Hardcoding to a constant means the tilt computation never reflects actual macro stress, so the gold position is effectively decoupled from the news cycle.

## Approach

Use the existing research-stage output (`theme_report` for the "gold" theme) as the source. The theme report has a `failure_reason` field, a `report_md` body, and — for usable reports — sentiment-related signal that can be summarized into a 0-1 score. The simplest defensible mapping:
- If no theme_report exists or it's unusable → keep current 0.4 default (no signal).
- If theme_report exists and is usable → derive a coarse score from a keyword tally over `report_md`: tokens like `战争 / war / sanction / tariff / 制裁 / 关税 / strike / 冲突` add to stress; `peace / 缓和 / ceasefire / 协议` subtract. Normalize to [0, 1], clip.

The keyword approach is intentionally simple — Item 010's value is removing the hardcode, not building a sentiment model. The function lives in `src/irc/research/` (or a new helper alongside theme_research.py).

## Acceptance criteria

- `gold_cmd.py:74` no longer hardcodes 0.4. It reads from a new `geopolitical_stress_from_theme_report(report)` helper.
- The helper returns 0.4 (the documented default) when input is `None` or the report is unusable, so gold computation is unaffected when news isn't available.
- A test verifies: report with stress keywords → score > 0.4; report with calm keywords → score < 0.4; `None` input → 0.4.
- The change is observable in `outputs/<date>/gold_regime.json` (the score field changes when a theme report is available).

## Files (expected)

- `src/irc/research/` (new helper, e.g. `geopolitical_stress.py`).
- `src/irc/commands/gold_cmd.py:74` — wire the helper.
- `tests/research/test_geopolitical_stress.py` — new test file.

## Non-goals

- Building a real sentiment model.
- Changing the other 5 gold driver inputs.
- Modifying the gold scoring formula itself.
