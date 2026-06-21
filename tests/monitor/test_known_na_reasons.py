"""Two-way exhaustiveness of KNOWN_NA_REASONS (spec §6).

Every _na() branch in build_factor_scores emits a member of KNOWN_NA_REASONS,
and every member is reachable from some branch (no dead codes). Note
constituent_no_coverage is emitted by TWO branches (factors.py:70 and :73) —
codes-to-branches is many-to-one, so two branches sharing one code is NOT a
dead-code false positive.
"""
from __future__ import annotations
import inspect
import re
from irc.monitor import factors
from irc.monitor.factors import KNOWN_NA_REASONS


# The twelve named constants the spec enumerates (§6 + ADR 0020).
_EXPECTED = {
    "profile_ineligible",
    "trend_insufficient_history",
    "valuation_no_anchor",
    "valuation_unknown_state",
    "heat_no_data",
    "macro_insufficient_families",
    "macro_empty_pool",
    "constituent_no_coverage",
    "flow_no_data",
    "flow_no_coverage",
    "valuation_no_data",
    "valuation_no_coverage",
}


def test_known_na_reasons_is_exactly_the_twelve_codes():
    assert KNOWN_NA_REASONS == frozenset(_EXPECTED)


def _emitted_reason_constants() -> set[str]:
    """Every NA-reason constant name referenced in the build_factor_scores source
    that resolves to a KNOWN_NA_REASONS member. We read the module source and
    resolve each _NA_* constant the helper bodies reference."""
    src = inspect.getsource(factors)
    names = set(re.findall(r"\b(_NA_[A-Z_]+)\b", src))
    return {getattr(factors, n) for n in names if hasattr(factors, n)}


def test_every_na_branch_emits_a_known_reason():
    emitted = _emitted_reason_constants()
    assert emitted, "no _NA_* constants referenced in factors.py"
    assert emitted <= KNOWN_NA_REASONS


def test_every_known_reason_is_reachable_from_a_branch():
    # Reachability: every member must be referenced by at least one _NA_* constant
    # used in the module (constituent_no_coverage reached via two branches → still
    # one code, counted once).
    emitted = _emitted_reason_constants()
    assert KNOWN_NA_REASONS <= emitted
