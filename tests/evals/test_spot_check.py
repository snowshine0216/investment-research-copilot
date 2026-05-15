from __future__ import annotations
from pathlib import Path
import pytest
from evals.spot_check.runner import sample_for_review, append_queue


def test_sample_for_review_round_robin(tmp_path: Path):
    items = {
        "research_citations": ["c1", "c2", "c3"],
        "discovery_reasons": ["r1", "r2"],
        "memo_claims": ["m1"],
        "query_responses": ["q1"],
    }
    sample = sample_for_review(pools=items, sizes={"research_citations": 2,
                                                    "discovery_reasons": 1,
                                                    "memo_claims": 1, "query_responses": 1},
                                seed=42)
    assert len(sample) == 5


def test_append_queue_writes_csv(tmp_path: Path):
    queue = tmp_path / "queue.csv"
    append_queue(queue, week="2026-05-07", entries=[
        {"stage": "research_citations", "sample_id": "c1", "content_ref": "x", "why_sampled": "weekly"},
    ])
    assert queue.exists()
    text = queue.read_text(encoding="utf-8")
    assert "c1" in text
