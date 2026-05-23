"""Live verification of ``ak.fund_announcement_em`` (Slice E13, Q4 hard-stop gate).

Why this file exists: item 005 (Slice F) wires ``fund_announcement_em`` as the
ONLY ``citation_kind="information"`` source for gold (``518880``) and
cn_bond_fund (``000001``). If the function is missing, empty, or schema-drifted
in the pinned AkShare, item 005 cannot ship its information leg — every gold
and cn_bond_fund row would fail the dual-coverage citation gate.

This file is the Q4 prerequisite test. The autodev orchestrator reads its
exit code as the gate signal: PASS proceeds to item 005, FAIL stops the run
and surfaces the structured ``Q4 PREREQUISITE FAILURE`` message.

Run::

    IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare \\
        tests/fundamentals/test_fund_announcement_em_live.py -v -s

Default ``pytest`` invocations skip every test in this file (both the marker
and the env var are required — see ``CONTEXT.md`` "Live test gate").
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

# ── Dual-gate preamble ──────────────────────────────────────────────────────

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        not _RUN,
        reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests",
    ),
]

# ── Logical-to-AkShare column equivalence map ───────────────────────────────

COLUMN_EQUIVALENCE: dict[str, tuple[str, ...]] = {
    "title": ("公告标题", "标题", "title"),
    "type":  ("公告类型", "类型", "type"),
    "date":  ("公告日期", "公告时间", "日期", "发布日期", "date"),
    "url":   ("公告链接", "链接", "url"),
}

# Per-symbol minimum row thresholds. 518880/000001 are long-running products
# with frequent disclosures; 005827 is a more recent active fund with fewer
# announcements but still expected to exceed N_MIN=3.
N_MIN: dict[str, int] = {
    "518880": 5,
    "000001": 5,
    "005827": 3,
}

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "akshare"


# ── Helpers (importable by the failure-modes companion file) ────────────────

def _akshare_version() -> str:
    """Return the installed AkShare version string, or 'unknown' on failure."""
    try:
        import akshare  # local import — see preamble docstring rationale
        return getattr(akshare, "__version__", "unknown")
    except Exception as exc:  # pragma: no cover — surface env defects loudly
        return f"unimportable ({type(exc).__name__})"


def _resolve_column(df: pd.DataFrame, logical: str) -> str:
    """Resolve a logical column name to the actual AkShare column.

    Raises an ``AssertionError`` carrying the structured Q4 prerequisite
    failure message if no candidate matches. The message lists the expected
    candidates and the observed columns so a future reader (orchestrator or
    human triage) gets the next action without re-reading the diagnosis doc.
    """
    candidates = COLUMN_EQUIVALENCE[logical]
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    raise AssertionError(
        "Q4 PREREQUISITE FAILURE: ak.fund_announcement_em returned a DataFrame "
        f"missing the '{logical}' column. Expected one of {candidates!r}. "
        f"Got columns: {sorted(df.columns)!r}. AkShare schema may have changed. "
        "STOP and re-decide Q4. See docs/diagnosis-thesis-cards-evidence-gap.md §5."
    )


# ── Tests ───────────────────────────────────────────────────────────────────

def test_fund_announcement_em_adapter_exists() -> None:
    """Preflight: ``ak.fund_announcement_em`` is callable in the pinned AkShare.

    Runs FIRST in this file so a missing function fails with the Q4 message
    instead of a buried ``AttributeError`` traceback inside ``_ak_call``.
    """
    try:
        import akshare as ak
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "akshare not installed in this venv. "
            "Install with: uv sync --extra dev (or check pyproject.toml dependencies). "
            f"Underlying error: {exc}"
        ) from exc

    if not hasattr(ak, "fund_announcement_em"):
        raise AssertionError(
            "Q4 PREREQUISITE FAILURE: ak.fund_announcement_em is missing from "
            f"the installed AkShare ({_akshare_version()}). Item 005 cannot "
            "ship its information leg. STOP and re-decide Q4 (option b: "
            "theme-report scope-promotion, option c: exclude gold + "
            "cn_bond_fund from V1). See docs/diagnosis-thesis-cards-evidence-gap.md §5."
        )
    print(
        f"\n  ✓ ak.fund_announcement_em present in AkShare {_akshare_version()}"
    )


def _capture_fixture(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` as UTF-8 JSON to ``path`` atomically (.tmp → os.replace).

    Format::

        {
          "columns": [...],
          "rows":    [{...}, ...],
          "captured_at":    "<ISO-8601 UTC>",
          "akshare_version": "<version>"
        }

    Chinese column names are preserved verbatim (``ensure_ascii=False``).
    Overwrite policy: ALWAYS overwrite on every successful live run — the
    fixture is a captured shadow of the latest live response, not a frozen
    snapshot. Tests never assert content equality against the fixture, so
    daily content drift is benign.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "columns": list(df.columns),
        "rows": df.to_dict(orient="records"),
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "akshare_version": _akshare_version(),
    }
    # Atomic write via tempfile in the same directory + os.replace.
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _assert_announcement_df(df: object, symbol: str) -> pd.DataFrame:
    """Per-symbol structural assertions. Returns ``df`` for chaining.

    Asserts:
      1. ``isinstance(df, pd.DataFrame)`` — covers Q-G (None / non-DataFrame).
      2. ``len(df) >= N_MIN[symbol]`` — threshold ratchet for row count.
      3. The 4 logical columns resolve via ``_resolve_column``.
      4. Row 0's resolved cells are non-null and non-empty-string (Q-H).
    """
    if not isinstance(df, pd.DataFrame):
        raise AssertionError(
            f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
            f"returned a non-DataFrame ({type(df).__name__}) — possibly an "
            "AkShare error path. STOP and re-decide Q4. "
            "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
        )
    n = len(df)
    if n < N_MIN[symbol]:
        raise AssertionError(
            f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
            f"returned {n} rows; threshold is {N_MIN[symbol]}. "
            "Information leg unreliable. STOP and re-decide Q4. "
            "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
        )
    for logical in ("title", "type", "date", "url"):
        col = _resolve_column(df, logical)
        first = df.iloc[0][col]
        if first is None or (isinstance(first, str) and first.strip() == ""):
            raise AssertionError(
                f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
                f"returned a DataFrame whose '{logical}' column ({col!r}) "
                f"is null/empty on row 0. STOP and re-decide Q4. "
                "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
            )
    return df  # type: ignore[return-value]


def _call_fund_announcement_em(symbol: str) -> pd.DataFrame:
    """Indirection so per-symbol tests + the aggregate gate share one path.

    Uses ``_ak_call`` from the project's wrapper (NOT a direct ``ak`` import)
    so future fixture-driven mocking patches the same function.
    """
    from irc.fundamentals.akshare_fundamentals import _ak_call
    try:
        return _ak_call("fund_announcement_em", symbol=symbol)
    except Exception as exc:
        raise AssertionError(
            f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
            f"raised {type(exc).__name__}: {exc}. Information leg unreachable. "
            "STOP and re-decide Q4. "
            "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
        ) from exc


def test_fund_announcement_em_gold_518880() -> None:
    """Gold ETF (518880) returns ≥5 announcements with required columns.

    On success, captures the fixture to
    ``tests/fixtures/akshare/fund_announcement_em_518880.json``.
    """
    symbol = "518880"
    df = _call_fund_announcement_em(symbol)
    _assert_announcement_df(df, symbol)
    fixture_path = _FIXTURE_DIR / f"fund_announcement_em_{symbol}.json"
    _capture_fixture(df, fixture_path)
    date_col = _resolve_column(df, "date")
    url_col = _resolve_column(df, "url")
    latest = df.iloc[0][date_col]
    latest_url = str(df.iloc[0][url_col])
    print(
        f"\n  ✓ fund_announcement_em/{symbol} → {len(df)} rows, "
        f"latest={latest}, url={latest_url[:60]}"
    )


def test_fund_announcement_em_bond_000001() -> None:
    """Bond fund (000001, 华夏成长) returns ≥5 announcements with required columns."""
    symbol = "000001"
    df = _call_fund_announcement_em(symbol)
    _assert_announcement_df(df, symbol)
    fixture_path = _FIXTURE_DIR / f"fund_announcement_em_{symbol}.json"
    _capture_fixture(df, fixture_path)
    date_col = _resolve_column(df, "date")
    url_col = _resolve_column(df, "url")
    print(
        f"\n  ✓ fund_announcement_em/{symbol} → {len(df)} rows, "
        f"latest={df.iloc[0][date_col]}, url={str(df.iloc[0][url_col])[:60]}"
    )


def test_fund_announcement_em_active_005827() -> None:
    """Active equity fund (005827, 易方达蓝筹精选) sanity check: ≥3 announcements."""
    symbol = "005827"
    df = _call_fund_announcement_em(symbol)
    _assert_announcement_df(df, symbol)
    fixture_path = _FIXTURE_DIR / f"fund_announcement_em_{symbol}.json"
    _capture_fixture(df, fixture_path)
    date_col = _resolve_column(df, "date")
    url_col = _resolve_column(df, "url")
    print(
        f"\n  ✓ fund_announcement_em/{symbol} → {len(df)} rows, "
        f"latest={df.iloc[0][date_col]}, url={str(df.iloc[0][url_col])[:60]}"
    )


def test_fund_announcement_em_q4_gate() -> None:
    """Aggregate Q4 gate: all 3 symbols must PASS.

    The autodev orchestrator reads this test's exit code as the gate signal.
    Re-calls AkShare independently of the per-symbol tests (pytest does not
    natively thread results between tests; three extra calls is negligible
    and keeps the gate self-contained).

    On failure, raises with a multi-line summary listing every failing symbol
    so a single read of the failure shows the full picture.
    """
    results: dict[str, str] = {}  # symbol -> "PASS" or failure detail
    for symbol in ("518880", "000001", "005827"):
        try:
            df = _call_fund_announcement_em(symbol)
            _assert_announcement_df(df, symbol)
            results[symbol] = "PASS"
        except AssertionError as exc:
            # First line of the message is the structured Q4 prefix.
            first_line = str(exc).splitlines()[0]
            results[symbol] = f"FAIL — {first_line}"

    failures = {s: r for s, r in results.items() if r != "PASS"}
    if failures:
        joined = "\n".join(f"  • {s}: {detail}" for s, detail in failures.items())
        raise AssertionError(
            "Q4 PREREQUISITE FAILURE (aggregate gate): "
            f"{len(failures)} of 3 symbol(s) failed.\n{joined}\n"
            "STOP and re-decide Q4. See docs/diagnosis-thesis-cards-evidence-gap.md §5 "
            "for the three fall-back options (a: re-pin AkShare, b: theme-report "
            "scope promotion, c: exclude gold + cn_bond_fund from V1)."
        )
    print(
        f"\n  ✓ Q4 gate: all 3 symbols PASS "
        f"(AkShare {_akshare_version()})"
    )
