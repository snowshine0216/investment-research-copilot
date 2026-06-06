from pathlib import Path
from irc.spend.config import load_pricing
from irc.spend.profile import effective_profile, fold_actuals, seed_profile
from irc.spend.types import TaskActual, TaskUsage, UsageProfile

REPO = Path(__file__).resolve().parents[2]


def test_seed_profile_marks_entries_unlearned_with_seed_values():
    pricing = load_pricing(REPO)
    profile = seed_profile(pricing)
    memo = profile.tasks["memo_synthesis"]
    assert memo.samples == 0
    assert memo.avg_prompt_tokens == pricing.seeds["memo_synthesis"].prompt_tokens
    assert memo.avg_calls_per_run == pricing.seeds["memo_synthesis"].calls
    assert profile.alpha == 0.3


def _seeded(task, calls, p, c, *, alpha=0.3):
    return UsageProfile(tasks={task: TaskUsage(task, calls, p, c, samples=0)}, alpha=alpha)


def test_fold_moves_estimate_toward_actual_and_increments_samples():
    profile = _seeded("memo_synthesis", calls=4.0, p=4000.0, c=2000.0)  # high cold seed
    actual = {"memo_synthesis": TaskActual("memo_synthesis", calls=1.0,
                                           avg_prompt_tokens=1000.0, avg_completion_tokens=500.0)}
    folded = fold_actuals(profile, actual)
    t = folded.tasks["memo_synthesis"]
    # new = 0.3*actual + 0.7*seed
    assert t.avg_prompt_tokens == 0.3 * 1000.0 + 0.7 * 4000.0   # 3100.0 — moved toward 1000
    assert t.avg_completion_tokens == 0.3 * 500.0 + 0.7 * 2000.0
    assert t.avg_calls_per_run == 0.3 * 1.0 + 0.7 * 4.0
    assert t.samples == 1
    assert t.avg_prompt_tokens < profile.tasks["memo_synthesis"].avg_prompt_tokens  # converging


def test_fold_leaves_untouched_tasks_unchanged():
    profile = UsageProfile(tasks={
        "memo_synthesis": TaskUsage("memo_synthesis", 4.0, 4000.0, 2000.0, samples=0),
        "memo_audit": TaskUsage("memo_audit", 2.0, 1000.0, 300.0, samples=0),
    }, alpha=0.3)
    folded = fold_actuals(profile, {
        "memo_synthesis": TaskActual("memo_synthesis", 1.0, 1000.0, 500.0)})
    assert folded.tasks["memo_audit"] == profile.tasks["memo_audit"]  # disjoint task untouched


def test_effective_profile_uses_learned_where_samples_positive_else_seed():
    seed = UsageProfile(tasks={
        "memo_synthesis": TaskUsage("memo_synthesis", 4.0, 4000.0, 2000.0, samples=0),
        "memo_audit": TaskUsage("memo_audit", 2.0, 1000.0, 300.0, samples=0),
    }, alpha=0.3)
    learned_raw = {  # what usage_profile.json deserialises to
        "memo_synthesis": {"avg_calls_per_run": 1.0, "avg_prompt_tokens": 1100.0,
                           "avg_completion_tokens": 520.0, "samples": 3},
        "memo_audit": {"avg_calls_per_run": 0.0, "avg_prompt_tokens": 0.0,
                       "avg_completion_tokens": 0.0, "samples": 0},  # zeroed → ignore
    }
    blended = effective_profile(seed, learned_raw)
    assert blended.tasks["memo_synthesis"].avg_prompt_tokens == 1100.0     # learned
    assert blended.tasks["memo_synthesis"].samples == 3
    assert blended.tasks["memo_audit"] == seed.tasks["memo_audit"]          # seed fallback
