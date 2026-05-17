# Item 007 — Implementation Plan

> Reference: `docs/AUTODEV-LOOP/items/007-spec.md`. Base branch: `feat/evidence-wiring-and-memo-enrichment`. Sub-branch: `claude/p1p2-007-traceability-honest-counts`.

**Goal:** Replace the broken token-overlap `coverage_ratio` with honest verbatim-substring counts: `n_refs_provided` and `n_refs_quoted_verbatim`. Keep `n_refs` as a back-compat alias for `n_refs_provided`.

**Architecture:** Single rewrite of `check_traceability()`. Update one writer (`memo_cmd.py`). Rewrite the three existing tests because they hard-code `coverage_ratio`.

---

## Task 1: Rewrite `check_traceability` to verbatim substring match

**Files:** `src/irc/memo/traceability.py`, `tests/memo/test_traceability_fuzzy.py`

### Step 1.1: Rewrite the test file
- [ ] Replace the entire contents of `tests/memo/test_traceability_fuzzy.py` with:

```python
from __future__ import annotations
from irc.memo.traceability import check_traceability


def test_verbatim_quote_counts_as_covered():
    refs = ("[BABA 阿里巴巴] score=75.5",)
    memo = "重点关注 [BABA 阿里巴巴] score=75.5 — 估值便宜。"
    out = check_traceability(memo_text=memo, raw_refs=refs)
    assert out["n_refs_provided"] == 1
    assert out["n_refs_quoted_verbatim"] == 1
    assert out["n_refs"] == 1  # back-compat alias


def test_paraphrased_quote_does_not_count():
    refs = ("[BABA 阿里巴巴] score=75.5",)
    memo = "Alibaba scored about 75 on our composite."
    out = check_traceability(memo_text=memo, raw_refs=refs)
    assert out["n_refs_provided"] == 1
    assert out["n_refs_quoted_verbatim"] == 0
    assert out["n_refs"] == 1


def test_no_refs_returns_zero_provided_zero_quoted():
    out = check_traceability(memo_text="anything", raw_refs=())
    assert out["n_refs_provided"] == 0
    assert out["n_refs_quoted_verbatim"] == 0
    assert out["n_refs"] == 0


def test_partial_coverage_counts_each_ref_independently():
    refs = ("ref-A:exact", "ref-B:exact", "ref-C:exact")
    memo = "Only ref-A:exact and ref-C:exact appear here."
    out = check_traceability(memo_text=memo, raw_refs=refs)
    assert out["n_refs_provided"] == 3
    assert out["n_refs_quoted_verbatim"] == 2


def test_coverage_ratio_key_is_no_longer_present():
    """Regression: the old, misleading coverage_ratio key must be gone."""
    out = check_traceability(memo_text="x", raw_refs=("y",))
    assert "coverage_ratio" not in out
    assert "n_covered" not in out
```

### Step 1.2: Run tests
- [ ] Run: `pytest tests/memo/test_traceability_fuzzy.py -v`
- [ ] Expected: most FAIL because `check_traceability` still returns the old keys.

### Step 1.3: Rewrite `check_traceability`
- [ ] Replace the entire contents of `src/irc/memo/traceability.py` with:

```python
from __future__ import annotations


def check_traceability(
    memo_text: str, raw_refs: tuple[str, ...] | list[str],
) -> dict[str, int]:
    """Count refs that the memo quotes verbatim.

    Reports:
      - n_refs_provided: how many evidence strings the synthesizer was given.
      - n_refs_quoted_verbatim: how many of those strings appear as an exact
        substring of the memo text (case-sensitive — refs are typically
        identifiers / quoted snippets, not free prose).
      - n_refs: back-compat alias for n_refs_provided (some downstream tools
        still read this key).

    We do NOT compute a coverage_ratio. Paraphrased citations were silently
    scored 0 by the previous token-overlap heuristic, especially for Chinese
    text, which made the ratio actively misleading. Reporting raw counts
    lets the reader judge for themselves.
    """
    refs_tuple = tuple(raw_refs)
    n_provided = len(refs_tuple)
    n_quoted = sum(1 for ref in refs_tuple if ref and ref in memo_text)
    return {
        "n_refs_provided": n_provided,
        "n_refs_quoted_verbatim": n_quoted,
        "n_refs": n_provided,
    }
```

### Step 1.4: Run tests, verify pass
- [ ] Run: `pytest tests/memo/test_traceability_fuzzy.py -v`
- [ ] Expected: 5 PASS.

### Step 1.5: Commit
- [ ] Run:

```bash
git add src/irc/memo/traceability.py tests/memo/test_traceability_fuzzy.py
git commit -m "feat(memo/traceability): replace fake coverage_ratio with verbatim quote counts"
```

---

## Task 2: Update the JSON writer in `memo_cmd.py`

**Files:** `src/irc/commands/memo_cmd.py:148-153`

### Step 2.1: Update the writer
- [ ] In `src/irc/commands/memo_cmd.py`, replace lines 148-153:

```python
    atomic_write_text(out_dir / "memo_traceability.json", json.dumps({
        "n_refs_provided": output.traceability["n_refs_provided"],
        "n_refs_quoted_verbatim": output.traceability["n_refs_quoted_verbatim"],
        "n_refs": output.traceability["n_refs"],
    }, indent=2))
    print(
        f"memo OK: {output.traceability['n_refs_quoted_verbatim']}/"
        f"{output.traceability['n_refs_provided']} refs quoted verbatim "
        f"→ {out_dir/'memo.md'}"
    )
```

### Step 2.2: Update the `MemoOutput` type annotation
- [ ] In `src/irc/memo/pipeline.py:56`, change the `MemoOutput.traceability` annotation from `dict[str, float]` to `dict[str, int]`:

```python
    traceability: dict[str, int]
```

### Step 2.3: Find and update any other consumers
- [ ] Run: `grep -rn "coverage_ratio\|n_covered" src/ tests/`
- [ ] Expected: zero hits (the two old keys are gone everywhere).
- [ ] If any hits surface in `tests/commands/test_memo_cmd.py` or `tests/test_e2e_plan3_full_pipeline.py` or elsewhere, update them: rewrite assertions to use the new keys.

### Step 2.4: Run the memo command tests
- [ ] Run: `pytest tests/commands/test_memo_cmd.py tests/memo/ -v`
- [ ] Expected: all PASS.

### Step 2.5: Commit
- [ ] Run:

```bash
git add src/irc/commands/memo_cmd.py src/irc/memo/pipeline.py tests/
git commit -m "feat(memo): write n_refs_provided/n_refs_quoted_verbatim to memo_traceability.json"
```

---

## Task 3: Full-suite verification

### Step 3.1: Run all tests
- [ ] Run: `pytest -q -x`
- [ ] Expected: all PASS. If any unrelated test now references `coverage_ratio`, update it.

### Step 3.2: Ruff
- [ ] Run: `ruff check src/irc/memo/ src/irc/commands/memo_cmd.py tests/memo/`
- [ ] Expected: no new findings.
