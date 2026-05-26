from __future__ import annotations
from pathlib import Path


STAGE_REQUIRED_OUTPUTS: dict[str, tuple[str, ...]] = {
    "discover":    ("discovered_watchlist.csv",),
    "score":       ("scoring.json",),
    "gold":        ("gold_regime.json", "gold_band.yaml"),
    "allocate":    ("proposed_allocation.yaml",),
    "plan":        ("trade_plan.yaml",),
    "opportunity": ("opportunity_report.json", "thesis_cards.yaml", "discipline_report.md"),
    # Memo's real contract is enforced in `missing_outputs` below (either
    # `memo.md` for audit pass or `memo_blocked.md` for audit block satisfies);
    # this empty tuple is just the manifest-presence sentinel.
    "memo":        (),
    "decision":    ("decision_report.json", "decision_report.md"),
}


def missing_outputs(out_dir: Path, stage: str) -> tuple[str, ...]:
    """Return the names of required outputs that do not yet exist in `out_dir`.

    Returns an empty tuple for stages not in the manifest (ingest, research,
    unknown stages) — those are validated by other mechanisms (freshness
    gates, opt-in flags) rather than file-existence.

    The `memo` stage is satisfied by either `memo.md` (audit pass) or
    `memo_blocked.md` (audit block). When neither exists, this returns the
    single literal token `"memo.md or memo_blocked.md"`.
    """
    if stage == "memo":
        if (out_dir / "memo.md").exists() or (out_dir / "memo_blocked.md").exists():
            return ()
        return ("memo.md or memo_blocked.md",)
    required = STAGE_REQUIRED_OUTPUTS.get(stage, ())
    return tuple(name for name in required if not (out_dir / name).exists())
