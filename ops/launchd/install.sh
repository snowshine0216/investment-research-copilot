#!/bin/bash
# Idempotent install: resolve uv, template __REPO_ROOT__ + __UV_BIN__ into
# the wrapper scripts and plists, copy to ~/Library/LaunchAgents, then
# bootout-then-bootstrap each LaunchAgent.
#
# Precondition: uv must be on PATH.  Install it first if absent:
#   curl -LsSf https://astral.sh/uv/install.sh | sh
set -euo pipefail

# ---- resolve uv (P0-2: launchd PATH is /usr/bin:/bin:/usr/sbin:/sbin) ----
UV_BIN="$(command -v uv 2>/dev/null || true)"
if [ -z "$UV_BIN" ]; then
  echo "ERROR: uv not found on PATH. Install uv first:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  echo "  Then re-run: bash ops/launchd/install.sh" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="$REPO_ROOT/ops/launchd"
DEST_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LABELS=("com.irc.monitor" "com.irc.fundamentals-quarterly" "com.irc.flow-capture")
WRAPPERS=("run-monitor.sh" "run-fundamentals.sh" "run-flow-capture.sh")

mkdir -p "$DEST_DIR"
mkdir -p "$REPO_ROOT/outputs/_logs"

# Remove legacy launchd-owned log files. The plists now log to /dev/null and the
# wrappers write their own run-*.log; the old launchd-{daily,weekly}.{out,err}.log
# carry the com.apple.provenance xattr that made launchd fail to reopen them
# (EX_CONFIG / 78). Drop them so nothing stale lingers. Also clear any stale lock.
rm -f "$REPO_ROOT/outputs/_logs"/launchd-daily.out.log \
      "$REPO_ROOT/outputs/_logs"/launchd-daily.err.log \
      "$REPO_ROOT/outputs/_logs"/launchd-weekly.out.log \
      "$REPO_ROOT/outputs/_logs"/launchd-weekly.err.log
rm -rf "$REPO_ROOT/outputs/_logs/.run.lock"

# Migration: boot out + remove the legacy jobs this vertical replaces
# (com.irc.daily / com.irc.weekly-full). Their wrapper scripts were deleted, so a
# stale LaunchAgent would fail on fire. Idempotent — ignore "not found".
for legacy in com.irc.daily com.irc.weekly-full; do
  if launchctl print "gui/$UID_NUM/$legacy" >/dev/null 2>&1; then
    launchctl bootout "gui/$UID_NUM/$legacy" 2>/dev/null || true
    echo "removed legacy job $legacy"
  fi
  rm -f "$DEST_DIR/$legacy.plist"
done

# Template wrapper scripts (resolve __REPO_ROOT__ + __UV_BIN__) into DEST_DIR.
for wrapper in "${WRAPPERS[@]}"; do
  sed -e "s#__REPO_ROOT__#$REPO_ROOT#g" \
      -e "s#__UV_BIN__#$UV_BIN#g" \
      "$SRC_DIR/$wrapper" > "$DEST_DIR/$wrapper"
  chmod +x "$DEST_DIR/$wrapper"
  bash -n "$DEST_DIR/$wrapper"
  echo "templated wrapper $wrapper → $DEST_DIR/$wrapper"
done

# Template plists (resolve __REPO_ROOT__) and redirect wrapper path to DEST_DIR.
for label in "${LABELS[@]}"; do
  src="$SRC_DIR/$label.plist"
  dest="$DEST_DIR/$label.plist"
  sed -e "s#__REPO_ROOT__/ops/launchd/#$DEST_DIR/#g" \
      -e "s#__REPO_ROOT__#$REPO_ROOT#g" \
      "$src" > "$dest"
  plutil -lint "$dest"
  # Idempotent: ignore "not found" on first install.
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$dest"
  echo "installed $label"
done

echo "Done. uv=$UV_BIN"
echo "Inspect with: launchctl print gui/$UID_NUM/com.irc.monitor"

# Cold-start: build the per-fund snapshot once so valuation/constituent factors
# aren't N/A on the first brief. The quarterly job maintains it thereafter.
echo "cold-start: irc monitor snapshot (one-time)…"
"$UV_BIN" run --directory "$REPO_ROOT" irc monitor snapshot || \
  echo "WARNING: cold-start snapshot failed — first brief may be degraded (factors N/A, surfaced)."

# P1: warn when the machine is not on UTC+8 — schedule assumes CN timezone.
_TZ_OFFSET="$(date +%z)"
if [ "$_TZ_OFFSET" != "+0800" ]; then
  echo ""
  echo "WARNING: your machine timezone offset is $_TZ_OFFSET (expected +0800)." >&2
  echo "  The launchd schedule fires at LOCAL time (12:15 daily)." >&2
  echo "  The monitor wrapper's trading-day gate runs in TZ='Asia/Shanghai'." >&2
  echo "  On a non-CN-TZ machine these two clocks disagree — runs may skip or" >&2
  echo "  shift. Edit Hour/Minute in the plists to match your local offset, or" >&2
  echo "  switch your machine to UTC+8 before installing. (ADR 0016)" >&2
fi
