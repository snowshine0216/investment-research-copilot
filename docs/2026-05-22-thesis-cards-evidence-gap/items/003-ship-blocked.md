# /ship halted — in-branch test failure (item 003)

`/ship` step 5 (run tests) surfaced a real in-branch test failure that blocks PR creation. Per the autodev contract (`ship.md` §"/ship review can demand fixes before push"), the orchestrator routes through `triage-fix` and re-invokes `/ship` after the fix lands.

## Failure

```
tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports
  E   AssertionError: assert False is True
```

The architecture metric `dag_acyclic_check(package_root=Path("src/irc"))` returns `False` — a top-level import cycle was introduced between the `irc.fundamentals` and `irc.opportunity` packages.

## Pre-existing vs. in-branch check

- Base (`autodev/thesis-cards-evidence-gap`): test **passes**.
- Branch (`autodev/thesis-evidence-003-active-fund-constituent-layer`): test **fails**.

Conclusion: introduced by item 003. Per `failure-triage.md`, in-branch failures block `/ship`.

## Root cause

Item 003 introduced two new imports of `irc.opportunity.types` from `irc.fundamentals` package, creating the cycle:

```
src/irc/fundamentals/snapshot.py:48
    from irc.opportunity.types import (
        ConstituentAnalysis,
        LookthroughTarget,
        ThesisEvidence,
    )

src/irc/fundamentals/snapshot_cache.py:21
    from irc.opportunity.types import ConstituentAnalysis, ThesisEvidence
```

Combined with the pre-existing `irc.opportunity → irc.fundamentals` edges (from `opportunity/thesis_evidence.py` and `opportunity/states.py`), these new imports create a logical cycle:

- `opportunity → fundamentals` (existing, valid direction)
- `fundamentals → opportunity` (NEW — invalidates layering)

The architecture test correctly refuses this layering inversion.

## Fix strategy

Relocate the three shared types so that `fundamentals` does not need to import from `opportunity`:

1. Move `LookthroughTarget` + `LookthroughKind` from `opportunity/types.py` → `fundamentals/types.py`. These types describe **how to fetch data** for a row — naturally fundamentals semantics. `opportunity/lookthrough.py` builds them; `fundamentals/snapshot.py` consumes them.
2. Move `ConstituentAnalysis` from `opportunity/types.py` → `fundamentals/types.py`. It represents per-stock evidence — naturally fundamentals semantics. Tightly coupled to `FundHolding` and `ActiveFundSnapshot` (already in fundamentals).
3. Move `ThesisEvidence` from `opportunity/types.py` → `fundamentals/types.py`. It is provenance-rich evidence data — naturally fundamentals.

To preserve backward compatibility with the many `from irc.opportunity.types import ThesisEvidence` call sites elsewhere in the codebase (and avoid an invasive sweep), `opportunity/types.py` re-exports the three types via:

```python
from irc.fundamentals.types import (
    ConstituentAnalysis,
    LookthroughKind,
    LookthroughTarget,
    ThesisEvidence,
)
__all__ = [..., "ConstituentAnalysis", "LookthroughKind", "LookthroughTarget", "ThesisEvidence"]
```

This adds an `opportunity → fundamentals` import edge (already exists from prior modules — no new cycle).

`fundamentals/snapshot.py` and `snapshot_cache.py` are updated to import these types from `fundamentals.types` directly (not via the opportunity re-export), breaking the literal `from irc.opportunity` import in the fundamentals package.

## Spec deviation note

Spec §"Detailed schema specifications" placed `ConstituentAnalysis` in `src/irc/opportunity/types.py` and ADR 0001 implicitly placed `ThesisEvidence` there. Spec §"Files touched" preview placed `LookthroughTarget` modifications in `opportunity/types.py`. The fix relocates the dataclass *definitions* to `fundamentals/types.py` while preserving the documented import path via re-export, so the spec's import-site assertions still hold. The drift verdict should be re-confirmed after the fix.

## Action

Dispatch a fix subagent on `autodev/thesis-evidence-003-active-fund-constituent-layer`. After fix lands, re-run `/ship`.
