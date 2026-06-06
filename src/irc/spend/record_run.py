from __future__ import annotations
import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from irc.io_utils import atomic_write_text
from irc.llm.cost_tracker import CostEntry
from irc.spend.config import (load_balances, load_consumption, load_pricing,
                              load_usage_profile_raw, write_consumption, write_usage_profile)
from irc.spend.estimate_io import merge_actuals_dict
from irc.spend.ledger import apply_usage
from irc.spend.profile import effective_profile, fold_actuals, seed_profile
from irc.spend.recorder import actuals_from_costs


def record_command_run(
    *, repo_root: Path, history: Sequence[CostEntry], search_units: Mapping[str, int],
    today: date, out_dir: Path | None = None,
) -> None:
    """Edge: one gated command's actuals → merge spend_actuals.json, EWMA-fold
    usage_profile.json, decrement consumption.json. Wallet-vs-quota is DERIVED from
    spend_balances.yaml (the same `entry.quota is not None` predicate the reader uses),
    so writer/reader can never drift. Hands-off; each call accumulates. Safe to call on
    both success and failure paths — `history` holds only completed, billed calls (Q4).
    `out_dir` defaults to `repo_root/outputs/<today>` (override only in tests).

    Concurrency: this read-modify-write of the three JSON state files is NOT locked.
    The contract assumes SEQUENTIAL invocation (the only path that accumulates within a
    day is `irc run`, which runs stages as sub-runners one at a time). `atomic_write_text`
    keeps each individual write torn-free; a lost update from two `irc` commands run
    concurrently (e.g. two terminals on the same day) is a tolerated, self-healing miss
    — the next sequential run re-folds the EWMA and re-decrements the ledger. File-level
    locking is intentionally out of scope for this single-user CLI."""
    if not history and not search_units:
        return                              # no paid calls → nothing to record (spec §12.2)
    root = Path(repo_root)
    out_dir = out_dir or root / "outputs" / today.isoformat()
    actuals = actuals_from_costs(history, search_units=search_units)

    actuals_path = Path(out_dir) / "spend_actuals.json"
    if actuals_path.exists():
        try:
            existing = json.loads(actuals_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"corrupt spend actuals at {actuals_path}: {exc}") from exc
    else:
        existing = {}
    atomic_write_text(actuals_path,
                      json.dumps(merge_actuals_dict(existing, actuals), indent=2, sort_keys=True))

    pricing = load_pricing(root)
    eff = effective_profile(seed_profile(pricing), load_usage_profile_raw(root))
    write_usage_profile(root, fold_actuals(eff, actuals.tasks))

    balances = load_balances(root)
    consumption = load_consumption(root)
    touched = False
    for provider, units in actuals.search_units.items():
        entry = balances.entries.get(provider)
        if entry is None:
            continue                       # no anchor to deplete → skip (no orphan row)
        kind = "quota" if entry.quota is not None else "wallet"
        consumption = apply_usage(consumption, provider, units=units, kind=kind, today=today)
        touched = True
    if touched:
        write_consumption(root, consumption)
