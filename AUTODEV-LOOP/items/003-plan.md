# 003 — Plan

## Step 1 — failing tests (Red)

`tests/evals/test_locator.py`:

```python
"""Locator behaviour tests.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/003-spec.md
"""
from __future__ import annotations
from pathlib import Path

import pytest

from evals._shared.locator import LocatedArtifacts, locate


def _touch(p: Path, content: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_returns_none_when_no_outputs_dir(tmp_path: Path) -> None:
    assert locate(tmp_path, ("foo.csv",)) is None


def test_returns_none_when_no_dated_dir_satisfies_contract(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "2026-05-01" / "other.csv")
    assert locate(tmp_path, ("required.csv",)) is None


def test_selects_today_when_full_contract_present(tmp_path: Path) -> None:
    today = "2026-05-18"
    _touch(tmp_path / "outputs" / "2026-05-17" / "foo.csv")
    _touch(tmp_path / "outputs" / today / "foo.csv")
    result = locate(tmp_path, ("foo.csv",), today_iso=today)
    assert result is not None
    assert result.artifact_date == today
    assert result.paths == (tmp_path / "outputs" / today / "foo.csv",)


def test_falls_back_to_latest_when_today_absent(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "2026-05-17" / "foo.csv")
    _touch(tmp_path / "outputs" / "2026-05-01" / "foo.csv")
    result = locate(tmp_path, ("foo.csv",), today_iso="2026-05-18")
    assert result is not None
    assert result.artifact_date == "2026-05-17"


def test_falls_back_when_today_partial(tmp_path: Path) -> None:
    today = "2026-05-18"
    _touch(tmp_path / "outputs" / today / "foo.csv")  # missing bar.yaml
    _touch(tmp_path / "outputs" / "2026-05-17" / "foo.csv")
    _touch(tmp_path / "outputs" / "2026-05-17" / "bar.yaml")
    result = locate(tmp_path, ("foo.csv", "bar.yaml"), today_iso=today)
    assert result is not None
    assert result.artifact_date == "2026-05-17"


def test_rejects_partial_multi_file_set_in_history(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "2026-05-17" / "foo.csv")  # missing bar
    _touch(tmp_path / "outputs" / "2026-05-01" / "foo.csv")
    _touch(tmp_path / "outputs" / "2026-05-01" / "bar.yaml")
    result = locate(tmp_path, ("foo.csv", "bar.yaml"), today_iso="2026-05-18")
    assert result is not None
    assert result.artifact_date == "2026-05-01"


def test_ignores_non_date_subdirs(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "logs" / "foo.csv")
    _touch(tmp_path / "outputs" / "tmp" / "foo.csv")
    assert locate(tmp_path, ("foo.csv",), today_iso="2026-05-18") is None


def test_empty_required_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        locate(tmp_path, (), today_iso="2026-05-18")


def test_paths_preserve_caller_order(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "2026-05-17" / "a")
    _touch(tmp_path / "outputs" / "2026-05-17" / "b")
    _touch(tmp_path / "outputs" / "2026-05-17" / "c")
    result = locate(tmp_path, ("c", "a", "b"), today_iso="2026-05-18")
    assert result is not None
    assert [p.name for p in result.paths] == ["c", "a", "b"]


def test_located_artifacts_is_frozen(tmp_path: Path) -> None:
    _touch(tmp_path / "outputs" / "2026-05-17" / "foo")
    result = locate(tmp_path, ("foo",), today_iso="2026-05-18")
    assert result is not None
    with pytest.raises(Exception):
        result.artifact_date = "x"  # type: ignore[misc]


def test_default_today_iso_uses_asia_shanghai(monkeypatch, tmp_path: Path) -> None:
    """The locator's default `today_iso` comes from `_today_iso()`; we verify it
    is wired up by monkeypatching the helper to a known value."""
    import evals._shared.locator as loc
    fixed = "2099-01-02"
    _touch(tmp_path / "outputs" / fixed / "foo")
    monkeypatch.setattr(loc, "_today_iso", lambda: fixed)
    result = locate(tmp_path, ("foo",))
    assert result is not None
    assert result.artifact_date == fixed
```

Run: `uv run pytest tests/evals/test_locator.py -x` — all FAIL (module not found).

## Step 2 — implementation (Green)

`evals/_shared/locator.py`:

```python
"""Shared artifact locator for dated runner outputs.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/003-spec.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


_TZ = timezone(timedelta(hours=8))  # Asia/Shanghai — project convention
_DATE_LEN = 10  # YYYY-MM-DD


@dataclass(frozen=True)
class LocatedArtifacts:
    paths: tuple[Path, ...]
    artifact_date: str


def _today_iso() -> str:
    return datetime.now(_TZ).date().isoformat()


def _is_date_dir(name: str) -> bool:
    if len(name) != _DATE_LEN:
        return False
    try:
        date.fromisoformat(name)
        return True
    except ValueError:
        return False


def _all_present(date_dir: Path, required_filenames: Iterable[str]) -> bool:
    return all((date_dir / fn).is_file() for fn in required_filenames)


def _build(
    date_dir: Path,
    date_iso: str,
    required_filenames: tuple[str, ...],
) -> LocatedArtifacts:
    return LocatedArtifacts(
        paths=tuple(date_dir / fn for fn in required_filenames),
        artifact_date=date_iso,
    )


def locate(
    repo_root: Path,
    required_filenames: tuple[str, ...],
    *,
    today_iso: str | None = None,
) -> LocatedArtifacts | None:
    """Find the dated artifact set satisfying `required_filenames`.

    Returns the today set if every required filename is present, otherwise the
    latest dated set with a full contract, otherwise None. Partial multi-file
    sets are skipped.
    """
    if not required_filenames:
        raise ValueError("locate() requires at least one filename")
    outputs = repo_root / "outputs"
    if not outputs.is_dir():
        return None
    today = today_iso if today_iso is not None else _today_iso()
    today_dir = outputs / today
    if today_dir.is_dir() and _all_present(today_dir, required_filenames):
        return _build(today_dir, today, required_filenames)
    candidates = sorted(
        (d for d in outputs.iterdir() if d.is_dir() and _is_date_dir(d.name)),
        key=lambda p: p.name,
        reverse=True,
    )
    for d in candidates:
        if _all_present(d, required_filenames):
            return _build(d, d.name, required_filenames)
    return None
```

Run: `uv run pytest tests/evals/test_locator.py -x` — all PASS.

## Step 3 — full suite verification

```
uv run pytest -x
uv run ruff check evals/_shared/locator.py tests/evals/test_locator.py
```

Both exit 0.

## Step 4 — commit

```
feat(evals): add shared dated-artifact locator (003)
```

## Notes / pitfalls

- `_today_iso()` is module-private so tests can monkeypatch it without touching the public signature.
- `today_iso` parameter is the preferred test injection point; the monkeypatch path is only there for the one default-wiring test.
- Use `.is_file()` rather than `.exists()` so a directory accidentally named after a required filename does not satisfy the contract.
- `_is_date_dir` validates via `date.fromisoformat`, which rejects malformed names but accepts valid leap dates.
- Sorted descending by `name` is correct because ISO `YYYY-MM-DD` strings sort lexicographically the same as chronologically.
