"""Live verification of topic-specific fund announcement endpoints (Slice E13, Q4 option a).

Why this file exists: item 005 (Slice F) needs a ``citation_kind="information"``
source for gold (``518880``), cn_bond_fund (``000001``), and active CN equity
fund (``005827``). AkShare 1.18.63 does not expose ``fund_announcement_em``
(the original spec assumed it would). Per Q4 option (a) chosen 2026-05-23, the
three topic-specific endpoints replace the missing unified endpoint:

- ``ak.fund_announcement_dividend_em(symbol)`` — 分红配送 / dividend & distribution
- ``ak.fund_announcement_report_em(symbol)`` — 定期报告 / periodic reports
- ``ak.fund_announcement_personnel_em(symbol)`` — 人员变动 / personnel changes

This file is the Q4 prerequisite test (option a). The aggregate gate passes if
each fund symbol has non-empty data from AT LEAST ONE of the three endpoints.

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

# ── Topic-specific endpoints (Q4 option a) ──────────────────────────────────

TOPIC_ENDPOINTS: tuple[str, ...] = (
    "fund_announcement_dividend_em",
    "fund_announcement_report_em",
    "fund_announcement_personnel_em",
)

SYMBOLS: tuple[str, ...] = ("518880", "000001", "005827")

# ── Per-endpoint column equivalence map ─────────────────────────────────────
# All three endpoints share the same schema in AkShare 1.18.63:
#   ['基金代码', '公告标题', '基金名称', '公告日期', '报告ID']
# Note: no '公告类型' (type) or '公告链接' (url) columns.
# '报告ID' is the canonical reference identifier (opaque string).

COLUMN_EQUIVALENCE: dict[str, dict[str, tuple[str, ...]]] = {
    "fund_announcement_dividend_em": {
        "title": ("公告标题", "标题", "title"),
        "date":  ("公告日期", "公告时间", "日期", "发布日期", "date"),
        "id":    ("报告ID", "id"),
        "fund":  ("基金代码", "code"),
    },
    "fund_announcement_report_em": {
        "title": ("公告标题", "标题", "title"),
        "date":  ("公告日期", "公告时间", "日期", "发布日期", "date"),
        "id":    ("报告ID", "id"),
        "fund":  ("基金代码", "code"),
    },
    "fund_announcement_personnel_em": {
        "title": ("公告标题", "标题", "title"),
        "date":  ("公告日期", "公告时间", "日期", "发布日期", "date"),
        "id":    ("报告ID", "id"),
        "fund":  ("基金代码", "code"),
    },
}

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "akshare"


# ── Helpers ─────────────────────────────────────────────────────────────────

def _akshare_version() -> str:
    """Return the installed AkShare version string, or 'unknown' on failure."""
    try:
        import akshare  # local import — avoids top-level import in non-live runs
        return getattr(akshare, "__version__", "unknown")
    except Exception as exc:  # pragma: no cover
        return f"unimportable ({type(exc).__name__})"


def _resolve_column(df: pd.DataFrame, logical: str, endpoint: str) -> str:
    """Resolve a logical column name to the actual AkShare column for an endpoint.

    Raises ``AssertionError`` with a structured Q4 failure message if no
    candidate matches.
    """
    candidates = COLUMN_EQUIVALENCE[endpoint][logical]
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    raise AssertionError(
        f"Q4 PIVOT FAILURE: ak.{endpoint} returned a DataFrame "
        f"missing the '{logical}' column. Expected one of {candidates!r}. "
        f"Got columns: {sorted(df.columns)!r}. AkShare schema may have changed. "
        "See docs/2026-05-22-thesis-cards-evidence-gap/items/004-spec.md §Pivot."
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
    Overwrite policy: ALWAYS overwrite on every successful live run.
    Empty DataFrames produce ``"rows": []`` — still a valid fixture (captures schema).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "columns": list(df.columns),
        "rows": df.to_dict(orient="records"),
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "akshare_version": _akshare_version(),
    }
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


def _call_endpoint(endpoint: str, symbol: str) -> pd.DataFrame:
    """Call a topic-specific endpoint through ``_ak_call``.

    Returns the DataFrame (possibly empty). Wraps exceptions in a structured
    Q4 failure message so the caller gets the right diagnostic.
    """
    from irc.fundamentals.akshare_fundamentals import _ak_call
    try:
        result = _ak_call(endpoint, symbol=symbol)
    except Exception as exc:
        raise AssertionError(
            f"Q4 PIVOT FAILURE: ak.{endpoint}(symbol={symbol!r}) "
            f"raised {type(exc).__name__}: {exc}. Endpoint unreachable. "
            "See docs/2026-05-22-thesis-cards-evidence-gap/items/004-spec.md §Pivot."
        ) from exc
    if not isinstance(result, pd.DataFrame):
        raise AssertionError(
            f"Q4 PIVOT FAILURE: ak.{endpoint}(symbol={symbol!r}) "
            f"returned a non-DataFrame ({type(result).__name__}). "
            "See docs/2026-05-22-thesis-cards-evidence-gap/items/004-spec.md §Pivot."
        )
    return result


def _assert_non_empty_df(df: pd.DataFrame, endpoint: str, symbol: str) -> None:
    """Assert a non-empty DataFrame with resolvable title + date columns.

    Called only when a test asserts non-empty. For cells that may legitimately
    be empty, use _call_endpoint directly and allow zero rows.
    """
    assert len(df) > 0, (
        f"Q4 PIVOT FAILURE: ak.{endpoint}(symbol={symbol!r}) returned 0 rows. "
        "Expected at least 1 announcement. "
        "See docs/2026-05-22-thesis-cards-evidence-gap/items/004-spec.md §Pivot."
    )
    title_col = _resolve_column(df, "title", endpoint)
    date_col = _resolve_column(df, "date", endpoint)
    first_title = df.iloc[0][title_col]
    first_date = df.iloc[0][date_col]
    assert first_title is not None and str(first_title).strip() != "", (
        f"Q4 PIVOT FAILURE: ak.{endpoint}(symbol={symbol!r}) row 0 '{title_col}' is null/empty."
    )
    assert first_date is not None, (
        f"Q4 PIVOT FAILURE: ak.{endpoint}(symbol={symbol!r}) row 0 '{date_col}' is null."
    )


# ── Tests ───────────────────────────────────────────────────────────────────

def test_fund_announcement_endpoints_exist() -> None:
    """Preflight: all 3 topic-specific endpoints are present in the pinned AkShare.

    Runs first so a missing endpoint fails with a clear diagnostic rather than
    a buried AttributeError inside _call_endpoint.
    """
    try:
        import akshare as ak
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "akshare not installed in this venv. "
            "Install with: uv sync --extra dev (or check pyproject.toml dependencies). "
            f"Underlying error: {exc}"
        ) from exc

    missing = [fn for fn in TOPIC_ENDPOINTS if not hasattr(ak, fn)]
    if missing:
        raise AssertionError(
            f"Q4 PIVOT FAILURE: the following topic-specific endpoints are missing from "
            f"AkShare {_akshare_version()}: {missing}. "
            "Option (a) cannot proceed. "
            "See docs/2026-05-22-thesis-cards-evidence-gap/items/004-spec.md §Pivot."
        )
    print(
        f"\n  ✓ All 3 topic-specific announcement endpoints present "
        f"in AkShare {_akshare_version()}"
    )


# ── dividend_em per-symbol tests ─────────────────────────────────────────────

def test_fund_announcement_dividend_em_518880_non_empty() -> None:
    """Gold ETF (518880) dividend announcements: returns DataFrame (non-empty)."""
    endpoint, symbol = "fund_announcement_dividend_em", "518880"
    df = _call_endpoint(endpoint, symbol)
    _assert_non_empty_df(df, endpoint, symbol)
    _capture_fixture(df, _FIXTURE_DIR / f"{endpoint}_{symbol}.json")
    print(f"\n  ✓ {endpoint}/{symbol} → {len(df)} rows")


def test_fund_announcement_dividend_em_000001_non_empty() -> None:
    """Bond fund (000001) dividend announcements: returns non-empty DataFrame."""
    endpoint, symbol = "fund_announcement_dividend_em", "000001"
    df = _call_endpoint(endpoint, symbol)
    _assert_non_empty_df(df, endpoint, symbol)
    _capture_fixture(df, _FIXTURE_DIR / f"{endpoint}_{symbol}.json")
    print(f"\n  ✓ {endpoint}/{symbol} → {len(df)} rows")


def test_fund_announcement_dividend_em_005827_non_empty() -> None:
    """Active equity fund (005827) dividend announcements: returns DataFrame.

    005827 returned only 1 dividend announcement in AkShare 1.18.63.
    The per-symbol test asserts non-empty (>=1). The aggregate gate uses
    report_em as the primary coverage check for this symbol.
    """
    endpoint, symbol = "fund_announcement_dividend_em", "005827"
    df = _call_endpoint(endpoint, symbol)
    _assert_non_empty_df(df, endpoint, symbol)
    _capture_fixture(df, _FIXTURE_DIR / f"{endpoint}_{symbol}.json")
    print(f"\n  ✓ {endpoint}/{symbol} → {len(df)} rows")


# ── report_em per-symbol tests ───────────────────────────────────────────────

def test_fund_announcement_report_em_518880_non_empty() -> None:
    """Gold ETF (518880) periodic reports: returns non-empty DataFrame."""
    endpoint, symbol = "fund_announcement_report_em", "518880"
    df = _call_endpoint(endpoint, symbol)
    _assert_non_empty_df(df, endpoint, symbol)
    _capture_fixture(df, _FIXTURE_DIR / f"{endpoint}_{symbol}.json")
    print(f"\n  ✓ {endpoint}/{symbol} → {len(df)} rows")


def test_fund_announcement_report_em_000001_non_empty() -> None:
    """Bond fund (000001) periodic reports: returns non-empty DataFrame."""
    endpoint, symbol = "fund_announcement_report_em", "000001"
    df = _call_endpoint(endpoint, symbol)
    _assert_non_empty_df(df, endpoint, symbol)
    _capture_fixture(df, _FIXTURE_DIR / f"{endpoint}_{symbol}.json")
    print(f"\n  ✓ {endpoint}/{symbol} → {len(df)} rows")


def test_fund_announcement_report_em_005827_non_empty() -> None:
    """Active equity fund (005827) periodic reports: returns non-empty DataFrame."""
    endpoint, symbol = "fund_announcement_report_em", "005827"
    df = _call_endpoint(endpoint, symbol)
    _assert_non_empty_df(df, endpoint, symbol)
    _capture_fixture(df, _FIXTURE_DIR / f"{endpoint}_{symbol}.json")
    print(f"\n  ✓ {endpoint}/{symbol} → {len(df)} rows")


# ── personnel_em per-symbol tests ────────────────────────────────────────────

def test_fund_announcement_personnel_em_518880_non_empty() -> None:
    """Gold ETF (518880) personnel changes: returns DataFrame (non-empty)."""
    endpoint, symbol = "fund_announcement_personnel_em", "518880"
    df = _call_endpoint(endpoint, symbol)
    _assert_non_empty_df(df, endpoint, symbol)
    _capture_fixture(df, _FIXTURE_DIR / f"{endpoint}_{symbol}.json")
    print(f"\n  ✓ {endpoint}/{symbol} → {len(df)} rows")


def test_fund_announcement_personnel_em_000001_non_empty() -> None:
    """Bond fund (000001) personnel changes: returns non-empty DataFrame."""
    endpoint, symbol = "fund_announcement_personnel_em", "000001"
    df = _call_endpoint(endpoint, symbol)
    _assert_non_empty_df(df, endpoint, symbol)
    _capture_fixture(df, _FIXTURE_DIR / f"{endpoint}_{symbol}.json")
    print(f"\n  ✓ {endpoint}/{symbol} → {len(df)} rows")


def test_fund_announcement_personnel_em_005827_non_empty() -> None:
    """Active equity fund (005827) personnel changes: returns DataFrame (non-empty)."""
    endpoint, symbol = "fund_announcement_personnel_em", "005827"
    df = _call_endpoint(endpoint, symbol)
    _assert_non_empty_df(df, endpoint, symbol)
    _capture_fixture(df, _FIXTURE_DIR / f"{endpoint}_{symbol}.json")
    print(f"\n  ✓ {endpoint}/{symbol} → {len(df)} rows")


# ── Aggregate Q4 gate ────────────────────────────────────────────────────────

def test_fund_announcement_q4_aggregate_gate() -> None:
    """Aggregate Q4 gate (option a): each symbol must have coverage from >= 1 endpoint.

    The autodev orchestrator reads this test's exit code as the gate signal.
    PASSes if for every symbol in (518880, 000001, 005827) at least one of the
    3 topic-specific endpoints returns a non-empty DataFrame.

    Per-endpoint × per-symbol results are collected into a structured summary
    dict and written to tests/fixtures/akshare/q4_aggregate_gate_summary.json
    for provenance.
    """
    summary: dict[str, dict[str, object]] = {}
    symbol_covered: dict[str, bool] = {s: False for s in SYMBOLS}

    for endpoint in TOPIC_ENDPOINTS:
        for symbol in SYMBOLS:
            try:
                df = _call_endpoint(endpoint, symbol)
                n = len(df)
                status = "pass" if n > 0 else "empty"
                summary.setdefault(endpoint, {})[symbol] = {"rows": n, "status": status}
                if n > 0:
                    symbol_covered[symbol] = True
            except AssertionError as exc:
                summary.setdefault(endpoint, {})[symbol] = {
                    "rows": 0,
                    "status": "error",
                    "detail": str(exc).splitlines()[0],
                }

    # Write aggregate summary fixture
    summary_path = _FIXTURE_DIR / "q4_aggregate_gate_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_payload = {
        "summary": summary,
        "symbol_covered": symbol_covered,
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "akshare_version": _akshare_version(),
    }
    fd, tmp_path_str = tempfile.mkstemp(
        prefix="q4_aggregate_gate_summary.json.",
        suffix=".tmp",
        dir=str(summary_path.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(summary_payload, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp_path, summary_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    uncovered = [s for s, covered in symbol_covered.items() if not covered]
    if uncovered:
        detail_lines = []
        for sym in uncovered:
            for ep in TOPIC_ENDPOINTS:
                cell = summary.get(ep, {}).get(sym, {})
                detail_lines.append(f"  {ep}/{sym}: {cell}")
        raise AssertionError(
            "Q4 PIVOT FAILURE (aggregate gate): the following symbol(s) have NO "
            f"non-empty data from any of the 3 topic-specific endpoints: {uncovered}\n"
            + "\n".join(detail_lines)
            + "\nSee docs/2026-05-22-thesis-cards-evidence-gap/items/004-spec.md §Pivot."
        )

    print(
        f"\n  ✓ Q4 aggregate gate (option a): all 3 symbols covered "
        f"(AkShare {_akshare_version()})"
    )
    for endpoint in TOPIC_ENDPOINTS:
        for symbol in SYMBOLS:
            cell = summary.get(endpoint, {}).get(symbol, {})
            print(f"    {endpoint}/{symbol}: {cell.get('rows', '?')} rows [{cell.get('status', '?')}]")


# ── Legacy helpers kept for failure-modes companion compatibility ────────────
# The companion file (test_fund_announcement_em_failure_modes.py) imports these
# names. They are preserved to avoid breaking the companion — it patches
# _ak_call and exercises the error-path assertions, which remain valid for the
# pivoted endpoints as well.

def _assert_announcement_df(df: object, symbol: str) -> pd.DataFrame:
    """Legacy per-symbol structural assertion (used by failure-modes companion).

    Uses a generic column set covering the original spec's logical columns.
    The pivot uses _assert_non_empty_df + per-endpoint COLUMN_EQUIVALENCE instead,
    but this helper is kept to avoid modifying the companion file.
    """
    if not isinstance(df, pd.DataFrame):
        raise AssertionError(
            f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
            f"returned a non-DataFrame ({type(df).__name__}) — possibly an "
            "AkShare error path. STOP and re-decide Q4. "
            "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
        )
    # Use N_MIN defaults from original spec for the companion's threshold tests
    _n_min: dict[str, int] = {"518880": 5, "000001": 5, "005827": 3}
    n = len(df)
    threshold = _n_min.get(symbol, 1)
    if n < threshold:
        raise AssertionError(
            f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
            f"returned {n} rows; threshold is {threshold}. "
            "Information leg unreliable. STOP and re-decide Q4. "
            "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
        )
    # Check logical columns using the original spec's equivalence (fallback to generic)
    _legacy_eq: dict[str, tuple[str, ...]] = {
        "title": ("公告标题", "标题", "title"),
        "type":  ("公告类型", "类型", "type"),
        "date":  ("公告日期", "公告时间", "日期", "发布日期", "date"),
        "url":   ("公告链接", "链接", "url"),
    }
    for logical in ("title", "type", "date", "url"):
        candidates = _legacy_eq[logical]
        resolved = next((c for c in candidates if c in df.columns), None)
        if resolved is None:
            raise AssertionError(
                f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em returned a DataFrame "
                f"missing the '{logical}' column. Expected one of {candidates!r}. "
                f"Got columns: {sorted(df.columns)!r}. AkShare schema may have changed. "
                "STOP and re-decide Q4. See docs/diagnosis-thesis-cards-evidence-gap.md §5."
            )
        first = df.iloc[0][resolved]
        if first is None or (isinstance(first, str) and first.strip() == ""):
            raise AssertionError(
                f"Q4 PREREQUISITE FAILURE: ak.fund_announcement_em(symbol={symbol!r}) "
                f"returned a DataFrame whose '{logical}' column ({resolved!r}) "
                f"is null/empty on row 0. STOP and re-decide Q4. "
                "See docs/diagnosis-thesis-cards-evidence-gap.md §5."
            )
    return df  # type: ignore[return-value]


def _call_fund_announcement_em(symbol: str) -> pd.DataFrame:
    """Legacy call wrapper (used by failure-modes companion).

    Preserved to avoid modifying the companion file. Routes through _ak_call
    using the original endpoint name (which is missing in AkShare 1.18.63,
    but the companion patches _ak_call so the actual endpoint is irrelevant).
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
