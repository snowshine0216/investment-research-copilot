from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"


def test_readme_documents_spend_gate_and_artifacts():
    text = README.read_text(encoding="utf-8")
    assert "## Spend / balance gate" in text or "Spend / balance gate" in text
    for path in ("outputs/<date>/spend_estimate.json",
                 "outputs/<date>/spend_actuals.json",
                 "data/spend/usage_profile.json"):
        assert path in text, f"README missing artifact path: {path}"
    assert "IRC_SPEND_MARGIN" in text
    assert "exit code 5" in text or "exit 5" in text
