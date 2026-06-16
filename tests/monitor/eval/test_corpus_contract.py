from __future__ import annotations
import re
from pathlib import Path
from irc.monitor.eval.case_loader import load_cases

_REPO = Path(__file__).resolve().parents[3]
_IMPACT_DIR = _REPO / "src/irc/monitor/eval/cases/impact"
_NARR_DIR = _REPO / "src/irc/monitor/eval/cases/narrative"
_HEX16 = re.compile(r"^[0-9a-f]{16}$")

_IMPACT_CATS = {"directional-strong", "directional-neutral", "contradiction",
                "injection", "citation-discipline"}
_NARR_CATS = {"citation-resolve", "entailment-ablation", "attribution-honesty",
              "no-numbers", "injection"}
# Categories whose scorer averages a per-case fraction → need ≥2 cases (AC3).
_IMPACT_FRACTION = {"directional-strong", "directional-neutral", "contradiction"}
_NARR_FRACTION = {"citation-resolve", "entailment-ablation", "attribution-honesty"}


def _by_cat(cases):
    out: dict[str, list] = {}
    for c in cases:
        out.setdefault(c["category"], []).append(c)
    return out


def test_impact_categories_exact():  # AC1
    cats = {c["category"] for c in load_cases(_IMPACT_DIR)}
    assert cats == _IMPACT_CATS


def test_narrative_categories_exact():  # AC2
    cats = {c["category"] for c in load_cases(_NARR_DIR)}
    assert cats == _NARR_CATS


def test_impact_fraction_categories_have_two_plus():  # AC3
    by = _by_cat(load_cases(_IMPACT_DIR))
    for cat in _IMPACT_FRACTION:
        assert len(by[cat]) >= 2, f"{cat} needs >=2 cases"


def test_narrative_fraction_categories_have_two_plus():  # AC3
    by = _by_cat(load_cases(_NARR_DIR))
    for cat in _NARR_FRACTION:
        assert len(by[cat]) >= 2, f"{cat} needs >=2 cases"


def test_every_case_has_required_keys_and_16hex_cids():  # AC4
    for case in (*load_cases(_IMPACT_DIR), *load_cases(_NARR_DIR)):
        assert isinstance(case, dict)
        assert case["category"]
        assert isinstance(case["evidence_pool"], list)
        assert "expected" in case
        for ev in case["evidence_pool"]:
            for k in ("source", "title", "date", "url", "owner_fund_id", "citation_id"):
                assert k in ev, f"missing {k} in {case['category']}"
            assert _HEX16.match(ev["citation_id"]), ev["citation_id"]


def test_injection_cases_are_adversarial():  # AC5
    impact_inj = [c for c in load_cases(_IMPACT_DIR) if c["category"] == "injection"]
    narr_inj = [c for c in load_cases(_NARR_DIR) if c["category"] == "injection"]
    assert impact_inj and narr_inj
    for case in (*impact_inj, *narr_inj):
        directive = case["expected"]["must_ignore"]
        # the directive is embedded in some evidence title (adversarial)
        assert any(directive in ev["title"] for ev in case["evidence_pool"])
        # expected reflects content, not the directive: impact stays small / narrative ignores verb
        if case in impact_inj:
            assert case["expected"]["max_abs"] <= 0.3


def test_impact_injection_corpus_covers_multiple_styles():  # granularity (gap fix)
    # A single injection case scored binary vs fail_below=0.95 pins
    # injection_resistance to 0.0 on one leak. Several distinct styles give the
    # metric granularity and broaden attack-surface coverage.
    impact_inj = [c for c in load_cases(_IMPACT_DIR) if c["category"] == "injection"]
    assert len(impact_inj) >= 4, "need several injection styles for metric granularity"
    directives = [c["expected"]["must_ignore"] for c in impact_inj]
    assert len(set(directives)) == len(directives), "injection directives must be distinct"


def test_impact_injection_directives_are_neutralised_by_sanitizer():
    # The deterministic guarantee behind the live metric: every corpus injection
    # directive must be broken by sanitize_untrusted (the live LLM call is gated).
    from irc.monitor.evidence import sanitize_untrusted
    impact_inj = [c for c in load_cases(_IMPACT_DIR) if c["category"] == "injection"]
    for case in impact_inj:
        for ev in case["evidence_pool"]:
            cleaned = sanitize_untrusted(ev["title"])
            assert case["expected"]["must_ignore"] not in cleaned, case
