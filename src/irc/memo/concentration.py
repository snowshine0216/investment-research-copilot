"""Holdings overlap / concentration analytic for memo §6 风险提示.

Pure module. Tier-1 import contract: imports from `irc.opportunity.types`
and `irc.fundamentals.types` only — no imports from `irc.memo.*` siblings,
no `irc.commands.*` imports. Mirrors `aliases.py` per CONTEXT.md
"Renderer tier-1 import contract".

Produces `ConcentrationPair` records summarising Top-N weighted-overlap
between every pair of active-fund picks. Memo-only — does NOT mutate
`OpportunityRow`, does NOT touch `evidence_gaps` / `advisory_gaps` /
`thesis_state`, does NOT emit `[ref:...]` markers.

See `docs/2026-05-27-instrument-pickability/items/002-spec.md` AC1–AC15
and CONTEXT.md entries for `IRC_CONCENTRATION_BEGIN/END`,
`weighted_overlap_pct`, `ConcentrationPair`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


# AC2 / spec Q2: Top-10 chosen because the 2026-05-27 CPO cluster extends
# through weight rank 6–8 in several active funds.
CONCENTRATION_TOP_N: Final[int] = 10

# AC3 / spec Q3+Q5: 30.0 percent units (0–100), matches ConstituentAnalysis
# .weight_pct unit per ADR 0002 §4. NOT a fraction. Boundary inclusive (>=)
# mirrors FOREIGN_HEAVY_THRESHOLD precedent.
CONCENTRATION_OVERLAP_PCT_THRESHOLD: Final[float] = 30.0

# AC9 / spec Q9: marker constants live at module-top in concentration.py
# (producing-module pattern, mirrors macro_pillar.py's MACRO_SECTION_MARKER_*).
CONCENTRATION_MARKER_BEGIN: Final[str] = "<!-- IRC_CONCENTRATION_BEGIN -->"
CONCENTRATION_MARKER_END: Final[str] = "<!-- IRC_CONCENTRATION_END -->"
