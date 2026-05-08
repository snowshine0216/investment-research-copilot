from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import yaml
import pandas as pd
from irc.config_loader import load_repo_configs
from irc.io_utils import atomic_write_text
from irc.allocation.pipeline import run_allocation


def _today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def run_allocate(repo_root: str) -> int:
    root = Path(repo_root)
    bundle = load_repo_configs(root)
    today = _today()
    scoring_path = root / "outputs" / today / "scoring.json"
    gold_regime_path = root / "outputs" / today / "gold_regime.json"
    if not scoring_path.exists():
        # fall back to latest
        candidates = sorted((root / "outputs").glob("*/scoring.json"))
        if not candidates:
            print("ERROR: no scoring.json; run `irc score` first.")
            return 2
        scoring_path = candidates[-1]
        gold_regime_path = scoring_path.parent / "gold_regime.json"
    scores = json.loads(scoring_path.read_text(encoding="utf-8"))["scores"]
    gold_tilt = "neutral"
    if gold_regime_path.exists():
        gold_tilt = json.loads(gold_regime_path.read_text(encoding="utf-8")).get("tilt", "neutral")
    class_targets = {
        k: {"center": v.center, "band": list(v.band)}
        for k, v in bundle.preferences.asset_class_targets.items()
    }
    out = run_allocation(
        scores=scores, class_targets=class_targets,
        gold_tilt=gold_tilt, correlation=pd.DataFrame(),
        per_class_top_k=2,
    )
    out_path = root / "outputs" / today / "proposed_allocation.yaml"
    payload = {
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "gold_tilt": gold_tilt,
        "target_weights_per_class": out.target_weights_per_class,
        "selected_instruments": out.selected_instruments,
        "dropped_due_to_correlation": out.dropped_due_to_correlation,
        "diagnostics": out.diagnostics,
    }
    atomic_write_text(out_path, yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
    print(f"allocate OK → {out_path}")
    return 0
