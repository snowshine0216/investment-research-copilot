#!/bin/bash
# Weekly launchd wrapper: unconditional FULL pipeline (Saturday), then notify.
# Fail-fast: one pipeline command, capture $? once, one notify-status call.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
mkdir -p outputs/_logs

rc=0
uv run irc run || rc=$?
uv run irc notify-status --run-kind weekly --last-exit-code "$rc"
