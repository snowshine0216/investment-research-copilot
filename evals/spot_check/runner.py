from __future__ import annotations
from pathlib import Path
import csv
import random


def sample_for_review(
    pools: dict[str, list[str]], sizes: dict[str, int], seed: int = 0,
) -> list[dict[str, str]]:
    rng = random.Random(seed)
    out: list[dict[str, str]] = []
    for stage, pool in pools.items():
        k = min(sizes.get(stage, 0), len(pool))
        chosen = rng.sample(pool, k=k) if pool else []
        for item in chosen:
            out.append({"stage": stage, "sample_id": item, "content_ref": item})
    return out


def append_queue(queue_path: Path, week: str, entries: list[dict]) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["week", "stage", "sample_id", "content_ref", "why_sampled", "status", "reviewer_notes"]
    new_file = not queue_path.exists()
    with queue_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        for e in entries:
            row = {**e, "week": week}
            row.setdefault("status", "pending")
            row.setdefault("reviewer_notes", "")
            row.setdefault("why_sampled", e.get("why_sampled", "weekly auto-sample"))
            w.writerow(row)
