#!/bin/bash
# AC10: a radar failure must NOT change the wrapper's exit code (flow-capture rc
# is authoritative). Static shell-level checks over ops/launchd/run-flow-capture.sh
# (ADR 0023 D1/§9 wrapper chaining).
set -u
cd "$(dirname "$0")/../.." || exit 1
FAIL=0
grep -q 'does not affect flow-capture rc' ops/launchd/run-flow-capture.sh || {
  echo "FAIL: radar chain comment/marker missing"; FAIL=1; }
# The radar line must appear AFTER the flow-capture rc echo and use `|| radar_rc=$?`
awk '/flow-capture rc=/{seen=1} /irc rotation/{if(seen)ok=1} END{exit !ok}' \
  ops/launchd/run-flow-capture.sh || { echo "FAIL: radar runs before capture rc"; FAIL=1; }
grep -q '|| radar_rc=$?' ops/launchd/run-flow-capture.sh || {
  echo "FAIL: radar rc not isolated from set -e"; FAIL=1; }
grep -q 'exit "$rc"' ops/launchd/run-flow-capture.sh || {
  echo "FAIL: wrapper no longer exits with flow-capture rc"; FAIL=1; }
[ "$FAIL" -eq 0 ] && echo "PASS: AC10 wrapper chaining" || exit 1
