"""QDII premium-to-NAV memo-surface module (item 003).

Pure module. Tier-1 import contract: imports from `irc.schemas.discovery`
(for `QDII_MAX_PREMIUM_DEFAULT`) and stdlib only — NO imports from
`irc.opportunity.*`, `irc.scoring.*`, or `irc.commands.*`. Mirrors
`aliases.py` / `concentration.py` per the renderer tier-1 import contract.

Surfaces four things consumed by the memo edge:
  1. `QDII_PREMIUM_THRESHOLD_PCT` — alias of `QDII_MAX_PREMIUM_DEFAULT` so
     the memo display value can never drift from the decision-gate value.
  2. `QDII_PREMIUM_MARKER_BEGIN/END` — deterministic §6 marker pair.
  3. Pure render helpers: `_format_qdii_premium_cell`,
     `build_qdii_premium_projection`, `render_qdii_premium_block`,
     `format_qdii_premium_prefix`.
  4. `write_qdii_premium_snapshot` — the only I/O edge, writes the
     top-level `outputs/<date>/qdii_premium.json` projection artefact
     via `irc.io_utils.atomic_write_text`.

See docs/adr/0006-qdii-premium-memo-surface.md and
docs/2026-05-27-instrument-pickability/items/003-spec.md.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

from irc.schemas.discovery import QDII_MAX_PREMIUM_DEFAULT


# AC5: re-export alias (NOT a redefinition) so the memo display value
# tracks the decision-gate value forever.
QDII_PREMIUM_THRESHOLD_PCT: Final[float] = QDII_MAX_PREMIUM_DEFAULT

# AC7 / G-Q2: marker constants live in the producing module
# (concentration.py / macro_pillar.py precedent).
QDII_PREMIUM_MARKER_BEGIN: Final[str] = "<!-- IRC_QDII_PREMIUM_BEGIN -->"
QDII_PREMIUM_MARKER_END: Final[str] = "<!-- IRC_QDII_PREMIUM_END -->"

# AC2 spec: QDII asset-class set comes from scoring.qdii_premium per the
# canonical home declaration there. We re-list as a module-local frozenset to
# keep the tier-1 import contract (no imports from irc.scoring.*).
_QDII_ASSET_CLASSES_LOCAL: Final[frozenset[str]] = frozenset(
    {"us_etf", "hk_etf", "qdii_global"}
)


def _format_qdii_premium_cell(
    qdii_premium_pct: float | None,
    asset_class: str,
) -> str:
    """Render the 溢价 picks-table cell (AC2).

    Branches:
      - None              → `—` (non-QDII rows; matches empty-citations).
      - 0.0 + QDII class  → `0.00%（场外申赎）` (synthetic-zero off-exchange).
      - non-zero          → `+{pct:.2f}%` / `-{pct:.2f}%` (signed, 2 decimals).
      - 0.0 + non-QDII    → `—` (defensive; structurally impossible).
    """
    if qdii_premium_pct is None:
        return "—"
    if qdii_premium_pct == 0.0:
        if asset_class in _QDII_ASSET_CLASSES_LOCAL:
            return "0.00%（场外申赎）"
        return "—"
    pct = qdii_premium_pct * 100
    sign = "+" if pct > 0 else "-"
    return f"{sign}{abs(pct):.2f}%"


def _coerce_premium(value: object) -> float | None:
    """Best-effort float coercion. Returns None when value is None,
    unparseable, or non-finite (nan / inf / -inf) — same pattern as
    `_decision_status_for_pick`.

    Non-finite guard is load-bearing: `nan > THRESHOLD` evaluates `False`,
    so a `nan` premium from a malformed upstream scorer would silently
    bypass the §7 hard-block and render as `"nan%"` / `"-nan%"` in §5.
    `json.dumps` would also emit literal `NaN` (not valid per RFC 8259)
    in the projection artifact. Refuse non-finite at the boundary
    (adversarial + silent-failure-hunter P1 finding on PR #78).
    """
    import math
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _project_row(score_row: dict) -> dict | None:
    """One projection row from one scoring row. Returns None when the
    row has no premium signal (filters out non-QDII + unknown-premium
    rows in one pass)."""
    pct = _coerce_premium(score_row.get("qdii_premium_pct"))
    if pct is None:
        return None
    asset_class = str(score_row.get("asset_class") or "")
    return {
        "instrument_id": str(score_row.get("instrument_id") or ""),
        "name_cn": str(score_row.get("name_cn") or ""),
        "asset_class": asset_class,
        "market": str(score_row.get("market") or ""),
        "qdii_premium_pct": pct,
        "blocking": pct > QDII_PREMIUM_THRESHOLD_PCT,
        "render_cell": _format_qdii_premium_cell(pct, asset_class),
    }


def build_qdii_premium_projection(
    score_rows: Sequence[dict],
    *,
    evidence_cutoff: str | None,
    now_fn: Callable[[], datetime],
) -> dict:
    """Build the deterministic projection dict consumed by both the §6
    marker block and the qdii_premium.json artefact (AC6 / AC14).

    Pure. `now_fn` is the clock-injection edge so two-run byte equality
    holds under test stubs and the production caller passes
    `lambda: datetime.now(timezone(timedelta(hours=8)))`.
    """
    rows = [r for r in (_project_row(s) for s in score_rows) if r is not None]
    rows.sort(key=lambda r: r["instrument_id"])
    return {
        "generated_at": now_fn().isoformat(),
        "threshold_pct": QDII_PREMIUM_THRESHOLD_PCT,
        "evidence_cutoff": evidence_cutoff,
        "rows": rows,
    }


def _format_row_bullet(row: dict) -> str:
    """One " - {iid} {name}：{cell}{（超阈值，已暂缓执行） if blocking}" line."""
    base = f" - {row['instrument_id']} {row['name_cn']}：{row['render_cell']}"
    if row.get("blocking"):
        return base + "（超阈值，已暂缓执行）"
    return base


def render_qdii_premium_block(projection: dict) -> str:
    """Render the §6 marker block (AC7 / G-Q2).

    Empty projection → empty string (caller emits the legacy placeholder).
    Otherwise: MARKER_BEGIN + header + per-row bullets + MARKER_END,
    joined by newlines. Header carries `evidence_cutoff` + threshold.
    """
    rows = projection.get("rows") or []
    if not rows:
        return ""
    threshold_pct = float(projection.get("threshold_pct") or 0.0)
    cutoff = projection.get("evidence_cutoff") or "(未知)"
    header = (
        f"溢价/折价：QDII 候选标的二级市场偏离快照"
        f"（数据截止 {cutoff}，阈值 {threshold_pct * 100:.0f}%）："
    )
    body = [_format_row_bullet(r) for r in rows]
    return "\n".join([QDII_PREMIUM_MARKER_BEGIN, header, *body, QDII_PREMIUM_MARKER_END])


def format_qdii_premium_prefix(row: dict) -> str:
    """§7 hard-block prefix (AC9 / G-Q3).

    Empty string for non-blocking rows; the canonical
    `⛔ qdii_premium_too_high（{cell} > {threshold_pct*100:.0f}%，已暂缓）｜`
    string for blocking rows. Separator is full-width U+FF5C `｜` to
    distinguish from the existing half-width `|` bullet separators.
    """
    if not row.get("blocking"):
        return ""
    threshold_display = f"{QDII_PREMIUM_THRESHOLD_PCT * 100:.0f}%"
    return (
        f"⛔ qdii_premium_too_high（{row['render_cell']} > "
        f"{threshold_display}，已暂缓）｜"
    )


def write_qdii_premium_snapshot(projection: dict, *, out_dir: Path) -> None:
    """Write the top-level `qdii_premium.json` artefact (AC6 / G-Q5).

    Always-written invariant: even with empty `rows`, the file is written
    so a missing file becomes a build error rather than ambiguous "no
    QDII this week." Atomic via `atomic_write_text` (`.tmp.{pid} → os.replace`).

    Serialisation uses `sort_keys=True` and `ensure_ascii=False` for
    byte-stable Chinese names.
    """
    from irc.io_utils import atomic_write_text

    payload = json.dumps(
        projection, ensure_ascii=False, sort_keys=True, indent=2,
    )
    atomic_write_text(Path(out_dir) / "qdii_premium.json", payload + "\n")
