from pathlib import Path
from irc.spend.config import load_pricing
from irc.spend.profile import seed_profile

REPO = Path(__file__).resolve().parents[2]


def test_seed_profile_marks_entries_unlearned_with_seed_values():
    pricing = load_pricing(REPO)
    profile = seed_profile(pricing)
    memo = profile.tasks["memo_synthesis"]
    assert memo.samples == 0
    assert memo.avg_prompt_tokens == pricing.seeds["memo_synthesis"].prompt_tokens
    assert memo.avg_calls_per_run == pricing.seeds["memo_synthesis"].calls
    assert profile.alpha == 0.3
