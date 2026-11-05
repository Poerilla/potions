#!/usr/bin/env bash
# Cron entry for the demo singleton audit (duplicate / unlocked / wrong-owner daemons).
# Alarms email via Resend (rate-limited per signature); exit 1 when any alarm is open.
#
#   */5 * * * * /home/tester/hsm/potions/scripts/demo_singleton_audit.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HSM="$(dirname "$ROOT")"
export PYTHONPATH="${HSM}:${ROOT}/v20-python/src${PYTHONPATH:+:$PYTHONPATH}"
export PATH="${HOME}/.local/bin:${HOME}/.pyenv/shims:${PATH}"
LOG="${ROOT}/live/demo/singleton_audit.log"

cd "$HSM"
{
  echo "=== $(date -Is)"
  python3 -m potions.live.cli demo-singleton-audit
  echo "exit=$?"
} >>"$LOG" 2>&1

if [ "$(wc -l <"$LOG")" -gt 20000 ]; then
  tail -n 10000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
